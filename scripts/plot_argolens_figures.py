"""Generate scientific figures for ArgoLens manuscript.

Produces:
  1. figures/fig_blt_seasonal.png - Seasonal Barrier Layer Thickness in the Bay of Bengal (2023-2024).
  2. figures/fig_ts_watermass.png - Temperature-Salinity (T-S) diagram colored by heuristic water mass with isopycnals.
"""
import os
import sqlite3
import sys
from pathlib import Path

# Ensure Matplotlib config dir is writable in sandbox
os.environ["MPLCONFIGDIR"] = "/tmp/matplotlib" if os.name != "nt" else os.path.join(os.environ.get("TEMP", "C:/tmp"), "mpl_config")
os.makedirs(os.environ["MPLCONFIGDIR"], exist_ok=True)

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "backend"))

from retrieval.dive_profile import build_dive_profile, classify_water_mass, potential_density_unesco

DB_PATH = ROOT / "backend" / "floatchat.db"
FIG_DIR = ROOT / "figures"
FIG_DIR.mkdir(parents=True, exist_ok=True)


def plot_seasonal_blt():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row

    profiles = conn.execute("""
        SELECT id, platform, lat, lon, timestamp,
        CASE 
            WHEN strftime('%m', timestamp) IN ('03', '04', '05') THEN 'Spring (MAM)'
            WHEN strftime('%m', timestamp) IN ('06', '07', '08', '09') THEN 'Summer Monsoon (JJAS)'
            WHEN strftime('%m', timestamp) IN ('10', '11') THEN 'Post-Monsoon (ON)'
            WHEN strftime('%m', timestamp) IN ('12', '01', '02') THEN 'Winter (DJF)'
        END as season
        FROM profiles
        ORDER BY timestamp ASC
    """).fetchall()

    seasons = ["Spring (MAM)", "Summer Monsoon (JJAS)", "Post-Monsoon (ON)", "Winter (DJF)"]
    by_season = {s: [] for s in seasons}
    for p in profiles:
        s = p["season"]
        if s in by_season:
            by_season[s].append(p)

    blt_data = {}
    for s in seasons:
        blts = []
        for p in by_season[s]:
            rows = conn.execute("""
                SELECT pressure, temperature, salinity, temp_qc, sal_qc
                FROM measurements
                WHERE profile_id = ?
                  AND (temp_qc IS NULL OR temp_qc IN (1, 2, 5, 8))
                  AND (sal_qc IS NULL OR sal_qc IN (1, 2, 5, 8))
                  AND pressure IS NOT NULL
                ORDER BY pressure ASC
            """, (p["id"],)).fetchall()
            if not rows:
                continue

            valid = [r for r in rows if r["temperature"] is not None and r["salinity"] is not None]
            # Near-surface qualification: level with valid T and S at p <= 15 dbar
            surf = [r for r in valid if r["pressure"] <= 15.0]
            if not surf:
                continue

            dive = build_dive_profile(rows, p["lat"])
            mld_rho = dive.get("mixed_layer_depth_density")
            mld_t = dive.get("mixed_layer_depth")
            blt = dive.get("barrier_layer_thickness")
            if mld_rho is not None and mld_t is not None and blt is not None:
                blts.append(blt)
        blt_data[s] = blts

    labels = [
        f"Spring (MAM)\n(n={len(blt_data['Spring (MAM)'])})",
        f"Summer (JJAS)\n(n={len(blt_data['Summer Monsoon (JJAS)'])})",
        f"Post-Monsoon (ON)\n(n={len(blt_data['Post-Monsoon (ON)'])})",
        f"Winter (DJF)\n(n={len(blt_data['Winter (DJF)'])})"
    ]
    plot_series = [blt_data[s] for s in seasons]

    fig, ax = plt.subplots(figsize=(7, 4.5), dpi=300)
    box = ax.boxplot(
        plot_series,
        tick_labels=labels,
        patch_artist=True,
        showfliers=False,  # outliers hidden as requested
        medianprops=dict(color="#b2182b", linewidth=2.0),
        boxprops=dict(facecolor="#e0f3f8", color="#2166ac", linewidth=1.2),
        whiskerprops=dict(color="#2166ac", linewidth=1.2),
        capprops=dict(color="#2166ac", linewidth=1.2)
    )

    # Annotate medians
    for i, s in enumerate(seasons):
        med = float(np.median(blt_data[s]))
        q25, q75 = float(np.percentile(blt_data[s], 25)), float(np.percentile(blt_data[s], 75))
        ax.text(i + 1, med + 1.2, f"{med:.1f} dbar\n[{q25:.1f}–{q75:.1f}]",
                horizontalalignment='center', size=8.5, weight='bold', color='#2b2b2b')

    ax.set_ylabel("Barrier Layer Thickness (dbar)", fontsize=10, weight='bold')
    ax.set_title("Seasonal Barrier Layer Thickness in the Bay of Bengal (2023–2024)", fontsize=11, weight='bold', pad=12)
    ax.grid(axis='y', linestyle='--', alpha=0.5)
    ax.set_ylim(-1, 55)

    out_path = FIG_DIR / "fig_blt_seasonal.png"
    plt.tight_layout()
    plt.savefig(out_path, dpi=300)
    plt.close()
    print(f"Saved {out_path}")


def plot_ts_diagram():
    conn = sqlite3.connect(DB_PATH)
    rows = conn.execute("""
        SELECT temperature, salinity, pressure
        FROM measurements
        WHERE temperature IS NOT NULL AND salinity IS NOT NULL AND pressure IS NOT NULL
    """).fetchall()

    temps = []
    sals = []
    classes = []
    for t, s, p in rows:
        temps.append(t)
        sals.append(s)
        classes.append(classify_water_mass(t, s, p))

    temps = np.array(temps)
    sals = np.array(sals)
    classes = np.array(classes)

    color_map = {
        "Bay of Bengal Surface Water (BBSW)": "#1f78b4",
        "Arabian Sea High Salinity Water (ASHSW)": "#e31a1c",
        "Equatorial Indian Ocean Surface Water": "#33a02c",
        "Indian Central Water (ICW)": "#ff7f00",
        "Indian Deep / Bottom Water": "#6a3d9a",
        "Transitional / Thermocline Water": "#b15928"
    }

    fig, ax = plt.subplots(figsize=(8, 5.5), dpi=300)

    # Plot isopycnal contours (density anomaly sigma)
    s_grid = np.linspace(25, 37, 100)
    t_grid = np.linspace(2, 33, 100)
    S_mesh, T_mesh = np.meshgrid(s_grid, t_grid)
    sigma_mesh = np.zeros_like(S_mesh)
    for i in range(T_mesh.shape[0]):
        for j in range(S_mesh.shape[1]):
            sigma_mesh[i, j] = potential_density_unesco(T_mesh[i, j], S_mesh[i, j])

    contours = ax.contour(S_mesh, T_mesh, sigma_mesh, levels=np.arange(18.0, 29.0, 1.0),
                          colors='gray', linestyles='dotted', linewidths=0.8, alpha=0.7)
    ax.clabel(contours, inline=True, fontsize=8, fmt=r"$\sigma$=%1.0f")

    # Plot points for each water mass class
    for name, col in color_map.items():
        mask = (classes == name)
        ax.scatter(sals[mask], temps[mask], color=col, s=2.5, alpha=0.45, label=name, edgecolors='none')

    ax.set_xlabel("Salinity (PSU)", fontsize=10, weight='bold')
    ax.set_ylabel("Temperature (°C)", fontsize=10, weight='bold')
    ax.set_title("T–S Diagram of 110,079 Observation Levels with Isopycnals ($\sigma$, kg/m³)", fontsize=11, weight='bold', pad=12)
    ax.set_xlim(28.0, 36.5)
    ax.set_ylim(2.0, 32.5)
    ax.grid(True, linestyle=':', alpha=0.4)
    ax.legend(loc="lower left", fontsize=8, framealpha=0.9, markerscale=4)

    out_path = FIG_DIR / "fig_ts_watermass.png"
    plt.tight_layout()
    plt.savefig(out_path, dpi=300)
    plt.close()
    print(f"Saved {out_path}")


if __name__ == "__main__":
    plot_seasonal_blt()
    plot_ts_diagram()

