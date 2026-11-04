"""Regression tests for the 16 FloatChat audit bug fixes."""
import sys
import os
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))
from rule_intent import parse_intent


def test_bug_01_followup_inherits_filters_and_does_not_switch_to_pressure():
    # Last data intent: salinity, avg, year 2023, month 1, pressure_max 500
    history = [
        {
            "role": "assistant",
            "intent_summary": {
                "task": "stat",
                "question_kind": "data",
                "variable": "salinity",
                "stat": "avg",
                "year": 2023,
                "month": 1,
                "pressure_min": None,
                "pressure_max": 500.0,
            },
        }
    ]

    # Follow-up naming month: "what about August?"
    intent_aug = parse_intent("what about August?", history=history)
    assert intent_aug["variable"] == "salinity"
    assert intent_aug["stat"] == "avg"
    assert intent_aug["year"] == 2023
    assert intent_aug["month"] == 8
    assert intent_aug["pressure_max"] == 500.0

    # Follow-up naming year: "and in 2024?"
    intent_2024 = parse_intent("and in 2024?", history=history)
    assert intent_2024["variable"] == "salinity"
    assert intent_2024["stat"] == "avg"
    assert intent_2024["year"] == 2024
    assert intent_2024["month"] == 1
    assert intent_2024["pressure_max"] == 500.0

    # Follow-up naming depth: "at 500 dbar" must keep previous variable (salinity), not switch to "pressure"
    intent_depth = parse_intent("at 500 dbar", history=history)
    assert intent_depth["variable"] == "salinity"
    assert intent_depth["stat"] == "avg"
    assert intent_depth["year"] == 2023
    assert intent_depth["month"] == 1
    assert intent_depth["pressure_min"] == 500.0
    assert intent_depth["pressure_max"] == 500.0


def test_bug_02_extreme_month_shortcut_respects_year_region_and_which_month():
    from main import _question_guard, _extreme_month_answer, _EXTREME_MONTH_RE

    # 1. Regex matches "which month was warmest" as well as "warmest month"
    m1 = _EXTREME_MONTH_RE.search("which month was warmest")
    assert m1 is not None
    word1 = (m1.group(1) or m1.group(2)).lower()
    assert word1 == "warmest"

    m2 = _EXTREME_MONTH_RE.search("which month was the coldest")
    assert m2 is not None
    word2 = (m2.group(1) or m2.group(2)).lower()
    assert word2 == "coldest"

    # 2. _question_guard triggers for "which month was warmest in 2023"
    intent_2023 = {"question_kind": "data", "task": "stat", "year": 2023, "named_region": None}
    res = _question_guard("Which month was warmest in 2023?", "which month was warmest in 2023?", intent_2023)
    assert res is not None
    ans, _ = res
    assert "in 2023" in ans
    assert "2023" in ans

    # 3. Year filtering is respected: only months from 2024 are ranked
    intent_2024 = {"question_kind": "data", "task": "stat", "year": 2024, "named_region": None}
    ans_2024 = _extreme_month_answer("warmest", intent=intent_2024)
    assert ans_2024 is not None
    assert "in 2024" in ans_2024
    assert "2024" in ans_2024
    assert "2023" not in ans_2024.split("Monthly means:")[1].split(". The dataset")[0]

    # 4. Region filtering is respected
    intent_region = {"question_kind": "data", "task": "stat", "year": 2023, "named_region": "Central Bay of Bengal"}
    ans_region = _extreme_month_answer("warmest", intent=intent_region)
    assert ans_region is not None
    assert "in Central Bay of Bengal" in ans_region


def test_bug_03_invalid_or_expired_bearer_token_returns_401():
    from fastapi.testclient import TestClient
    from main import app

    client = TestClient(app)

    # 1. Unauthenticated guest request succeeds on /api/chat
    r_guest = client.post("/api/chat", json={"question": "What is a thermocline?"})
    assert r_guest.status_code == 200

    # 2. Invalid Bearer token must return 401, not silently treat user as guest
    r_invalid = client.post(
        "/api/chat",
        json={"question": "What is a thermocline?"},
        headers={"Authorization": "Bearer invalid_or_expired_token_1234567890"},
    )
    assert r_invalid.status_code == 401
    assert "Invalid or expired token" in r_invalid.json().get("detail", "")


def test_bug_04_packaging_excludes_databases_and_removes_auth_db():
    from pathlib import Path
    import sys
    sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))
    from package import should_include

    # 1. Shipped auth database with real account must not exist in backend/
    auth_db_shipped = Path(__file__).resolve().parent.parent / "backend" / "floatchat_auth.db"
    assert not auth_db_shipped.exists()

    # 2. Package inclusion rule must exclude both floatchat.db and floatchat_auth.db
    assert not should_include(Path("backend/floatchat.db"))
    assert not should_include(Path("backend/floatchat_auth.db"))
    assert not should_include(Path("floatchat.db"))
    assert not should_include(Path("floatchat_auth.db"))
    assert not should_include(Path(".env"))
    assert should_include(Path("backend/main.py"))

    # 3. .gitignore must ignore database files
    gitignore_path = Path(__file__).resolve().parent.parent / ".gitignore"
    content = gitignore_path.read_text(encoding="utf-8")
    assert "*.db" in content
    assert "floatchat_auth.db" in content
    assert "floatchat.db" in content


def test_bug_05_date_parsing_edge_cases():
    from rule_intent import parse_intent

    # 1. "Feb 2023 and Mar 2023" (same year with explicit years is comparison)
    i1 = parse_intent("Compare temperature in Feb 2023 and Mar 2023")
    assert i1.get("compare") is True
    assert i1.get("compare_months") == [2, 3]

    # 2. "02/2023" slash format
    i2 = parse_intent("Salinity in 02/2023")
    assert i2.get("month") == 2
    assert i2.get("year") == 2023

    # 3. "January 2023 to 2024" preserves month January (1)
    i3 = parse_intent("Temperature from January 2023 to 2024")
    assert i3.get("month") == 1
    assert i3.get("year") == 2023
    assert i3.get("year_end") == 2024

    # 4. Impossible dates ("February 30", "April 31")
    i4 = parse_intent("Salinity on February 30 2023")
    assert i4.get("ambiguous") is True
    assert "February 30" in i4.get("clarification_needed", "")

    i4b = parse_intent("Temperature on April 31 2023")
    assert i4b.get("ambiguous") is True
    assert "April 31" in i4b.get("clarification_needed", "")

    # 5. Unsupported relative dates ("last month", "yesterday")
    i5 = parse_intent("What was the temperature yesterday?")
    assert i5.get("ambiguous") is True
    assert "yesterday" in i5.get("clarification_needed", "")


def test_bug_06_where_is_float_trajectory():
    from rule_intent import parse_intent

    # 1. "where is float 2902758"
    i1 = parse_intent("where is float 2902758")
    assert i1.get("task") == "trajectory"
    assert i1.get("chart_type") == "trajectory"
    assert i1.get("platform_id") == "2902758"
    assert i1.get("variable") is None

    # 2. "where is platform 2902758"
    i2 = parse_intent("where is platform 2902758")
    assert i2.get("task") == "trajectory"
    assert i2.get("chart_type") == "trajectory"
    assert i2.get("platform_id") == "2902758"

    # 3. "show me where float 2902758 is"
    i3 = parse_intent("show me where float 2902758 is")
    assert i3.get("task") == "trajectory"
    assert i3.get("chart_type") == "trajectory"
    assert i3.get("platform_id") == "2902758"


def test_bug_07_qc_filtering_and_db_cleanup():
    import sqlite3
    import tempfile
    from ingestion.fetch_and_load import parse_profile_detail, cleanup_db

    # 1. parse_profile_detail drops QC in (3, 4, 9), negative pressure, and salinity < 2.0
    mock_detail = {
        "data_info": [["temperature", "pressure", "salinity"]],
        "data": [
            [1, 28.5, 4, 29.0, 1, 27.0, 1, 26.0],  # temp: [qc0, val0, qc1, val1, qc2, val2, qc3, val3] (qc1=4 is bad)
            [10.0, 11.0, 20.0, 21.0, -5.0, -4.0, 30.0, 31.0],  # pres: pairs [lower, upper] (pres2=-5.0 is negative)
            [1, 34.5, 1, 35.0, 1, 34.8, 1, 0.5],   # sal: [qc, val] (val3=0.5 is impossible salinity < 2.0)
        ]
    }
    rows = parse_profile_detail(mock_detail)
    # Total levels: 4. Level 2 (pres=-5.0) is dropped completely.
    # Level 0: pres=10.0, temp=28.5, sal=34.5
    # Level 1: pres=20.0, temp=None (bad QC 4), sal=35.0
    # Level 3: pres=30.0, temp=26.0, sal=None (sal 0.5 < 2.0 dropped)
    assert len(rows) == 3
    assert rows[0] == (10.0, 28.5, 34.5)
    assert rows[1] == (20.0, None, 35.0)
    assert rows[2] == (30.0, 26.0, None)

    # 2. Verify floatchat.db has zero negative pressure rows and zero salinity < 2.0
    db_path = os.path.join(os.path.dirname(__file__), "..", "backend", "floatchat.db")
    if os.path.exists(db_path):
        conn = sqlite3.connect(db_path)
        cur = conn.cursor()
        neg_pres = cur.execute("SELECT COUNT(*) FROM measurements WHERE pressure < 0").fetchone()[0]
        bad_sal = cur.execute("SELECT COUNT(*) FROM measurements WHERE salinity IS NOT NULL AND salinity < 2.0").fetchone()[0]
        conn.close()
        assert neg_pres == 0
        assert bad_sal == 0

    # 3. Test cleanup_db on a temporary database
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as tf:
        tpath = tf.name
    try:
        conn = sqlite3.connect(tpath)
        conn.execute("CREATE TABLE measurements (profile_id TEXT, pressure REAL, temperature REAL, salinity REAL)")
        conn.execute("INSERT INTO measurements VALUES ('p1', -10.0, 25.0, 35.0)")
        conn.execute("INSERT INTO measurements VALUES ('p2', 10.0, 25.0, 0.5)")
        conn.execute("INSERT INTO measurements VALUES ('p3', 10.0, 25.0, 35.0)")
        conn.commit()
        conn.close()

        res = cleanup_db(tpath)
        assert res["deleted_pressure_lt_0"] == 1
        assert res["updated_salinity_lt_2"] == 1

        conn = sqlite3.connect(tpath)
        cur = conn.cursor()
        rows_after = cur.execute("SELECT pressure, salinity FROM measurements").fetchall()
        conn.close()
        assert len(rows_after) == 2
        assert rows_after[0] == (10.0, None)  # sal was 0.5 -> set to None
        assert rows_after[1] == (10.0, 35.0)
    finally:
        if os.path.exists(tpath):
            os.remove(tpath)


def test_bug_13_loader_savepoint_and_error_logging():
    import sqlite3
    from ingestion import fetch_and_load

    # Verify that load_measurements wraps each profile in a SAVEPOINT load_profile
    # and rolls back on failure without leaving corrupt half-deleted state
    with sqlite3.connect(":memory:") as conn:
        conn.execute("CREATE TABLE measurements (profile_id TEXT, pressure REAL, temperature REAL, salinity REAL)")
        conn.execute("INSERT INTO measurements VALUES ('p_fail', 10.0, 20.0, 35.0)")
        conn.commit()

        # Monkeypatch fetch_profile_detail to fail on 'p_fail'
        orig_fetch = fetch_and_load.fetch_profile_detail
        try:
            fetch_and_load.fetch_profile_detail = lambda pid: 1 / 0
            loaded, levels = fetch_and_load.load_measurements(conn, ["p_fail"], incremental=False)
            assert loaded == 0
            # Ensure rollback preserved the original record
            cur = conn.cursor()
            rows = cur.execute("SELECT * FROM measurements WHERE profile_id = 'p_fail'").fetchall()
            assert len(rows) == 1
        finally:
            fetch_and_load.fetch_profile_detail = orig_fetch


def test_bug_08_andaman_sea_not_suggested_as_subregion():
    from main import _question_guard

    intent = {"question_kind": "data", "task": "stat"}
    # Unsupported region query, e.g. Arabian Sea
    ans, clar = _question_guard("What is the temperature in the Arabian Sea?", "what is the temperature in the arabian sea?", intent)
    assert ans is not None
    assert "Arabian Sea" in ans
    assert "Andaman Sea" not in ans
    assert "sub-regions (north, central, south, Sri Lanka)" in ans


def test_bug_09_login_rate_limiting_and_xff():
    from fastapi.testclient import TestClient
    from main import app, _get_client_ip, _RATE_LIMITS, _LOGIN_ATTEMPTS
    from starlette.requests import Request
    from starlette.datastructures import Headers

    client = TestClient(app)

    # 1. Per-email login throttling
    _LOGIN_ATTEMPTS.clear()
    target_email = "victim_test_email@example.com"
    for _ in range(5):
        resp = client.post("/api/login", json={"email": target_email, "password": "wrong_password"})
        assert resp.status_code == 401

    # 6th attempt should be blocked with 429
    resp_blocked = client.post("/api/login", json={"email": target_email, "password": "wrong_password"})
    assert resp_blocked.status_code == 429
    assert "Too many failed login attempts" in resp_blocked.json()["detail"]
    _LOGIN_ATTEMPTS.clear()

    # 2. X-Forwarded-For support with TRUST_X_FORWARDED_FOR
    os.environ["TRUST_X_FORWARDED_FOR"] = "true"
    scope = {
        "type": "http",
        "headers": [(b"x-forwarded-for", b"203.0.113.195, 70.41.3.18")],
        "client": ("127.0.0.1", 12345),
    }
    req = Request(scope)
    assert _get_client_ip(req) == "203.0.113.195"

    os.environ["TRUST_X_FORWARDED_FOR"] = "false"
    assert _get_client_ip(req) == "127.0.0.1"


def test_bug_10_cache_deepcopy_and_lru():
    from collections import OrderedDict
    from main import _INTENT_CACHE, _get_cached_intent, _set_cached_intent

    assert isinstance(_INTENT_CACHE, OrderedDict)
    _INTENT_CACHE.clear()

    # 1. Deepcopy prevents mutation of cached data
    original_intent = {"variable": "temperature", "stat": "avg", "subdict": {"flag": True}}
    _set_cached_intent("test_key_1", original_intent)

    retrieved = _get_cached_intent("test_key_1")
    assert retrieved == original_intent
    retrieved["variable"] = "salinity"
    retrieved["subdict"]["flag"] = False

    retrieved_again = _get_cached_intent("test_key_1")
    assert retrieved_again["variable"] == "temperature"
    assert retrieved_again["subdict"]["flag"] is True

    # 2. LRU access moves key to end
    _set_cached_intent("test_key_2", {"variable": "pressure"})
    assert list(_INTENT_CACHE.keys()) == ["test_key_1", "test_key_2"]
    _get_cached_intent("test_key_1")
    assert list(_INTENT_CACHE.keys()) == ["test_key_2", "test_key_1"]
    _INTENT_CACHE.clear()


def test_bug_11_frontend_escape_html_and_blob_revocation():
    script_path = Path(__file__).resolve().parent.parent / "frontend" / "script.js"
    content = script_path.read_text(encoding="utf-8")

    # 1. escapeHtml handles 0 properly without blanking it out
    assert 'if (str == null || str === "") return "";' in content
    assert 'if (!str) return "";' not in content

    # 2. Blob downloads append anchor to document.body and delay revocation
    assert "document.body.appendChild(a);" in content
    assert "document.body.removeChild(a);" in content
    assert "setTimeout(() => URL.revokeObjectURL(url)" in content


def test_bug_12_fallback_coverage_date():
    import config
    assert config._FALLBACK_END == (2024, 12)


def test_bug_14_depth_default_consistency():
    from fastapi.testclient import TestClient
    from main import app

    client = TestClient(app)
    # Question with stat='none' (not explicitly 'avg') where depth is unspecified
    # e.g. "temperature in Jan 2023"
    r = client.post("/api/chat", json={"question": "temperature in January 2023"})
    assert r.status_code == 200
    data = r.json()
    assert data["observation_count"] > 0
    # Answers that applied the 50 dbar upper surface limit mention upper 50 dbar
    # or return observations filtered to upper depth
    assert "50" in data["answer"] or "surface" in data["answer"].lower() or "dbar" in data["answer"]


def test_bug_15_cors_wildcard_with_credentials():
    from main import app
    from starlette.middleware.cors import CORSMiddleware

    cors_middleware = None
    for m in app.user_middleware:
        if m.cls == CORSMiddleware:
            cors_middleware = m
            break

    assert cors_middleware is not None
    allow_origins = cors_middleware.kwargs.get("allow_origins", [])
    allow_credentials = cors_middleware.kwargs.get("allow_credentials", False)

    # Browsers disallow allow_credentials=True when allow_origins is ["*"]
    if allow_credentials:
        assert "*" not in allow_origins
        assert len(allow_origins) > 0


def test_bug_16_float_count_definition_consistency():
    from retrieval.discovery import list_floats, coverage_summary

    floats = list_floats()
    cov = coverage_summary()

    # Both count floats that have measurement rows (37)
    assert len(floats) == 37
    assert cov["total_floats"] == 37


def test_unique_feature_argo_dive_profile_endpoint():
    from fastapi.testclient import TestClient
    from main import app
    client = TestClient(app)

    # 1. Valid platform returns status 200 with physical oceanography metrics
    r = client.get("/api/floats/2902680/dive-profile")
    assert r.status_code == 200
    data = r.json()
    assert data["platform"] == "2902680"
    assert "levels" in data and len(data["levels"]) > 0
    first_level = data["levels"][0]
    assert "pressure" in first_level
    assert "temperature" in first_level
    assert "salinity" in first_level
    assert "sound_speed" in first_level

    # Verify calculated physical features
    assert data["sofar_depth"] is not None
    assert 100.0 <= data["sofar_depth"] <= 2000.0
    assert data["sofar_speed"] is not None
    assert 1450.0 <= data["sofar_speed"] <= 1550.0
    assert data["mixed_layer_depth"] is not None

    # 2. Non-existent float returns 404
    r_bad = client.get("/api/floats/9999999/dive-profile")
    assert r_bad.status_code == 404
