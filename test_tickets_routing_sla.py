"""Routing, after-hours, SLA warning/escalation and runtime-change checks (temporary files only)."""
import copy
import json
import os
import sys
import tempfile
import time
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from src.tickets.config import DEFAULT_CONFIG, get_config, reset_cache
from src.tickets.lifecycle import SUMMARY_LISTS, reconcile_open_tickets, reset_sla_flags, resolve_ticket
from src.tickets.service import process_conversation
from src.tickets.store import assigned_counts, connect, get_ticket, iso, list_events, parse_ticket_label
from src.tickets.workflow import process_unresolved, reconciler_running, start_reconciler, stop_reconciler

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


def at(year, month, day, hour=0, minute=0):
    return datetime(year, month, day, hour, minute, tzinfo=IST)


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


def event_total(db):
    conn = connect(db)
    try:
        return conn.execute("SELECT COUNT(*) FROM events").fetchone()[0]
    finally:
        conn.close()


def workload(db):
    conn = connect(db)
    try:
        return assigned_counts(conn)
    finally:
        conn.close()


reset_cache()
with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
    os.environ["TICKET_LOG_PATH"] = str(Path(tmp) / "tickets.jsonl")
    base = copy.deepcopy(DEFAULT_CONFIG)
    base["holidays"] = [{"date": "2026-10-22", "name": "Test holiday"}]
    config_file = Path(tmp) / "config.json"

    def reload(mutator=None):
        data = copy.deepcopy(base)
        if mutator is not None:
            mutator(data)
        config_file.write_text(json.dumps(data, indent=2), encoding="utf-8")
        return get_config(config_file)

    def agent_of(data, agent_id):
        return next(item for item in data["routing"]["agents"] if item["id"] == agent_id)

    def set_agent(agent_id, **changes):
        def mutate(data):
            agent_of(data, agent_id).update(changes)
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

    t0 = at(2026, 10, 21, 10)

    # ------------------------------------------------------------ workload-aware routing
    db1 = Path(tmp) / "route.db"
    cfg = reload()
    r1 = process_unresolved(cfg, "r1", delivery("10001", "a1@x.com"), t0, db_path=db1)
    r2 = process_unresolved(cfg, "r2", delivery("10002", "a2@x.com"), t0, db_path=db1)
    r3 = process_unresolved(cfg, "r3", delivery("10003", "a3@x.com"), t0, db_path=db1)
    check("first ticket takes the lowest id on a tie", (r1["status"], r1["routing"]["agent"]), ("assigned", "agent_orders_1"))
    check("second ticket goes to the less loaded agent", r2["routing"]["agent"], "agent_orders_2")
    check("third ticket ties again and takes the lower id", r3["routing"]["agent"], "agent_orders_1")
    check("workload is counted from open tickets", workload(db1), {"agent_orders_1": 2, "agent_orders_2": 1})
    check("routing reason is recorded", (r1["routing"]["code"], "lowest workload" in r1["routing"]["reason"]), ("assigned", True))
    check("team is recorded", r1["routing"]["team"], "orders")

    # availability changes: reassignment
    cfg = reload(set_agent("agent_orders_1", available=False))
    summary = reconcile_open_tickets(cfg, t0, db_path=db1)
    check("tickets of the unavailable agent are reassigned", summary["reassigned"], ["TKT-000001", "TKT-000003"])
    check("everything now sits with the available agent",
          [load(db1, label)["assigned_agent"] for label in ("TKT-000001", "TKT-000002", "TKT-000003")],
          ["agent_orders_2", "agent_orders_2", "agent_orders_2"])
    check("reassignment is in the audit trail", event_types(db1, "TKT-000001"), ["created", "assigned", "reassigned"])

    # no agent at all: tickets are kept in the fallback queue
    cfg = reload(combine(set_agent("agent_orders_1", available=False), set_agent("agent_orders_2", available=False)))
    summary = reconcile_open_tickets(cfg, t0, db_path=db1)
    check("tickets go to the fallback queue", summary["queued"], ["TKT-000001", "TKT-000002", "TKT-000003"])
    queued = [load(db1, label) for label in ("TKT-000001", "TKT-000002", "TKT-000003")]
    check("none is marked assigned", [t["status"] for t in queued], ["queued", "queued", "queued"])
    check("queue name comes from the configuration", {t["queue_name"] for t in queued}, {"unassigned_queue"})
    check("reason code is recorded", all(t["routing_reason"].startswith("team_unavailable") for t in queued), True)
    check("the intended team is kept", {t["assigned_team"] for t in queued}, {"orders"})

    # capacity returns
    cfg = reload()
    summary = reconcile_open_tickets(cfg, t0, db_path=db1)
    check("queued tickets are assigned when agents return", summary["assigned"], ["TKT-000001", "TKT-000002", "TKT-000003"])
    check("they are spread by workload",
          [load(db1, label)["assigned_agent"] for label in ("TKT-000001", "TKT-000002", "TKT-000003")],
          ["agent_orders_1", "agent_orders_2", "agent_orders_1"])
    check("full history is kept", event_types(db1, "TKT-000001"),
          ["created", "assigned", "reassigned", "unassigned", "assigned"])
    check("repeat reconcile changes nothing", quiet(reconcile_open_tickets(cfg, t0, db_path=db1)), True)

    # ------------------------------------------------------------ no skill match
    db2 = Path(tmp) / "skills.db"
    cfg = reload(set_agent("agent_tech_1", skills=["billing"]))
    tech = [turn("customer", "The website checkout page shows error E-502 for order 80001"),
            turn("customer", "reach me at t1@x.com")]
    rt = process_unresolved(cfg, "t1", tech, t0, db_path=db2)
    check("no skill match is queued, not assigned", (rt["status"], rt["routing"]["code"]), ("queued", "no_matching_agent"))
    check("no skill match has no agent", rt["routing"]["agent"], None)

    # ------------------------------------------------------------ capacity and priority order
    db3 = Path(tmp) / "capacity.db"
    cfg = reload(set_agent("agent_billing_1", max_open=1))
    rx = process_unresolved(cfg, "x", payment("70000", "x0@x.com", True), t0, db_path=db3)
    ra = process_unresolved(cfg, "a", payment("70001", "a@x.com", False), t0, db_path=db3)
    rb = process_unresolved(cfg, "b", payment("70002", "b@x.com", True), t0, db_path=db3)
    check("first payment ticket is assigned", (rx["status"], rx["routing"]["agent"]), ("assigned", "agent_billing_1"))
    check("second waits for capacity", (ra["status"], ra["routing"]["code"]), ("queued", "all_at_capacity"))
    check("third waits for capacity", (rb["status"], rb["routing"]["code"]), ("queued", "all_at_capacity"))
    check("priorities differ", (ra["priority"], rb["priority"]), ("low", "medium"))
    check("resolving frees the agent", resolve_ticket("TKT-000001", t0, "fixed", db_path=db3), True)
    check("resolving twice reports no change", resolve_ticket("TKT-000001", t0, "again", db_path=db3), False)
    summary = reconcile_open_tickets(cfg, t0, db_path=db3)
    check("the higher priority ticket gets the freed slot", summary["assigned"], ["TKT-000003"])
    check("the lower priority ticket keeps waiting", load(db3, "TKT-000002")["status"], "queued")
    check("waiting ticket history", event_types(db3, "TKT-000002"), ["created", "queued"])
    check("assigned ticket history", event_types(db3, "TKT-000003"), ["created", "queued", "assigned"])
    check("resolved ticket history", event_types(db3, "TKT-000001"), ["created", "assigned", "resolved"])
    before = event_total(db3)
    check("repeat reconcile is quiet", quiet(reconcile_open_tickets(cfg, t0, db_path=db3)), True)
    check("repeat reconcile adds no events", event_total(db3), before)

    # ------------------------------------------------------------ after hours
    db4 = Path(tmp) / "after_hours.db"
    cfg = reload()
    saturday = at(2026, 10, 24, 23)
    rh = process_unresolved(cfg, "h1", delivery("90001", "h1@x.com"), saturday, db_path=db4)
    check("after-hours ticket is created and queued", (rh["action"], rh["status"], rh["routing"]["code"]),
          ("created", "queued", "after_hours"))
    check("it records when support reopens", rh["routing"]["queued_until"], iso(at(2026, 10, 26, 9)))
    th = load(db4, "TKT-000001")
    check("created time is the real time", th["created_at"], iso(saturday))
    check("deadline skips the closed hours", th["sla_deadline"], iso(at(2026, 10, 27, 18)))
    check("no working time has elapsed", th["priority_detail"]["sla"]["elapsed_seconds"], 0.0)
    check("still waiting on Sunday", quiet(reconcile_open_tickets(cfg, at(2026, 10, 25, 12), db_path=db4)), True)
    summary = reconcile_open_tickets(cfg, at(2026, 10, 26, 9), db_path=db4)
    check("assigned when support reopens", summary["assigned"], ["TKT-000001"])
    th = load(db4, "TKT-000001")
    check("assigned to a real agent", (th["status"], th["assigned_agent"], th["queued_until"]), ("assigned", "agent_orders_1", None))
    check("sla is fine at opening time", th["sla_state"], "ok")
    check("after-hours history", event_types(db4, "TKT-000001"), ["created", "queued", "assigned"])

    # urgent tickets may use on-call agents after hours
    urgent = [turn("customer", "URGENT my account was hacked and money stolen on order 50001"),
              turn("customer", "reach me at k1@x.com")]
    db5 = Path(tmp) / "oncall.db"
    cfg = reload(combine(critical_at_40, set_agent("agent_general_2", on_call=True)))
    ro = process_unresolved(cfg, "k1", urgent, saturday, db_path=db5)
    check("critical ticket after hours", ro["priority"], "critical")
    check("critical ticket goes to the on-call agent", (ro["status"], ro["routing"]["agent"]), ("assigned", "agent_general_2"))
    db6 = Path(tmp) / "no_oncall.db"
    cfg = reload(critical_at_40)
    rn = process_unresolved(cfg, "k2", urgent, saturday, db_path=db6)
    check("without an on-call agent it queues", (rn["priority"], rn["status"], rn["routing"]["code"]),
          ("critical", "queued", "after_hours"))
    check("the reason names the on-call gap", "on-call" in rn["routing"]["reason"], True)

    # ------------------------------------------------------------ SLA warning and escalation
    db_sla = Path(tmp) / "sla.db"
    cfg = reload()
    process_unresolved(cfg, "s1", delivery("11111", "s1@x.com"), t0, db_path=db_sla)
    label = "TKT-000001"
    check("deadline for the sla ticket", load(db_sla, label)["sla_deadline"], iso(at(2026, 10, 26, 10)))
    summary = reconcile_open_tickets(cfg, at(2026, 10, 23, 14, 29), db_path=db_sla)
    check("no warning just before 75 percent", summary["warnings"], [])
    check("priority rose with waiting", load(db_sla, label)["priority"], "medium")
    summary = reconcile_open_tickets(cfg, at(2026, 10, 23, 14, 30), db_path=db_sla)
    check("warning at exactly 75 percent", summary["warnings"], [label])
    check("warning state", load(db_sla, label)["sla_state"], "warning")
    check("warning time is recorded", load(db_sla, label)["warning_sent_at"], iso(at(2026, 10, 23, 14, 30)))
    summary = reconcile_open_tickets(cfg, at(2026, 10, 23, 14, 31), db_path=db_sla)
    check("no repeated warning", summary["warnings"], [])
    summary = reconcile_open_tickets(cfg, at(2026, 10, 26, 10), db_path=db_sla)
    check("escalation at the deadline", summary["escalations"], [label])
    tk = load(db_sla, label)
    check("breach state and priority", (tk["sla_state"], tk["priority"]), ("breached", "high"))
    check("escalation is recorded once", (tk["escalation_count"], tk["escalated_at"]), (1, iso(at(2026, 10, 26, 10))))
    summary = reconcile_open_tickets(cfg, at(2026, 10, 26, 10, 5), db_path=db_sla)
    check("no repeated escalation", (summary["escalations"], summary["warnings"]), ([], []))
    check("sla events in order", [t for t in event_types(db_sla, label) if t.startswith("sla_") or t == "escalated"],
          ["sla_warning", "sla_breached", "escalated"])
    check("escalation count unchanged", load(db_sla, label)["escalation_count"], 1)
    check("explicit reset clears both flags",
          reset_sla_flags(label, at(2026, 10, 26, 10, 6), "supervisor reset", db_path=db_sla), ["warning", "escalation"])
    summary = reconcile_open_tickets(cfg, at(2026, 10, 26, 10, 10), db_path=db_sla)
    check("an explicit reset allows a new escalation", summary["escalations"], [label])
    check("escalation count after reset", load(db_sla, label)["escalation_count"], 2)

    # ------------------------------------------------------------ runtime SLA changes
    # a holiday added while the ticket is open moves its deadline and prevents a false breach
    db_rt1 = Path(tmp) / "runtime_holiday.db"
    cfg = reload()
    process_unresolved(cfg, "rt1", delivery("22222", "r1@x.com"), t0, db_path=db_rt1)
    reconcile_open_tickets(cfg, at(2026, 10, 22, 12), db_path=db_rt1)
    cfg = reload(lambda d: d["holidays"].append({"date": "2026-10-23", "name": "Added while running"}))
    summary = reconcile_open_tickets(cfg, at(2026, 10, 22, 12), db_path=db_rt1)
    check("new holiday recalculates the open ticket", summary["recalculated"], ["TKT-000001"])
    check("deadline moves past the new holiday", load(db_rt1, "TKT-000001")["sla_deadline"], iso(at(2026, 10, 27, 10)))
    recalculated = next(e for e in events(db_rt1, "TKT-000001") if e["type"] == "sla_recalculated")
    check("recalculation records both deadlines",
          (recalculated["detail"]["from_deadline"], recalculated["detail"]["to_deadline"]),
          (iso(at(2026, 10, 26, 10)), iso(at(2026, 10, 27, 10))))
    summary = reconcile_open_tickets(cfg, at(2026, 10, 26, 10), db_path=db_rt1)
    check("no false breach on the old deadline", summary["escalations"], [])
    summary = reconcile_open_tickets(cfg, at(2026, 10, 27, 10), db_path=db_rt1)
    check("escalation at the new deadline", summary["escalations"], ["TKT-000001"])
    late_warning = next(e for e in events(db_rt1, "TKT-000001") if e["type"] == "sla_warning")
    check("a late warning records when 75 percent was really reached",
          late_warning["detail"]["crossed_at"], iso(at(2026, 10, 26, 14, 30)))
    check("one warning and one escalation", (count_events(db_rt1, "TKT-000001", "sla_warning"),
                                             count_events(db_rt1, "TKT-000001", "escalated")), (1, 1))

    # a shorter target applied while the ticket is open escalates it on the next reconcile
    db_rt2 = Path(tmp) / "runtime_target.db"
    cfg = reload()
    process_unresolved(cfg, "rt2", delivery("33333", "r2@x.com"), t0, db_path=db_rt2)
    cfg = reload(lambda d: d["sla"]["policies"]["medium"].update(target_minutes=360))
    summary = reconcile_open_tickets(cfg, at(2026, 10, 21, 17), db_path=db_rt2)
    check("shorter target recalculates", summary["recalculated"], ["TKT-000001"])
    check("shorter target warns and escalates", (summary["warnings"], summary["escalations"]), (["TKT-000001"], ["TKT-000001"]))
    tk = load(db_rt2, "TKT-000001")
    check("new deadline", tk["sla_deadline"], iso(at(2026, 10, 21, 16)))
    check("breached ticket is high priority", (tk["sla_state"], tk["priority"]), ("breached", "high"))
    warning = next(e for e in events(db_rt2, "TKT-000001") if e["type"] == "sla_warning")
    check("warning records the new threshold time", warning["detail"]["crossed_at"], iso(at(2026, 10, 21, 14, 30)))

    # a longer target clears the warning, and a later crossing warns again
    db_rt3 = Path(tmp) / "runtime_reset.db"
    cfg = reload()
    process_unresolved(cfg, "rt3", delivery("44444", "r3@x.com"), t0, db_path=db_rt3)
    summary = reconcile_open_tickets(cfg, at(2026, 10, 23, 14, 30), db_path=db_rt3)
    check("warning before the change", summary["warnings"], ["TKT-000001"])
    cfg = reload(lambda d: d["sla"]["policies"]["medium"].update(target_minutes=3000))
    summary = reconcile_open_tickets(cfg, at(2026, 10, 23, 14, 30), db_path=db_rt3)
    check("longer target resets the warning", summary["resets"], ["TKT-000001"])
    check("warning flag is cleared", load(db_rt3, "TKT-000001")["warning_sent_at"], None)
    check("state is ok again", load(db_rt3, "TKT-000001")["sla_state"], "ok")
    summary = reconcile_open_tickets(cfg, at(2026, 10, 28, 11, 30), db_path=db_rt3)
    check("a new crossing warns again", summary["warnings"], ["TKT-000001"])
    check("two warnings in total", count_events(db_rt3, "TKT-000001", "sla_warning"), 2)
    check("quiet afterwards", quiet(reconcile_open_tickets(cfg, at(2026, 10, 28, 11, 30), db_path=db_rt3)), True)

    # ------------------------------------------------------------ background reconciler
    db_thread = Path(tmp) / "thread.db"
    cfg = reload()
    process_conversation(cfg, "bg1", delivery("55555", "th@x.com"), t0, db_path=db_thread)
    check("service alone leaves the ticket unrouted", load(db_thread, "TKT-000001")["status"], "open")
    check("reconciler starts", start_reconciler(0.2, db_path=db_thread, config_loader=lambda: cfg, clock=lambda: t0), True)
    check("reconciler reports running", reconciler_running(), True)
    check("a second start is refused",
          start_reconciler(0.2, db_path=db_thread, config_loader=lambda: cfg, clock=lambda: t0), False)
    deadline = time.time() + 20
    while time.time() < deadline and load(db_thread, "TKT-000001")["status"] != "assigned":
        time.sleep(0.2)
    check("the background loop routed the ticket", load(db_thread, "TKT-000001")["status"], "assigned")
    check("reconciler stops", stop_reconciler(), True)
    check("reconciler is no longer running", reconciler_running(), False)

os.environ.pop("TICKET_LOG_PATH", None)
print(f"checks run: {total}, problems: {problems}")
sys.exit(1 if problems else 0)