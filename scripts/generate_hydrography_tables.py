"""Generate seasonal hydrography and stratification statistics.

Computes median SST, SSS, potential density (sigma_theta),
density mixed layer depth (MLD_rho), thermal mixed layer depth (MLD_t),
and barrier layer thickness (BLT) across the four canonical Bay of Bengal seasons.

Outputs eval/hydrography_tables.json for paper reproducibility.
"""
import json
import sqlite3
import sys
from pathlib import Path
import numpy as np

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "backend"))

from retrieval.dive_profile import build_dive_profile, potential_density_unesco

DB_PATH = ROOT / "backend" / "floatchat.db"
OUT_PATH = ROOT / "eval" / "hydrography_tables.json"

def main():
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

    results = {}
    for s in seasons:
        plist = by_season[s]
        ssts = []
        ssss = []
        sigs = []
        mld_rhos = []
        mld_ts = []
        blts = []

        for p in plist:
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
            surf_candidates = [r for r in valid if r["pressure"] <= 15.0]
            if not surf_candidates:
                continue

            surf = surf_candidates[0]  # shallowest valid measurement level
            dive = build_dive_profile(rows, p["lat"])
            mld_rho = dive.get("mixed_layer_depth_density")
            mld_t = dive.get("mixed_layer_depth")
            blt = dive.get("barrier_layer_thickness")

            if mld_rho is not None and mld_t is not None:
                ssts.append(surf["temperature"])
                ssss.append(surf["salinity"])
                sigs.append(potential_density_unesco(surf["temperature"], surf["salinity"]))
                mld_rhos.append(mld_rho)
                mld_ts.append(mld_t)
                if blt is not None:
                    blts.append(blt)

        results[s] = {
            "total_profiles": len(plist),
            "usable_profiles": len(ssts),
            "sst_median": round(float(np.median(ssts)), 1) if ssts else None,
            "sss_median": round(float(np.median(ssss)), 1) if ssss else None,
            "sigma_median": round(float(np.median(sigs)), 2) if sigs else None,
            "mld_rho_median": round(float(np.median(mld_rhos)), 1) if mld_rhos else None,
            "mld_t_median": round(float(np.median(mld_ts)), 1) if mld_ts else None,
            "blt_median": round(float(np.median(blts)), 1) if blts else None,
        }

    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(OUT_PATH, "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2)

    print(f"Generated {OUT_PATH}")
    for s, data in results.items():
        print(f"  {s}: usable={data['usable_profiles']}/{data['total_profiles']}, SST={data['sst_median']}, SSS={data['sss_median']}, sigma={data['sigma_median']}, MLD_rho={data['mld_rho_median']}, MLD_t={data['mld_t_median']}, BLT={data['blt_median']}")

if __name__ == "__main__":
    main()
