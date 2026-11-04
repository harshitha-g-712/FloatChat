"""Regression tests for the conversation-history sidebar (storage layer + API)."""
import os
import sqlite3
import sys
import uuid

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))

import pytest
import auth


# ── Storage layer (isolated temp database, no web framework needed) ──────────

@pytest.fixture()
def db(tmp_path):
    path = str(tmp_path / "history.db")
    auth.init_auth_db(path)
    conn = sqlite3.connect(path)
    conn.execute("INSERT INTO users (username, email, password_hash) VALUES ('alice','a@x.io','h'),('bob','b@x.io','h')")
    conn.commit()
    conn.close()
    return path


def test_save_list_and_reopen_keeps_order_and_chart(db):
    auth.save_message("c1", 1, "user", "avg temp in March", db_path=db)
    auth.save_message("c1", 1, "assistant", "20 C", response_data={"chart_data": '{"data":[1]}'}, db_path=db)
    convs = auth.get_conversations(1, db_path=db)
    assert [(c["id"], c["message_count"]) for c in convs] == [("c1", 2)]
    msgs = auth.get_conversation_messages("c1", 1, db_path=db)
    assert [m["role"] for m in msgs] == ["user", "assistant"]
    assert msgs[1]["response_data"]["chart_data"] == '{"data":[1]}'


def test_users_are_isolated(db):
    auth.save_message("c1", 1, "user", "secret question", db_path=db)
    assert auth.get_conversation_messages("c1", 2, db_path=db) == []
    assert auth.get_conversations(2, db_path=db) == []
    assert auth.search_conversations(2, "secret", db_path=db) == []
    assert auth.delete_conversation("c1", 2, db_path=db) is False
    with pytest.raises(PermissionError):
        auth.save_message("c1", 2, "user", "hijack", db_path=db)
    assert len(auth.get_conversation_messages("c1", 1, db_path=db)) == 1


@pytest.mark.parametrize("wildcard", ["%", "_"])
def test_search_does_not_treat_like_wildcards_as_patterns(db, wildcard):
    auth.save_message("c1", 1, "user", "average temperature", db_path=db)
    assert auth.search_conversations(1, wildcard, db_path=db) == []


def test_search_matches_literal_special_characters_and_has_message_count(db):
    auth.save_message("c1", 1, "user", "100% salinity_check", db_path=db)
    auth.save_message("c2", 1, "user", "something else", db_path=db)
    for term in ("100%", "salinity_c"):
        hits = auth.search_conversations(1, term, db_path=db)
        assert [h["id"] for h in hits] == ["c1"]
        assert hits[0]["message_count"] == 1


def test_blank_search_returns_full_list(db):
    auth.save_message("c1", 1, "user", "one", db_path=db)
    auth.save_message("c2", 1, "user", "two", db_path=db)
    assert len(auth.search_conversations(1, "   ", db_path=db)) == 2


def test_titles_are_truncated_even_when_passed_explicitly(db):
    auth.save_message("c1", 1, "user", "x" * 3000, title="x" * 3000, db_path=db)
    title = auth.get_conversations(1, db_path=db)[0]["title"]
    assert len(title) <= auth.MAX_TITLE_LEN


@pytest.mark.parametrize("bad", ["", "a" * 65, "a/b", "x y", "../etc"])
def test_invalid_conversation_ids_are_rejected(db, bad):
    assert auth.is_valid_conversation_id(bad) is False
    with pytest.raises(PermissionError):
        auth.save_message(bad, 1, "user", "hi", db_path=db)


def test_uuid_and_existing_test_style_ids_are_accepted():
    assert auth.is_valid_conversation_id(str(uuid.uuid4()))
    assert auth.is_valid_conversation_id("api-test-123456")


def test_equal_timestamps_keep_insertion_order(db):
    auth.save_message("c1", 1, "user", "q", db_path=db)
    auth.save_message("c1", 1, "assistant", "a", db_path=db)
    conn = sqlite3.connect(db)
    conn.execute("UPDATE chat_messages SET created_at='2026-01-01T00:00:00'")
    conn.commit()
    conn.close()
    assert [m["role"] for m in auth.get_conversation_messages("c1", 1, db_path=db)] == ["user", "assistant"]


def test_delete_removes_messages(db):
    auth.save_message("c1", 1, "user", "q", db_path=db)
    assert auth.delete_conversation("c1", 1, db_path=db) is True
    assert auth.get_conversations(1, db_path=db) == []
    assert auth.get_conversation_messages("c1", 1, db_path=db) == []


# ── HTTP layer ────────────────────────────────────────────────────────────────

def _signup(client):
    tag = uuid.uuid4().hex[:10]
    r = client.post("/api/register", json={"username": f"hist_{tag}", "email": f"hist_{tag}@example.com", "password": "Str0ng-Pass-" + tag})
    assert r.status_code == 200, r.text
    assert "token" not in r.json()          # registering never signs in (no account enumeration)
    login = client.post("/api/login", json={"email": f"hist_{tag}@example.com", "password": "Str0ng-Pass-" + tag})
    assert login.status_code == 200, login.text
    return {"Authorization": f"Bearer {login.json()['token']}"}


def test_api_history_round_trip_and_isolation():
    pytest.importorskip("fastapi")
    from fastapi.testclient import TestClient
    from main import app
    client = TestClient(app)
    alice, bob = _signup(client), _signup(client)
    cid = str(uuid.uuid4())

    r = client.post("/api/chat", json={"message": "Average temperature in March 2023", "conversation_id": cid}, headers=alice)
    assert r.status_code == 200

    listed = client.get("/api/conversations", headers=alice).json()["conversations"]
    assert cid in [c["id"] for c in listed]
    msgs = client.get(f"/api/conversations/{cid}/messages", headers=alice).json()["messages"]
    assert [m["role"] for m in msgs] == ["user", "assistant"]

    # another account can neither read, write into, nor delete it
    assert client.get(f"/api/conversations/{cid}/messages", headers=bob).json()["messages"] == []
    assert client.post("/api/chat", json={"message": "Average temperature in March 2023", "conversation_id": cid}, headers=bob).status_code == 404
    assert client.delete(f"/api/conversations/{cid}", headers=bob).status_code == 404
    assert client.get("/api/conversations").status_code == 401

    assert client.delete(f"/api/conversations/{cid}", headers=alice).status_code == 200
    assert client.get(f"/api/conversations/{cid}/messages", headers=alice).json()["messages"] == []


def test_api_rejects_malformed_conversation_ids():
    pytest.importorskip("fastapi")
    from fastapi.testclient import TestClient
    from main import app
    client = TestClient(app)
    headers = _signup(client)
    r = client.post("/api/chat", json={"message": "Average temperature in March 2023", "conversation_id": "A" * 200}, headers=headers)
    assert r.status_code == 422
    assert client.get("/api/conversations/" + "A" * 200 + "/messages", headers=headers).status_code == 404


# ── Round-2 fixes: list limits, SQLite settings, crash-safe history, export ──

def test_list_and_search_respect_limit(db):
    for i in range(5):
        auth.save_message(f"c{i}", 1, "user", f"question {i}", db_path=db)
    assert len(auth.get_conversations(1, db_path=db)) == 5
    assert len(auth.get_conversations(1, db_path=db, limit=2)) == 2
    assert len(auth.search_conversations(1, "question", db_path=db, limit=3)) == 3
    assert len(auth.search_conversations(1, "   ", db_path=db, limit=4)) == 4
    # newest first, and a bad limit falls back to something sane instead of crashing
    assert auth.get_conversations(1, db_path=db, limit=1)[0]["id"] == "c4"
    assert len(auth.get_conversations(1, db_path=db, limit="abc")) == 5
    assert len(auth.get_conversations(1, db_path=db, limit=0)) == 1


def test_connection_uses_wal_busy_timeout_and_foreign_keys(db):
    conn = auth._connect(db)
    try:
        assert conn.execute("PRAGMA foreign_keys").fetchone()[0] == 1
        assert conn.execute("PRAGMA busy_timeout").fetchone()[0] >= 10000
        assert conn.execute("PRAGMA journal_mode").fetchone()[0].lower() == "wal"
    finally:
        conn.close()


def test_foreign_key_cascade_now_removes_messages(db):
    auth.save_message("c1", 1, "user", "q", db_path=db)
    conn = auth._connect(db)
    conn.execute("DELETE FROM conversations WHERE id='c1'")
    conn.commit()
    left = conn.execute("SELECT COUNT(*) FROM chat_messages").fetchone()[0]
    conn.close()
    assert left == 0


def _client():
    pytest.importorskip("fastapi")
    from fastapi.testclient import TestClient
    from main import app
    return TestClient(app)


def test_api_conversations_limit_param_is_validated_and_applied():
    client = _client()
    headers = _signup(client)
    for _ in range(3):
        client.post("/api/chat", json={"message": "Average temperature in March 2023", "conversation_id": str(uuid.uuid4())}, headers=headers)
    assert len(client.get("/api/conversations?limit=2", headers=headers).json()["conversations"]) == 2
    assert len(client.get("/api/conversations/search?q=temperature&limit=1", headers=headers).json()["conversations"]) == 1
    assert client.get("/api/conversations?limit=0", headers=headers).status_code == 422
    # there is no upper cap any more: a huge limit is simply "everything"
    assert client.get("/api/conversations?limit=9999", headers=headers).status_code == 200


def test_pipeline_crash_leaves_question_and_error_reply_in_history(monkeypatch):
    import main
    client = _client()
    headers = _signup(client)
    cid = str(uuid.uuid4())

    def boom(*a, **k):
        raise RuntimeError("parser exploded")
    monkeypatch.setattr(main, "parse_question_intent", boom)

    r = client.post("/api/chat", json={"message": "crash test question unique-77", "conversation_id": cid}, headers=headers)
    assert r.status_code == 500
    assert r.json()["detail"] == main.CHAT_FAILURE_MESSAGE   # no stack trace / internals leaked

    msgs = client.get(f"/api/conversations/{cid}/messages", headers=headers).json()["messages"]
    assert [m["role"] for m in msgs] == ["user", "assistant"]
    assert msgs[0]["content"] == "crash test question unique-77"
    assert msgs[1]["content"] == main.CHAT_FAILURE_MESSAGE


def test_crash_before_user_message_saved_does_not_duplicate_or_leak(monkeypatch):
    import main
    client = _client()
    headers = _signup(client)
    cid = str(uuid.uuid4())

    real = main.get_conversation_messages
    calls = {"n": 0}

    def fail_once(*a, **k):          # first call = the pipeline's history load, before the user message is saved
        calls["n"] += 1
        if calls["n"] == 1:
            raise RuntimeError("history load exploded")
        return real(*a, **k)
    monkeypatch.setattr(main, "get_conversation_messages", fail_once)
    r = client.post("/api/chat", json={"message": "another unique question 88", "conversation_id": cid}, headers=headers)
    assert r.status_code == 500
    monkeypatch.undo()
    msgs = client.get(f"/api/conversations/{cid}/messages", headers=headers).json()["messages"]
    assert [m["role"] for m in msgs] == ["user", "assistant"]


def test_export_of_chat_without_cached_results_still_returns_same_csv():
    """Task 1: after the in-memory cache is gone, the CSV is rebuilt from the saved chat."""
    import csv, io
    import main
    client = _client()
    headers = _signup(client)
    cid = str(uuid.uuid4())
    assert client.post("/api/chat", json={"message": "Average temperature in March 2023", "conversation_id": cid}, headers=headers).status_code == 200
    first = client.post("/api/export", json={"conversation_id": cid}, headers=headers)
    assert first.status_code == 200
    main._last_results.clear()                 # simulates a server restart / expired cache
    second = client.post("/api/export", json={"conversation_id": cid}, headers=headers)
    assert second.status_code == 200
    assert second.text == first.text
    rows = list(csv.DictReader(io.StringIO(second.text)))
    assert len(rows) > 0 and "temperature" in rows[0]


def test_export_of_legacy_chat_without_saved_export_data_returns_clear_409():
    import main
    client = _client()
    headers = _signup(client)
    cid = str(uuid.uuid4())
    assert client.post("/api/chat", json={"message": "Average temperature in March 2023", "conversation_id": cid}, headers=headers).status_code == 200
    conn = sqlite3.connect(str(auth.AUTH_DB_PATH))
    conn.execute("UPDATE chat_messages SET export_data = NULL WHERE conversation_id = ?", (cid,))
    conn.commit(); conn.close()
    main._last_results.clear()
    r = client.post("/api/export", json={"conversation_id": cid}, headers=headers)
    assert r.status_code == 409
    assert "Ask the question again" in r.json()["detail"]
