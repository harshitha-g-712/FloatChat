"""Tests for the technologies_used badge metadata in API responses.

Verifies that every chat response includes the `technologies_used` list,
and that the health endpoint exposes the active technology stack.
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))
from fastapi.testclient import TestClient
from main import app

client = TestClient(app)

def ask(q, **kwargs):
    return client.post(
        "/api/chat",
        json={"message": q, "conversation_id": "tech-badge-test-" + str(abs(hash(q))), **kwargs},
    )


# ── Health endpoint ──────────────────────────────────────────────────────────

def test_health_returns_technologies():
    """The /api/health response must include the technologies dict."""
    r = client.get("/api/health")
    assert r.status_code == 200
    data = r.json()
    assert "technologies" in data
    techs = data["technologies"]
    assert "nlp" in techs
    assert "genai_llm" in techs
    assert "rag" in techs
    assert "data_visualization" in techs


def test_health_returns_rag_mode():
    """The /api/health response must include rag_mode."""
    r = client.get("/api/health")
    assert r.status_code == 200
    data = r.json()
    assert "rag_mode" in data
    assert data["rag_mode"] in {"tfidf", "embedding"}


# ── Chat response: technologies_used field ───────────────────────────────────

def test_stat_query_has_technologies_used():
    """A data/stat query must return technologies_used with at least NLP."""
    r = ask("What is the average temperature in January 2023?")
    assert r.status_code == 200
    data = r.json()
    assert "technologies_used" in data
    techs = data["technologies_used"]
    assert isinstance(techs, list)
    assert "NLP" in techs


def test_stat_query_with_chart_includes_data_viz():
    """When chart_data is present, 'Data Visualization' must appear in technologies_used."""
    r = ask("Show temperature vs depth for January 2023")
    assert r.status_code == 200
    data = r.json()
    techs = data.get("technologies_used", [])
    if data.get("chart_data"):
        assert "Data Visualization" in techs


def test_knowledge_query_has_technologies_used():
    """A knowledge/concept query must include NLP and RAG in technologies_used."""
    r = ask("What is a thermocline?")
    assert r.status_code == 200
    data = r.json()
    assert "technologies_used" in data
    techs = data["technologies_used"]
    assert "NLP" in techs
    assert "RAG" in techs


def test_technologies_used_contains_only_known_values():
    """All entries in technologies_used must be from the known set."""
    known = {"NLP", "GenAI/LLM", "RAG", "Data Visualization"}
    r = ask("Average salinity in March 2023")
    assert r.status_code == 200
    techs = r.json().get("technologies_used", [])
    for t in techs:
        assert t in known, f"Unexpected technology badge: {t!r}"


def test_discovery_query_has_technologies_used():
    """A discovery query (e.g. listing floats) must return technologies_used."""
    r = ask("List floats in 2023")
    assert r.status_code == 200
    data = r.json()
    assert "technologies_used" in data
    assert isinstance(data["technologies_used"], list)
    assert len(data["technologies_used"]) >= 1


def test_gemini_badge_when_answer_mode_gemini():
    """If answer_mode is 'gemini', 'GenAI/LLM' must be in technologies_used."""
    r = ask("What is an ARGO float?")
    assert r.status_code == 200
    data = r.json()
    if data.get("answer_mode") == "gemini":
        assert "GenAI/LLM" in data.get("technologies_used", [])


def test_rag_mode_field_on_knowledge_response():
    """Knowledge answers should carry a rag_mode field."""
    r = ask("How do monsoons affect the Bay of Bengal?")
    assert r.status_code == 200
    data = r.json()
    # rag_mode may be present on knowledge answers
    if data.get("question_kind") == "knowledge" or data.get("task") == "concept":
        assert "rag_mode" in data or "RAG" in data.get("technologies_used", [])

