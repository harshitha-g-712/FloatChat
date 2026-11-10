"""Measure execution latency across stages for representative queries.

Outputs eval/stage_latency.json containing per-stage and end-to-end timing statistics.
"""
import json
import os
import sys
import time
from pathlib import Path

# Add backend directory to path
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "backend"))

from rule_intent import parse_intent
from retrieval.query_engine import retrieve
from retrieval.dive_profile import potential_density_unesco, _mixed_layer_depth_density, _mixed_layer_depth

TEST_QUERIES = [
    "What is the average temperature in January 2023?",
    "Show me the salinity in July 2024",
    "Average temperature in North Bay of Bengal",
    "Compare temperature in January 2023 vs January 2024",
    "What is the maximum pressure recorded in 2023?",
]

def measure():
    import numpy as np

    parsing_times = []
    sql_times = []
    thermo_times = []
    total_times = []

    # Warm-up run
    for q in TEST_QUERIES:
        intent = parse_intent(q)
        if intent:
            retrieve(intent)

    # Benchmark iterations
    iterations = 50
    for _ in range(iterations):
        for q in TEST_QUERIES:
            t0 = time.perf_counter()

            # 1. Parsing
            intent = parse_intent(q)
            t1 = time.perf_counter()
            parsing_times.append((t1 - t0) * 1000.0)

            # 2. SQL Retrieval
            if intent:
                res = retrieve(intent)
            else:
                res = {}
            t2 = time.perf_counter()
            sql_times.append((t2 - t1) * 1000.0)

            # 3. Thermodynamic Calculation
            t_sample = [28.5 - i * 0.05 for i in range(100)]
            s_sample = [34.0 + i * 0.01 for i in range(100)]
            for t_val, s_val in zip(t_sample, s_sample):
                potential_density_unesco(t_val, s_val)
            levels = [{"pressure": float(i * 10), "temperature": t_sample[i], "salinity": s_sample[i], "density": potential_density_unesco(t_sample[i], s_sample[i])} for i in range(100)]
            _mixed_layer_depth(levels)
            _mixed_layer_depth_density(levels)
            t3 = time.perf_counter()
            thermo_times.append((t3 - t2) * 1000.0)

            total_times.append((t3 - t0) * 1000.0)

    summary = {
        "iterations": iterations * len(TEST_QUERIES),
        "intent_parsing_ms": {
            "mean": round(float(np.mean(parsing_times)), 2),
            "median": round(float(np.median(parsing_times)), 2),
            "p95": round(float(np.percentile(parsing_times, 95)), 2),
        },
        "sql_retrieval_ms": {
            "mean": round(float(np.mean(sql_times)), 2),
            "median": round(float(np.median(sql_times)), 2),
            "p95": round(float(np.percentile(sql_times, 95)), 2),
        },
        "thermodynamics_ms": {
            "mean": round(float(np.mean(thermo_times)), 2),
            "median": round(float(np.median(thermo_times)), 2),
            "p95": round(float(np.percentile(thermo_times, 95)), 2),
        },
        "total_internal_ms": {
            "mean": round(float(np.mean(total_times)), 2),
            "median": round(float(np.median(total_times)), 2),
            "p95": round(float(np.percentile(total_times, 95)), 2),
        }
    }

    out_path = ROOT / "eval" / "stage_latency.json"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(summary, f, indent=2)

    print("Latency evaluation complete:")
    print(json.dumps(summary, indent=2))

if __name__ == "__main__":
    measure()

