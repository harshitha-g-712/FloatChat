"""
FloatChat – Rule-Based Intent Parser
====================================
Fast, 100% offline, deterministic natural language intent parser.
Requires 0 AI tokens, 0 network calls, and eliminates quota failures.
Supports multi-turn follow-ups, date ranges, comparisons, pressure filters,
geographic coordinates, named regions, float discovery, and conceptual questions.
"""

import re
from typing import Optional, List, Dict, Any
from config import coverage_label

MONTH_MAP = {
    "january": 1, "jan": 1,
    "february": 2, "feb": 2,
    "march": 3, "mar": 3,
    "april": 4, "apr": 4,
    "may": 5,
    "june": 6, "jun": 6,
    "july": 7, "jul": 7,
    "august": 8, "aug": 8,
    "september": 9, "sep": 9, "sept": 9,
    "october": 10, "oct": 10,
    "november": 11, "nov": 11,
    "december": 12, "dec": 12
}

MONTH_REGEX = r"(?:january|jan|february|feb|march|mar|april|apr|may|june|jun|july|jul|august|aug|september|sep|sept|october|oct|november|nov|december|dec)"

CONCEPTUAL_KEYWORDS = [
    "what is a thermocline", "what is thermocline", "thermocline definition",
    "what is a halocline", "what is halocline", "halocline definition",
    "what is salinity", "what does salinity mean", "how is salinity measured",
    "what is pressure", "what is dbar", "what does dbar mean",
    "what is an argo float", "how do argo floats work", "what is argo",
    "monsoon seasons", "bay of bengal monsoon", "how to read depth profile",
    "what is mixed layer", "mixed layer depth", "pycnocline"
]

SAMPLE_CLARIFICATION = (
    "I could not understand the specific ocean query. Here are examples of questions you can ask:\n"
    "• 'What was the average temperature in January 2023?'\n"
    "• 'Compare salinity between January and June 2023'\n"
    "• 'Show temperature profile for float 2902758'\n"
    "• 'List floats in 2023'\n"
    "• 'Where did float 2902758 travel?'\n"
    "• 'What is a thermocline?'"
)


# Ordinary words that can follow "float"/"platform"/"profile" ("depth profile for March 2023");
# they must not be mistaken for a malformed float/profile ID.
_NOT_AN_ID = (
    "for|in|of|at|on|by|to|and|or|vs|versus|with|from|during|between|near|over|across|the|a|an|"
    "is|are|was|were|has|have|had|that|which|data|number|count|counts|summary|details?|info|"
    "locations?|positions?|tracks?|travel(?:led|ed)?|drift(?:ed)?|moved|path|measurements?|"
    "observations?|similar|coverage|list|ids?|temperature|salinity|pressure|first|last|latest|"
    "newest|oldest|nearest|closest|deepest|shallowest"
)


def _extract_variable(text: str) -> Optional[str]:
    t = text.lower()
    if re.search(r"\b(oxygen|dissolved oxygen|\bph\b|acidity|alkalinity|density|dense)\b", t):
        return "unsupported:" + ("oxygen" if "oxygen" in t else "pH" if re.search(r"\bph\b", t) or "acidity" in t else "density")
    if re.search(r"\b(temp|temperature|warmest|coldest|heat)\b", t):
        return "temperature"
    if re.search(r"\b(salinity|sal|saltiest|freshest|salty|salt)\b", t):
        return "salinity"
    # Note: "at 500 dbar" specifies a depth/pressure level, not variable="pressure".
    if re.search(r"\b(pressure|deepest)\b", t) or (re.search(r"\bdepth\b", t) and not re.search(r"\bdepth[ -]profiles?\b", t)):
        return "pressure"
    # Default for 'depth profile' without explicit variable is temperature
    if re.search(r"\bdepth[ -]profiles?\b", t):
        return "temperature"
    return None


def _extract_stat(text: str, var: Optional[str]) -> str:
    t = text.lower()
    if re.search(r"\b(average|avg|mean)\b", t):
        return "avg"
    if re.search(r"\b(highest|maximum|max|warmest|saltiest|deepest|peak)\b", t):
        return "max"
    if re.search(r"\b(lowest|minimum|min|coldest|freshest|shallowest)\b", t):
        return "min"
    if re.search(r"\b(count|how many|number of observations|total profiles|number of profiles)\b", t):
        return "count"
    return "none"


def _extract_chart_type(text: str) -> str:
    t = text.lower()
    if re.search(r"\b(trajectory|track|path|drift|travel(?:ed)?)\b", t):
        return "trajectory"
    if re.search(r"\b(coverage|availability|overview|monthly)\b", t):
        return "coverage"
    if re.search(r"\b(similar|closest profiles?|profile similarity)\b", t):
        return "similar_profiles"
    if re.search(r"\b(map|spatial|location|where)\b", t):
        return "map"
    if re.search(r"\b(depth[ -]profiles?|profiles? vs depth|vs depth|vertical profiles?|(?:temperature|temp|salinity)\s+profiles?)\b", t):
        return "depth_profile"
    if re.search(r"\b(timeseries|trend|over time|time series|progression)\b", t):
        return "timeseries"
    if re.search(r"\b(distribution|histogram|hist|spread)\b", t):
        return "distribution"
    if re.search(r"\b(compare|versus|vs|comparison)\b", t):
        return "compare"
    return "none"


def _extract_platform_id(text: str) -> Optional[str]:
    # Match platform IDs e.g. "float 2902758", "platform 2902123", "2902758_139", or isolated 7-digit ID
    m = re.search(r"\b(?:float|platform|profile|id)\s*#?\s*([0-9]{7}(?:_[0-9]{1,4})?)\b|(?<![A-Za-z])([0-9]{7}_[0-9]{1,4})(?![A-Za-z])", text, re.IGNORECASE)
    if m:
        val = m.group(1) or m.group(2)
        if "_" in val:
            return None
        return val
    return None


def _extract_profile_id(text: str) -> Optional[str]:
    m = re.search(r"\b([0-9]{7}_[0-9]{1,4})\b", text)
    if m:
        return m.group(1)
    return None


def _extract_named_region(text: str) -> Optional[str]:
    t = text.lower()
    if "andaman" in t:
        return "Andaman Sea"
    if "north bay of bengal" in t or "northern bay" in t:
        return "North Bay of Bengal"
    if "south bay of bengal" in t or "southern bay" in t:
        return "South Bay of Bengal"
    if "central bay of bengal" in t:
        return "Central Bay of Bengal"
    if "bay of bengal" in t:
        return "Bay of Bengal"
    if "sri lanka" in t:
        return "Sri Lanka"
    return None


def _extract_coordinates(text: str) -> tuple[Optional[float], Optional[float], Optional[float]]:
    # 1. Look for lat/lon like 15.5N 88.2E or 15N, 88E
    m_dir = re.search(r"(\d+(?:\.\d+)?)\s*°?\s*([NS])\s*[,;]?\s*(\d+(?:\.\d+)?)\s*°?\s*([EW])", text, re.IGNORECASE)
    if m_dir:
        lat = float(m_dir.group(1)) * (-1 if m_dir.group(2).upper() == "S" else 1)
        lon = float(m_dir.group(3)) * (-1 if m_dir.group(4).upper() == "W" else 1)
        return lat, lon, 2.0

    # 2. Look for lat X lon Y
    m_latlon = re.search(r"lat(?:itude)?\s*[:=]?\s*([+-]?\d+(?:\.\d+)?)\s*[,;]?\s*lon(?:gitude)?\s*[:=]?\s*([+-]?\d+(?:\.\d+)?)", text, re.IGNORECASE)
    if m_latlon:
        return float(m_latlon.group(1)), float(m_latlon.group(2)), 2.0

    # 3. Look for named point Sri Lanka (approx lat 7.5, lon 82.5)
    if "sri lanka" in text.lower():
        return 7.5, 82.5, 3.0

    return None, None, None


def _extract_pressure_range(text: str) -> tuple[Optional[float], Optional[float]]:
    # "between 100 and 500 dbar" or "between 100 and 500 m" or "100-500 dbar"
    m = re.search(r"(?:between|from)?\s*(\d+(?:\.\d+)?)\s*(?:to|and|-)\s*(\d+(?:\.\d+)?)\s*(?:dbar|m|meter|meters|depth)?", text, re.IGNORECASE)
    if m and ("dbar" in text.lower() or "depth" in text.lower() or "pressure" in text.lower()):
        p1 = float(m.group(1))
        p2 = float(m.group(2))
        return min(p1, p2), max(p1, p2)

    # A single explicitly requested depth/pressure (for example, "at 2000 dbar")
    # is an exact level, not an unfiltered query. Keep it separate from year tokens.
    m_exact = re.search(r"\b(?:at|exactly|near)\s+(\d+(?:\.\d+)?)\s*(?:dbar|decibar|decibars)\b", text, re.IGNORECASE)
    if m_exact:
        value = float(m_exact.group(1))
        return value, value

    # "below 500 dbar", "> 500 dbar"
    m_min = re.search(r"(?:below|>|greater than|deeper than)\s*(\d+(?:\.\d+)?)\s*(?:dbar|m)?", text, re.IGNORECASE)
    if m_min and ("dbar" in text.lower() or "depth" in text.lower() or "pressure" in text.lower()):
        return float(m_min.group(1)), None

    # "under 200 dbar", "< 200 dbar", "surface" (0 to 50 dbar)
    if re.search(r"\bsurface\b", text, re.IGNORECASE):
        return 0.0, 50.0

    m_max = re.search(r"(?:above|<|less than|shallower than|under)\s*(\d+(?:\.\d+)?)\s*(?:dbar|m)?", text, re.IGNORECASE)
    if m_max and ("dbar" in text.lower() or "depth" in text.lower() or "pressure" in text.lower()):
        return None, float(m_max.group(1))

    return None, None


_COMPARE_WORD = re.compile(r"\b(compare|compared|comparison|versus|vs|difference|differences|differ|differs)\b")
_MAY_VERB = re.compile(r"\bmay\s+(?:be|have|also|not|need|want|cause)\b")


def _extract_explicit_periods(t: str) -> Optional[Dict[str, Any]]:
    """Comparisons / ranges that name periods in different years ("July 2023 vs July 2024").

    Returns the date fields to merge, or None to let the older single-year patterns run.
    Without this, the second period was silently dropped and only the first was answered.
    """
    has_compare = bool(_COMPARE_WORD.search(t))
    mentions = []   # [month, year-or-None] in order of appearance
    for m in re.finditer(rf"\b({MONTH_REGEX})\b(?:\s+((?:19|20)\d\d)\b)?", t):
        if m.group(1) == "may" and not m.group(2) and _MAY_VERB.search(t):
            continue
        mentions.append([MONTH_MAP[m.group(1)], int(m.group(2)) if m.group(2) else None])
    all_explicit = bool(mentions and all(m[1] is not None for m in mentions))
    # "March and April 2024": a month without a year takes the next explicit year after it.
    next_year = None
    for mention in reversed(mentions):
        if mention[1] is None:
            mention[1] = next_year
        else:
            next_year = mention[1]
    periods = []
    for mo, yr in mentions:
        if (yr, mo) not in [(p["year"], p["month"]) for p in periods]:
            periods.append({"year": yr, "month": mo})

    if has_compare and len(periods) >= 2:
        years = {p["year"] for p in periods}
        if len(years) == 1:
            if all_explicit:
                return {"compare": True, "compare_months": [p["month"] for p in periods[:4]],
                        "compare_periods": periods[:4], "year": list(years)[0],
                        "month": None, "year_end": None, "month_end": None}
            return None            # same year (or none): the original compare pattern handles it
        if None in years:
            return {"compare": True, "compare_months": None, "compare_periods": None,
                    "year": None, "month": None, "year_end": None, "month_end": None,
                    "_ambiguous_periods": True}
        return {"compare": True, "compare_months": [p["month"] for p in periods[:4]],
                "compare_periods": periods[:4], "year": None, "month": None, "year_end": None, "month_end": None}

    if has_compare and not mentions:
        years = []
        for m in re.finditer(r"\b((?:19|20)\d\d)\b(?!\s*(?:dbar|decibars?|m\b|meters?))", t):
            if int(m.group(1)) not in years:
                years.append(int(m.group(1)))
        if len(years) >= 2:
            return {"compare": True, "compare_months": None,
                    "compare_periods": [{"year": y, "month": None} for y in years[:4]],
                    "year": None, "month": None, "year_end": None, "month_end": None}

    if not has_compare and len(periods) >= 2 and all(p["year"] is not None for p in periods):
        first, last = sorted(periods, key=lambda p: (p["year"], p["month"]))[::len(periods) - 1]
        if first["year"] != last["year"]:
            return {"year": first["year"], "month": first["month"],
                    "year_end": last["year"], "month_end": last["month"]}
        elif all_explicit:
            # Same year periods where both had explicit year: "Feb 2023 to Mar 2023" vs "Feb 2023 and Mar 2023"
            if re.search(r"\b(to|through)\b", t) and not re.search(r"\band\b", t):
                return {"year": first["year"], "month": first["month"],
                        "year_end": last["year"], "month_end": last["month"]}
            return {
                "compare": True,
                "compare_months": [p["month"] for p in periods[:4]],
                "compare_periods": periods[:4],
                "year": first["year"],
                "month": None,
                "year_end": None,
                "month_end": None,
            }
    return None


def _extract_dates(text: str) -> Dict[str, Any]:
    res = {
        "year": None,
        "month": None,
        "year_end": None,
        "month_end": None,
        "compare": False,
        "compare_months": None,
        "compare_periods": None,
    }
    t = text.lower()

    explicit = _extract_explicit_periods(t)
    if explicit is not None:
        res.update(explicit)
        return res

    # 1. Compare pattern: "compare January and July 2023" or "Jan vs July 2023"
    m_comp = re.search(
        rf"(?:compare|vs|versus)(?:\s+\w+){{0,4}}?\s+({MONTH_REGEX})\s+(?:and|with|to|vs|versus)\s+({MONTH_REGEX})(?:\s+(\d{{4}}))?",
        t
    )
    if m_comp:
        m1 = MONTH_MAP[m_comp.group(1)]
        m2 = MONTH_MAP[m_comp.group(2)]
        yr = int(m_comp.group(3)) if m_comp.group(3) else None
        res["compare"] = True
        res["compare_months"] = [m1, m2]
        res["year"] = yr
        return res

    # 2. Date range of months in a year: "between January and March 2023", "Jan to Mar 2023", "from Jan to Mar"
    m_mrange = re.search(
        rf"(?:between|from)?\s*({MONTH_REGEX})\s*(?:to|and|-)\s*({MONTH_REGEX})(?:\s+(\d{{4}}))?",
        t
    )
    if m_mrange:
        res["month"] = MONTH_MAP[m_mrange.group(1)]
        res["month_end"] = MONTH_MAP[m_mrange.group(2)]
        if m_mrange.group(3):
            yr = int(m_mrange.group(3))
            if res["month_end"] < res["month"]:
                res["year"] = yr - 1
                res["year_end"] = yr
            else:
                res["year"] = yr
                res["year_end"] = yr
        return res

    # 2b. Slash dates: "02/2023 to 04/2023" or single "02/2023"
    m_slash_range = re.search(r"\b(0?[1-9]|1[0-2])/(19\d\d|20\d\d)\s*(?:to|and|-)\s*(0?[1-9]|1[0-2])/(19\d\d|20\d\d)\b", t)
    if m_slash_range:
        m1, y1 = int(m_slash_range.group(1)), int(m_slash_range.group(2))
        m2, y2 = int(m_slash_range.group(3)), int(m_slash_range.group(4))
        if "and" in m_slash_range.group(0):
            res["compare"] = True
            res["compare_months"] = [m1, m2]
            res["compare_periods"] = [{"year": y1, "month": m1}, {"year": y2, "month": m2}]
            res["year"] = y1 if y1 == y2 else None
            return res
        res["month"], res["year"] = m1, y1
        res["month_end"], res["year_end"] = m2, y2
        return res

    m_slash = re.search(r"\b(0?[1-9]|1[0-2])/(19\d\d|20\d\d)\b", t)
    if m_slash:
        res["month"] = int(m_slash.group(1))
        res["year"] = int(m_slash.group(2))
        res["year_end"] = res["year"]
        return res

    # 2c. Month + Year to Year: "January 2023 to 2024", "Jan 2023 - 2024", "from January 2023 to 2024"
    m_my_to_y = re.search(rf"\b(?:between|from)?\s*({MONTH_REGEX})\s+(\d{{4}})\s*(?:to|and|-)\s*(\d{{4}})\b", t)
    if m_my_to_y:
        res["month"] = MONTH_MAP[m_my_to_y.group(1)]
        res["year"] = int(m_my_to_y.group(2))
        res["year_end"] = int(m_my_to_y.group(3))
        return res

    # 2d. Year to Month + Year: "2023 to March 2024", "from 2023 to March 2024", "between 2023 and March 2024"
    m_y_to_my = re.search(rf"\b(?:between|from)?\s*(\d{{4}})\s*(?:to|and|-)\s*({MONTH_REGEX})\s+(\d{{4}})\b", t)
    if m_y_to_my:
        res["year"] = int(m_y_to_my.group(1))
        res["month"] = None
        res["month_end"] = MONTH_MAP[m_y_to_my.group(2)]
        res["year_end"] = int(m_y_to_my.group(3))
        return res

    # 3. Year range: "2022 to 2024", "between 2022 and 2024", "2022-2024"
    m_yrange = re.search(r"\b(?:between|from)?\s*(\d{4})\s*(?:to|and|-)\s*(\d{4})\b", t)
    if m_yrange:
        res["year"] = int(m_yrange.group(1))
        res["year_end"] = int(m_yrange.group(2))
        return res

    # 4. Month + Year: "January 2023", "Jan 2023"
    m_my = re.search(rf"\b({MONTH_REGEX})\s+(\d{{4}})\b", t)
    if m_my:
        res["month"] = MONTH_MAP[m_my.group(1)]
        res["year"] = int(m_my.group(2))
        res["year_end"] = res["year"]
        return res

    # 5. Month only: "in January", "during July"
    m_m = re.search(rf"\b({MONTH_REGEX})\b", t)
    if m_m and not (m_m.group(1) == "may" and re.search(r"\bmay\s+(?:be|have|also|not|need|want|cause|cause)", t)):
        res["month"] = MONTH_MAP[m_m.group(1)]

    # 6. Year only: "in 2023", "for 2024"
    m_y = None if re.search(r"\b\d+(?:\.\d+)?\s*(?:dbar|decibar|dbars)\b", t) else re.search(r"\b(19\d\d|20\d\d)\b", t)
    if m_y:
        res["year"] = int(m_y.group(1))
        res["year_end"] = res["year"]

    return res


def _check_conceptual(text: str) -> tuple[bool, Optional[str], Optional[List[str]]]:
    t = text.lower().strip()
    # A variable combined with a year/date asks for observations, not a definition.
    if re.search(r"\b(temperature|temp|salinity|pressure|dbar)\b", t) and re.search(r"\b(19\d{2}|20\d{2})\b", t):
        return False, None, None
    for kw in CONCEPTUAL_KEYWORDS:
        if kw in t or t.startswith(kw):
            return True, None, None

    # If it contains variable names or months or stats, it's not a general concept question
    if any(v in t for v in ["temperature", "temp", "salinity", "pressure", "dbar", "warmest", "coldest", "saltiest", "deepest", "average", "avg", "mean", "min", "max", "highest", "lowest"]):
        if any(m in t for m in MONTH_MAP.keys()) or re.search(r"\b(19\d\d|20\d\d|\d{7})\b", t) or "in " in t or "near " in t or "for " in t or "between " in t:
            return False, None, None

    if re.search(r"^(what is|what are|explain|define|how do|how does|what does)\b", t) and not any(
        w in t for w in ["average", "avg", "min", "max", "highest", "lowest", "warmest", "coldest", "saltiest", "count", "data", "profiles", "floats in", "temperature in", "salinity in", "pressure in"]
    ):
        return True, None, None
    return False, None, None


def _check_discovery_task(text: str) -> Optional[str]:
    t = text.lower()
    if re.search(r"\b(similar profiles?|profiles? similar to|find similar)\b", t):
        return "similar_profiles"
    if re.search(
        r"\b(trajectory|where\s+(?:is|did|are)\s+(?:float|platform)|"
        r"where\s+(?:the\s+)?(?:float|platform)\b.*?is|"
        r"track\s+(?:float|platform)|float\s+path|float\s+track|drift\s+track|"
        r"location\s+of\s+(?:float|platform))\b",
        t,
    ):
        return "trajectory"
    if re.search(r"\b(coverage|what data do you have|what datasets? do you have|dataset overview|data availability|how much data)\b", t):
        return "coverage"
    if re.search(r"\b(tell me about float|float summary|float details?|details? for float|info on float|about platform)\b", t):
        return "float_detail"
    if re.search(r"\b(list floats?|which floats?|find floats?|floats near|floats in|show floats?|all floats?)\b", t):
        return "discover_floats"
    return None


def _check_invalid_day(text: str) -> Optional[str]:
    import calendar
    t = text.lower()
    # Pattern 1: Month Day (e.g. "February 30", "Feb 30th", "February 30 2023")
    for m in re.finditer(rf"\b({MONTH_REGEX})\s+(\d{{1,2}})(?:st|nd|rd|th)?(?:\s+((?:19|20)\d\d))?\b", t):
        mo_name, day_str, yr_str = m.group(1), m.group(2), m.group(3)
        mo = MONTH_MAP.get(mo_name)
        if not mo:
            continue
        day = int(day_str)
        yr = int(yr_str) if yr_str else 2024
        max_days = calendar.monthrange(yr, mo)[1] if yr_str else (29 if mo == 2 else (30 if mo in (4, 6, 9, 11) else 31))
        if day < 1 or day > max_days:
            return f"{mo_name.title()} {day}"

    # Pattern 2: Day Month (e.g. "30th of February", "30 February", "31st of April 2023")
    for m in re.finditer(rf"\b(\d{{1,2}})(?:st|nd|rd|th)?\s+(?:of\s+)?({MONTH_REGEX})(?:\s+((?:19|20)\d\d))?\b", t):
        day_str, mo_name, yr_str = m.group(1), m.group(2), m.group(3)
        mo = MONTH_MAP.get(mo_name)
        if not mo:
            continue
        day = int(day_str)
        yr = int(yr_str) if yr_str else 2024
        max_days = calendar.monthrange(yr, mo)[1] if yr_str else (29 if mo == 2 else (30 if mo in (4, 6, 9, 11) else 31))
        if day < 1 or day > max_days:
            return f"{mo_name.title()} {day}"

    return None


def parse_intent(question: str, history: Optional[List[Dict[str, Any]]] = None) -> Dict[str, Any]:
    """Parse natural language question into structured intent dict.
    
    Adheres strictly to the validator schema and handles multi-turn memory.
    """
    raw_q = (question or "").strip()
    q_lower = raw_q.lower()

    # Initial empty intent template
    intent: Dict[str, Any] = {
        "task": "stat",
        "variable": None,
        "stat": "none",
        "year": None,
        "month": None,
        "year_end": None,
        "month_end": None,
        "compare": False,
        "compare_months": None,
        "compare_periods": None,
        "region_lat": None,
        "region_lon": None,
        "region_radius_deg": None,
        "named_region": None,
        "platform_id": None,
        "profile_id": None,
        "chart_type": "none",
        "pressure_min": None,
        "pressure_max": None,
        "export_csv": False,
        "ambiguous": False,
        "clarification_needed": None,
        "is_conceptual": False,
        "conceptual_answer": None,
        "rag_sources": None,
    }

    if not raw_q:
        intent["ambiguous"] = True
        intent["clarification_needed"] = SAMPLE_CLARIFICATION
        return intent

    # Check for invalid day (e.g. "February 30", "April 31")
    bad_day = _check_invalid_day(q_lower)
    if bad_day:
        intent["ambiguous"] = True
        intent["clarification_needed"] = f"Invalid date: {bad_day} does not exist on the calendar. Please provide a valid calendar date."
        return intent

    # Reject unsupported relative dates (e.g. "last month", "yesterday") rather than returning all-time averages
    m_rel = re.search(
        r"\b(last\s+month|this\s+month|next\s+month|past\s+month|recent\s+months?|"
        r"last\s+year|this\s+year|next\s+year|past\s+year|recent\s+years?|"
        r"last\s+week|this\s+week|past\s+week|yesterday|today|tomorrow)\b",
        q_lower,
    )
    if m_rel:
        intent["ambiguous"] = True
        intent["clarification_needed"] = (
            f"Relative dates like '{m_rel.group(1)}' are not supported. "
            f"The database covers {coverage_label()}. Please specify an explicit month and year, for example 'January 2023'."
        )
        return intent

    # Reject explicit impossible date filters rather than silently dropping them.
    bad_month = re.search(r"\bmonth\s+(\d{1,2})\b", q_lower)
    bad_year = re.search(r"\byear\s+(\d{4})\b", q_lower)
    if (bad_month and not 1 <= int(bad_month.group(1)) <= 12) or (bad_year and not 1900 <= int(bad_year.group(1)) <= 2100):
        intent["ambiguous"] = True
        intent["clarification_needed"] = "That month or year is outside the supported range. Please provide a month from 1–12 and a valid year."
        return intent

    # Check export request
    if re.search(r"\b(export|download|csv)\b", q_lower):
        intent["export_csv"] = True

    if re.search(r"\bmonsoon\b", q_lower) and not re.search(r"\b(pre[ -]?monsoon|south[ -]?west\s+monsoon|north[ -]?east\s+monsoon|sw\s+monsoon|ne\s+monsoon)\b", q_lower):
        intent["ambiguous"] = True
        intent["clarification_needed"] = "Which monsoon period do you mean: pre-monsoon (March–May), south-west monsoon (June–September), or north-east monsoon (October–January)? The bundled data only covers " + coverage_label() + "."
        return intent

    # 1. Conceptual check
    is_concept, ans, sources = _check_conceptual(raw_q)
    if is_concept:
        intent["task"] = "concept"
        intent["is_conceptual"] = True
        intent["conceptual_answer"] = ans
        intent["rag_sources"] = sources
        return intent

    # 2. Discovery task check
    disc_task = _check_discovery_task(raw_q)
    if disc_task:
        intent["task"] = disc_task

    # Extract entities
    intent["variable"] = _extract_variable(raw_q)
    intent["stat"] = _extract_stat(raw_q, intent["variable"])
    intent["chart_type"] = _extract_chart_type(raw_q)
    intent["platform_id"] = _extract_platform_id(raw_q)
    intent["profile_id"] = _extract_profile_id(raw_q)
    if intent["task"] == "trajectory":
        intent["chart_type"] = "trajectory"
        intent["variable"] = None
        intent["stat"] = "none"
    if re.search(rf"\b(?:float|platform|profile)\s+(?!(?:{_NOT_AN_ID})\b)[A-Za-z0-9_]+", raw_q, re.IGNORECASE) and not intent["platform_id"] and not intent["profile_id"]:
        intent["ambiguous"] = True
        intent["clarification_needed"] = "I could not validate that float/profile ID. Please provide a 7-digit float ID or a profile ID such as 2902758_002."
        return intent
    intent["named_region"] = _extract_named_region(raw_q)

    lat, lon, rad = _extract_coordinates(raw_q)
    if lat is not None and lon is not None:
        intent["region_lat"] = lat
        intent["region_lon"] = lon
        intent["region_radius_deg"] = rad

    pmin, pmax = _extract_pressure_range(raw_q)
    intent["pressure_min"] = pmin
    intent["pressure_max"] = pmax

    dates = _extract_dates(raw_q)
    if dates.pop("_ambiguous_periods", False):
        intent["ambiguous"] = True
        intent["clarification_needed"] = ("Some of the months you want to compare have a year and some do not. "
                                          "Please give a year for each, for example 'Compare March 2023 and April 2024'.")
        return intent
    intent.update(dates)
    if intent.get("compare") and intent.get("stat") == "none":
        intent["stat"] = "avg"

    # 3. Follow-up handling from history
    # If the user asks a follow-up e.g. "what about salinity?", "and in 2024?", "show as map"
    if history:
        last_intent = None
        for turn in reversed(history):
            if not isinstance(turn, dict):
                continue
            candidate = turn.get("intent")
            if not isinstance(candidate, dict):
                candidate = turn.get("intent_summary")
            if not isinstance(candidate, dict):
                response_data = turn.get("response_data")
                if isinstance(response_data, dict):
                    candidate = response_data.get("intent")
            if not isinstance(candidate, dict):
                continue
            # Knowledge/off-topic turns must not shadow the last usable data intent.
            if candidate.get("question_kind") in ("knowledge", "off_topic") or candidate.get("task") == "concept":
                continue
            if candidate.get("variable") or candidate.get("year") or candidate.get("month") or candidate.get("platform_id"):
                last_intent = candidate
                break

        _INHERIT_KEYS = ("variable", "stat", "year", "year_end", "month", "month_end",
                         "pressure_min", "pressure_max", "platform_id", "named_region")
        _before_inherit = {k: intent.get(k) for k in _INHERIT_KEYS}
        if last_intent:
            is_followup = bool(re.search(r"\b(what about|how about|and|also|same|instead|show as|plot as)\b", q_lower))
            has_explicit_filter = bool(intent["year"] or intent["month"] or intent["pressure_min"] is not None or intent["pressure_max"] is not None or intent["platform_id"])
            was_missing_variable = not intent["variable"]
            is_trend = (intent["chart_type"] == "timeseries" or bool(re.search(r"\b(timeseries|trend|trends|trending|over time|time series|progression)\b", q_lower)))
            if is_trend:
                intent["chart_type"] = "timeseries"
            # A message with nothing recognisable in it (gibberish, or a pure punctuation/SQL string)
            # must not silently re-run the previous question's filters.
            _recognised = bool(
                intent["variable"] or intent["stat"] != "none" or has_explicit_filter
                or intent["chart_type"] != "none" or is_followup or is_trend
                or intent.get("compare") or intent.get("compare_periods") or intent.get("compare_months")
                or intent.get("named_region") or intent.get("task") not in (None, "stat")
            )
            if not _recognised:
                last_intent = None
        if last_intent:
            # A stand-alone "how many floats/profiles ...?" is a new question, not a follow-up:
            # it keeps only the filters it names itself.
            _standalone_count = (
                not is_followup and not has_explicit_filter
                and bool(re.search(r"\b(how many|number of)\b", q_lower))
                and bool(re.search(r"\b(floats?|profiles?)\b", q_lower))
            )
            if _standalone_count:
                last_intent = None
        if last_intent:

            # If current question omitted variable but asked a stat/time/chart/depth/followup
            if was_missing_variable and last_intent.get("variable"):
                if intent["stat"] != "none" or has_explicit_filter or intent["chart_type"] != "none" or is_followup or is_trend:
                    intent["variable"] = last_intent.get("variable")

            # Follow-up inheritance:
            # 1) When user specifies variable only ("what about salinity?")
            # 2) When user specifies month or year ("what about August?", "and in 2024?")
            # 3) When user specifies depth only ("at 500 dbar", "what about at 500 dbar?")
            # 4) When user uses follow-up phrase ("and in 2024?", "what about ...")
            if is_followup or was_missing_variable or (not has_explicit_filter and intent["stat"] == "none") or is_trend:
                # Inherit stat if current has none (trend queries must remain stat="none" to return timeseries data)
                if intent["stat"] == "none" and last_intent.get("stat") and last_intent["stat"] != "none":
                    if not is_trend:
                        intent["stat"] = last_intent["stat"]
                # Inherit year if current question did not name a year (trend queries widen to full dataset unless explicit year given)
                if not intent["year"] and last_intent.get("year"):
                    if not is_trend:
                        intent["year"] = last_intent["year"]
                        if last_intent.get("year_end"):
                            intent["year_end"] = last_intent["year_end"]
                # Inherit month if current question did not name a month (trend queries widen to full dataset unless explicit month given)
                if not intent["month"] and last_intent.get("month"):
                    if not is_trend:
                        intent["month"] = last_intent["month"]
                        if last_intent.get("month_end"):
                            intent["month_end"] = last_intent["month_end"]
                # Inherit pressure range if current did not specify any
                if intent["pressure_min"] is None and intent["pressure_max"] is None:
                    if last_intent.get("pressure_min") is not None:
                        intent["pressure_min"] = last_intent["pressure_min"]
                    if last_intent.get("pressure_max") is not None:
                        intent["pressure_max"] = last_intent["pressure_max"]
                # Inherit platform_id if current has none
                if not intent["platform_id"] and last_intent.get("platform_id"):
                    intent["platform_id"] = last_intent["platform_id"]
                # Inherit named_region if current has none
                if not intent["named_region"] and last_intent.get("named_region"):
                    intent["named_region"] = last_intent["named_region"]

            # If current question asks for a chart only e.g. "show as map" or "show trend"
            if intent["chart_type"] != "none" and not intent["variable"] and last_intent.get("variable"):
                intent["variable"] = last_intent.get("variable")
                if not is_trend:
                    intent["stat"] = last_intent.get("stat", "none")
                    intent["year"] = last_intent.get("year")
                    intent["month"] = last_intent.get("month")

            if is_trend:
                intent["chart_type"] = "timeseries"
                if _extract_stat(raw_q, intent["variable"]) == "none":
                    intent["stat"] = "none"
                if not (dates and (dates.get("year") or dates.get("month"))):
                    intent["year"] = None
                    intent["year_end"] = None
                    intent["month"] = None
                    intent["month_end"] = None

    # Tell the caller which settings came from the previous question rather than from this one,
    # so the reply can say so instead of applying them silently.
    if history:
        _carried = [k for k in _INHERIT_KEYS
                    if _before_inherit.get(k) in (None, "", "none") and intent.get(k) not in (None, "", "none")]
        if _carried:
            intent["inherited"] = _carried

    # Set default chart type if sensible
    if intent["chart_type"] == "none":
        if intent["task"] == "trajectory":
            intent["chart_type"] = "trajectory"
        elif intent["task"] == "coverage":
            intent["chart_type"] = "coverage"
        elif intent["task"] == "similar_profiles":
            intent["chart_type"] = "similar_profiles"
        elif intent["task"] == "discover_floats":
            intent["chart_type"] = "floats_map"
        elif intent["compare"]:
            intent["chart_type"] = "compare"
        elif intent["platform_id"]:
            intent["chart_type"] = "depth_profile"
        elif intent["year"] and not intent["month"]:
            intent["chart_type"] = "timeseries"

    # Validate whether we have a meaningful question or if it is ambiguous
    has_target = any([
        intent["variable"],
        (intent["stat"] == "count" and re.search(r"\b(profiles?|floats?)\b", raw_q.lower())),
        intent["platform_id"],
        intent["profile_id"],
        intent["task"] in ("discover_floats", "float_detail", "trajectory", "coverage", "similar_profiles", "concept"),
        intent["region_lat"] is not None,
        intent["named_region"],
        intent["year"] is not None,
        intent["month"] is not None,
        intent["compare"],
        bool(intent.get("compare_periods")),
        bool(intent.get("compare_months")),
    ])

    if not has_target:
        intent["ambiguous"] = True
        intent["clarification_needed"] = SAMPLE_CLARIFICATION

    return intent
