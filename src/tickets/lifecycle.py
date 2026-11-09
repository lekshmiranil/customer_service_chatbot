"""Ticket lifecycle: priority/SLA refresh, warnings, escalation and routing (Task 3, stage 4).

reconcile_open_tickets() is safe to call as often as you like. For every open ticket it:
  1. recalculates priority and the SLA clock from the stored fields and the CURRENT configuration,
     so runtime changes to targets, calendars and holidays apply on the next call without a restart;
  2. records an SLA warning once when the warning fraction (75%) of the allowed time is used, and an
     escalation once when the deadline is breached - never repeated for the same threshold or breach;
  3. resets those flags only when applicable SLA conditions changed and the ticket is no longer past
     the threshold (or when reset_sla_flags() is called explicitly);
  4. routes tickets in priority order (see routing.py), retries queued tickets, and reassigns tickets
     whose agent is no longer eligible.
Calling it again with the same inputs changes nothing and records no new events.
"""
import json

from src.tickets.business_time import to_utc
from src.tickets.extract import DEFAULT_SEVERITY
from src.tickets.masking import mask_text
from src.tickets.priority import compute_priority, queue_sort_key
from src.tickets.routing import agent_is_valid, decide_route
from src.tickets.store import (
    ACTIVE_STATUSES,
    add_event,
    all_tickets,
    assigned_counts,
    connect,
    dumps,
    get_ticket,
    iso,
    parse_iso,
    parse_ticket_label,
    transaction,
    update_ticket,
)

SUMMARY_LISTS = (
    "priority_changes", "recalculated", "resets", "warnings", "escalations", "assigned", "reassigned", "queued",
)


def _new_summary():
    summary = {"checked": 0}
    for name in SUMMARY_LISTS:
        summary[name] = []
    return summary


def _differs(first, second):
    if isinstance(first, (dict, list)) or isinstance(second, (dict, list)):
        return dumps(first) != dumps(second)
    return first != second


def _value(fields, name, default=None):
    field = fields.get(name)
    return field["value"] if field else default


def _score(cfg, ticket, now):
    fields = ticket["fields"]
    severity = _value(fields, "severity", DEFAULT_SEVERITY)
    if severity not in cfg.data["priority"]["severity_points"]:
        severity = DEFAULT_SEVERITY
    return compute_priority(
        cfg,
        severity=severity,
        impact=_value(fields, "impact", "single_customer"),
        sentiment=_value(fields, "sentiment", "neutral"),
        issue_category=_value(fields, "issue_category", "general"),
        created_at=parse_iso(ticket["created_at"]),
        now=now,
    )


def _refresh(conn, cfg, ticket, now, summary):
    label = ticket["ticket_id"]
    scored = _score(cfg, ticket, now)
    sla = scored["sla"]
    target = scored["sla_target"]
    priority = scored["priority"]
    new_deadline = iso(sla["deadline"])
    changes = {}
    events = []

    fingerprint_changed = (
        ticket["sla_fingerprint"] is not None and ticket["sla_fingerprint"] != cfg.calendar_fingerprint
    )
    target_changed = ticket["sla_target_minutes"] is not None and (
        ticket["sla_target_minutes"] != target["target_minutes"] or ticket["sla_basis"] != target["basis"]
    )
    policy_changed = fingerprint_changed or target_changed

    if policy_changed and ticket["sla_deadline"] != new_deadline:
        reason = (
            "SLA policy, business calendar or holiday configuration changed"
            if fingerprint_changed
            else "the applicable SLA target changed with the ticket's priority class"
        )
        events.append(("sla_recalculated", {
            "from_deadline": ticket["sla_deadline"], "to_deadline": new_deadline, "reason": reason,
        }))
        summary["recalculated"].append(label)

    warning_at = ticket["warning_sent_at"]
    escalated_at = ticket["escalated_at"]
    if policy_changed:
        cleared = []
        if warning_at and sla["state"] == "ok":
            warning_at = None
            cleared.append("warning")
        if escalated_at and sla["state"] != "breached":
            escalated_at = None
            cleared.append("escalation")
        if cleared:
            events.append(("sla_reset", {
                "cleared": cleared,
                "reason": "applicable SLA conditions changed and the ticket is no longer past that threshold",
            }))
            summary["resets"].append(label)
            changes["warning_sent_at"] = warning_at
            changes["escalated_at"] = escalated_at

    if ticket["priority"] != priority:
        changes["priority"] = priority
        if ticket["priority"] is not None:
            events.append(("priority_changed", {
                "from": ticket["priority"], "to": priority, "score": scored["score"],
                "rules": scored["rules_applied"], "reasons": scored["reasons"],
            }))
            summary["priority_changes"].append(label)

    if sla["state"] in ("warning", "breached") and not warning_at:
        events.append(("sla_warning", {
            "threshold": cfg.data["sla"]["warning_fraction"],
            "crossed_at": iso(sla["warning_at"]),
            "deadline": new_deadline,
            "consumed_fraction": round(sla["consumed_fraction"], 4),
        }))
        warning_at = iso(now)
        changes["warning_sent_at"] = warning_at
        summary["warnings"].append(label)
    if sla["state"] == "breached" and not escalated_at:
        events.append(("sla_breached", {"deadline": new_deadline, "detected_at": iso(now)}))
        events.append(("escalated", {
            "reason": "SLA deadline breached",
            "action": "priority raised to at least the configured floor; urgent routing and on-call eligibility",
        }))
        escalated_at = iso(now)
        changes["escalated_at"] = escalated_at
        changes["escalation_count"] = ticket["escalation_count"] + 1
        summary["escalations"].append(label)

    urgent = priority in cfg.data["urgent_priorities"] or bool(escalated_at)
    if ticket["status"] == "pending_information" and urgent:
        changes["status"] = "open"
        events.append(("status_changed", {
            "from": "pending_information", "to": "open",
            "reason": "an urgent or escalated ticket is not held for missing information",
        }))

    refresh = {
        "score": scored["score"],
        "priority_detail": json.loads(dumps(scored)),
        "sla_class": scored["sla_class"],
        "sla_basis": target["basis"],
        "sla_target_minutes": target["target_minutes"],
        "sla_deadline": new_deadline,
        "sla_warning_at": iso(sla["warning_at"]),
        "sla_state": sla["state"],
        "sla_fingerprint": cfg.calendar_fingerprint,
    }
    for key, value in refresh.items():
        if _differs(ticket.get(key), value):
            changes[key] = value

    if changes:
        touch = any(key in changes for key in ("priority", "status", "warning_sent_at", "escalated_at"))
        update_ticket(conn, ticket["id"], now, touch=touch, **changes)
    for event_type, detail in events:
        add_event(conn, ticket["id"], event_type, now, **detail)


def _route(conn, cfg, ticket, now, counts, summary):
    if ticket["status"] == "pending_information":
        return
    label = ticket["ticket_id"]
    category = _value(ticket["fields"], "issue_category", "general")
    escalated = bool(ticket["escalated_at"])
    previous = None
    if ticket["status"] == "assigned" and ticket["assigned_agent"]:
        if agent_is_valid(cfg, ticket["assigned_agent"], category):
            return
        previous = ticket["assigned_agent"]
        counts[previous] = max(0, counts.get(previous, 0) - 1)

    decision = decide_route(cfg, category, ticket["priority"], escalated, now, counts)
    if decision["outcome"] == "assigned":
        new_state = {
            "status": "assigned",
            "assigned_agent": decision["agent"],
            "assigned_team": decision["team"],
            "queue_name": None,
            "routing_reason": f"assigned: {decision['reason']}",
            "queued_until": None,
        }
    else:
        new_state = {
            "status": "queued",
            "assigned_agent": None,
            "assigned_team": decision["team"],
            "queue_name": decision["queue"],
            "routing_reason": f"{decision['code']}: {decision['reason']}",
            "queued_until": decision["queued_until"],
        }
    if previous is None and all(ticket.get(key) == value for key, value in new_state.items()):
        return

    update_ticket(conn, ticket["id"], now, touch=True, **new_state)
    if decision["outcome"] == "assigned":
        counts[decision["agent"]] = counts.get(decision["agent"], 0) + 1
        if previous is None:
            detail = {"agent": decision["agent"], "team": decision["team"], "reason": decision["reason"]}
            if ticket["status"] == "queued":
                detail["was_queued"] = ticket["routing_reason"]
            add_event(conn, ticket["id"], "assigned", now, **detail)
            summary["assigned"].append(label)
        else:
            add_event(conn, ticket["id"], "reassigned", now, **{
                "from": previous, "to": decision["agent"], "reason": decision["reason"],
            })
            summary["reassigned"].append(label)
    else:
        if previous is not None:
            add_event(conn, ticket["id"], "unassigned", now, **{
                "from": previous, "code": decision["code"], "reason": decision["reason"],
            })
        else:
            add_event(conn, ticket["id"], "queued", now, queue=decision["queue"], code=decision["code"],
                      reason=decision["reason"], queued_until=decision["queued_until"])
        summary["queued"].append(label)


def reconcile_open_tickets(cfg, now, db_path=None, only=None):
    """Refreshes priority and SLA, records warnings and escalations, and routes open tickets.

    only: a numeric ticket id to restrict the run to one ticket (used right after creating it).
    Returns a summary: {"checked": n, <list name>: [ticket labels]}.
    """
    to_utc(now)
    conn = connect(db_path)
    try:
        with transaction(conn):
            summary = _new_summary()
            tickets = [t for t in all_tickets(conn) if t["status"] in ACTIVE_STATUSES]
            if only is not None:
                tickets = [t for t in tickets if t["id"] == only]
            summary["checked"] = len(tickets)
            for ticket in tickets:
                _refresh(conn, cfg, ticket, now, summary)
            refreshed = [get_ticket(conn, ticket["id"]) for ticket in tickets]
            refreshed.sort(key=lambda t: queue_sort_key(t["priority"], t["score"], t["created_at"], t["ticket_id"]))
            counts = assigned_counts(conn)
            for ticket in refreshed:
                _route(conn, cfg, ticket, now, counts, summary)
            return summary
    finally:
        conn.close()


def resolve_ticket(label, now, note="", db_path=None):
    """Marks a ticket resolved (freeing its agent's capacity). Returns False if it already was."""
    ticket_id = parse_ticket_label(label)
    to_utc(now)
    conn = connect(db_path)
    try:
        with transaction(conn):
            ticket = get_ticket(conn, ticket_id)
            if ticket is None:
                raise ValueError(f"unknown ticket: {label}")
            if ticket["status"] == "resolved":
                return False
            update_ticket(conn, ticket_id, now, status="resolved", resolved_at=iso(now))
            add_event(conn, ticket_id, "resolved", now, note=mask_text(note)[:200],
                      previous_status=ticket["status"])
            return True
    finally:
        conn.close()


def reset_sla_flags(label, now, reason, db_path=None):
    """Explicitly clears the warning and escalation flags so they can fire again. Returns what was cleared."""
    ticket_id = parse_ticket_label(label)
    to_utc(now)
    conn = connect(db_path)
    try:
        with transaction(conn):
            ticket = get_ticket(conn, ticket_id)
            if ticket is None:
                raise ValueError(f"unknown ticket: {label}")
            cleared = []
            changes = {}
            if ticket["warning_sent_at"]:
                cleared.append("warning")
                changes["warning_sent_at"] = None
            if ticket["escalated_at"]:
                cleared.append("escalation")
                changes["escalated_at"] = None
            if cleared:
                update_ticket(conn, ticket_id, now, touch=False, **changes)
                add_event(conn, ticket_id, "sla_reset", now, cleared=cleared, explicit=True,
                          reason=mask_text(reason)[:200])
            return cleared
    finally:
        conn.close()