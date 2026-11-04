"""Packaging script: Create a clean distributable archive excluding database and secret files."""
import os
import zipfile
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent

EXCLUDE_DIRS = {
    "__pycache__", ".pytest_cache", ".venv", "venv", ".git", ".vscode", ".idea", "logs", "dist", "build"
}

EXCLUDE_FILES = {
    ".env", "floatchat.db", "floatchat_auth.db", "non_existent.db"
}

EXCLUDE_EXTENSIONS = {
    ".db", ".sqlite", ".sqlite3", ".log", ".pyc", ".swp", ".zip", ".tar", ".gz"
}


def should_include(rel_path: Path) -> bool:
    if isinstance(rel_path, str):
        rel_path = Path(rel_path)
    for part in rel_path.parts:
        if part in EXCLUDE_DIRS:
            return False
    if rel_path.name in EXCLUDE_FILES or rel_path.name.lower() == "non_existent.db":
        return False
    # Any .env variant (".env.local", ".env.production", ...) except the template is a secret.
    if rel_path.name.startswith(".env") and rel_path.name != ".env.example":
        return False
    if rel_path.suffix.lower() in EXCLUDE_EXTENSIONS or rel_path.name.lower().endswith(".db"):
        return False
    return True


def package_distributable(output_zip: str = "dist/floatchat_dist.zip") -> str:
    out_path = PROJECT_ROOT / output_zip
    out_path.parent.mkdir(parents=True, exist_ok=True)

    with zipfile.ZipFile(out_path, "w", zipfile.ZIP_DEFLATED) as zf:
        for root, dirs, files in os.walk(PROJECT_ROOT):
            dirs[:] = [d for d in dirs if d not in EXCLUDE_DIRS]
            for file in files:
                p = Path(root) / file
                rel = p.relative_to(PROJECT_ROOT)
                if should_include(rel):
                    zf.write(p, rel)

    _verify_clean(out_path)
    return str(out_path)


def _verify_clean(archive: Path) -> None:
    """Fail loudly if the finished archive contains a secret, a database or a log."""
    with zipfile.ZipFile(archive) as zf:
        bad = [n for n in zf.namelist()
               if (Path(n).name.startswith(".env") and Path(n).name != ".env.example")
               or n.lower().endswith((".db", ".sqlite", ".sqlite3", ".log"))]
    if bad:
        archive.unlink(missing_ok=True)
        raise RuntimeError(f"Refusing to ship an archive containing private files: {bad}")


if __name__ == "__main__":
    archive = package_distributable()
    print(f"Created clean distributable: {archive}")
