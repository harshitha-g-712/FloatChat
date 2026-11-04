"""
FloatChat – Gemini Service Module (google-genai SDK v2)
=========================================================
Handles natural language question interpretation and explanation generation.
Protected with strict rate-limit backoff, daily quota safety blocks,
and schema validation.

Guarantees:
- NEVER fabricates or guesses ocean measurements.
- Silently cools down for 30 minutes on daily quota 429 limits.
- Never logs API keys or sensitive values.
"""

import os
import json
import logging
import re
import time
from typing import Optional, Dict, Any, List

from config import (
    ALLOWED_VARIABLES, ALLOWED_STATS, ALLOWED_CHART_TYPES, ALLOWED_TASKS,
    USE_GEMINI, USE_LLM_EXPLANATION, GEMINI_MODEL, GEMINI_EMBEDDING_MODEL
)

logger = logging.getLogger("floatchat.gemini")

_CLIENT = None
_MODEL_NAME: str = GEMINI_MODEL or "gemini-2.5-flash"
_BLOCKED_UNTIL: float = 0.0

MAX_RETRIES = 2
BASE_BACKOFF_SECONDS = 1.0


def is_gemini_available() -> bool:
    """Check if Gemini client is initialized and not currently cooling down from a quota limit."""
    use_gem = os.environ.get("USE_GEMINI", "false").strip().lower() == "true" or USE_GEMINI
    if not use_gem:
        return False
    if _CLIENT is None:
        return False
    if time.time() < _BLOCKED_UNTIL:
        return False
    return True


def init_gemini() -> bool:
    """Initialize Gemini client safely. Returns True if configured, False otherwise."""
    global _CLIENT, _MODEL_NAME
    key = os.environ.get("GEMINI_API_KEY", "").strip()
    if not key or key.startswith("your_") or key == "placeholder":
        logger.info("No Gemini API key provided. Operating in 100% offline rules mode.")
        _CLIENT = None
        return False

    try:
        from google import genai
        model_name = os.environ.get("GEMINI_MODEL", "gemini-2.5-flash").strip()
        _CLIENT = genai.Client(api_key=key)
        _MODEL_NAME = model_name
        logger.info("Gemini client initialized successfully (model=%s)", model_name)
        return True
    except Exception as e:
        logger.warning("Could not initialize Gemini client: %s", e)
        _CLIENT = None
        return False


def _call_gemini(prompt: str) -> Optional[str]:
    """Execute Gemini API call with quota backoff protection."""
    global _BLOCKED_UNTIL, _CLIENT
    if not is_gemini_available():
        return None

    from google.genai import types as genai_types

    last_error = None
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            response = _CLIENT.models.generate_content(
                model=_MODEL_NAME,
                contents=prompt,
                config=genai_types.GenerateContentConfig(
                    temperature=0.1,
                    max_output_tokens=1024,
                ),
            )
            if response and response.text:
                return response.text.strip()
            return None

        except Exception as e:
            err_str = str(e).lower()
            last_error = e

            # Daily quota limit hit (PerDay / RESOURCE_EXHAUSTED / retryDelay > 60s)
            if "perday" in err_str or "resource_exhausted" in err_str or "quota" in err_str or "429" in err_str:
                logger.warning("Gemini 429/Quota limit detected: %s. Enabling 30-minute block.", e)
                _BLOCKED_UNTIL = time.time() + 1800.0  # 30 minutes block
                return None

            if "401" in err_str or "403" in err_str or "invalid" in err_str or "key" in err_str:
                logger.error("Gemini authentication error. Disabling Gemini calls.")
                _CLIENT = None
                return None

            # Short retry for 503 or transient network errors
            if attempt < MAX_RETRIES:
                time.sleep(BASE_BACKOFF_SECONDS * attempt)

    logger.warning("Gemini call failed after %d attempts: %s", MAX_RETRIES, last_error)
    return None


# ── Structured Intent Extraction ─────────────────────────────────────────────

_INTENT_PROMPT_TEMPLATE = """\
You are an oceanographic data assistant that converts natural language queries about ARGO floats into a JSON intent.
Return ONLY valid JSON (no markdown formatting) with these exact keys:
{{
  "task": "stat" | "discover_floats" | "float_detail" | "trajectory" | "coverage" | "similar_profiles" | "concept",
  "variable": "temperature" | "salinity" | "pressure" | null,
  "stat": "avg" | "min" | "max" | "count" | "none",
  "year": integer | null,
  "month": integer (1-12) | null,
  "year_end": integer | null,
  "month_end": integer (1-12) | null,
  "compare": true | false,
  "compare_months": list of integers | null,
  "region_lat": float | null,
  "region_lon": float | null,
  "region_radius_deg": float | null,
  "named_region": string | null,
  "platform_id": string | null,
  "profile_id": string | null,
  "chart_type": "depth_profile" | "timeseries" | "distribution" | "map" | "compare" | "trajectory" | "coverage" | "similar_profiles" | "floats_map" | "none",
  "pressure_min": float | null,
  "pressure_max": float | null,
  "export_csv": true | false,
  "ambiguous": true | false,
  "clarification_needed": string | null,
  "is_conceptual": true | false
}}

Question: {question}
"""


def interpret_question(question: str, history: Optional[List[Dict[str, Any]]] = None) -> Optional[Dict[str, Any]]:
    """Interpret question using Gemini if enabled, returning sanitized intent."""
    if not is_gemini_available():
        return None

    prompt = _INTENT_PROMPT_TEMPLATE.format(question=question)
    raw = _call_gemini(prompt)
    if not raw:
        return None

    # Clean markdown formatting
    raw = re.sub(r"^```(?:json)?\s*", "", raw.strip())
    raw = re.sub(r"\s*```$", "", raw.strip())

    try:
        intent = json.loads(raw)
        return validate_intent(intent)
    except Exception as e:
        logger.warning("Could not parse Gemini intent response: %s", e)
        return None


def validate_intent(intent: Dict[str, Any]) -> Dict[str, Any]:
    """Validate and sanitize intent dict against strict allowlists."""
    task = intent.get("task", "stat")
    if task not in ALLOWED_TASKS:
        intent["task"] = "stat"

    var = intent.get("variable")
    if var not in ALLOWED_VARIABLES and var is not None:
        intent["variable"] = None

    stat = intent.get("stat", "none")
    if stat not in ALLOWED_STATS:
        intent["stat"] = "none"

    ct = intent.get("chart_type", "none")
    if ct not in ALLOWED_CHART_TYPES:
        intent["chart_type"] = "none"

    for f in ("year", "month", "year_end", "month_end"):
        val = intent.get(f)
        try:
            intent[f] = int(val) if val is not None else None
        except (TypeError, ValueError):
            intent[f] = None

    if intent.get("month") and not (1 <= intent["month"] <= 12):
        intent["month"] = None
    if intent.get("month_end") and not (1 <= intent["month_end"] <= 12):
        intent["month_end"] = None

    for f in ("region_lat", "region_lon", "region_radius_deg", "pressure_min", "pressure_max"):
        val = intent.get(f)
        try:
            intent[f] = float(val) if val is not None else None
        except (TypeError, ValueError):
            intent[f] = None

    for f in ("compare", "export_csv", "ambiguous", "is_conceptual"):
        intent[f] = bool(intent.get(f, False))

    for f in ("named_region", "platform_id", "profile_id", "clarification_needed"):
        val = intent.get(f)
        intent[f] = str(val).strip() if val is not None else None

    return intent

_validate_intent = validate_intent



_EXPLAIN_PROMPT = """\
You are FloatChat, explaining verified ARGO ocean float data for the Bay of Bengal.
Write a clear, factual, 2-3 sentence answer using ONLY these verified statistics:
- Question: {question}
- Variable: {variable} ({units})
- Observation Count: {count}
- Applied Filters: {filters}
- Statistics: {stats}

Do NOT invent any numbers. Keep numbers exactly as computed.
"""


def generate_explanation(question: str, db_result: Dict[str, Any]) -> Optional[str]:
    """Generate plain-English summary of verified numbers using Gemini if enabled."""
    use_llm_exp = os.environ.get("USE_LLM_EXPLANATION", "false").strip().lower() == "true" or USE_LLM_EXPLANATION
    if not is_gemini_available() or not use_llm_exp:
        return None

    count = db_result.get("count", 0)
    variable = db_result.get("variable", "temperature")
    units = db_result.get("units", "°C")
    filters = str(db_result.get("filters", {}))
    stat = db_result.get("stat")
    stats_str = f"{stat['stat']} = {stat['value']}" if stat else f"total count = {count}"

    prompt = _EXPLAIN_PROMPT.format(
        question=question,
        variable=variable,
        units=units,
        count=count,
        filters=filters,
        stats=stats_str,
    )
    return _call_gemini(prompt)


# ── Embedding Support (for RAG) ─────────────────────────────────────────────

_EMBEDDING_MODEL: str = GEMINI_EMBEDDING_MODEL or "text-embedding-004"


def embed_texts(texts: List[str]) -> Optional[List[List[float]]]:
    """Generate embeddings for a list of texts using Gemini embedding model.

    Returns a list of embedding vectors, or None on failure.
    """
    if not is_gemini_available() or _CLIENT is None:
        return None

    try:
        from google.genai import types as genai_types
        result = _CLIENT.models.embed_content(
            model=_EMBEDDING_MODEL,
            contents=texts,
            config=genai_types.EmbedContentConfig(
                task_type="RETRIEVAL_DOCUMENT",
            ),
        )
        if result and result.embeddings:
            return [emb.values for emb in result.embeddings]
        return None
    except Exception as e:
        logger.warning("Embedding generation failed: %s", e)
        return None


def embed_query(text: str) -> Optional[List[float]]:
    """Generate embedding for a single query text (uses RETRIEVAL_QUERY task type)."""
    if not is_gemini_available() or _CLIENT is None:
        return None

    try:
        from google.genai import types as genai_types
        result = _CLIENT.models.embed_content(
            model=_EMBEDDING_MODEL,
            contents=[text],
            config=genai_types.EmbedContentConfig(
                task_type="RETRIEVAL_QUERY",
            ),
        )
        if result and result.embeddings:
            return result.embeddings[0].values
        return None
    except Exception as e:
        logger.warning("Query embedding failed: %s", e)
        return None


# ── RAG Answer Generation (Retrieval-Augmented Generation) ───────────────────

_RAG_PROMPT = """\
You are FloatChat, an expert AI assistant for ARGO ocean float data in the Bay of Bengal.
Answer the user's question using ONLY the retrieved knowledge context below.
Be clear, concise, and scientifically accurate. Use 3-5 sentences.

If the context doesn't contain enough information to answer, say so honestly.
Do NOT invent facts or numbers not present in the context.

Retrieved Context:
{context}

User Question: {question}

Answer:"""


def generate_rag_answer(question: str, context_docs: List[Dict[str, Any]]) -> Optional[str]:
    """Generate an LLM answer grounded in retrieved RAG documents.

    This is the 'Generation' step of Retrieval-Augmented Generation:
    the retriever found relevant docs, now the LLM synthesizes an answer.
    """
    if not is_gemini_available():
        return None

    # Build context from retrieved documents
    context_parts = []
    for i, doc in enumerate(context_docs, 1):
        title = doc.get("title", "Document")
        content = doc.get("content", "")
        # Trim to avoid exceeding token limits
        if len(content) > 2000:
            content = content[:2000] + "..."
        context_parts.append(f"[Source {i}: {title}]\n{content}")

    context = "\n\n".join(context_parts)
    prompt = _RAG_PROMPT.format(context=context, question=question)
    return _call_gemini(prompt)
