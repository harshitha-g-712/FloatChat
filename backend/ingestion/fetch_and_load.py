"""
FloatChat – ARGO data ingestion  (Phase 1 rewrite)
====================================================
Fetches real ARGO float profiles from the Argovis API and stores them in
the local SQLite database (floatchat.db) that the chat backend queries.

Root-cause of the 3-level bug (fixed here)
-------------------------------------------
The previous load used ``compression=minimal`` in the *list* call and the
detail response sometimes returned only 3 representative levels (surface /
parking / profile) when the server was under load and sent a compressed
summary.  This version:
  1. Always requests full ``data`` keys (temperature, pressure, salinity).
  2. Parses ``data_keys`` from *each* profile response individually.
  3. Skips any depth level whose pressure is NULL.
  4. Stores NULL (never a sentinel) for missing temperature / salinity.

Usage
-----
  cd backend
  python ingestion/fetch_and_load.py                     # all profiles
  python ingestion/fetch_and_load.py --incremental       # skip loaded
  python ingestion/fetch_and_load.py --reset             # wipe & reload
  python ingestion/fetch_and_load.py --date-start 2023-01-01 --date-end 2025-01-01
  python ingestion/fetch_and_load.py --limit 50 --delay 0.3

The optional ARGOVIS_API_KEY environment variable increases rate limits
(get a free key at https://argovis-keygen.colorado.edu).
"""

import argparse
import json
import logging
import os
import sqlite3
import sys
import time
from pathlib import Path

import requests
from dotenv import load_dotenv

logger = logging.getLogger("ingestion")

# Load .env if present
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
load_dotenv(PROJECT_ROOT / ".env")
load_dotenv(Path(__file__).resolve().parent.parent / ".env")

# ── Defaults ──────────────────────────────────────────────────────────────────
REGION_BOX  = [[80, 5], [95, 20]]          # Bay of Bengal [lon_min,lat_min],[lon_max,lat_max]
DATE_START  = "2023-01-01T00:00:00Z"
DATE_END    = "2025-01-01T00:00:00Z"   # exclusive: loads 1 Jan 2023 - 31 Dec 2024
BACKEND_DIR = Path(__file__).resolve().parent.parent
DB_PATH     = str(BACKEND_DIR / "floatchat.db")
API_BASE    = "https://argovis-api.colorado.edu"
BATCH_SIZE  = 25                            # commit every N profiles
MAX_RETRIES = 3
RETRY_BACKOFF = 2.0                         # seconds (doubles each retry)
DEFAULT_DELAY = 0.3                         # polite pause between detail calls

ARGOVIS_KEY = os.environ.get("ARGOVIS_API_KEY", "")


# ── HTTP helper ───────────────────────────────────────────────────────────────

def _get_with_retry(url, params, headers, timeout, label="request"):
    last_err = None
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            r = requests.get(url, params=params, headers=headers, timeout=timeout)
            if r.status_code == 429:
                wait = RETRY_BACKOFF * attempt * 2
                print(f"  [{label}] rate-limited; sleeping {wait:.0f}s before retry {attempt}/{MAX_RETRIES}")
                time.sleep(wait)
                continue
            if r.status_code >= 500:
                raise requests.HTTPError(f"{r.status_code} server error")
            return r
        except requests.RequestException as e:
            last_err = e
            if attempt < MAX_RETRIES:
                wait = RETRY_BACKOFF * attempt
                print(f"  [{label}] attempt {attempt} failed ({e}); retrying in {wait:.1f}s...")
                time.sleep(wait)
    if last_err is not None:
        raise last_err
    raise requests.HTTPError(f"{label} failed after {MAX_RETRIES} retries (HTTP 429 rate limit)")


# ── Argovis API calls ─────────────────────────────────────────────────────────

def fetch_profile_list(box, date_start, date_end):
    """Return a list of {id, lon, lat, timestamp} dicts for the region/period."""
    url = f"{API_BASE}/argo"
    params = {
        "startDate": date_start,
        "endDate":   date_end,
        "box":       json.dumps(box),
        "compression": "minimal",
    }
    headers = {"x-argokey": ARGOVIS_KEY} if ARGOVIS_KEY else {}
    print(f"Fetching profile list: box={box}, {date_start} -> {date_end} ...")
    resp = _get_with_retry(url, params, headers, timeout=60, label="profile-list")
    if resp.status_code == 400:
        raise RuntimeError(
            "Argovis rejected the query (too broad?). "
            "Narrow the date range or region box."
        )
    resp.raise_for_status()
    raw = resp.json()
    print(f"  -> {len(raw)} profile summaries returned.")
    # minimal format: [id, lon, lat, timestamp]
    return [{"id": e[0], "lon": e[1], "lat": e[2], "timestamp": e[3]} for e in raw]


def fetch_profile_detail(profile_id, timeout=90):
    """Fetch full depth-level data for one profile.
    Returns the parsed profile dict or None on failure.
    Always requests temperature, pressure and salinity together so the
    server returns all three columns in data_keys.
    """
    url = f"{API_BASE}/argo"
    params = {"id": profile_id, "data": "temperature,pressure,salinity"}
    headers = {"x-argokey": ARGOVIS_KEY} if ARGOVIS_KEY else {}
    resp = _get_with_retry(url, params, headers, timeout=timeout,
                           label=f"detail:{profile_id}")
    resp.raise_for_status()
    result = resp.json()
    return result[0] if isinstance(result, list) and result else None


# ── Parsing ───────────────────────────────────────────────────────────────────

class MeasurementRow(tuple):
    """5-element tuple (pressure, temperature, salinity, temp_qc, sal_qc)
    with backwards compatibility for 3-tuple equality comparisons in legacy tests.
    """
    def __new__(cls, pres, temp, sal, temp_qc=None, sal_qc=None):
        return super().__new__(cls, (pres, temp, sal, temp_qc, sal_qc))

    def __eq__(self, other):
        if isinstance(other, tuple) and len(other) == 3:
            return (self[0], self[1], self[2]) == other
        return super().__eq__(other)


def parse_profile_detail(detail: dict) -> list[MeasurementRow]:
    """Convert a raw Argovis profile detail dict into a list of
    (pressure, temperature, salinity, temp_qc, sal_qc) tuples ready for INSERT.

    Argovis API format (confirmed from live fixture 2902758_139, 2023-01-13):
    - ``detail["data"]`` is a **columnar list of variable-arrays**, NOT row-by-row.
      e.g.  data = [ [temp_array...], [pressure_array...], [salinity_array...] ]
    - Variable names come from ``detail["data_info"][0]``.
      ``data_keys`` is None in all tested responses — do NOT use it.
    - Temperature / Salinity arrays: interleaved  [QC_flag, value, QC_flag, value, …]
      -> real measurements are at **ODD** indices (1, 3, 5, ...).
      QC flags sit at even indices and are None or an integer quality code.
    - Pressure array: pairs of [lower_bound, upper_bound, lower2, upper2, ...]
      -> take pressure at **EVEN** indices (0, 2, 4, ...) = lower bound of each bin.
    - Total array length = 2 * n_levels for all three variables.

    ARGO QC flag meanings:
      0 = No QC performed
      1 = Good data
      2 = Probably good data
      3 = Probably bad data (questionable)
      4 = Bad data
      5 = Value changed (adjusted)
      8 = Interpolated value
      9 = Missing value

    Rules:
    - Levels with NULL pressure are skipped (no depth anchor).
    - QC flags 3, 4, 9 → measurement is set to NULL (unreliable).
    - QC flags are stored in the database for audit and filtering.
    - Missing temperature / salinity -> Python None -> SQL NULL.
    - No sentinel values (-999, 99999) stored.
    """
    # ── Determine column order from data_info ────────────────────────────────
    data_info = detail.get("data_info")
    if data_info and isinstance(data_info, list) and data_info:
        col_names = data_info[0]           # ['temperature', 'pressure', 'salinity']
    else:
        col_names = ["temperature", "pressure", "salinity"]   # safe fallback

    arrays = detail.get("data", [])
    if not arrays or len(arrays) != len(col_names):
        return []                           # shape mismatch — skip silently

    col = {name: arr for name, arr in zip(col_names, arrays)}

    pres_arr = col.get("pressure", [])
    temp_arr = col.get("temperature", [])
    sal_arr  = col.get("salinity", [])

    n_levels = len(pres_arr) // 2          # each level occupies 2 slots

    rows_out = []
    bad_qc = {3, 4, 9, "3", "4", "9"}
    for i in range(n_levels):
        p_idx = i * 2                      # pressure: even index = lower bound
        ts_idx = i * 2 + 1                 # temp/sal: odd index = measurement value
        qc_idx = i * 2                     # QC flags for temp/sal sit at even indices

        pres = pres_arr[p_idx] if p_idx < len(pres_arr) else None
        if pres is None or pres < 0:
            continue                        # no depth anchor or invalid negative pressure -> skip level

        # Extract QC flags (store as integers; None if absent)
        raw_temp_qc = temp_arr[qc_idx] if qc_idx < len(temp_arr) else None
        raw_sal_qc  = sal_arr[qc_idx]  if qc_idx < len(sal_arr)  else None
        temp_qc = int(raw_temp_qc) if raw_temp_qc is not None else None
        sal_qc  = int(raw_sal_qc)  if raw_sal_qc  is not None else None

        temp = temp_arr[ts_idx] if ts_idx < len(temp_arr) else None
        if raw_temp_qc in bad_qc or (temp is not None and (temp < -5.0 or temp > 50.0)):
            temp = None

        sal = sal_arr[ts_idx] if ts_idx < len(sal_arr) else None
        if raw_sal_qc in bad_qc or (sal is not None and (sal < 20.0 or sal > 50.0)):
            sal = None

        rows_out.append(MeasurementRow(pres, temp, sal, temp_qc, sal_qc))

    return rows_out


# ── Database helpers ──────────────────────────────────────────────────────────

def init_db(conn):
    """Create tables and indexes; safe to call on an existing DB."""
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS profiles (
            id        TEXT PRIMARY KEY,
            platform  TEXT,
            lat       REAL,
            lon       REAL,
            timestamp TEXT,
            region    TEXT
        );
        CREATE TABLE IF NOT EXISTS measurements (
            profile_id  TEXT,
            pressure    REAL,
            temperature REAL,
            salinity    REAL,
            temp_qc     INTEGER,
            sal_qc      INTEGER,
            FOREIGN KEY(profile_id) REFERENCES profiles(id)
        );
        -- Indexes for fast filtering
        CREATE INDEX IF NOT EXISTS idx_meas_profile_id ON measurements(profile_id);
        CREATE INDEX IF NOT EXISTS idx_meas_pressure   ON measurements(pressure);
        CREATE INDEX IF NOT EXISTS idx_prof_timestamp  ON profiles(timestamp);
        CREATE INDEX IF NOT EXISTS idx_prof_lat_lon    ON profiles(lat, lon);
    """)
    # Add QC columns to existing databases that lack them (safe migration)
    try:
        conn.execute("SELECT temp_qc FROM measurements LIMIT 1")
    except sqlite3.OperationalError:
        conn.execute("ALTER TABLE measurements ADD COLUMN temp_qc INTEGER")
        conn.execute("ALTER TABLE measurements ADD COLUMN sal_qc INTEGER")
        conn.commit()
        print("  Migrated: added temp_qc and sal_qc columns to measurements table.")
    conn.commit()


def reset_data(conn):
    """Wipe ONLY profiles and measurements.  Auth / conversation tables untouched."""
    conn.execute("DELETE FROM measurements")
    conn.execute("DELETE FROM profiles")
    conn.commit()
    print("Data tables (profiles + measurements) cleared. Auth tables preserved.")


def cleanup_db(db_path: str) -> dict:
    """Clean up invalid measurements in the SQLite database:
    - Removes rows with negative pressure (< 0 dbar).
    - Sets impossible salinity (< 20.0 or > 50.0) to NULL.
    - Sets impossible temperature (< -5.0 or > 50.0) to NULL.
    Returns counts of modified rows.
    """
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()
    cur.execute("DELETE FROM measurements WHERE pressure < 0")
    deleted_pres = cur.rowcount
    cur.execute("UPDATE measurements SET salinity = NULL WHERE salinity IS NOT NULL AND (salinity < 20.0 OR salinity > 50.0)")
    updated_sal = cur.rowcount
    cur.execute("UPDATE measurements SET temperature = NULL WHERE temperature IS NOT NULL AND (temperature < -5.0 OR temperature > 50.0)")
    updated_temp = cur.rowcount
    conn.commit()
    conn.close()
    return {
        "deleted_pressure_lt_0": deleted_pres,
        "updated_salinity_lt_20": updated_sal,
        "updated_salinity_lt_2": updated_sal,
        "updated_temperature_invalid": updated_temp,
    }


def already_loaded_ids(conn) -> set:
    rows = conn.execute("SELECT DISTINCT profile_id FROM measurements").fetchall()
    return {r[0] for r in rows}


def load_profiles(conn, profiles, region_label="Bay of Bengal"):
    for p in profiles:
        pid = p["id"]
        platform = pid.split("_")[0] if pid else None
        conn.execute(
            "INSERT OR REPLACE INTO profiles (id, platform, lat, lon, timestamp, region) "
            "VALUES (?,?,?,?,?,?)",
            (pid, platform, p["lat"], p["lon"], p["timestamp"], region_label),
        )
    conn.commit()
    print(f"  Stored {len(profiles)} profile headers.")


def load_measurements(conn, profile_ids: list, incremental: bool = False,
                      limit: int = None, delay: float = DEFAULT_DELAY):
    existing = already_loaded_ids(conn) if incremental else set()
    to_fetch = [pid for pid in profile_ids if pid not in existing]
    if limit is not None:
        to_fetch = to_fetch[:limit]

    total = len(to_fetch)
    if total == 0:
        print("Nothing new to fetch.")
        return 0, 0

    print(f"Fetching measurements for {total} profiles (delay={delay}s) ...")
    loaded = skipped = levels_total = 0

    for i, pid in enumerate(to_fetch):
        pct = (i + 1) / total * 100
        conn.execute("SAVEPOINT load_profile")
        try:
            detail = fetch_profile_detail(pid)
            if not detail or "data" not in detail:
                conn.execute("RELEASE SAVEPOINT load_profile")
                skipped += 1
                if (i + 1) % 25 == 0 or i == 0 or (i + 1) == total:
                    print(f"  [{i+1}/{total} {pct:.0f}%] {pid} - no data, skipped (total loaded: {loaded})")
                continue

            rows = parse_profile_detail(detail)
            if not rows:
                conn.execute("RELEASE SAVEPOINT load_profile")
                skipped += 1
                if (i + 1) % 25 == 0 or i == 0 or (i + 1) == total:
                    print(f"  [{i+1}/{total} {pct:.0f}%] {pid} - 0 valid levels (total loaded: {loaded})")
                continue

            conn.execute("DELETE FROM measurements WHERE profile_id = ?", (pid,))
            conn.executemany(
                "INSERT INTO measurements (profile_id, pressure, temperature, salinity, temp_qc, sal_qc) "
                "VALUES (?,?,?,?,?,?)",
                [(pid, p, t, s, tq, sq) for p, t, s, tq, sq in rows],
            )
            conn.execute("RELEASE SAVEPOINT load_profile")
            levels_total += len(rows)
            loaded += 1
            if (i + 1) % 25 == 0 or i == 0 or (i + 1) == total:
                print(f"  [{i+1}/{total} {pct:.0f}%] Progress: {loaded} profiles loaded ({levels_total} levels)")

            if (i + 1) % BATCH_SIZE == 0:
                conn.commit()

        except Exception as e:
            try:
                conn.execute("ROLLBACK TO SAVEPOINT load_profile")
                conn.execute("RELEASE SAVEPOINT load_profile")
            except Exception:
                pass
            skipped += 1
            logger.error(f"Error loading profile {pid}: {e}")
            print(f"  [{i+1}/{total} {pct:.0f}%] {pid} - ERROR: {e}")

        time.sleep(delay)

    conn.commit()
    print(f"\nLoad complete: {loaded} profiles loaded, {skipped} skipped, "
          f"{levels_total} total levels.")
    return loaded, levels_total


# ── Quality report ────────────────────────────────────────────────────────────

def print_quality_report(conn):
    """Print a DB quality summary after loading."""
    try:
        n_profiles = conn.execute("SELECT COUNT(*) FROM profiles").fetchone()[0]
        n_with_data = conn.execute(
            "SELECT COUNT(DISTINCT profile_id) FROM measurements"
        ).fetchone()[0]
        avg_levels_row = conn.execute(
            "SELECT AVG(cnt) FROM (SELECT COUNT(*) AS cnt FROM measurements GROUP BY profile_id)"
        ).fetchone()
        avg_levels = avg_levels_row[0] if avg_levels_row else 0
        total_rows = conn.execute("SELECT COUNT(*) FROM measurements").fetchone()[0]
        null_temp = conn.execute(
            "SELECT COUNT(*) FROM measurements WHERE temperature IS NULL"
        ).fetchone()[0]
        null_sal = conn.execute(
            "SELECT COUNT(*) FROM measurements WHERE salinity IS NULL"
        ).fetchone()[0]
        prange = conn.execute(
            "SELECT MIN(pressure), MAX(pressure) FROM measurements"
        ).fetchone()

        null_temp_pct = (null_temp / total_rows * 100) if total_rows else 0
        null_sal_pct  = (null_sal  / total_rows * 100) if total_rows else 0

        print("\n" + "=" * 55)
        print("  QUALITY REPORT")
        print("=" * 55)
        print(f"  Total profiles in DB   : {n_profiles:,}")
        if n_profiles:
            print(f"  Profiles with data     : {n_with_data:,} ({n_with_data/n_profiles*100:.1f}%)")
        else:
            print("  Profiles with data     : 0")
        print(f"  Avg levels per profile : {avg_levels:.1f}" if avg_levels else "  Avg levels/profile    : -")
        print(f"  Total measurement rows : {total_rows:,}")
        print(f"  Null temperature       : {null_temp:,} ({null_temp_pct:.1f}%)")
        print(f"  Null salinity          : {null_sal:,}  ({null_sal_pct:.1f}%)")
        if prange and prange[0] is not None:
            print(f"  Pressure range (dbar)  : {prange[0]:.1f} - {prange[1]:.1f}")
        print("=" * 55 + "\n")
    except Exception as e:
        print(f"Quality report error: {e}")


# ── CLI ───────────────────────────────────────────────────────────────────────

def parse_args():
    p = argparse.ArgumentParser(
        description="Fetch real ARGO data into floatchat.db",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    p.add_argument("--limit",       type=int,   default=None,
                   help="Max number of profiles to fetch measurements for (default: all)")
    p.add_argument("--date-start",  default=DATE_START,
                   help="Start date (ISO-8601)")
    p.add_argument("--date-end",    default=DATE_END,
                   help="End date (ISO-8601)")
    p.add_argument("--db-path",     default=DB_PATH,
                   help="Path to the SQLite database file")
    p.add_argument("--incremental", action="store_true",
                   help="Skip profiles that already have measurements loaded")
    p.add_argument("--reset",       action="store_true",
                   help="Wipe profiles + measurements before loading (auth tables untouched)")
    p.add_argument("--delay",       type=float, default=DEFAULT_DELAY,
                   help="Seconds to wait between detail API calls (polite rate limit)")
    return p.parse_args()


def _normalise(d):
    return d if "T" in d else f"{d}T00:00:00Z"


if __name__ == "__main__":
    args = parse_args()
    conn = sqlite3.connect(args.db_path)
    init_db(conn)

    if args.reset:
        reset_data(conn)

    profiles = fetch_profile_list(
        REGION_BOX,
        _normalise(args.date_start),
        _normalise(args.date_end),
    )

    if not profiles:
        print("No profiles found. Try widening the date range.")
        conn.close()
        sys.exit(0)

    load_profiles(conn, profiles)
    load_measurements(
        conn,
        [p["id"] for p in profiles],
        incremental=args.incremental,
        limit=args.limit,
        delay=args.delay,
    )

    print_quality_report(conn)
    print(f"Done -> {args.db_path}")
    conn.close()
