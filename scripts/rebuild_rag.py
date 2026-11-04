#!/usr/bin/env python3
"""Rebuild the RAG knowledge index (TF-IDF + optional Gemini embeddings).

Usage
-----
    # TF-IDF only (no API key needed)
    python scripts/rebuild_rag.py

    # TF-IDF + embedding index (requires GEMINI_API_KEY in .env or environment)
    python scripts/rebuild_rag.py --embeddings

The embedding index is stored at backend/rag/embedding_index.json.
"""
import os
import sys
import subprocess

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BACKEND = os.path.join(ROOT, "backend")


def main():
    use_embeddings = "--embeddings" in sys.argv

    if use_embeddings:
        # Check for API key
        from dotenv import load_dotenv
        load_dotenv(os.path.join(ROOT, ".env"))
        key = os.environ.get("GEMINI_API_KEY", "").strip()
        if not key:
            print("ERROR: GEMINI_API_KEY is not set.")
            print("Set it in .env or as an environment variable to build the embedding index.")
            print("Run without --embeddings to build the TF-IDF index only.")
            sys.exit(1)
        print("🔑 Gemini API key found. Building TF-IDF + embedding index...")
    else:
        print("📚 Building TF-IDF index (no embeddings)...")

    cmd = [sys.executable, "-m", "rag.build"]
    if use_embeddings:
        cmd.append("--embeddings")

    result = subprocess.run(cmd, cwd=BACKEND)
    if result.returncode == 0:
        print("\n✅ RAG index rebuilt successfully!")
        if use_embeddings:
            idx_path = os.path.join(BACKEND, "rag", "embedding_index.json")
            if os.path.exists(idx_path):
                size_kb = os.path.getsize(idx_path) / 1024
                print(f"   Embedding index: {idx_path} ({size_kb:.1f} KB)")
    else:
        print(f"\n❌ Build failed with exit code {result.returncode}")
        sys.exit(result.returncode)


if __name__ == "__main__":
    main()

