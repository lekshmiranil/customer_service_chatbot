"""Entry points used by main.py and the tests. Plain Python, no Streamlit. The clock is always an
argument, and no function raises: a problem returns a safe result and is noted in LAST_ERROR."""
import os
import threading
from contextlib import closing
from datetime import datetime, timezone

from src.sentiment import escalation as store
from src.sentiment.classify import classify_message
from src.sentiment.history import apply_history
from src.sentiment.risk import detect_risks
from src.sentiment.tone import detect_language, notice_line, opening_line, profile_for
from src.tickets.config import get_config

UTC = timezone.utc
LAST_ERROR = {"value": None}
QUEUE_KEYS = {store.QUEUE_ON_CALL: "on_call", store.QUEUE_NEXT_DAY: "next_day"}
_thread = None
_stop = threading.Event()
_guard = threading.Lock()


def utc_now(now=None):
    """The given time as UTC (a naive time is taken as UTC). SENTIMENT_NOW overrides the clock for manual tests."""
    if now is None:
        override = os.getenv("SENTIMENT_NOW", "").strip()
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


def _note(error):
    LAST_ERROR["value"] = f"{type(error).__name__}: {str(error)[:120]}"


def _empty(error=None):
    return {
        "label": "neutral", "confidence": 0.0, "scores": {}, "flags": [], "negative_type": False, "urgent": False,
        "risks": [], "language": "en", "profile": "neutral", "opening": "", "notice": "", "escalated": False,
        "queued": False, "rows": [], "context_notes": [], "error": error,
    }


def _notice(rows, language):
    if not rows:
        return ""
    chosen = next((r for r in rows if r["kind"] == "escalation"), rows[0])
    return notice_line(QUEUE_KEYS.get(chosen["queue"], "now"), language)


def analyze_and_decide(conversation_id, text, now=None, cfg=None, db_path=None):
    """Classifies one customer message, records it and applies the escalation and queue rules."""
    try:
        moment = utc_now(now)
        config = cfg if cfg is not None else get_config()
        text = str(text or "")
        with closing(store.connect(db_path)) as conn:
            previous = store.previous_results(conn, conversation_id)
            combined = apply_history(classify_message(text), previous)
            risks = detect_risks(text)
            complaint = combined["negative_type"] or combined["urgent"] or bool(risks)
            resets = (combined["resolved"] or combined["positive"]) and not combined["negative_type"]
            store.record_customer(conn, conversation_id, moment, combined, risks, text, complaint, resets)
            rows = store.evaluate(conn, config, conversation_id, moment, received=complaint, notified=1)
        language = detect_language(text)
        profile = profile_for(combined, risks)
        return {
            "label": combined["label"], "confidence": combined["confidence"], "scores": combined["scores"],
            "flags": combined["flags"], "negative_type": combined["negative_type"], "urgent": combined["urgent"],
            "risks": risks, "language": language, "profile": profile, "opening": opening_line(profile, language),
            "notice": _notice(rows, language), "escalated": any(r["kind"] == "escalation" for r in rows),
            "queued": any(r["kind"] == "queue" for r in rows), "rows": rows,
            "context_notes": combined.get("context_notes", []), "error": None,
        }
    except Exception as error:
        _note(error)
        return _empty(type(error).__name__)


def record_human_reply(conversation_id, now=None, db_path=None):
    """A human reply stops the 15-minute clock."""
    try:
        with closing(store.connect(db_path)) as conn:
            store.record_human(conn, conversation_id, utc_now(now))
        return True
    except Exception as error:
        _note(error)
        return False


def check_timeouts(now=None, cfg=None, db_path=None, only=None):
    """Applies the 15-minute rule (and the other rules) at the given time. Returns the new rows."""
    try:
        config = cfg if cfg is not None else get_config()
        return store.check_timeouts(config, utc_now(now), db_path=db_path, only=only, notified=0)
    except Exception as error:
        _note(error)
        return []


def claim_unnotified(conversation_id, now=None, cfg=None, db_path=None, language="en"):
    """Rows created in the background for this conversation. Each row is returned once, with a notice."""
    try:
        config = cfg if cfg is not None else get_config()
        store.check_timeouts(config, utc_now(now), db_path=db_path, only=conversation_id, notified=0)
        rows = store.claim_rows(conversation_id, db_path)
        for row in rows:
            row["notice"] = notice_line(QUEUE_KEYS.get(row["queue"], "now"), language)
        return rows
    except Exception as error:
        _note(error)
        return []


def set_ticket(row_id, ticket_id, db_path=None):
    try:
        store.set_ticket(row_id, ticket_id, db_path)
        return True
    except Exception as error:
        _note(error)
        return False


def list_rows(conversation_id=None, db_path=None):
    try:
        return store.list_rows(conversation_id, db_path)
    except Exception as error:
        _note(error)
        return []


def timeout_checker_running():
    return _thread is not None and _thread.is_alive()


def start_timeout_checker(interval_seconds=60.0, clock=None, db_path=None):
    """Starts the background 15-minute check once. Returns False if it is already running."""
    global _thread
    with _guard:
        if timeout_checker_running():
            return False
        _stop.clear()

        def loop():
            while not _stop.is_set():
                check_timeouts(now=clock() if clock else None, db_path=db_path)
                _stop.wait(max(0.1, float(interval_seconds)))

        _thread = threading.Thread(target=loop, name="sentiment-timeouts", daemon=True)
        _thread.start()
        return True


def stop_timeout_checker():
    global _thread
    with _guard:
        thread = _thread
        _stop.set()
    if thread is not None:
        thread.join(timeout=5)
    with _guard:
        _thread = None
    return thread is not None