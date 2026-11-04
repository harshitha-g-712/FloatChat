"""
Small shared validators for retrieval / parsing code.

Kept dependency-free (only ``config``) so query_engine, discovery and
nl_parser can all use the same rules.
"""

import re
from typing import Any, Optional

from config import ALLOWED_CHART_TYPES

# Argo WMO platform IDs are 7 digits (see rule_intent._extract_platform_id).
PLATFORM_ID_RE = re.compile(r"^\d{7}$")


def validate_platform_id(value: Any) -> Optional[str]:
    """Return ``value`` if it is a well-formed 7-digit float ID string, else None.

    Strict on purpose: ints, floats, padded or non-digit strings are rejected so
    that no float filter is applied for anything that is not a real float ID.
    """
    if isinstance(value, str) and PLATFORM_ID_RE.match(value):
        return value
    return None


def validated_chart_hint(value: Any) -> Optional[str]:
    """Return ``value`` if it is an allowlisted, meaningful chart type, else None.

    ``"none"`` means "no hint" and maps to None.
    """
    if isinstance(value, str) and value != "none" and value in ALLOWED_CHART_TYPES:
        return value
    return None
