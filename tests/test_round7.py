"""Round 7: unlimited history, username rule, no email enumeration, per-owner export cache, chat sharing."""
import json
import os
import sqlite3
import sys
import time
import uuid

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))

import pytest
import auth


@pytest.fixture()
def db(tmp_path):
    path = str(tmp_path / "r7.db")
    auth.init_auth_db(path)
    conn = sqlite3.connect(path)
    conn.execute("INSERT INTO users (username, email, password_hash) VALUES ('alice','a@x.io','h'),('bob','b@x.io','h')")
    conn.commit()
    conn.close()
    return path


# ── No limit on how many conversations a user can have ───────────────────────

def test_listing_and_ownership_work_beyond_100_and_500_conversations(db):
    conn = auth._connect(db)
    for i in range(650):
        conn.execute("INSERT INTO conversations (id, user_id, title, updated_at) VALUES (?,?,?,?)",
                     (f"c{i}", 1, f"t{i}", f"2024-01-01T00:{i // 60:02d}:{i % 60:02d}"))
    conn.commit()
    conn.close()
    assert len(auth.get_conversations(1, db_path=db)) == 650               # everything, no cap
    assert len(auth.search_conversations(1, "", db_path=db)) == 650
    assert len(auth.get_conversations(1, db_path=db, limit=5000)) == 650   # big limit is not clamped to 500
    assert auth.conversation_owned("c0", 1, db_path=db)                    # the very oldest one
    assert not auth.conversation_owned("c0", 2, db_path=db)
    assert not auth.conversation_owned("nope", 1, db_path=db)
    assert not auth.conversation_owned("bad id!", 1, db_path=db)


# ── Username rule: validation and message agree ──────────────────────────────

@pytest.mark.parametrize("name", ["bad name", "dot.name", "a b", "x.y"])
def test_username_with_space_or_dot_is_rejected(name):
    r = auth.register_user(name, "u@example.com", "Str0ng-Pass-123")
    assert "error" in r
    assert "no spaces or dots" in r["error"]


def test_valid_username_is_accepted(db):
    assert auth.register_user("ok_name-1", "ok@example.com", "Str0ng-Pass-123", db_path=db) == {"ok": True}


# ── Registration does not reveal whether an email exists ─────────────────────

def test_register_same_answer_for_new_and_existing_email(db):
    first = auth.register_user("carol", "carol@example.com", "Str0ng-Pass-123", db_path=db)
    again = auth.register_user("carol2", "CAROL@example.com", "Str0ng-Pass-456", db_path=db)
    assert first == again == {"ok": True}
    conn = sqlite3.connect(db)
    assert conn.execute("SELECT COUNT(*) FROM users WHERE email='carol@example.com'").fetchone()[0] == 1
    assert conn.execute("SELECT COUNT(*) FROM users WHERE username='carol2'").fetchone()[0] == 0
    conn.close()
    # the original password still works; the duplicate attempt did not change it
    assert "token" in auth.login_user("carol@example.com", "Str0ng-Pass-123", db_path=db)
    assert "error" in auth.login_user("carol@example.com", "Str0ng-Pass-456", db_path=db)


def test_username_taken_is_still_reported_for_a_new_email(db):
    auth.register_user("dave", "dave@example.com", "Str0ng-Pass-123", db_path=db)
    r = auth.register_user("dave", "other@example.com", "Str0ng-Pass-123", db_path=db)
    assert r == {"error": "This username is already taken."}


# ── Sharing ──────────────────────────────────────────────────────────────────

def test_share_snapshot_refresh_revoke_and_privacy(db):
    auth.save_message("c1", 1, "user", "hello", db_path=db)
    auth.save_message("c1", 1, "assistant", "hi", response_data={"answer": "hi"}, db_path=db)
    shared = auth.create_or_refresh_share("c1", 1, db_path=db)
    token = shared["token"]
    chat = auth.get_shared_chat(token, db_path=db)
    assert [m["role"] for m in chat["messages"]] == ["user", "assistant"]
    dumped = json.dumps(chat)
    assert "alice" not in dumped and "a@x.io" not in dumped          # owner identity never exposed

    auth.save_message("c1", 1, "user", "later question", db_path=db)
    assert len(auth.get_shared_chat(token, db_path=db)["messages"]) == 2     # snapshot, not live
    assert auth.create_or_refresh_share("c1", 1, db_path=db)["token"] == token  # same link
    assert len(auth.get_shared_chat(token, db_path=db)["messages"]) == 3     # after refresh

    assert auth.get_share_status("c1", 1, db_path=db) == token
    assert auth.revoke_share("c1", 1, db_path=db) is True
    assert auth.get_shared_chat(token, db_path=db) is None
    assert auth.get_share_status("c1", 1, db_path=db) is None


def test_share_requires_ownership_and_content_and_valid_token(db):
    auth.save_message("c1", 1, "user", "hello", db_path=db)
    assert auth.create_or_refresh_share("c1", 2, db_path=db) is None       # not bob's chat
    assert auth.revoke_share("c1", 2, db_path=db) is False
    assert auth.create_or_refresh_share("missing", 1, db_path=db) is None
    assert auth.get_shared_chat("short", db_path=db) is None
    assert auth.get_shared_chat("x" * 30, db_path=db) is None


def test_deleting_a_conversation_kills_its_share_link(db):
    auth.save_message("c1", 1, "user", "hello", db_path=db)
    token = auth.create_or_refresh_share("c1", 1, db_path=db)["token"]
    assert auth.delete_conversation("c1", 1, db_path=db)
    assert auth.get_shared_chat(token, db_path=db) is None


# ── HTTP layer (skipped when FastAPI is not installed) ───────────────────────

def _client():
    pytest.importorskip("fastapi")
    from fastapi.testclient import TestClient
    import main
    from main import app
    main._RATE_LIMITS.clear()   # the whole suite shares one test IP; don't inherit earlier tests' quota
    return TestClient(app)


def _signup(client):
    tag = uuid.uuid4().hex[:10]
    email, pw = f"r7_{tag}@example.com", "Str0ng-Pass-" + tag
    r = client.post("/api/register", json={"username": f"r7_{tag}", "email": email, "password": pw})
    assert r.status_code == 200, r.text
    login = client.post("/api/login", json={"email": email, "password": pw})
    assert login.status_code == 200, login.text
    return {"Authorization": f"Bearer {login.json()['token']}"}, email


def test_api_register_identical_for_new_and_existing_email():
    client = _client()
    headers, email = _signup(client)
    new = client.post("/api/register", json={"username": "zz_" + uuid.uuid4().hex[:8], "email": f"n_{uuid.uuid4().hex[:8]}@example.com", "password": "Str0ng-Pass-999"})
    dup = client.post("/api/register", json={"username": "zz_" + uuid.uuid4().hex[:8], "email": email, "password": "Str0ng-Pass-999"})
    assert new.status_code == dup.status_code == 200
    assert new.json() == dup.json()
    assert "token" not in dup.json() and "already" not in dup.text.lower()


def test_api_username_error_message_matches_rule():
    client = _client()
    r = client.post("/api/register", json={"username": "has space", "email": "s@example.com", "password": "Str0ng-Pass-999"})
    assert r.status_code in (400, 422)
    assert "no spaces or dots" in r.text


def test_api_export_and_reset_work_for_old_conversations_past_100():
    client = _client()
    headers, _ = _signup(client)
    me = client.get("/api/me", headers=headers).json()["user"]["id"]
    conn = auth._connect(str(auth.AUTH_DB_PATH))
    old = "old-" + uuid.uuid4().hex[:8]
    conn.execute("INSERT INTO conversations (id, user_id, title, updated_at) VALUES (?,?,?,?)", (old, me, "oldest", "2000-01-01T00:00:00"))
    for i in range(120):
        conn.execute("INSERT INTO conversations (id, user_id, title) VALUES (?,?,?)", (f"new-{uuid.uuid4().hex[:8]}-{i}", me, f"n{i}"))
    conn.commit(); conn.close()
    assert len(client.get("/api/conversations", headers=headers).json()["conversations"]) == 121
    assert client.post("/api/reset", json={"conversation_id": old}, headers=headers).status_code == 200
    # Owned, so never 404; there is simply nothing saved to export (409).
    assert client.post("/api/export", json={"conversation_id": old}, headers=headers).status_code == 409


def test_export_cache_is_per_owner_purged_and_cleared_on_delete():
    client = _client()
    import main
    headers, _ = _signup(client)
    me = client.get("/api/me", headers=headers).json()["user"]
    cid = str(uuid.uuid4())
    assert client.post("/api/chat", json={"message": "Average temperature in March 2023", "conversation_id": cid}, headers=headers).status_code == 200
    assert main._get_export_result(me, cid) is not None
    assert main._get_export_result(None, cid) is None            # a guest with the same id sees nothing
    assert client.delete(f"/api/conversations/{cid}", headers=headers).status_code == 200
    assert main._get_export_result(me, cid) is None              # deleting the chat drops the cached rows

    # expiry purge + hard bound
    main._last_results.clear()
    main._save_export_result(None, "stale", {"rows": []})
    key = main._export_key(None, "stale")
    main._last_results[key] = (main._last_results[key][0], time.time() - main._EXPORT_TTL_SECS - 1)
    main._save_export_result(None, "fresh", {"rows": []})
    assert key not in main._last_results
    for i in range(main._EXPORT_CACHE_MAX + 50):
        main._save_export_result(None, f"k{i}", {"rows": []})
    assert len(main._last_results) <= main._EXPORT_CACHE_MAX


def test_api_share_flow_public_read_and_revoke():
    client = _client()
    headers, email = _signup(client)
    cid = str(uuid.uuid4())
    assert client.post(f"/api/conversations/{cid}/share", headers=headers).status_code == 404   # nothing saved yet
    assert client.post("/api/chat", json={"message": "Average temperature in March 2023", "conversation_id": cid}, headers=headers).status_code == 200
    assert client.post(f"/api/conversations/{cid}/share").status_code == 401                    # sign-in needed to create
    made = client.post(f"/api/conversations/{cid}/share", headers=headers)
    assert made.status_code == 200
    token = made.json()["token"]
    pub = client.get(f"/api/shared/{token}")                                                      # no auth header
    assert pub.status_code == 200 and len(pub.json()["messages"]) >= 2
    assert email not in pub.text
    assert client.get(f"/api/conversations/{cid}/share", headers=headers).json() == {"shared": True, "token": token}
    assert client.delete(f"/api/conversations/{cid}/share", headers=headers).status_code == 200
    assert client.get(f"/api/shared/{token}").status_code == 404
    other, _ = _signup(client)
    assert client.post(f"/api/conversations/{cid}/share", headers=other).status_code == 404     # not their chat


def test_api_rate_limit_returns_429_response_not_a_crash():
    client = _client()
    import main
    from collections import deque
    import time
    main._RATE_LIMITS["testclient"] = deque([time.time()] * main._MAX_REQUESTS_PER_MINUTE)
    r = client.get("/api/coverage")
    assert r.status_code == 429 and "Too many requests" in r.json()["detail"]
    main._RATE_LIMITS.clear()