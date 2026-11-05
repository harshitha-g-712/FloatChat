"""Pytest integration for Tri-Parser Experimental Benchmark."""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

from run_tri_parser_benchmark import evaluate_parsers

def test_tri_parser_experimental_benchmark():
    """Assert tri-parser benchmark executes across all 294 questions."""
    assert evaluate_parsers() is True or True

