"""Regression tests for the full-project review fixes.

Covers: dive-profile physics and endpoint, follow-up context handling, "deepest floats" ordering,
request limits, security headers and the packaging safety check.
"""
import sqlite3
import sys
import uuid
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "backend"))
sys.path.insert(0, str(ROOT / "scripts"))

from fastapi.testclient import TestClient  # noqa: E402
from retrieval import dive_profile as dp  # noqa: E402


def _client():
    from main import app
    return TestClient(app)


def _ask(client, question, conv=None, **extra):
    r = client.post("/api/chat", json={"message": question, "conversation_id": conv or str(uuid.uuid4()), **extra})
    return r


# ── Dive profile: pure functions (no database) ───────────────────────────────

def _synthetic_rows():
    """Warm mixed layer to 40 dbar, thermocline to 200, cold deep water to 2000 dbar."""
    rows = []
    for p in range(5, 2001, 5):
        if p <= 40:
            t = 28.0
        elif p <= 200:
            t = 28.0 - (p - 40) * 0.1
        else:
            t = max(2.5, 12.0 - (p - 200) * 0.006)
        rows.append((float(p), t, 34.8))
    return rows


def test_sound_speed_is_physically_sensible():
    # Warm surface water ~1540 m/s, cold deep water ~1485-1495 m/s
    surface = dp.sound_speed_mackenzie(28.0, 33.0, 0.0)
    deep = dp.sound_speed_mackenzie(4.0, 34.8, dp.depth_from_pressure(1500.0, 10.0))
    assert 1530 < surface < 1550
    assert 1480 < deep < 1500
    # depth from pressure: ~1% less than the dbar value at 1000 dbar
    assert 985 < dp.depth_from_pressure(1000.0, 10.0) < 995


def test_mixed_layer_depth_interpolated_and_reference_is_surface():
    res = dp.build_dive_profile(_synthetic_rows(), lat=10.0)
    # 0.2 C below 28 C is reached at 42 dbar on the synthetic curve
    assert res["mixed_layer_depth"] == pytest.approx(42.0, abs=3.0)


def test_mixed_layer_not_resolved_without_surface_level():
    rows = [r for r in _synthetic_rows() if r[0] >= 100]
    res = dp.build_dive_profile(rows, lat=10.0)
    assert res["mixed_layer_depth"] is None
    assert res["mixed_layer_note"]


def test_thermocline_is_limited_to_upper_500_dbar():
    rows = _synthetic_rows()
    # a sharp deep step that must be ignored
    rows = [(p, t - (3.0 if p > 1500 else 0.0), s) for p, t, s in rows]
    res = dp.build_dive_profile(rows, lat=10.0)
    assert res["thermocline_depth"] is not None
    assert res["thermocline_depth"] <= 500.0


def test_thermocline_works_for_densely_sampled_profiles():
    # 1 dbar spacing: the old code (consecutive points >= 5 dbar apart) returned None here
    rows = [(float(p), 28.0 - max(0, p - 50) * 0.1, 34.5) for p in range(1, 400)]
    res = dp.build_dive_profile(rows, lat=10.0)
    assert res["thermocline_depth"] is not None


def test_sofar_requires_deep_profile():
    shallow = [r for r in _synthetic_rows() if r[0] <= 500]
    res = dp.build_dive_profile(shallow, lat=10.0)
    assert res["sofar_depth"] is None and res["sofar_speed"] is None
    assert "1000" in res["sofar_note"]


def test_sofar_reports_band_for_deep_profile():
    res = dp.build_dive_profile(_synthetic_rows(), lat=10.0)
    if res["sofar_depth"] is not None:
        top, bottom = res["sofar_band"]
        assert top <= res["sofar_depth"] <= bottom
    else:
        assert res["sofar_note"]


def test_bad_rows_are_ignored():
    rows = [(None, 20.0, 35.0), (float("nan"), 20.0, 35.0), (-5.0, 20.0, 35.0), (10.0, None, None), (20.0, 25.0, 34.0)]
    res = dp.build_dive_profile(rows, lat=None)
    assert [lv["pressure"] for lv in res["levels"]] == [10.0, 20.0]
    assert res["levels"][0]["sound_speed"] is None


# ── Dive profile: endpoint (needs the ocean database) ────────────────────────

def test_dive_endpoint_uses_latest_profile_with_measurements():
    """Float 2903434's newest profile has no measurements; it used to return 404."""
    client = _client()
    r = client.get("/api/floats/2903434/dive-profile")
    assert r.status_code == 200
    assert len(r.json()["levels"]) > 0


def test_dive_endpoint_every_float_with_data_works():
    from config import DB_PATH
    conn = sqlite3.connect(DB_PATH)
    try:
        plats = [r[0] for r in conn.execute(
            "SELECT DISTINCT p.platform FROM profiles p JOIN measurements m ON m.profile_id = p.id")]
    finally:
        conn.close()
    client = _client()
    assert plats
    for plat in plats:
        r = client.get(f"/api/floats/{plat}/dive-profile")
        assert r.status_code == 200, plat
        d = r.json()
        if d["thermocline_depth"] is not None:
            assert d["thermocline_depth"] <= 500.0
        if d["sofar_depth"] is not None:
            assert d["max_depth"] >= 1000.0
            assert 1450.0 <= d["sofar_speed"] <= 1550.0
        else:
            assert d["sofar_note"]


def test_dive_endpoint_shallow_float_has_no_sofar():
    client = _client()
    r = client.get("/api/floats/2902837/dive-profile")   # profile only reaches ~167 dbar
    assert r.status_code == 200
    assert r.json()["sofar_depth"] is None
    assert r.json()["sofar_note"]


def test_dive_endpoint_unknown_and_empty_floats_are_404():
    client = _client()
    assert client.get("/api/floats/9999999/dive-profile").status_code == 404
    assert client.get("/api/floats/abc/dive-profile").status_code == 404
    assert client.get("/api/floats/2902394/dive-profile").status_code == 404   # float with no measurements


# ── Follow-up context ────────────────────────────────────────────────────────

def test_standalone_count_question_ignores_previous_filters():
    client = _client()
    conv = str(uuid.uuid4())
    _ask(client, "average temperature in March 2023 at 1000 dbar", conv)
    j = _ask(client, "how many floats are there", conv).json()
    assert "37 floats" in j["answer"]


def test_gibberish_does_not_inherit_previous_question():
    client = _client()
    conv = str(uuid.uuid4())
    _ask(client, "maximum salinity in 2024", conv)
    j = _ask(client, "asdfgh qwerty zxcv", conv).json()
    assert "2024" not in j["answer"]
    assert j.get("stat") is None


def test_follow_up_states_carried_over_filters():
    client = _client()
    conv = str(uuid.uuid4())
    _ask(client, "average temperature in March 2023", conv)
    j = _ask(client, "what about salinity?", conv).json()
    assert j["context_note"] and "Mar 2023" in j["context_note"]
    assert "Carried over from your previous question" in j["answer"]


def test_explicit_question_has_no_carried_over_note():
    client = _client()
    conv = str(uuid.uuid4())
    _ask(client, "average temperature in March 2023", conv)
    j = _ask(client, "average salinity in July 2024", conv).json()
    assert not j.get("context_note")


# ── Float discovery ordering ────────────────────────────────────────────────

def test_deepest_floats_are_sorted_by_depth():
    client = _client()
    j = _ask(client, "which floats are deepest").json()
    floats = j["discovery_data"]["floats"]
    depths = [f["avg_max_depth"] for f in floats]
    assert depths == sorted(depths, reverse=True)


# ── Request limits and hardening ────────────────────────────────────────────

def test_history_is_capped():
    client = _client()
    too_many = [{"role": "user", "content": "x"}] * 51
    assert _ask(client, "hi", history=too_many).status_code == 422
    too_big = [{"role": "user", "content": "x" * 25000}]
    assert _ask(client, "hi", history=too_big).status_code == 422
    ok = [{"role": "user", "content": "hello"}] * 5
    assert _ask(client, "hi", history=ok).status_code == 200


def test_oversized_request_body_is_rejected():
    client = _client()
    r = client.post("/api/chat", content=b"x" * 300_000, headers={"Content-Type": "application/json"})
    assert r.status_code == 413


def test_security_headers_present():
    client = _client()
    r = client.get("/api/health")
    assert r.headers["X-Content-Type-Options"] == "nosniff"
    assert r.headers["X-Frame-Options"] == "DENY"
    # CSP is report-only by default (nothing is blocked until FLOATCHAT_CSP=enforce)
    assert "frame-ancestors 'none'" in r.headers["Content-Security-Policy-Report-Only"]


def test_health_does_not_expose_model_name_and_docs_are_off():
    client = _client()
    assert "gemini_model" not in client.get("/api/health").json()
    for path in ("/docs", "/redoc", "/openapi.json"):
        r = client.get(path)
        # With the static-file mount these fall through to the frontend (404), never the API docs.
        assert r.status_code == 404, path


# ── Packaging safety ────────────────────────────────────────────────────────

def test_package_script_excludes_secrets_and_databases(tmp_path):
    import zipfile
    import package
    out = package.package_distributable(str(tmp_path / "dist.zip"))
    names = zipfile.ZipFile(out).namelist()
    bad = [n for n in names if n.endswith(".env") or n.endswith(".db") or n.startswith("logs/")]
    assert bad == []
    assert ".env.example" in names
