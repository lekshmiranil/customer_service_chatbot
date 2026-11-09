"""Removes the test rows from session_data\\sessions.db. Dry run unless --yes is given.
Refuses when the backup is missing or older than the live file, when any session belongs to a customer other than
TEST_CUSTOMER, or when a turn has no session."""
import sqlite3
import sys
from pathlib import Path

LIVE = Path("session_data") / "sessions.db"
BACKUP = Path("backups") / "sessions_before_cleanup.db"
TEST_CUSTOMER = "cust1"


def counts(path):
    conn = sqlite3.connect(path.resolve().as_uri() + "?mode=ro", uri=True)
    try:
        sessions = conn.execute("SELECT session_id, customer_id FROM sessions").fetchall()
        turns = conn.execute("SELECT session_id FROM turns").fetchall()
    finally:
        conn.close()
    return sessions, turns


def main():
    apply = "--yes" in sys.argv[1:]
    for path in (LIVE, BACKUP):
        if not path.exists():
            print("FAIL missing", path)
            return 1
    sessions, turns = counts(LIVE)
    b_sessions, b_turns = counts(BACKUP)
    print("live:", len(sessions), "sessions,", len(turns), "turns; backup:", len(b_sessions), "sessions,", len(b_turns), "turns")
    if len(sessions) > len(b_sessions) or len(turns) > len(b_turns):
        print("FAIL the live file has rows the backup does not; take a new backup first")
        return 1
    others = sorted({c for _, c in sessions if c != TEST_CUSTOMER})
    if others:
        print("FAIL sessions belong to other customers:", [ascii(c) for c in others], "; nothing deleted")
        return 1
    known = {s for s, _ in sessions}
    orphans = [s for (s,) in turns if s not in known]
    if orphans:
        print("FAIL", len(orphans), "turns have no session; nothing deleted")
        return 1
    print("all", len(sessions), "sessions belong to", TEST_CUSTOMER)
    if not apply:
        print("dry run: nothing deleted. Run again with --yes to delete.")
        return 0
    conn = sqlite3.connect(str(LIVE), timeout=10)
    try:
        with conn:
            conn.execute("DELETE FROM turns")
            conn.execute("DELETE FROM sessions")
        conn.execute("VACUUM")
        left = (conn.execute("SELECT COUNT(*) FROM sessions").fetchone()[0],
                conn.execute("SELECT COUNT(*) FROM turns").fetchone()[0])
    finally:
        conn.close()
    if left != (0, 0):
        print("FAIL rows remain:", left)
        return 1
    print("ok   deleted; sessions and turns are now empty (the VACUUM removes the old text from the file)")
    return 0


if __name__ == "__main__":
    sys.exit(main())