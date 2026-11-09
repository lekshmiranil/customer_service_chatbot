"""One call from the chatbot to a fully processed ticket (Task 3, stage 4).

process_unresolved() creates or updates the ticket for an unresolved conversation (service.py),
then recalculates priority/SLA and routes that ticket (lifecycle.py), and writes masked log lines.
run_reconcile() does the same housekeeping for every open ticket, and start_reconciler() runs it on
a background timer so SLA warnings and escalations happen even when nobody is chatting.
"""
import os
import threading
from datetime import datetime, timezone

from src.tickets.config import get_config
from src.tickets.lifecycle import reconcile_open_tickets
from src.tickets.service import process_conversation
from src.tickets.store import connect, get_ticket, parse_ticket_label
from src.tickets.ticket_log import log_event

DEFAULT_RECONCILE_SECONDS = 60.0
_thread = None
_stop = threading.Event()
_guard = threading.Lock()


def _log_summary(summary):
    for label in summary["warnings"]:
        log_event("sla_warning", ticket_id=label)
    for label in summary["escalations"]:
        log_event("sla_escalation", ticket_id=label)
    for label in summary["resets"]:
        log_event("sla_reset", ticket_id=label)
    for label in summary["recalculated"]:
        log_event("sla_recalculated", ticket_id=label)
    for label in summary["priority_changes"]:
        log_event("priority_changed", ticket_id=label)
    for label in summary["assigned"]:
        log_event("ticket_assigned", ticket_id=label)
    for label in summary["reassigned"]:
        log_event("ticket_reassigned", ticket_id=label)
    for label in summary["queued"]:
        log_event("ticket_queued", ticket_id=label)


def process_unresolved(cfg, conversation_id, turns, now, trigger_reason="unresolved", db_path=None):
    """Creates or updates the ticket, routes it, and returns the service summary plus a "routing" block."""
    result = process_conversation(cfg, conversation_id, turns, now, trigger_reason, db_path)
    ticket_number = parse_ticket_label(result["ticket_id"])
    summary = reconcile_open_tickets(cfg, now, db_path=db_path, only=ticket_number)
    conn = connect(db_path)
    try:
        ticket = get_ticket(conn, ticket_number)
    finally:
        conn.close()
    reason = ticket["routing_reason"] or ""
    code, _, text = reason.partition(": ")
    result["status"] = ticket["status"]
    result["priority"] = ticket["priority"]
    result["sla_state"] = ticket["sla_state"]
    result["routing"] = {
        "agent": ticket["assigned_agent"],
        "team": ticket["assigned_team"],
        "queue": ticket["queue_name"],
        "code": code or None,
        "reason": text or None,
        "queued_until": ticket["queued_until"],
    }
    log_event(
        "ticket_processed",
        ticket_id=result["ticket_id"],
        action=result["action"],
        relation=result["relation"],
        status=ticket["status"],
        priority=ticket["priority"],
        missing=result["missing"],
        assigned_agent=ticket["assigned_agent"],
        routing_code=code or None,
        sla_state=ticket["sla_state"],
    )
    _log_summary(summary)
    return result


def run_reconcile(db_path=None, now=None, config_loader=None):
    """Reconciles every open ticket against the current configuration and clock."""
    cfg = (config_loader or get_config)()
    moment = now if now is not None else datetime.now(timezone.utc)
    summary = reconcile_open_tickets(cfg, moment, db_path=db_path)
    _log_summary(summary)
    return summary


def _interval(value):
    if value is None:
        try:
            value = float(os.getenv("TICKET_RECONCILE_SECONDS", DEFAULT_RECONCILE_SECONDS))
        except ValueError:
            value = DEFAULT_RECONCILE_SECONDS
    return max(0.1, float(value))


def reconciler_running():
    return _thread is not None and _thread.is_alive()


def start_reconciler(interval_seconds=None, db_path=None, config_loader=None, clock=None):
    """Starts the background reconcile loop once. Returns False if it is already running."""
    global _thread
    with _guard:
        if reconciler_running():
            return False
        interval = _interval(interval_seconds)
        _stop.clear()

        def loop():
            while not _stop.is_set():
                try:
                    run_reconcile(db_path=db_path, now=clock() if clock else None, config_loader=config_loader)
                except Exception as error:
                    log_event("reconcile_error", error=type(error).__name__)
                _stop.wait(interval)

        _thread = threading.Thread(target=loop, name="ticket-reconciler", daemon=True)
        _thread.start()
        return True


def stop_reconciler():
    """Stops the background loop. Returns True if it was running."""
    global _thread
    with _guard:
        thread = _thread
        if thread is None:
            return False
        _stop.set()
    thread.join(timeout=10)
    with _guard:
        if not thread.is_alive():
            _thread = None
    return True