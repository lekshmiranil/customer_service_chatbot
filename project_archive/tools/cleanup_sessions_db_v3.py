"""Cleanup of the multilingual session store (session_data\\sessions.db).

Run from the project root, with Streamlit closed:
  python -m tools.cleanup_sessions_db_v3            dry run: prints counts, changes nothing
  python -m tools.cleanup_sessions_db_v3 --apply    backup, then deletes every row in turns and sessions

Touches only the tables sessions and turns of this one file. It never touches the
ticket store, the sentiment data or any log. Prints no message text.
"""
import sqlite3
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path.cwd()
DB = ROOT / "session_data" / "sessions.db"
BACKUPS = ROOT / "backups"
APPLY = "--apply" in sys.argv[1:]


def refuse(message):
    print("REFUSED: " + message)
    print("Nothing was changed.")
    sys.exit(1)


def counts(conn):
    sessions = conn.execute("SELECT COUNT(*) FROM sessions").fetchone()[0]
    turns = conn.execute("SELECT COUNT(*) FROM turns").fetchone()[0]
    return sessions, turns


if not DB.is_file():
    refuse("file not found: " + str(DB))

try:
    conn = sqlite3.connect(str(DB), timeout=5, isolation_level=None)
    tables = {row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
except Exception as exc:
    refuse("cannot open the database: " + type(exc).__name__)

for table in ("sessions", "turns"):
    if table not in tables:
        refuse("table missing: " + table)
    columns = {row[1] for row in conn.execute("PRAGMA table_info(" + table + ")")}
    if "session_id" not in columns:
        refuse("column session_id missing in " + table)

before = counts(conn)
orphans = conn.execute(
    "SELECT COUNT(*) FROM turns WHERE session_id NOT IN (SELECT session_id FROM sessions)"
).fetchone()[0]
print("sessions: " + str(before[0]) + ", turns: " + str(before[1]) + ", turns without a session: " + str(orphans))

rows = conn.execute(
    "SELECT s.started_at, s.last_active_at, s.customer_id, s.end_reason, "
    "(SELECT COUNT(*) FROM turns t WHERE t.session_id = s.session_id) "
    "FROM sessions s ORDER BY s.started_at"
).fetchall()
for started, last_active, customer, reason, turn_count in rows:
    print(
        "  started " + str(started) + "  last active " + str(last_active)
        + "  customer id " + ("set" if customer else "empty")
        + "  end reason " + str(reason or "-") + "  turns " + str(turn_count)
    )

if not APPLY:
    print("Dry run only. Nothing was changed. Run again with --apply to delete these rows.")
    sys.exit(0)

BACKUPS.mkdir(exist_ok=True)
target = BACKUPS / ("sessions.db.before_cleanup_" + datetime.now().strftime("%Y%m%d_%H%M%S"))
try:
    dest = sqlite3.connect(str(target))
    try:
        conn.backup(dest)
    finally:
        dest.close()
    check = sqlite3.connect(str(target))
    try:
        backed_up = counts(check)
    finally:
        check.close()
except Exception as exc:
    refuse("backup failed (" + type(exc).__name__ + "); the database was not changed")
if backed_up != before:
    refuse("backup counts " + str(backed_up) + " differ from the database " + str(before))
print("backup written: " + str(target))

try:
    conn.execute("BEGIN IMMEDIATE")
    conn.execute("DELETE FROM turns")
    conn.execute("DELETE FROM sessions")
    conn.execute("COMMIT")
except Exception as exc:
    try:
        conn.execute("ROLLBACK")
    except Exception:
        pass
    print("DELETE FAILED and was rolled back: " + type(exc).__name__)
    sys.exit(1)

after = counts(conn)
conn.close()
if after != (0, 0):
    print("VERIFY FAILED: counts after delete " + str(after))
    sys.exit(1)
print("deleted; sessions: 0, turns: 0")