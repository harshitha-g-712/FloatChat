"""Test suite for Phase 4 Performance Evaluation.

Validates that the benchmark evaluation summary meets all required accuracy,
fidelity, and latency thresholds.
"""

import json
from pathlib import Path
import pytest

ROOT = Path(__file__).resolve().parent.parent
SUMMARY_FILE = ROOT / "eval" / "performance_evaluation_summary.json"


def test_performance_evaluation_summary_exists():
    assert SUMMARY_FILE.exists(), f"Summary file not found at {SUMMARY_FILE}"


def test_performance_metrics_thresholds():
    summary = json.loads(SUMMARY_FILE.read_text(encoding="utf-8"))

    # 1. Intent Accuracy
    intent = summary["intent_accuracy"]
    assert intent["score_pct"] >= 80.0, f"Intent accuracy {intent['score_pct']}% below 80% threshold"

    # 2. SQL Execution Accuracy
    sql_exec = summary["sql_execution_accuracy"]
    assert sql_exec["score_pct"] >= 95.0, f"SQL execution accuracy {sql_exec['score_pct']}% below 95%"

    # 3. Numerical Accuracy
    num = summary["numerical_accuracy"]
    assert num["score_pct"] >= 95.0, f"Numerical accuracy {num['score_pct']}% below 95%"

    # 4. Abstention Accuracy
    abst = summary["abstention_accuracy"]
    assert abst["score_pct"] >= 85.0, f"Abstention accuracy {abst['score_pct']}% below 85%"

    # 5. Retrieval Precision
    rag = summary["retrieval_precision"]
    assert rag["precision_at_1"] >= 90.0
    assert rag["mrr"] >= 0.90

    # 6. Response Time
    rt = summary["response_time"]
    assert rt["mean_seconds"] < 1.0, f"Mean latency {rt['mean_seconds']}s too slow"
    assert rt["p95_seconds"] < 2.0, f"P95 latency {rt['p95_seconds']}s too slow"

    # 7. QC Impact
    qc = summary["qc_impact"]
    assert qc["temperature_error_divergence_pct"] > 50.0, "QC error divergence should be substantial (>50%)"

