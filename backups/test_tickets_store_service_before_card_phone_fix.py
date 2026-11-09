"""Checks for src\\tickets\\store.py, duplicates.py and service.py (temporary files only)."""
import copy
import json
import sys
import tempfile
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from src.tickets.config import DEFAULT_CONFIG, get_config, reset_cache
from src.tickets.duplicates import compare_fields, identity_keys, similarity, tokens
from src.tickets.service import process_conversation
from src.tickets.store import (
    connect,
    count_tickets,
    get_conversation_turns,
    get_ticket,
    iso,
    list_events,
    parse_ticket_label,
    ticket_label,
    update_ticket,
)

IST = ZoneInfo("Asia/Kolkata")
total = 0
problems = 0


def check(name, got, expected):
    global total, problems
    total += 1
    if got == expected:
        print(f"ok   {name}")
    else:
        problems += 1
        print(f"FAIL {name}: got {got!r}, expected {expected!r}")


def raises(name, exception_type, function):
    global total, problems
    total += 1
    try:
        function()
    except exception_type:
        print(f"ok   {name}")
    except Exception as error:
        problems += 1
        print(f"FAIL {name}: raised {type(error).__name__} instead of {exception_type.__name__}")
    else:
        problems += 1
        print(f"FAIL {name}: nothing was raised")


def at(year, month, day, hour=0, minute=0):
    return datetime(year, month, day, hour, minute, tzinfo=IST)


def turn(role, text, **extra):
    return {"role": role, "text": text, "at": "2026-10-21T10:00:00+05:30", **extra}


def fld(category=None, email=None, order=None, errors=None, product=None, text="", phone=None):
    fields = {}
    if category:
        fields["issue_category"] = {"value": category}
    if email:
        fields["contact_email"] = {"value": email}
    if phone:
        fields["contact_phone"] = {"value": phone}
    if order:
        fields["order_id"] = {"value": order}
    if errors:
        fields["error_codes"] = {"value": errors}
    if product:
        fields["product"] = {"value": product}
    if text:
        fields["issue_description"] = {"value": text}
    return fields


reset_cache()

with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
    base = copy.deepcopy(DEFAULT_CONFIG)
    base["holidays"] = [{"date": "2026-10-22", "name": "Test holiday"}]
    config_file = Path(tmp) / "config.json"
    config_file.write_text(json.dumps(base, indent=2), encoding="utf-8")
    cfg = get_config(config_file)
    db = Path(tmp) / "tickets.db"

    def run(conversation_id, turns, now):
        return process_conversation(cfg, conversation_id, turns, now, db_path=db)

    def tickets_total():
        conn = connect(db)
        try:
            return count_tickets(conn)
        finally:
            conn.close()

    def load(label):
        conn = connect(db)
        try:
            return get_ticket(conn, parse_ticket_label(label))
        finally:
            conn.close()

    def events_of(label):
        conn = connect(db)
        try:
            return list_events(conn, parse_ticket_label(label))
        finally:
            conn.close()

    def event_types(label):
        return [event["type"] for event in events_of(label)]

    # ---------------------------------------------------- similarity and comparison
    check("tokens drop filler and numbers", tokens("My order 78231 has not arrived yet, please check"),
          {"order", "not", "arrived", "check"})
    check("identical descriptions", similarity("order not arrived", "not arrived order"), 1.0)
    check("empty description scores zero", similarity("", "anything here"), 0.0)
    check("unrelated descriptions score low", similarity("package late", "refund for headphones") < 0.2, True)
    check("phone digits identify a customer",
          identity_keys(fld(phone="+91 98765 43210")) == identity_keys(fld(phone="9876543210")), True)

    same_customer_other_issue = compare_fields(
        cfg,
        fld("delivery", email="a@x.com", text="package late"),
        fld("delivery", email="a@x.com", text="totally different words entirely"),
    )
    check("same customer and category but another issue stays unrelated",
          same_customer_other_issue["decision"], "unrelated")
    shared_order_mid_similarity = compare_fields(
        cfg,
        fld("delivery", order="111111", text="order not arrived"),
        fld("delivery", order="111111", text="order not delivered"),
    )
    check("shared order with middling similarity is related", shared_order_mid_similarity["decision"], "related")
    same_text_no_identity = compare_fields(
        cfg,
        fld("delivery", order="111111", text="order not arrived check"),
        fld("delivery", order="222222", text="order not arrived check"),
    )
    check("identical text without a shared customer or order is unrelated", same_text_no_identity["decision"], "unrelated")
    different_category = compare_fields(
        cfg,
        fld("payment", email="a@x.com", order="111111", text="charged twice for order"),
        fld("delivery", email="a@x.com", order="111111", text="charged twice for order"),
    )
    check("different category is unrelated even with everything else shared", different_category["decision"], "unrelated")
    check("decisions explain themselves", "decision: unrelated" in different_category["reasons"], True)

    # --------------------------------------------------------------- store helpers
    check("ticket label round trip", parse_ticket_label(ticket_label(7)), 7)
    raises("bad ticket label is refused", ValueError, lambda: parse_ticket_label("ORD-12"))

    # ------------------------------------------------ one ticket per conversation
    base_time = at(2026, 10, 21, 10)
    c1 = [
        turn("customer", "My order 78231 has not arrived yet, please check"),
        turn("customer", "You can email me at sam@example.com"),
    ]
    r1 = run("c1", c1, base_time)
    check("c1 created", r1["action"], "created")
    check("c1 ticket id", r1["ticket_id"], "TKT-000001")
    check("c1 status", r1["status"], "open")
    check("c1 nothing missing", r1["missing"], [])
    check("c1 priority", r1["priority"], "low")
    t1 = load("TKT-000001")
    check("c1 sla class", t1["sla_class"], "medium")
    check("c1 sla basis", t1["sla_basis"], "business")
    check("c1 sla deadline skips the holiday and weekend", t1["sla_deadline"], iso(at(2026, 10, 26, 10)))
    check("c1 sla fingerprint recorded", t1["sla_fingerprint"], cfg.calendar_fingerprint)
    check("c1 events", event_types("TKT-000001"), ["created"])

    r1b = run("c1", c1, base_time)
    check("c1 repeat is unchanged", r1b["action"], "unchanged")
    check("c1 repeat adds no ticket", tickets_total(), 1)
    check("c1 repeat adds no event", event_types("TKT-000001"), ["created"])

    # ------------------------------------------------------ duplicate linking
    c2 = [
        turn("customer", "Order 78231 still not arrived, please check again"),
        turn("customer", "email is sam@example.com"),
    ]
    c2_time = at(2026, 10, 21, 11)
    r2 = run("c2", c2, c2_time)
    check("c2 is linked, not created", r2["action"], "linked_duplicate")
    check("c2 lands on the original ticket", r2["ticket_id"], "TKT-000001")
    check("c2 relation", r2["relation"], "duplicate")
    check("c2 adds no ticket", tickets_total(), 1)
    t1 = load("TKT-000001")
    check("c2 audit event exists", "duplicate_linked" in event_types("TKT-000001"), True)
    check("both conversations are in the evidence", sorted({e["conversation_id"] for e in t1["evidence"]}), ["c1", "c2"])
    conn = connect(db)
    try:
        link_rows = conn.execute("SELECT conversation_id, relation FROM conversations ORDER BY conversation_id").fetchall()
        check("both conversations are linked", [(row["conversation_id"], row["relation"]) for row in link_rows],
              [("c1", "primary"), ("c2", "duplicate")])
        check("original conversation text is kept", len(get_conversation_turns(conn, "c1")), 2)
        check("duplicate conversation text is kept", len(get_conversation_turns(conn, "c2")), 2)
    finally:
        conn.close()
    events_after_c2 = len(events_of("TKT-000001"))
    r2b = run("c2", c2, c2_time)
    check("c2 repeat is unchanged", r2b["action"], "unchanged")
    check("c2 repeat adds no event", len(events_of("TKT-000001")), events_after_c2)
    check("c2 repeat adds no ticket", tickets_total(), 1)

    # ------------------------------------- same customer and order, different issue
    c3 = [
        turn("customer", "I was charged twice for order 78231, please refund"),
        turn("customer", "mail me at sam@example.com"),
    ]
    r3 = run("c3", c3, at(2026, 10, 21, 12))
    check("a different issue on the same order gets its own ticket", (r3["action"], r3["ticket_id"]),
          ("created", "TKT-000002"))
    check("c3 is not grouped with c1", r3["incident_id"], None)
    check("c3 priority", r3["priority"], "medium")

    # ------------------------------------------- missing information and follow-up
    c10 = [
        turn("customer", "Checkout fails with error E-502 when paying by card"),
        turn("customer", "You can email me at a@x.com"),
    ]
    c10_time = at(2026, 10, 21, 13)
    r10 = run("c10", c10, c10_time)
    check("c10 created", (r10["action"], r10["ticket_id"]), ("created", "TKT-000003"))
    check("c10 waits for information", r10["status"], "pending_information")
    check("c10 missing field", r10["missing"], ["order_id"])
    check("c10 asks for the order number", "order number" in r10["follow_up"], True)
    r10b = run("c10", c10, c10_time)
    check("c10 repeat is unchanged", r10b["action"], "unchanged")
    check("c10 repeat shows the same question", r10b["follow_up"], r10["follow_up"])
    check("c10 question counted once", load("TKT-000003")["follow_up"]["asked"], {"order_id": 1})

    # ------------------------------------------ related issue shares an incident
    c11 = [
        turn("customer", "Getting error E-502 at checkout this morning"),
        turn("customer", "contact me at b@y.com"),
    ]
    r11 = run("c11", c11, at(2026, 10, 21, 13, 30))
    check("c11 gets its own ticket", (r11["action"], r11["ticket_id"]), ("created", "TKT-000004"))
    check("c11 joins an incident", r11["incident_id"] is not None, True)
    check("c10 shares the same incident", load("TKT-000003")["incident_id"], r11["incident_id"])
    check("c11 related event", "related_linked" in event_types("TKT-000004"), True)
    check("c10 related event", "related_linked" in event_types("TKT-000003"), True)

    # ------------------------------------ same customer, unrelated issue stays apart
    c12 = [
        turn("customer", "My headphones arrived damaged and I want a refund"),
        turn("customer", "my email is a@x.com"),
    ]
    r12 = run("c12", c12, at(2026, 10, 21, 13, 45))
    check("c12 gets its own ticket", (r12["action"], r12["ticket_id"]), ("created", "TKT-000005"))
    check("c12 is not grouped with c10", r12["incident_id"], None)

    # ---------------------------- customer answers the question: nothing is re-asked
    c10_more = c10 + [
        turn("bot", "Could you share your order number?"),
        turn("customer", "It is order 90001"),
    ]
    r10c = run("c10", c10_more, at(2026, 10, 21, 14))
    check("c10 update", r10c["action"], "updated")
    check("c10 no longer waits", r10c["status"], "open")
    check("c10 nothing missing", r10c["missing"], [])
    check("c10 no new question", r10c["follow_up"], "")
    t3 = load("TKT-000003")
    check("c10 order number stored", t3["fields"]["order_id"]["value"], "90001")
    check("c10 contact is preserved", t3["fields"]["contact_email"]["value"], "a@x.com")
    check("c10 question count unchanged", t3["follow_up"]["asked"], {"order_id": 1})
    check("c10 status change recorded", "status_changed" in event_types("TKT-000003"), True)

    # --------------------------------------------------------- after-hours request
    c40 = [
        turn("customer", "My order 33333 has not arrived yet, please check"),
        turn("customer", "reach me at z@z.com"),
    ]
    r40 = run("c40", c40, at(2026, 10, 24, 23))
    check("c40 created on a Saturday night", (r40["action"], r40["ticket_id"]), ("created", "TKT-000006"))
    t6 = load("TKT-000006")
    check("c40 created time is the real moment", t6["created_at"], iso(at(2026, 10, 24, 23)))
    check("c40 deadline counts only working time", t6["sla_deadline"], iso(at(2026, 10, 27, 18)))
    check("c40 no working time has elapsed", t6["priority_detail"]["sla"]["elapsed_seconds"], 0.0)
    check("c40 sla is ok", t6["sla_state"], "ok")

    # ------------------------------ similar text without a shared customer or order
    c20 = [
        turn("customer", "My order 78231 has not arrived yet, please check"),
        turn("customer", "You can email me at sam@example.com"),
    ]
    r20 = run("c20", c20, at(2026, 10, 26, 10))
    check("same text five days later is a new ticket", (r20["action"], r20["ticket_id"]), ("created", "TKT-000007"))
    check("c20 is not grouped with c40 despite identical wording", r20["incident_id"], None)

    # ---------------------------------------- urgent issue is not held back
    c30 = [turn("customer", "URGENT my account was hacked and money stolen")]
    r30 = run("c30", c30, at(2026, 10, 26, 11))
    check("c30 created", (r30["action"], r30["ticket_id"]), ("created", "TKT-000008"))
    check("c30 priority", r30["priority"], "high")
    check("c30 is open despite missing information", r30["status"], "open")
    check("c30 missing fields are recorded", r30["missing"], ["order_id", "contact"])
    check("c30 still asks questions", len(r30["questions"]) > 0, True)

    # --------------------------------------------- sensitive data never stored
    c50 = [
        turn("customer", "Charged twice on card 4111 1111 1111 1111, my password is hunter2xyz for order 44444"),
        turn("customer", "mail me at card@z.com"),
    ]
    r50 = run("c50", c50, at(2026, 10, 26, 12))
    check("c50 created", (r50["action"], r50["ticket_id"]), ("created", "TKT-000009"))
    conn = connect(db)
    try:
        dump = "\n".join(conn.iterdump())
    finally:
        conn.close()
    check("card number is not in the database", "4111 1111" in dump, False)
    check("password is not in the database", "hunter2xyz" in dump, False)
    check("masked card is in the database", "[CARD ending 1111]" in dump, True)
    check("tickets created in total", tickets_total(), 9)

    # --------------------------------------- priority is recalculated over time
    r1c = run("c1", c1, at(2026, 10, 21, 20))
    check("waiting raises the priority", (r1c["action"], r1c["priority"]), ("updated", "medium"))
    check("priority change is recorded", "priority_changed" in event_types("TKT-000001"), True)

    # --------------------------------------------------------------- bad input
    raises("bot-only conversation is refused", ValueError, lambda: run("c99", [turn("bot", "hello")], base_time))
    raises("naive time is refused", ValueError,
           lambda: process_conversation(cfg, "c98", c1, datetime(2026, 10, 21, 10), db_path=db))
    raises("blank conversation id is refused", ValueError, lambda: run("  ", c1, base_time))
    conn = connect(db)
    try:
        raises("unknown column is refused", ValueError, lambda: update_ticket(conn, 1, base_time, nonsense=1))
    finally:
        conn.close()

print(f"checks run: {total}, problems: {problems}")
sys.exit(1 if problems else 0)