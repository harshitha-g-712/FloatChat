"""Pytest integration for the gold-standard scientific benchmark suite."""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

from evaluate import run_benchmark

def test_gold_standard_benchmark_suite():
    """Assert all 15 scientific benchmark queries achieve 100% precision."""
    assert run_benchmark() is True

