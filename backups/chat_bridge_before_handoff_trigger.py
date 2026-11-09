"""Glue between the Streamlit chat and the ticket workflow (Task 3, stage 5).

Plain Python with no Streamlit, so everything here is testable. It decides WHEN a conversation
counts as unresolved, builds conversation turns, submits them to the ticket workflow without ever
raising, and words the notice shown to the customer.

Unresolved triggers:
  low_confidence       - the text answer was flagged for a human (low retrieval confidence)
  answer_error         - the text answer failed
  customer_unresolved  - the customer says it is not solved or asks for a human
  file_unresolved      - a file result is still conflict / needs_confirmation / needs_better_file
                         on the second consecutive attempt
  file_failed          - the file job failed
  customer_requested   - the customer pressed the "ask a human" button
Messages blocked as prompt injection and rejected (unsafe) files never create tickets.
"""
import re
import uuid
from datetime import datetime, timezone

from src.tickets.config import get_config
from src.tickets.masking import mask_text
from src.tickets.ticket_log import log_event
from src.tickets.workflow import process_unresolved

UNRESOLVED_FILE_STATUSES = ("conflict", "needs_confirmation", "needs_better_file")
FAILED_FILE_STATUSES = ("failed", "error", "unavailable")
UNRESOLVED_FILE_LIMIT = 2

HUMAN_REQUEST_RES = (
    re.compile(r"(?i)\b(?:speak|talk|chat)\s+(?:to|with)\s+(?:a|an|the|your)?\s*"
               r"(?:human|person|agent|representative|someone|manager|supervisor)\b"),
    re.compile(r"(?i)\b(?:human agent|real person|live agent|human being|customer care)\b"),
    re.compile(r"(?i)\bescalate\b|\b(?:want|need|request|requesting|require)\s+(?:an?\s+|the\s+)?escalation\b"),
    re.compile(r"(?i)\b(?:still|even now)?\s*(?:not|isn't|is not|wasn't|hasn't been|has not been|haven't|have not)"
               r"\s+(?:been\s+)?(?:solved|resolved|fixed)\b"),
    re.compile(r"(?i)\b(?:did not|didn't|does not|doesn't|did nothing to)\s+(?:help|solve|fix|work)\b"),
    re.compile(r"(?i)\b(?:still|again)\s+(?:not working|broken|failing|the same)\b|\bsame problem\b"),
)


def wants_human_or_unresolved(text):
    """True when the customer says the problem is not solved or asks for a person."""
    normalised = str(text or "").replace("\u2019", "'").replace("\u2018", "'")
    return any(pattern.search(normalised) for pattern in HUMAN_REQUEST_RES)


def text_trigger(answer, question):
    """The trigger reason for a text exchange, or None when it needs no ticket."""
    kind = answer.get("kind")
    if kind == "blocked":
        return None
    if wants_human_or_unresolved(question):
        return "customer_unresolved"
    if kind == "answer" and answer.get("escalated"):
        return "low_confidence"
    if kind == "error":
        return "answer_error"
    return None


def file_trigger(status, unresolved_count):
    """(trigger or None, new count of consecutive unresolved file results)."""
    if status == "confirmed":
        return None, 0
    if status in FAILED_FILE_STATUSES:
        return "file_failed", unresolved_count
    if status in UNRESOLVED_FILE_STATUSES:
        count = unresolved_count + 1
        return ("file_unresolved" if count >= UNRESOLVED_FILE_LIMIT else None), count
    return None, unresolved_count


def new_conversation_id():
    return "web-" + uuid.uuid4().hex[:16]


def _stamp(now):
    return (now or datetime.now(timezone.utc)).isoformat(timespec="seconds")


def customer_turn(text, attachment=None, now=None):
    turn = {"role": "customer", "text": str(text or ""), "at": _stamp(now)}
    if attachment:
        turn["attachment"] = dict(attachment)
    return turn


def bot_turn(text, now=None):
    return {"role": "bot", "text": str(text or ""), "at": _stamp(now)}


def submit_to_tickets(conversation_id, turns, trigger, now=None, cfg=None, db_path=None):
    """Creates or updates the ticket for this conversation. Never raises: on a problem it returns
    {"error": <exception name>} so the chat keeps working."""
    try:
        config = cfg if cfg is not None else get_config()
        moment = now if now is not None else datetime.now(timezone.utc)
        return process_unresolved(config, conversation_id, turns, moment, trigger_reason=trigger, db_path=db_path)
    except Exception as error:
        log_event("ticket_error", error=type(error).__name__, trigger=trigger)
        return {"error": type(error).__name__}


def customer_notice(result):
    """The message shown to the customer after a ticket was created or updated."""
    if "error" in result:
        return "We couldn't create a support ticket just now. Please try again in a moment."
    ticket = result.get("ticket_id", "your ticket")
    routing = result.get("routing") or {}
    if result.get("action") == "linked_duplicate":
        parts = [f"This matches your earlier request, so it was added to ticket {ticket}."]
    else:
        parts = [f"Your request is logged as ticket {ticket}."]
    status = result.get("status")
    if status == "assigned":
        parts.append(f"It has been assigned to our {routing.get('team') or 'support'} team.")
    elif status == "queued":
        if routing.get("code") == "after_hours":
            parts.append("Our team is offline right now, so it will be picked up when support reopens.")
        else:
            parts.append("It is waiting in the queue for the next available agent.")
    elif status == "pending_information":
        parts.append("We need a little more information to move it forward.")
    follow_up = result.get("follow_up")
    if follow_up:
        parts.append(follow_up)
    return mask_text(" ".join(parts))