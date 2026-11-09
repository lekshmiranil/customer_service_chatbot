"""Read-only inspection of the project's SQLite databases, log files and tools folder.

Run from the project root:  python -m tools.inspect_test_data
Writes nothing. Prints folder names, file names, table names, column names and row counts only.
"""
import os
import sqlite3
from datetime import datetime
from pathlib import Path

ROOT = Path.cwd()
SKIP_DIRS = {".venv", "venv", "backups", "__pycache__", ".git", "node_modules", "site-packages"}
DB_SUFFIXES = {".db", ".sqlite", ".sqlite3"}
LOG_SUFFIXES = {".log", ".jsonl"}


def stamp(path):
    return datetime.fromtimestamp(path.stat().st_mtime).strftime("%Y-%m-%d %H:%M")


def walk_files():
    for dirpath, dirnames, filenames in os.walk(ROOT):
        dirnames[:] = [d for d in dirnames if d not in SKIP_DIRS]
        for name in filenames:
            yield Path(dirpath) / name


print("== top-level folders")
for item in sorted(ROOT.iterdir()):
    if item.is_dir() and item.name not in SKIP_DIRS and not item.name.startswith("."):
        print("  " + item.name)

print("== tools folder (.py files)")
tools = ROOT / "tools"
if tools.is_dir():
    for item in sorted(tools.glob("*.py")):
        print("  " + item.name)
else:
    print("  tools folder not found")

databases = []
logs = []
for path in walk_files():
    suffix = path.suffix.lower()
    if suffix in DB_SUFFIXES:
        databases.append(path)
    elif suffix in LOG_SUFFIXES:
        logs.append(path)

print("== SQLite databases")
if not databases:
    print("  none found")
for path in sorted(databases):
    print("  " + str(path.relative_to(ROOT)) + "  size " + str(path.stat().st_size) + "  modified " + stamp(path))
    try:
        conn = sqlite3.connect(path.as_uri() + "?mode=ro", uri=True)
        try:
            tables = [
                row[0]
                for row in conn.execute(
                    "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name"
                )
            ]
            if not tables:
                print("      no tables")
            for table in tables:
                quoted = '"' + table.replace('"', '""') + '"'
                count = conn.execute("SELECT COUNT(*) FROM " + quoted).fetchone()[0]
                columns = [row[1] for row in conn.execute("PRAGMA table_info(" + quoted + ")")]
                print("      " + table + ": " + str(count) + " rows; columns: " + ", ".join(columns))
        finally:
            conn.close()
    except Exception as exc:
        print("      could not open read-only: " + type(exc).__name__)

print("== log files (.log, .jsonl)")
if not logs:
    print("  none found")
for path in sorted(logs):
    print("  " + str(path.relative_to(ROOT)) + "  size " + str(path.stat().st_size) + "  modified " + stamp(path))