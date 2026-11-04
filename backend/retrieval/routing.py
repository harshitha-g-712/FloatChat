"""
Intent routing: decides whether a parsed intent may touch the dataset.

Standalone (NOT imported by main.py). Retrieval functions are injectable so
tests never need a database or network.

  data       -> dataset retrieval (stat via ``retrieve``, trajectory via
                ``trajectory_points``), with season/coverage and chart-hint
                metadata attached.
  knowledge  -> never retrieves from the dataset; flagged for the RAG handler.
  off_topic  -> polite refusal, no retrieval.
"""

from typing import Any, Callable, Dict, Optional

from retrieval.question_classifier import OFF_TOPIC_REFUSAL
from retrieval.validators import validate_platform_id, validated_chart_hint
from rule_intent import SAMPLE_CLARIFICATION


def _base(route: str, intent: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "route": route,
        "retrieval_performed": False,
        "answer": None,
        "task": intent.get("task"),
        "parser_used": intent.get("parser_used"),
        "season": intent.get("season"),
        "partial_coverage": bool((intent.get("season") or {}).get("partial_coverage")),
        "coverage_note": (intent.get("season") or {}).get("coverage_note"),
    }


def chart_metadata(intent: Dict[str, Any]) -> Dict[str, Any]:
    """Validated chart hint metadata (LLM/rules chart_type, allowlist-checked)."""
    hint = validated_chart_hint(intent.get("chart_type"))
    task = intent.get("task")
    default = "trajectory" if task == "trajectory" else None
    return {"chart_hint": hint, "chart_type": hint or default}


def route_intent(
    intent: Dict[str, Any],
    question: str = "",
    *,
    retrieve_fn: Optional[Callable[..., Dict[str, Any]]] = None,
    trajectory_fn: Optional[Callable[..., Any]] = None,
    db_path: Optional[str] = None,
) -> Dict[str, Any]:
    """Route a parsed intent and return result + answer metadata."""
    kind = intent.get("question_kind") or ("knowledge" if intent.get("is_conceptual") else "data")

    if kind == "off_topic":
        res = _base("off_topic", intent)
        res["answer"] = OFF_TOPIC_REFUSAL + SAMPLE_CLARIFICATION
        return res

    if kind == "knowledge" or intent.get("is_conceptual") or intent.get("task") == "concept":
        res = _base("knowledge", intent)
        res["handler"] = "rag"  # caller answers via the RAG helper; no dataset access
        return res

    res = _base("data", intent)
    res.update(chart_metadata(intent))

    if intent.get("ambiguous"):
        res["answer"] = intent.get("clarification_needed") or SAMPLE_CLARIFICATION
        return res

    if intent.get("no_data_in_dataset"):
        res["answer"] = res["coverage_note"]  # explicit: nothing to retrieve
        return res

    task = intent.get("task") or "stat"
    platform = validate_platform_id(intent.get("platform_id"))
    res["platform_filter"] = platform  # None => no float filter applied

    if task == "trajectory":
        if trajectory_fn is None:
            from retrieval.discovery import trajectory_points as trajectory_fn
        res["data"] = trajectory_fn(
            platform, db_path=db_path,
            year=intent.get("year"), month=intent.get("month"),
            year_end=intent.get("year_end"), month_end=intent.get("month_end"))
        res["retrieval_performed"] = True
    elif task == "stat":
        if retrieve_fn is None:
            from retrieval.query_engine import retrieve as retrieve_fn
        clean = dict(intent)
        clean["platform_id"] = platform
        res["data"] = retrieve_fn(clean, db_path) if db_path else retrieve_fn(clean)
        res["retrieval_performed"] = True
    else:
        res["handler"] = "discovery"  # other discovery tasks stay with main.py's handlers

    if res["coverage_note"] and res["retrieval_performed"]:
        res["answer_prefix"] = res["coverage_note"]
    return res
