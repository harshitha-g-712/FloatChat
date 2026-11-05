"""
FloatChat – Unified Configuration & Constants
=============================================
Central single source of truth for variables, database paths,
allowed schemas, chart limits, and model configuration.
"""

import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = BASE_DIR.parent

def _resolve_db_path(env_var: str, default_name: str, preferred_dir: Path) -> str:
    raw = os.environ.get(env_var)
    if not raw:
        return str((preferred_dir / default_name).resolve())
    p = Path(raw)
    if p.is_absolute():
        return str(p.resolve())
    # Relative paths are resolved against the project root, so "backend/floatchat.db" never
    # becomes "backend/backend/floatchat.db" when the server is started from inside backend/.
    return str((PROJECT_ROOT / p).resolve())

# Database location: default to backend/floatchat.db
DB_PATH = _resolve_db_path("DB_PATH", "floatchat.db", BASE_DIR)
# Keep private account/session/chat records out of the distributable ocean-data DB.
AUTH_DB_PATH = _resolve_db_path("AUTH_DB_PATH", "floatchat_auth.db", PROJECT_ROOT)

# Variable metadata
VARIABLES = {
    "temperature": {
        "column": "m.temperature",
        "units": "°C",
        "prompt_description": "temperature (measured in °C)"
    },
    "salinity": {
        "column": "m.salinity",
        "units": "PSU",
        "prompt_description": "salinity (measured in PSU)"
    },
    "pressure": {
        "column": "m.pressure",
        "units": "dbar",
        "prompt_description": "pressure (measured in dbar)"
    }
}

ALLOWED_VARIABLES = set(VARIABLES.keys())
ALLOWED_STATS = {"avg", "min", "max", "count", "none"}
ALLOWED_CHART_TYPES = {
    "depth_profile",
    "timeseries",
    "distribution",
    "map",
    "compare",
    "none",
    "trajectory",
    "coverage",
    "similar_profiles",
    "floats_map"
}
# Named regions the rule-based parser can emit (see rule_intent._extract_named_region).
# Used to validate the `region` field of LLM-parsed queries.
ALLOWED_REGIONS = {
    "Bay of Bengal",
    "North Bay of Bengal",
    "South Bay of Bengal",
    "Central Bay of Bengal",
    "Andaman Sea",
    "Sri Lanka",
}

EXPANSION_REGIONS = {
    "Arabian Sea",
    "Equatorial Indian Ocean",
}

SUPPORTED_BASINS = {
    "bay_of_bengal": {
        "name": "Bay of Bengal",
        "bbox": [[80, 5], [95, 22]],
        "center": [14.0, 88.0],
        "default": True
    },
    "arabian_sea": {
        "name": "Arabian Sea",
        "bbox": [[55, 5], [77, 25]],
        "center": [15.0, 65.0],
        "default": False
    },
    "equatorial_indian_ocean": {
        "name": "Equatorial Indian Ocean",
        "bbox": [[60, -8], [95, 5]],
        "center": [-2.0, 78.0],
        "default": False
    }
}
# High-level classification of a user question (LLM parser output).
ALLOWED_QUESTION_KINDS = {"data", "knowledge", "off_topic"}
ALLOWED_TASKS = {
    "stat",
    "discover_floats",
    "float_detail",
    "trajectory",
    "coverage",
    "similar_profiles",
    "concept"
}

# AI / Quota settings
# Auto-enable Gemini features when an API key is present (evaluators see LLM active).
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "").strip()
_has_key = bool(GEMINI_API_KEY) and not GEMINI_API_KEY.startswith("your_") and GEMINI_API_KEY != "placeholder"
USE_GEMINI = os.environ.get("USE_GEMINI", "true" if _has_key else "false").strip().lower() == "true"
USE_LLM_EXPLANATION = os.environ.get("USE_LLM_EXPLANATION", "true" if _has_key else "false").strip().lower() == "true"
GEMINI_MODEL = os.environ.get("GEMINI_MODEL", "gemini-2.5-flash").strip()
GEMINI_EMBEDDING_MODEL = os.environ.get("GEMINI_EMBEDDING_MODEL", "text-embedding-004").strip()

# RAG mode: "embedding" (Gemini embeddings, requires API key) or "tfidf" (offline, default fallback)
RAG_MODE = os.environ.get("RAG_MODE", "embedding" if _has_key else "tfidf").strip().lower()

# Visualisation limits
MAX_CHART_POINTS = 4000
MAX_DISCOVERY_FLOATS = 200

# Security & CORS
ALLOWED_ORIGINS = [
    origin.strip()
    for origin in os.environ.get(
        "ALLOWED_ORIGINS",
        "http://127.0.0.1:8000,http://localhost:8000,http://127.0.0.1:5500,http://localhost:5500"
    ).split(",")
    if origin.strip()
]

# ── Dataset coverage (used by season handling in retrieval/seasons.py) ───────
# Derived from the profiles actually in the database (first and last profile month), so
# loading more years with backend/ingestion/fetch_and_load.py updates every coverage
# message automatically. The fallback below is only used if the database cannot be read.
_FALLBACK_START = (2023, 1)   # (year, month) inclusive
_FALLBACK_END = (2024, 12)    # (year, month) inclusive
_MONTH_FULL = ["January", "February", "March", "April", "May", "June", "July",
               "August", "September", "October", "November", "December"]


def _read_db_coverage(db_path=None):
    import sqlite3
    try:
        conn = sqlite3.connect(db_path or DB_PATH)
        try:
            lo, hi = conn.execute("SELECT MIN(timestamp), MAX(timestamp) FROM profiles").fetchone()
        finally:
            conn.close()
        if lo and hi:
            return (int(lo[:4]), int(lo[5:7])), (int(hi[:4]), int(hi[5:7]))
    except Exception:
        pass
    return _FALLBACK_START, _FALLBACK_END


DATASET_START, DATASET_END = _read_db_coverage()


def coverage_label(start=None, end=None) -> str:
    """Human wording of the data period: 'January–June 2023' or 'January 2023–March 2025'."""
    (y1, m1), (y2, m2) = start or DATASET_START, end or DATASET_END
    if (y1, m1) == (y2, m2):
        return f"{_MONTH_FULL[m1 - 1]} {y1}"
    if y1 == y2:
        return f"{_MONTH_FULL[m1 - 1]}\u2013{_MONTH_FULL[m2 - 1]} {y1}"
    return f"{_MONTH_FULL[m1 - 1]} {y1}\u2013{_MONTH_FULL[m2 - 1]} {y2}"


# Season phrases -> months (calendar months, in season order).
SEASON_MONTHS = {
    "south_west_monsoon": (6, 7, 8, 9),
    "north_east_monsoon": (10, 11, 12, 1),
    "pre_monsoon": (3, 4, 5),
}
