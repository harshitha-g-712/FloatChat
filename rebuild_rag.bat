@echo off
REM Rebuild the RAG knowledge index (TF-IDF + Gemini embeddings)
REM Requires GEMINI_API_KEY in .env for embedding mode
echo.
echo  FloatChat RAG Index Builder
echo  ===========================
echo.
python scripts\rebuild_rag.py --embeddings
pause

