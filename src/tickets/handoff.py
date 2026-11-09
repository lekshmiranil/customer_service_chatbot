"""Masked handoff summary for the next agent or team (Task 3).

build_handoff() returns a structured dict and a text version. Phone numbers and email addresses are
masked (last four digits / first letter and domain kept), payment data and secrets never appear, and
every string is masked again at the end. Order numbers, ticket ids and customer ids are kept because
agents need them. Troubleshooting steps come from the stored conversation transcript and are not
independently verified. Inferred fields are labelled as such with the wording they came from.
"""
from src.tickets.business_time import evaluate_sla, to_utc
from src.tickets.extract import QUESTIONS
from src.tickets.masking import mask_email, mask_phone, mask_text
from src.tickets.store import (
    connect,
    conversations_of,
    get_conversation_turns,
    get_ticket,
    incident_ticket_ids,
    list_events,
    parse_iso,
    parse_ticket_label,
    ticket_label,
)

HISTORY_TYPES = (
    "queued", "assigned", "reassigned", "unassigned", "sla_warning", "sla_breached", "escalated",
    "sla_reset", "sla_recalculated",
)
INFERRED_FIELDS = ("issue_category", "severity", "impact", "sentiment")
MAX_STEPS = 8
MAX_EVIDENCE = 10


def _mask_deep(value):
    if isinstance(value, str):
        return mask_text(value)
    if isinstance(value, dict):
        return {key: _mask_deep(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_mask_deep(item) for item in value]
    return value


def _val(fields, name, default=None):
    field = fields.get(name)
    return field["value"] if field else default


def _history_note(event):
    detail = event["detail"]
    kind = event["type"]
    if kind == "sla_warning":
        return f"{round(detail.get('threshold', 0) * 100)}% of the SLA time used (deadline {detail.get('deadline')})"
    if kind == "sla_breached":
        return f"deadline {detail.get('deadline')} passed"
    if kind == "escalated":
        return str(detail.get("reason", ""))
    if kind == "sla_reset":
        return "cleared " + ", ".join(detail.get("cleared", []))
    if kind == "sla_recalculated":
        return f"deadline moved to {detail.get('to_deadline')}"
    if kind in ("assigned", "reassigned"):
        return f"to {detail.get('agent') or detail.get('to')}"
    if kind == "unassigned":
        return f"from {detail.get('from')} ({detail.get('code')})"
    if kind == "queued":
        return str(detail.get("code", ""))
    return ""


def _recommend(cfg, ticket, sla, missing, code):
    fraction = round(cfg.data["sla"]["warning_fraction"] * 100)
    if ticket["status"] == "resolved":
        return "Ticket is resolved; no further action is needed."
    if ticket["escalated_at"] or (sla and sla["state"] == "breached"):
        action = "SLA breached and escalated: contact the customer now, then resolve or send a status update."
    elif ticket["status"] == "queued":
        if code == "after_hours":
            action = ("Queued outside business hours; the first available agent should pick it up when "
                      f"support reopens ({ticket['queued_until']}).")
        else:
            action = (f"No eligible agent could take this ticket ({code}); assign it manually or restore "
                      "agent availability or capacity.")
    elif ticket["status"] == "pending_information":
        return "Waiting for the customer: ask for " + ", ".join(missing) + "."
    elif sla and sla["state"] == "warning":
        action = f"SLA is past {fraction}% of the allowed time: respond before {sla['deadline']}."
    else:
        action = "Review the issue and reply to the customer before the SLA deadline."
    if missing:
        action += " Also still missing: " + ", ".join(missing) + "."
    return action


def render_text(handoff):
    sla = handoff["sla"]
    customer = handoff["customer"]
    context = handoff["context"]
    issue = handoff["issue"]
    assignment = handoff["assignment"]
    related = handoff["related"]
    lines = [
        f"HANDOFF {handoff['ticket_id']} | status: {handoff['status']} | "
        f"priority: {handoff['priority']} (score {handoff['priority_score']})",
    ]
    if sla:
        lines.append(
            f"SLA: {sla['state']} | {sla['target_minutes']} min {sla['basis']} target | deadline {sla['deadline']} | "
            f"remaining {sla['remaining_minutes']} min | escalations {sla['escalation_count']}"
        )
    else:
        lines.append("SLA: not calculated")
    lines.append(
        f"Customer: {customer['name'] or 'not given'} | id {customer['customer_id'] or 'not given'} | "
        f"email {customer['email'] or 'not given'} | phone {customer['phone'] or 'not given'} | "
        f"preferred contact {customer['preferred_contact'] or 'not given'}"
    )
    lines.append(
        f"Order: {context['order_id'] or 'not given'}"
        + (f" (also {', '.join(context['other_order_ids'])})" if context["other_order_ids"] else "")
        + f" | product {context['product'] or 'not given'}"
        + (f" | amounts {', '.join(context['amounts'])}" if context["amounts"] else "")
        + (f" | error codes {', '.join(context['error_codes'])}" if context["error_codes"] else "")
    )
    lines.append(f"Issue: {issue['description'] or 'not given'}")
    lines.append(
        f"Assessment (inferred from wording): category {issue['category']}, severity {issue['severity']}, "
        f"impact {issue['impact']}, sentiment {issue['sentiment']}"
    )
    lines.append("Troubleshooting so far:")
    lines.extend(f"- {step}" for step in handoff["attempted_steps"])
    lines.append("Evidence:")
    lines.extend(
        f"- {item['type']}: " + (item.get("excerpt") or f"file {item.get('file_id')} ({item.get('status')})")
        for item in handoff["evidence"]
    ) if handoff["evidence"] else lines.append("- none recorded")
    lines.append("Outstanding questions: " + (
        "; ".join(f"{item['question']} (asked {item['times_asked']}x)" for item in handoff["outstanding_questions"])
        or "none"
    ))
    lines.append("Missing mandatory information: " + (", ".join(handoff["missing_mandatory"]) or "none"))
    lines.append(
        "Related: duplicate conversations " + (", ".join(related["duplicate_conversations"]) or "none")
        + " | related tickets " + (", ".join(related["related_tickets"]) or "none")
        + (f" | incident {related['incident_id']}" if related["incident_id"] else "")
    )
    lines.append(
        f"Assignment: agent {assignment['agent'] or 'none'} | team {assignment['team'] or 'none'} | "
        f"queue {assignment['queue'] or 'none'} | {assignment['reason'] or 'no routing decision yet'}"
    )
    lines.append("History:")
    lines.extend(f"- {item['at']} {item['type']} {item['note']}".rstrip() for item in handoff["history"]) \
        if handoff["history"] else lines.append("- none")
    lines.append(f"Recommended next action: {handoff['recommended_next_action']}")
    return mask_text("\n".join(lines))


def build_handoff(cfg, label, now, db_path=None):
    """Builds the masked handoff summary for one ticket as of the given moment."""
    ticket_id = parse_ticket_label(label)
    to_utc(now)
    conn = connect(db_path)
    try:
        ticket = get_ticket(conn, ticket_id)
        if ticket is None:
            raise ValueError(f"unknown ticket: {label}")
        links = conversations_of(conn, ticket_id)
        transcripts = {link["conversation_id"]: get_conversation_turns(conn, link["conversation_id"]) for link in links}
        events = list_events(conn, ticket_id)
        incident_id = ticket["incident_id"]
        related_tickets = (
            [ticket_label(other) for other in incident_ticket_ids(conn, incident_id) if other != ticket_id]
            if incident_id else []
        )
    finally:
        conn.close()

    fields = ticket["fields"]
    sla = None
    if ticket["sla_target_minutes"] is not None and ticket["sla_basis"]:
        state = evaluate_sla(
            cfg,
            parse_iso(ticket["created_at"]),
            {"target_minutes": ticket["sla_target_minutes"], "basis": ticket["sla_basis"]},
            now,
        )
        sla = {
            "state": state["state"],
            "basis": state["basis"],
            "target_minutes": state["target_minutes"],
            "deadline": ticket["sla_deadline"],
            "remaining_minutes": round(state["remaining_seconds"] / 60.0, 1),
            "warning_sent_at": ticket["warning_sent_at"],
            "escalated_at": ticket["escalated_at"],
            "escalation_count": ticket["escalation_count"],
        }

    email = _val(fields, "contact_email")
    phone = _val(fields, "contact_phone")
    method_field = fields.get("contact_method")
    customer = {
        "name": _val(fields, "customer_name"),
        "customer_id": _val(fields, "customer_id"),
        "email": mask_email(email) if email else None,
        "phone": mask_phone(phone) if phone else None,
        "preferred_contact": method_field["value"] if method_field else None,
        "preferred_contact_source": method_field["source"] if method_field else None,
    }
    context = {
        "order_id": _val(fields, "order_id"),
        "other_order_ids": _val(fields, "other_order_ids", []),
        "product": _val(fields, "product"),
        "amounts": _val(fields, "amounts", []),
        "error_codes": _val(fields, "error_codes", []),
    }
    issue = {
        "description": _val(fields, "issue_description"),
        "category": _val(fields, "issue_category"),
        "severity": _val(fields, "severity"),
        "impact": _val(fields, "impact"),
        "sentiment": _val(fields, "sentiment"),
        "inferred": [name for name in INFERRED_FIELDS if name in fields],
        "basis": {name: fields[name].get("reason") for name in INFERRED_FIELDS if name in fields},
    }

    steps = [f"Escalation trigger: {ticket['trigger_reason']}"]
    for link in links:
        for entry in transcripts[link["conversation_id"]]:
            if entry.get("role") == "bot" and entry.get("text"):
                steps.append("Bot replied: " + entry["text"][:160])
            attachment = entry.get("attachment")
            if isinstance(attachment, dict):
                steps.append(f"Customer file check ({attachment.get('kind', 'file')}): outcome {attachment.get('status')}")
    steps = steps[:MAX_STEPS]
    if len(steps) == 1:
        steps.append("No automated troubleshooting beyond the first reply was recorded.")

    evidence = []
    for item in ticket["evidence"][:MAX_EVIDENCE]:
        if item.get("type") == "attachment":
            evidence.append({"type": "attachment", "conversation": item.get("conversation_id"),
                             "file_id": item.get("file_id"), "status": item.get("status"), "kind": item.get("kind")})
        else:
            evidence.append({"type": "message", "conversation": item.get("conversation_id"),
                             "turn": item.get("turn"), "excerpt": item.get("excerpt"), "supports": item.get("supports")})

    asked = (ticket["follow_up"] or {}).get("asked", {})
    outstanding = [
        {"field": name, "question": QUESTIONS[name], "times_asked": asked.get(name, 0)}
        for name in ticket["missing"] if name in QUESTIONS
    ]
    code = (ticket["routing_reason"] or "").partition(": ")[0] or None
    handoff = {
        "ticket_id": ticket["ticket_id"],
        "status": ticket["status"],
        "priority": ticket["priority"],
        "priority_score": ticket["score"],
        "priority_reasons": (ticket["priority_detail"] or {}).get("reasons", []),
        "sla": sla,
        "customer": customer,
        "context": context,
        "issue": issue,
        "attempted_steps": steps,
        "evidence": evidence,
        "outstanding_questions": outstanding,
        "missing_mandatory": list(ticket["missing"]),
        "related": {
            "duplicate_conversations": [link["conversation_id"] for link in links if link["relation"] == "duplicate"],
            "incident_id": incident_id,
            "related_tickets": related_tickets,
        },
        "assignment": {
            "agent": ticket["assigned_agent"],
            "team": ticket["assigned_team"],
            "queue": ticket["queue_name"],
            "reason": ticket["routing_reason"],
            "queued_until": ticket["queued_until"],
        },
        "history": [
            {"at": event["at"], "type": event["type"], "note": _history_note(event)}
            for event in events if event["type"] in HISTORY_TYPES
        ],
        "recommended_next_action": _recommend(cfg, ticket, sla, ticket["missing"], code),
    }
    handoff = _mask_deep(handoff)
    handoff["text"] = render_text(handoff)
    return handoff