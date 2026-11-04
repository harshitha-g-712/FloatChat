"""Two-year behaviour, independent of whichever real data is loaded.

Builds a synthetic Jan 2023 - Dec 2024 database in the real schema, runs the real API against it
in a subprocess (so config reads this DB) and checks every number against direct SQL.
"""
import datetime as dt
import json
import math
import os
import sqlite3
import subprocess
import sys

import pytest

ROOT = os.path.join(os.path.dirname(__file__), "..")


def _make_db(path):
    c = sqlite3.connect(path)
    c.executescript("""CREATE TABLE profiles (id TEXT PRIMARY KEY, platform TEXT, lat REAL, lon REAL, timestamp TEXT, region TEXT);
    CREATE TABLE measurements (profile_id TEXT, pressure REAL, temperature REAL, salinity REAL,
                               FOREIGN KEY(profile_id) REFERENCES profiles(id));
    CREATE INDEX idx_meas_profile_id ON measurements(profile_id);""")
    d0 = dt.datetime(2023, 1, 1, 6)
    for plat, lat0, lon0 in (("5900001", 8.0, 85.0), ("5900002", 16.0, 88.0), ("5900003", 12.0, 82.0)):
        for i in range(73):
            ts = d0 + dt.timedelta(days=10 * i, hours=int(plat[-1]))
            if ts.year > 2024:
                continue
            pid = f"{plat}_{i:03d}"
            c.execute("INSERT INTO profiles VALUES (?,?,?,?,?,?)",
                      (pid, plat, lat0 + 0.05 * i % 1.5, lon0 + 0.04 * i % 2, ts.strftime("%Y-%m-%dT%H:%M:%S.000Z"), "Bay of Bengal"))
            seasonal = 3 * math.sin((ts.timetuple().tm_yday - 60) / 365 * 2 * math.pi) + (0.8 if ts.year == 2024 else 0)
            for k, p in enumerate((5.0, 25.0, 50.0, 100.0, 500.0, 1000.0)):
                t, s = 28.5 + seasonal - p / 45.0, 33.0 + 0.3 * seasonal + p / 900.0
                if (i + k) % 11 == 0:
                    t = s = None
                c.execute("INSERT INTO measurements VALUES (?,?,?,?)", (pid, p, t, s))
    c.commit()
    c.close()


QUESTIONS = [
    "Average temperature in March 2024",
    "Compare salinity between July 2023 and July 2024",
    "Compare average temperature 2023 vs 2024",
    "Average temperature between January 2023 and March 2024",
    "Average temperature in the north-east monsoon",
    "Average salinity in the south-west monsoon 2024",
    "Average temperature in the north-east monsoon 2024",
    "Average temperature in January 2025",
    "Compare temperature in March 2024 and March 2025",
    "Compare March 2023 and April",
    "What is the data coverage?",
    "Maximun salinty in Aprl 2024",
    "List floats in 2024",
    "Warmest month in the data",
    "Compare temperature in January vs June 2023",
]


@pytest.fixture(scope="module")
def world(tmp_path_factory):
    d = tmp_path_factory.mktemp("ny")
    db = str(d / "ocean.db")
    _make_db(db)
    env = dict(os.environ, DB_PATH=db, AUTH_DB_PATH=str(d / "auth.db"))
    res = subprocess.run([sys.executable, os.path.join(ROOT, "tests", "_new_years_runner.py"), json.dumps(QUESTIONS)],
                         env=env, capture_output=True, text=True, timeout=300, cwd=ROOT)
    assert "@@JSON@@" in res.stdout, res.stderr[-2000:]
    answers = json.loads(res.stdout.split("@@JSON@@")[1])
    conn = sqlite3.connect(db)
    yield answers, conn
    conn.close()


def _avg(conn, col, lo, hi, pmax=50):
    return conn.execute(
        f"SELECT AVG(m.{col}), COUNT(m.{col}) FROM measurements m JOIN profiles p ON p.id=m.profile_id "
        f"WHERE p.timestamp >= ? AND p.timestamp < ? AND m.pressure <= ? AND m.{col} IS NOT NULL", (lo, hi, pmax)).fetchone()


def _in_answer(text, value, nd=3):
    return f"{value:.{nd}f}" in text


def test_every_question_answered(world):
    answers, _ = world
    assert all(a["status"] == 200 for a in answers.values())


def test_single_month_in_second_year_matches_sql(world):
    answers, conn = world
    a = answers["Average temperature in March 2024"]
    avg, n = _avg(conn, "temperature", "2024-03-01", "2024-04-01")
    assert a["stat"]["value"] == pytest.approx(avg, abs=1e-3) and a["observation_count"] == n


def test_cross_year_month_comparison_uses_both_periods(world):
    answers, conn = world
    a = answers["Compare salinity between July 2023 and July 2024"]["answer"]
    assert "Jul 2023" in a and "Jul 2024" in a
    v1, n1 = _avg(conn, "salinity", "2023-07-01", "2023-08-01")
    v2, n2 = _avg(conn, "salinity", "2024-07-01", "2024-08-01")
    assert _in_answer(a, v1) and _in_answer(a, v2) and f"{n1:,} observations" in a and f"{n2:,} observations" in a
    assert f"{v2 - v1:+.3f}" in a


def test_year_vs_year_comparison(world):
    answers, conn = world
    a = answers["Compare average temperature 2023 vs 2024"]["answer"]
    v1, _ = _avg(conn, "temperature", "2023-01-01", "2024-01-01")
    v2, _ = _avg(conn, "temperature", "2024-01-01", "2025-01-01")
    assert "• 2023:" in a and "• 2024:" in a and _in_answer(a, v1) and _in_answer(a, v2)


def test_cross_year_range_is_not_cut_to_its_first_month(world):
    answers, conn = world
    a = answers["Average temperature between January 2023 and March 2024"]
    v, n = _avg(conn, "temperature", "2023-01-01", "2024-04-01")
    assert a["stat"]["value"] == pytest.approx(v, abs=1e-3) and a["observation_count"] == n
    assert "between January 2023 and March 2024" in a["answer"]


def test_north_east_monsoon_spans_two_calendar_years_and_says_which_year_was_assumed(world):
    answers, conn = world
    a = answers["Average temperature in the north-east monsoon"]
    v, n = _avg(conn, "temperature", "2023-10-01", "2024-02-01")
    assert a["stat"]["value"] == pytest.approx(v, abs=1e-3) and a["observation_count"] == n
    assert "between October 2023 and January 2024" in a["answer"]
    assert "2023 was assumed" in a["answer"] and "2024" in a["answer"].split("assumed.)")[1]


def test_explicit_year_season_and_partial_season(world):
    answers, conn = world
    a = answers["Average salinity in the south-west monsoon 2024"]
    v, n = _avg(conn, "salinity", "2024-06-01", "2024-10-01")
    assert a["stat"]["value"] == pytest.approx(v, abs=1e-3) and a["observation_count"] == n
    assert "assumed" not in a["answer"]
    b = answers["Average temperature in the north-east monsoon 2024"]
    v, n = _avg(conn, "temperature", "2024-10-01", "2025-01-01")
    assert b["stat"]["value"] == pytest.approx(v, abs=1e-3) and b["observation_count"] == n
    assert "Partial coverage" in b["answer"] and "January 2025" in b["answer"]


def test_outside_coverage_messages_name_the_real_window(world):
    answers, _ = world
    a = answers["Average temperature in January 2025"]["answer"]
    assert "January 2023–December 2024" in a and "2024-12-" in a and answers["Average temperature in January 2025"]["stat"] is None
    c = answers["Compare temperature in March 2024 and March 2025"]["answer"]
    assert "Mar 2025: no observations in the dataset" in c and "Mar 2024: avg" in c


def test_mixed_year_and_yearless_months_ask_for_clarification(world):
    a = world[0]["Compare March 2023 and April"]
    assert a["ambiguous"] is True and "give a year for each" in a["answer"]


def test_coverage_card_matches_sql(world):
    answers, conn = world
    a = answers["What is the data coverage?"]["answer"]
    lo, hi = conn.execute("SELECT MIN(timestamp), MAX(timestamp) FROM profiles").fetchone()
    assert f"{lo[:10]} to {hi[:10]}" in a
    assert f"{conn.execute('SELECT COUNT(DISTINCT platform) FROM profiles').fetchone()[0]} distinct floats" in a


def test_typo_month_in_second_year(world):
    a = world[0]["Maximun salinty in Aprl 2024"]
    conn = world[1]
    mx = conn.execute("SELECT MAX(m.salinity) FROM measurements m JOIN profiles p ON p.id=m.profile_id "
                      "WHERE p.timestamp >= '2024-04-01' AND p.timestamp < '2024-05-01'").fetchone()[0]
    assert a["stat"]["value"] == pytest.approx(mx, abs=1e-3)
    assert a["interpreted_as"] == "Maximum salinity in April 2024"


def test_float_list_for_second_year(world):
    a, conn = world[0]["List floats in 2024"], world[1]
    rows = conn.execute("SELECT platform, COUNT(*) FROM profiles WHERE timestamp >= '2024-01-01' GROUP BY 1").fetchall()
    got = {f["platform"]: f["profile_count"] for f in a["discovery_data"]["floats"]}
    assert got == dict(rows)


def test_warmest_month_ranks_all_24_months(world):
    answers, conn = world
    a = answers["Warmest month in the data"]["answer"]
    rows = conn.execute("SELECT substr(p.timestamp,1,7), AVG(m.temperature) FROM measurements m JOIN profiles p ON p.id=m.profile_id "
                        "WHERE m.pressure <= 50 AND m.temperature IS NOT NULL GROUP BY 1").fetchall()
    best = max(rows, key=lambda r: r[1])
    names = ["January", "February", "March", "April", "May", "June", "July", "August", "September", "October", "November", "December"]
    assert f"The warmest month in the dataset was {names[int(best[0][5:]) - 1]} {best[0][:4]}" in a
    assert a.count(" °C;") >= 23   # all 24 monthly means listed


def test_single_year_month_comparison_unchanged(world):
    a = world[0]["Compare temperature in January vs June 2023"]["answer"]
    assert "Jan 2023" in a and "Jun 2023" in a
