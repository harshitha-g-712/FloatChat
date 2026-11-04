@echo off
setlocal

echo =======================================================
echo   FloatChat - Fetch Real ARGO Ocean Data
echo =======================================================

if exist .venv\Scripts\activate.bat (
    call .venv\Scripts\activate.bat
)

echo [INFO] Running ARGO data ingestion...
python backend\ingestion\fetch_and_load.py --reset

echo [INFO] Rebuilding offline RAG knowledge index...
python backend\rag\build.py

echo.
echo [SUCCESS] ARGO ocean data and RAG index successfully loaded!
pause
