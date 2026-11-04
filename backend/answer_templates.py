"""
FloatChat – Natural Language Answer Templates
=============================================
Zero-AI deterministic natural language generator.
Constructs clear, professional, scientific summaries from computed database results.
Guarantees 100% numerical fidelity: every number comes directly from the database/Python.
"""

from typing import Dict, Any, List
from config import VARIABLES, coverage_label


MONTH_NAMES = [
    "January", "February", "March", "April", "May", "June",
    "July", "August", "September", "October", "November", "December"
]


def _format_date_filter(filters: Dict[str, Any]) -> str:
    """Format human-readable date string from filter dict."""
    year = filters.get("year")
    year_end = filters.get("year_end")
    month = filters.get("month")
    month_end = filters.get("month_end")

    if year and year_end and year != year_end:
        start = f"{MONTH_NAMES[month - 1]} {year}" if month and 1 <= month <= 12 else str(year)
        end = f"{MONTH_NAMES[month_end - 1]} {year_end}" if month_end and 1 <= month_end <= 12 else str(year_end)
        return f"between {start} and {end}"

    if month and month_end and month != month_end:
        m1_name = MONTH_NAMES[month - 1] if 1 <= month <= 12 else str(month)
        m2_name = MONTH_NAMES[month_end - 1] if 1 <= month_end <= 12 else str(month_end)
        if year:
            return f"between {m1_name} and {m2_name} {year}"
        return f"between {m1_name} and {m2_name}"

    if month:
        m_name = MONTH_NAMES[month - 1] if 1 <= month <= 12 else str(month)
        if year:
            return f"in {m_name} {year}"
        return f"in {m_name} (across all available years)"

    if year and year_end and year != year_end:
        return f"between {year} and {year_end}"

    if year:
        return f"in {year}"

    return "across the recorded time period"


def _format_pressure_filter(filters: Dict[str, Any]) -> str:
    pmin = filters.get("pressure_min")
    pmax = filters.get("pressure_max")
    if pmin is not None and pmax is not None:
        return f" at depth {pmin:g}–{pmax:g} dbar"
    if pmin is not None:
        return f" at depths of {pmin:g} dbar or deeper"
    if pmax is not None:
        return f" at depths up to {pmax:g} dbar"
    return " at all depths"


def _format_region_filter(filters: Dict[str, Any]) -> str:
    region = filters.get("region")
    if region and isinstance(region, dict):
        lat = region.get("lat")
        lon = region.get("lon")
        rad = region.get("radius_deg", 2.0)
        return f" near ({lat:.2f}°, {lon:.2f}° ±{rad:g}°)"
    named = filters.get("named_region")
    if named:
        return f" in the {named}"
    if filters.get("platform_id"):
        return f" for float {filters['platform_id']}"
    return " in the Bay of Bengal"


def build_answer(question: str, db_result: Dict[str, Any]) -> str:
    """Build a natural language answer strictly from db_result without calling an LLM."""
    if not db_result:
        return (
            "No data was returned for your query. The dataset covers ARGO float observations "
            f"in the Bay of Bengal ({coverage_label()}). Please verify your filters or date range."
        )

    task = db_result.get("task", "stat")

    # 1. Handle Conceptual Questions
    if task == "concept" or db_result.get("is_conceptual"):
        ans = db_result.get("conceptual_answer") or "Conceptual information regarding ARGO floats and oceanography."
        sources = db_result.get("rag_sources")
        if sources and isinstance(sources, list):
            sources_str = ", ".join(sources)
            return f"{ans}\n\nSources: {sources_str}"
        return ans

    # 2. Handle Discovery Tasks
    if task == "coverage":
        return _build_coverage_answer(db_result)
    if task == "discover_floats":
        return _build_discover_floats_answer(db_result)
    if task == "float_detail":
        return _build_float_detail_answer(db_result)
    if task == "trajectory":
        return _build_trajectory_answer(db_result)
    if task == "similar_profiles":
        return _build_similar_profiles_answer(db_result)

    # 3. Handle Standard Stat / Comparison Queries
    count = db_result.get("count", 0)
    variable = db_result.get("variable", "temperature")
    var_meta = VARIABLES.get(variable, {"units": ""})
    units = db_result.get("units") or var_meta.get("units", "")
    filters = db_result.get("filters", {})
    stat = db_result.get("stat")
    compare_groups = db_result.get("compare_groups")

    time_str = _format_date_filter(filters)
    depth_str = _format_pressure_filter(filters)
    region_str = _format_region_filter(filters)

    # Empty result
    if count == 0 and not compare_groups:
        return (
            f"No matching {variable} observations were found {time_str}{depth_str}{region_str}. "
            f"The database currently holds ARGO float profiles for the Bay of Bengal. "
            f"Try broadening your depth range or searching across {coverage_label()}."
        )

    # Comparison query
    if compare_groups:
        return _build_compare_answer(compare_groups, variable, units, region_str, depth_str)

    # Specific statistic requested
    if stat and isinstance(stat, dict):
        st_type = stat.get("stat")
        val = stat.get("value")
        if st_type == "avg":
            return f"The average {variable} {time_str}{depth_str}{region_str} was {val:.3f} {units} across {count:,} observations."
        elif st_type == "max":
            return f"The maximum {variable} recorded {time_str}{depth_str}{region_str} was {val:.3f} {units} across {count:,} observations."
        elif st_type == "min":
            return f"The minimum {variable} recorded {time_str}{depth_str}{region_str} was {val:.3f} {units} across {count:,} observations."
        elif st_type == "count":
            return f"There were {count:,} {variable} observations recorded {time_str}{depth_str}{region_str}."

    # General summary when no specific stat was requested
    rows = db_result.get("rows", [])
    vals = [r.get(variable) for r in rows if r.get(variable) is not None]
    if vals:
        mean_val = sum(vals) / len(vals)
        min_val = min(vals)
        max_val = max(vals)
        return (
            f"Based on {count:,} observations {time_str}{depth_str}{region_str}, "
            f"the {variable} averaged {mean_val:.3f} {units} "
            f"(minimum: {min_val:.3f} {units}, maximum: {max_val:.3f} {units})."
        )

    return f"Retrieved {count:,} records {time_str}{depth_str}{region_str}."


def _build_compare_answer(groups: List[Dict[str, Any]], variable: str, units: str, region_str: str, depth_str: str = "") -> str:
    valid_groups = [g for g in groups if g.get("count", 0) > 0]
    empty_groups = [g for g in groups if g.get("count", 0) == 0]
    if not valid_groups:
        return f"No observations found for the comparison periods{region_str}."

    lines = []
    lines.append(f"Comparison of {variable} ({units}){depth_str}{region_str}:")
    for g in valid_groups:
        lbl = g.get("label", "Period")
        cnt = g.get("count", 0)
        s = g.get("stat")
        if s and s.get("value") is not None:
            st_name = s.get("stat", "avg")
            lines.append(f"• {lbl}: {st_name} = {s['value']:.3f} {units} ({cnt:,} observations)")
        else:
            lines.append(f"• {lbl}: {cnt:,} observations")

    for g in empty_groups:   # never drop a requested period silently
        lines.append(f"• {g.get('label', 'Period')}: no observations in the dataset (coverage: {coverage_label()})")

    if len(valid_groups) == 2:
        s1 = valid_groups[0].get("stat", {}).get("value")
        s2 = valid_groups[1].get("stat", {}).get("value")
        if s1 is not None and s2 is not None:
            diff = s2 - s1
            lines.append(f"The difference ({valid_groups[1]['label']} vs {valid_groups[0]['label']}) is {diff:+.3f} {units}.")

    return "\n".join(lines)


def _build_coverage_answer(result: Dict[str, Any]) -> str:
    cov = result.get("coverage", {})
    total_prof = cov.get("total_profiles", 0)
    total_meas = cov.get("total_measurements", 0)
    total_floats = cov.get("total_floats", 0)
    dstart = cov.get("date_start", "N/A")
    dend = cov.get("date_end", "N/A")
    vars_avail = cov.get("variables", ["temperature", "salinity", "pressure"])

    records = cov.get("profile_records") or 0
    no_meas = (f" ({records:,} profile records in the database; {records - total_prof:,} have no measurement rows)"
               if records > total_prof else "")
    return (
        f"ARGO Data Coverage Overview (Bay of Bengal):\n"
        f"• Profiles with measurements: {total_prof:,} across {total_floats} distinct floats{no_meas}\n"
        f"• Total Measurement Levels: {total_meas:,}\n"
        f"• Observation Window: {dstart[:10] if dstart else 'N/A'} to {dend[:10] if dend else 'N/A'}\n"
        f"• Measured Parameters: {', '.join(vars_avail)}"
    )


def _build_discover_floats_answer(result: Dict[str, Any]) -> str:
    floats = result.get("floats", [])
    count = len(floats)
    if count == 0:
        return (
            "No ARGO floats matched the specified criteria. "
            f"The database contains floats in the Bay of Bengal for {coverage_label()}. "
            "Try querying without strict location or year filters."
        )

    preview = floats[:5]
    summary_items = []
    for f in preview:
        pid = f.get("platform")
        cnt = f.get("profile_count", 0)
        d_min = (f.get("first_date") or "")[:10]
        d_max = (f.get("last_date") or "")[:10]
        summary_items.append(f"• Float {pid}: {cnt} profiles ({d_min} to {d_max})")

    more = f"\n... and {count - 5} more floats shown in the table below." if count > 5 else ""
    return (
        f"Discovered {count} ARGO float(s) in the Bay of Bengal:\n"
        + "\n".join(summary_items) + more
    )


def _build_float_detail_answer(result: Dict[str, Any]) -> str:
    f = result.get("float_summary")
    if not f:
        pid = result.get("platform_id", "Unknown")
        return f"Float {pid} was not found in the database. Please verify the 7-digit WMO float identifier."

    pid = f.get("platform")
    cnt = f.get("profile_count", 0)
    d_start = (f.get("first_date") or "")[:10]
    d_end = (f.get("last_date") or "")[:10]
    max_d = f.get("avg_max_depth", 0)
    last_pos = f.get("last_position", {})

    pos_str = f"({last_pos.get('lat', 0):.2f}°N, {last_pos.get('lon', 0):.2f}°E)" if last_pos else "N/A"
    
    stats_str = ""
    stats = f.get("stats", {})
    if stats:
        t_stat = stats.get("temperature", {})
        s_stat = stats.get("salinity", {})
        t_avg = t_stat.get("mean")
        s_avg = s_stat.get("mean")
        if t_avg is not None or s_avg is not None:
            stats_str = f"\n• Mean Temperature: {t_avg:.2f} °C | Mean Salinity: {s_avg:.2f} PSU" if t_avg and s_avg else ""

    return (
        f"ARGO Float {pid} Profile Summary:\n"
        f"• Total Profiles: {cnt}\n"
        f"• Active Period: {d_start} to {d_end}\n"
        f"• Last Known Position: {pos_str}\n"
        f"• Average Max Depth: {max_d:.1f} dbar"
        f"{stats_str}"
    )


def _build_trajectory_answer(result: Dict[str, Any]) -> str:
    traj = result.get("trajectory", [])
    pid = result.get("platform_id", "Unknown")
    if not traj:
        return f"No trajectory points found for float {pid}."

    start_pt = traj[0]
    end_pt = traj[-1]
    return (
        f"Drift Trajectory for Float {pid}:\n"
        f"• Tracked {len(traj)} profiles from {start_pt.get('timestamp', '')[:10]} to {end_pt.get('timestamp', '')[:10]}\n"
        f"• Initial Position: ({start_pt.get('lat', 0):.2f}°, {start_pt.get('lon', 0):.2f}°)\n"
        f"• Final Position: ({end_pt.get('lat', 0):.2f}°, {end_pt.get('lon', 0):.2f}°)"
    )


def _build_similar_profiles_answer(result: Dict[str, Any]) -> str:
    target_id = result.get("target_profile_id", "Unknown")
    sims = result.get("similar_profiles", [])
    if not sims:
        return f"No similar profiles found for profile {target_id}."

    lines = [f"Profiles with highest physical similarity to {target_id} (based on vertical T/S profiles):"]
    for s in sims[:5]:
        pid = s.get("profile_id")
        score = s.get("similarity_score", 0)
        dt = (s.get("timestamp") or "")[:10]
        lines.append(f"• Profile {pid} ({dt}): Similarity score {score:.3f}")

    return "\n".join(lines)
