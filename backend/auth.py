"""
FloatChat – Authentication & Secure Session Management
======================================================
Implements Argon2-cffi password hashing with automatic transparent migration
from legacy SHA-256 salts.
Stores hashed authentication tokens with 7-day expiration and automatic purging.
"""

import hashlib
import json
import logging
import os
import re
import secrets
import sqlite3
from datetime import datetime, timezone, timedelta
from typing import Optional, Dict, Any, List
from pydantic import BaseModel, Field, field_validator

from config import AUTH_DB_PATH

logger = logging.getLogger("floatchat.auth")

TOKEN_EXPIRY_DAYS = 7
MAX_TITLE_LEN = 60
USERNAME_RE = re.compile(r"^[A-Za-z0-9_-]+$")
SHARE_TOKEN_RE = re.compile(r"^[A-Za-z0-9_-]{20,128}$")
CONV_ID_RE = re.compile(r"^[A-Za-z0-9_-]{1,64}$")


def is_valid_conversation_id(conv_id: Optional[str]) -> bool:
    """Conversation ids are client-supplied; accept only short, safe tokens (UUIDs included)."""
    return isinstance(conv_id, str) and bool(CONV_ID_RE.match(conv_id))


def _make_title(text: str) -> str:
    text = " ".join((text or "").split())
    if not text:
        return "New Chat"
    return text if len(text) <= MAX_TITLE_LEN else text[: MAX_TITLE_LEN - 1].rstrip() + "…"


def _connect(path: str) -> sqlite3.Connection:
    """Open the auth/history DB with a busy timeout, WAL and enforced foreign keys."""
    conn = sqlite3.connect(path, timeout=10)
    conn.execute("PRAGMA busy_timeout=10000")
    conn.execute("PRAGMA foreign_keys=ON")
    try:
        conn.execute("PRAGMA journal_mode=WAL")
    except sqlite3.DatabaseError:
        pass  # e.g. read-only or network file systems: keep the default journal
    return conn

# Argon2 Hasher with fallback
try:
    from argon2 import PasswordHasher
    from argon2.exceptions import VerifyMismatchError
    _hasher = PasswordHasher()
    _HAS_ARGON2 = True
except ImportError:
    _HAS_ARGON2 = False
    _hasher = None
    logger.warning("argon2-cffi not installed; using PBKDF2/SHA256 fallback")


# ── Pydantic Request Models ──────────────────────────────────────────────────

class RegisterModel(BaseModel):
    username: str = Field(..., min_length=3, max_length=50, description="Username")
    email: str = Field(..., description="Valid user email")
    password: str = Field(..., min_length=10, max_length=128, description="Password (10–128 characters)")

    @field_validator("password")
    @classmethod
    def validate_password(cls, v: str) -> str:
        if v.strip().lower() in {"password", "password123", "1234567890", "qwerty12345", "admin12345"}:
            raise ValueError("Choose a less common password")
        if len(v) > 128:
            raise ValueError("Password must be at most 128 characters")
        return v

    @field_validator("email")
    @classmethod
    def validate_email(cls, v: str) -> str:
        v = v.strip().lower()
        if not re.match(r"^[^@\s]+@[^@\s]+\.[^@\s]+$", v):
            raise ValueError("Invalid email format")
        return v

    @field_validator("username")
    @classmethod
    def validate_username(cls, v: str) -> str:
        v = v.strip()
        if not USERNAME_RE.match(v):
            raise ValueError("Username can only contain letters, numbers, hyphens, and underscores (no spaces or dots)")
        return v


class LoginModel(BaseModel):
    email: str
    password: str

    @field_validator("email")
    @classmethod
    def clean_email(cls, v: str) -> str:
        return v.strip().lower()


class ResetModel(BaseModel):
    conversation_id: Optional[str] = None


class UpdateUsernameModel(BaseModel):
    username: str = Field(..., min_length=3, max_length=50, description="New Username")

    @field_validator("username")
    @classmethod
    def validate_username(cls, v: str) -> str:
        v = v.strip()
        if not USERNAME_RE.match(v):
            raise ValueError("Username can only contain letters, numbers, hyphens, and underscores (no spaces or dots)")
        return v


class ChangePasswordModel(BaseModel):
    old_password: str
    new_password: str = Field(..., min_length=10, max_length=128, description="New Password (10–128 characters)")

    @field_validator("new_password")
    @classmethod
    def validate_new_password(cls, v: str) -> str:
        if v.strip().lower() in {"password", "password123", "1234567890", "qwerty12345", "admin12345"}:
            raise ValueError("Choose a less common password")
        if len(v) > 128:
            raise ValueError("Password must be at most 128 characters")
        return v


# ── Database Initialization ──────────────────────────────────────────────────

def init_auth_db(db_path: Optional[str] = None):
    """Create auth + conversation tables with indexes and token hash schema."""
    path = db_path or str(AUTH_DB_PATH)
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    conn = _connect(path)
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS users (
            id            INTEGER PRIMARY KEY AUTOINCREMENT,
            username      TEXT UNIQUE NOT NULL,
            email         TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            salt          TEXT,
            created_at    TEXT DEFAULT CURRENT_TIMESTAMP
        );
        CREATE TABLE IF NOT EXISTS conversations (
            id            TEXT PRIMARY KEY,
            user_id       INTEGER NOT NULL,
            title         TEXT DEFAULT 'New Chat',
            created_at    TEXT DEFAULT CURRENT_TIMESTAMP,
            updated_at    TEXT DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE
        );
        CREATE TABLE IF NOT EXISTS chat_messages (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            conversation_id TEXT NOT NULL,
            role            TEXT NOT NULL,
            content         TEXT NOT NULL,
            response_data   TEXT,
            export_data     TEXT,
            created_at      TEXT DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY(conversation_id) REFERENCES conversations(id) ON DELETE CASCADE
        );
        CREATE TABLE IF NOT EXISTS shared_chats (
            token           TEXT PRIMARY KEY,
            conversation_id TEXT NOT NULL UNIQUE,
            user_id         INTEGER NOT NULL,
            title           TEXT,
            snapshot        TEXT NOT NULL,
            created_at      TEXT DEFAULT CURRENT_TIMESTAMP,
            updated_at      TEXT DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY(conversation_id) REFERENCES conversations(id) ON DELETE CASCADE,
            FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE
        );
        CREATE INDEX IF NOT EXISTS idx_users_email ON users(email);
        CREATE INDEX IF NOT EXISTS idx_conv_user ON conversations(user_id);
        CREATE INDEX IF NOT EXISTS idx_msg_conv ON chat_messages(conversation_id);
    """)
    # Migrate legacy databases: CREATE TABLE IF NOT EXISTS does not alter columns.
    user_cols = {r[1] for r in conn.execute("PRAGMA table_info(users)")}
    if "salt" not in user_cols:
        conn.execute("ALTER TABLE users ADD COLUMN salt TEXT")
    if "created_at" not in user_cols:
        conn.execute("ALTER TABLE users ADD COLUMN created_at TEXT DEFAULT CURRENT_TIMESTAMP")
    msg_cols = {r[1] for r in conn.execute("PRAGMA table_info(chat_messages)")}
    if "export_data" not in msg_cols:
        # Compact CSV-export payload (see export_store.py); never sent to the browser.
        conn.execute("ALTER TABLE chat_messages ADD COLUMN export_data TEXT")
    token_cols = {r[1] for r in conn.execute("PRAGMA table_info(auth_tokens)")} if conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='auth_tokens'").fetchone() else set()
    if token_cols and "token_hash" not in token_cols:
        # Old schema stored raw tokens; revoke them rather than treating secrets as hashes.
        conn.execute("DROP TABLE auth_tokens")
        token_cols = set()
    if not token_cols:
        conn.execute("CREATE TABLE auth_tokens (token_hash TEXT PRIMARY KEY, user_id INTEGER NOT NULL, created_at TEXT DEFAULT CURRENT_TIMESTAMP, FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_tokens_user ON auth_tokens(user_id)")
    conn.commit()
    conn.close()


def _hash_token(raw_token: str) -> str:
    """Hash session token with SHA-256 for secure DB storage."""
    return hashlib.sha256(raw_token.encode("utf-8")).hexdigest()


_PBKDF2_ITERATIONS = 600_000


def _hash_new_password(password: str) -> str:
    """Hash password using Argon2 (or PBKDF2 if argon2 is missing)."""
    if _HAS_ARGON2 and _hasher:
        return _hasher.hash(password)
    # Fallback PBKDF2 (OWASP-recommended iteration count; the count is stored with the hash)
    salt = secrets.token_hex(16)
    dk = hashlib.pbkdf2_hmac("sha256", password.encode(), salt.encode(), _PBKDF2_ITERATIONS)
    return f"pbkdf2v2:{_PBKDF2_ITERATIONS}:{salt}:{dk.hex()}"


def _verify_password(password: str, stored_hash: str, salt: Optional[str] = None) -> tuple[bool, bool]:
    """Verify password. Returns (is_valid, needs_rehash)."""
    # 1. Argon2 verification
    if stored_hash.startswith("$argon2"):
        if _HAS_ARGON2 and _hasher:
            try:
                _hasher.verify(stored_hash, password)
                needs_rehash = _hasher.check_needs_rehash(stored_hash)
                return True, needs_rehash
            except VerifyMismatchError:
                return False, False
            except Exception:
                return False, False
        return False, False

    # 2a. PBKDF2 with a stored iteration count
    if stored_hash.startswith("pbkdf2v2:"):
        try:
            _, iters, s, h = stored_hash.split(":")
            dk = hashlib.pbkdf2_hmac("sha256", password.encode(), s.encode(), int(iters))
            valid = secrets.compare_digest(dk.hex(), h)
            return valid, bool(valid and ((int(iters) < _PBKDF2_ITERATIONS) or _HAS_ARGON2))
        except Exception:
            return False, False

    # 2b. Older PBKDF2 hashes (100,000 iterations)
    if stored_hash.startswith("pbkdf2:"):
        try:
            _, s, h = stored_hash.split(":")
            dk = hashlib.pbkdf2_hmac("sha256", password.encode(), s.encode(), 100000)
            valid = secrets.compare_digest(dk.hex(), h)
            return valid, True if _HAS_ARGON2 else False
        except Exception:
            return False, False

    # 3. Legacy SHA-256 verification with salt
    if salt:
        legacy_hash = hashlib.sha256((salt + password).encode("utf-8")).hexdigest()
        if secrets.compare_digest(legacy_hash, stored_hash):
            return True, True  # Needs immediate upgrade to Argon2

    return False, False


def purge_expired_tokens(db_path: Optional[str] = None) -> int:
    """Delete authentication tokens older than TOKEN_EXPIRY_DAYS."""
    path = db_path or str(AUTH_DB_PATH)
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    conn = _connect(path)
    cutoff = (datetime.now(timezone.utc) - timedelta(days=TOKEN_EXPIRY_DAYS)).isoformat()
    try:
        cur = conn.execute("DELETE FROM auth_tokens WHERE created_at < ?", (cutoff,))
        conn.commit()
        return cur.rowcount
    finally:
        conn.close()


def register_user(username: str, email: str, password: str, db_path: Optional[str] = None) -> Dict[str, Any]:
    """Register a new user after validation. Returns user info or error dict."""
    try:
        req = RegisterModel(username=username, email=email, password=password)
    except Exception as e:
        return {"error": str(e)}

    path = db_path or str(AUTH_DB_PATH)
    # Hash first, in every branch, so a duplicate email costs the same time as a new one.
    pw_hash = _hash_new_password(req.password)

    conn = _connect(path)
    try:
        # Account-enumeration protection: an already-registered email gets exactly the same
        # answer as a brand-new one ({"ok": True}); the caller never learns which it was.
        # (Usernames are not secret, so "username taken" is still reported.)
        if conn.execute("SELECT 1 FROM users WHERE email = ?", (req.email,)).fetchone():
            logger.info("Registration attempt for an existing email (ignored)")
            return {"ok": True}
        try:
            conn.execute(
                "INSERT INTO users (username, email, password_hash, salt) VALUES (?,?,?,?)",
                (req.username, req.email, pw_hash, None),
            )
            conn.commit()
        except sqlite3.IntegrityError:
            # Lost a race: someone registered the same email/username between check and insert.
            if conn.execute("SELECT 1 FROM users WHERE email = ?", (req.email,)).fetchone():
                return {"ok": True}
            return {"error": "This username is already taken."}
        logger.info("User registered: %s", req.username)
        return {"ok": True}
    finally:
        conn.close()


def login_user(email: str, password: str, db_path: Optional[str] = None) -> Dict[str, Any]:
    """Authenticate user with automatic hash upgrade and return token."""
    path = db_path or str(AUTH_DB_PATH)
    email = email.strip().lower()

    purge_expired_tokens(path)

    conn = _connect(path)
    conn.row_factory = sqlite3.Row
    try:
        row = conn.execute(
            "SELECT id, username, email, password_hash, salt FROM users WHERE email = ?",
            (email,),
        ).fetchone()
        if not row:
            return {"error": "Incorrect email or password."}

        valid, needs_upgrade = _verify_password(password, row["password_hash"], row["salt"])
        if not valid:
            return {"error": "Incorrect email or password."}

        # Transparent upgrade to Argon2 if old hash format
        if needs_upgrade and _HAS_ARGON2:
            new_hash = _hash_new_password(password)
            conn.execute(
                "UPDATE users SET password_hash = ?, salt = NULL WHERE id = ?",
                (new_hash, row["id"]),
            )
            conn.commit()
            logger.info("Upgraded password hash for user %s (id=%d) to Argon2", row["username"], row["id"])

        # Create token (raw token sent to client, hash stored in DB)
        raw_token = secrets.token_urlsafe(48)
        t_hash = _hash_token(raw_token)
        now_str = datetime.now(timezone.utc).isoformat()

        conn.execute(
            "INSERT INTO auth_tokens (token_hash, user_id, created_at) VALUES (?,?,?)",
            (t_hash, row["id"], now_str),
        )
        conn.commit()

        return {
            "ok": True,
            "token": raw_token,
            "user": {
                "id": row["id"],
                "username": row["username"],
                "email": row["email"],
            },
        }
    finally:
        conn.close()


def validate_token(token: str, db_path: Optional[str] = None) -> Optional[Dict[str, Any]]:
    """Validate raw token against stored token hash and check expiration."""
    if not token or len(token) < 20:
        return None

    path = db_path or str(AUTH_DB_PATH)
    t_hash = _hash_token(token)
    cutoff = (datetime.now(timezone.utc) - timedelta(days=TOKEN_EXPIRY_DAYS)).isoformat()

    conn = _connect(path)
    conn.row_factory = sqlite3.Row
    try:
        row = conn.execute(
            """
            SELECT u.id, u.username, u.email 
            FROM auth_tokens t 
            JOIN users u ON t.user_id = u.id 
            WHERE t.token_hash = ? AND t.created_at >= ?
            """,
            (t_hash, cutoff),
        ).fetchone()
        return dict(row) if row else None
    finally:
        conn.close()


def logout_user(token: str, db_path: Optional[str] = None):
    """Invalidate session by deleting stored token hash."""
    if not token:
        return
    path = db_path or str(AUTH_DB_PATH)
    t_hash = _hash_token(token)
    conn = _connect(path)
    conn.execute("DELETE FROM auth_tokens WHERE token_hash = ?", (t_hash,))
    conn.commit()
    conn.close()


def get_user_profile(user_id: int, db_path: Optional[str] = None) -> Optional[Dict[str, Any]]:
    """Fetch user profile metadata, account creation date, and total conversation count."""
    path = db_path or str(AUTH_DB_PATH)
    conn = _connect(path)
    conn.row_factory = sqlite3.Row
    try:
        row = conn.execute(
            """
            SELECT u.id, u.username, u.email, u.created_at,
                   (SELECT COUNT(*) FROM conversations c WHERE c.user_id = u.id) AS conversation_count
            FROM users u
            WHERE u.id = ?
            """,
            (user_id,),
        ).fetchone()
        return dict(row) if row else None
    finally:
        conn.close()


def update_user_username(user_id: int, new_username: str, db_path: Optional[str] = None) -> Dict[str, Any]:
    """Update a user's display username after format and uniqueness validation."""
    try:
        model = UpdateUsernameModel(username=new_username)
    except Exception as e:
        return {"error": str(e)}

    path = db_path or str(AUTH_DB_PATH)
    conn = _connect(path)
    try:
        existing = conn.execute("SELECT id FROM users WHERE username = ? AND id != ?", (model.username, user_id)).fetchone()
        if existing:
            return {"error": "This username is already taken."}
        conn.execute("UPDATE users SET username = ? WHERE id = ?", (model.username, user_id))
        conn.commit()
        return {"ok": True, "username": model.username}
    finally:
        conn.close()


def change_user_password(user_id: int, old_password: str, new_password: str, db_path: Optional[str] = None) -> Dict[str, Any]:
    """Verify existing password and set a new password hash for user_id."""
    try:
        model = ChangePasswordModel(old_password=old_password, new_password=new_password)
    except Exception as e:
        return {"error": str(e)}

    path = db_path or str(AUTH_DB_PATH)
    conn = _connect(path)
    conn.row_factory = sqlite3.Row
    try:
        row = conn.execute("SELECT password_hash, salt FROM users WHERE id = ?", (user_id,)).fetchone()
        if not row:
            return {"error": "User not found."}

        valid, _ = _verify_password(model.old_password, row["password_hash"], row["salt"])
        if not valid:
            return {"error": "Current password is incorrect."}

        new_hash = _hash_new_password(model.new_password)
        conn.execute("UPDATE users SET password_hash = ?, salt = NULL WHERE id = ?", (new_hash, user_id))
        conn.commit()
        return {"ok": True}
    finally:
        conn.close()


def revoke_all_user_sessions(user_id: int, db_path: Optional[str] = None) -> int:
    """Invalidate all active sessions for a user."""
    path = db_path or str(AUTH_DB_PATH)
    conn = _connect(path)
    try:
        cur = conn.execute("DELETE FROM auth_tokens WHERE user_id = ?", (user_id,))
        conn.commit()
        return cur.rowcount
    finally:
        conn.close()


def save_message(conversation_id: str, user_id: int, role: str, content: str,
                 response_data: Optional[Dict[str, Any]] = None,
                 title: Optional[str] = None, db_path: Optional[str] = None,
                 export_data: Optional[str] = None):
    """Save message under conversation, creating conversation if needed.

    ``export_data`` is an optional JSON string for CSV export (export_store.py). Only the
    newest one per conversation is kept: saving a new one clears older ones.
    """
    if not is_valid_conversation_id(conversation_id):
        raise PermissionError("Invalid conversation id")
    path = db_path or str(AUTH_DB_PATH)
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    conn = _connect(path)
    now = datetime.now(timezone.utc).isoformat()
    try:
        existing = conn.execute("SELECT id FROM conversations WHERE id = ?", (conversation_id,)).fetchone()
        if not existing:
            display_title = _make_title(title or content)
            conn.execute(
                "INSERT INTO conversations (id, user_id, title, created_at, updated_at) VALUES (?,?,?,?,?)",
                (conversation_id, user_id, display_title, now, now),
            )
        else:
            owner = conn.execute("SELECT user_id FROM conversations WHERE id = ?", (conversation_id,)).fetchone()
            if not owner or owner[0] != user_id:
                raise PermissionError("Conversation not found or access denied")
            conn.execute("UPDATE conversations SET updated_at = ? WHERE id = ? AND user_id = ?", (now, conversation_id, user_id))

        resp_json = json.dumps(response_data) if response_data else None
        if export_data:
            conn.execute("UPDATE chat_messages SET export_data = NULL WHERE conversation_id = ? AND export_data IS NOT NULL", (conversation_id,))
        conn.execute(
            "INSERT INTO chat_messages (conversation_id, role, content, response_data, export_data, created_at) VALUES (?,?,?,?,?,?)",
            (conversation_id, role, content, resp_json, export_data or None, now),
        )
        conn.commit()
    finally:
        conn.close()


def get_latest_export(conversation_id: str, user_id: int, db_path: Optional[str] = None) -> Optional[str]:
    """Return the stored export JSON string for a conversation owned by ``user_id`` (or None)."""
    path = db_path or str(AUTH_DB_PATH)
    conn = _connect(path)
    try:
        owner = conn.execute("SELECT user_id FROM conversations WHERE id = ?", (conversation_id,)).fetchone()
        if not owner or owner[0] != user_id:
            return None
        row = conn.execute(
            "SELECT export_data FROM chat_messages WHERE conversation_id = ? AND export_data IS NOT NULL ORDER BY id DESC LIMIT 1",
            (conversation_id,),
        ).fetchone()
        return row[0] if row else None
    finally:
        conn.close()


def _clamp_limit(limit: Any) -> int:
    """SQLite LIMIT value. ``None`` (or anything unusable) means *no limit* (-1 in SQLite);
    a number is honoured as given (minimum 1). There is deliberately no upper cap."""
    if limit is None:
        return -1
    try:
        return max(1, int(limit))
    except (TypeError, ValueError):
        return -1


def get_conversations(user_id: int, db_path: Optional[str] = None, limit: Optional[int] = None) -> List[Dict[str, Any]]:
    """Fetch ALL of the user's conversation threads (newest first); ``limit`` is optional paging only."""
    path = db_path or str(AUTH_DB_PATH)
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    conn = _connect(path)
    conn.row_factory = sqlite3.Row
    try:
        rows = conn.execute("""
            SELECT c.id, c.title, c.created_at, c.updated_at,
                   (SELECT COUNT(*) FROM chat_messages m WHERE m.conversation_id = c.id) AS message_count
            FROM conversations c 
            WHERE c.user_id = ? 
            ORDER BY c.updated_at DESC
            LIMIT ?
        """, (user_id, _clamp_limit(limit))).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def conversation_owned(conversation_id: str, user_id: int, db_path: Optional[str] = None) -> bool:
    """True if ``conversation_id`` exists and belongs to ``user_id`` (a direct lookup: works for
    any number of conversations, unlike scanning a paged list)."""
    if not is_valid_conversation_id(conversation_id):
        return False
    path = db_path or str(AUTH_DB_PATH)
    conn = _connect(path)
    try:
        row = conn.execute("SELECT user_id FROM conversations WHERE id = ?", (conversation_id,)).fetchone()
        return bool(row) and row[0] == user_id
    finally:
        conn.close()


def get_conversation_messages(conversation_id: str, user_id: int, db_path: Optional[str] = None) -> List[Dict[str, Any]]:
    """Fetch conversation messages after ownership verification."""
    path = db_path or str(AUTH_DB_PATH)
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    conn = _connect(path)
    conn.row_factory = sqlite3.Row
    try:
        owner = conn.execute("SELECT user_id FROM conversations WHERE id = ?", (conversation_id,)).fetchone()
        if not owner or owner["user_id"] != user_id:
            return []

        rows = conn.execute("""
            SELECT role, content, response_data, created_at 
            FROM chat_messages 
            WHERE conversation_id = ? 
            ORDER BY created_at ASC, id ASC
        """, (conversation_id,)).fetchall()

        results = []
        for r in rows:
            m = dict(r)
            if m["response_data"]:
                try:
                    m["response_data"] = json.loads(m["response_data"])
                except Exception:
                    pass
            results.append(m)
        return results
    finally:
        conn.close()


def delete_conversation(conversation_id: str, user_id: int, db_path: Optional[str] = None) -> bool:
    """Delete conversation and all its messages."""
    path = db_path or str(AUTH_DB_PATH)
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    conn = _connect(path)
    try:
        owner = conn.execute("SELECT user_id FROM conversations WHERE id = ?", (conversation_id,)).fetchone()
        if not owner or owner[0] != user_id:
            return False
        conn.execute("DELETE FROM shared_chats WHERE conversation_id = ?", (conversation_id,))
        conn.execute("DELETE FROM chat_messages WHERE conversation_id = ?", (conversation_id,))
        conn.execute("DELETE FROM conversations WHERE id = ?", (conversation_id,))
        conn.commit()
        return True
    finally:
        conn.close()


def search_conversations(user_id: int, query: str, db_path: Optional[str] = None, limit: Optional[int] = None) -> List[Dict[str, Any]]:
    """Search user conversations by title or message contents (LIKE wildcards are escaped)."""
    query = (query or "").strip()
    if not query:
        return get_conversations(user_id, db_path, limit)
    path = db_path or str(AUTH_DB_PATH)
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    conn = _connect(path)
    conn.row_factory = sqlite3.Row
    escaped = query.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    term = f"%{escaped}%"
    try:
        rows = conn.execute("""
            SELECT c.id, c.title, c.created_at, c.updated_at,
                   (SELECT COUNT(*) FROM chat_messages x WHERE x.conversation_id = c.id) AS message_count
            FROM conversations c
            WHERE c.user_id = ?
              AND (c.title LIKE ? ESCAPE '\\'
                   OR EXISTS (SELECT 1 FROM chat_messages m
                              WHERE m.conversation_id = c.id AND m.content LIKE ? ESCAPE '\\'))
            ORDER BY c.updated_at DESC LIMIT ?
        """, (user_id, term, term, _clamp_limit(limit))).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


# ── Chat sharing (read-only public snapshot links) ───────────────────────────
# A share link is a capability URL: anyone holding the token can read a *snapshot* of the chat
# (messages up to the moment of sharing; later messages are not exposed). The owner can refresh
# the snapshot or revoke the link at any time. No username/email is ever included.

def _snapshot_messages(messages: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    return [{"role": m.get("role"), "content": m.get("content"),
             "response_data": m.get("response_data") if isinstance(m.get("response_data"), dict) else None,
             "created_at": m.get("created_at")} for m in messages]


def create_or_refresh_share(conversation_id: str, user_id: int, db_path: Optional[str] = None) -> Optional[Dict[str, Any]]:
    """Create (or refresh the snapshot of) the share link for an owned conversation.
    Returns {"token", "title"} or None if the conversation is missing / not owned / empty."""
    if not conversation_owned(conversation_id, user_id, db_path):
        return None
    messages = get_conversation_messages(conversation_id, user_id, db_path)
    if not messages:
        return None
    path = db_path or str(AUTH_DB_PATH)
    now = datetime.now(timezone.utc).isoformat()
    conn = _connect(path)
    try:
        title = conn.execute("SELECT title FROM conversations WHERE id = ?", (conversation_id,)).fetchone()[0] or "Shared chat"
        snap = json.dumps(_snapshot_messages(messages))
        row = conn.execute("SELECT token FROM shared_chats WHERE conversation_id = ?", (conversation_id,)).fetchone()
        if row:
            token = row[0]
            conn.execute("UPDATE shared_chats SET snapshot = ?, title = ?, updated_at = ? WHERE token = ?", (snap, title, now, token))
        else:
            token = secrets.token_urlsafe(24)
            conn.execute(
                "INSERT INTO shared_chats (token, conversation_id, user_id, title, snapshot, created_at, updated_at) VALUES (?,?,?,?,?,?,?)",
                (token, conversation_id, user_id, title, snap, now, now),
            )
        conn.commit()
        return {"token": token, "title": title}
    finally:
        conn.close()


def revoke_share(conversation_id: str, user_id: int, db_path: Optional[str] = None) -> bool:
    """Stop sharing an owned conversation. True if the conversation is owned (idempotent)."""
    if not conversation_owned(conversation_id, user_id, db_path):
        return False
    path = db_path or str(AUTH_DB_PATH)
    conn = _connect(path)
    try:
        conn.execute("DELETE FROM shared_chats WHERE conversation_id = ? AND user_id = ?", (conversation_id, user_id))
        conn.commit()
        return True
    finally:
        conn.close()


def get_share_status(conversation_id: str, user_id: int, db_path: Optional[str] = None) -> Optional[str]:
    """Return the active share token of an owned conversation, else None."""
    if not conversation_owned(conversation_id, user_id, db_path):
        return None
    path = db_path or str(AUTH_DB_PATH)
    conn = _connect(path)
    try:
        row = conn.execute("SELECT token FROM shared_chats WHERE conversation_id = ? AND user_id = ?", (conversation_id, user_id)).fetchone()
        return row[0] if row else None
    finally:
        conn.close()


def get_shared_chat(token: str, db_path: Optional[str] = None) -> Optional[Dict[str, Any]]:
    """Public read of a shared snapshot by token (None if unknown / revoked)."""
    if not isinstance(token, str) or not SHARE_TOKEN_RE.match(token):
        return None
    path = db_path or str(AUTH_DB_PATH)
    conn = _connect(path)
    try:
        row = conn.execute("SELECT title, snapshot, updated_at FROM shared_chats WHERE token = ?", (token,)).fetchone()
        if not row:
            return None
        try:
            messages = json.loads(row[1])
        except Exception:
            return None
        return {"title": row[0] or "Shared chat", "messages": messages, "shared_at": row[2]}
    finally:
        conn.close()
