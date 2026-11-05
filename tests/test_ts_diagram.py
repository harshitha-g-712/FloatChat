"""Unit tests for the T-S diagram and oceanographic density calculator."""
import sys
from pathlib import Path
from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "backend"))

from main import app, _RATE_LIMITS
from retrieval.dive_profile import potential_density_unesco, classify_water_mass

client = TestClient(app)


def test_unesco_density_formula():
    # Warm surface Bay of Bengal
    sig = potential_density_unesco(28.5, 33.5)
    assert 20.0 <= sig <= 22.0

    # Cold intermediate depth
    sig_cold = potential_density_unesco(8.0, 34.8)
    assert 26.5 <= sig_cold <= 27.5


def test_classify_water_mass():
    assert "Bay of Bengal Surface Water" in classify_water_mass(28.5, 32.5)
    assert "Arabian Sea High Salinity" in classify_water_mass(26.0, 35.5)
    assert "Indian Central Water" in classify_water_mass(14.0, 34.8)


def test_ts_diagram_endpoint():
    _RATE_LIMITS.clear()
    resp = client.get("/api/floats/2902758/ts-diagram")
    assert resp.status_code == 200
    data = resp.json()
    assert data["platform"] == "2902758"
    assert "levels" in data
    assert len(data["levels"]) > 0
    assert "isopycnals" in data
    assert len(data["isopycnals"]) > 0

    # Check level keys
    lvl = data["levels"][0]
    assert "temperature" in lvl
    assert "salinity" in lvl
    assert "sigma_theta" in lvl
    assert "water_mass" in lvl

