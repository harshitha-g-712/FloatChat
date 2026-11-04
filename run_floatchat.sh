#!/usr/bin/env bash
set -e

echo "======================================================="
echo "  FloatChat - AI Ocean Data Discovery (One-Click Start)"
echo "======================================================="

# 1. Ensure .env exists
if [ ! -f ".env" ]; then
    echo "[INFO] Copying .env.example to .env..."
    cp .env.example .env
fi

# 2. Check the Python version (3.10+ required; tested on 3.12)
python3 -c "import sys; sys.exit(0 if sys.version_info >= (3, 10) else 1)" || {
    echo "[ERROR] Python 3.10 or newer is required (found: $(python3 --version 2>&1))."
    exit 1
}

# 3. Create virtual environment if missing
if [ ! -d ".venv" ]; then
    echo "[INFO] Creating Python virtual environment in .venv..."
    python3 -m venv .venv
fi

# 3. Activate venv & install requirements
source .venv/bin/activate
echo "[INFO] Checking dependencies..."
pip install -q -r backend/requirements.txt

# 4. Check if database has data
python3 -c "import sqlite3, sys, os; p = os.path.join('backend', 'floatchat.db'); sys.exit(0 if (os.path.exists(p) and sqlite3.connect(p).execute('SELECT COUNT(*) FROM profiles').fetchone()[0] > 0) else 1)" || {
    echo ""
    echo "[WARNING] The database is currently empty."
    echo "To populate real ARGO float data, run: python3 backend/ingestion/fetch_and_load.py --reset"
    echo ""
}

# 5. Run FloatChat Backend + UI
echo "[INFO] Starting FloatChat..."
python3 backend/main.py
