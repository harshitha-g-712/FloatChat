"""Tests for ARGO Quality Control (QC) flag storage and filtering."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))

from ingestion.fetch_and_load import parse_profile_detail
from retrieval.dive_profile import build_dive_profile
from retrieval.query_engine import build_query

def test_parse_profile_detail_stores_qc_flags():
    """Verify parse_profile_detail extracts and returns temp_qc and sal_qc."""
    fake_detail = {
        "data_info": [["temperature", "pressure", "salinity"]],
        "data": [
            [1, 28.5, 4, 25.0],      # Level 0: QC 1 (good, val=28.5), Level 1: QC 4 (bad, val=25.0)
            [5.0, 10.0, 15.0, 20.0],  # Level 0: p=5.0, Level 1: p=15.0
            [1, 33.8, 1, 34.2]       # Level 0: QC 1 (good, val=33.8), Level 1: QC 1 (good, val=34.2)
        ]
    }
    rows = parse_profile_detail(fake_detail)
    assert len(rows) == 2
    
    # Level 0: Good QC (1)
    p0, t0, s0, tq0, sq0 = rows[0]
    assert p0 == 5.0
    assert t0 == 28.5
    assert s0 == 33.8
    assert tq0 == 1
    assert sq0 == 1
    
    # Level 1: Bad Temp QC (4) -> Temperature nulled out, but QC flag preserved
    p1, t1, s1, tq1, sq1 = rows[1]
    assert p1 == 15.0
    assert t1 is None          # nulled due to QC 4
    assert s1 == 34.2
    assert tq1 == 4          # flag preserved!
    assert sq1 == 1

def test_build_query_applies_qc_filtering():
    """Verify build_query filters bad QC flags by default."""
    sql, params = build_query({"variable": "temperature", "qc_mode": "good_only"})
    assert "m.temp_qc IN (1, 2, 5, 8)" in sql or "m.temp_qc IS NULL" in sql

    sql_sal, _ = build_query({"variable": "salinity", "qc_mode": "good_only"})
    assert "m.sal_qc IN (1, 2, 5, 8)" in sql_sal or "m.sal_qc IS NULL" in sql_sal

def test_dive_profile_respects_qc_flags():
    """Verify build_dive_profile excludes flagged bad QC levels from derived calculations."""
    levels_input = [
        # (pressure, temperature, salinity, temp_qc, sal_qc)
        (5.0, 28.0, 34.0, 1, 1),
        (20.0, 27.5, 34.2, 4, 1), # temp_qc = 4 (bad)
        (50.0, 25.0, 34.5, 1, 1),
    ]
    res = build_dive_profile(levels_input, lat=15.0)
    levels = res["levels"]
    assert len(levels) == 3
    assert levels[0]["temperature"] == 28.0
    assert levels[1]["temperature"] is None  # filtered out by QC 4!
    assert levels[1]["temp_qc"] == 4
    assert levels[2]["temperature"] == 25.0

