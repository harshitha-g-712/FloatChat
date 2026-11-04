"""
Rules-based question classification: data | knowledge | off_topic.

Used by nl_parser when the LLM path is unavailable or rejected. It refines
``rule_intent.parse_intent`` (which cannot tell "off topic" from "unclear" and
treats region mentions as data) without modifying rule_intent itself.
"""

import re
from typing import Any, Dict

from rule_intent import MONTH_REGEX, SAMPLE_CLARIFICATION

OFF_TOPIC_REFUSAL = (
    "Sorry, I can only help with ARGO ocean float data and related ocean science "
    "for the Bay of Bengal, so I can't answer that one. "
)

_DOMAIN = re.compile(
    r"\b(ocean\w*|sea|bay|bengal|argo|floats?|platforms?|profiles?|\d{7}(?:_\d{1,4})?|temperature|salinity|"
    r"saline|salt\w*|fresh\w*|warm\w*|cold\w*|pressure|dbar|depth|monsoons?|thermocline|halocline|pycnocline|"
    r"mixed layer|upwelling|stratification|current|surface|water|marine|andaman|sri lanka|"
    r"trajector\w+|season\w*|river|discharge|cyclone|heat|coverage|dataset|database)\b", re.IGNORECASE)

_DATA_SIGNAL = re.compile(
    r"(\b\d{7}\b|\b(?:19|20)\d\d\b|\b" + MONTH_REGEX + r"\b|"
    r"\b(?:average|avg|mean|maximum|minimum|max|min|highest|lowest|warmest|coldest|saltiest|"
    r"count|how many|number of|show|list|plot|chart|graph|compare|export|download|csv|find|"
    r"retrieve|display|visuali[sz]e|trajectory|track|where did|where is|where are|location of|coverage|data)\b)",
    re.IGNORECASE)

_STAT_OR_ACTION = re.compile(
    r"\b(average|avg|mean|maximum|minimum|max|min|highest|lowest|warmest|coldest|saltiest|freshest|"
    r"count|how many|number of|show|list|plot|chart|graph|compare|export|download|csv|find|"
    r"retrieve|display|visuali[sz]e|trajectory|track|profile|profiles|trend\w*|timeseries|progression)\b", re.IGNORECASE)

_KNOWLEDGE_LEAD = re.compile(
    r"^\s*(why|how (?:do|does|did|is|are|can|come)|what (?:is|are|causes?|does|'s)|what's|"
    r"who\b|when\b|explain|define|describe|tell me about|tell me who|tell me when)\b", re.IGNORECASE)


def classify_question_rules(question: str, rules_intent: Dict[str, Any]) -> str:
    """Return "data", "knowledge" or "off_topic" for the rules fallback."""
    q = (question or "").strip()
    if not q:
        return "data"  # empty stays ambiguous data, as before
    has_domain = bool(_DOMAIN.search(q))
    has_data = bool(_DATA_SIGNAL.search(q))
    has_stat_action = bool(_STAT_OR_ACTION.search(q))

    if not has_domain and not has_data:
        return "off_topic"
    if not has_domain and has_data:
        # If question has no ocean domain and lacks statistical/data action words, or starts with knowledge lead, it is off-topic
        if not has_stat_action or _KNOWLEDGE_LEAD.search(q):
            return "off_topic"
        return "data"
    if has_data:
        return "data"
    if _KNOWLEDGE_LEAD.search(q) or rules_intent.get("is_conceptual") \
            or rules_intent.get("task") == "concept":
        return "knowledge"
    return "data"


def apply_kind_to_intent(intent: Dict[str, Any], kind: str) -> Dict[str, Any]:
    """Return a copy of ``intent`` made consistent with ``kind``.

    knowledge -> task "concept", data filters cleared (never reaches retrieval).
    off_topic -> everything cleared, ambiguous with a polite refusal.
    data      -> unchanged.
    """
    out = dict(intent)
    out["question_kind"] = kind
    if kind == "data":
        return out
    out.update({
        "task": "concept" if kind == "knowledge" else "stat",
        "variable": None, "stat": "none", "year": None, "month": None,
        "year_end": None, "month_end": None, "compare": False, "compare_months": None, "compare_periods": None,
        "region_lat": None, "region_lon": None, "region_radius_deg": None,
        "named_region": None, "platform_id": None, "profile_id": None,
        "chart_type": "none", "pressure_min": None, "pressure_max": None,
        "export_csv": False,
        "is_conceptual": kind == "knowledge",
        "ambiguous": kind == "off_topic",
        "clarification_needed": (OFF_TOPIC_REFUSAL + SAMPLE_CLARIFICATION) if kind == "off_topic" else None,
    })
    return out
