"""Unit tests for multi-region expansion and basin metadata."""
import sys
from pathlib import Path
from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "backend"))

from main import app, _RATE_LIMITS
from config import SUPPORTED_BASINS

client = TestClient(app)


def test_supported_basins_config():
    assert "bay_of_bengal" in SUPPORTED_BASINS
    assert "arabian_sea" in SUPPORTED_BASINS
    assert "equatorial_indian_ocean" in SUPPORTED_BASINS


def test_regions_endpoint():
    _RATE_LIMITS.clear()
    resp = client.get("/api/regions")
    assert resp.status_code == 200
    data = resp.json()
    assert "basins" in data
    assert len(data["basins"]) >= 3

    basin_ids = [b["id"] for b in data["basins"]]
    assert "bay_of_bengal" in basin_ids
    assert "arabian_sea" in basin_ids
    assert "equatorial_indian_ocean" in basin_ids

    # Bay of Bengal should be active
    bob = next(b for b in data["basins"] if b["id"] == "bay_of_bengal")
    assert bob["status"] == "active"
    assert bob["profiles_loaded"] > 0
