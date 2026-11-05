#!/usr/bin/env python3
"""Quantitative RAG Evaluation Suite for FloatChat.

Evaluates and measures standard Information Retrieval (IR) and Generation Grounding metrics:
  1. Precision@1: Is the top retrieved document relevant?
  2. Precision@K (K=3): Fraction of retrieved documents that are relevant.
  3. Recall@K (K=3): Fraction of all relevant documents successfully retrieved.
  4. Mean Reciprocal Rank (MRR): 1 / rank of the primary expected target document.
  5. Answer Grounding Score: Percentage of ground-truth key facts supported in the generated answer.
  6. Citation Provenance Ratio: Percentage of answers providing verified [S#] source citations.
"""

import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "backend"))

from rag.indexer import retrieve, answer_conceptual_query

EVAL_DATASET_PATH = ROOT / "eval" / "rag_eval_dataset.json"


def evaluate_rag():
    if not EVAL_DATASET_PATH.exists():
        print(f"Error: {EVAL_DATASET_PATH} not found.")
        sys.exit(1)

    cases = json.loads(EVAL_DATASET_PATH.read_text(encoding="utf-8"))

    print("\n=======================================================")
    print("  FloatChat Quantitative RAG Evaluation")
    print(f"  Test queries: {len(cases)}")
    print("=======================================================\n")

    p1_scores = []
    pK_scores = []
    recall_scores = []
    mrr_scores = []
    grounding_scores = []
    citation_counts = 0

    K = 3

    for idx, case in enumerate(cases):
        qid = case["id"]
        query = case["query"]
        target_doc = case["expected_target_doc"]
        relevant_docs = set(case.get("relevant_docs", [target_doc]))
        key_facts = case.get("grounding_key_facts", [])

        # 1. Retrieval evaluation
        retrieved = retrieve(query, k=K, doc_type="concept")
        retrieved_titles = [r["doc"]["title"] for r in retrieved]

        # Precision@1
        top1_hit = 1.0 if retrieved_titles and retrieved_titles[0] in relevant_docs else 0.0
        p1_scores.append(top1_hit)

        # Precision@K
        relevant_in_k = sum(1 for t in retrieved_titles if t in relevant_docs)
        p_at_k = relevant_in_k / len(retrieved_titles) if retrieved_titles else 0.0
        pK_scores.append(p_at_k)

        # Recall@K
        recall_at_k = relevant_in_k / len(relevant_docs) if relevant_docs else 1.0
        recall_scores.append(min(1.0, recall_at_k))

        # MRR
        rr = 0.0
        for rank, title in enumerate(retrieved_titles, start=1):
            if title == target_doc or title in relevant_docs:
                rr = 1.0 / rank
                break
        mrr_scores.append(rr)

        # 2. Answer Generation & Grounding evaluation
        ans_obj = answer_conceptual_query(query)
        answer_text = ans_obj.get("answer", "").lower()
        sources = ans_obj.get("sources", [])

        if sources:
            citation_counts += 1

        supported_facts = 0
        for fact in key_facts:
            if fact.lower() in answer_text:
                supported_facts += 1
        grounding = supported_facts / len(key_facts) if key_facts else 1.0
        grounding_scores.append(grounding)

        status = "PASS" if top1_hit and grounding >= 0.6 else "WARN"
        print(f"[{status}] [{qid}] {query}")
        print(f"       Top-1: '{retrieved_titles[0] if retrieved_titles else 'None'}' (P@1: {top1_hit})")
        print(f"       Recall@{K}: {recall_at_k:.2f} | Grounding: {grounding * 100:.1f}% | Citations: {len(sources)}")

    # Aggregate Metrics
    avg_p1 = (sum(p1_scores) / len(p1_scores)) * 100
    avg_pK = (sum(pK_scores) / len(pK_scores)) * 100
    avg_recall = (sum(recall_scores) / len(recall_scores)) * 100
    mrr = sum(mrr_scores) / len(mrr_scores)
    avg_grounding = (sum(grounding_scores) / len(grounding_scores)) * 100
    citation_ratio = (citation_counts / len(cases)) * 100

    print("\n-------------------------------------------------------")
    print("  QUANTITATIVE RAG METRICS SUMMARY")
    print("-------------------------------------------------------")
    print(f"  Retrieval Precision@1     : {avg_p1:.1f}%")
    print(f"  Retrieval Precision@{K}     : {avg_pK:.1f}%")
    print(f"  Retrieval Recall@{K}        : {avg_recall:.1f}%")
    print(f"  Mean Reciprocal Rank (MRR) : {mrr:.3f}")
    print(f"  Answer Grounding Score     : {avg_grounding:.1f}%")
    print(f"  Citation Provenance Ratio  : {citation_ratio:.1f}%")
    print("-------------------------------------------------------\n")

    metrics = {
        "precision_at_1": avg_p1,
        "precision_at_k": avg_pK,
        "recall_at_k": avg_recall,
        "mrr": mrr,
        "answer_grounding": avg_grounding,
        "citation_provenance_ratio": citation_ratio,
        "queries_evaluated": len(cases),
    }

    # Output metrics to json file for persistent tracking
    out_file = ROOT / "eval" / "rag_metrics.json"
    out_file.write_text(json.dumps(metrics, indent=2), encoding="utf-8")
    print(f"Metrics saved to {out_file}")

    # Pass criteria: High precision & grounding
    return avg_p1 >= 80.0 and avg_grounding >= 75.0 and mrr >= 0.8


if __name__ == "__main__":
    ok = evaluate_rag()
    sys.exit(0 if ok else 1)

