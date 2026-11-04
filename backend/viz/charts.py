"""
FloatChat – Visualisation Layer
================================
Builds interactive, modern Plotly charts serialized to JSON for the frontend.
Supports:
  - Vertical depth profiles (reversed y-axis, <= 15 profiles, clean traces)
  - Timeseries trends with units
  - Histograms and distribution plots
  - Geographic profile maps & float summary maps
  - Float drift trajectories (line + points)
  - Comparison charts (overlaid distributions / group averages)
  - Depth-vs-time Hovmöller section plots
  - Coverage charts (monthly profiles stacked by year)
  - Similar profiles comparison overlay
  - Downsampling to <= 4,000 points
"""

import logging
from typing import Optional, List, Any

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import plotly.io as pio

from config import VARIABLES, MAX_CHART_POINTS

logger = logging.getLogger("floatchat.viz")

# Custom dark theme styling tokens
BG_COLOR = "#0f172a"
PAPER_COLOR = "#1e293b"
GRID_COLOR = "#334155"
TEXT_COLOR = "#f8fafc"
ACCENT_COLORS = ["#38bdf8", "#818cf8", "#34d399", "#fbbf24", "#f43f5e", "#a855f7", "#ec4899", "#06b6d4"]


def _downsample(df: pd.DataFrame, max_points: int = MAX_CHART_POINTS) -> pd.DataFrame:
    """Downsample DataFrame if row count exceeds max_points."""
    if len(df) > max_points:
        return df.sample(n=max_points, random_state=42).sort_index()
    return df


def rows_to_df(rows: list) -> pd.DataFrame:
    """Convert row dicts to pandas DataFrame with parsed timestamps."""
    if not rows:
        return pd.DataFrame()
    df = pd.DataFrame(rows)
    if "timestamp" in df.columns:
        df["timestamp"] = pd.to_datetime(df["timestamp"], errors="coerce")
    return df


def _apply_theme(fig: go.Figure, title: str, x_title: str = "", y_title: str = "") -> go.Figure:
    """Apply unified modern dark aesthetic to Plotly figures."""
    fig.update_layout(
        title={
            "text": title,
            "font": {"size": 16, "color": TEXT_COLOR, "family": "Inter, system-ui, sans-serif"},
            "x": 0.05,
            "xanchor": "left"
        },
        paper_bgcolor=PAPER_COLOR,
        plot_bgcolor=BG_COLOR,
        font={"color": TEXT_COLOR, "family": "Inter, system-ui, sans-serif"},
        margin=dict(l=55, r=30, t=55, b=45),
        hovermode="closest",
        legend=dict(
            bgcolor="rgba(30, 41, 59, 0.7)",
            bordercolor=GRID_COLOR,
            borderwidth=1,
            font={"size": 11, "color": TEXT_COLOR},
        ),
        xaxis=dict(
            title=x_title,
            gridcolor=GRID_COLOR,
            zerolinecolor=GRID_COLOR,
            showgrid=True,
        ),
        yaxis=dict(
            title=y_title,
            gridcolor=GRID_COLOR,
            zerolinecolor=GRID_COLOR,
            showgrid=True,
        ),
    )
    return fig


def _depth_note(df: pd.DataFrame) -> str:
    """' | 0-50 dbar' taken from the plotted data, so charts never hide the depth range they mix."""
    try:
        if "pressure" in df.columns:
            p = df["pressure"].dropna()
            if not p.empty:
                return f" | {p.min():.0f}\u2013{p.max():.0f} dbar"
    except Exception:
        pass
    return ""


MAX_PROFILE_TRACES = 15


def _even_indices(n: int, q: int) -> List[int]:
    """q indices spread evenly over range(n) (q <= n); the middle one when q == 1."""
    if q >= n:
        return list(range(n))
    if q == 1:
        return [n // 2]
    return sorted({round(i * (n - 1) / (q - 1)) for i in range(q)})


def _pick_spread_profiles(df: pd.DataFrame, profile_col: str, k: int = MAX_PROFILE_TRACES) -> List[Any]:
    """Choose k profile ids spread across floats AND dates, deterministically.

    Floats share the k slots as evenly as possible (extra slots go to floats with more profiles,
    ties broken by float id); inside a float the profiles picked are evenly spaced in time. When
    there are more floats than slots, floats are themselves taken evenly spaced in id order.
    Plain row order is never used, so a single float cannot dominate the chart.
    """
    cols = [profile_col] + [c for c in ("platform", "timestamp") if c in df.columns and c != profile_col]
    meta = df[cols].drop_duplicates(profile_col).copy()
    if "platform" not in meta.columns:
        meta["platform"] = ""
    if "timestamp" not in meta.columns:
        meta["timestamp"] = pd.NaT
    meta["platform"] = meta["platform"].astype(str)
    meta = meta.sort_values(["platform", "timestamp", profile_col], na_position="last")
    by_float = {plat: grp[profile_col].tolist() for plat, grp in meta.groupby("platform", sort=True)}
    floats = sorted(by_float)
    if len(floats) > k:
        floats = [floats[i] for i in _even_indices(len(floats), k)]
    quota = {f: 1 for f in floats}
    spare = k - len(floats)
    while spare > 0:
        grew = False
        for f in sorted(floats, key=lambda f: (-(len(by_float[f]) - quota[f]), f)):
            if spare > 0 and quota[f] < len(by_float[f]):
                quota[f] += 1
                spare -= 1
                grew = True
        if not grew:
            break
    chosen: List[Any] = []
    for f in floats:
        ids = by_float[f]
        chosen.extend(ids[i] for i in _even_indices(len(ids), quota[f]))
    return chosen


def make_depth_profile(rows: list, variable: str = "temperature") -> Optional[str]:
    """Depth profile chart: reversed y-axis, at most 15 profiles as distinct traces."""
    df = rows_to_df(rows)
    if df.empty or variable not in df.columns or "pressure" not in df.columns:
        return None

    df = df.dropna(subset=[variable, "pressure"])
    if df.empty:
        return None

    var_meta = VARIABLES.get(variable, {"units": ""})
    units = var_meta.get("units", "")

    # Group by profile id; select at most 15 profiles
    profile_col = "id" if "id" in df.columns else ("platform" if "platform" in df.columns else None)
    trunc_note = ""
    if profile_col:
        unique_profs = df[profile_col].unique()
        if len(unique_profs) > MAX_PROFILE_TRACES:
            chosen = _pick_spread_profiles(df, profile_col, MAX_PROFILE_TRACES)
            df = df[df[profile_col].isin(chosen)]
            trunc_note = f" \u2013 showing {MAX_PROFILE_TRACES} of {len(unique_profs)} profiles"

    df = _downsample(df)
    fig = go.Figure()

    if profile_col:
        for idx, (pid, group) in enumerate(df.groupby(profile_col)):
            sorted_g = group.sort_values(by="pressure")
            color = ACCENT_COLORS[idx % len(ACCENT_COLORS)]
            fig.add_trace(go.Scatter(
                x=sorted_g[variable],
                y=sorted_g["pressure"],
                mode="lines+markers",
                name=str(pid),
                line=dict(width=2, color=color),
                marker=dict(size=4),
                hovertemplate=f"Depth: %{{y:.1f}} dbar<br>{variable.capitalize()}: %{{x:.2f}} {units}<br>Profile: {pid}<extra></extra>"
            ))
    else:
        sorted_df = df.sort_values(by="pressure")
        fig.add_trace(go.Scatter(
            x=sorted_df[variable],
            y=sorted_df["pressure"],
            mode="markers",
            marker=dict(size=4, color="#38bdf8"),
            hovertemplate=f"Depth: %{{y:.1f}} dbar<br>{variable.capitalize()}: %{{x:.2f}} {units}<extra></extra>"
        ))

    _apply_theme(
        fig,
        title=f"{variable.capitalize()} Vertical Depth Profile ({units}){trunc_note}",
        x_title=f"{variable.capitalize()} ({units})",
        y_title="Pressure / Depth (dbar)"
    )
    fig.update_yaxes(autorange="reversed")
    return pio.to_json(fig)


def make_timeseries(rows: list, variable: str = "temperature") -> Optional[str]:
    """Timeseries trend chart over time with aggregation."""
    df = rows_to_df(rows)
    if df.empty or variable not in df.columns or "timestamp" not in df.columns:
        return None

    df = df.dropna(subset=[variable, "timestamp"])
    if df.empty:
        return None

    var_meta = VARIABLES.get(variable, {"units": ""})
    units = var_meta.get("units", "")

    # Aggregate daily average
    df["date"] = df["timestamp"].dt.date
    daily = df.groupby("date", as_index=False)[variable].agg(["mean", "min", "max", "count"]).reset_index()

    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=daily["date"],
        y=daily["mean"],
        mode="lines+markers",
        name=f"Mean {variable.capitalize()}",
        line=dict(color="#38bdf8", width=2.5),
        marker=dict(size=5),
        hovertemplate=f"Date: %{{x}}<br>Mean: %{{y:.2f}} {units}<extra></extra>"
    ))

    _apply_theme(
        fig,
        title=f"{variable.capitalize()} \u2013 daily mean over time ({units}){_depth_note(df)}",
        x_title="Date",
        y_title=f"{variable.capitalize()} ({units})"
    )
    return pio.to_json(fig)


def make_distribution(rows: list, variable: str = "temperature") -> Optional[str]:
    """Distribution histogram of measurements."""
    df = rows_to_df(rows)
    if df.empty or variable not in df.columns:
        return None

    df = df.dropna(subset=[variable])
    if df.empty:
        return None

    var_meta = VARIABLES.get(variable, {"units": ""})
    units = var_meta.get("units", "")
    df = _downsample(df)

    fig = px.histogram(
        df,
        x=variable,
        nbins=40,
        color_discrete_sequence=["#818cf8"],
        labels={variable: f"{variable.capitalize()} ({units})"}
    )
    _apply_theme(
        fig,
        title=f"Distribution of {variable.capitalize()} ({units}){_depth_note(df)}",
        x_title=f"{variable.capitalize()} ({units})",
        y_title="Observation Count"
    )
    return pio.to_json(fig)


def make_map(rows: list) -> Optional[str]:
    """Map of profiling locations in the Bay of Bengal."""
    df = rows_to_df(rows)
    if df.empty or "lat" not in df.columns or "lon" not in df.columns:
        return None

    df_unique = df.drop_duplicates(subset=["id"]) if "id" in df.columns else df
    df_unique = _downsample(df_unique, 1000)

    fig = px.scatter_geo(
        df_unique,
        lat="lat",
        lon="lon",
        hover_name="id" if "id" in df_unique.columns else None,
        hover_data={"platform": True, "lat": ":.2f", "lon": ":.2f"},
        color_discrete_sequence=["#38bdf8"],
    )
    fig.update_geos(
        center={"lat": 13.0, "lon": 88.0},
        projection_scale=4.5,
        showland=True,
        landcolor="#1e293b",
        showocean=True,
        oceancolor="#0f172a",
        showlakes=True,
        lakecolor="#0f172a",
        showcountries=True,
        countrycolor="#475569",
    )
    fig.update_layout(
        title={"text": "ARGO Float Profile Locations (Bay of Bengal)", "font": {"color": TEXT_COLOR, "size": 16}},
        paper_bgcolor=PAPER_COLOR,
        font={"color": TEXT_COLOR},
        margin=dict(l=10, r=10, t=45, b=10)
    )
    return pio.to_json(fig)


def make_comparison(compare_groups: list, variable: str = "temperature") -> Optional[str]:
    """Compare groups via overlaid distributions and summary statistics."""
    if not compare_groups:
        return None

    var_meta = VARIABLES.get(variable, {"units": ""})
    units = var_meta.get("units", "")

    dfs = []
    for g in compare_groups:
        if g.get("count", 0) == 0:
            continue
        gdf = rows_to_df(g.get("rows", []))
        if not gdf.empty and variable in gdf.columns:
            gdf["Group"] = g.get("label", "Group")
            dfs.append(gdf)

    if not dfs:
        return None

    combined = pd.concat(dfs, ignore_index=True)
    combined = _downsample(combined)

    fig = px.histogram(
        combined,
        x=variable,
        color="Group",
        barmode="overlay",
        opacity=0.6,
        color_discrete_sequence=ACCENT_COLORS,
        labels={variable: f"{variable.capitalize()} ({units})"}
    )
    _apply_theme(
        fig,
        title=f"{variable.capitalize()} Comparison Across Periods ({units}){_depth_note(combined)}",
        x_title=f"{variable.capitalize()} ({units})",
        y_title="Observation Count"
    )
    return pio.to_json(fig)


def make_trajectory(trajectory_points: list, platform: Optional[str] = None) -> Optional[str]:
    """Render GPS drift trajectory of a float over time."""
    if not trajectory_points:
        return None

    df = pd.DataFrame(trajectory_points)
    if df.empty or "lat" not in df.columns or "lon" not in df.columns:
        return None

    plat_label = platform or (df["platform"].iloc[0] if "platform" in df.columns else "ARGO Float")

    fig = go.Figure()
    fig.add_trace(go.Scattergeo(
        lat=df["lat"],
        lon=df["lon"],
        mode="lines+markers",
        name=f"Float {plat_label}",
        line=dict(width=3, color="#38bdf8"),
        marker=dict(size=6, color="#f43f5e", symbol="circle"),
        text=[f"Profile: {r.get('profile_id', '')}<br>Date: {r.get('timestamp', '')[:10]}" for _, r in df.iterrows()],
        hoverinfo="text+lat+lon"
    ))

    # Mark start and end points
    fig.add_trace(go.Scattergeo(
        lat=[df["lat"].iloc[0]],
        lon=[df["lon"].iloc[0]],
        mode="markers+text",
        marker=dict(size=10, color="#34d399", symbol="star"),
        name="Start",
        text=["Start"],
        textposition="top center"
    ))
    fig.add_trace(go.Scattergeo(
        lat=[df["lat"].iloc[-1]],
        lon=[df["lon"].iloc[-1]],
        mode="markers+text",
        marker=dict(size=10, color="#f43f5e", symbol="diamond"),
        name="Latest",
        text=["End"],
        textposition="top center"
    ))

    c_lat = float(df["lat"].mean())
    c_lon = float(df["lon"].mean())

    fig.update_geos(
        center={"lat": c_lat, "lon": c_lon},
        projection_scale=8.0,
        showland=True,
        landcolor="#1e293b",
        showocean=True,
        oceancolor="#0f172a",
        showcountries=True,
        countrycolor="#475569",
    )
    fig.update_layout(
        title={"text": f"Drift Trajectory for Float {plat_label}", "font": {"color": TEXT_COLOR, "size": 16}},
        paper_bgcolor=PAPER_COLOR,
        font={"color": TEXT_COLOR},
        margin=dict(l=10, r=10, t=45, b=10)
    )
    return pio.to_json(fig)


def make_coverage_chart(coverage_data: dict) -> Optional[str]:
    """Monthly profiles chart grouped/stacked by year."""
    by_month = coverage_data.get("profiles_by_month", {})
    if not by_month:
        return None

    items = sorted(by_month.items())
    months = [k for k, _ in items]
    counts = [v for _, v in items]

    fig = go.Figure(data=[
        go.Bar(
            x=months,
            y=counts,
            marker_color="#818cf8",
            hovertemplate="Month: %{x}<br>Profiles: %{y:,}<extra></extra>"
        )
    ])
    _apply_theme(
        fig,
        title="ARGO Monthly Profile Coverage (Bay of Bengal)",
        x_title="Year-Month",
        y_title="Profile Count"
    )
    return pio.to_json(fig)


def make_floats_map(floats: list) -> Optional[str]:
    """Map of all discovered floats colored by profile count."""
    if not floats:
        return None

    df = pd.DataFrame(floats)
    if df.empty or "bounding_box" not in df.columns:
        return None

    # Centroid lat/lon
    df["lat"] = df["bounding_box"].apply(lambda b: (b.get("min_lat", 0) + b.get("max_lat", 0)) / 2.0 if b else 0)
    df["lon"] = df["bounding_box"].apply(lambda b: (b.get("min_lon", 0) + b.get("max_lon", 0)) / 2.0 if b else 0)

    fig = px.scatter_geo(
        df,
        lat="lat",
        lon="lon",
        size="profile_count",
        color="profile_count",
        hover_name="platform",
        hover_data={"profile_count": True, "avg_max_depth": True, "lat": False, "lon": False},
        color_continuous_scale="Viridis",
    )
    fig.update_geos(
        center={"lat": 13.0, "lon": 88.0},
        projection_scale=4.5,
        showland=True,
        landcolor="#1e293b",
        showocean=True,
        oceancolor="#0f172a",
        showcountries=True,
        countrycolor="#475569",
    )
    fig.update_layout(
        title={"text": f"Active ARGO Floats ({len(floats)} floats discovered)", "font": {"color": TEXT_COLOR, "size": 16}},
        paper_bgcolor=PAPER_COLOR,
        font={"color": TEXT_COLOR},
        margin=dict(l=10, r=10, t=45, b=10)
    )
    return pio.to_json(fig)


def make_similar_profiles_overlay(target_profile_id: str, similar_profiles: list, db_path: Optional[str] = None) -> Optional[str]:
    """Overlay target profile vertical temperature curve against top similar profiles."""
    import sqlite3
    from config import DB_PATH
    db_file = db_path or str(DB_PATH)

    if not similar_profiles:
        return None

    profile_ids = [target_profile_id] + [p["profile_id"] for p in similar_profiles[:4]]

    try:
        conn = sqlite3.connect(db_file)
        conn.row_factory = sqlite3.Row
        placeholders = ",".join(["?"] * len(profile_ids))
        rows = conn.execute(f"""
            SELECT profile_id, pressure, temperature, salinity
            FROM measurements
            WHERE profile_id IN ({placeholders}) AND pressure IS NOT NULL AND temperature IS NOT NULL
            ORDER BY pressure ASC
        """, profile_ids).fetchall()
        conn.close()
    except Exception:
        return None

    if not rows:
        return None

    df = pd.DataFrame([dict(r) for r in rows])
    fig = go.Figure()

    for idx, (pid, grp) in enumerate(df.groupby("profile_id")):
        is_target = (pid == target_profile_id)
        name_label = f"Target: {pid}" if is_target else f"Match: {pid}"
        color = "#f43f5e" if is_target else ACCENT_COLORS[idx % len(ACCENT_COLORS)]
        width = 3.5 if is_target else 1.8

        fig.add_trace(go.Scatter(
            x=grp["temperature"],
            y=grp["pressure"],
            mode="lines",
            name=name_label,
            line=dict(color=color, width=width, dash="solid" if is_target else "dot"),
            hovertemplate=f"{name_label}<br>Depth: %{{y:.1f}} dbar<br>Temp: %{{x:.2f}} °C<extra></extra>"
        ))

    _apply_theme(
        fig,
        title=f"Vertical Temperature Comparison – Profile {target_profile_id} vs Similar Matches",
        x_title="Temperature (°C)",
        y_title="Pressure / Depth (dbar)"
    )
    fig.update_yaxes(autorange="reversed")
    return pio.to_json(fig)


def pick_chart(chart_type: str, rows: list, variable: str = "temperature",
               compare_groups: Optional[list] = None,
               extra_data: Optional[dict] = None) -> Optional[str]:
    """Select and build the appropriate chart based on intent and payload."""
    extra_data = extra_data or {}

    if chart_type == "trajectory":
        return make_trajectory(extra_data.get("trajectory", rows), extra_data.get("platform"))
    if chart_type == "coverage":
        return make_coverage_chart(extra_data.get("coverage", {}))
    if chart_type == "floats_map":
        return make_floats_map(extra_data.get("floats", []))
    if chart_type == "similar_profiles":
        return make_similar_profiles_overlay(extra_data.get("target_profile_id", ""), extra_data.get("similar_profiles", []))
    if chart_type == "compare" and compare_groups:
        return make_comparison(compare_groups, variable)
    if chart_type == "map":
        return make_map(rows)
    if chart_type == "distribution":
        return make_distribution(rows, variable)
    if chart_type == "timeseries":
        return make_timeseries(rows, variable)
    if rows:
        return make_depth_profile(rows, variable)
    return None
