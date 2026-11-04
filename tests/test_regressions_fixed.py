"""Regression tests for parser and query bugs found during app-level audit."""
import sqlite3
import os
import sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))

from rule_intent import parse_intent
from retrieval.query_engine import retrieve


def test_compare_with_variable_and_no_stat_defaults_to_average():
    intent = parse_intent("Compare temperature in January and June 2023")
    assert intent["compare"] is True
    assert intent["compare_months"] == [1, 6]
    assert intent["year"] == 2023
    assert intent["stat"] == "avg"


def test_year_range_is_not_pressure_range():
    intent = parse_intent("Between 2022 and 2024")
    assert intent["year"] == 2022
    assert intent["year_end"] == 2024
    assert intent["pressure_min"] is None
    assert intent["pressure_max"] is None


def test_pressure_language_has_oceanographic_direction():
    below = parse_intent("Below 500 dbar")
    above = parse_intent("Above 500 dbar")
    assert below["pressure_min"] == 500
    assert below["pressure_max"] is None
    assert above["pressure_min"] is None
    assert above["pressure_max"] == 500


def test_exact_pressure_level_is_not_year_and_is_applied():
    intent = parse_intent("At 2000 dbar")
    assert intent["year"] is None
    assert intent["pressure_min"] == 2000
    assert intent["pressure_max"] == 2000


def test_wrapped_month_range_crosses_year_boundary():
    intent = parse_intent("November to February 2023")
    assert (intent["year"], intent["year_end"]) == (2022, 2023)
    assert (intent["month"], intent["month_end"]) == (11, 2)


def test_may_be_is_not_month_may():
    intent = parse_intent("What may be the cause?")
    assert intent["month"] is None


def test_month_without_year_filters_to_calendar_month():
    result = retrieve({"variable": "temperature", "stat": "avg", "month": 3})
    assert result["rows"]
    assert all(row["timestamp"] and row["timestamp"][5:7] == "03" for row in result["rows"])
    assert result["count"] == sum(row["temperature"] is not None for row in result["rows"])


def test_shipped_database_has_no_private_auth_or_chat_tables():
    from config import DB_PATH
    conn = sqlite3.connect(DB_PATH)
    try:
        tables = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        assert not ({"users", "auth_tokens", "conversations", "chat_messages"} & tables)
    finally:
        conn.close()


def test_followup_skips_knowledge_turn_when_finding_data_context():
    history = [
        {"role": "assistant", "intent_summary": {"task": "stat", "question_kind": "data", "variable": "temperature", "stat": "avg", "year": 2023, "month": 1}},
        {"role": "assistant", "intent_summary": {"task": "concept", "question_kind": "knowledge", "variable": None}},
    ]
    intent = parse_intent("what about salinity?", history=history)
    assert intent["variable"] == "salinity"
    assert intent["year"] == 2023
    assert intent["month"] == 1


def test_exact_pressure_filter_reaches_query_engine():
    intent = parse_intent("Average temperature at 2000 dbar in January 2023")
    assert intent["year"] == 2023
    assert intent["month"] == 1
    assert intent["pressure_min"] == 2000
    assert intent["pressure_max"] == 2000
    result = retrieve(intent)
    assert all(row["pressure"] == 2000 for row in result["rows"])


def test_conceptual_answers_return_a_relevant_section_not_entire_document():
    from rag.indexer import answer_conceptual_query
    result = answer_conceptual_query("Why is the Bay of Bengal fresher at the surface?")
    assert result is not None
    answer = result["answer"].lower()
    assert "fresh" in answer or "salinity" in answer or "river" in answer
    assert len(result["answer"]) < 3000
