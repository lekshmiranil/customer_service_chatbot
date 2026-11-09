"""Read-only look at session_data\\sessions.db. Prints counts and masked previews. Changes nothing."""
import json
import sqlite3
import sys
from pathlib import Path

from src.multilingual import masking

PATH = Path("session_data") / "sessions.db"
if not PATH.exists():
    print("FAIL missing", PATH)
    sys.exit(1)
conn = sqlite3.connect(PATH.resolve().as_uri() + "?mode=ro", uri=True)
conn.row_factory = sqlite3.Row
sessions = conn.execute(
    "SELECT session_id, customer_id, started_at, ended_at, end_reason, state FROM sessions ORDER BY started_at"
).fetchall()
turns = conn.execute("SELECT id, session_id, role, text FROM turns ORDER BY id").fetchall()
print("sessions:", len(sessions), "turns:", len(turns))
print("turns that masking would change:", sum(1 for t in turns if masking.mask(t["text"]) != t["text"]))
held = 0
for s in sessions:
    try:
        state = json.loads(s["state"] or "{}")
    except ValueError:
        state = {}
    if isinstance(state, dict) and state.get("held_text"):
        held += 1
print("sessions with held_text in state:", held)
per = {}
for t in turns:
    per.setdefault(t["session_id"], []).append(t)
for s in sessions:
    mine = per.get(s["session_id"], [])
    print(ascii(s["session_id"]), "customer", ascii(s["customer_id"]), "started", s["started_at"][:19],
          "end", ascii(s["end_reason"] or "-"), "turns", len(mine))
    for t in mine[:2]:
        print("    ", t["role"], ascii(masking.mask(t["text"])[:60]))
conn.close()