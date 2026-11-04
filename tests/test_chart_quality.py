"""Chart correctness/readability checks (need plotly; skipped where it is not installed)."""
import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))

import pytest

pytest.importorskip("plotly")
from retrieval.nl_parser import parse_question  # noqa: E402
from retrieval.query_engine import retrieve  # noqa: E402
from viz import charts  # noqa: E402


def _title(fig):
    t = fig["layout"]["title"]
    return t["text"] if isinstance(t, dict) else t


def _rows(q):
    return retrieve(parse_question(q))


def test_depth_profile_axis_is_reversed_has_units_and_says_when_truncated():
    r = _rows("temperature profiles in March 2023")
    fig = json.loads(charts.make_depth_profile(r["rows"], "temperature"))
    assert fig["layout"]["yaxis"]["autorange"] == "reversed"
    assert "dbar" in fig["layout"]["yaxis"]["title"]["text"]
    assert "°C" in fig["layout"]["xaxis"]["title"]["text"]
    assert len(fig["data"]) <= 15
    n_profiles = len({row["id"] for row in r["rows"]})
    if n_profiles > 15:
        assert f"showing 15 of {n_profiles} profiles" in _title(fig)


def test_compare_histograms_are_translucent_and_both_groups_present():
    r = _rows("Compare temperature in January and June 2023")
    fig = json.loads(charts.make_comparison(r["compare_groups"], "temperature"))
    assert len(fig["data"]) == 2
    # plotly stores histogram opacity under marker.opacity
    assert all((tr.get("marker") or {}).get("opacity", 1) < 1 for tr in fig["data"])
    assert fig["layout"]["barmode"] == "overlay"
    assert "dbar" in _title(fig)


def test_timeseries_and_distribution_state_depth_range_and_units():
    r = _rows("temperature in April 2023 at all depths")
    ts = json.loads(charts.make_timeseries(r["rows"], "temperature"))
    assert "daily mean" in _title(ts) and "dbar" in _title(ts) and "°C" in _title(ts)
    dist = json.loads(charts.make_distribution(r["rows"], "temperature"))
    assert "dbar" in _title(dist)
    dates = ts["data"][0]["x"]
    assert list(dates) == sorted(dates)


def test_depth_note_uses_plotted_data_only():
    import pandas as pd
    assert charts._depth_note(pd.DataFrame({"pressure": [2.0, 49.6]})) == " | 2–50 dbar"
    assert charts._depth_note(pd.DataFrame({"x": [1]})) == ""


# ── Depth-profile selection: spread across floats and dates (Round 5) ────────

def _synthetic(profiles_per_float):
    import pandas as pd
    rows = []
    for plat, n in profiles_per_float.items():
        for i in range(n):
            ts = pd.Timestamp("2023-01-01", tz="UTC") + pd.Timedelta(days=i * 4)
            for p in (5.0, 50.0, 500.0):
                rows.append({"id": f"{plat}_{i:03d}", "platform": plat, "timestamp": ts, "pressure": p, "temperature": 30 - p / 40})
    return pd.DataFrame(rows)


def test_pick_spread_one_busy_float_cannot_take_every_slot():
    df = _synthetic({"1000001": 40, "1000002": 3, "1000003": 2})
    chosen = charts._pick_spread_profiles(df, "id", 15)
    assert len(chosen) == len(set(chosen)) == 15
    plats = {c.split("_")[0] for c in chosen}
    assert plats == {"1000001", "1000002", "1000003"}
    first_float = sorted(c for c in chosen if c.startswith("1000001"))
    assert first_float[0] == "1000001_000" and first_float[-1] == "1000001_039"  # whole date range, not the first N rows


def test_pick_spread_is_deterministic_and_independent_of_row_order():
    df = _synthetic({"1000001": 30, "1000002": 30})
    a = charts._pick_spread_profiles(df, "id", 15)
    b = charts._pick_spread_profiles(df.sample(frac=1, random_state=7), "id", 15)
    assert a == b


def test_pick_spread_more_floats_than_slots_takes_floats_evenly():
    df = _synthetic({f"20000{i:02d}": 2 for i in range(40)})
    chosen = charts._pick_spread_profiles(df, "id", 15)
    assert len(chosen) == 15 and len({c.split("_")[0] for c in chosen}) == 15


def test_depth_profile_chart_real_data_covers_many_floats_and_months_and_keeps_note():
    r = _rows("temperature profiles in 2023")
    fig = json.loads(charts.make_depth_profile(r["rows"], "temperature"))
    assert len(fig["data"]) == 15
    n_profiles = len({row["id"] for row in r["rows"]})
    assert f"showing 15 of {n_profiles} profiles" in _title(fig)
    names = {tr["name"] for tr in fig["data"]}
    by_id = {row["id"]: row for row in r["rows"]}
    assert len({by_id[n]["platform"] for n in names}) >= 10
    assert len({by_id[n]["timestamp"][:7] for n in names}) >= 4   # not just the first days of January
