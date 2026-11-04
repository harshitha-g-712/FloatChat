"""
FloatChat – Retrieval / query layer
=====================================
Given the structured query intent produced by gemini_service.interpret_question(),
build a safe, parameterised SQL query against the real SQLite ARGO database,
execute it, and compute exact statistics in Python.

No arbitrary SQL is ever executed; only the validated query built here
reaches the database.
"""

import sqlite3
import logging
from typing import Optional

logger = logging.getLogger("floatchat.retrieval")

from config import DB_PATH, VARIABLES as VARIABLE_META
from retrieval.validators import validate_platform_id


# ── Query construction ─────────────────────────────────────────────────────────

def _date_bounds(year: Optional[int], month: Optional[int],
                 year_end: Optional[int], month_end: Optional[int]):
    """Return ISO date strings [start, end) or None if no date filter."""
    if year is None:
        return None
    start_y, start_m = year, month or 1
    end_y = year_end or year
    if year_end and year_end != year and month_end is None:
        end_m = None
    else:
        end_m = month_end or month

    start = f"{start_y:04d}-{start_m:02d}-01"
    if end_m is None:
        end = f"{end_y + 1:04d}-01-01"
    elif end_m == 12:
        end = f"{end_y + 1:04d}-01-01"
    else:
        end = f"{end_y:04d}-{end_m + 1:02d}-01"
    return start, end


def build_query(intent: dict) -> tuple[str, list]:
    """Build a safe parameterised SQL query from the validated intent.
    Returns (sql, params).  Only whitelisted columns and filters are used.
    """
    sql = """
        SELECT p.id, p.platform, p.lat, p.lon, p.timestamp,
               m.pressure, m.temperature, m.salinity
        FROM profiles p
        JOIN measurements m ON p.id = m.profile_id
        WHERE 1=1
    """
    params: list = []

    bounds = _date_bounds(
        intent.get("year"), intent.get("month"),
        intent.get("year_end"), intent.get("month_end"),
    )
    if bounds:
        sql += " AND p.timestamp >= ? AND p.timestamp < ?"
        params.extend(bounds)

    lat = intent.get("region_lat")
    lon = intent.get("region_lon")
    radius = intent.get("region_radius_deg")
    if lat is not None and lon is not None:
        r = radius or 2.0
        sql += " AND p.lat BETWEEN ? AND ? AND p.lon BETWEEN ? AND ?"
        params.extend([lat - r, lat + r, lon - r, lon + r])

    pmin = intent.get("pressure_min")
    pmax = intent.get("pressure_max")
    if pmin is not None:
        sql += " AND m.pressure >= ?"
        params.append(pmin)
    if pmax is not None:
        sql += " AND m.pressure <= ?"
        params.append(pmax)

    # Only a well-formed 7-digit float ID filters; anything else is ignored.
    platform_id = validate_platform_id(intent.get("platform_id"))
    if platform_id is not None:
        sql += " AND p.platform = ?"
        params.append(platform_id)
        
    named_region = intent.get("named_region")
    if named_region is not None:
        region = str(named_region).lower()
        if "north" in region:
            sql += " AND p.lat >= ?"; params.append(15.0)
        elif "south" in region:
            sql += " AND p.lat <= ?"; params.append(10.0)
        elif "central" in region:
            sql += " AND p.lat > ? AND p.lat < ?"; params.extend([10.0, 15.0])
        elif "andaman" in region:
            sql += " AND p.lon >= ?"; params.append(92.0)
        elif "sri lanka" in region:
            sql += " AND p.lon <= ? AND p.lat <= ?"; params.extend([82.5, 10.0])
        else:
            sql += " AND p.region LIKE ?"; params.append(f"%{named_region}%")

    sql += " ORDER BY p.timestamp"
    return sql, params


# ── Statistics ─────────────────────────────────────────────────────────────────

def compute_stat(rows: list, variable: str, stat_type: str) -> Optional[dict]:
    """Compute the requested statistic in Python over the returned rows.
    Returns a dict or None if there are no valid values."""
    col = variable if variable in VARIABLE_META else "temperature"
    values = [r.get(col) for r in rows if r.get(col) is not None]
    if not values:
        return None
    if stat_type == "count":
        return {"stat": "count", "value": len(values), "parameter": col}
    if stat_type == "avg":
        return {"stat": "avg", "value": round(sum(values) / len(values), 3), "parameter": col}
    if stat_type == "max":
        return {"stat": "max", "value": round(max(values), 3), "parameter": col}
    if stat_type == "min":
        return {"stat": "min", "value": round(min(values), 3), "parameter": col}
    return None


# ── Main retrieval entry point ────────────────────────────────────────────────

def retrieve(intent: dict, db_path: str = None) -> dict:
    """Execute the validated query and return a fully described result dict.

    For compare queries (intent["compare"] is True) a separate sub-query
    is run per comparison period and grouped into compare_groups.
    """
    db_path = db_path or DB_PATH
    variable = intent.get("variable") or "temperature"
    if variable not in VARIABLE_META:
        variable = "temperature"
    stat_type = intent.get("stat") or "none"
    units = VARIABLE_META[variable]["units"]

    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    try:
        if intent.get("compare") and (intent.get("compare_months") or intent.get("compare_periods")):
            return _retrieve_compare(conn, intent, variable, stat_type, units)

        sql, params = build_query(intent)
        rows = [dict(r) for r in conn.execute(sql, params).fetchall()]
        # A month without a year is a calendar-month filter, not an all-time label.
        if intent.get("month") is not None and intent.get("year") is None:
            start_month = int(intent["month"])
            end_month = int(intent.get("month_end") or start_month)
            rows = [r for r in rows if r.get("timestamp") and (start_month <= int(r["timestamp"][5:7]) <= end_month if start_month <= end_month else (int(r["timestamp"][5:7]) >= start_month or int(r["timestamp"][5:7]) <= end_month))]
        stat = compute_stat(rows, variable, stat_type) if stat_type != "none" else None

        return {
            "rows": rows,
            "count": sum(1 for row in rows if row.get(variable) is not None),
            "row_count": len(rows),
            "stat": stat,
            "compare_groups": None,
            "variable": variable,
            "units": units,
            "filters": _filters_summary(intent),
        }
    finally:
        conn.close()


def _retrieve_compare(conn, intent: dict, variable: str, stat_type: str, units: str) -> dict:
    """Run one sub-query per comparison month and package into groups."""
    compare_months = intent.get("compare_months") or []
    year = intent.get("year")
    groups = []
    all_rows = []

    month_names = ["Jan", "Feb", "Mar", "Apr", "May", "Jun",
                   "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]

    # Explicit (year, month) periods, e.g. July 2023 vs July 2024, or whole years 2023 vs 2024.
    for per in (intent.get("compare_periods") or [])[:4]:
        py, pm = int(per["year"]), per.get("month")
        sub_intent = dict(intent)
        sub_intent.update({"year": py, "year_end": py, "month": pm, "month_end": pm,
                           "compare": False, "compare_months": None, "compare_periods": None})
        sql, params = build_query(sub_intent)
        rows = [dict(r) for r in conn.execute(sql, params).fetchall()]
        label = f"{month_names[int(pm) - 1]} {py}" if pm else str(py)
        for r in rows:
            r["group_label"] = label
        stat = compute_stat(rows, variable, stat_type if stat_type != "none" else "avg") if rows else None
        groups.append({"label": label, "rows": rows, "count": sum(1 for row in rows if row.get(variable) is not None),
                       "row_count": len(rows), "stat": stat, "filters": _filters_summary(sub_intent)})
        all_rows.extend(rows)
    if groups:
        return {"rows": all_rows, "count": sum(1 for row in all_rows if row.get(variable) is not None),
                "row_count": len(all_rows), "stat": None, "compare_groups": groups, "variable": variable,
                "units": units, "filters": _filters_summary(intent)}

    for m in compare_months[:4]:          # cap at 4 groups
        sub_intent = dict(intent)
        sub_intent.update({"month": m, "month_end": m, "compare": False, "compare_months": None})
        sql, params = build_query(sub_intent)
        rows = [dict(r) for r in conn.execute(sql, params).fetchall()]
        if year is None:
            rows = [r for r in rows if r.get("timestamp") and int(r["timestamp"][5:7]) == int(m)]
        for r in rows:
            r["group_label"] = f"{month_names[m-1]} {year}" if year else month_names[m-1]
        stat = compute_stat(rows, variable, stat_type if stat_type != "none" else "avg") if rows else None
        label = f"{month_names[m-1]} {year}" if year else month_names[m-1]
        groups.append({"label": label, "rows": rows, "count": sum(1 for row in rows if row.get(variable) is not None), "row_count": len(rows), "stat": stat,
                        "filters": _filters_summary(sub_intent)})
        all_rows.extend(rows)

    return {
        "rows": all_rows,
        "count": sum(1 for row in all_rows if row.get(variable) is not None),
        "row_count": len(all_rows),
        "stat": None,
        "compare_groups": groups,
        "variable": variable,
        "units": units,
        "filters": _filters_summary(intent),
    }


def _filters_summary(intent: dict) -> dict:
    """Return a clean, serialisable dict of the effective filters."""
    f: dict = {}
    for k in ("year", "month", "year_end", "month_end", "pressure_min", "pressure_max"):
        if intent.get(k) is not None:
            f[k] = intent[k]
    lat = intent.get("region_lat")
    lon = intent.get("region_lon")
    if lat is not None and lon is not None:
        f["region"] = {
            "lat": lat, "lon": lon,
            "radius_deg": intent.get("region_radius_deg") or 2.0,
        }
    platform_id = validate_platform_id(intent.get("platform_id"))
    if platform_id is not None:
        f["platform_id"] = platform_id
    if intent.get("named_region"):
        f["named_region"] = intent["named_region"]
    if intent.get("variable"):
        f["parameter"] = intent["variable"]
    if intent.get("stat") and intent["stat"] != "none":
        f["stat"] = intent["stat"]
    return f


# ── Utility: check DB and count rows ─────────────────────────────────────────

def db_stats(db_path: str = None) -> dict:
    """Return basic row counts – used by the /api/health endpoint."""
    db_path = db_path or DB_PATH
    try:
        conn = sqlite3.connect(db_path)
        profiles = conn.execute("SELECT COUNT(*) FROM profiles").fetchone()[0]
        measurements = conn.execute("SELECT COUNT(*) FROM measurements").fetchone()[0]
        conn.close()
        return {"profiles": profiles, "measurements": measurements, "db_path": db_path}
    except Exception as e:
        logger.error("db_stats error: %s", e)
        return {"profiles": 0, "measurements": 0, "db_path": db_path, "error": str(e)}
