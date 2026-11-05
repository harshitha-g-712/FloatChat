"""Unit tests for the /api/map/points endpoint."""
import sys
import os
from pathlib import Path
from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "backend"))

from main import app, _RATE_LIMITS

client = TestClient(app)


def test_map_points_endpoint():
    _RATE_LIMITS.clear()
    resp = client.get("/api/map/points?limit=50")
    assert resp.status_code == 200
    data = resp.json()
    assert "points" in data
    assert "count" in data
    assert "platforms" in data
    assert len(data["points"]) <= 50

    if data["points"]:
        pt = data["points"][0]
        assert "id" in pt
        assert "platform" in pt
        assert "lat" in pt
        assert "lon" in pt
        assert "timestamp" in pt


def test_map_points_filtered():
    _RATE_LIMITS.clear()
    resp = client.get("/api/map/points?year=2023&limit=20")
    assert resp.status_code == 200
    data = resp.json()
    for pt in data["points"]:
        assert pt["timestamp"].startswith("2023")
