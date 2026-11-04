"""
FloatChat – RAG Indexer & Retriever (Embedding + TF-IDF)
========================================================
Dual-mode document indexer and retriever:
- **Embedding mode** (default when Gemini API key is set): Uses Gemini
  text-embedding-004 for semantic similarity search, with LLM-generated
  answers grounded in retrieved context (true RAG pipeline).
- **TF-IDF mode** (offline fallback): 100% offline keyword-based retrieval.
  Zero paid APIs, zero quota usage, zero network dependencies.

Indexes conceptual knowledge base (markdown files) and float metadata from SQLite.
"""

import os
import json
import sqlite3
import re
import math
import logging
from pathlib import Path
from typing import List, Dict, Any, Optional

logger = logging.getLogger("floatchat.rag")

RAG_DIR = Path(__file__).resolve().parent
KNOWLEDGE_DIR = RAG_DIR / "knowledge"
DOCS_PATH = RAG_DIR / "docs.json"
INDEX_PATH = RAG_DIR / "tfidf_index.json"
EMBEDDING_INDEX_PATH = RAG_DIR / "embedding_index.json"


def _tokenize(text: str) -> List[str]:
    """Simple lowercase alphanumeric tokenizer with stopword filtering."""
    stopwords = {
        "a", "about", "above", "after", "again", "against", "all", "am", "an", "and",
        "any", "are", "as", "at", "be", "because", "been", "before", "being", "below",
        "between", "both", "but", "by", "could", "did", "do", "does", "doing", "down",
        "during", "each", "few", "for", "from", "further", "had", "has", "have", "having",
        "he", "her", "here", "hers", "herself", "him", "himself", "his", "how", "i", "if",
        "in", "into", "is", "it", "its", "itself", "me", "more", "most", "my", "myself",
        "no", "nor", "not", "of", "off", "on", "once", "only", "or", "other", "ought",
        "our", "ours", "ourselves", "out", "over", "own", "same", "she", "should", "so",
        "some", "such", "than", "that", "the", "their", "theirs", "them", "themselves",
        "then", "there", "these", "they", "this", "those", "through", "to", "too", "under",
        "until", "up", "very", "was", "we", "were", "what", "when", "where", "which",
        "while", "who", "whom", "why", "with", "would", "you", "your", "yours"
    }
    tokens = re.findall(r"[a-z0-9]+", text.lower())
    normalized = []
    for token in tokens:
        if token in stopwords or len(token) <= 1:
            continue
        # Small deterministic plural/gerund normalizer to bridge monsoon/monsoons,
        # measure/measuring and profile/profiles without adding an NLP dependency.
        if len(token) > 5 and token.endswith("ies"):
            token = token[:-3] + "y"
        elif len(token) > 5 and token.endswith("ing"):
            token = token[:-3]
        elif len(token) > 4 and token.endswith("es"):
            token = token[:-2]
        elif len(token) > 3 and token.endswith("s") and not token.endswith("ss"):
            token = token[:-1]
        normalized.append(token)
    return normalized


# ── Document Loading ─────────────────────────────────────────────────────────

def _load_knowledge_docs() -> List[Dict[str, Any]]:
    """Load markdown knowledge files from the knowledge directory."""
    docs: List[Dict[str, Any]] = []
    if not KNOWLEDGE_DIR.exists():
        return docs

    for md_path in sorted(KNOWLEDGE_DIR.glob("*.md")):
        try:
            content = md_path.read_text(encoding="utf-8")
            title = md_path.stem.replace("_", " ").title()
            lines = content.strip().split("\n")
            if lines and lines[0].startswith("# "):
                title = lines[0].replace("# ", "").strip()

            docs.append({
                "id": f"kb_{md_path.stem}",
                "title": title,
                "content": content,
                "source": title,
                "type": "concept",
            })
        except Exception as e:
            logger.warning("Error reading %s: %s", md_path, e)
    return docs


def _load_float_metadata(db_path: str) -> List[Dict[str, Any]]:
    """Load float profile metadata from the SQLite database."""
    docs: List[Dict[str, Any]] = []
    if not os.path.exists(db_path):
        return docs

    try:
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        rows = conn.execute("""
            SELECT 
                platform,
                COUNT(DISTINCT id) as profile_count,
                MIN(timestamp) as first_date,
                MAX(timestamp) as last_date,
                MIN(lat) as min_lat,
                MAX(lat) as max_lat,
                MIN(lon) as min_lon,
                MAX(lon) as max_lon,
                region
            FROM profiles
            GROUP BY platform
        """).fetchall()

        for r in rows:
            plat = r["platform"]
            p_cnt = r["profile_count"]
            d_min = (r["first_date"] or "")[:10]
            d_max = (r["last_date"] or "")[:10]
            min_lat, max_lat = r["min_lat"] or 0, r["max_lat"] or 0
            min_lon, max_lon = r["min_lon"] or 0, r["max_lon"] or 0
            region = r["region"] or "Bay of Bengal"

            content = (
                f"ARGO Float Platform {plat} in {region}. "
                f"Recorded {p_cnt} profiles between {d_min} and {d_max}. "
                f"Bounding coordinates: latitude {min_lat:.2f} to {max_lat:.2f}, "
                f"longitude {min_lon:.2f} to {max_lon:.2f}. "
                f"Measures temperature, salinity, and pressure down to 2000 dbar."
            )

            docs.append({
                "id": f"float_{plat}",
                "title": f"ARGO Float {plat}",
                "content": content,
                "source": f"Float {plat} Summary",
                "type": "float_metadata",
                "platform": plat,
                "lat": (min_lat + max_lat) / 2.0,
                "lon": (min_lon + max_lon) / 2.0,
            })
        conn.close()
    except Exception as e:
        logger.warning("Error loading float metadata for RAG: %s", e)
    return docs


# ── TF-IDF Index (Offline Fallback) ─────────────────────────────────────────

def _build_tfidf_index(docs: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Compute TF-IDF vectors for all documents."""
    N = len(docs)
    if N == 0:
        return {"idf": {}, "doc_vectors": [], "doc_ids": []}

    doc_tokens = [_tokenize(doc["content"] + " " + doc["title"]) for doc in docs]

    # Calculate Document Frequency (DF)
    df: Dict[str, int] = {}
    for tokens in doc_tokens:
        unique_terms = set(tokens)
        for term in unique_terms:
            df[term] = df.get(term, 0) + 1

    # Calculate IDF: log((N + 1) / (df + 1)) + 1
    idf: Dict[str, float] = {}
    for term, freq in df.items():
        idf[term] = math.log((N + 1.0) / (freq + 1.0)) + 1.0

    # Build document vector representations
    doc_vectors: List[Dict[str, float]] = []
    for tokens in doc_tokens:
        tf: Dict[str, float] = {}
        for t in tokens:
            tf[t] = tf.get(t, 0) + 1.0

        vec: Dict[str, float] = {}
        norm_sq = 0.0
        for t, count in tf.items():
            weight = count * idf.get(t, 1.0)
            vec[t] = weight
            norm_sq += weight * weight

        norm = math.sqrt(norm_sq) if norm_sq > 0 else 1.0
        normalized_vec = {t: w / norm for t, w in vec.items()}
        doc_vectors.append(normalized_vec)

    return {
        "idf": idf,
        "doc_vectors": doc_vectors,
        "doc_ids": [d["id"] for d in docs]
    }


# ── Embedding Index (Gemini-powered) ────────────────────────────────────────

def _build_embedding_index(docs: List[Dict[str, Any]]) -> bool:
    """Build an embedding index using Gemini text-embedding-004.

    Returns True if the embedding index was built successfully.
    """
    try:
        from gemini_service import embed_texts
    except ImportError:
        logger.warning("gemini_service not available for embedding index")
        return False

    # Prepare texts for embedding (title + content, truncated)
    texts = []
    for doc in docs:
        text = f"{doc['title']}\n\n{doc['content']}"
        if len(text) > 8000:
            text = text[:8000]
        texts.append(text)

    if not texts:
        return False

    # Embed in batches of 20 (API limit)
    all_embeddings = []
    batch_size = 20
    for i in range(0, len(texts), batch_size):
        batch = texts[i:i + batch_size]
        embeddings = embed_texts(batch)
        if embeddings is None:
            logger.warning("Embedding batch %d failed, falling back to TF-IDF", i // batch_size)
            return False
        all_embeddings.extend(embeddings)

    if len(all_embeddings) != len(docs):
        logger.warning("Embedding count mismatch: %d embeddings for %d docs", len(all_embeddings), len(docs))
        return False

    # Save embedding index
    index_data = {
        "doc_ids": [d["id"] for d in docs],
        "embeddings": all_embeddings,
        "model": "text-embedding-004",
    }
    EMBEDDING_INDEX_PATH.write_text(json.dumps(index_data), encoding="utf-8")
    logger.info("Embedding index built: %d documents embedded", len(docs))
    print(f"Embedding index built: {len(docs)} documents embedded with text-embedding-004.")
    return True


# ── Main Build Function ─────────────────────────────────────────────────────

def build_index(db_path: Optional[str] = None, use_embeddings: bool = False) -> List[Dict[str, Any]]:
    """Build docs and indexes from knowledge files and SQLite DB.

    Args:
        db_path: Path to the ocean database (defaults to config.DB_PATH).
        use_embeddings: If True, also build the Gemini embedding index.
    """
    from config import DB_PATH
    db_file = db_path or str(DB_PATH)

    # Load all documents
    docs = _load_knowledge_docs()
    docs.extend(_load_float_metadata(db_file))

    N = len(docs)
    if N == 0:
        print("No documents found to index.")
        return []

    # Save documents
    DOCS_PATH.write_text(json.dumps(docs, indent=2), encoding="utf-8")

    # Always build TF-IDF (offline fallback)
    tfidf_index = _build_tfidf_index(docs)
    INDEX_PATH.write_text(json.dumps(tfidf_index), encoding="utf-8")
    print(f"TF-IDF index built: {N} documents indexed.")

    # Optionally build embedding index
    if use_embeddings:
        _build_embedding_index(docs)

    print(f"RAG index built successfully: {N} documents indexed.")
    return docs


# ── Retrieval: Embedding-based ──────────────────────────────────────────────

def _cosine_similarity(a: List[float], b: List[float]) -> float:
    """Compute cosine similarity between two vectors."""
    dot = sum(x * y for x, y in zip(a, b))
    norm_a = math.sqrt(sum(x * x for x in a))
    norm_b = math.sqrt(sum(x * x for x in b))
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return dot / (norm_a * norm_b)


def retrieve_by_embedding(query: str, k: int = 3, min_score: float = 0.3,
                          doc_type: Optional[str] = None) -> List[Dict[str, Any]]:
    """Retrieve documents using embedding similarity (semantic search).

    Returns a list of {doc, score, retrieval_method} dicts, or empty list on failure.
    """
    if not EMBEDDING_INDEX_PATH.exists() or not DOCS_PATH.exists():
        return []

    try:
        from gemini_service import embed_query
    except ImportError:
        return []

    # Get query embedding
    query_embedding = embed_query(query)
    if query_embedding is None:
        return []

    try:
        docs = json.loads(DOCS_PATH.read_text(encoding="utf-8"))
        index_data = json.loads(EMBEDDING_INDEX_PATH.read_text(encoding="utf-8"))
    except Exception:
        return []

    embeddings = index_data.get("embeddings", [])
    doc_ids = index_data.get("doc_ids", [])

    if len(embeddings) != len(docs) or len(doc_ids) != len(docs):
        return []

    # Compute similarities
    scores = []
    for idx, doc_emb in enumerate(embeddings):
        if doc_type and docs[idx].get("type") != doc_type:
            continue
        sim = _cosine_similarity(query_embedding, doc_emb)
        if sim > min_score:
            scores.append((sim, idx))

    scores.sort(key=lambda x: x[0], reverse=True)

    results = []
    for score, idx in scores[:k]:
        results.append({
            "doc": docs[idx],
            "score": round(score, 4),
            "retrieval_method": "embedding",
        })
    return results


# ── Retrieval: TF-IDF (Offline) ─────────────────────────────────────────────

def retrieve(query: str, k: int = 3, min_score: float = 0.05, doc_type: Optional[str] = None) -> List[Dict[str, Any]]:
    """Retrieve top k documents matching query using cosine similarity over TF-IDF."""
    if not DOCS_PATH.exists() or not INDEX_PATH.exists():
        build_index()

    if not DOCS_PATH.exists() or not INDEX_PATH.exists():
        return []

    try:
        docs = json.loads(DOCS_PATH.read_text(encoding="utf-8"))
        index_data = json.loads(INDEX_PATH.read_text(encoding="utf-8"))
    except Exception:
        return []

    idf: Dict[str, float] = index_data.get("idf", {})
    doc_vectors: List[Dict[str, float]] = index_data.get("doc_vectors", [])

    q_tokens = _tokenize(query)
    if not q_tokens:
        return []

    # Build query TF-IDF vector
    q_tf: Dict[str, float] = {}
    for t in q_tokens:
        q_tf[t] = q_tf.get(t, 0) + 1.0

    q_vec: Dict[str, float] = {}
    norm_sq = 0.0
    for t, count in q_tf.items():
        weight = count * idf.get(t, 1.0)
        q_vec[t] = weight
        norm_sq += weight * weight

    norm = math.sqrt(norm_sq) if norm_sq > 0 else 1.0
    q_norm_vec = {t: w / norm for t, w in q_vec.items()}

    # Compute cosine similarities
    scores: List[tuple[float, int]] = []
    for idx, d_vec in enumerate(doc_vectors):
        dot = sum(q_norm_vec.get(t, 0.0) * w for t, w in d_vec.items())
        if dot > min_score:
            scores.append((dot, idx))

    scores.sort(key=lambda x: x[0], reverse=True)

    results = []
    for score, idx in scores:
        if doc_type and docs[idx].get("type") != doc_type:
            continue
        results.append({
            "doc": docs[idx],
            "score": round(score, 4),
            "retrieval_method": "tfidf",
        })
        if len(results) >= k:
            break
    return results


# ── Smart Retrieval (Embedding first, TF-IDF fallback) ──────────────────────

def smart_retrieve(query: str, k: int = 3, doc_type: Optional[str] = None) -> List[Dict[str, Any]]:
    """Retrieve documents using the best available method.

    Tries embedding-based retrieval first (semantic), falls back to TF-IDF (keyword).
    """
    # Try embedding retrieval first
    results = retrieve_by_embedding(query, k=k, min_score=0.3, doc_type=doc_type)
    if results:
        logger.info("RAG retrieval: embedding mode (%d results)", len(results))
        return results

    # Fall back to TF-IDF
    results = retrieve(query, k=k, min_score=0.02, doc_type=doc_type)
    if results:
        logger.info("RAG retrieval: TF-IDF fallback (%d results)", len(results))
        for r in results:
            r["retrieval_method"] = "tfidf"
    return results


# ── Conceptual Q&A (with LLM generation when available) ─────────────────────

def answer_conceptual_query(query: str) -> Optional[Dict[str, Any]]:
    """Answer a conceptual question using RAG: retrieve relevant docs, then generate.

    Pipeline:
    1. Retrieve relevant knowledge sections (embedding or TF-IDF)
    2. If Gemini is available: generate an LLM answer grounded in retrieved context
    3. Otherwise: return the best-matching section as a template answer

    Returns {answer, sources, rag_mode} or None.
    """
    # Step 1: Retrieve relevant documents
    results = smart_retrieve(query, k=5, doc_type="concept")
    if not results:
        return None

    retrieval_method = results[0].get("retrieval_method", "tfidf")

    # Step 2: Try LLM-generated answer (true RAG = Retrieval + Generation)
    try:
        from gemini_service import generate_rag_answer, is_gemini_available
        if is_gemini_available():
            context_docs = [r["doc"] for r in results[:3]]
            llm_answer = generate_rag_answer(query, context_docs)
            if llm_answer:
                sources = [f"[S{i+1}] {r['doc'].get('source', r['doc'].get('title', 'Knowledge base'))}"
                          for i, r in enumerate(results[:3])]
                return {
                    "answer": llm_answer,
                    "sources": sources,
                    "rag_mode": f"embedding+llm" if retrieval_method == "embedding" else "tfidf+llm",
                }
    except Exception as e:
        logger.warning("LLM RAG generation failed, falling back to template: %s", e)

    # Step 3: Fallback — section-level template answer (no LLM)
    return _template_conceptual_answer(query, results, retrieval_method)


def _template_conceptual_answer(query: str, results: List[Dict[str, Any]],
                                 retrieval_method: str) -> Optional[Dict[str, Any]]:
    """Fallback: return the best-matching section without LLM generation."""
    query_terms = set(_tokenize(query))
    candidates = []
    for result in results:
        doc = result["doc"]
        content = doc.get("content", "")
        sections = []
        current_heading = doc.get("title", "Ocean knowledge")
        current_lines = []
        for line in content.splitlines():
            if line.startswith("#"):
                if current_lines:
                    sections.append((current_heading, "\n".join(current_lines).strip()))
                current_heading = line.lstrip("# ").strip() or current_heading
                current_lines = []
            else:
                current_lines.append(line)
        if current_lines:
            sections.append((current_heading, "\n".join(current_lines).strip()))
        if not sections and content.strip():
            sections = [(doc.get("title", "Ocean knowledge"), content.strip())]

        for heading, section_text in sections:
            if not section_text.strip():
                continue
            terms = set(_tokenize(heading + " " + section_text))
            if not terms:
                continue
            overlap = len(query_terms & terms) / max(1, len(query_terms))
            heading_terms = set(_tokenize(heading))
            heading_bonus = 0.25 * len(query_terms & heading_terms) / max(1, len(query_terms))
            score = overlap + heading_bonus + float(result.get("score", 0)) * 0.15
            candidates.append((score, heading, section_text, doc.get("source", doc.get("title", "Knowledge base"))))

    if not candidates:
        best = results[0]["doc"]
        chosen_heading, chosen_text = best.get("title", "Ocean knowledge"), best.get("content", "")
        source = best.get("source", best.get("title", "Knowledge base"))
    else:
        candidates.sort(key=lambda item: item[0], reverse=True)
        score, chosen_heading, chosen_text, source = candidates[0]
        if score < 0.035:
            return None

    content = chosen_text.strip()
    content = re.sub(r"^#{1,6}\s*", "", content, flags=re.MULTILINE)
    content = re.sub(r"^\s*[-*+]\s+", "• ", content, flags=re.MULTILINE)
    content = re.sub(r"\*\*(.*?)\*\*", r"\1", content)
    content = re.sub(r"`([^`]*)`", r"\1", content)
    return {
        "answer": (f"{chosen_heading}\n\n" if chosen_heading.lower() not in content.lower() else "") + content,
        "sources": [f"[S1] {source}"],
        "rag_mode": retrieval_method,
    }
