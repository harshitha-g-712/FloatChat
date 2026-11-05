#!/usr/bin/env python3
"""Gold-Standard Scientific Accuracy Benchmark Suite for FloatChat.

Evaluates the application against the curated benchmark query set in eval/gold_standard_benchmark.json.
Measures:
  1. Semantic & Numerical Accuracy (Tolerance-checked values)
  2. Scientific Variable Fidelity (No hallucinated variable substitutions)
  3. Spatial & Temporal Guardrails (Rejection of invalid months / out-of-bounds regions)
  4. RAG Precision (Accurate oceanographic citations & source tagging)
"""

import json
import os
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "backend"))

from fastapi.testclient import TestClient
from main import app

BENCHMARK_PATH = ROOT / "eval" / "gold_standard_benchmark.json"

def run_benchmark():
    if not BENCHMARK_PATH.exists():
        print(f"Error: Benchmark file {BENCHMARK_PATH} not found.")
        sys.exit(1)

    cases = json.loads(BENCHMARK_PATH.read_text(encoding="utf-8"))
    client = TestClient(app)

    print(f"\n=======================================================")
    print(f"  FloatChat Scientific Accuracy Benchmark")
    print(f"  Total test cases: {len(cases)}")
    print(f"=======================================================\n")

    results = []
    passed_count = 0

    for idx, case in enumerate(cases):
        cid = case["id"]
        query = case["query"]
        category = case["category"]
        desc = case.get("description", "")

        t0 = time.time()
        resp = client.post("/api/chat", json={"message": query, "conversation_id": f"benchmark-{cid}"})
        elapsed = time.time() - t0

        if resp.status_code != 200:
            print(f"[FAIL] [{cid}] HTTP {resp.status_code} - {query}")
            results.append({"id": cid, "passed": False, "reason": f"HTTP {resp.status_code}"})
            continue

        data = resp.json()
        answer = data.get("answer", "")
        answer_lower = answer.lower()
        failures = []

        # 1. Required text check
        for req in case.get("required_in_answer", []):
            if req.lower() not in answer_lower:
                failures.append(f"Missing required phrase: '{req}'")

        # 2. Forbidden text check
        for forb in case.get("forbidden_in_answer", []):
            if forb.lower() in answer_lower:
                failures.append(f"Found forbidden text: '{forb}'")

        # 3. Numerical tolerance check
        if "expected_value_approx" in case:
            target = case["expected_value_approx"]
            tol = case.get("tolerance", 0.05)
            stat = data.get("stat") or {}
            val = stat.get("value")
            if val is None:
                failures.append(f"Expected numerical stat value approx {target}, but got None")
            elif abs(val - target) > tol:
                failures.append(f"Value {val} outside tolerance [{target - tol:.3f}, {target + tol:.3f}]")

        # 4. Observation count check
        if "expected_observation_count" in case:
            expected_obs = case["expected_observation_count"]
            actual_obs = data.get("observation_count")
            if actual_obs != expected_obs:
                failures.append(f"Observation count mismatch: expected {expected_obs}, got {actual_obs}")

        # 5. Task check
        if "expected_task" in case:
            expected_task = case["expected_task"]
            actual_task = data.get("task")
            if actual_task != expected_task:
                failures.append(f"Task mismatch: expected '{expected_task}', got '{actual_task}'")

        # 6. RAG Source tags check
        if "required_sources_prefix" in case:
            sources = data.get("sources", [])
            if not sources:
                failures.append("Expected sources in RAG answer, but none were returned")
            else:
                for prefix in case["required_sources_prefix"]:
                    if not any(s.startswith(prefix) for s in sources):
                        failures.append(f"Missing source starting with '{prefix}'")

        if not failures:
            passed_count += 1
            print(f"[PASS] [{cid}] ({elapsed:.2f}s) - {category}: \"{query}\"")
            results.append({"id": cid, "passed": True, "elapsed": elapsed})
        else:
            print(f"[FAIL] [{cid}] ({elapsed:.2f}s) - {category}: \"{query}\"")
            for f in failures:
                print(f"     -> {f}")
            results.append({"id": cid, "passed": False, "failures": failures, "elapsed": elapsed})

    accuracy = (passed_count / len(cases)) * 100
    print(f"\n-------------------------------------------------------")
    print(f"  Benchmark Summary: {passed_count}/{len(cases)} passed ({accuracy:.1f}%)")
    print(f"-------------------------------------------------------\n")

    return passed_count == len(cases)


if __name__ == "__main__":
    success = run_benchmark()
    sys.exit(0 if success else 1)
