"""Ticket creation and update workflow (Task 3, stage 3).

process_conversation() is the single entry point. Given a conversation that has become
unresolved, it:
  - creates one ticket per conversation (repeat calls update that ticket, never add another);
  - links a conversation that duplicates an open ticket to that ticket instead of creating a new
    one, keeping its masked turns, evidence and an audit event;
  - links a related (same incident) conversation to its own new ticket through a shared incident;
  - extracts and merges structured fields, checks mandatory fields and prepares follow-up questions;
  - recalculates priority and the SLA clock every time it runs;
  - records audit events only for real changes, so repeating the same call changes nothing.
Routing, SLA warnings and escalation, and the handoff summary are added in later stages.
"""
import json
from datetime import timedelta

from src.tickets.business_time import to_utc
from src.tickets.duplicates import compare_fields
from src.tickets.extract import (
    DEFAULT_SEVERITY,
    QUESTIONS,
    extract_ticket_fields,
    follow_up_questions,
    follow_up_text,
    merge_fields,
    missing_mandatory,
)
from src.tickets.masking import mask_text
from src.tickets.priority import compute_priority
from src.tickets.store import (
    add_event,
    active_tickets_since,
    connect,
    create_incident,
    dumps,
    get_conversation_link,
    get_ticket,
    insert_ticket,
    iso,
    link_conversation,
    parse_iso,
    save_conversation_turns,
    ticket_label,
    transaction,
    update_ticket,
)

MAX_STORED_TURNS = 50


def _value(fields, name, default=None):
    field = fields.get(name)
    return field["value"] if field else default


def _differs(first, second):
    if isinstance(first, (dict, list)) or isinstance(second, (dict, list)):
        return dumps(first) != dumps(second)
    return first != second


def _masked_turns(turns):
    kept = []
    for turn in turns[-MAX_STORED_TURNS:]:
        entry = {
            "role": str(turn.get("role", "")),
            "text": mask_text(turn.get("text", ""))[:500],
            "at": turn.get("at"),
        }
        if isinstance(turn.get("attachment"), dict):
            entry["attachment"] = turn["attachment"]
        kept.append(entry)
    return kept


def _evidence_key(item):
    return (str(item.get("conversation_id", "")), item.get("turn", 0), 0 if item.get("type") == "message" else 1)


def _desired_status(current, missing, urgent):
    """pending_information while mandatory data is missing, unless the issue is urgent."""
    if current == "resolved":
        return "open"
    if missing and not urgent:
        return "pending_information"
    if current in (None, "pending_information", "open"):
        return "open"
    return current


def _find_match(conn, cfg, new_fields, now):
    """The best duplicate (preferred) or related open ticket inside the duplicate window."""
    since = iso(now - timedelta(hours=cfg.data["duplicates"]["window_hours"]))
    best = {"duplicate": None, "related": None}
    for candidate in active_tickets_since(conn, since):
        comparison = compare_fields(cfg, new_fields, candidate["fields"])
        decision = comparison["decision"]
        if decision == "unrelated":
            continue
        rank = (comparison["signals"]["similarity"], -candidate["id"])
        current = best[decision]
        if current is None or rank > current["rank"]:
            best[decision] = {"decision": decision, "ticket": candidate, "comparison": comparison, "rank": rank}
    return best["duplicate"] or best["related"]


def _join_incident(conn, new_id, other, comparison, now):
    signals = comparison["signals"]
    label = f"{signals['category']} incident"
    if signals["shared_error_codes"]:
        label += " (" + ", ".join(signals["shared_error_codes"]) + ")"
    incident_id = other["incident_id"]
    if incident_id is None:
        incident_id = create_incident(conn, now, signals["category"], label)
        update_ticket(conn, other["id"], now, incident_id=incident_id)
    add_event(conn, other["id"], "related_linked", now, incident_id=incident_id,
              related_ticket=ticket_label(new_id), signals=signals, reasons=comparison["reasons"])
    update_ticket(conn, new_id, now, incident_id=incident_id)
    add_event(conn, new_id, "related_linked", now, incident_id=incident_id,
              related_ticket=ticket_label(other["id"]), signals=signals, reasons=comparison["reasons"])
    return incident_id


def _apply(conn, cfg, ticket, conversation_id, relation, turns, extraction, now, created, conversation_changed):
    merged = merge_fields(ticket["fields"], extraction["fields"])
    evidence = [item for item in ticket["evidence"] if item.get("conversation_id") != conversation_id]
    evidence += [{**item, "conversation_id": conversation_id} for item in extraction["evidence"]]
    evidence.sort(key=_evidence_key)

    category = _value(merged, "issue_category", "general")
    severity = _value(merged, "severity", DEFAULT_SEVERITY)
    if severity not in cfg.data["priority"]["severity_points"]:
        severity = DEFAULT_SEVERITY
    scored = compute_priority(
        cfg,
        severity=severity,
        impact=_value(merged, "impact", "single_customer"),
        sentiment=_value(merged, "sentiment", "neutral"),
        issue_category=category,
        created_at=parse_iso(ticket["created_at"]),
        now=now,
    )
    priority = scored["priority"]
    missing = missing_mandatory(cfg, merged)
    urgent = priority in cfg.data["urgent_priorities"]
    status = _desired_status(ticket["status"], missing, urgent)

    # ---- follow-up questions: counted only when the customer has said something new
    state = json.loads(dumps(ticket["follow_up"] or {}))
    for key in ("asked", "turn_counts", "last"):
        state.setdefault(key, {})
    customer_count = sum(
        1 for turn in turns if turn.get("role") == "customer" and str(turn.get("text", "")).strip()
    )
    if customer_count > state["turn_counts"].get(conversation_id, 0):
        questions = follow_up_questions(missing, state["asked"])
        for question in questions:
            state["asked"][question["field"]] = state["asked"].get(question["field"], 0) + 1
        state["turn_counts"][conversation_id] = customer_count
        state["last"][conversation_id] = [question["field"] for question in questions]
        asked_now = bool(questions)
    else:
        questions = [
            {"field": name, "question": QUESTIONS[name]}
            for name in state["last"].get(conversation_id, [])
            if name in missing
        ]
        asked_now = False

    # ---- what changed
    meaningful = {}
    events = []
    if _differs(ticket["fields"], merged):
        meaningful["fields"] = merged
        if not created:
            changed = sorted(
                name for name in set(merged) | set(ticket["fields"])
                if merged.get(name) != ticket["fields"].get(name)
            )
            events.append(("fields_updated", {"changed": changed}))
    if _differs(ticket["evidence"], evidence):
        meaningful["evidence"] = evidence
    if _differs(ticket["missing"], missing):
        meaningful["missing"] = missing
        if not created:
            events.append(("missing_updated", {"missing": missing}))
    if ticket["status"] != status:
        meaningful["status"] = status
        if not created:
            if ticket["status"] == "resolved":
                events.append(("reopened", {"conversation_id": conversation_id}))
            events.append(("status_changed", {"from": ticket["status"], "to": status}))
    if ticket["priority"] != priority:
        meaningful["priority"] = priority
        if not created and ticket["priority"] is not None:
            events.append(("priority_changed", {
                "from": ticket["priority"], "to": priority, "score": scored["score"],
                "rules": scored["rules_applied"], "reasons": scored["reasons"],
            }))
    if _differs(ticket["follow_up"], state):
        meaningful["follow_up"] = state
    if asked_now:
        events.append(("follow_up_asked", {"conversation_id": conversation_id,
                                           "fields": [question["field"] for question in questions]}))

    sla = scored["sla"]
    refresh = {
        "score": scored["score"],
        "priority_detail": json.loads(dumps(scored)),
        "sla_class": scored["sla_class"],
        "sla_basis": scored["sla_target"]["basis"],
        "sla_target_minutes": scored["sla_target"]["target_minutes"],
        "sla_deadline": iso(sla["deadline"]),
        "sla_warning_at": iso(sla["warning_at"]),
        "sla_state": sla["state"],
        "sla_fingerprint": cfg.calendar_fingerprint,
    }
    refresh_changes = {key: value for key, value in refresh.items() if _differs(ticket.get(key), value)}

    if meaningful or refresh_changes or conversation_changed:
        update_ticket(
            conn, ticket["id"], now,
            touch=bool(meaningful or conversation_changed),
            **meaningful, **refresh_changes,
        )
    if created:
        add_event(conn, ticket["id"], "created", now, conversation_id=conversation_id,
                  trigger=ticket["trigger_reason"], status=status, priority=priority, missing=missing,
                  reasons=scored["reasons"])
    for event_type, detail in events:
        add_event(conn, ticket["id"], event_type, now, **detail)

    changed = bool(meaningful) or conversation_changed or created
    return {
        "action": "created" if created else ("updated" if changed else "unchanged"),
        "ticket_id": ticket_label(ticket["id"]),
        "relation": relation,
        "status": status,
        "priority": priority,
        "score": scored["score"],
        "reasons": scored["reasons"],
        "missing": missing,
        "questions": questions,
        "follow_up": follow_up_text(questions),
        "incident_id": ticket["incident_id"],
        "sla_state": sla["state"],
        "sla_deadline": refresh["sla_deadline"],
    }


def _process(conn, cfg, conversation_id, turns, now, trigger_reason):
    if not any(turn.get("role") == "customer" and str(turn.get("text", "")).strip() for turn in turns):
        raise ValueError("a conversation needs at least one customer message to become a ticket")
    extraction = extract_ticket_fields(cfg, turns)
    conversation_changed = save_conversation_turns(conn, conversation_id, _masked_turns(turns), now)

    link = get_conversation_link(conn, conversation_id)
    if link is not None:
        ticket = get_ticket(conn, link["ticket_id"])
        return _apply(conn, cfg, ticket, conversation_id, link["relation"], turns, extraction, now,
                      created=False, conversation_changed=conversation_changed)

    match = _find_match(conn, cfg, extraction["fields"], now)
    if match is not None and match["decision"] == "duplicate":
        ticket = match["ticket"]
        link_conversation(conn, conversation_id, ticket["id"], "duplicate", now)
        first_message = next(
            (turn.get("text", "") for turn in turns if turn.get("role") == "customer"), ""
        )
        add_event(conn, ticket["id"], "duplicate_linked", now, conversation_id=conversation_id,
                  signals=match["comparison"]["signals"], reasons=match["comparison"]["reasons"],
                  excerpt=mask_text(first_message)[:120])
        result = _apply(conn, cfg, ticket, conversation_id, "duplicate", turns, extraction, now,
                        created=False, conversation_changed=True)
        result["action"] = "linked_duplicate"
        return result

    ticket_id = insert_ticket(conn, conversation_id, trigger_reason, now)
    link_conversation(conn, conversation_id, ticket_id, "primary", now)
    if match is not None and match["decision"] == "related":
        _join_incident(conn, ticket_id, match["ticket"], match["comparison"], now)
    ticket = get_ticket(conn, ticket_id)
    return _apply(conn, cfg, ticket, conversation_id, "primary", turns, extraction, now,
                  created=True, conversation_changed=True)


def process_conversation(cfg, conversation_id, turns, now, trigger_reason="unresolved", db_path=None):
    """Creates or updates the ticket for an unresolved conversation and returns a summary dict.

    turns: list of {"role": "customer"|"bot"|"system", "text": str, "at": str (optional),
           "attachment": {...} (optional)}. now must be timezone-aware.
    The summary has: action (created, updated, unchanged, linked_duplicate), ticket_id, relation,
    status, priority, score, reasons, missing, questions, follow_up, incident_id, sla_state,
    sla_deadline.
    """
    if not isinstance(conversation_id, str) or not conversation_id.strip():
        raise ValueError("conversation_id must be a non-empty string")
    to_utc(now)
    conn = connect(db_path)
    try:
        with transaction(conn):
            return _process(conn, cfg, conversation_id, turns, now, trigger_reason)
    finally:
        conn.close()