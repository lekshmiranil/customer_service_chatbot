"""Session storage in SQLite (standard library). Every query filters by session id, so simultaneous customers never
see each other's rows. The clock is always an argument. Plain Python, no Streamlit. Functions here can raise on a
broken database; bridge.py catches that.

A session ends after inactivity_minutes without a message. A customer who returns within restore_window_hours of
their last message gets the summary of the previous session; otherwise a new session starts. The window is measured
from the last message of the previous session."""
import json
import os
import sqlite3
import uuid
from datetime import datetime, timedelta, timezone

from src.multilingual import config as mconfig
from src.multilingual import summary as summ

UTC = timezone.utc
SCHEMA = """
CREATE TABLE IF NOT EXISTS sessions (
  session_id TEXT PRIMARY KEY,
  customer_id TEXT NOT NULL DEFAULT '',
  started_at TEXT NOT NULL,
  last_active_at TEXT NOT NULL,
  ended_at TEXT,
  end_reason TEXT,
  restored_from TEXT,
  state TEXT NOT NULL DEFAULT '{}',
  summary TEXT
);
CREATE TABLE IF NOT EXISTS turns (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  session_id TEXT NOT NULL,
  role TEXT NOT NULL,
  text TEXT NOT NULL,
  language TEXT,
  at TEXT NOT NULL,
  meta TEXT
);
CREATE INDEX IF NOT EXISTS idx_turns_session ON turns(session_id, id);
CREATE INDEX IF NOT EXISTS idx_sessions_customer ON sessions(customer_id);
"""


def new_session_id():
    return "s_" + uuid.uuid4().hex[:16]


def utc_now(now=None):
    """The given time as UTC (a naive time is taken as UTC). MULTILINGUAL_NOW overrides the clock for manual tests."""
    if now is None:
        override = os.getenv("MULTILINGUAL_NOW", "").strip()
        if override:
            try:
                now = datetime.fromisoformat(override)
            except ValueError:
                now = None
    if now is None:
        return datetime.now(UTC)
    if now.tzinfo is None:
        return now.replace(tzinfo=UTC)
    return now.astimezone(UTC)


def _iso(moment):
    return moment.astimezone(UTC).isoformat()


def _parse(value):
    moment = datetime.fromisoformat(value)
    return moment if moment.tzinfo else moment.replace(tzinfo=UTC)


def _loads(text):
    try:
        data = json.loads(text) if text else {}
    except ValueError:
        return {}
    return data if isinstance(data, dict) else {}


def connect(path=None):
    target = mconfig.db_path(path)
    os.makedirs(os.path.dirname(os.path.abspath(target)), exist_ok=True)
    conn = sqlite3.connect(target, timeout=10)
    conn.row_factory = sqlite3.Row
    conn.executescript(SCHEMA)
    return conn


def _row(row):
    if row is None:
        return None
    data = dict(row)
    data["state"] = _loads(data.get("state"))
    data["summary"] = _loads(data.get("summary")) if data.get("summary") else None
    return data


def get_session(conn, session_id):
    if not session_id:
        return None
    return _row(conn.execute("SELECT * FROM sessions WHERE session_id = ?", (session_id,)).fetchone())


def start_session(conn, session_id, customer_id, now, state=None, restored_from=""):
    stamp = _iso(now)
    conn.execute(
        "INSERT INTO sessions (session_id, customer_id, started_at, last_active_at, restored_from, state) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        (session_id, customer_id, stamp, stamp, restored_from or "", json.dumps(state or {}, ensure_ascii=False)),
    )
    conn.commit()
    return get_session(conn, session_id)


def save_state(conn, session_id, state):
    conn.execute("UPDATE sessions SET state = ? WHERE session_id = ?",
                 (json.dumps(state, ensure_ascii=False), session_id))
    conn.commit()


def add_turn(conn, session_id, role, text, language, now, meta=None, max_turns=40):
    """Stores one turn, marks the session active and keeps only the newest max_turns turns of this session."""
    stamp = _iso(now)
    conn.execute(
        "INSERT INTO turns (session_id, role, text, language, at, meta) VALUES (?, ?, ?, ?, ?, ?)",
        (session_id, role, str(text or ""), language or "", stamp, json.dumps(meta or {}, ensure_ascii=False)),
    )
    conn.execute("UPDATE sessions SET last_active_at = ? WHERE session_id = ? AND ended_at IS NULL", (stamp, session_id))
    conn.execute(
        "DELETE FROM turns WHERE session_id = ? AND id NOT IN "
        "(SELECT id FROM turns WHERE session_id = ? ORDER BY id DESC LIMIT ?)",
        (session_id, session_id, int(max_turns)),
    )
    conn.commit()


def recent_turns(conn, session_id, limit=20):
    rows = conn.execute(
        "SELECT role, text, language, at, meta FROM turns WHERE session_id = ? ORDER BY id DESC LIMIT ?",
        (session_id, int(limit)),
    ).fetchall()
    turns = []
    for row in reversed(rows):
        item = dict(row)
        item["meta"] = _loads(item.get("meta"))
        turns.append(item)
    return turns


def count_turns(conn, session_id):
    return conn.execute("SELECT COUNT(*) FROM turns WHERE session_id = ?", (session_id,)).fetchone()[0]


def close_session(conn, session_id, ended_at, reason):
    """Ends a session and stores its summary. A session that is already ended is left unchanged."""
    row = get_session(conn, session_id)
    if row is None or row["ended_at"]:
        return row
    built = summ.build(row["state"], _iso(ended_at), reason)
    conn.execute(
        "UPDATE sessions SET ended_at = ?, end_reason = ?, summary = ? WHERE session_id = ?",
        (_iso(ended_at), reason, json.dumps(built, ensure_ascii=False), session_id),
    )
    conn.commit()
    return get_session(conn, session_id)


def expire_idle(conn, now, cfg, customer_id=None):
    """Ends every active session that has been idle for inactivity_minutes or more. The end time recorded is the
    last message plus the timeout. Returns the ids that were ended."""
    limit = timedelta(minutes=cfg["session"]["inactivity_minutes"])
    query = "SELECT session_id, last_active_at FROM sessions WHERE ended_at IS NULL"
    args = ()
    if customer_id:
        query += " AND customer_id = ?"
        args = (customer_id,)
    closed = []
    for row in conn.execute(query, args).fetchall():
        last = _parse(row["last_active_at"])
        if now - last >= limit:
            close_session(conn, row["session_id"], last + limit, "inactivity")
            closed.append(row["session_id"])
    return closed


def sweep(conn, now, cfg):
    """Ends all idle sessions of all customers (used by an optional background check and by the evaluation)."""
    return expire_idle(conn, utc_now(now), cfg)


def _within_window(row, now, cfg):
    return now - _parse(row["last_active_at"]) <= timedelta(hours=cfg["session"]["restore_window_hours"])


def find_restorable(conn, customer_id, now, cfg, exclude=()):
    """The most recent ended session of this customer if it is inside the restore window and has content."""
    if not customer_id:
        return None
    rows = [_row(r) for r in conn.execute(
        "SELECT * FROM sessions WHERE customer_id = ? AND ended_at IS NOT NULL", (customer_id,)).fetchall()]
    rows = [r for r in rows if r["session_id"] not in exclude]
    if not rows:
        return None
    latest = max(rows, key=lambda r: _parse(r["last_active_at"]))
    if _within_window(latest, now, cfg) and summ.has_content(latest.get("summary")):
        return latest
    return None


def resolve_session(conn, session_id, customer_id, now, cfg):
    """Finds or creates the session for this message. Returns a dict with session, status ('active', 'restored' or
    'new'), notice ('', 'restored' or 'expired_new'), summary (the restored summary or None) and previous_session_id."""
    now = utc_now(now)
    customer_id = str(customer_id or "").strip()
    default_language = cfg.get("default_language", "en")
    out = {"session": None, "status": "new", "notice": "", "summary": None, "previous_session_id": ""}
    row = get_session(conn, session_id)
    old = None
    changed = False
    if row and not row["ended_at"]:
        last = _parse(row["last_active_at"])
        timeout = timedelta(minutes=cfg["session"]["inactivity_minutes"])
        if now - last >= timeout:
            old = close_session(conn, row["session_id"], last + timeout, "inactivity")
        elif customer_id and row["customer_id"] and row["customer_id"] != customer_id:
            old = close_session(conn, row["session_id"], now, "customer_changed")
            changed = True
        else:
            if customer_id and not row["customer_id"]:
                conn.execute("UPDATE sessions SET customer_id = ? WHERE session_id = ?", (customer_id, row["session_id"]))
                conn.commit()
            out["status"] = "active"
            out["session"] = get_session(conn, row["session_id"])
            return out
    elif row:
        old = row
    expire_idle(conn, now, cfg, customer_id=customer_id)
    candidates = []
    if old and not changed and old.get("summary") and _within_window(old, now, cfg) and summ.has_content(old["summary"]):
        candidates.append(old)
    other = find_restorable(conn, customer_id, now, cfg, exclude=(row["session_id"],) if row else ())
    if other:
        candidates.append(other)
    previous = max(candidates, key=lambda r: _parse(r["last_active_at"])) if candidates else None
    new_id = session_id if (session_id and row is None) else new_session_id()
    if previous:
        state = summ.carry_state(previous["summary"], default_language)
        out["status"], out["notice"], out["summary"] = "restored", "restored", previous["summary"]
        out["previous_session_id"] = previous["session_id"]
    else:
        state = summ.empty_state(default_language)
        if old and not changed:
            out["notice"] = "expired_new"
    out["session"] = start_session(conn, new_id, customer_id or (old["customer_id"] if old and not changed else ""),
                                   now, state, previous["session_id"] if previous else "")
    return out


def session_status(conn, session_id, now, cfg):
    """'active', 'expired' (idle past the timeout, not yet closed), 'ended' or 'unknown'. Read only."""
    row = get_session(conn, session_id)
    if row is None:
        return "unknown"
    if row["ended_at"]:
        return "ended"
    idle = utc_now(now) - _parse(row["last_active_at"])
    return "expired" if idle >= timedelta(minutes=cfg["session"]["inactivity_minutes"]) else "active"