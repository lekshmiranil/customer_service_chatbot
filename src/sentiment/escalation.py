"""Escalation rules and the SQLite store. Every function takes the clock as an argument.

Conditions: repeated_negative (3 negative-type messages among the last 5), high_risk:<category>
(escalates even when the message is calm) and unresolved_timeout (negative for more than 15 minutes).
Outside business hours an urgent complaint enters the on_call queue and a normal complaint is scheduled
for the next working day. Every row stores a reason, the activated condition and a masked summary.
"""
import json
import os
import sqlite3
from contextlib import closing
from datetime import datetime, timedelta, timezone
from pathlib import Path

from src.tickets.business_time import is_business_open, next_business_open
from src.tickets.masking import mask_text

PROJECT_ROOT = Path(__file__).resolve().parents[2]
UTC = timezone.utc
REPEAT_WINDOW = 5
REPEAT_THRESHOLD = 3
TIMEOUT_MINUTES = 15
HIGH_RISK_IS_URGENT = True
QUEUE_ON_CALL = "on_call"
QUEUE_NEXT_DAY = "next_working_day"
QUEUE_LIVE = "priority_support"

SCHEMA = """
CREATE TABLE IF NOT EXISTS messages (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    conversation_id TEXT NOT NULL,
    at TEXT NOT NULL,
    kind TEXT NOT NULL,
    label TEXT, confidence REAL, scores TEXT,
    negative_type INTEGER NOT NULL DEFAULT 0,
    urgent INTEGER NOT NULL DEFAULT 0,
    complaint INTEGER NOT NULL DEFAULT 0,
    resets_clock INTEGER NOT NULL DEFAULT 0,
    risks TEXT, excerpt TEXT
);
CREATE INDEX IF NOT EXISTS idx_messages_conv ON messages(conversation_id, id);
CREATE TABLE IF NOT EXISTS escalations (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    conversation_id TEXT NOT NULL,
    created_at TEXT NOT NULL,
    kind TEXT NOT NULL,
    code TEXT NOT NULL,
    reason TEXT NOT NULL,
    condition_code TEXT NOT NULL,
    summary TEXT NOT NULL,
    queue TEXT NOT NULL,
    scheduled_for TEXT NOT NULL,
    stretch_key TEXT NOT NULL,
    dedupe_key TEXT NOT NULL,
    ticket_id TEXT,
    notified INTEGER NOT NULL DEFAULT 0,
    UNIQUE(conversation_id, dedupe_key)
);
"""


def iso(moment):
    return moment.astimezone(UTC).isoformat(timespec="seconds")


def _parse(text):
    return datetime.fromisoformat(text)


def connect(path=None):
    target = Path(path) if path else Path(os.getenv("SENTIMENT_DB_PATH") or PROJECT_ROOT / "sentiment_data" / "sentiment.db")
    target.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(target), timeout=10)
    conn.row_factory = sqlite3.Row
    conn.executescript(SCHEMA)
    return conn


def previous_results(conn, conversation_id, limit=5):
    rows = conn.execute(
        "SELECT negative_type FROM messages WHERE conversation_id=? AND kind='customer' ORDER BY id DESC LIMIT ?",
        (conversation_id, limit),
    ).fetchall()
    return [{"negative_type": bool(r["negative_type"])} for r in reversed(rows)]


def record_customer(conn, conversation_id, now, result, risks, text, complaint, resets):
    try:
        excerpt = mask_text(str(text))[:200]
    except Exception:
        excerpt = ""
    conn.execute(
        "INSERT INTO messages (conversation_id, at, kind, label, confidence, scores, negative_type, urgent,"
        " complaint, resets_clock, risks, excerpt) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
        (conversation_id, iso(now), "customer", result["label"], result["confidence"], json.dumps(result["scores"]),
         int(result["negative_type"]), int(result["urgent"]), int(bool(complaint)), int(bool(resets)),
         json.dumps(list(risks)), excerpt),
    )
    conn.commit()


def record_human(conn, conversation_id, now):
    conn.execute(
        "INSERT INTO messages (conversation_id, at, kind, resets_clock) VALUES (?,?,?,1)",
        (conversation_id, iso(now), "human"),
    )
    conn.commit()


def _stretch(conn, conversation_id):
    """The messages after the last clock reset (a human reply, or a solved or thankful customer message)."""
    rows = conn.execute("SELECT * FROM messages WHERE conversation_id=? ORDER BY id", (conversation_id,)).fetchall()
    start = 0
    for index, row in enumerate(rows):
        if row["resets_clock"]:
            start = index + 1
    return rows[start:]


def summarize(conn, conversation_id, now):
    rows = conn.execute(
        "SELECT * FROM messages WHERE conversation_id=? AND kind='customer' ORDER BY id", (conversation_id,)
    ).fetchall()
    categories = []
    for row in rows:
        for category in json.loads(row["risks"] or "[]"):
            if category not in categories:
                categories.append(category)
    parts = [f"{len(rows)} customer message(s)", "recent labels: " + ", ".join(r["label"] or "?" for r in rows[-6:])]
    if categories:
        parts.append("high-risk topics: " + ", ".join(categories))
    negatives = [r for r in rows if r["negative_type"]]
    if negatives:
        minutes = int((now - _parse(negatives[0]["at"])).total_seconds() // 60)
        parts.append(f"negative for {max(minutes, 0)} minute(s) since the first negative message")
    if rows:
        parts.append("last message (masked): " + (rows[-1]["excerpt"] or ""))
    return "; ".join(parts)[:700]


def _queue_exists(conn, conversation_id, stretch_key, queue):
    row = conn.execute(
        "SELECT 1 FROM escalations WHERE conversation_id=? AND stretch_key=? AND queue=? LIMIT 1",
        (conversation_id, stretch_key, queue),
    ).fetchone()
    return row is not None


def _add(conn, conversation_id, now, kind, code, reason, condition, summary, queue, scheduled, stretch_key, dedupe, notified):
    cursor = conn.execute(
        "INSERT OR IGNORE INTO escalations (conversation_id, created_at, kind, code, reason, condition_code, summary,"
        " queue, scheduled_for, stretch_key, dedupe_key, notified) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
        (conversation_id, iso(now), kind, code, reason, condition, summary, queue, iso(scheduled), stretch_key,
         dedupe, int(notified)),
    )
    return cursor.lastrowid if cursor.rowcount == 1 else None


def _row_dict(conn, row_id):
    return dict(conn.execute("SELECT * FROM escalations WHERE id=?", (row_id,)).fetchone())


def evaluate(conn, cfg, conversation_id, now, received=False, notified=1):
    """Applies the rules to the current stretch of the conversation and returns the NEW rows."""
    stretch = _stretch(conn, conversation_id)
    customers = [r for r in stretch if r["kind"] == "customer"]
    complaints = [r for r in customers if r["complaint"]]
    if not complaints:
        return []
    stretch_key = complaints[0]["at"]
    risks = []
    for row in customers:
        for category in json.loads(row["risks"] or "[]"):
            if category not in risks:
                risks.append(category)
    urgent = any(r["urgent"] for r in customers) or (HIGH_RISK_IS_URGENT and bool(risks))
    open_now = is_business_open(cfg, now)
    if open_now:
        queue, scheduled = QUEUE_LIVE, now
    elif urgent:
        queue, scheduled = QUEUE_ON_CALL, now
    else:
        queue, scheduled = QUEUE_NEXT_DAY, next_business_open(cfg, now)

    fired = []
    recent = customers[-REPEAT_WINDOW:]
    count = sum(1 for r in recent if r["negative_type"])
    if count >= REPEAT_THRESHOLD:
        fired.append((
            "repeated_negative", "Repeated negative messages from the customer",
            f"repeated_negative: negative_type_in_last_{REPEAT_WINDOW} >= {REPEAT_THRESHOLD} (observed {count})",
        ))
    for category in risks:
        fired.append((
            f"high_risk:{category}", f"High-risk issue reported: {category.replace('_', ' ')}",
            f"high_risk_issue: category={category} (escalates even when the message is calm)",
        ))
    negatives = [r for r in customers if r["negative_type"]]
    if negatives:
        elapsed = now - _parse(negatives[0]["at"])
        if elapsed > timedelta(minutes=TIMEOUT_MINUTES):
            minutes = int(elapsed.total_seconds() // 60)
            fired.append((
                "unresolved_timeout", f"Negative conversation unresolved for more than {TIMEOUT_MINUTES} minutes",
                f"unresolved_negative_minutes > {TIMEOUT_MINUTES} (observed {minutes})",
            ))

    created, summary = [], None
    for code, reason, condition in fired:
        if summary is None:
            summary = summarize(conn, conversation_id, now)
        row_id = _add(conn, conversation_id, now, "escalation", code, reason, condition, summary, queue, scheduled,
                      stretch_key, f"{code}|{stretch_key}", notified)
        if row_id:
            created.append(row_id)

    if received and not open_now and not _queue_exists(conn, conversation_id, stretch_key, queue):
        if summary is None:
            summary = summarize(conn, conversation_id, now)
        if urgent:
            code = "after_hours_urgent"
            reason = "Urgent complaint received outside business hours"
            condition = "after_hours_urgent: urgent or high-risk message and business hours closed -> on-call queue"
        else:
            code = "after_hours_normal"
            reason = "Complaint received outside business hours"
            condition = "after_hours_normal: complaint without urgency and business hours closed -> next working day"
        row_id = _add(conn, conversation_id, now, "queue", code, reason, condition, summary, queue, scheduled,
                      stretch_key, f"queue|{queue}|{stretch_key}", notified)
        if row_id:
            created.append(row_id)

    conn.commit()
    return [_row_dict(conn, row_id) for row_id in created]


def check_timeouts(cfg, now, db_path=None, only=None, notified=0):
    """Applies the rules again at a later time. Used for the 15-minute rule."""
    created = []
    with closing(connect(db_path)) as conn:
        if only:
            ids = [only]
        else:
            ids = [r[0] for r in conn.execute("SELECT DISTINCT conversation_id FROM messages")]
        for conversation_id in ids:
            created.extend(evaluate(conn, cfg, conversation_id, now, received=False, notified=notified))
    return created


def claim_rows(conversation_id, db_path=None):
    """Rows created in the background that the customer has not been told about yet."""
    with closing(connect(db_path)) as conn:
        rows = [dict(r) for r in conn.execute(
            "SELECT * FROM escalations WHERE conversation_id=? AND notified=0 ORDER BY id", (conversation_id,)
        ).fetchall()]
        if rows:
            conn.execute("UPDATE escalations SET notified=1 WHERE conversation_id=? AND notified=0", (conversation_id,))
            conn.commit()
    return rows


def set_ticket(row_id, ticket_id, db_path=None):
    with closing(connect(db_path)) as conn:
        conn.execute("UPDATE escalations SET ticket_id=? WHERE id=?", (str(ticket_id), int(row_id)))
        conn.commit()


def list_rows(conversation_id=None, db_path=None):
    with closing(connect(db_path)) as conn:
        if conversation_id:
            cursor = conn.execute("SELECT * FROM escalations WHERE conversation_id=? ORDER BY id", (conversation_id,))
        else:
            cursor = conn.execute("SELECT * FROM escalations ORDER BY id")
        return [dict(r) for r in cursor.fetchall()]