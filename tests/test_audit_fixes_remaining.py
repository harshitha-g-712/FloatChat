"""Regression tests for the 7 audit bug fixes."""
import os
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))
from main import app

client = TestClient(app)


def test_bug_01_depth_profile_not_capped_at_50_dbar():
    # 1. Depth profile question for float 1902198 returns observations deeper than 50 dbar up to ~2000 dbar
    r = client.post("/api/chat", json={"message": "show temperature depth profile for float 1902198"})
    assert r.status_code == 200
    data = r.json()
    assert data["observation_count"] > 1000
    assert data["chart_type"] == "depth_profile"

    # 2. Depth profile of salinity in 2023 returns full depth
    r_sal = client.post("/api/chat", json={"message": "depth profile of salinity in 2023"})
    assert r_sal.status_code == 200
    data_sal = r_sal.json()
    assert data_sal["observation_count"] > 1000
    assert data_sal["chart_type"] == "depth_profile"

    # 3. Plain temperature query without profile still defaults to upper 50 dbar
    r_plain = client.post("/api/chat", json={"message": "temperature in January 2023"})
    assert r_plain.status_code == 200
    data_plain = r_plain.json()
    assert "50" in data_plain["answer"] or "surface" in data_plain["answer"].lower() or "dbar" in data_plain["answer"]


def test_bug_02_salinity_cleanup():
    import sqlite3
    from ingestion.fetch_and_load import parse_profile_detail, cleanup_db
    from config import DB_PATH

    # 1. parse_profile_detail nulls out salinity below 20.0 PSU
    mock_detail = {
        "data_info": [["temperature", "pressure", "salinity"]],
        "data": [
            [1, 28.5, 1, 27.0],
            [10.0, 11.0, 20.0, 21.0],
            [1, 34.5, 1, 15.5],  # 15.5 < 20.0 must be nulled
        ],
    }
    rows = parse_profile_detail(mock_detail)
    assert rows[0] == (10.0, 28.5, 34.5)
    assert rows[1] == (20.0, 27.0, None)

    # 2. No measurement in floatchat.db has salinity below 20 PSU
    if os.path.exists(DB_PATH):
        with sqlite3.connect(DB_PATH) as conn:
            bad_count = conn.execute("SELECT COUNT(*) FROM measurements WHERE salinity IS NOT NULL AND salinity < 20.0").fetchone()[0]
            assert bad_count == 0

    # 3. API query "minimum salinity in 2023" returns plausible value (25.48 PSU)
    r = client.post("/api/chat", json={"message": "minimum salinity in 2023"})
    assert r.status_code == 200
    res = r.json()
    assert res["stat"] is not None
    val = res["stat"]["value"]
    assert val >= 20.0
    assert "25.48" in res["answer"] or pytest.approx(val, abs=0.1) == 25.48


def test_bug_03_packaging_excludes_disallowed_files(tmp_path):
    import zipfile
    sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))
    from package import package_distributable, should_include

    # 1. Verification of should_include rules
    assert not should_include(Path("floatchat.db"))
    assert not should_include(Path("backend/floatchat.db"))
    assert not should_include(Path("floatchat_auth.db"))
    assert not should_include(Path("backend/floatchat_auth.db"))
    assert not should_include(Path("non_existent.db"))
    assert not should_include(Path("any_other.db"))
    assert not should_include(Path("logs/floatchat.log"))
    assert not should_include(Path(".pytest_cache/v/cache/nodeids"))
    assert not should_include(Path("backend/__pycache__/main.cpython-312.pyc"))
    assert should_include(Path("backend/main.py"))
    assert should_include(Path("frontend/index.html"))

    # 2. Package into a temp zip and inspect all members
    test_zip = tmp_path / "test_dist.zip"
    created_path = package_distributable(str(test_zip))
    assert os.path.exists(created_path)

    with zipfile.ZipFile(created_path, "r") as zf:
        names = zf.namelist()
        for name in names:
            name_lower = name.lower()
            assert not name_lower.endswith(".db"), f"Unexpected db file in zip: {name}"
            assert "floatchat.db" not in name_lower, f"floatchat.db in zip: {name}"
            assert "non_existent.db" not in name_lower, f"non_existent.db in zip: {name}"
            assert ".pytest_cache" not in name_lower, f".pytest_cache in zip: {name}"
            assert "__pycache__" not in name_lower, f"__pycache__ in zip: {name}"
            assert not name_lower.startswith("logs/"), f"logs file in zip: {name}"


def test_bug_04_docs_updated():
    root = Path(__file__).resolve().parent.parent
    readme = (root / "README.md").read_text(encoding="utf-8")
    arch = (root / "ARCHITECTURE.md").read_text(encoding="utf-8")

    # 1. 37 floats with measurements
    assert "37 floats with measurements" in readme
    assert "37 floats with measurements" in arch

    # 2. Mentions database cleanup: 111 negative-pressure rows, 2 bad salinity rows
    assert "111 negative-pressure rows" in readme
    assert "2 bad salinity rows" in readme
    assert "111 negative-pressure rows" in arch
    assert "2 bad surface salinity" in arch or "2 bad salinity" in arch


def test_bug_05_login_throttle_ip_isolation():
    from main import _LOGIN_ATTEMPTS, _EMAIL_LOGIN_ATTEMPTS
    _LOGIN_ATTEMPTS.clear()
    _EMAIL_LOGIN_ATTEMPTS.clear()

    os.environ["TRUST_X_FORWARDED_FOR"] = "true"
    email = "victim_account@example.com"
    password = "Correct-Password-1234"

    # Register user
    r_reg = client.post("/api/register", json={"username": "victim_user", "email": email, "password": password})
    assert r_reg.status_code == 200

    attacker_headers = {"X-Forwarded-For": "198.51.100.55"}
    victim_headers = {"X-Forwarded-For": "203.0.113.88"}

    # Attacker IP fails 5 times with wrong password
    for _ in range(5):
        r_fail = client.post("/api/login", json={"email": email, "password": "wrong_password"}, headers=attacker_headers)
        assert r_fail.status_code == 401

    # Attacker IP is now throttled (429)
    r_throttled = client.post("/api/login", json={"email": email, "password": "wrong_password"}, headers=attacker_headers)
    assert r_throttled.status_code == 429
    assert "Too many failed login attempts" in r_throttled.json()["detail"]

    # Victim from a different IP can still successfully log in with the correct password!
    r_success = client.post("/api/login", json={"email": email, "password": password}, headers=victim_headers)
    assert r_success.status_code == 200
    assert "token" in r_success.json()

    _LOGIN_ATTEMPTS.clear()
    _EMAIL_LOGIN_ATTEMPTS.clear()


def test_bug_06_date_range_end_year_uses_whole_year():
    from retrieval.query_engine import _date_bounds

    # 1. When end has only a year (e.g. from January 2023 to 2024), bounds must cover the whole of 2024
    bounds_multi = _date_bounds(2023, 1, 2024, None)
    assert bounds_multi == ("2023-01-01", "2025-01-01")

    # 2. When end has an explicit month (e.g. January 2023 to March 2024), ends at March 2024
    bounds_explicit = _date_bounds(2023, 1, 2024, 3)
    assert bounds_explicit == ("2023-01-01", "2024-04-01")

    # 3. Single-month query (e.g. January 2023), ends at end of January 2023
    bounds_single = _date_bounds(2023, 1, 2023, None)
    assert bounds_single == ("2023-01-01", "2023-02-01")

    # 4. API request for "average temperature from January 2023 to 2024" includes data through end of 2024
    r = client.post("/api/chat", json={"message": "average temperature from January 2023 to 2024"})
    assert r.status_code == 200
    data = r.json()
    assert data["observation_count"] > 1000
    assert "between January 2023 and 2024" in data["answer"]


def test_bug_07_trend_after_single_month():
    from rule_intent import parse_intent

    # 1. parse_intent widens time range to full dataset and resets stat to none for trend follow-ups
    prev_history = [
        {
            "role": "assistant",
            "intent_summary": {
                "task": "stat",
                "question_kind": "data",
                "variable": "temperature",
                "stat": "max",
                "year": 2023,
                "month": 3,
                "pressure_min": None,
                "pressure_max": 50.0,
            },
        }
    ]
    intent = parse_intent("show me the trend", history=prev_history)
    assert intent["chart_type"] == "timeseries"
    assert intent["variable"] == "temperature"
    assert intent["stat"] == "none"
    assert intent["year"] is None
    assert intent["month"] is None

    # 2. API query "show me the trend" after single-month query returns timeseries across full dataset
    r = client.post(
        "/api/chat",
        json={
            "message": "show me the trend",
            "history": [
                {
                    "role": "user",
                    "message": "maximum temperature in March 2023",
                },
                {
                    "role": "assistant",
                    "message": "The maximum temperature was 30.123 across 15 observations.",
                    "intent": {
                        "variable": "temperature",
                        "stat": "max",
                        "year": 2023,
                        "month": 3,
                        "pressure_max": 50.0,
                    },
                },
            ],
        },
    )
    assert r.status_code == 200
    data = r.json()
    assert data["chart_type"] == "timeseries"
    assert data["chart_data"] is not None
    # Widen time range to full dataset means observations span beyond the single month of March 2023
    assert data["observation_count"] > 1000
    # Does not return a single maximum statistic
    assert data["stat"] is None
    assert "minimum" in data["answer"].lower() and "maximum" in data["answer"].lower()


def test_bug_08_default_variable_surface_depth_cap():
    # 1. Unspecified variable with month "what was the average in March 2024?" defaults to surface temp (<= 50 dbar)
    r = client.post("/api/chat", json={"message": "what was the average in March 2024?"})
    assert r.status_code == 200
    data = r.json()
    assert data["variable"] == "temperature"
    assert "surface" in data["answer"].lower() or "50" in data["answer"]
    # Surface temp in Bay of Bengal is ~28-29 °C; full water column average down to 2000 dbar would be ~12 °C
    assert "28." in data["answer"]


def test_bug_09_multi_period_comparison_has_target():
    from rule_intent import parse_intent

    # 1. Comparison of years without explicit variable word is NOT marked ambiguous
    intent_years = parse_intent("compare 2023 vs 2024")
    assert intent_years["compare"] is True
    assert intent_years["ambiguous"] is False
    assert len(intent_years["compare_periods"]) == 2

    # 2. Comparison of months without explicit variable word is NOT marked ambiguous
    intent_months = parse_intent("compare January and February")
    assert intent_months["compare"] is True
    assert intent_months["ambiguous"] is False
    assert intent_months["compare_months"] == [1, 2]

    # 3. API executes year comparison without refusal
    r = client.post("/api/chat", json={"message": "compare 2023 vs 2024"})
    assert r.status_code == 200
    data = r.json()
    assert data["chart_type"] == "compare"
    assert "2023" in data["answer"] and "2024" in data["answer"]
    assert "difference" in data["answer"].lower()


def test_bug_10_year_to_month_year_date_range():
    from rule_intent import parse_intent

    # 1. "average temperature from 2023 to March 2024" captures year=2023, year_end=2024, month_end=3
    intent = parse_intent("average temperature from 2023 to March 2024")
    assert intent["year"] == 2023
    assert intent["month"] is None
    assert intent["year_end"] == 2024
    assert intent["month_end"] == 3

    # 2. Query executes and formats date range in answer
    r = client.post("/api/chat", json={"message": "average temperature from 2023 to March 2024"})
    assert r.status_code == 200
    data = r.json()
    assert "between 2023 and March 2024" in data["answer"]
    assert data["observation_count"] > 1000


def test_bug_11_question_classifier_non_ocean_dates():
    from retrieval.question_classifier import classify_question_rules
    from rule_intent import parse_intent

    # 1. Questions with years but no ocean context or ocean action/data verbs are classified off_topic
    q1 = "Who won the cricket world cup in 2023?"
    intent1 = parse_intent(q1)
    kind1 = classify_question_rules(q1, intent1)
    assert kind1 == "off_topic"

    q2 = "Who was elected president in 2024?"
    intent2 = parse_intent(q2)
    kind2 = classify_question_rules(q2, intent2)
    assert kind2 == "off_topic"

    # 2. Chat endpoint refuses non-ocean question politely
    r = client.post("/api/chat", json={"message": q1})
    assert r.status_code == 200
    data = r.json()
    assert "ocean" in data["answer"].lower() or "bay of bengal" in data["answer"].lower() or "dataset" in data["answer"].lower()
    assert data["observation_count"] == 0


def test_bug_12_discovery_date_bounds_and_similar_profile_counts():
    from retrieval.discovery import list_floats

    # 1. list_floats with year and year_end includes data through the full year_end
    floats_single = list_floats({"year": 2023})
    floats_multi = list_floats({"year": 2023, "year_end": 2024})
    # Multi-year span has at least as many profiles / floats as single year
    assert len(floats_multi) >= len(floats_single)

    # 2. Similar profiles ChatResponse counts observation_count from similar_profiles list
    r = client.post("/api/chat", json={"message": "find similar profiles to 1902198_230"})
    assert r.status_code == 200
    data = r.json()
    assert data["task"] == "similar_profiles"
    assert data["observation_count"] == 5
    assert len(data.get("discovery_data", {}).get("similar_profiles", [])) == 5


def test_bug_13_export_store_safe_types():
    from export_store import csv_for_result

    # 1. None fields do not raise TypeError
    assert csv_for_result({"floats": None}) is None
    assert csv_for_result({"rows": None}) is None
    assert csv_for_result({"trajectory": None}) is None
    assert csv_for_result({"coverage": None}) is None
    assert csv_for_result({"float_summary": None}) is None
    assert csv_for_result({"similar_profiles": None}) is None

    # 2. Valid lists export cleanly
    csv_text, fname = csv_for_result({"floats": [{"platform": "1902198", "profile_count": 5, "first_date": "2023-01-01", "last_date": "2023-02-01", "avg_max_depth": 2000.0}]})
    assert fname == "floatchat_floats.csv"
    assert "1902198" in csv_text


def test_bug_14_package_exclude_archive_formats():
    from pathlib import Path
    import sys
    sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))
    import package

    assert not package.should_include(Path("dist/floatchat_dist.zip"))
    assert not package.should_include(Path("backup.tar.gz"))
    assert not package.should_include(Path("archive.tar"))
    assert package.should_include(Path("backend/main.py"))


def test_bug_15_default_chart_type_timeseries_for_unspecified_variable_year():
    from rule_intent import parse_intent

    # Query with full year and no explicit variable defaults to timeseries chart
    intent = parse_intent("average in 2024")
    assert intent["chart_type"] == "timeseries"

    r = client.post("/api/chat", json={"message": "average in 2024"})
    assert r.status_code == 200
    data = r.json()
    assert data["chart_type"] == "timeseries"
    assert data["chart_data"] is not None


