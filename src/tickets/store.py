"""SQLite storage for support tickets (Task 3).

One database file holds tickets, the conversations linked to them, an audit trail of events,
the masked conversation text, and incidents (groups of related tickets). Every public function
takes an open connection from connect(); write sequences run inside transaction(), which uses
BEGIN IMMEDIATE so two sessions cannot create the same ticket at once.

Only masked conversation text is stored. Structured contact fields are kept because follow-up
needs them; they are masked again whenever they are shown in a handoff or a log.
"""
import json
import os
import sqlite3
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path

from src.tickets.business_time import to_utc

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_DB_PATH = PROJECT_ROOT / "ticket_data" / "tickets.db"

ACTIVE_STATUSES = ("pending_information", "open", "assigned", "queued")

SCHEMA = """
CREATE TABLE IF NOT EXISTS incidents (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    created_at TEXT NOT NULL,
    category TEXT,
    label TEXT
);
CREATE TABLE IF NOT EXISTS tickets (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    conversation_id TEXT NOT NULL,
    trigger_reason TEXT,
    status TEXT NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    fields_json TEXT NOT NULL DEFAULT '{}',
    evidence_json TEXT NOT NULL DEFAULT '[]',
    missing_json TEXT NOT NULL DEFAULT '[]',
    follow_up_json TEXT NOT NULL DEFAULT '{}',
    priority TEXT,
    score INTEGER,
    priority_json TEXT,
    sla_class TEXT,
    sla_basis TEXT,
    sla_target_minutes REAL,
    sla_deadline TEXT,
    sla_warning_at TEXT,
    sla_state TEXT,
    sla_fingerprint TEXT,
    assigned_agent TEXT,
    assigned_team TEXT,
    queue_name TEXT,
    routing_reason TEXT,
    queued_until TEXT,
    incident_id INTEGER REFERENCES incidents(id),
    warning_sent_at TEXT,
    escalated_at TEXT,
    escalation_count INTEGER NOT NULL DEFAULT 0,
    resolved_at TEXT
);
CREATE TABLE IF NOT EXISTS conversations (
    conversation_id TEXT PRIMARY KEY,
    ticket_id INTEGER NOT NULL REFERENCES tickets(id),
    relation TEXT NOT NULL,
    linked_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS conversation_turns (
    conversation_id TEXT PRIMARY KEY,
    turns_json TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ticket_id INTEGER NOT NULL REFERENCES tickets(id),
    at TEXT NOT NULL,
    type TEXT NOT NULL,
    detail_json TEXT NOT NULL DEFAULT '{}'
);
CREATE INDEX IF NOT EXISTS idx_tickets_status ON tickets(status);
CREATE INDEX IF NOT EXISTS idx_events_ticket ON events(ticket_id, id);
"""

ALIASES = {
    "fields": "fields_json",
    "evidence": "evidence_json",
    "missing": "missing_json",
    "follow_up": "follow_up_json",
    "priority_detail": "priority_json",
}
JSON_COLUMNS = frozenset(ALIASES.values())
UPDATABLE = frozenset(JSON_COLUMNS | {
    "status", "trigger_reason", "priority", "score", "sla_class", "sla_basis", "sla_target_minutes",
    "sla_deadline", "sla_warning_at", "sla_state", "sla_fingerprint", "assigned_agent", "assigned_team",
    "queue_name", "routing_reason", "queued_until", "incident_id", "warning_sent_at", "escalated_at",
    "escalation_count", "resolved_at",
})


def _json_default(value):
    if isinstance(value, datetime):
        if value.tzinfo is not None:
            return to_utc(value).isoformat(timespec="seconds")
        return value.isoformat(timespec="seconds")
    raise TypeError(f"cannot store {type(value).__name__}")


def dumps(value):
    return json.dumps(value, sort_keys=True, default=_json_default)


def loads(text, default):
    if text is None:
        return default
    return json.loads(text)


def iso(moment):
    """UTC ISO-8601 text with seconds; the one format used for every stored time."""
    return to_utc(moment).isoformat(timespec="seconds")


def parse_iso(text):
    return datetime.fromisoformat(text)


def ticket_label(ticket_id):
    return f"TKT-{int(ticket_id):06d}"


def parse_ticket_label(label):
    prefix, _, number = str(label).partition("-")
    if prefix != "TKT" or not number.isdigit():
        raise ValueError(f"not a ticket id: {label!r}")
    return int(number)


def db_path(path=None):
    if path is not None:
        return Path(path)
    from_env = os.getenv("TICKET_DB_PATH")
    return Path(from_env) if from_env else DEFAULT_DB_PATH


def connect(path=None):
    """Opens the database (creating it and its tables on first use). The caller closes it."""
    target = db_path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(target), timeout=15, isolation_level=None)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys=ON")
    conn.execute("PRAGMA journal_mode=WAL")
    conn.executescript(SCHEMA)
    return conn


@contextmanager
def transaction(conn):
    """All-or-nothing block that takes the write lock up front."""
    conn.execute("BEGIN IMMEDIATE")
    try:
        yield conn
    except BaseException:
        conn.execute("ROLLBACK")
        raise
    conn.execute("COMMIT")


def row_to_ticket(row):
    ticket = dict(row)
    ticket["fields"] = loads(ticket.pop("fields_json"), {})
    ticket["evidence"] = loads(ticket.pop("evidence_json"), [])
    ticket["missing"] = loads(ticket.pop("missing_json"), [])
    ticket["follow_up"] = loads(ticket.pop("follow_up_json"), {})
    ticket["priority_detail"] = loads(ticket.pop("priority_json"), None)
    ticket["ticket_id"] = ticket_label(ticket["id"])
    return ticket


def insert_ticket(conn, conversation_id, trigger_reason, now):
    stamp = iso(now)
    cursor = conn.execute(
        "INSERT INTO tickets (conversation_id, trigger_reason, status, created_at, updated_at) "
        "VALUES (?, ?, 'open', ?, ?)",
        (conversation_id, trigger_reason, stamp, stamp),
    )
    return cursor.lastrowid


def get_ticket(conn, ticket_id):
    row = conn.execute("SELECT * FROM tickets WHERE id = ?", (ticket_id,)).fetchone()
    return row_to_ticket(row) if row else None


def update_ticket(conn, ticket_id, now, touch=True, **changes):
    """Updates whitelisted columns. JSON columns take Python objects. touch=False leaves updated_at alone."""
    assignments, values = [], []
    for key, value in changes.items():
        column = ALIASES.get(key, key)
        if column not in UPDATABLE:
            raise ValueError(f"cannot update column {key!r}")
        if column in JSON_COLUMNS:
            value = dumps(value)
        assignments.append(f"{column} = ?")
        values.append(value)
    if touch:
        assignments.append("updated_at = ?")
        values.append(iso(now))
    if not assignments:
        return
    values.append(ticket_id)
    conn.execute(f"UPDATE tickets SET {', '.join(assignments)} WHERE id = ?", values)


def all_tickets(conn):
    return [row_to_ticket(row) for row in conn.execute("SELECT * FROM tickets ORDER BY id").fetchall()]


def count_tickets(conn):
    return conn.execute("SELECT COUNT(*) FROM tickets").fetchone()[0]


def active_tickets_since(conn, since_iso):
    marks = ",".join("?" for _ in ACTIVE_STATUSES)
    rows = conn.execute(
        f"SELECT * FROM tickets WHERE status IN ({marks}) AND created_at >= ? ORDER BY id",
        (*ACTIVE_STATUSES, since_iso),
    ).fetchall()
    return [row_to_ticket(row) for row in rows]


def assigned_counts(conn):
    """Open tickets per assigned agent (the workload used by routing)."""
    rows = conn.execute(
        "SELECT assigned_agent, COUNT(*) AS total FROM tickets "
        "WHERE status = 'assigned' AND assigned_agent IS NOT NULL GROUP BY assigned_agent"
    ).fetchall()
    return {row["assigned_agent"]: row["total"] for row in rows}


def get_conversation_link(conn, conversation_id):
    row = conn.execute("SELECT * FROM conversations WHERE conversation_id = ?", (conversation_id,)).fetchone()
    return dict(row) if row else None


def link_conversation(conn, conversation_id, ticket_id, relation, now):
    conn.execute(
        "INSERT INTO conversations (conversation_id, ticket_id, relation, linked_at) VALUES (?, ?, ?, ?)",
        (conversation_id, ticket_id, relation, iso(now)),
    )


def conversations_of(conn, ticket_id):
    rows = conn.execute(
        "SELECT conversation_id, relation FROM conversations WHERE ticket_id = ? ORDER BY linked_at, conversation_id",
        (ticket_id,),
    ).fetchall()
    return [dict(row) for row in rows]


def save_conversation_turns(conn, conversation_id, turns, now):
    """Stores the masked turns; returns True when they differ from what was stored."""
    new_text = dumps(turns)
    row = conn.execute(
        "SELECT turns_json FROM conversation_turns WHERE conversation_id = ?", (conversation_id,)
    ).fetchone()
    if row is not None and row["turns_json"] == new_text:
        return False
    conn.execute(
        "INSERT OR REPLACE INTO conversation_turns (conversation_id, turns_json, updated_at) VALUES (?, ?, ?)",
        (conversation_id, new_text, iso(now)),
    )
    return True


def get_conversation_turns(conn, conversation_id):
    row = conn.execute(
        "SELECT turns_json FROM conversation_turns WHERE conversation_id = ?", (conversation_id,)
    ).fetchone()
    return loads(row["turns_json"], []) if row else []


def add_event(conn, ticket_id, event_type, at, **detail):
    conn.execute(
        "INSERT INTO events (ticket_id, at, type, detail_json) VALUES (?, ?, ?, ?)",
        (ticket_id, iso(at), event_type, dumps(detail)),
    )


def list_events(conn, ticket_id):
    rows = conn.execute("SELECT * FROM events WHERE ticket_id = ? ORDER BY id", (ticket_id,)).fetchall()
    return [
        {"id": row["id"], "at": row["at"], "type": row["type"], "detail": loads(row["detail_json"], {})}
        for row in rows
    ]


def create_incident(conn, now, category, label):
    cursor = conn.execute(
        "INSERT INTO incidents (created_at, category, label) VALUES (?, ?, ?)", (iso(now), category, label)
    )
    return cursor.lastrowid


def incident_ticket_ids(conn, incident_id):
    rows = conn.execute("SELECT id FROM tickets WHERE incident_id = ? ORDER BY id", (incident_id,)).fetchall()
    return [row["id"] for row in rows]