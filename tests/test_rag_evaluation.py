"""Pytest integration for quantitative RAG precision and answer grounding."""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

from evaluate_rag import evaluate_rag

def test_quantitative_rag_precision_and_grounding():
    """Assert RAG retrieval Precision@1 >= 80% and Grounding >= 75%."""
    assert evaluate_rag() is True

