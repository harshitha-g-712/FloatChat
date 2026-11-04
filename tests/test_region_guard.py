"""Task 4: knowledge questions naming a region outside the knowledge base say so first."""
import os, sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))
from region_guard import knowledge_region_notice, unsupported_regions
from rag.indexer import answer_conceptual_query


def test_notice_names_the_region_and_comes_first():
    n = knowledge_region_notice("Why is the Arabian Sea saltier than the Bay of Bengal?")
    assert n.startswith("Note:") and "Arabian Sea" in n and n.endswith("\n\n")
    assert "cover only the Bay of Bengal" in n


def test_multiple_regions_and_dedup():
    assert unsupported_regions("Pacific vs Atlantic and the pacific again") == ["Pacific", "Atlantic"]
    assert "Pacific or Atlantic" in knowledge_region_notice("pacific vs atlantic thermocline")


def test_no_notice_for_covered_or_generic_questions():
    for q in ["What is the thermocline?", "How do monsoons affect the Bay of Bengal?", "Andaman Sea salinity", ""]:
        assert knowledge_region_notice(q) == ""


def test_knowledge_answer_still_available_after_notice():
    q = "Why is the Arabian Sea saltier than the Bay of Bengal?"
    r = answer_conceptual_query(q)
    assert r and "Bay of Bengal" in r["answer"]
    assert not r["answer"].startswith("Note:")      # the notice is added by the endpoint, never faked as KB content
