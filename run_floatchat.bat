@echo off
setlocal enabledelayedexpansion

echo =======================================================
echo   FloatChat - AI Ocean Data Discovery (One-Click Start)
echo =======================================================

REM 1. Ensure .env exists
if not exist .env (
    echo [INFO] Copying .env.example to .env...
    copy .env.example .env >nul
)

REM 2. Create virtual environment if missing
if not exist .venv (
    echo [INFO] Creating Python virtual environment in .venv...
    python -m venv .venv
    if errorlevel 1 (
        echo [ERROR] Failed to create virtual environment. Ensure Python 3.10 or newer is installed (tested on 3.12).
        pause
        exit /b 1
    )
)

REM 3. Activate venv & install/update requirements
call .venv\Scripts\activate.bat
echo [INFO] Checking dependencies...
python -m pip install -q --upgrade pip
python -m pip install -q -r backend\requirements.txt

REM 4. Check if database has data
python -c "import sqlite3, sys, os; p = os.path.join('backend', 'floatchat.db'); sys.exit(0 if (os.path.exists(p) and sqlite3.connect(p).execute('SELECT COUNT(*) FROM profiles').fetchone()[0] > 0) else 1)"
if errorlevel 1 (
    echo.
    echo [WARNING] The database is currently empty.
    echo To populate real ARGO float data, run fetch_data.bat.
    echo.
)

REM 5. Run FloatChat Backend + UI
echo [INFO] Starting FloatChat...
python backend\main.py

pause
