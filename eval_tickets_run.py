"""End-to-end evaluation of the Task 3 ticket workflow.

Run from the project root: python eval_tickets_run.py
Synthetic conversations only, in a temporary folder (temp config, temp database, temp log).
Prints one PASS/FAIL line per scenario, writes eval_results_tickets.md, exits non-zero on any failure.
"""
import copy
import json
import os
import shutil
import sys
import tempfile
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from src.tickets.config import DEFAULT_CONFIG, get_config, reset_cache
from src.tickets.handoff import build_handoff
from src.tickets.lifecycle import SUMMARY_LISTS, reconcile_open_tickets, resolve_ticket
from src.tickets.masking import mask_text
from src.tickets.store import assigned_counts, connect, count_tickets, get_ticket, iso, list_events, parse_ticket_label
from src.tickets.ticket_log import log_event
from src.tickets.workflow import process_unresolved

IST = ZoneInfo("Asia/Kolkata")
PROJECT = Path(__file__).resolve().parent
REPORT_FILE = PROJECT / "eval_results_tickets.md"
REAL_FILES = [
    PROJECT / "logs" / "tickets.jsonl",
    PROJECT / "ticket_data" / "tickets.db",
    PROJECT / "config" / "ticket_config.json",
]


def snapshot(path):
    try:
        info = path.stat()
        return (info.st_size, info.st_mtime_ns)
    except FileNotFoundError:
        return None


BEFORE = {path: snapshot(path) for path in REAL_FILES}
TMP = Path(tempfile.mkdtemp(prefix="eval_tickets_"))
CONFIG_FILE = TMP / "config.json"
BASE = copy.deepcopy(DEFAULT_CONFIG)
BASE["holidays"] = [{"date": "2026-10-22", "name": "Test holiday"}]
CACHE = {}


# ---------------------------------------------------------------- helpers
class Check:
    def __init__(self):
        self.count = 0
        self.problems = []

    def eq(self, name, got, expected):
        self.count += 1
        if got != expected:
            self.problems.append(f"{name}: got {got!r}, expected {expected!r}")


def at(year, month, day, hour=0, minute=0):
    return datetime(year, month, day, hour, minute, tzinfo=IST)


T0 = at(2026, 10, 21, 10)


def turn(role, text, **extra):
    return {"role": role, "text": text, "at": "2026-10-21T10:00:00+05:30", **extra}


def delivery(order, email):
    return [
        turn("customer", f"My order {order} has not arrived yet, please check"),
        turn("customer", f"reach me at {email}"),
    ]


def payment(order, email, twice):
    wording = "charged twice" if twice else "charged"
    return [
        turn("customer", f"I was {wording} for order {order}, please refund"),
        turn("customer", f"reach me at {email}"),
    ]


def new_db(name):
    return TMP / f"{name}.db"


def reload(mutator=None):
    data = copy.deepcopy(BASE)
    if mutator is not None:
        mutator(data)
    CONFIG_FILE.write_text(json.dumps(data, indent=2), encoding="utf-8")
    return get_config(CONFIG_FILE)


def set_agent(agent_id, **changes):
    def mutate(data):
        agent = next(item for item in data["routing"]["agents"] if item["id"] == agent_id)
        agent.update(changes)
    return mutate


def combine(*mutators):
    def mutate(data):
        for mutator in mutators:
            mutator(data)
    return mutate


def critical_at_40(data):
    data["priority"]["thresholds"] = {"critical": 40, "high": 30, "medium": 20}


def quiet(summary):
    return all(summary[name] == [] for name in SUMMARY_LISTS)


def load(db, label):
    conn = connect(db)
    try:
        return get_ticket(conn, parse_ticket_label(label))
    finally:
        conn.close()


def events(db, label):
    conn = connect(db)
    try:
        return list_events(conn, parse_ticket_label(label))
    finally:
        conn.close()


def event_types(db, label):
    return [event["type"] for event in events(db, label)]


def count_events(db, label, event_type):
    return sum(1 for event in events(db, label) if event["type"] == event_type)


def ticket_count(db):
    conn = connect(db)
    try:
        return count_tickets(conn)
    finally:
        conn.close()


def workload(db):
    conn = connect(db)
    try:
        return assigned_counts(conn)
    finally:
        conn.close()


# ---------------------------------------------------------------- scenarios
def sc_duplicates():
    c = Check()
    db = new_db("duplicates")
    cfg = reload()
    first = [turn("customer", "My order 78231 has not arrived yet, please check"),
             turn("customer", "You can email me at sam@example.com")]
    second = [turn("customer", "Order 78231 still not arrived, please check again"),
              turn("customer", "email is sam@example.com")]
    second_time = at(2026, 10, 21, 11)
    r1 = process_unresolved(cfg, "c1", first, T0, db_path=db)
    c.eq("first conversation creates the ticket", (r1["action"], r1["ticket_id"]), ("created", "TKT-000001"))
    events_before = event_types(db, "TKT-000001")
    r1b = process_unresolved(cfg, "c1", first, T0, db_path=db)
    c.eq("repeating the same conversation is unchanged", r1b["action"], "unchanged")
    c.eq("repeat adds no events", event_types(db, "TKT-000001"), events_before)
    c.eq("repeat adds no ticket", ticket_count(db), 1)
    r2 = process_unresolved(cfg, "c2", second, second_time, db_path=db)
    c.eq("second conversation is linked, not created",
         (r2["action"], r2["ticket_id"], r2["relation"]), ("linked_duplicate", "TKT-000001", "duplicate"))
    c.eq("no second ticket", ticket_count(db), 1)
    c.eq("duplicate is in the audit trail", "duplicate_linked" in event_types(db, "TKT-000001"), True)
    ticket = load(db, "TKT-000001")
    c.eq("both conversations are in the evidence",
         sorted({item["conversation_id"] for item in ticket["evidence"]}), ["c1", "c2"])
    events_after = len(events(db, "TKT-000001"))
    r2b = process_unresolved(cfg, "c2", second, second_time, db_path=db)
    c.eq("repeating the duplicate is unchanged", r2b["action"], "unchanged")
    c.eq("repeating the duplicate adds no events", len(events(db, "TKT-000001")), events_after)
    c.eq("still one ticket", ticket_count(db), 1)
    return c, f"second conversation {r2['action']} onto {r2['ticket_id']}; tickets={ticket_count(db)}; repeats unchanged"


def sc_same_order_other_issue():
    c = Check()
    db = new_db("other_issue")
    cfg = reload()
    process_unresolved(cfg, "c1", delivery("78231", "sam@example.com"), T0, db_path=db)
    r3 = process_unresolved(cfg, "c3", payment("78231", "sam@example.com", True), at(2026, 10, 21, 12), db_path=db)
    c.eq("a different issue on the same order gets its own ticket",
         (r3["action"], r3["ticket_id"]), ("created", "TKT-000002"))
    c.eq("it is not grouped with the delivery ticket", r3.get("incident_id"), None)
    c.eq("two tickets exist", ticket_count(db), 2)
    return c, f"{r3['action']} {r3['ticket_id']}; incident={r3.get('incident_id')}; tickets={ticket_count(db)}"


def sc_related_unrelated():
    c = Check()
    db = new_db("related")
    cfg = reload()
    first = [turn("customer", "Checkout fails with error E-502 when paying by card"),
             turn("customer", "You can email me at a@x.com")]
    second = [turn("customer", "Getting error E-502 at checkout this morning"),
              turn("customer", "contact me at b@y.com")]
    third = [turn("customer", "My headphones arrived damaged and I want a refund"),
             turn("customer", "my email is a@x.com")]
    r10 = process_unresolved(cfg, "c10", first, at(2026, 10, 21, 13), db_path=db)
    r11 = process_unresolved(cfg, "c11", second, at(2026, 10, 21, 13, 30), db_path=db)
    r12 = process_unresolved(cfg, "c12", third, at(2026, 10, 21, 13, 45), db_path=db)
    c.eq("first issue creates a ticket", r10["action"], "created")
    c.eq("related issue gets its own ticket", r11["action"], "created")
    c.eq("related issue joins an incident", r11.get("incident_id") is not None, True)
    c.eq("first ticket shares the incident", load(db, r10["ticket_id"])["incident_id"], r11.get("incident_id"))
    c.eq("related link is recorded on the new ticket", "related_linked" in event_types(db, r11["ticket_id"]), True)
    c.eq("related link is recorded on the first ticket", "related_linked" in event_types(db, r10["ticket_id"]), True)
    c.eq("unrelated issue from the same customer gets its own ticket", r12["action"], "created")
    c.eq("unrelated issue is not grouped", r12.get("incident_id"), None)
    c.eq("three tickets exist", ticket_count(db), 3)
    return c, f"related incident={r11.get('incident_id')}; unrelated incident={r12.get('incident_id')}; tickets={ticket_count(db)}"


def sc_missing_info():
    c = Check()
    db = new_db("missing")
    cfg = reload()
    first = [turn("customer", "Hello, my package never arrived")]
    r = process_unresolved(cfg, "m1", first, T0, db_path=db)
    c.eq("ticket waits for information", (r["ticket_id"], r["status"]), ("TKT-000001", "pending_information"))
    c.eq("missing mandatory fields are listed", r["missing"], ["order_id", "contact"])
    c.eq("follow-up asks for the order number", "order number" in r["follow_up"], True)
    c.eq("pending ticket is not routed", (r["routing"]["agent"], r["routing"]["code"]), (None, None))
    repeat = process_unresolved(cfg, "m1", first, T0, db_path=db)
    c.eq("repeat is unchanged", repeat["action"], "unchanged")
    handoff = build_handoff(cfg, "TKT-000001", T0, db_path=db)
    c.eq("each question is counted once", [q["times_asked"] for q in handoff["outstanding_questions"]], [1, 1])
    answered = first + [
        turn("bot", "Could you share your order number?"),
        turn("customer", "It is order 90001, reach me at m1@x.com"),
    ]
    r2 = process_unresolved(cfg, "m1", answered, at(2026, 10, 21, 10, 5), db_path=db)
    c.eq("answer updates the same ticket", (r2["action"], r2["ticket_id"]), ("updated", "TKT-000001"))
    c.eq("nothing is missing any more", r2["missing"], [])
    c.eq("nothing is asked again", r2["follow_up"], "")
    c.eq("ticket no longer waits", r2["status"] != "pending_information", True)
    ticket = load(db, "TKT-000001")
    c.eq("order number is stored", ticket["fields"]["order_id"]["value"], "90001")
    c.eq("contact is stored", ticket["fields"]["contact_email"]["value"], "m1@x.com")
    return c, f"asked for {r['missing']}; after the reply status={r2['status']}, missing={r2['missing']}"


def sc_priority_recalculation():
    c = Check()
    db = new_db("priority")
    cfg = reload()
    r = process_unresolved(cfg, "p1", delivery("12121", "p1@x.com"), T0, db_path=db)
    c.eq("priority at creation", r["priority"], "low")
    reconcile_open_tickets(cfg, at(2026, 10, 23, 14, 29), db_path=db)
    c.eq("priority rises with waiting time", load(db, "TKT-000001")["priority"], "medium")
    reconcile_open_tickets(cfg, at(2026, 10, 26, 10), db_path=db)
    ticket = load(db, "TKT-000001")
    c.eq("a breach raises priority to high", (ticket["sla_state"], ticket["priority"]), ("breached", "high"))
    return c, f"low at creation, medium while waiting, {ticket['priority']} after breach"


def sc_agent_unavailable():
    c = Check()
    db = new_db("route")
    CACHE["route_db"] = db
    cfg = reload()
    results = [
        process_unresolved(cfg, f"r{i}", delivery(f"1000{i}", f"a{i}@x.com"), T0, db_path=db) for i in (1, 2, 3)
    ]
    c.eq("tickets are spread by workload", [item["routing"]["agent"] for item in results],
         ["agent_orders_1", "agent_orders_2", "agent_orders_1"])
    c.eq("workload is counted from open tickets", workload(db), {"agent_orders_1": 2, "agent_orders_2": 1})
    cfg = reload(set_agent("agent_orders_1", available=False))
    summary = reconcile_open_tickets(cfg, T0, db_path=db)
    c.eq("tickets of the unavailable agent are reassigned", summary["reassigned"], ["TKT-000001", "TKT-000003"])
    owners = [load(db, label)["assigned_agent"] for label in ("TKT-000001", "TKT-000002", "TKT-000003")]
    c.eq("everything sits with the available agent", owners, ["agent_orders_2"] * 3)
    c.eq("reassignment is in the audit trail", event_types(db, "TKT-000001"), ["created", "assigned", "reassigned"])
    return c, f"reassigned {summary['reassigned']}; owners={owners}"


def sc_team_unavailable():
    c = Check()
    db = CACHE["route_db"]
    cfg = reload(combine(set_agent("agent_orders_1", available=False), set_agent("agent_orders_2", available=False)))
    summary = reconcile_open_tickets(cfg, T0, db_path=db)
    labels = ("TKT-000001", "TKT-000002", "TKT-000003")
    c.eq("tickets go to the fallback queue", summary["queued"], list(labels))
    queued = [load(db, label) for label in labels]
    c.eq("none is marked assigned", [item["status"] for item in queued], ["queued"] * 3)
    c.eq("queue name comes from the configuration", {item["queue_name"] for item in queued}, {"unassigned_queue"})
    c.eq("reason code is recorded",
         all(item["routing_reason"].startswith("team_unavailable") for item in queued), True)
    c.eq("the intended team is kept", {item["assigned_team"] for item in queued}, {"orders"})
    return c, f"queued {summary['queued']} in {queued[0]['queue_name']} ({queued[0]['routing_reason'].split(':')[0]})"


def sc_team_returns():
    c = Check()
    db = CACHE["route_db"]
    cfg = reload()
    labels = ("TKT-000001", "TKT-000002", "TKT-000003")
    summary = reconcile_open_tickets(cfg, T0, db_path=db)
    c.eq("queued tickets are assigned when agents return", summary["assigned"], list(labels))
    owners = [load(db, label)["assigned_agent"] for label in labels]
    c.eq("they are spread by workload", owners, ["agent_orders_1", "agent_orders_2", "agent_orders_1"])
    c.eq("full history is kept", event_types(db, "TKT-000001"),
         ["created", "assigned", "reassigned", "unassigned", "assigned"])
    c.eq("repeat reconcile changes nothing", quiet(reconcile_open_tickets(cfg, T0, db_path=db)), True)
    return c, f"assigned {summary['assigned']}; owners={owners}"


def sc_no_skill_match():
    c = Check()
    db = new_db("skills")
    cfg = reload(set_agent("agent_tech_1", skills=["billing"]))
    tech = [turn("customer", "The website checkout page shows error E-502 for order 80001"),
            turn("customer", "reach me at t1@x.com")]
    r = process_unresolved(cfg, "t1", tech, T0, db_path=db)
    c.eq("no skill match is queued, not assigned", (r["status"], r["routing"]["code"]), ("queued", "no_matching_agent"))
    c.eq("no agent is picked", r["routing"]["agent"], None)
    return c, f"status={r['status']}, code={r['routing']['code']}"


def sc_capacity():
    c = Check()
    db = new_db("capacity")
    cfg = reload(set_agent("agent_billing_1", max_open=1))
    rx = process_unresolved(cfg, "x", payment("70000", "x0@x.com", True), T0, db_path=db)
    ra = process_unresolved(cfg, "a", payment("70001", "a@x.com", False), T0, db_path=db)
    rb = process_unresolved(cfg, "b", payment("70002", "b@x.com", True), T0, db_path=db)
    c.eq("first ticket is assigned", (rx["status"], rx["routing"]["agent"]), ("assigned", "agent_billing_1"))
    c.eq("second waits for capacity", (ra["status"], ra["routing"]["code"]), ("queued", "all_at_capacity"))
    c.eq("third waits for capacity", (rb["status"], rb["routing"]["code"]), ("queued", "all_at_capacity"))
    c.eq("waiting tickets have different priorities", (ra["priority"], rb["priority"]), ("low", "medium"))
    c.eq("resolving frees the agent", resolve_ticket("TKT-000001", T0, "fixed", db_path=db), True)
    c.eq("resolving twice reports no change", resolve_ticket("TKT-000001", T0, "again", db_path=db), False)
    summary = reconcile_open_tickets(cfg, T0, db_path=db)
    c.eq("the higher priority ticket gets the freed slot", summary["assigned"], ["TKT-000003"])
    c.eq("the lower priority ticket keeps waiting", load(db, "TKT-000002")["status"], "queued")
    c.eq("repeat reconcile is quiet", quiet(reconcile_open_tickets(cfg, T0, db_path=db)), True)
    return c, f"freed slot went to {summary['assigned']}; TKT-000002 still queued"


def sc_after_hours():
    c = Check()
    db = new_db("after_hours")
    cfg = reload()
    saturday = at(2026, 10, 24, 23)
    r = process_unresolved(cfg, "h1", delivery("90001", "h1@x.com"), saturday, db_path=db)
    c.eq("after-hours ticket is created and queued",
         (r["action"], r["status"], r["routing"]["code"]), ("created", "queued", "after_hours"))
    c.eq("it records when support reopens", r["routing"]["queued_until"], iso(at(2026, 10, 26, 9)))
    ticket = load(db, "TKT-000001")
    c.eq("created time is the real time", ticket["created_at"], iso(saturday))
    c.eq("deadline skips the closed hours", ticket["sla_deadline"], iso(at(2026, 10, 27, 18)))
    c.eq("no working time has elapsed", ticket["priority_detail"]["sla"]["elapsed_seconds"], 0.0)
    c.eq("still waiting on Sunday", quiet(reconcile_open_tickets(cfg, at(2026, 10, 25, 12), db_path=db)), True)
    summary = reconcile_open_tickets(cfg, at(2026, 10, 26, 9), db_path=db)
    c.eq("assigned when support reopens", summary["assigned"], ["TKT-000001"])
    ticket = load(db, "TKT-000001")
    c.eq("assigned to a real agent", (ticket["status"], ticket["assigned_agent"]), ("assigned", "agent_orders_1"))
    c.eq("after-hours history", event_types(db, "TKT-000001"), ["created", "queued", "assigned"])
    return c, f"queued until Mon 09:00 ({r['routing']['code']}), assigned to {ticket['assigned_agent']} at opening"


def sc_critical_after_hours():
    c = Check()
    saturday = at(2026, 10, 24, 23)
    urgent = [turn("customer", "URGENT my account was hacked and money stolen on order 50001"),
              turn("customer", "reach me at k1@x.com")]
    cfg = reload(combine(critical_at_40, set_agent("agent_general_2", on_call=True)))
    ro = process_unresolved(cfg, "k1", urgent, saturday, db_path=new_db("oncall"))
    c.eq("ticket is critical", ro["priority"], "critical")
    c.eq("it goes to the on-call agent", (ro["status"], ro["routing"]["agent"]), ("assigned", "agent_general_2"))
    cfg = reload(critical_at_40)
    rn = process_unresolved(cfg, "k2", urgent, saturday, db_path=new_db("no_oncall"))
    c.eq("without an on-call agent it queues",
         (rn["priority"], rn["status"], rn["routing"]["code"]), ("critical", "queued", "after_hours"))
    c.eq("the reason names the on-call gap", "on-call" in rn["routing"]["reason"], True)
    return c, f"with on-call: {ro['routing']['agent']}; without: {rn['status']} ({rn['routing']['code']})"


def sc_sla_warning():
    c = Check()
    db = new_db("sla")
    CACHE["sla_db"] = db
    cfg = reload()
    process_unresolved(cfg, "s1", delivery("11111", "s1@x.com"), T0, db_path=db)
    label = "TKT-000001"
    c.eq("deadline skips the holiday and weekend", load(db, label)["sla_deadline"], iso(at(2026, 10, 26, 10)))
    summary = reconcile_open_tickets(cfg, at(2026, 10, 23, 14, 29), db_path=db)
    c.eq("no warning just before 75 percent", summary["warnings"], [])
    summary = reconcile_open_tickets(cfg, at(2026, 10, 23, 14, 30), db_path=db)
    c.eq("warning at exactly 75 percent", summary["warnings"], [label])
    ticket = load(db, label)
    c.eq("state is warning", ticket["sla_state"], "warning")
    c.eq("warning time is recorded", ticket["warning_sent_at"], iso(at(2026, 10, 23, 14, 30)))
    summary = reconcile_open_tickets(cfg, at(2026, 10, 23, 14, 31), db_path=db)
    c.eq("no repeated warning", summary["warnings"], [])
    c.eq("one warning event", count_events(db, label, "sla_warning"), 1)
    return c, f"warned at 75 percent ({ticket['warning_sent_at']}), not repeated"


def sc_sla_escalation():
    c = Check()
    db = CACHE["sla_db"]
    label = "TKT-000001"
    cfg = reload()
    summary = reconcile_open_tickets(cfg, at(2026, 10, 26, 10), db_path=db)
    c.eq("escalation at the deadline", summary["escalations"], [label])
    ticket = load(db, label)
    c.eq("breach state and priority", (ticket["sla_state"], ticket["priority"]), ("breached", "high"))
    c.eq("escalation is recorded once", (ticket["escalation_count"], ticket["escalated_at"]),
         (1, iso(at(2026, 10, 26, 10))))
    summary = reconcile_open_tickets(cfg, at(2026, 10, 26, 10, 5), db_path=db)
    c.eq("no repeated escalation", (summary["escalations"], summary["warnings"]), ([], []))
    kinds = [item for item in event_types(db, label) if item.startswith("sla_") or item == "escalated"]
    c.eq("sla events in order", kinds, ["sla_warning", "sla_breached", "escalated"])
    c.eq("escalation count stays one", load(db, label)["escalation_count"], 1)
    return c, f"escalated once at the deadline; events={kinds}"


def sc_runtime_holiday():
    c = Check()
    db = new_db("runtime_holiday")
    cfg = reload()
    process_unresolved(cfg, "rt1", delivery("22222", "r1@x.com"), T0, db_path=db)
    reconcile_open_tickets(cfg, at(2026, 10, 22, 12), db_path=db)
    cfg = reload(lambda data: data["holidays"].append({"date": "2026-10-23", "name": "Added while running"}))
    summary = reconcile_open_tickets(cfg, at(2026, 10, 22, 12), db_path=db)
    c.eq("new holiday recalculates the open ticket", summary["recalculated"], ["TKT-000001"])
    c.eq("deadline moves past the new holiday", load(db, "TKT-000001")["sla_deadline"], iso(at(2026, 10, 27, 10)))
    recalculated = next(item for item in events(db, "TKT-000001") if item["type"] == "sla_recalculated")
    c.eq("recalculation records both deadlines",
         (recalculated["detail"]["from_deadline"], recalculated["detail"]["to_deadline"]),
         (iso(at(2026, 10, 26, 10)), iso(at(2026, 10, 27, 10))))
    summary = reconcile_open_tickets(cfg, at(2026, 10, 26, 10), db_path=db)
    c.eq("no false breach on the old deadline", summary["escalations"], [])
    summary = reconcile_open_tickets(cfg, at(2026, 10, 27, 10), db_path=db)
    c.eq("escalation at the new deadline", summary["escalations"], ["TKT-000001"])
    warning = next(item for item in events(db, "TKT-000001") if item["type"] == "sla_warning")
    c.eq("late warning records the real crossing time", warning["detail"]["crossed_at"], iso(at(2026, 10, 26, 14, 30)))
    c.eq("one warning and one escalation",
         (count_events(db, "TKT-000001", "sla_warning"), count_events(db, "TKT-000001", "escalated")), (1, 1))
    return c, "deadline moved Mon 26 to Tue 27; no false breach; one escalation at the new deadline"


def sc_runtime_shorter_target():
    c = Check()
    db = new_db("runtime_shorter")
    cfg = reload()
    process_unresolved(cfg, "rt2", delivery("33333", "r2@x.com"), T0, db_path=db)
    cfg = reload(lambda data: data["sla"]["policies"]["medium"].update(target_minutes=360))
    summary = reconcile_open_tickets(cfg, at(2026, 10, 21, 17), db_path=db)
    c.eq("shorter target recalculates", summary["recalculated"], ["TKT-000001"])
    c.eq("it warns and escalates", (summary["warnings"], summary["escalations"]), (["TKT-000001"], ["TKT-000001"]))
    ticket = load(db, "TKT-000001")
    c.eq("new deadline", ticket["sla_deadline"], iso(at(2026, 10, 21, 16)))
    c.eq("breached ticket is high priority", (ticket["sla_state"], ticket["priority"]), ("breached", "high"))
    warning = next(item for item in events(db, "TKT-000001") if item["type"] == "sla_warning")
    c.eq("warning records the new threshold time", warning["detail"]["crossed_at"], iso(at(2026, 10, 21, 14, 30)))
    return c, f"target cut to 360 min; escalated on the next reconcile; deadline {ticket['sla_deadline']}"


def sc_runtime_longer_target():
    c = Check()
    db = new_db("runtime_longer")
    cfg = reload()
    process_unresolved(cfg, "rt3", delivery("44444", "r3@x.com"), T0, db_path=db)
    summary = reconcile_open_tickets(cfg, at(2026, 10, 23, 14, 30), db_path=db)
    c.eq("warning before the change", summary["warnings"], ["TKT-000001"])
    cfg = reload(lambda data: data["sla"]["policies"]["medium"].update(target_minutes=3000))
    summary = reconcile_open_tickets(cfg, at(2026, 10, 23, 14, 30), db_path=db)
    c.eq("longer target resets the warning", summary["resets"], ["TKT-000001"])
    c.eq("warning flag is cleared", load(db, "TKT-000001")["warning_sent_at"], None)
    c.eq("state is ok again", load(db, "TKT-000001")["sla_state"], "ok")
    summary = reconcile_open_tickets(cfg, at(2026, 10, 28, 11, 30), db_path=db)
    c.eq("a new crossing warns again", summary["warnings"], ["TKT-000001"])
    c.eq("two warnings in total", count_events(db, "TKT-000001", "sla_warning"), 2)
    c.eq("quiet afterwards", quiet(reconcile_open_tickets(cfg, at(2026, 10, 28, 11, 30), db_path=db)), True)
    return c, "target raised to 3000 min; warning cleared, then re-issued at the new 75 percent point"


def sc_handoff_masking():
    c = Check()
    db = new_db("handoff")
    cfg = reload()
    first_message = ("Hi, my name is Priya Nair. My order 78231 has not arrived and I was charged twice for "
                     "Rs 4500! I paid by card 4111 1111 1111 1111 and my password is hunter2xyz")
    conversation = [
        turn("customer", first_message),
        turn("bot", "Sorry about that. I could not find a tracking update, so I have asked a human to look."),
        turn("customer", "Reach me on priya@example.com or +91 98765 43210, please email me",
             attachment={"file_id": "f1", "status": "needs_better_file", "kind": "image"}),
    ]
    result = process_unresolved(cfg, "hc1", conversation, T0, db_path=db)
    c.eq("ticket is created and routed", (result["ticket_id"], result["status"], result["routing"]["agent"]),
         ("TKT-000001", "assigned", "agent_billing_1"))
    handoff = build_handoff(cfg, "TKT-000001", T0, db_path=db)
    text = handoff["text"]
    c.eq("customer name is kept", handoff["customer"]["name"], "Priya Nair")
    c.eq("email is masked", handoff["customer"]["email"], "p***@example.com")
    c.eq("phone is masked", handoff["customer"]["phone"], "+** ***** *3210")
    c.eq("order number is kept", handoff["context"]["order_id"], "78231")
    c.eq("raw email is not in the text", "priya@example.com" in text, False)
    c.eq("raw phone digits are not in the text", "98765" in text, False)
    c.eq("card number is not in the text", "4111" in text, False)
    c.eq("password is not in the text", "hunter2xyz" in text, False)
    c.eq("masked email is in the text", "p***@example.com" in text, True)
    c.eq("handoff text is already masked", mask_text(text), text)
    c.eq("inferred fields are labelled", handoff["issue"]["inferred"],
         ["issue_category", "severity", "impact", "sentiment"])
    c.eq("troubleshooting steps are listed",
         any("tracking update" in step for step in handoff["attempted_steps"]), True)
    c.eq("attachment reference is kept",
         any(item["type"] == "attachment" and item["file_id"] == "f1" for item in handoff["evidence"]), True)
    c.eq("recommended action is present", "Recommended next action" in text, True)
    return c, "name and order kept; email, phone, card and password masked or removed; text unchanged by masking again"


def sc_log_masking():
    c = Check()
    log_file = Path(os.environ["TICKET_LOG_PATH"])
    log_event("probe", note="mail john@example.com card 4111 1111 1111 1111", ids=["TKT-000001"])
    text = log_file.read_text(encoding="utf-8")
    lines = [json.loads(line) for line in text.splitlines() if line.strip()]
    c.eq("the log has entries", len(lines) > 0, True)
    c.eq("every line has a type and a timestamp", all("type" in line and "timestamp" in line for line in lines), True)
    for secret in ("priya@example.com", "98765", "4111", "hunter2xyz", "john@example.com"):
        c.eq(f"{secret} is not in the log", secret in text, False)
    return c, f"{len(lines)} log lines, none contain raw contact details, card numbers or passwords"


def sc_real_files_untouched():
    c = Check()
    for path in REAL_FILES:
        c.eq(f"{path.name} is unchanged", snapshot(path) == BEFORE[path], True)
    return c, "real log, database and configuration were not modified"


SCENARIOS = [
    ("Duplicate request and repeated processing", "Detect duplicate requests",
     "linked to the open ticket; repeats unchanged", sc_duplicates),
    ("Same order, different issue", "Separate unrelated issues",
     "own ticket, no incident", sc_same_order_other_issue),
    ("Related and unrelated issues", "Group related issues, separate unrelated ones",
     "related share an incident; unrelated stays apart", sc_related_unrelated),
    ("Missing mandatory information", "Request missing mandatory information",
     "follow-up asked once; cleared after the reply", sc_missing_info),
    ("Priority recalculation", "Priority from waiting time and SLA",
     "low, then medium, then high after breach", sc_priority_recalculation),
    ("Agent unavailable: reassignment", "Route by availability and workload",
     "tickets move to the available agent", sc_agent_unavailable),
    ("Team unavailable: fallback queue", "Route when a team is unavailable",
     "queued in the fallback queue, team kept", sc_team_unavailable),
    ("Team returns: queued tickets assigned", "Capacity returning",
     "queued tickets assigned and spread", sc_team_returns),
    ("No agent with the required skill", "Route by agent skills",
     "queued with no_matching_agent", sc_no_skill_match),
    ("Capacity limit and priority order", "Route by workload and priority",
     "freed slot goes to the higher priority", sc_capacity),
    ("After-hours request", "Respect business hours",
     "queued until reopening, then assigned", sc_after_hours),
    ("Critical request after hours", "Critical tickets may use on-call agents",
     "on-call agent, or queue naming the gap", sc_critical_after_hours),
    ("SLA warning at 75 percent", "Warn when 75 percent of the time is used",
     "one warning, no repeats", sc_sla_warning),
    ("SLA breach escalation", "Escalate automatically after a breach",
     "one escalation, no repeats", sc_sla_escalation),
    ("Runtime change: holiday added", "Runtime changes to SLA conditions",
     "deadline moves, no false breach", sc_runtime_holiday),
    ("Runtime change: shorter target", "Runtime changes to SLA conditions",
     "recalculated and escalated", sc_runtime_shorter_target),
    ("Runtime change: longer target", "Runtime changes to SLA conditions",
     "warning reset, warns again later", sc_runtime_longer_target),
    ("Masked handoff summary", "Generate a masked handoff summary",
     "contact details and secrets masked", sc_handoff_masking),
    ("Masked log", "No sensitive data in logs",
     "no raw values in the log", sc_log_masking),
    ("Real files untouched", "Evaluation does not use real data",
     "real log, database and config unchanged", sc_real_files_untouched),
]


def cell(text):
    return str(text).replace("|", "/").replace("\n", " ")[:300]


def write_report(rows, passed, total):
    lines = [
        "# Task 3 evaluation results",
        "",
        f"Run: {datetime.now():%Y-%m-%d %H:%M}. Synthetic conversations only; no customer values.",
        "",
        "| Scenario | Brief requirement | Expected | Observed | Result |",
        "|---|---|---|---|---|",
    ]
    for name, requirement, expected, observed, ok in rows:
        lines.append(f"| {cell(name)} | {cell(requirement)} | {cell(expected)} | {cell(observed)} | {'PASS' if ok else 'FAIL'} |")
    lines += ["", f"{passed}/{total} scenarios passed.", ""]
    REPORT_FILE.write_text("\n".join(lines), encoding="utf-8")


def main():
    reset_cache()
    os.environ["TICKET_LOG_PATH"] = str(TMP / "tickets.jsonl")
    rows = []
    passed = 0
    for name, requirement, expected, func in SCENARIOS:
        try:
            check, observed = func()
            ok = not check.problems
            if not ok:
                observed = "mismatch: " + check.problems[0]
        except Exception as error:
            ok = False
            observed = f"error: {type(error).__name__}: {error}"
        passed += 1 if ok else 0
        rows.append((name, requirement, expected, observed, ok))
        print(("PASS  " if ok else "FAIL  ") + name + ("" if ok else " - " + observed))
    write_report(rows, passed, len(SCENARIOS))
    print(f"{passed}/{len(SCENARIOS)} scenarios passed. Report: {REPORT_FILE.name}")
    return 0 if passed == len(SCENARIOS) else 1


if __name__ == "__main__":
    try:
        code = main()
    finally:
        os.environ.pop("TICKET_LOG_PATH", None)
        shutil.rmtree(TMP, ignore_errors=True)
    sys.exit(code)