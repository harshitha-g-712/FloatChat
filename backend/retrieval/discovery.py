"""
FloatChat – Data Discovery Layer
================================
Read-only, parameterised discovery functions for exploring ARGO ocean float data.
Supports float listings, spatial searches, trajectories, coverage summaries,
and profile vertical similarity matching.
"""

import math
import sqlite3
from typing import Dict, List, Optional, Any
from config import DB_PATH, MAX_DISCOVERY_FLOATS, MAX_CHART_POINTS
from retrieval.validators import validate_platform_id


def _get_db(db_path: Optional[str] = None) -> sqlite3.Connection:
    path = db_path or DB_PATH
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    return conn


def _haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Compute haversine great-circle distance between two points in kilometres."""
    R = 6371.0  # Earth radius in km
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = (math.sin(dlat / 2.0) ** 2 +
         math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) *
         math.sin(dlon / 2.0) ** 2)
    c = 2.0 * math.atan2(math.sqrt(a), math.sqrt(1.0 - a))
    return R * c


def list_floats(filters: Optional[Dict[str, Any]] = None, db_path: Optional[str] = None) -> List[Dict[str, Any]]:
    """List distinct floats with profile counts, time bounds, bounding box, and max depths."""
    conn = _get_db(db_path)
    filters = filters or {}
    try:
        sql = """
            SELECT 
                p.platform,
                COUNT(DISTINCT p.id) as profile_count,
                MIN(p.timestamp) as first_date,
                MAX(p.timestamp) as last_date,
                MIN(p.lat) as min_lat,
                MAX(p.lat) as max_lat,
                MIN(p.lon) as min_lon,
                MAX(p.lon) as max_lon,
                AVG(m_depth.max_p) as avg_max_depth
            FROM profiles p
            INNER JOIN (
                SELECT profile_id, MAX(pressure) as max_p
                FROM measurements
                GROUP BY profile_id
            ) m_depth ON p.id = m_depth.profile_id
            WHERE 1=1
        """
        params: List[Any] = []

        year = filters.get("year")
        month = filters.get("month")
        month_end = filters.get("month_end")
        year_end = filters.get("year_end")
        if year:
            start_m = month or 1
            end_m = month_end or month or 12
            if not year_end and end_m < start_m:
                # Wrapped month range (e.g. November to February): include tail and head.
                sql += " AND (p.timestamp >= ? OR (p.timestamp >= ? AND p.timestamp < ?))"
                params.extend([f"{year:04d}-{start_m:02d}-01", f"{year:04d}-01-01", f"{year:04d}-{end_m+1:02d}-01"])
            else:
                from retrieval.query_engine import _date_bounds
                bounds = _date_bounds(year, month, year_end, month_end)
                if bounds:
                    sql += " AND p.timestamp >= ? AND p.timestamp < ?"
                    params.extend(bounds)
        elif month:
            end_m = month_end or month
            if end_m >= month:
                sql += " AND CAST(SUBSTR(p.timestamp, 6, 2) AS INTEGER) BETWEEN ? AND ?"
                params.extend([month, end_m])
            else:
                sql += " AND (CAST(SUBSTR(p.timestamp, 6, 2) AS INTEGER) >= ? OR CAST(SUBSTR(p.timestamp, 6, 2) AS INTEGER) <= ?)"
                params.extend([month, end_m])

        if filters.get("platform"):
            sql += " AND p.platform = ?"
            params.append(filters["platform"])

        if filters.get("named_region"):
            region = str(filters["named_region"]).lower()
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
                sql += " AND p.region LIKE ?"; params.append(f"%{filters['named_region']}%")

        sql += " GROUP BY p.platform ORDER BY profile_count DESC LIMIT ?"
        params.append(MAX_DISCOVERY_FLOATS)

        rows = conn.execute(sql, params).fetchall()
        result = []
        for r in rows:
            result.append({
                "platform": r["platform"],
                "profile_count": r["profile_count"],
                "first_date": r["first_date"],
                "last_date": r["last_date"],
                "bounding_box": {
                    "min_lat": round(r["min_lat"], 3) if r["min_lat"] is not None else None,
                    "max_lat": round(r["max_lat"], 3) if r["max_lat"] is not None else None,
                    "min_lon": round(r["min_lon"], 3) if r["min_lon"] is not None else None,
                    "max_lon": round(r["max_lon"], 3) if r["max_lon"] is not None else None,
                },
                "variables": ["temperature", "salinity", "pressure"],
                "avg_max_depth": round(r["avg_max_depth"], 1) if r["avg_max_depth"] is not None else 0.0,
            })
        return result
    finally:
        conn.close()


def float_summary(platform: str, db_path: Optional[str] = None) -> Optional[Dict[str, Any]]:
    """Detailed summary of a single float platform, including stats and last position."""
    conn = _get_db(db_path)
    try:
        # Base platform info
        sql_info = """
            SELECT 
                p.platform,
                COUNT(DISTINCT p.id) as profile_count,
                MIN(p.timestamp) as first_date,
                MAX(p.timestamp) as last_date,
                MIN(p.lat) as min_lat,
                MAX(p.lat) as max_lat,
                MIN(p.lon) as min_lon,
                MAX(p.lon) as max_lon,
                AVG(m_depth.max_p) as avg_max_depth
            FROM profiles p
            LEFT JOIN (
                SELECT profile_id, MAX(pressure) as max_p
                FROM measurements
                GROUP BY profile_id
            ) m_depth ON p.id = m_depth.profile_id
            WHERE p.platform = ?
            GROUP BY p.platform
        """
        row = conn.execute(sql_info, [platform]).fetchone()
        if not row:
            return None

        # Last known position
        sql_last = """
            SELECT lat, lon, timestamp 
            FROM profiles 
            WHERE platform = ? 
            ORDER BY timestamp DESC 
            LIMIT 1
        """
        last_row = conn.execute(sql_last, [platform]).fetchone()
        last_pos = dict(last_row) if last_row else None

        # Variable stats
        sql_stats = """
            SELECT 
                AVG(m.temperature) as mean_temp,
                MIN(m.temperature) as min_temp,
                MAX(m.temperature) as max_temp,
                AVG(m.salinity) as mean_sal,
                MIN(m.salinity) as min_sal,
                MAX(m.salinity) as max_sal,
                AVG(m.pressure) as mean_pres,
                MIN(m.pressure) as min_pres,
                MAX(m.pressure) as max_pres
            FROM measurements m
            JOIN profiles p ON m.profile_id = p.id
            WHERE p.platform = ?
        """
        stat_row = conn.execute(sql_stats, [platform]).fetchone()

        stats = {}
        if stat_row:
            if stat_row["mean_temp"] is not None:
                stats["temperature"] = {
                    "mean": round(stat_row["mean_temp"], 3),
                    "min": round(stat_row["min_temp"], 3),
                    "max": round(stat_row["max_temp"], 3),
                    "units": "°C",
                }
            if stat_row["mean_sal"] is not None:
                stats["salinity"] = {
                    "mean": round(stat_row["mean_sal"], 3),
                    "min": round(stat_row["min_sal"], 3),
                    "max": round(stat_row["max_sal"], 3),
                    "units": "PSU",
                }
            if stat_row["mean_pres"] is not None:
                stats["pressure"] = {
                    "mean": round(stat_row["mean_pres"], 3),
                    "min": round(stat_row["min_pres"], 3),
                    "max": round(stat_row["max_pres"], 3),
                    "units": "dbar",
                }

        return {
            "platform": row["platform"],
            "profile_count": row["profile_count"],
            "first_date": row["first_date"],
            "last_date": row["last_date"],
            "bounding_box": {
                "min_lat": round(row["min_lat"], 3) if row["min_lat"] is not None else None,
                "max_lat": round(row["max_lat"], 3) if row["max_lat"] is not None else None,
                "min_lon": round(row["min_lon"], 3) if row["min_lon"] is not None else None,
                "max_lon": round(row["max_lon"], 3) if row["max_lon"] is not None else None,
            },
            "last_position": last_pos,
            "avg_max_depth": round(row["avg_max_depth"], 1) if row["avg_max_depth"] is not None else 0.0,
            "stats": stats,
        }
    finally:
        conn.close()


def find_floats_near(lat: float, lon: float, radius_deg: float = 2.0,
                     date_window: Optional[Dict[str, Any]] = None,
                     db_path: Optional[str] = None) -> List[Dict[str, Any]]:
    """Find floats operating near coordinates, sorted by Haversine distance to their centroid."""
    conn = _get_db(db_path)
    try:
        sql = """
            SELECT 
                p.platform,
                COUNT(DISTINCT p.id) as profile_count,
                AVG(p.lat) as center_lat,
                AVG(p.lon) as center_lon,
                MIN(p.timestamp) as first_date,
                MAX(p.timestamp) as last_date
            FROM profiles p
            WHERE p.lat BETWEEN ? AND ? AND p.lon BETWEEN ? AND ?
        """
        params: List[Any] = [lat - radius_deg, lat + radius_deg, lon - radius_deg, lon + radius_deg]

        if date_window:
            from retrieval.query_engine import _date_bounds
            bounds = _date_bounds(
                date_window.get("year"), date_window.get("month"),
                date_window.get("year_end"), date_window.get("month_end")
            )
            if bounds:
                sql += " AND p.timestamp >= ? AND p.timestamp < ?"
                params.extend(bounds)

        sql += " GROUP BY p.platform"
        rows = conn.execute(sql, params).fetchall()

        results = []
        for r in rows:
            c_lat = r["center_lat"]
            c_lon = r["center_lon"]
            dist_km = _haversine_km(lat, lon, c_lat, c_lon)
            results.append({
                "platform": r["platform"],
                "profile_count": r["profile_count"],
                "center_lat": round(c_lat, 3),
                "center_lon": round(c_lon, 3),
                "distance_km": round(dist_km, 1),
                "first_date": r["first_date"],
                "last_date": r["last_date"],
            })

        # Order by closest haversine distance
        results.sort(key=lambda x: x["distance_km"])
        return results
    finally:
        conn.close()


def coverage_summary(db_path: Optional[str] = None) -> Dict[str, Any]:
    """Return overall data coverage stats: totals, temporal range, monthly & yearly distributions."""
    conn = _get_db(db_path)
    try:
        prof_row = conn.execute("""
            SELECT 
                COUNT(DISTINCT CASE WHEN EXISTS (SELECT 1 FROM measurements m WHERE m.profile_id = profiles.id) THEN id END) as total_profiles,
                COUNT(DISTINCT CASE WHEN EXISTS (SELECT 1 FROM measurements m WHERE m.profile_id = profiles.id) THEN platform END) as total_floats,
                MIN(timestamp) as date_start,
                MAX(timestamp) as date_end
            FROM profiles
        """).fetchone()

        total_meas = conn.execute("SELECT COUNT(*) FROM measurements").fetchone()[0]
        temp_meas = conn.execute("SELECT COUNT(*) FROM measurements WHERE temperature IS NOT NULL").fetchone()[0]
        sal_meas = conn.execute("SELECT COUNT(*) FROM measurements WHERE salinity IS NOT NULL").fetchone()[0]
        pres_meas = conn.execute("SELECT COUNT(*) FROM measurements WHERE pressure IS NOT NULL").fetchone()[0]

        # Monthly breakdown
        monthly_rows = conn.execute("""
            SELECT SUBSTR(timestamp, 1, 7) as ym, COUNT(*) as cnt
            FROM profiles
            WHERE timestamp IS NOT NULL
            GROUP BY ym
            ORDER BY ym
        """).fetchall()
        by_month = {r["ym"]: r["cnt"] for r in monthly_rows}

        # Yearly breakdown
        yearly_rows = conn.execute("""
            SELECT SUBSTR(timestamp, 1, 4) as y, COUNT(*) as cnt
            FROM profiles
            WHERE timestamp IS NOT NULL
            GROUP BY y
            ORDER BY y
        """).fetchall()
        by_year = {r["y"]: r["cnt"] for r in yearly_rows}

        record_row = conn.execute("SELECT COUNT(*) AS n FROM profiles").fetchone()
        return {
            "profile_records": record_row["n"] if record_row else 0,
            "total_profiles": prof_row["total_profiles"] if prof_row else 0,
            "total_floats": prof_row["total_floats"] if prof_row else 0,
            "total_measurements": total_meas,
            "date_start": prof_row["date_start"] if prof_row else None,
            "date_end": prof_row["date_end"] if prof_row else None,
            "variables": ["temperature", "salinity", "pressure"],
            "variable_counts": {
                "temperature": temp_meas,
                "salinity": sal_meas,
                "pressure": pres_meas,
            },
            "profiles_by_month": by_month,
            "profiles_by_year": by_year,
        }
    finally:
        conn.close()


def float_trajectory(platform: str, db_path: Optional[str] = None) -> List[Dict[str, Any]]:
    """Return chronologically ordered GPS drift trajectory for a float."""
    conn = _get_db(db_path)
    try:
        rows = conn.execute("""
            SELECT id as profile_id, platform, lat, lon, timestamp
            FROM profiles
            WHERE platform = ?
            ORDER BY timestamp ASC
        """, [platform]).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def trajectory_points(platform_id: Any = None, db_path: Optional[str] = None,
                      year: Optional[int] = None, month: Optional[int] = None,
                      year_end: Optional[int] = None, month_end: Optional[int] = None,
                      limit: int = MAX_CHART_POINTS) -> List[Dict[str, Any]]:
    """Trajectory points, optionally filtered by a *validated* float ID and dates.

    The float filter is applied only when ``platform_id`` is a well-formed
    7-digit ID; otherwise (None, malformed) no float filter is applied.
    Date bounds reuse query_engine's [start, end) logic. ``float_trajectory``
    is left unchanged for existing callers.
    """
    from retrieval.query_engine import _date_bounds  # local import avoids a cycle

    sql = "SELECT id as profile_id, platform, lat, lon, timestamp FROM profiles WHERE 1=1"
    params: List[Any] = []
    plat = validate_platform_id(platform_id)
    if plat is not None:
        sql += " AND platform = ?"
        params.append(plat)
    bounds = _date_bounds(year, month, year_end, month_end)
    if bounds:
        sql += " AND timestamp >= ? AND timestamp < ?"
        params.extend(bounds)
    sql += " ORDER BY timestamp ASC LIMIT ?"
    params.append(int(limit))
    conn = _get_db(db_path)
    try:
        return [dict(r) for r in conn.execute(sql, params).fetchall()]
    finally:
        conn.close()


def find_similar_profiles(profile_id: str, k: int = 5, db_path: Optional[str] = None) -> List[Dict[str, Any]]:
    """Find k most similar profiles to target profile based on temperature and salinity profiles.
    
    Computed using depth-binned Euclidean distance similarity (normalized score between 0.0 and 1.0).
    Presented as a profile similarity index, not a formal oceanographic assertion.
    """
    conn = _get_db(db_path)
    try:
        # 1. Fetch target profile measurements
        target_rows = conn.execute("""
            SELECT pressure, temperature, salinity
            FROM measurements
            WHERE profile_id = ? AND pressure IS NOT NULL
            ORDER BY pressure ASC
        """, [profile_id]).fetchall()

        if not target_rows:
            return []

        # Target profile metadata
        target_prof = conn.execute("SELECT lat, lon, timestamp, platform FROM profiles WHERE id = ?", [profile_id]).fetchone()
        if not target_prof:
            return []

        # Bin target into 50 dbar depth bins
        def _bin_profile(rows):
            bins = {}
            for r in rows:
                p = r["pressure"]
                bin_key = int(p // 50) * 50
                if bin_key not in bins:
                    bins[bin_key] = {"t": [], "s": []}
                if r["temperature"] is not None:
                    bins[bin_key]["t"].append(r["temperature"])
                if r["salinity"] is not None:
                    bins[bin_key]["s"].append(r["salinity"])
            
            binned = {}
            for bk, data in bins.items():
                t_avg = sum(data["t"]) / len(data["t"]) if data["t"] else None
                s_avg = sum(data["s"]) / len(data["s"]) if data["s"] else None
                binned[bk] = (t_avg, s_avg)
            return binned

        target_binned = _bin_profile(target_rows)

        # 2. Fetch all other candidate profiles
        candidates = conn.execute("""
            SELECT DISTINCT id, platform, lat, lon, timestamp
            FROM profiles
            LIMIT 300
        """).fetchall()

        scores = []
        for cand in candidates:
            cand_id = cand["id"]
            if cand_id == profile_id:
                continue

            cand_rows = conn.execute("""
                SELECT pressure, temperature, salinity
                FROM measurements
                WHERE profile_id = ? AND pressure IS NOT NULL
            """, [cand_id]).fetchall()

            if not cand_rows:
                continue

            cand_binned = _bin_profile(cand_rows)

            # Compare overlapping depth bins
            common_bins = set(target_binned.keys()) & set(cand_binned.keys())
            if not common_bins:
                continue

            diffs_t = []
            diffs_s = []
            for b in common_bins:
                tt, ts = target_binned[b]
                ct, cs = cand_binned[b]
                if tt is not None and ct is not None:
                    diffs_t.append((tt - ct) ** 2)
                if ts is not None and cs is not None:
                    diffs_s.append((ts - cs) ** 2)

            rmse_t = math.sqrt(sum(diffs_t) / len(diffs_t)) if diffs_t else 10.0
            rmse_s = math.sqrt(sum(diffs_s) / len(diffs_s)) if diffs_s else 5.0

            # Composite distance and similarity score (1 / (1 + dist))
            combined_dist = math.sqrt(rmse_t ** 2 + (rmse_s * 2.0) ** 2)
            similarity = 1.0 / (1.0 + combined_dist)

            scores.append({
                "profile_id": cand_id,
                "platform": cand["platform"],
                "lat": cand["lat"],
                "lon": cand["lon"],
                "timestamp": cand["timestamp"],
                "similarity_score": round(similarity, 3),
            })

        # Sort highest similarity first, return top k
        scores.sort(key=lambda x: x["similarity_score"], reverse=True)
        return scores[:k]
    finally:
        conn.close()
