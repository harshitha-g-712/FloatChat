"""Keep the test-suite's throwaway accounts out of the real auth database."""
import os
import tempfile
import pytest

_tmp = tempfile.mkdtemp(prefix="floatchat_test_auth_")
os.environ.setdefault("AUTH_DB_PATH", os.path.join(_tmp, "auth_test.db"))


def _ocean_db_path():
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    raw = os.environ.get("DB_PATH")
    if raw:
        return raw if os.path.isabs(raw) else os.path.join(root, raw)
    return os.path.join(root, "backend", "floatchat.db")


def pytest_sessionstart(session):
    """Most tests query the ocean database, which is not shipped in the code ZIP.

    Stop with a clear instruction instead of ~300 confusing "no such table" failures.
    Set FLOATCHAT_TESTS_NO_DB=1 to run anyway (only database-free tests will pass).
    """
    if os.environ.get("FLOATCHAT_TESTS_NO_DB") == "1":
        return
    import sqlite3
    path = _ocean_db_path()
    ok = False
    try:
        conn = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
        try:
            ok = conn.execute("SELECT COUNT(*) FROM profiles").fetchone()[0] > 0
        finally:
            conn.close()
    except Exception:
        ok = False
    if not ok:
        pytest.exit(
            "Ocean database not found or empty at %s.\n"
            "Load it once with: python backend/ingestion/fetch_and_load.py --reset  (needs internet)\n"
            "or point DB_PATH at an existing floatchat.db. See README 'Tests'." % path,
            returncode=2,
        )


@pytest.fixture(autouse=True)
def _reset_testclient_rate_limits():
    """Clear in-memory rate limits so high request volume across the test suite doesn't hit 429."""
    try:
        import main
        main._RATE_LIMITS.clear()
        main._LOGIN_ATTEMPTS.clear()
    except Exception:
        pass
    yield
    try:
        import main
        main._RATE_LIMITS.clear()
        main._LOGIN_ATTEMPTS.clear()
    except Exception:
        pass
