"""Round 5: fixes found by asking new questions through /api/chat and checking them against SQL."""
import os
import sqlite3
import sys
import uuid

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))

import pytest
from fastapi.testclient import TestClient

import main
from config import DB_PATH
from typo_tolerance import correct_typos
from retrieval.nl_parser import parse_question

client = TestClient(main.app)


def ask(q, headers=None, cid=None):
    cid = cid or "r5-" + uuid.uuid4().hex[:12]
    r = client.post("/api/chat", json={"message": q, "conversation_id": cid}, headers=headers or {})
    assert r.status_code == 200, r.text
    return r.json()


def sql(query, *params):
    conn = sqlite3.connect(DB_PATH)
    try:
        return conn.execute(query, params).fetchall()
    finally:
        conn.close()


def _signup():
    tag = uuid.uuid4().hex[:10]
    r = client.post("/api/register", json={"username": f"r5_{tag}", "email": f"r5_{tag}@example.com", "password": "Str0ng-Pass-" + tag})
    assert r.status_code == 200, r.text
    login = client.post("/api/login", json={"email": f"r5_{tag}@example.com", "password": "Str0ng-Pass-" + tag})
    assert login.status_code == 200, login.text
    return {"Authorization": f"Bearer {login.json()['token']}"}


# ── Typos: short months before a year ────────────────────────────────────────

@pytest.mark.parametrize("bad,good", [
    ("Maximun salinty in Aprl 2023", "Maximum salinity in April 2023"),
    ("Average temperature in Mrch 2023", "Average temperature in March 2023"),
    ("salinity in Augst 2023", "salinity in August 2023"),
])
def test_short_month_typos_are_fixed_before_a_year(bad, good):
    assert correct_typos(bad)[0] == good


@pytest.mark.parametrize("ok", ["data 2023", "year 2023", "since 2023", "mean 2023", "avg 2023", "Mars 2023",
                                "in June 2023", "May 2023", "Sept 2023", "late 2023", "from 2022 to 2024"])
def test_short_word_before_year_is_not_changed_when_it_is_not_a_month_typo(ok):
    assert correct_typos(ok) == (ok, [])


def test_aprl_no_longer_drops_the_month_and_matches_sql():
    j = ask("Maximun salinty in Aprl 2023")
    want = sql("SELECT MAX(m.salinity), COUNT(m.salinity) FROM measurements m JOIN profiles p ON p.id=m.profile_id "
               "WHERE p.timestamp LIKE '2023-04%' AND m.salinity IS NOT NULL")[0]
    assert j["stat"]["value"] == pytest.approx(want[0], abs=1e-3)
    assert j["observation_count"] == want[1]
    assert "April 2023" in j["answer"]


# ── "Interpreted as" line ────────────────────────────────────────────────────

def test_interpreted_line_shown_when_corrected_and_absent_otherwise():
    j = ask("avarage temprature in March 2023")
    assert 'Interpreted as: "average temperature in March 2023"' in j["answer"]
    assert j["interpreted_as"] == "average temperature in March 2023"
    assert j["answer"].count("Interpreted as") == 1
    clean = ask("average temperature in March 2023")
    assert "Interpreted as" not in clean["answer"] and clean["interpreted_as"] is None


def test_interpreted_line_on_refusals_and_discovery_too():
    assert "Interpreted as" in ask("avarage temprature in the arabian sea in March 2023")["answer"]
    assert "Interpreted as" in ask("show the trajectry of float 2902837")["answer"]


def test_history_keeps_original_text_and_reopened_answer_has_the_line():
    headers = _signup()
    cid = str(uuid.uuid4())
    original = "avarage temprature in March 2023"
    ask(original, headers=headers, cid=cid)
    msgs = client.get(f"/api/conversations/{cid}/messages", headers=headers).json()["messages"]
    assert msgs[0]["role"] == "user" and msgs[0]["content"] == original
    assert "Interpreted as" in msgs[1]["content"]


def test_interpreted_state_does_not_leak_into_the_next_request():
    ask("avarage temprature in March 2023")
    assert "Interpreted as" not in ask("What is the thermocline?")["answer"]


# ── Parser fixes ─────────────────────────────────────────────────────────────

@pytest.mark.parametrize("q", [
    "Show temperature depth profiles for March 2023",
    "show depth profile for March 2023",
    "temperature profile in March 2023",
])
def test_depth_profile_questions_keep_their_date_and_get_a_depth_chart(q):
    i = parse_question(q)
    assert (i["year"], i["month"]) == (2023, 3)
    assert i["chart_type"] == "depth_profile" and not i.get("ambiguous")
    j = ask(q)
    assert j["chart_data"], "depth profile chart missing"
    assert j["chart_type"] == "depth_profile"


def test_malformed_float_id_is_still_rejected():
    assert parse_question("float xyz123 profile")["ambiguous"] is True


def test_data_coverage_question_is_answered():
    for q in ("What is the data coverage?", "What dataset do you have?"):
        j = ask(q)
        assert j["task"] == "coverage" and "Observation Window" in j["answer"], q


def test_trajectory_without_float_asks_for_an_id_with_real_examples():
    j = ask("Show the trajectory of the first float")
    assert "float None" not in j["answer"] and "Which float?" in j["answer"]
    real = {r[0] for r in sql("SELECT DISTINCT platform FROM profiles")}
    mentioned = [w.strip(",)") for w in j["answer"].split() if w.strip(",)").isdigit() and len(w.strip(",)")) == 7]
    assert mentioned and set(mentioned) <= real
    assert j["ambiguous"] is True


def test_depth_wording_matches_the_inclusive_sql_bound():
    j = ask("What was the average salinity in February 2023?")
    assert "up to 50 dbar" in j["answer"] and "shallower" not in j["answer"]
    want = sql("SELECT AVG(m.salinity), COUNT(m.salinity) FROM measurements m JOIN profiles p ON p.id=m.profile_id "
               "WHERE p.timestamp LIKE '2023-02%' AND m.pressure<=50 AND m.salinity IS NOT NULL")[0]
    assert j["stat"]["value"] == pytest.approx(want[0], abs=1e-3) and j["observation_count"] == want[1]


# ── Anonymous export ─────────────────────────────────────────────────────────

def test_anonymous_export_explains_why_and_suggests_signing_in():
    cid = "anon-" + uuid.uuid4().hex[:10]
    ask("Average temperature in March 2023", cid=cid)
    assert client.post("/api/export", json={"conversation_id": cid}).status_code == 200
    main._last_results.clear()  # cache expired / evicted but the guest chat is still in memory
    r = client.post("/api/export", json={"conversation_id": cid})
    assert r.status_code == 409 and "Sign in" in r.json()["detail"]
    main._anon_memory.pop(cid, None)   # server restart
    r = client.post("/api/export", json={"conversation_id": cid})
    assert r.status_code == 404 and "Sign in" in r.json()["detail"]
