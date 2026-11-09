"""Removes test rows from session_data\\sessions.db. Dry run unless --yes is given.
Refuses when the backup does not match the live file, when any session belongs to a customer outside ALLOWED,
or when a turn has no session."""
import sqlite3
import sys
from pathlib import Path

from src.multilingual import masking

LIVE = Path("session_data") / "sessions.db"
BACKUP = Path("backups") / "sessions_before_second_cleanup.db"
ALLOWED = {"cust1", ""}


def load(path):
    conn = sqlite3.connect(path.resolve().as_uri() + "?mode=ro", uri=True)
    try:
        sessions = conn.execute("SELECT session_id, customer_id, started_at FROM sessions ORDER BY started_at").fetchall()
        turns = conn.execute("SELECT session_id, role, text FROM turns ORDER BY id").fetchall()
    finally:
        conn.close()
    return sessions, turns


def main():
    apply = "--yes" in sys.argv[1:]
    for path in (LIVE, BACKUP):
        if not path.exists():
            print("FAIL missing", path)
            return 1
    sessions, turns = load(LIVE)
    b_sessions, b_turns = load(BACKUP)
    print("live:", len(sessions), "sessions,", len(turns), "turns; backup:", len(b_sessions), "sessions,", len(b_turns), "turns")
    if (len(sessions), len(turns)) != (len(b_sessions), len(b_turns)):
        print("FAIL the backup does not match the live file; take a new backup first")
        return 1
    others = sorted({c for _, c, _ in sessions if c not in ALLOWED})
    if others:
        print("FAIL sessions belong to other customers:", [ascii(c) for c in others], "; nothing deleted")
        return 1
    known = {s for s, _, _ in sessions}
    if [1 for s, _, _ in turns if s not in known]:
        print("FAIL some turns have no session; nothing deleted")
        return 1
    for session_id, customer, started in sessions:
        first = next((t for s, r, t in turns if s == session_id and r == "customer"), "")
        print("  ", ascii(session_id), "customer", ascii(customer), "started", started[:19], "first message", ascii(masking.mask(first)[:50]))
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
    print("ok   deleted; sessions and turns are now empty")
    return 0


if __name__ == "__main__":
    sys.exit(main())