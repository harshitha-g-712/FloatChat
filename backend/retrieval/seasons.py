"""
Season recognition and dataset-coverage metadata.

Seasons (calendar months):
  south-west monsoon  June–September
  north-east monsoon  October–January
  pre-monsoon         March–May

A season "occurrence" is anchored to the calendar year in which it STARTS
(so the 2023 north-east monsoon is Oct 2023 – Jan 2024). Coverage is computed
against ``config.DATASET_START`` / ``DATASET_END`` (read from the profiles table, so it
follows whatever years are loaded); nothing is assumed about months outside
that window. With no year in the question the first dataset year is used and the
answer says so, naming the other years that can be asked for.
"""

import re
from typing import Any, Dict, List, Optional, Tuple

from config import DATASET_END, DATASET_START, SEASON_MONTHS

SEASON_LABELS = {
    "south_west_monsoon": "south-west monsoon",
    "north_east_monsoon": "north-east monsoon",
    "pre_monsoon": "pre-monsoon",
}

_SEASON_PATTERNS = {
    "south_west_monsoon": re.compile(
        r"\b(?:south[\s-]?west|sw|summer)\s+monsoon\b|"
        r"\bsouth[\s-]?west\b(?=.*\bmonsoon)", re.IGNORECASE),
    "north_east_monsoon": re.compile(
        r"\b(?:north[\s-]?east|ne|winter)\s+monsoon\b|"
        r"\bnorth[\s-]?east\b(?=.*\bmonsoon)", re.IGNORECASE),
    "pre_monsoon": re.compile(r"\bpre[\s-]?monsoon\b", re.IGNORECASE),
}

_MONTH_NAMES = ["January", "February", "March", "April", "May", "June", "July",
                "August", "September", "October", "November", "December"]


def detect_seasons(question: str) -> List[str]:
    """Season keys mentioned in the question, in order of appearance."""
    found: List[Tuple[int, str]] = []
    for key, pat in _SEASON_PATTERNS.items():
        m = pat.search(question or "")
        if m:
            found.append((m.start(), key))
    return [k for _, k in sorted(found)]


def _ym_index(year: int, month: int) -> int:
    return year * 12 + (month - 1)


def _fmt(year: int, month: int) -> str:
    return f"{_MONTH_NAMES[month - 1]} {year}"


def dataset_window_label() -> str:
    return f"{_fmt(*DATASET_START)} to {_fmt(*DATASET_END)}"


def season_occurrence(key: str, start_year: int) -> List[Tuple[int, int]]:
    """(year, month) pairs of the season that starts in ``start_year``."""
    out: List[Tuple[int, int]] = []
    year = start_year
    prev = None
    for m in SEASON_MONTHS[key]:
        if prev is not None and m < prev:  # wrapped past December
            year += 1
        out.append((year, m))
        prev = m
    return out


def season_coverage(key: str, year: Optional[int] = None) -> Dict[str, Any]:
    """Coverage metadata of one season against the dataset window.

    ``year`` is the season's start year. When None, the dataset year is
    assumed and ``year_assumed`` is True.
    """
    if key not in SEASON_MONTHS:
        raise ValueError(f"unknown season: {key}")
    year_assumed = year is None
    season_year = DATASET_START[0] if year is None else year
    occ = season_occurrence(key, season_year)
    lo, hi = _ym_index(*DATASET_START), _ym_index(*DATASET_END)
    covered = [ym for ym in occ if lo <= _ym_index(*ym) <= hi]
    missing = [ym for ym in occ if ym not in covered]

    if not covered:
        level = "none"
    elif missing:
        level = "partial"
    else:
        level = "full"

    label = SEASON_LABELS[key]
    span = f"{_fmt(*occ[0])} – {_fmt(*occ[-1])}"
    if level == "full":
        note = (f"The {label} ({span}) is fully covered by the dataset "
                f"({dataset_window_label()}).")
    elif level == "partial":
        cov = ", ".join(_fmt(*ym) for ym in covered)
        note = (f"Partial coverage: the {label} ({span}) is only partly available. "
                f"The dataset ({dataset_window_label()}) covers just {cov} of this season; "
                f"{len(missing)} of {len(occ)} season months have no data. "
                f"Results do not represent the complete season.")
    else:
        note = (f"No data: the {label} ({span}) falls outside the dataset "
                f"({dataset_window_label()}), so there are no matching months.")
    others = []
    if year_assumed:
        note += f" (No year was given; {season_year} was assumed.)"
        years = list(range(DATASET_START[0], DATASET_END[0] + 1))
        others = [y for y in years if y != season_year]
        if others:
            ex = others[0]
            note += (f" Data also exists for {', '.join(str(y) for y in others)}; "
                     f"add a year, for example 'the {label} {ex}', to choose it.")

    return {
        "key": key,
        "name": label,
        "season_year": season_year,
        "year_assumed": year_assumed,
        "other_years": others,
        "season_months": [list(ym) for ym in occ],
        "covered_months": [list(ym) for ym in covered],
        "missing_months": [list(ym) for ym in missing],
        "coverage": level,
        "partial_coverage": level == "partial",
        "dataset_window": dataset_window_label(),
        "coverage_note": note,
    }


def apply_season_to_intent(intent: Dict[str, Any], question: str) -> Dict[str, Any]:
    """Attach season/coverage metadata to a *data* intent (returns a new dict).

    * One season: ``intent["season"]`` gets the coverage dict. The date filter
      is narrowed to the covered months only (never the full season). If there
      is no coverage, no date filter is set and ``intent["no_data_in_dataset"]``
      is True so callers do not run an unfiltered query.
    * Several seasons in one question: marked ambiguous (one season at a time).
    * An explicit month in the intent wins over the season's month range; the
      season metadata is still attached with ``date_source="explicit_month"``.
    Knowledge / off-topic intents are returned unchanged.
    """
    if intent.get("question_kind") in ("knowledge", "off_topic") or intent.get("is_conceptual"):
        return intent
    keys = detect_seasons(question)
    if not keys:
        return intent

    out = dict(intent)
    if len(keys) > 1:
        cov = [season_coverage(k, intent.get("year")) for k in keys]
        out["seasons"] = cov
        out["ambiguous"] = True
        out["clarification_needed"] = (
            "Please ask about one season at a time. Dataset coverage: "
            + " ".join(c["coverage_note"] for c in cov))
        return out

    cov = season_coverage(keys[0], intent.get("year"))
    out["season"] = cov
    out["no_data_in_dataset"] = False

    if intent.get("month") is not None:
        cov["date_source"] = "explicit_month"
        return out
    cov["date_source"] = "season"

    if cov["coverage"] == "none":
        out["no_data_in_dataset"] = True
        for k in ("year", "month", "year_end", "month_end"):
            out[k] = None
        return out

    first, last = cov["covered_months"][0], cov["covered_months"][-1]
    out["year"], out["month"] = first
    out["year_end"], out["month_end"] = last
    return out
