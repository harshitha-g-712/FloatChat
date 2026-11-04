"""Knowledge retrieval regression tests."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))
from rag.indexer import retrieve, answer_conceptual_query

def test_concept_retrieval_excludes_float_metadata():
    results = retrieve('What is an ARGO float?', k=3, min_score=0.0, doc_type='concept')
    assert results
    assert all(r['doc'].get('type') == 'concept' for r in results)

def test_concept_answer_has_source_labels():
    result = answer_conceptual_query('Why is the Bay of Bengal fresher at the surface?')
    assert result
    assert result['sources']
    assert all(s.startswith('[S') for s in result['sources'])
