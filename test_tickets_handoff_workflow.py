"""Handoff summary, masked logging and workflow wrapper checks (temporary files only)."""
import copy
import json
import os
import sys
import tempfile
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from src.tickets.config import DEFAULT_CONFIG, get_config, reset_cache
from src.tickets.handoff import build_handoff
from src.tickets.masking import mask_text
from src.tickets.ticket_log import log_event
from src.tickets.workflow import process_unresolved, run_reconcile

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


reset_cache()
with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
    log_file = Path(tmp) / "tickets.jsonl"
    os.environ["TICKET_LOG_PATH"] = str(log_file)
    base = copy.deepcopy(DEFAULT_CONFIG)
    base["holidays"] = [{"date": "2026-10-22", "name": "Test holiday"}]
    config_file = Path(tmp) / "config.json"
    config_file.write_text(json.dumps(base, indent=2), encoding="utf-8")
    cfg = get_config(config_file)
    db = Path(tmp) / "handoff.db"
    t0 = at(2026, 10, 21, 10)

    first_message = ("Hi, my name is Priya Nair. My order 78231 has not arrived and I was charged twice for "
                     "Rs 4500! I paid by card 4111 1111 1111 1111 and my password is hunter2xyz")
    conversation = [
        turn("customer", first_message),
        turn("bot", "Sorry about that. I could not find a tracking update, so I have asked a human to look."),
        turn("customer", "Reach me on priya@example.com or +91 98765 43210, please email me",
             attachment={"file_id": "f1", "status": "needs_better_file", "kind": "image"}),
    ]
    result = process_unresolved(cfg, "hc1", conversation, t0, db_path=db)
    check("ticket is created and routed", (result["ticket_id"], result["status"], result["routing"]["agent"]),
          ("TKT-000001", "assigned", "agent_billing_1"))

    h = build_handoff(cfg, "TKT-000001", t0, db_path=db)
    text = h["text"]
    check("handoff ticket id and status", (h["ticket_id"], h["status"], h["priority"]), ("TKT-000001", "assigned", "medium"))
    check("customer name is kept", h["customer"]["name"], "Priya Nair")
    check("email is masked", h["customer"]["email"], "p***@example.com")
    check("phone is masked", h["customer"]["phone"], "+** ***** *3210")
    check("preferred contact is stated", (h["customer"]["preferred_contact"], h["customer"]["preferred_contact_source"]),
          ("email", "stated"))
    check("order number is kept", h["context"]["order_id"], "78231")
    check("amounts are kept", h["context"]["amounts"], ["Rs 4500"])
    check("inferred fields are labelled", h["issue"]["inferred"], ["issue_category", "severity", "impact", "sentiment"])
    check("inferred fields explain themselves", "charged twice" in h["issue"]["basis"]["severity"], True)
    check("handoff text has the ticket id", "TKT-000001" in text, True)
    check("handoff text keeps the order number", "78231" in text, True)
    check("raw email is not in the text", "priya@example.com" in text, False)
    check("masked email is in the text", "p***@example.com" in text, True)
    check("raw phone digits are not in the text", "98765" in text, False)
    check("last four phone digits are in the text", "3210" in text, True)
    check("card number is not in the text", "4111" in text, False)
    check("password is not in the text", "hunter2xyz" in text, False)
    check("handoff has a recommended action", "Recommended next action" in text, True)
    check("handoff text is already masked", mask_text(text), text)
    check("troubleshooting includes the bot reply", any("tracking update" in step for step in h["attempted_steps"]), True)
    check("troubleshooting includes the file outcome", any("needs_better_file" in step for step in h["attempted_steps"]), True)
    check("evidence keeps the attachment reference",
          any(item["type"] == "attachment" and item["file_id"] == "f1" for item in h["evidence"]), True)
    check("assignment is shown", (h["assignment"]["agent"], h["assignment"]["team"]), ("agent_billing_1", "billing"))
    check("nothing is missing", h["missing_mandatory"], [])
    check("calm ticket gets a plain recommendation", h["recommended_next_action"].startswith("Review the issue"), True)
    check("sla is reported", h["sla"]["state"], "ok")

    # duplicate conversation is linked and visible in the handoff
    repeat = [turn("customer", first_message), turn("customer", "email me at priya@example.com")]
    dup = process_unresolved(cfg, "hc2", repeat, at(2026, 10, 21, 10, 5), db_path=db)
    check("duplicate is linked, not created", (dup["action"], dup["ticket_id"]), ("linked_duplicate", "TKT-000001"))
    h = build_handoff(cfg, "TKT-000001", at(2026, 10, 21, 10, 5), db_path=db)
    check("handoff lists the duplicate conversation", h["related"]["duplicate_conversations"], ["hc2"])

    # a ticket waiting for information
    pending = process_unresolved(cfg, "hp1", [turn("customer", "Hello, my package never arrived")], t0, db_path=db)
    check("pending ticket", (pending["ticket_id"], pending["status"]), ("TKT-000002", "pending_information"))
    check("pending ticket is not routed", (pending["routing"]["agent"], pending["routing"]["code"]), (None, None))
    hp = build_handoff(cfg, "TKT-000002", t0, db_path=db)
    check("missing information is listed", hp["missing_mandatory"], ["order_id", "contact"])
    check("outstanding questions are listed", [q["field"] for q in hp["outstanding_questions"]], ["order_id", "contact"])
    check("questions count how often they were asked", [q["times_asked"] for q in hp["outstanding_questions"]], [1, 1])
    check("pending recommendation", hp["recommended_next_action"].startswith("Waiting for the customer"), True)
    check("pending ticket has no assignment", hp["assignment"]["agent"], None)

    # an escalated ticket
    process_unresolved(cfg, "hs1", [turn("customer", "My order 11111 has not arrived yet, please check"),
                                    turn("customer", "reach me at s1@x.com")], t0, db_path=db)
    breach_time = at(2026, 10, 26, 10)
    summary = run_reconcile(db_path=db, now=breach_time, config_loader=lambda: cfg)
    check("the third ticket escalates", "TKT-000003" in summary["escalations"], True)
    hs = build_handoff(cfg, "TKT-000003", breach_time, db_path=db)
    check("escalated sla state", hs["sla"]["state"], "breached")
    check("escalation history is in the handoff", {"sla_warning", "sla_breached", "escalated"} <= {e["type"] for e in hs["history"]}, True)
    check("escalated recommendation", hs["recommended_next_action"].startswith("SLA breached"), True)
    raises("unknown ticket is refused", ValueError, lambda: build_handoff(cfg, "TKT-999999", t0, db_path=db))
    raises("malformed ticket id is refused", ValueError, lambda: build_handoff(cfg, "nonsense", t0, db_path=db))

    # the log is masked and holds no conversation text
    log_event("probe", note="mail john@example.com card 4111 1111 1111 1111", ids=["TKT-000001"])
    lines = [json.loads(line) for line in log_file.read_text(encoding="utf-8").splitlines() if line.strip()]
    log_text = log_file.read_text(encoding="utf-8")
    check("every log line has a type and a timestamp", all("type" in line and "timestamp" in line for line in lines), True)
    check("tickets were logged", any(line["type"] == "ticket_processed" for line in lines), True)
    check("escalations were logged", any(line["type"] == "sla_escalation" for line in lines), True)
    check("probe email is masked in the log", "john@example.com" in log_text, False)
    check("probe card is masked in the log", "[CARD ending 1111]" in log_text, True)
    for secret in ("priya@example.com", "98765", "hunter2xyz", "4111 1111", "Priya", "Nair"):
        check(f"log does not contain {secret!r}", secret in log_text, False)

os.environ.pop("TICKET_LOG_PATH", None)
print(f"checks run: {total}, problems: {problems}")
sys.exit(1 if problems else 0)