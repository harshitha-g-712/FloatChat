"""
ArgoLens – Unified FastAPI Application
=======================================
Integrates rules-first intent parsing, offline RAG, deterministic answer generation,
data discovery endpoints, visualization layer, Argon2 security, and static frontend delivery.
"""

import copy
import hashlib
import json
import logging
from logging.handlers import RotatingFileHandler
import os
import re
import sys
import time
from collections import deque, OrderedDict
from contextvars import ContextVar
from pathlib import Path
from typing import Optional, List, Dict, Any

if sys.version_info < (3, 10):  # fail with a clear message instead of a SyntaxError/TypeError later
    sys.exit("FloatChat needs Python 3.10 or newer (found %s). Tested on Python 3.12." % sys.version.split()[0])

from dotenv import load_dotenv

# Load .env from project root or backend dir
PROJECT_ROOT = Path(__file__).resolve().parent.parent
load_dotenv(PROJECT_ROOT / ".env")
load_dotenv(Path(__file__).resolve().parent / ".env")

from fastapi import FastAPI, HTTPException, Request, Query, status, Response
# pyrefly: ignore[missing-import]
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field, field_validator

# FloatChat core modules
_BACKEND_DIR = str(Path(__file__).resolve().parent)
if _BACKEND_DIR not in sys.path:
    sys.path.insert(0, _BACKEND_DIR)

from config import (
    BASE_DIR, PROJECT_ROOT, DB_PATH, ALLOWED_ORIGINS,
    USE_LLM_EXPLANATION, coverage_label
)
from typo_tolerance import correct_typos
from region_guard import UNSUPPORTED_REGION_RE as _UNSUPPORTED_REGION_RE, knowledge_region_notice
from small_talk import small_talk_reply
from export_store import build_export_payload, resolve_result, csv_for_result
from answer_templates import build_answer
from retrieval.query_engine import retrieve, db_stats
from retrieval.nl_parser import parse_question as parse_question_intent
from retrieval.validators import validate_platform_id
from retrieval.discovery import (
    list_floats, float_summary, find_floats_near,
    coverage_summary, float_trajectory, trajectory_points, find_similar_profiles
)
from rag.indexer import answer_conceptual_query
from viz.charts import pick_chart
from gemini_service import init_gemini, is_gemini_available, generate_explanation as gemini_explain
from auth import (
    init_auth_db, register_user, login_user, validate_token, logout_user,
    save_message, get_conversations, get_conversation_messages, is_valid_conversation_id,
    delete_conversation, search_conversations, get_latest_export, conversation_owned,
    create_or_refresh_share, revoke_share, get_share_status, get_shared_chat,
    get_user_profile, update_user_username, change_user_password, revoke_all_user_sessions,
    request_password_reset, verify_and_reset_password,
    RegisterModel, LoginModel, ResetModel, UpdateUsernameModel, ChangePasswordModel,
    RequestResetModel, ConfirmResetModel
)

# ── Logging Setup (Rotating log in logs/) ──────────────────────────────────────
LOGS_DIR = PROJECT_ROOT / "logs"
LOGS_DIR.mkdir(parents=True, exist_ok=True)

file_handler = RotatingFileHandler(
    LOGS_DIR / "floatchat.log",
    maxBytes=5 * 1024 * 1024,
    backupCount=3,
    encoding="utf-8"
)
formatter = logging.Formatter("%(asctime)s  %(levelname)-8s  %(name)s  %(message)s")
file_handler.setFormatter(formatter)

stream_handler = logging.StreamHandler(sys.stdout)
stream_handler.setFormatter(formatter)

logging.basicConfig(
    level=logging.INFO,
    handlers=[stream_handler, file_handler]
)
logger = logging.getLogger("floatchat.api")
logging.getLogger("watchfiles").setLevel(logging.WARNING)

# ── Service Initializations (Safe startup) ────────────────────────────────────
init_auth_db()
init_gemini()

# Interactive API docs (/docs, /redoc, /openapi.json) are off unless ENABLE_DOCS=true.
_ENABLE_DOCS = os.getenv("ENABLE_DOCS", "false").strip().lower() in ("true", "1", "yes")

app = FastAPI(
    title="ArgoLens API",
    description="Conversational Interface for ARGO Ocean Data Discovery & Hydrodynamic Density Profiling",
    version="3.0.0",
    docs_url="/docs" if _ENABLE_DOCS else None,
    redoc_url="/redoc" if _ENABLE_DOCS else None,
    openapi_url="/openapi.json" if _ENABLE_DOCS else None,
)

DEFAULT_ORIGINS = [
    "http://127.0.0.1:8000",
    "http://localhost:8000",
    "http://127.0.0.1:5500",
    "http://localhost:5500",
]
_cors_origins = [o for o in ALLOWED_ORIGINS if o and o != "*"]
if not _cors_origins:
    _cors_origins = DEFAULT_ORIGINS

app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.middleware("http")
async def api_rate_limit_middleware(request: Request, call_next):
    # Apply a shared per-IP quota to every API route, including auth and export.
    if request.url.path.startswith("/api/") and request.url.path != "/api/health":
        try:
            _check_rate_limit(request)
        except HTTPException as exc:
            # Raised inside middleware an HTTPException is not converted to a response by FastAPI
            # (it would surface as a server error), so answer with the 429 directly.
            return JSONResponse({"detail": exc.detail}, status_code=exc.status_code, headers={"Retry-After": "60"})
    return await call_next(request)

# Content-Security-Policy: scripts only from this site and the Plotly CDN. FLOATCHAT_CSP selects
# "report-only" (default: log violations in the browser console, block nothing), "enforce" or "off".
_CSP = (
    "default-src 'self'; "
    "script-src 'self' https://cdn.plot.ly https://unpkg.com; "
    "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com https://unpkg.com; "
    "font-src 'self' https://fonts.gstatic.com data:; "
    "img-src 'self' data: blob: https://server.arcgisonline.com https://*.arcgisonline.com https://unpkg.com; "
    "connect-src 'self'; "
    "object-src 'none'; base-uri 'self'; frame-ancestors 'none'"
)


@app.middleware("http")
async def security_middleware(request: Request, call_next):
    """Reject oversized API bodies and add standard browser security headers."""
    if request.url.path.startswith("/api/") and request.method in ("POST", "PUT", "PATCH"):
        declared = request.headers.get("content-length")
        if declared and declared.isdigit() and int(declared) > _MAX_BODY_BYTES:
            return JSONResponse({"detail": "Request body too large."}, status_code=413)
    response = await call_next(request)
    response.headers.setdefault("X-Content-Type-Options", "nosniff")
    response.headers.setdefault("X-Frame-Options", "DENY")
    response.headers.setdefault("Referrer-Policy", "no-referrer")
    mode = os.getenv("FLOATCHAT_CSP", "report-only").strip().lower()
    if mode in ("enforce", "on", "true", "1"):
        response.headers.setdefault("Content-Security-Policy", _CSP)
    elif mode == "report-only":
        # Violations are only logged in the browser console; nothing is blocked.
        response.headers.setdefault("Content-Security-Policy-Report-Only", _CSP)
    return response


# ── Intent Cache (LRU + TTL, 256 entries, 1 hour) ─────────────────────────────
_INTENT_CACHE: OrderedDict[str, tuple[Dict[str, Any], float]] = OrderedDict()
_INTENT_CACHE_MAX = 256
_INTENT_CACHE_TTL = 3600.0


def _intent_cache_key(question: str, conv_id: Optional[str], history: List[Dict[str, Any]]) -> str:
    recent = [
        {"role": x.get("role"), "content": x.get("content", x.get("text", "")), "intent": x.get("intent", x.get("intent_summary"))}
        for x in history[-6:] if isinstance(x, dict)
    ]
    digest = hashlib.sha256(json.dumps(recent, sort_keys=True, default=str).encode()).hexdigest()[:12]
    return f"{question.lower()}||{conv_id or ''}||{digest}"


def _get_cached_intent(key: str) -> Optional[Dict[str, Any]]:
    if key in _INTENT_CACHE:
        intent, ts = _INTENT_CACHE[key]
        if time.time() - ts <= _INTENT_CACHE_TTL:
            _INTENT_CACHE.move_to_end(key)
            return copy.deepcopy(intent)
        else:
            del _INTENT_CACHE[key]
    return None


def _set_cached_intent(key: str, intent: Dict[str, Any]):
    if key in _INTENT_CACHE:
        _INTENT_CACHE[key] = (copy.deepcopy(intent), time.time())
        _INTENT_CACHE.move_to_end(key)
    else:
        if len(_INTENT_CACHE) >= _INTENT_CACHE_MAX:
            _INTENT_CACHE.popitem(last=False)
        _INTENT_CACHE[key] = (copy.deepcopy(intent), time.time())


def _get_client_ip(request: Request) -> str:
    trust_xff = os.getenv("TRUST_X_FORWARDED_FOR", "false").lower() in ("true", "1", "yes")
    if trust_xff:
        xff = request.headers.get("x-forwarded-for")
        if xff:
            return xff.split(",")[0].strip()
    return request.client.host if request.client else "127.0.0.1"


# ── Per-IP Rate Limiting ──────────────────────────────────────────────────────
_RATE_LIMITS: Dict[str, deque] = {}
_MAX_REQUESTS_PER_MINUTE = 120
_RATE_LAST_SWEEP = 0.0


def _check_rate_limit(request: Request):
    client_ip = _get_client_ip(request)
    now = time.time()

    # Evict idle IPs (no activity in 120s); sweep at most every 30s so the cost does not grow
    # with the number of tracked clients on every request.
    global _RATE_LAST_SWEEP
    if now - _RATE_LAST_SWEEP > 30:
        _RATE_LAST_SWEEP = now
        idle = [ip for ip, d in list(_RATE_LIMITS.items()) if not d or (now - d[-1] > 120)]
        for ip in idle:
            if ip != client_ip:
                _RATE_LIMITS.pop(ip, None)

    if client_ip not in _RATE_LIMITS:
        _RATE_LIMITS[client_ip] = deque()
    
    times = _RATE_LIMITS[client_ip]
    while times and now - times[0] > 60:
        times.popleft()
    
    if len(times) >= _MAX_REQUESTS_PER_MINUTE:
        logger.warning("Rate limit exceeded for IP: %s", client_ip)
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Too many requests. Please wait a moment."
        )
    times.append(now)


# ── Login Rate Limiting (Keyed by email + client IP, with looser per-email cap) ─
_LOGIN_ATTEMPTS: Dict[str, deque] = {}
_MAX_LOGIN_ATTEMPTS = 5
_LOGIN_WINDOW_SECONDS = 300.0  # 5 attempts per 5 minutes per (email, IP)

_EMAIL_LOGIN_ATTEMPTS: Dict[str, deque] = {}
_MAX_EMAIL_ATTEMPTS = 25
_EMAIL_WINDOW_SECONDS = 60.0  # 25 attempts per 1 minute per email overall (short cool-down)


def _login_attempt_key(email: str, ip: str = "127.0.0.1") -> str:
    return f"{email.lower().strip()}:{(ip or '127.0.0.1').strip()}"


def _check_login_attempts(email: str, ip: str = "127.0.0.1"):
    email_key = email.lower().strip()
    key = _login_attempt_key(email, ip)
    now = time.time()

    # 1. Check strict per-(email, IP) limit
    idle = [k for k, d in list(_LOGIN_ATTEMPTS.items()) if not d or (now - d[-1] > _LOGIN_WINDOW_SECONDS)]
    for k in idle:
        _LOGIN_ATTEMPTS.pop(k, None)

    if key not in _LOGIN_ATTEMPTS:
        _LOGIN_ATTEMPTS[key] = deque()

    attempts = _LOGIN_ATTEMPTS[key]
    while attempts and now - attempts[0] > _LOGIN_WINDOW_SECONDS:
        attempts.popleft()

    if len(attempts) >= _MAX_LOGIN_ATTEMPTS:
        logger.warning("Too many failed login attempts for %s from IP %s", email_key, ip)
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Too many failed login attempts. Please wait a few minutes before trying again."
        )

    # 2. Check looser per-email limit with short cool-down (distributed brute force guard)
    idle_email = [e for e, d in list(_EMAIL_LOGIN_ATTEMPTS.items()) if not d or (now - d[-1] > _EMAIL_WINDOW_SECONDS)]
    for e in idle_email:
        _EMAIL_LOGIN_ATTEMPTS.pop(e, None)

    if email_key not in _EMAIL_LOGIN_ATTEMPTS:
        _EMAIL_LOGIN_ATTEMPTS[email_key] = deque()

    email_attempts = _EMAIL_LOGIN_ATTEMPTS[email_key]
    while email_attempts and now - email_attempts[0] > _EMAIL_WINDOW_SECONDS:
        email_attempts.popleft()

    if len(email_attempts) >= _MAX_EMAIL_ATTEMPTS:
        logger.warning("Too many failed login attempts across IPs for email: %s", email_key)
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Too many failed login attempts for this account. Please wait a moment before trying again."
        )


def _record_login_failure(email: str, ip: str = "127.0.0.1"):
    email_key = email.lower().strip()
    key = _login_attempt_key(email, ip)
    now = time.time()
    if key not in _LOGIN_ATTEMPTS:
        _LOGIN_ATTEMPTS[key] = deque()
    _LOGIN_ATTEMPTS[key].append(now)

    if email_key not in _EMAIL_LOGIN_ATTEMPTS:
        _EMAIL_LOGIN_ATTEMPTS[email_key] = deque()
    _EMAIL_LOGIN_ATTEMPTS[email_key].append(now)


def _reset_login_attempts(email: str, ip: str = "127.0.0.1"):
    key = _login_attempt_key(email, ip)
    _LOGIN_ATTEMPTS.pop(key, None)
    _EMAIL_LOGIN_ATTEMPTS.pop(email.lower().strip(), None)


# ── Anonymous Multi-Turn Memory Store ─────────────────────────────────────────
_ANON_MAX_CONVS = 1000
_ANON_MAX_TURNS = 6
_ANON_TTL_SECS = 3600.0
_anon_memory: Dict[str, Dict[str, Any]] = {}


def _anon_add_turn(conv_id: str, role: str, text: str, intent_summary: Optional[Dict[str, Any]] = None):
    now = time.time()
    expired = [k for k, v in _anon_memory.items() if now - v["ts"] > _ANON_TTL_SECS]
    for k in expired:
        del _anon_memory[k]
    if conv_id not in _anon_memory and len(_anon_memory) >= _ANON_MAX_CONVS:
        oldest = min(_anon_memory, key=lambda k: _anon_memory[k]["ts"])
        del _anon_memory[oldest]
    if conv_id not in _anon_memory:
        _anon_memory[conv_id] = {"turns": deque(maxlen=_ANON_MAX_TURNS), "ts": now}
    _anon_memory[conv_id]["turns"].append(
        {"role": role, "text": text, "intent_summary": intent_summary}
    )
    _anon_memory[conv_id]["ts"] = now


def _anon_get_history(conv_id: str) -> List[Dict[str, Any]]:
    if not conv_id or conv_id not in _anon_memory:
        return []
    entry = _anon_memory[conv_id]
    if time.time() - entry["ts"] > _ANON_TTL_SECS:
        del _anon_memory[conv_id]
        return []
    return list(entry["turns"])


# ── Export Cache (Bounded, per owner) ────────────────────────────────────────
# Keys are namespaced by owner ("u<user id>:<conversation id>" or "g:<conversation id>") so a guest
# who sends someone else's conversation id can never read or overwrite that user's cached results.
_EXPORT_TTL_SECS = 3600.0
_EXPORT_CACHE_MAX = 200
_last_results: Dict[str, tuple[Dict[str, Any], float]] = {}


def _export_key(user: Optional[Dict[str, Any]], conv_id: str) -> str:
    return f"u{user['id']}:{conv_id}" if user else f"g:{conv_id}"


def _purge_export_cache(now: Optional[float] = None) -> None:
    now = time.time() if now is None else now
    for k in [k for k, (_, ts) in _last_results.items() if now - ts >= _EXPORT_TTL_SECS]:
        del _last_results[k]


def _save_export_result(user: Optional[Dict[str, Any]], conv_id: str, data: Dict[str, Any]):
    now = time.time()
    _purge_export_cache(now)                       # expired entries never linger
    key = _export_key(user, conv_id)
    while key not in _last_results and len(_last_results) >= _EXPORT_CACHE_MAX:
        del _last_results[min(_last_results, key=lambda k: _last_results[k][1])]
    _last_results[key] = (data, now)


def _get_export_result(user: Optional[Dict[str, Any]], conv_id: str) -> Optional[Dict[str, Any]]:
    key = _export_key(user, conv_id)
    entry = _last_results.get(key)
    if entry is None:
        return None
    data, ts = entry
    if time.time() - ts < _EXPORT_TTL_SECS:
        return data
    del _last_results[key]
    return None


def _clear_export_result(user: Optional[Dict[str, Any]], conv_id: str) -> None:
    _last_results.pop(_export_key(user, conv_id), None)


# ── Models ───────────────────────────────────────────────────────────────────

_MAX_HISTORY_ITEMS = 50
_MAX_HISTORY_ITEM_CHARS = 20000
_MAX_BODY_BYTES = 256 * 1024   # largest accepted API request body

class ChatRequest(BaseModel):
    message: Optional[str] = Field(None, max_length=500, description="User question")
    question: Optional[str] = Field(None, max_length=500, description="User question alias")
    conversation_id: Optional[str] = Field(None, description="Session ID")
    history: Optional[List[Dict[str, Any]]] = Field(None, max_length=_MAX_HISTORY_ITEMS, description="Optional history list")

    @field_validator("history")
    @classmethod
    def _check_history_size(cls, v):
        # The browser never sends history (the server loads it); cap it so a caller cannot
        # push megabytes of text through the parser and the intent cache key.
        if v:
            for item in v:
                if len(json.dumps(item, default=str)) > _MAX_HISTORY_ITEM_CHARS:
                    raise ValueError(f"each history entry must be under {_MAX_HISTORY_ITEM_CHARS} characters")
        return v

    @field_validator("conversation_id")
    @classmethod
    def _check_conversation_id(cls, v):
        if v is not None and not is_valid_conversation_id(v):
            raise ValueError("conversation_id must be 1-64 characters: letters, digits, '-' or '_'")
        return v

    def get_query(self) -> str:
        q = self.message or self.question or ""
        return q.strip()



class StatResult(BaseModel):
    stat: str
    value: float
    parameter: str


class ChatResponse(BaseModel):
    answer: str
    variable: Optional[str] = None
    units: Optional[str] = None
    observation_count: int = 0
    applied_filters: Dict[str, Any] = {}
    stat: Optional[StatResult] = None
    chart_type: Optional[str] = None
    chart_data: Optional[str] = None
    data_source: str = "ARGO via Argovis API (Bay of Bengal)"
    date_range: Optional[str] = None
    conversation_id: Optional[str] = None
    ambiguous: bool = False
    clarification_needed: Optional[str] = None
    sources: Optional[List[str]] = None
    answer_mode: str = "basic"
    task: str = "stat"
    discovery_data: Optional[Dict[str, Any]] = None
    parser_used: Optional[str] = None
    question_kind: Optional[str] = None
    interpreted_as: Optional[str] = None
    context_note: Optional[str] = None
    # Technology metadata — lets the frontend show which tech stack powered this response
    technologies_used: Optional[List[str]] = None
    rag_mode: Optional[str] = None


class ExportRequest(BaseModel):
    conversation_id: Optional[str] = None
    data_type: Optional[str] = "chat"
    platform: Optional[str] = None


# ── Helper: Format Date Range ─────────────────────────────────────────────────

def _date_range_str(filters: dict) -> Optional[str]:
    year = filters.get("year")
    if not year:
        return None
    month = filters.get("month")
    month_names = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
    start = f"{month_names[month-1]} {year}" if month and 1 <= month <= 12 else str(year)
    year_end = filters.get("year_end")
    month_end = filters.get("month_end")
    if year_end and (year_end != year or (month_end and month_end != month)):
        end = f"{month_names[month_end-1]} {year_end}" if month_end and 1 <= month_end <= 12 else str(year_end)
        return f"{start} – {end}"
    return start


def _get_current_user(request: Request) -> Optional[dict]:
    auth = request.headers.get("Authorization", "")
    if auth.startswith("Bearer "):
        user = validate_token(auth[7:].strip())
        if not user:
            raise HTTPException(status_code=401, detail="Invalid or expired token")
        return user
    return None


_MAX_SAVED_CHART_CHARS = 300_000


def _history_payload(response: "ChatResponse", intent: dict) -> Dict[str, Any]:
    """Payload stored with an assistant message so reopened chats can redraw charts.

    chart_data is kept unless it is very large, in which case it is dropped to keep the
    history database small (the text answer is always kept).
    """
    payload = response.model_dump()
    chart = payload.get("chart_data")
    if isinstance(chart, str) and len(chart) > _MAX_SAVED_CHART_CHARS:
        payload["chart_data"] = None
    payload["intent"] = intent
    return payload


def _safe_export_payload(task: str, intent: dict, result: dict) -> Optional[str]:
    """Export payload for the history DB; a failure here must never break the chat reply."""
    try:
        return build_export_payload(task, intent, result)
    except Exception:
        logger.exception("Could not build export payload")
        return None


# The question as corrected by the typo step (None when nothing was corrected). The history keeps
# the user's original text; the reply shows what was actually answered.
_INTERPRETED: ContextVar[Optional[str]] = ContextVar("floatchat_interpreted", default=None)


# Settings (period, depth, float ...) a follow-up question took over from the previous question.
_INHERITED_NOTE: ContextVar[Optional[str]] = ContextVar("floatchat_inherited_note", default=None)

_MONTH_ABBR = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]


def _describe_inherited(intent: Dict[str, Any]) -> Optional[str]:
    """Human wording of the filters carried over from the previous question (None if none)."""
    keys = intent.get("inherited") or []
    if not keys:
        return None
    parts: List[str] = []
    year, month = intent.get("year"), intent.get("month")
    if ("year" in keys or "month" in keys) and (year or month):
        m = f"{_MONTH_ABBR[month - 1]} " if isinstance(month, int) and 1 <= month <= 12 else ""
        y = str(year) if year else ""
        end = f"–{intent['year_end']}" if "year_end" in keys and intent.get("year_end") else ""
        parts.append(f"{m}{y}{end}".strip())
    if "pressure_min" in keys or "pressure_max" in keys:
        lo, hi = intent.get("pressure_min"), intent.get("pressure_max")
        if lo is not None and hi is not None:
            parts.append(f"{lo:g}–{hi:g} dbar")
        elif lo is not None:
            parts.append(f"deeper than {lo:g} dbar")
        elif hi is not None:
            parts.append(f"shallower than {hi:g} dbar")
    if "platform_id" in keys and intent.get("platform_id"):
        parts.append(f"float {intent['platform_id']}")
    if "named_region" in keys and intent.get("named_region"):
        parts.append(str(intent["named_region"]))
    if "variable" in keys and intent.get("variable"):
        parts.append(str(intent["variable"]))
    if "stat" in keys and intent.get("stat") not in (None, "none"):
        parts.append(str(intent["stat"]))
    parts = [p for p in parts if p]
    if not parts:
        return None
    return ("Carried over from your previous question: " + ", ".join(parts)
            + ". Name the period, depth or float explicitly (or start a new chat) to change it.")


def _annotate_interpreted(response: "ChatResponse") -> "ChatResponse":
    """Append 'Interpreted as: ...' (typo correction) and the carried-over-filters note (idempotent)."""
    interpreted = _INTERPRETED.get()
    if interpreted and response.interpreted_as is None:
        response.interpreted_as = interpreted
        response.answer = f"{response.answer.rstrip()}\n\nInterpreted as: \"{interpreted}\""
    note = _INHERITED_NOTE.get()
    if note and response.context_note is None:
        response.context_note = note
        response.answer = f"{response.answer.rstrip()}\n\n({note})"
    # Populate technology badges for the frontend
    if response.technologies_used is None:
        techs = ["NLP"]   # every response uses NLP (intent parsing)
        if response.parser_used == "llm" or response.answer_mode == "gemini":
            techs.append("GenAI/LLM")
        if response.rag_mode:
            techs.append("RAG")
        if response.chart_data:
            techs.append("Data Visualization")
        response.technologies_used = techs
    return response


def _persist_early_chat_response(response: "ChatResponse", current_user: Optional[dict],
                                conv_id: Optional[str], question: str, intent: dict) -> "ChatResponse":
    """Persist assistant replies from validation/early-exit branches too."""
    _annotate_interpreted(response)
    if current_user and conv_id:
        try:
            save_message(conv_id, current_user["id"], "assistant", response.answer, response_data=_history_payload(response, intent))
        except PermissionError:
            raise HTTPException(status_code=404, detail="Conversation not found")
    elif conv_id:
        _anon_add_turn(conv_id, "assistant", response.answer, intent_summary=intent)
    return response


# ── Health Endpoint ───────────────────────────────────────────────────────────

@app.get("/api/health")
def api_health():
    """Readiness probe. Safe and fast without external API calls."""
    stats = db_stats()
    gemini_avail = is_gemini_available()
    from config import RAG_MODE
    return {
        "status": "ok",
        "answer_mode": "gemini" if gemini_avail else "basic",
        "gemini_ready": gemini_avail,
        "rag_mode": RAG_MODE if gemini_avail else "tfidf",
        "technologies": {
            "nlp": "rule-based intent parser + typo tolerance",
            "genai_llm": f"Gemini (active)" if gemini_avail else "offline (rules-only)",
            "rag": f"{RAG_MODE} retrieval" + (" + LLM generation" if gemini_avail else " + template"),
            "data_visualization": "Plotly.js interactive charts",
        },
        "db": stats,
    }


# ── Auth Endpoints ────────────────────────────────────────────────────────────

@app.post("/api/register")
def api_register(req: RegisterModel, request: Request):
    result = register_user(req.username, req.email, req.password)
    if "error" in result:
        raise HTTPException(status_code=400, detail=result["error"])
    # Identical response for a new and an already-registered email (no account enumeration),
    # so there is no auto-login: the client sends the user to the sign-in form.
    return {"ok": True, "message": "Account request received. Please sign in with your email and password."}


@app.post("/api/login")
def api_login(req: LoginModel, request: Request):
    ip = _get_client_ip(request)
    _check_login_attempts(req.email, ip)
    result = login_user(req.email, req.password)
    if "error" in result:
        _record_login_failure(req.email, ip)
        raise HTTPException(status_code=401, detail=result["error"])
    _reset_login_attempts(req.email, ip)
    return result


@app.post("/api/forgot-password")
def api_forgot_password(req: RequestResetModel, request: Request):
    res = request_password_reset(req.email)
    if "error" in res:
        raise HTTPException(status_code=400, detail=res["error"])
    return res


@app.post("/api/reset-password")
def api_reset_password(req: ConfirmResetModel, request: Request):
    res = verify_and_reset_password(req.email, req.reset_code, req.new_password)
    if "error" in res:
        raise HTTPException(status_code=400, detail=res["error"])
    return res


@app.post("/api/logout")
def api_logout(request: Request):
    auth = request.headers.get("Authorization", "")
    if auth.startswith("Bearer "):
        logout_user(auth[7:].strip())
    return {"status": "ok"}


@app.get("/api/me")
def api_me(request: Request):
    user = _get_current_user(request)
    if not user:
        raise HTTPException(status_code=401, detail="Not authenticated")
    profile = get_user_profile(user["id"])
    combined = profile or user
    if "session_expires_at" in user:
        combined["session_expires_at"] = user["session_expires_at"]
    if "session_remaining_seconds" in user:
        combined["session_remaining_seconds"] = user["session_remaining_seconds"]
    return {"user": combined}


@app.put("/api/profile/username")
def api_update_username(req: UpdateUsernameModel, request: Request):
    user = _get_current_user(request)
    if not user:
        raise HTTPException(status_code=401, detail="Not authenticated")
    res = update_user_username(user["id"], req.username)
    if "error" in res:
        raise HTTPException(status_code=400, detail=res["error"])
    return res


@app.post("/api/profile/password")
def api_change_password(req: ChangePasswordModel, request: Request):
    user = _get_current_user(request)
    if not user:
        raise HTTPException(status_code=401, detail="Not authenticated")
    res = change_user_password(user["id"], req.old_password, req.new_password)
    if "error" in res:
        raise HTTPException(status_code=400, detail=res["error"])
    return {"ok": True, "message": "Password updated successfully."}


@app.post("/api/profile/logout-all")
def api_logout_all(request: Request):
    user = _get_current_user(request)
    if not user:
        raise HTTPException(status_code=401, detail="Not authenticated")
    count = revoke_all_user_sessions(user["id"])
    return {"ok": True, "message": f"Revoked {count} active session(s)."}


# ── Discovery Endpoints ───────────────────────────────────────────────────────

@app.get("/api/map/points")
def api_map_points(
    request: Request,
    platform: Optional[str] = None,
    year: Optional[int] = None,
    month: Optional[int] = None,
    region: Optional[str] = None,
    limit: int = 2000
):
    """Return geospatial points of ARGO profiles for interactive mapping."""
    import sqlite3
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        sql = """
            SELECT p.id, p.platform, p.lat, p.lon, p.timestamp, p.region,
                   (SELECT temperature FROM measurements m WHERE m.profile_id = p.id AND m.temperature IS NOT NULL AND m.pressure <= 20 ORDER BY m.pressure ASC LIMIT 1) as surface_temp,
                   (SELECT salinity FROM measurements m WHERE m.profile_id = p.id AND m.salinity IS NOT NULL AND m.pressure <= 20 ORDER BY m.pressure ASC LIMIT 1) as surface_sal,
                   (SELECT MAX(pressure) FROM measurements m WHERE m.profile_id = p.id) as max_depth
            FROM profiles p
            WHERE p.lat IS NOT NULL AND p.lon IS NOT NULL
        """
        params = []
        plat = validate_platform_id(platform) if platform else None
        if plat:
            sql += " AND p.platform = ?"
            params.append(plat)
        if year:
            if month:
                sql += " AND p.timestamp >= ? AND p.timestamp < ?"
                params.extend([f"{year:04d}-{month:02d}-01", f"{year:04d}-{month+1:02d}-01" if month < 12 else f"{year+1:04d}-01-01"])
            else:
                sql += " AND p.timestamp >= ? AND p.timestamp < ?"
                params.extend([f"{year:04d}-01-01", f"{year+1:04d}-01-01"])
        elif month:
            sql += " AND CAST(SUBSTR(p.timestamp, 6, 2) AS INTEGER) = ?"
            params.append(month)

        if region:
            sql += " AND p.region LIKE ?"
            params.append(f"%{region}%")

        sql += " ORDER BY p.timestamp ASC LIMIT ?"
        params.append(int(limit))

        rows = conn.execute(sql, params).fetchall()

        plat_rows = conn.execute("SELECT DISTINCT platform FROM profiles WHERE lat IS NOT NULL AND lon IS NOT NULL ORDER BY platform ASC").fetchall()
        platforms = [r[0] for r in plat_rows if r[0]]

        points = []
        for r in rows:
            points.append({
                "id": r["id"],
                "platform": r["platform"],
                "lat": round(r["lat"], 4),
                "lon": round(r["lon"], 4),
                "timestamp": r["timestamp"],
                "surface_temp": round(r["surface_temp"], 2) if r["surface_temp"] is not None else None,
                "surface_sal": round(r["surface_sal"], 2) if r["surface_sal"] is not None else None,
                "max_depth": round(r["max_depth"], 1) if r["max_depth"] is not None else None,
                "region": r["region"],
            })

        return {
            "points": points,
            "count": len(points),
            "platforms": platforms
        }
    finally:
        conn.close()


@app.get("/api/floats")
def api_list_floats(request: Request, year: Optional[int] = None, month: Optional[int] = None, month_end: Optional[int] = None, region: Optional[str] = None):
    """List ARGO floats with coverage metadata."""
    filters = {}
    if year:
        filters["year"] = year
    if month:
        filters["month"] = month
    if month_end:
        filters["month_end"] = month_end
    if region:
        filters["named_region"] = region
    floats = list_floats(filters)
    return {"floats": floats, "count": len(floats)}


@app.get("/api/floats/{platform}")
def api_float_detail(platform: str, request: Request):
    """Get detailed profile and statistics for a specific float."""
    summary = float_summary(platform)
    if not summary:
        raise HTTPException(status_code=404, detail=f"Float {platform} not found")
    traj = float_trajectory(platform)
    return {"summary": summary, "trajectory": traj}


@app.get("/api/floats/{platform}/dive-profile")
def api_float_dive_profile(platform: str, request: Request):
    """Vertical dive profile of a float's most recent profile that has measurements.

    Adds sound speed (Mackenzie 1981), mixed layer depth, thermocline and SOFAR axis.
    See retrieval/dive_profile.py for the exact methods and when a value is "not resolved".
    """
    import sqlite3
    from retrieval.dive_profile import build_dive_profile

    plat = validate_platform_id(platform)
    if not plat:
        raise HTTPException(status_code=404, detail=f"Invalid or unknown float platform ID: {platform}")

    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        known = conn.execute("SELECT 1 FROM profiles WHERE platform = ? LIMIT 1", (plat,)).fetchone()
        if not known:
            raise HTTPException(status_code=404, detail=f"Float {plat} is not in this dataset")
        # Newest profile that actually has measurements (the very latest one can be empty).
        prof = conn.execute("""
            SELECT p.id, p.platform, p.lat, p.lon, p.timestamp
            FROM profiles p
            WHERE p.platform = ?
              AND EXISTS (SELECT 1 FROM measurements m
                          WHERE m.profile_id = p.id AND m.pressure IS NOT NULL
                            AND (m.temperature IS NOT NULL OR m.salinity IS NOT NULL))
            ORDER BY p.timestamp DESC
            LIMIT 1
        """, (plat,)).fetchone()
        if not prof:
            raise HTTPException(status_code=404, detail=f"Float {plat} has no profiles with measurements")

        cols = {r[1] for r in conn.execute("PRAGMA table_info(measurements)").fetchall()}
        qc_cols = ", temp_qc, sal_qc" if "temp_qc" in cols else ""
        rows = conn.execute(f"""
            SELECT pressure, temperature, salinity{qc_cols}
            FROM measurements
            WHERE profile_id = ? AND pressure IS NOT NULL
            ORDER BY pressure ASC
        """, (prof["id"],)).fetchall()
        result = build_dive_profile(rows, prof["lat"])
        return {
            "platform": plat,
            "profile_id": prof["id"],
            "timestamp": prof["timestamp"],
            "lat": round(prof["lat"], 3) if prof["lat"] is not None else None,
            "lon": round(prof["lon"], 3) if prof["lon"] is not None else None,
            **result,
        }
    finally:
        conn.close()


@app.get("/api/floats/{platform}/ts-diagram")
def api_float_ts_diagram(platform: str, request: Request):
    """Temperature-Salinity (T-S) diagram with potential density isopycnals and water masses."""
    import sqlite3
    from retrieval.dive_profile import build_dive_profile, potential_density_unesco

    plat = validate_platform_id(platform)
    if not plat:
        raise HTTPException(status_code=400, detail="Invalid float platform ID (must be a 7-digit WMO ID)")

    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        prof = conn.execute("""
            SELECT p.id, p.platform, p.lat, p.lon, p.timestamp
            FROM profiles p
            WHERE p.platform = ?
              AND EXISTS (SELECT 1 FROM measurements m
                          WHERE m.profile_id = p.id AND m.pressure IS NOT NULL
                            AND m.temperature IS NOT NULL AND m.salinity IS NOT NULL)
            ORDER BY p.timestamp DESC
            LIMIT 1
        """, (plat,)).fetchone()
        if not prof:
            raise HTTPException(status_code=404, detail=f"Float {plat} has no complete T-S profiles")

        cols = {r[1] for r in conn.execute("PRAGMA table_info(measurements)").fetchall()}
        qc_cols = ", temp_qc, sal_qc" if "temp_qc" in cols else ""
        rows = conn.execute(f"""
            SELECT pressure, temperature, salinity{qc_cols}
            FROM measurements
            WHERE profile_id = ? AND pressure IS NOT NULL
              AND temperature IS NOT NULL AND salinity IS NOT NULL
            ORDER BY pressure ASC
        """, (prof["id"],)).fetchall()
        dive = build_dive_profile(rows, prof["lat"])

        # Compute background isopycnal curves for T-S grid (salinity 30..36.5, sigma 20..27.5)
        isopycnals = []
        target_sigmas = [20.0, 21.0, 22.0, 23.0, 24.0, 25.0, 26.0, 27.0, 27.5]
        for sig_target in target_sigmas:
            curve_pts = []
            for s_val in [30.0, 31.0, 32.0, 33.0, 34.0, 34.5, 35.0, 35.5, 36.0, 36.5]:
                t_low, t_high = -2.0, 33.0
                for _ in range(20):
                    t_mid = (t_low + t_high) / 2.0
                    sig_mid = potential_density_unesco(t_mid, s_val)
                    if sig_mid > sig_target:
                        t_low = t_mid
                    else:
                        t_high = t_mid
                if 0.0 <= t_mid <= 32.0:
                    curve_pts.append({"salinity": s_val, "temperature": round(t_mid, 2)})
            if len(curve_pts) >= 2:
                isopycnals.append({
                    "sigma_theta": sig_target,
                    "points": curve_pts
                })

        return {
            "platform": plat,
            "profile_id": prof["id"],
            "timestamp": prof["timestamp"],
            "lat": round(prof["lat"], 3) if prof["lat"] is not None else None,
            "lon": round(prof["lon"], 3) if prof["lon"] is not None else None,
            "levels": dive["levels"],
            "mixed_layer_depth_temp": dive.get("mixed_layer_depth"),
            "mixed_layer_depth_density": dive.get("mixed_layer_depth_density"),
            "barrier_layer_thickness": dive.get("barrier_layer_thickness"),
            "isopycnals": isopycnals,
        }
    finally:
        conn.close()




@app.get("/api/coverage")
def api_coverage(request: Request):
    """Return overview coverage stats for the database."""
    return coverage_summary()


# ── Conversation History ──────────────────────────────────────────────────────

@app.get("/api/conversations")
def api_conversations(request: Request, limit: Optional[int] = Query(None, ge=1)):
    """All of the user's conversations; ``limit`` is optional paging (no maximum)."""
    user = _get_current_user(request)
    if not user:
        raise HTTPException(status_code=401, detail="Not authenticated")
    return {"conversations": get_conversations(user["id"], limit=limit)}


@app.get("/api/conversations/search")
def api_search_conversations(request: Request, q: str = "", limit: Optional[int] = Query(None, ge=1)):
    user = _get_current_user(request)
    if not user:
        raise HTTPException(status_code=401, detail="Not authenticated")
    return {"conversations": search_conversations(user["id"], q.strip(), limit=limit)}


@app.get("/api/conversations/{conv_id}/messages")
def api_conversation_messages(conv_id: str, request: Request):
    user = _get_current_user(request)
    if not user:
        raise HTTPException(status_code=401, detail="Not authenticated")
    if not is_valid_conversation_id(conv_id):
        raise HTTPException(status_code=404, detail="Conversation not found")
    return {"messages": get_conversation_messages(conv_id, user["id"])}


@app.delete("/api/conversations/{conv_id}")
def api_delete_conversation(conv_id: str, request: Request):
    user = _get_current_user(request)
    if not user:
        raise HTTPException(status_code=401, detail="Not authenticated")
    if not is_valid_conversation_id(conv_id):
        raise HTTPException(status_code=404, detail="Conversation not found")
    if not delete_conversation(conv_id, user["id"]):
        raise HTTPException(status_code=404, detail="Conversation not found")
    _clear_export_result(user, conv_id)
    return {"status": "ok"}


# ── Share a chat (read-only public snapshot link) ─────────────────────────────

@app.get("/api/conversations/{conv_id}/share")
def api_share_status(conv_id: str, request: Request):
    user = _get_current_user(request)
    if not user:
        raise HTTPException(status_code=401, detail="Not authenticated")
    if not is_valid_conversation_id(conv_id) or not conversation_owned(conv_id, user["id"]):
        raise HTTPException(status_code=404, detail="Conversation not found")
    token = get_share_status(conv_id, user["id"])
    return {"shared": bool(token), "token": token}


@app.post("/api/conversations/{conv_id}/share")
def api_share_create(conv_id: str, request: Request):
    """Create the share link (or refresh its snapshot to include newer messages)."""
    user = _get_current_user(request)
    if not user:
        raise HTTPException(status_code=401, detail="Not authenticated")
    if not is_valid_conversation_id(conv_id) or not conversation_owned(conv_id, user["id"]):
        raise HTTPException(status_code=404, detail="Conversation not found")
    shared = create_or_refresh_share(conv_id, user["id"])
    if not shared:
        raise HTTPException(status_code=400, detail="This chat has no messages to share yet.")
    return {"shared": True, "token": shared["token"], "path": f"/?share={shared['token']}"}


@app.delete("/api/conversations/{conv_id}/share")
def api_share_revoke(conv_id: str, request: Request):
    user = _get_current_user(request)
    if not user:
        raise HTTPException(status_code=401, detail="Not authenticated")
    if not is_valid_conversation_id(conv_id) or not revoke_share(conv_id, user["id"]):
        raise HTTPException(status_code=404, detail="Conversation not found")
    return {"shared": False}


@app.get("/api/shared/{token}")
def api_shared_chat(token: str):
    """Public, read-only: no sign-in needed. Unknown or revoked tokens look identical (404)."""
    chat = get_shared_chat(token)
    if not chat:
        raise HTTPException(status_code=404, detail="This shared chat does not exist or is no longer shared.")
    return JSONResponse(chat, headers={"Cache-Control": "no-store", "X-Robots-Tag": "noindex, nofollow"})


# ── Main Chat Pipeline (/api/chat) ────────────────────────────────────────────

SINGLE_LEVEL_TOLERANCE_DBAR = 10.0
# Small talk (greetings, "how are you", thanks, goodbye, help) is handled by small_talk.py.
_BARE_SEASON_RE = re.compile(r"\b(winter|summer|spring|autumn)\b", re.IGNORECASE)
_EXTREME_MONTH_RE = re.compile(
    r"(?:\b(warmest|hottest|coldest|coolest|saltiest|freshest|most saline|least saline)\s+(?:month|period)\b"
    r"|\b(?:which|what)\s+month\s+(?:was|is|has been)?\s*(?:the\s+)?(warmest|hottest|coldest|coolest|saltiest|freshest|most saline|least saline)\b)",
    re.IGNORECASE,
)
_EXTREME_MONTH_SPEC = {   # word -> (variable, highest?, label)
    "warmest": ("temperature", True, "warmest"), "hottest": ("temperature", True, "warmest"),
    "coldest": ("temperature", False, "coldest"), "coolest": ("temperature", False, "coolest"),
    "saltiest": ("salinity", True, "saltiest"), "most saline": ("salinity", True, "saltiest"),
    "freshest": ("salinity", False, "freshest"), "least saline": ("salinity", False, "freshest"),
}


def _extreme_month_answer(word: str, intent: Optional[dict] = None) -> Optional[str]:
    """Rank calendar months by their mean upper-50-dbar value (same default depth as other averages)."""
    import sqlite3 as _sq
    from datetime import datetime as _dt
    from config import DB_PATH as _DB
    variable, highest, label = _EXTREME_MONTH_SPEC[word.lower()]
    units = {"temperature": "°C", "salinity": "PSU"}[variable]

    sql = (
        f"SELECT substr(p.timestamp,1,7) AS ym, AVG(m.{variable}), COUNT(m.{variable}) "
        f"FROM measurements m JOIN profiles p ON p.id = m.profile_id "
        f"WHERE m.pressure <= 50 AND m.{variable} IS NOT NULL"
    )
    params = []

    year = intent.get("year") if intent else None
    year_end = intent.get("year_end") if intent else None
    if year:
        if year_end and year_end != year:
            sql += " AND substr(p.timestamp,1,4) >= ? AND substr(p.timestamp,1,4) <= ?"
            params.extend([str(year), str(year_end)])
        else:
            sql += " AND substr(p.timestamp,1,4) = ?"
            params.append(str(year))

    named_region = intent.get("named_region") if intent else None
    if named_region:
        reg = str(named_region).lower()
        if "north" in reg:
            sql += " AND p.lat >= ?"; params.append(15.0)
        elif "south" in reg:
            sql += " AND p.lat <= ?"; params.append(10.0)
        elif "central" in reg:
            sql += " AND p.lat > ? AND p.lat < ?"; params.extend([10.0, 15.0])
        elif "andaman" in reg:
            sql += " AND p.lon >= ?"; params.append(92.0)
        elif "sri lanka" in reg:
            sql += " AND p.lon <= ? AND p.lat <= ?"; params.extend([82.5, 10.0])
        else:
            sql += " AND p.region LIKE ?"; params.append(f"%{named_region}%")

    if intent and intent.get("region_lat") is not None and intent.get("region_lon") is not None:
        rad = intent.get("region_radius_deg") or 2.0
        sql += " AND p.lat BETWEEN ? AND ? AND p.lon BETWEEN ? AND ?"
        params.extend([intent["region_lat"] - rad, intent["region_lat"] + rad, intent["region_lon"] - rad, intent["region_lon"] + rad])

    sql += " GROUP BY ym ORDER BY ym"

    conn = _sq.connect(_DB)
    try:
        rows = conn.execute(sql, params).fetchall()
    finally:
        conn.close()

    rows = [r for r in rows if r[0] and r[2]]
    if not rows:
        return None

    scope_parts = []
    if named_region:
        scope_parts.append(f"in {named_region}")
    if year:
        if year_end and year_end != year:
            scope_parts.append(f"between {year} and {year_end}")
        else:
            scope_parts.append(f"in {year}")
    scope_str = (" " + " ".join(scope_parts)) if scope_parts else " in the dataset"

    best = max(rows, key=lambda r: r[1]) if highest else min(rows, key=lambda r: r[1])
    name = lambda ym: _dt.strptime(ym, "%Y-%m").strftime("%B %Y")
    by_month = "; ".join(f"{name(r[0])}: {r[1]:.2f} {units}" for r in rows)
    return (f"The {label} month{scope_str} was {name(best[0])}, with a mean {variable} of {best[1]:.2f} {units} "
            f"at depths up to 50 dbar ({best[2]:,} observations). Monthly means: {by_month}. "
            f"The dataset only covers {name(rows[0][0])} to {name(rows[-1][0])}.")


def _missing_id_message(intent: dict) -> Optional[str]:
    """Explain a float/profile ID that is well-formed but not in the dataset (instead of a misleading 'no temperature data')."""
    import sqlite3 as _sq
    from config import DB_PATH as _DB
    pid, prof = intent.get("platform_id"), intent.get("profile_id")
    if not ((isinstance(pid, str) and pid.isdigit()) or isinstance(prof, str)):
        return None
    conn = _sq.connect(_DB)
    try:
        if isinstance(prof, str) and prof:
            if conn.execute("SELECT 1 FROM profiles WHERE id = ?", (prof,)).fetchone():
                return None
            base = prof.split("_")[0]
            ex = conn.execute("SELECT id FROM profiles WHERE platform = ? ORDER BY id LIMIT 3", (base,)).fetchall()
            hint = f" Float {base} has profile IDs such as {', '.join(r[0] for r in ex)}." if ex else \
                f" Float {base} is not in the dataset either."
            return f"Profile {prof} is not in this dataset.{hint}"
        if conn.execute("SELECT 1 FROM profiles WHERE platform = ?", (pid,)).fetchone():
            return None
        n = conn.execute("SELECT COUNT(DISTINCT platform) FROM profiles").fetchone()[0]
        ex = conn.execute("SELECT DISTINCT platform FROM profiles ORDER BY platform LIMIT 3").fetchall()
        return (f"Float {pid} is not in this dataset. It contains {n} floats (for example {', '.join(r[0] for r in ex)}). "
                "Ask 'List floats' to see all of them.")
    finally:
        conn.close()


def _missing_target_message(task: str, intent: dict) -> Optional[str]:
    """Ask for an ID (with real examples from the database) instead of answering about 'float None'."""
    need_float = task in ("trajectory", "float_detail") and not intent.get("platform_id")
    need_profile = task == "similar_profiles" and not intent.get("profile_id")
    if not (need_float or need_profile):
        return None
    import sqlite3 as _sq
    from config import DB_PATH as _DB
    conn = _sq.connect(_DB)
    try:
        if need_float:
            ex = [r[0] for r in conn.execute("SELECT DISTINCT platform FROM profiles ORDER BY platform LIMIT 3")]
            hint = f" (for example {', '.join(ex)})" if ex else ""
            what = {"trajectory": "trace a trajectory", "float_detail": "show float details"}[task]
            return (f"Which float? To {what} I need a 7-digit float ID{hint}. "
                    "Ask 'List floats' to see every float in the dataset.")
        ex = [r[0] for r in conn.execute("SELECT id FROM profiles ORDER BY id LIMIT 2")]
        hint = f" such as {', '.join(ex)}" if ex else ""
        return f"Which profile? To find similar profiles I need a profile ID{hint}."
    finally:
        conn.close()


def _question_guard(question: str, qlow: str, intent: dict):
    """Return (answer, clarification_or_None) when the question must NOT be run as a normal data query.

    * greetings get a friendly reply instead of an off-topic refusal;
    * regions the dataset does not cover are refused instead of silently answered with Bay of Bengal data;
    * bare season words ("winter") are ambiguous: ask instead of silently ignoring them.
    Knowledge/concept questions are never blocked.
    """
    chat_reply = small_talk_reply(question, coverage_label())
    if chat_reply:
        return (chat_reply, None)
    if intent.get("question_kind", "data") != "data" or intent.get("task") == "concept" or intent.get("is_conceptual"):
        return None
    m = _UNSUPPORTED_REGION_RE.search(qlow)
    if m:
        label = m.group(1).title()
        return (f"This dataset only covers the Bay of Bengal, so it has no observations for the {label}. "
                "I won't answer with Bay of Bengal data instead. Ask the same question for the Bay of Bengal "
                "or one of its sub-regions (north, central, south, Sri Lanka).",
                "Choose a region covered by the dataset.")
    m = _EXTREME_MONTH_RE.search(qlow)
    if m:
        word = (m.group(1) or m.group(2)).lower()
        text = _extreme_month_answer(word, intent=intent)
        if text:
            return (text, None)
    missing = _missing_id_message(intent)
    if missing:
        return (missing, "Use a float or profile ID that exists in the dataset.")
    m = _BARE_SEASON_RE.search(qlow)
    if m and not re.search(r"\bmonsoon\b", qlow):
        word = m.group(1).lower()
        return (f"'{word.title()}' can mean different months in different places, and the dataset only covers "
                f"{coverage_label()}, so I haven't guessed. Please give the months (for example 'December to "
                "February' or 'January 2023') or a monsoon period such as pre-monsoon or north-east monsoon.",
                "Give explicit months or a monsoon period.")
    return None


CHAT_FAILURE_MESSAGE = "Sorry, something went wrong while answering this question. Please try again."


def _record_chat_failure(req: "ChatRequest", request: Request) -> None:
    """Keep saved history consistent when the pipeline crashes: make sure the question and
    an error reply are both stored, so a reopened chat never shows a question with no answer."""
    try:
        user = _get_current_user(request)
        conv_id = req.conversation_id
        question = req.get_query()
        if not (user and conv_id and question):
            return
        msgs = get_conversation_messages(conv_id, user["id"])
        if not msgs or msgs[-1].get("role") != "user" or msgs[-1].get("content") != question:
            save_message(conv_id, user["id"], "user", question, title=question)
        save_message(conv_id, user["id"], "assistant", CHAT_FAILURE_MESSAGE)
    except Exception:
        logger.exception("Could not record chat failure in history")


@app.post("/api/chat", response_model=ChatResponse)
def api_chat(req: ChatRequest, request: Request):
    """Primary conversational query endpoint (crash-safe wrapper around the pipeline)."""
    try:
        return _chat_pipeline(req, request)
    except HTTPException:
        raise
    except Exception:
        logger.exception("Unhandled error in /api/chat")
        _record_chat_failure(req, request)
        raise HTTPException(status_code=500, detail=CHAT_FAILURE_MESSAGE)


def _chat_pipeline(req: ChatRequest, request: Request):
    """Primary conversational query endpoint. Rules-first with verified data fidelity."""
    question = req.get_query()
    if not question:
        raise HTTPException(status_code=400, detail="Query message cannot be empty")
    conv_id = req.conversation_id
    current_user = _get_current_user(request)

    # 1. Load context history
    history = req.history if isinstance(req.history, list) else []
    history = [h for h in history if isinstance(h, dict) and isinstance(h.get("role", "user"), str) and isinstance(h.get("content", h.get("text", "")), str)]
    if not history:
        if current_user and conv_id:
            history = get_conversation_messages(conv_id, current_user["id"])
        elif conv_id:
            history = _anon_get_history(conv_id)

    # Save incoming user message
    if current_user and conv_id:
        try:
            save_message(conv_id, current_user["id"], "user", question, title=question)
        except PermissionError:
            raise HTTPException(status_code=404, detail="Conversation not found")
    elif conv_id:
        _anon_add_turn(conv_id, "user", question)

    # 1b. Typo tolerance: the history keeps the user's original text; everything after this
    # point (parsing, cache key, answer templates) sees the corrected question. Only fixed
    # vocabulary words are changed; numbers and IDs never are (see typo_tolerance.py).
    original_question = question
    question, _typo_fixes = correct_typos(question)
    _INTERPRETED.set(question if _typo_fixes and question != original_question else None)
    if _typo_fixes:
        logger.info("Typo correction applied: %s", _typo_fixes)

    # 2. Check Intent Cache
    cache_key = _intent_cache_key(question, conv_id, history)
    intent = _get_cached_intent(cache_key)

    answer_mode = "basic"

    if not intent:
        # Use the validated production parser; it attempts Gemini when configured and
        # always falls back to deterministic rules. It returns parser_used explicitly.
        intent = parse_question_intent(question, history=history)
        if intent.get("parser_used") == "llm":
            answer_mode = "gemini"
        _set_cached_intent(cache_key, intent)

    task = intent.get("task", "stat")
    _INHERITED_NOTE.set(_describe_inherited(intent))
    # Explicit invalid filters must not degrade into an unfiltered dataset query.
    qlow = question.lower()
    import re as _re
    mm_bad = _re.search(r"\bmonth\s+(\d{1,2})\b", qlow)
    yy_bad = _re.search(r"\byear\s+(\d{4})\b", qlow)
    if (mm_bad and not 1 <= int(mm_bad.group(1)) <= 12) or (yy_bad and not 1900 <= int(yy_bad.group(1)) <= 2100):
        response = ChatResponse(answer="That month or year is invalid or outside the supported range. Please specify a month from 1–12 and a year from 1900–2100.", observation_count=0, conversation_id=conv_id, ambiguous=True, clarification_needed="Correct the month/year filter.", task="stat", parser_used=intent.get("parser_used", "rules"), question_kind="data")
        return _persist_early_chat_response(response, current_user, conv_id, question, intent)
    # Guards for questions that would otherwise be answered with the wrong data.
    guard = _question_guard(question, qlow, intent)
    if guard:
        answer_text, clarification = guard
        response = ChatResponse(answer=answer_text, observation_count=0, conversation_id=conv_id,
                                ambiguous=clarification is not None, clarification_needed=clarification,
                                task=task, parser_used=intent.get("parser_used", "rules"),
                                question_kind=intent.get("question_kind", "data"))
        return _persist_early_chat_response(response, current_user, conv_id, question, intent)
    # Count entity questions using the entity tables, never measurement-row counts.
    if _re.search(r"\bhow many\b|\bnumber of\b|\bcount\b", qlow) and _re.search(r"\b(floats?|profiles?)\b", qlow) and not _re.search(r"\b(observations?|measurements?)\b", qlow):
        import sqlite3 as _sqlite3
        from config import DB_PATH as _OCEAN_DB
        from retrieval.query_engine import build_query as _build_filtered_query
        conn_count = _sqlite3.connect(_OCEAN_DB)
        try:
            base_sql, params = _build_filtered_query(intent)
            # Reuse the same WHERE filters as statistical queries so date, region,
            # platform, and pressure constraints are never silently ignored.
            where = base_sql.split("WHERE 1=1", 1)[1].split("ORDER BY p.timestamp", 1)[0]
            if _re.search(r"\bfloats?\b", qlow):
                value = conn_count.execute("SELECT COUNT(DISTINCT p.platform) FROM profiles p JOIN measurements m ON p.id=m.profile_id WHERE 1=1 " + where, params).fetchone()[0]
                noun = "floats"
            else:
                value = conn_count.execute("SELECT COUNT(DISTINCT p.id) FROM profiles p JOIN measurements m ON p.id=m.profile_id WHERE 1=1 " + where, params).fetchone()[0]
                noun = "profiles"
        finally:
            conn_count.close()
        response = ChatResponse(answer=f"The dataset contains {value:,} {noun} with measurement records matching the requested filters.", observation_count=value, applied_filters={k: intent[k] for k in ("year", "month", "year_end", "month_end", "pressure_min", "pressure_max") if intent.get(k) is not None}, conversation_id=conv_id, task="stat", parser_used=intent.get("parser_used", "rules"), question_kind="data")
        return _persist_early_chat_response(response, current_user, conv_id, question, intent)
    requested_variable = intent.get("variable")
    if isinstance(requested_variable, str) and requested_variable.startswith("unsupported:"):
        label = requested_variable.split(":", 1)[1]
        response = ChatResponse(answer=f"This dataset does not contain {label} measurements. Available variables are temperature, salinity, and pressure; I will not substitute temperature for the requested variable.", observation_count=0, conversation_id=conv_id, ambiguous=True, clarification_needed="Choose temperature, salinity, or pressure.", task="stat", parser_used=intent.get("parser_used", "rules"), question_kind="data")
        return _persist_early_chat_response(response, current_user, conv_id, question, intent)

    # 3. Handle Ambiguous
    if intent.get("ambiguous"):
        clarification = intent.get("clarification_needed") or (
            "I could not understand your ocean query. Try asking about temperature, salinity, "
            "or listing floats in the Bay of Bengal."
        )
        response = ChatResponse(
            answer=clarification,
            observation_count=0,
            ambiguous=True,
            clarification_needed=clarification,
            conversation_id=conv_id,
            answer_mode=answer_mode,
            task=task,
            parser_used=intent.get("parser_used", "rules"), question_kind=intent.get("question_kind"),
        )
        return _persist_early_chat_response(response, current_user, conv_id, question, intent)

    if intent.get("no_data_in_dataset"):
        note = (intent.get("season") or {}).get("coverage_note") or "The requested period is outside the available dataset coverage."
        response = ChatResponse(answer=note, observation_count=0, conversation_id=conv_id, task=task, answer_mode="basic", parser_used=intent.get("parser_used", "rules"), question_kind=intent.get("question_kind", "data"))
        return _persist_early_chat_response(response, current_user, conv_id, question, intent)

    # 4. Handle Conceptual Questions (RAG)
    if task == "concept" or intent.get("is_conceptual"):
        if conv_id:
            _clear_export_result(current_user, conv_id)
        rag_res = answer_conceptual_query(question)
        if rag_res:
            rag_mode = rag_res.get("rag_mode", "tfidf")
            # If the RAG pipeline used LLM generation, the answer is already natural language.
            # Otherwise, wrap it through the template builder.
            if "llm" in (rag_mode or ""):
                answer = knowledge_region_notice(question) + rag_res["answer"]
                answer_mode_val = "gemini"
            else:
                answer = build_answer(question, {
                    "task": "concept",
                    "is_conceptual": True,
                    "conceptual_answer": knowledge_region_notice(question) + rag_res["answer"],
                    "rag_sources": rag_res["sources"],
                })
                answer_mode_val = "basic"
            resp = ChatResponse(
                answer=answer,
                observation_count=0,
                conversation_id=conv_id,
                sources=rag_res["sources"],
                answer_mode=answer_mode_val,
                task="concept", parser_used=intent.get("parser_used", "rules"), question_kind=intent.get("question_kind", "knowledge"),
                rag_mode=rag_mode,
            )
            _annotate_interpreted(resp)
            if current_user and conv_id:
                save_message(conv_id, current_user["id"], "assistant", resp.answer, response_data=_history_payload(resp, intent))
            elif conv_id:
                _anon_add_turn(conv_id, "assistant", resp.answer, intent_summary=intent)
            return resp

    # 4b. Float/profile tasks that need an ID but were given none ("trajectory of the first float").
    _need_id = _missing_target_message(task, intent)
    if _need_id:
        response = ChatResponse(answer=_need_id, observation_count=0, conversation_id=conv_id, ambiguous=True,
                                clarification_needed=_need_id, task=task, parser_used=intent.get("parser_used", "rules"),
                                question_kind=intent.get("question_kind", "data"))
        return _persist_early_chat_response(response, current_user, conv_id, question, intent)

    # 5. Handle Discovery Tasks
    if task in ("discover_floats", "float_detail", "trajectory", "coverage", "similar_profiles"):
        disc_result = {}
        chart_data = None

        if task == "discover_floats":
            lat = intent.get("region_lat")
            lon = intent.get("region_lon")
            if lat is not None and lon is not None:
                floats = find_floats_near(lat, lon, radius_deg=intent.get("region_radius_deg", 2.0), date_window=intent)
            else:
                floats = list_floats(intent)
            # "deepest"/"shallowest" floats: order by mean maximum profile depth (not profile count).
            if _re.search(r"\bdeepest\b|\bdeeper\b", qlow):
                floats = sorted(floats, key=lambda f: f.get("avg_max_depth") or 0.0, reverse=True)
            elif _re.search(r"\bshallowest\b|\bshallower\b", qlow):
                floats = sorted(floats, key=lambda f: f.get("avg_max_depth") or 0.0)
            disc_result = {"task": "discover_floats", "floats": floats}
            chart_data = pick_chart("floats_map", [], extra_data={"floats": floats})

        elif task == "float_detail":
            plat = intent.get("platform_id")
            summ = float_summary(plat) if plat else None
            disc_result = {"task": "float_detail", "platform_id": plat, "float_summary": summ}
            if summ:
                traj = float_trajectory(plat)
                chart_data = pick_chart("trajectory", [], extra_data={"trajectory": traj, "platform": plat})

        elif task == "trajectory":
            plat = intent.get("platform_id")
            traj = trajectory_points(plat, year=intent.get("year"), month=intent.get("month"), year_end=intent.get("year_end"), month_end=intent.get("month_end")) if plat else []
            disc_result = {"task": "trajectory", "platform_id": plat, "trajectory": traj}
            chart_data = pick_chart("trajectory", [], extra_data={"trajectory": traj, "platform": plat})

        elif task == "coverage":
            cov = coverage_summary()
            disc_result = {"task": "coverage", "coverage": cov}
            chart_data = pick_chart("coverage", [], extra_data={"coverage": cov})

        elif task == "similar_profiles":
            prof_id = intent.get("profile_id")
            sims = find_similar_profiles(prof_id or "", k=5) if prof_id else []
            disc_result = {"task": "similar_profiles", "target_profile_id": prof_id, "similar_profiles": sims}
            chart_data = pick_chart("similar_profiles", [], extra_data={"target_profile_id": prof_id, "similar_profiles": sims})

        answer = build_answer(question, disc_result)
        if conv_id:
            _save_export_result(current_user, conv_id, disc_result)

        resp = ChatResponse(
            answer=answer,
            observation_count=len(disc_result.get("floats") or disc_result.get("trajectory") or disc_result.get("similar_profiles") or []),
            chart_type=intent.get("chart_type") or task,
            chart_data=chart_data,
            conversation_id=conv_id,
            answer_mode="basic",
            task=task,
            discovery_data=disc_result, parser_used=intent.get("parser_used", "rules"), question_kind=intent.get("question_kind", "data"),
        )
        _annotate_interpreted(resp)
        if current_user and conv_id:
            save_message(conv_id, current_user["id"], "assistant", resp.answer, response_data=_history_payload(resp, intent),
                         export_data=_safe_export_payload(task, intent, disc_result))
        elif conv_id:
            _anon_add_turn(conv_id, "assistant", resp.answer, intent_summary=intent)
        return resp

    # 6. Standard Statistical Query Execution
    # Unqualified temperature averages default to the upper 50 dbar and disclose it,
    # rather than silently averaging the entire water column to 2000 dbar.
    # Do not apply the 50 dbar default when chart_type == "depth_profile" or the question asks for a profile/depth profile.
    is_depth_profile = (
        intent.get("chart_type") == "depth_profile"
        or bool(re.search(r"\b(depth[ -]?profiles?|profiles?)\b", qlow))
    )
    if not is_depth_profile and (intent.get("variable") in ("temperature", "salinity") or intent.get("variable") is None) and intent.get("stat") in ("avg", "none") and intent.get("pressure_min") is None and intent.get("pressure_max") is None and not re.search(r"\b(all depths|entire water column|all levels|full depth)\b", qlow):
        intent["pressure_max"] = 50.0
    # A single level ("at 2000 dbar") almost never matches a float's exact sampled pressure,
    # so use a +/-10 dbar band; the answer states the band that was actually used.
    _p_lo, _p_hi = intent.get("pressure_min"), intent.get("pressure_max")
    if _p_lo is not None and _p_lo == _p_hi:
        intent["pressure_min"], intent["pressure_max"] = _p_lo - SINGLE_LEVEL_TOLERANCE_DBAR, _p_hi + SINGLE_LEVEL_TOLERANCE_DBAR
    try:
        db_result = retrieve(intent)
    except Exception as e:
        logger.error("Database query failed: %s", e)
        raise HTTPException(status_code=500, detail="Database query error")

    if conv_id:
        _save_export_result(current_user, conv_id, db_result)

    # 7. Generate Natural Language Answer
    answer = None
    if USE_LLM_EXPLANATION and is_gemini_available():
        answer = gemini_explain(question, db_result)
        if answer:
            answer_mode = "gemini"

    if not answer:
        answer = build_answer(question, db_result)
        answer_mode = "basic"
    # Disclose when a requested year/range extends outside the actual bundled data.
    requested_years = [y for y in (intent.get("year"), intent.get("year_end")) if isinstance(y, int)]
    if requested_years:
        try:
            import sqlite3 as _coverage_sqlite3
            from config import DB_PATH as _coverage_db_path
            with _coverage_sqlite3.connect(_coverage_db_path) as _coverage_conn:
                _min_date, _max_date = _coverage_conn.execute("SELECT MIN(timestamp), MAX(timestamp) FROM profiles").fetchone()
            if _min_date and _max_date:
                coverage_text = f"Dataset coverage is {_min_date[:10]} through {_max_date[:10]}. Results only represent observations available within that coverage; requested dates outside it are not represented."
                if requested_years[0] < int(_min_date[:4]) or max(requested_years) > int(_max_date[:4]):
                    answer = answer.rstrip() + "\n\n" + coverage_text
        except Exception as coverage_error:
            logger.warning("Could not determine dataset coverage for response: %s", coverage_error)

    season_meta = intent.get("season")
    # Say so when a year was assumed although the dataset holds other years too (silent choice otherwise).
    if season_meta and (season_meta.get("coverage") == "partial"
                        or (season_meta.get("year_assumed") and season_meta.get("other_years"))):
        coverage_note = season_meta.get("coverage_note")
        if coverage_note and coverage_note not in answer:
            answer = answer.rstrip() + "\n\n" + coverage_note

    # 8. Generate Chart
    chart_type = intent.get("chart_type") or "depth_profile"
    if intent.get("compare"):
        chart_type = "compare"

    chart_json = pick_chart(
        chart_type=chart_type,
        rows=db_result.get("rows", []),
        variable=db_result.get("variable", "temperature"),
        compare_groups=db_result.get("compare_groups"),
    )

    stat = db_result.get("stat")
    stat_model = StatResult(stat=stat["stat"], value=stat["value"], parameter=stat["parameter"]) if stat else None

    resp = ChatResponse(
        answer=answer,
        variable=db_result.get("variable"),
        units=db_result.get("units"),
        observation_count=db_result.get("count", 0),
        applied_filters=db_result.get("filters", {}),
        stat=stat_model,
        chart_type=chart_type if chart_json else None,
        chart_data=chart_json,
        date_range=_date_range_str(db_result.get("filters", {})),
        conversation_id=conv_id,
        answer_mode=answer_mode,
        task="stat", parser_used=intent.get("parser_used", "rules"), question_kind=intent.get("question_kind", "data"),
    )

    _annotate_interpreted(resp)
    if current_user and conv_id:
        save_message(conv_id, current_user["id"], "assistant", resp.answer, response_data=_history_payload(resp, intent),
                     export_data=_safe_export_payload("stat", intent, db_result))
    elif conv_id:
        _anon_add_turn(conv_id, "assistant", resp.answer, intent_summary=intent)

    return resp


# ── CSV Export ────────────────────────────────────────────────────────────────

_ANON_EXPORT_GONE = (
    "This guest chat's results are no longer on the server (guest chats are kept in memory for about an hour "
    "and are lost when the server restarts). Sign in to keep your chats and exports, or ask the question again, then export."
)


@app.post("/api/export")
def api_export_csv(body: ExportRequest, request: Request):
    """Secure CSV export for current session."""
    conv_id = body.conversation_id
    user = _get_current_user(request)
    if not conv_id:
        raise HTTPException(status_code=400, detail="conversation_id is required")
    if user:
        if not conversation_owned(conv_id, user["id"]):
            raise HTTPException(status_code=404, detail="Conversation not found")
    elif conv_id not in _anon_memory:
        raise HTTPException(status_code=404, detail=_ANON_EXPORT_GONE)
    stored = _get_export_result(user, conv_id)
    if stored is None and user:
        # In-memory cache expired / server restarted: rebuild from what was saved with the chat.
        try:
            stored = resolve_result(get_latest_export(conv_id, user["id"]), retrieve)
        except Exception:
            logger.exception("Could not rebuild export from saved chat")
            stored = None

    built = csv_for_result(stored)
    if built is None:
        raise HTTPException(
            status_code=409,
            detail=_ANON_EXPORT_GONE if not user else
            "Export data is not available for this chat (it was saved before exports were stored, or the result was too large to keep). Ask the question again, then export.",
        )
    csv_text, filename = built

    return StreamingResponse(
        iter([csv_text]),
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename={filename}"},
    )


@app.post("/api/export/pdf")
def api_export_pdf(body: ExportRequest, request: Request):
    """Generate and download a publication-ready PDF Scientific Oceanographic Report."""
    conv_id = body.conversation_id
    user = _get_current_user(request)
    if not conv_id:
        raise HTTPException(status_code=400, detail="conversation_id is required")
    if user:
        if not conversation_owned(conv_id, user["id"]):
            raise HTTPException(status_code=404, detail="Conversation not found")
    elif conv_id not in _anon_memory:
        raise HTTPException(status_code=404, detail=_ANON_EXPORT_GONE)

    stored = _get_export_result(user, conv_id)
    if stored is None and user:
        try:
            stored = resolve_result(get_latest_export(conv_id, user["id"]), retrieve)
        except Exception:
            logger.exception("Could not rebuild export from saved chat")
            stored = None

    if not stored:
        # Fallback to general database coverage summary
        stored = coverage_summary()
        stored["task"] = "coverage"

    from pdf_report import generate_scientific_pdf_report
    pdf_bytes, filename = generate_scientific_pdf_report(
        stored,
        metadata={
            "conversation_id": conv_id,
            "user": (user or {}).get("email", "Guest Researcher")
        }
    )

    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f"attachment; filename={filename}"}
    )


@app.post("/api/reset")
def api_reset(body: ResetModel, request: Request):
    conv_id = body.conversation_id
    if conv_id:
        user = _get_current_user(request)
        if user:
            # Only clear state for a conversation owned by this user.
            if not conversation_owned(conv_id, user["id"]):
                raise HTTPException(status_code=404, detail="Conversation not found")
            _clear_export_result(user, conv_id)
        else:
            _clear_export_result(None, conv_id)
            _anon_memory.pop(conv_id, None)
    return {"status": "ok"}


# ── Static File Serving (Frontend) ───────────────────────────────────────────
FRONTEND_DIR = PROJECT_ROOT / "frontend"
if FRONTEND_DIR.exists():
    app.mount("/", StaticFiles(directory=str(FRONTEND_DIR), html=True), name="static")


# ── Programmatic Runner (Stage 6) ─────────────────────────────────────────────

def start_server():
    """Start FloatChat server programmatically with port detection and browser opening."""
    import socket
    import webbrowser
    import uvicorn

    port = int(os.environ.get("PORT", 8000))
    host = "127.0.0.1"

    # Test port availability
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        sock.bind((host, port))
        sock.close()
    except OSError:
        print(f"\n[ERROR] Port {port} is already in use by another process.")
        print("Please stop the existing process or set PORT=<another_port> in .env.\n")
        sys.exit(1)

    url = f"http://{host}:{port}"
    print("\n=======================================================")
    print(f"  ArgoLens is running at {url}")
    print("  Press Ctrl+C to stop the server.")
    print("=======================================================\n")

    # Automatically open default browser after a short delay
    try:
        webbrowser.open(url)
    except Exception:
        pass

    uvicorn.run("main:app", host=host, port=port, reload=False, app_dir=str(BASE_DIR))


if __name__ == "__main__":
    start_server()