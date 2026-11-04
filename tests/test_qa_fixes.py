"""Regression tests for question/answer correctness (round 3 audit)."""
import os
import sqlite3
import sys
import uuid

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))

import pytest

pytest.importorskip("fastapi")
from fastapi.testclient import TestClient  # noqa: E402

import main  # noqa: E402
from config import DB_PATH  # noqa: E402
from rag.indexer import answer_conceptual_query  # noqa: E402

client = TestClient(main.app)


def ask(q):
    r = client.post("/api/chat", json={"message": q, "conversation_id": str(uuid.uuid4())})
    assert r.status_code == 200, r.text
    return r.json()


def sql(query, *args):
    conn = sqlite3.connect(DB_PATH)
    try:
        return conn.execute(query, args).fetchone()
    finally:
        conn.close()


# ── RAG: heading-only title block must never be the answer ───────────────────

@pytest.mark.parametrize("q,must_have", [
    ("What is the thermocline?", "temperature decreases rapidly"),
    ("what is halocline", "salinity changes rapidly"),
    ("explain pycnocline", "vertical density gradient"),
])
def test_layer_concepts_return_real_text_not_just_the_title(q, must_have):
    res = answer_conceptual_query(q)
    assert res and must_have in res["answer"]
    assert len(res["answer"].strip()) > 80


def test_thermocline_via_api_has_body():
    a = ask("What is the thermocline?")["answer"]
    assert "temperature decreases rapidly" in a


# ── Regions the dataset does not cover are refused, not silently substituted ─

@pytest.mark.parametrize("q", ["temperature in Arabian Sea", "average salinity in the Pacific in March 2023", "show floats in the Mediterranean"])
def test_unsupported_region_is_refused(q):
    d = ask(q)
    assert d["observation_count"] == 0 and d["ambiguous"] is True
    assert "only covers the Bay of Bengal" in d["answer"]
    assert d["stat"] is None


def test_knowledge_question_mentioning_other_sea_says_it_is_not_covered_first():
    d = ask("Why is the Arabian Sea saltier than the Bay of Bengal?")
    assert d["task"] == "concept"
    assert d["answer"].startswith("Note: this knowledge base and the bundled dataset cover only the Bay of Bengal")
    assert "Arabian Sea" in d["answer"].split("\n")[0]
    assert "Bay of Bengal" in d["answer"].split("\n\n", 1)[1]      # then what is available


def test_knowledge_question_about_covered_region_has_no_notice():
    d = ask("How do monsoons affect the Bay of Bengal?")
    assert not d["answer"].startswith("Note:")


# ── Bare seasons are ambiguous, never silently dropped ───────────────────────

def test_winter_asks_for_clarification():
    d = ask("average temperature in winter 2023")
    assert d["ambiguous"] is True and d["observation_count"] == 0
    assert "months" in d["answer"].lower()


def test_named_monsoon_seasons_still_work_and_concept_winter_is_allowed():
    d = ask("average temperature in pre-monsoon 2023")
    assert d["observation_count"] > 0
    assert ask("Why is the sea surface cooler in winter?")["task"] == "concept"


# ── Single pressure level uses a disclosed band ──────────────────────────────

def test_single_pressure_level_uses_band_and_matches_sql():
    d = ask("average temperature at 2000 dbar")
    assert d["applied_filters"]["pressure_min"] == 1990.0 and d["applied_filters"]["pressure_max"] == 2010.0
    assert "1990–2010 dbar" in d["answer"]
    n, avg = sql("SELECT COUNT(temperature), AVG(temperature) FROM measurements WHERE pressure BETWEEN 1990 AND 2010")
    assert d["observation_count"] == n > 0
    assert d["stat"]["value"] == pytest.approx(avg, abs=1e-3)


# ── Same default depth for temperature and salinity averages, always disclosed ─

def test_avg_salinity_defaults_to_upper_50_dbar_like_temperature():
    d = ask("average salinity in April 2023")
    assert d["applied_filters"]["pressure_max"] == 50.0
    assert "up to 50 dbar" in d["answer"]
    n, avg = sql("SELECT COUNT(m.salinity), AVG(m.salinity) FROM measurements m JOIN profiles p ON p.id=m.profile_id "
                 "WHERE substr(p.timestamp,1,7)='2023-04' AND m.pressure<=50")
    assert d["observation_count"] == n
    assert d["stat"]["value"] == pytest.approx(avg, abs=1e-3)


def test_all_depths_phrase_is_explicit_when_no_depth_filter():
    d = ask("Maximum temperature in January 2023")
    assert "at all depths" in d["answer"]
    (mx,) = sql("SELECT MAX(m.temperature) FROM measurements m JOIN profiles p ON p.id=m.profile_id WHERE substr(p.timestamp,1,7)='2023-01'")
    assert d["stat"]["value"] == pytest.approx(mx, abs=1e-3)


def test_explicit_all_depths_overrides_surface_default():
    d = ask("average temperature in March 2023 at all depths")
    assert d["applied_filters"].get("pressure_max") is None


def test_compare_answer_discloses_depth_band():
    assert "up to 50 dbar" in ask("compare temperature in January vs June 2023")["answer"]


# ── Numbers match the database ───────────────────────────────────────────────

def test_march_average_temperature_matches_sql():
    d = ask("Average temperature in March 2023")
    n, avg = sql("SELECT COUNT(m.temperature), AVG(m.temperature) FROM measurements m JOIN profiles p ON p.id=m.profile_id "
                 "WHERE substr(p.timestamp,1,7)='2023-03' AND m.pressure<=50")
    assert d["observation_count"] == n
    assert d["stat"]["value"] == pytest.approx(avg, abs=1e-3)


def test_profile_and_float_counts_match_sql():
    (n,) = sql("SELECT COUNT(DISTINCT profile_id) FROM measurements")
    (f,) = sql("SELECT COUNT(DISTINCT p.platform) FROM profiles p WHERE p.id IN (SELECT profile_id FROM measurements)")
    assert ask("How many floats are there?")["observation_count"] == f
    cov = ask("coverage of the dataset")["answer"]
    assert f"Profiles with measurements: {n:,}" in cov
    (records,) = sql("SELECT COUNT(*) FROM profiles")
    if records > n:
        assert f"{records:,} profile records" in cov


# ── Greetings ────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("q", ["hello", "Hi there!", "good morning"])
def test_greeting_gets_friendly_reply_not_refusal(q):
    a = ask(q)["answer"]
    assert a.startswith("Hello!") and "Sorry" not in a


def test_offtopic_is_still_refused():
    assert "Sorry" in ask("what is the capital of France")["answer"]


# ── Sub-region is applied AND reported ───────────────────────────────────────

def test_named_subregion_is_reported_and_matches_sql():
    d = ask("average temperature in north Bay of Bengal in February 2023")
    assert "in the North Bay of Bengal" in d["answer"] or "in the north Bay of Bengal" in d["answer"].lower()
    n, avg = sql("SELECT COUNT(m.temperature), AVG(m.temperature) FROM measurements m JOIN profiles p ON p.id=m.profile_id "
                 "WHERE substr(p.timestamp,1,7)='2023-02' AND m.pressure<=50 AND p.lat>=15")
    assert d["observation_count"] == n
    assert d["stat"]["value"] == pytest.approx(avg, abs=1e-3)


def test_empty_subregion_names_the_subregion_not_the_whole_bay():
    d = ask("average temperature in Andaman Sea")
    assert d["observation_count"] == 0
    assert "Andaman" in d["answer"]


# ── Float summary names the float; unknown IDs are explained ─────────────────

def test_float_profile_answer_names_the_float():
    assert "float 2902758" in ask("Show temperature profile for float 2902758")["answer"]


def test_unknown_float_gets_clear_message():
    d = ask("float 9999999 summary")
    assert "Float 9999999 is not in this dataset" in d["answer"]
    assert d["observation_count"] == 0


def test_unknown_profile_id_points_to_real_ones():
    d = ask("similar profiles to 2902758_002")
    assert "Profile 2902758_002 is not in this dataset" in d["answer"]
    assert "2902758_137" in d["answer"]


def test_existing_float_still_works():
    assert ask("Where did float 2902758 travel?")["observation_count"] == 14


# ── "warmest month" is answered with a month ─────────────────────────────────

def test_warmest_and_saltiest_month_are_real_rankings():
    rows = {}
    conn = sqlite3.connect(DB_PATH)
    for ym, t, s in conn.execute("SELECT substr(p.timestamp,1,7), AVG(m.temperature), AVG(m.salinity) FROM measurements m "
                                 "JOIN profiles p ON p.id=m.profile_id WHERE m.pressure<=50 GROUP BY 1"):
        rows[ym] = (t, s)
    conn.close()
    import datetime
    name = lambda ym: datetime.datetime.strptime(ym, "%Y-%m").strftime("%B %Y")
    warm = max(rows, key=lambda k: rows[k][0])
    salty = max(rows, key=lambda k: rows[k][1])
    assert f"warmest month in the dataset was {name(warm)}" in ask("warmest month")["answer"]
    assert f"saltiest month in the dataset was {name(salty)}" in ask("which is the saltiest month?")["answer"]
