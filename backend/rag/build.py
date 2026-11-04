"""
Build or rebuild the FloatChat RAG index.
Usage:
    python -m rag.build                  # TF-IDF only (offline)
    python backend/rag/build.py          # TF-IDF only (offline)
    python backend/rag/build.py --embeddings  # TF-IDF + Gemini embeddings
"""

import argparse
import sys
from pathlib import Path

# Add backend to sys.path
backend_dir = Path(__file__).resolve().parent.parent
if str(backend_dir) not in sys.path:
    sys.path.insert(0, str(backend_dir))

from rag.indexer import build_index

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Build FloatChat RAG index")
    parser.add_argument("--embeddings", action="store_true",
                        help="Also build Gemini embedding index (requires GEMINI_API_KEY)")
    args = parser.parse_args()

    print("Building FloatChat RAG index...")
    if args.embeddings:
        print("  -> Embedding mode enabled (requires GEMINI_API_KEY)")
    build_index(use_embeddings=args.embeddings)
