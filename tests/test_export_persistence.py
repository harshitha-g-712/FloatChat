"""Task 1: CSV export data is saved with the chat and survives an empty in-memory cache."""
import csv
import io
import json
import os
import sqlite3
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))

import pytest
import auth
import export_store as es
from retrieval.query_engine import retrieve


@pytest.fixture()
def db(tmp_path):
    path = str(tmp_path / "history.db")
    auth.init_auth_db(path)
    conn = sqlite3.connect(path)
    conn.execute("INSERT INTO users (username, email, password_hash) VALUES ('alice','a@x.io','h'),('bob','b@x.io','h')")
    conn.commit(); conn.close()
    return path


INTENT = {"task": "stat", "variable": "temperature", "stat": "avg", "month": 3, "year": 2023, "pressure_max": 50.0}


def _rows(text):
    return list(csv.DictReader(io.StringIO(text)))


def test_roundtrip_rows_identical_after_cache_cleared(db):
    result = retrieve(INTENT)
    assert result["rows"], "bundled DB must have March 2023 rows"
    live_csv, name = es.csv_for_result(result)
    auth.save_message("c1", 1, "assistant", "ans", export_data=es.build_export_payload("stat", INTENT, result), db_path=db)
    restored = es.resolve_result(auth.get_latest_export("c1", 1, db_path=db), retrieve)
    rebuilt_csv, name2 = es.csv_for_result(restored)
    assert name == name2 == "floatchat_observations.csv"
    assert rebuilt_csv == live_csv
    assert len(_rows(rebuilt_csv)) == len(result["rows"])


def test_large_result_stores_only_intent_and_is_rebuilt_from_database(db, monkeypatch):
    result = retrieve(INTENT)
    monkeypatch.setattr(es, "MAX_STORED_BYTES", 500)       # force the cap
    payload = es.build_export_payload("stat", INTENT, result)
    stored = json.loads(payload)
    assert stored["truncated"] is True and stored["result"] is None
    assert len(payload) < 2000                              # intent only: tiny
    auth.save_message("c1", 1, "assistant", "ans", export_data=payload, db_path=db)
    restored = es.resolve_result(auth.get_latest_export("c1", 1, db_path=db), retrieve)
    assert es.csv_for_result(restored)[0] == es.csv_for_result(result)[0]


def test_row_cap_applies(monkeypatch):
    monkeypatch.setattr(es, "MAX_STORED_ROWS", 3)
    payload = es.build_export_payload("stat", INTENT, {"rows": [{"id": i} for i in range(10)]})
    assert json.loads(payload)["truncated"] is True


def test_oversized_discovery_result_is_not_stored(monkeypatch):
    monkeypatch.setattr(es, "MAX_STORED_BYTES", 100)
    assert es.build_export_payload("discover_floats", {}, {"floats": [{"platform": "x" * 50}] * 20}) is None


def test_only_latest_payload_per_conversation_is_kept(db):
    auth.save_message("c1", 1, "assistant", "a1", export_data='{"v":1,"n":1}', db_path=db)
    auth.save_message("c1", 1, "assistant", "a2", export_data='{"v":1,"n":2}', db_path=db)
    auth.save_message("c1", 1, "assistant", "a3", db_path=db)    # no export (e.g. clarification): keeps previous
    conn = sqlite3.connect(db)
    n = conn.execute("SELECT COUNT(*) FROM chat_messages WHERE export_data IS NOT NULL").fetchone()[0]
    conn.close()
    assert n == 1
    assert json.loads(auth.get_latest_export("c1", 1, db_path=db))["n"] == 2


def test_other_users_cannot_read_export(db):
    auth.save_message("c1", 1, "assistant", "a", export_data='{"v":1}', db_path=db)
    assert auth.get_latest_export("c1", 2, db_path=db) is None
    assert auth.get_latest_export("nope", 1, db_path=db) is None


def test_export_data_is_never_returned_to_the_browser(db):
    auth.save_message("c1", 1, "assistant", "a", response_data={"x": 1}, export_data='{"v":1,"secret":"rows"}', db_path=db)
    msgs = auth.get_conversation_messages("c1", 1, db_path=db)
    assert "export_data" not in msgs[0] and "secret" not in json.dumps(msgs)


def test_legacy_database_is_migrated(tmp_path):
    path = str(tmp_path / "legacy.db")
    conn = sqlite3.connect(path)
    conn.executescript("""
        CREATE TABLE users (id INTEGER PRIMARY KEY AUTOINCREMENT, username TEXT, email TEXT, password_hash TEXT, salt TEXT, created_at TEXT);
        CREATE TABLE conversations (id TEXT PRIMARY KEY, user_id INTEGER, title TEXT, created_at TEXT, updated_at TEXT);
        CREATE TABLE chat_messages (id INTEGER PRIMARY KEY AUTOINCREMENT, conversation_id TEXT, role TEXT, content TEXT, response_data TEXT, created_at TEXT);
        INSERT INTO users (username,email,password_hash) VALUES ('a','a@x.io','h');
    """)
    conn.commit(); conn.close()
    auth.init_auth_db(path)
    auth.save_message("c1", 1, "assistant", "a", export_data='{"v":1}', db_path=path)
    assert auth.get_latest_export("c1", 1, db_path=path) == '{"v":1}'


def test_garbage_or_missing_payload_returns_none():
    assert es.resolve_result(None, retrieve) is None
    assert es.resolve_result("not json", retrieve) is None
    assert es.resolve_result('{"task":"stat","result":null,"intent":"x"}', retrieve) is None
    assert es.csv_for_result(None) is None and es.csv_for_result({}) is None


def test_discovery_csv_shapes():
    text, name = es.csv_for_result({"floats": [{"platform": "1", "profile_count": 3, "first_date": "a", "last_date": "b", "avg_max_depth": 1.0}]})
    assert name == "floatchat_floats.csv" and _rows(text)[0]["platform"] == "1"
    assert es.csv_for_result({"coverage": {"profiles": 244}})[1] == "floatchat_coverage.csv"
