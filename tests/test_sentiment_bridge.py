import os
import sys
import tempfile
import time

from sentiment_sim import UTC, mon, new_db
from src.sentiment import bridge
from src.tickets.chat_bridge import customer_turn, submit_to_tickets
from src.tickets.config import get_config

failures = 0


def check(label, condition):
    global failures
    if not condition:
        failures += 1
    print(("ok   " if condition else "FAIL ") + label)


cfg = get_config()
db = new_db()

r = bridge.analyze_and_decide("b1", "This is terrible service, I am very upset", now=mon(10, 0), cfg=cfg, db_path=db)
check("negative message gets an opening line", bool(r["opening"]) and r["negative_type"] and r["error"] is None)
check("result carries scores and confidence", bool(r["scores"]) and r["confidence"] > 0)
r = bridge.analyze_and_decide("b2", "Where can I find my invoice?", now=mon(10, 0), cfg=cfg, db_path=db)
check("neutral message gets no opening line", r["opening"] == "" and not r["escalated"])
r = bridge.analyze_and_decide("b3", "मेरा अकाउंट हैक हो गया है", now=mon(10, 0), cfg=cfg, db_path=db)
check("hindi high-risk message escalates", r["escalated"] and r["risks"] == ["account_compromise"])
check("hindi message gets a hindi notice", r["language"] == "hi" and any("\u0900" <= c <= "\u097f" for c in r["notice"]))

# never raises
r = bridge.analyze_and_decide("b4", None, now=mon(10, 0), cfg=cfg, db_path=db)
check("None text is handled", r["error"] is None and r["label"] == "neutral")
r = bridge.analyze_and_decide("b5", "hello", now=mon(10, 0).replace(tzinfo=None), cfg=cfg, db_path=db)
check("naive time is treated as UTC", r["error"] is None)
r = bridge.analyze_and_decide("b6", "hello", now=mon(10, 0), cfg=cfg, db_path=os.path.dirname(db))
check("a broken database returns a safe result", bool(r["error"]) and not r["escalated"] and r["rows"] == [])
check("the error is noted", bridge.LAST_ERROR["value"] is not None)
bridge.LAST_ERROR["value"] = None

# SENTIMENT_NOW override
os.environ["SENTIMENT_NOW"] = "2026-10-27T14:30:00+00:00"
bridge.analyze_and_decide("b7", "I noticed a duplicate payment on my card.", cfg=cfg, db_path=db)
os.environ.pop("SENTIMENT_NOW", None)
rows = bridge.list_rows("b7", db_path=db)
check("SENTIMENT_NOW sets the clock", bool(rows) and rows[0]["created_at"].startswith("2026-10-27T14:30:00"))

# background rows are claimed once
bridge.analyze_and_decide("b8", "This is terrible service, I am very upset", now=mon(10, 0), cfg=cfg, db_path=db)
claimed = bridge.claim_unnotified("b8", now=mon(10, 30), cfg=cfg, db_path=db)
check("a timeout is claimed with a notice", len(claimed) == 1 and bool(claimed[0]["notice"]))
check("a claimed row is not returned twice", bridge.claim_unnotified("b8", now=mon(10, 31), cfg=cfg, db_path=db) == [])
check("set_ticket links the row", bridge.set_ticket(claimed[0]["id"], "TKT-000001", db_path=db)
      and bridge.list_rows("b8", db_path=db)[0]["ticket_id"] == "TKT-000001")

# the background checker
bridge.analyze_and_decide("b9", "This is terrible service, I am very upset", now=mon(10, 0), cfg=cfg, db_path=db)
started = bridge.start_timeout_checker(interval_seconds=0.2, clock=lambda: mon(10, 30), db_path=db)
time.sleep(1.5)
stopped = bridge.stop_timeout_checker()
check("the background checker starts and stops", started is True and stopped is True)
check("the background checker records the timeout", [r["code"] for r in bridge.list_rows("b9", db_path=db)] == ["unresolved_timeout"])

# a Task 3 ticket accepts the new trigger (temporary ticket database only)
ticket_db = os.path.join(tempfile.mkdtemp(), "tickets_test.db")
turns = [customer_turn("My payment was charged twice, please help me with this order.", now=mon(10, 0))]
result = submit_to_tickets("web-sentiment-test", turns, "sentiment_escalation", now=mon(10, 0), cfg=cfg, db_path=ticket_db)
check("a ticket accepts the sentiment_escalation trigger", "error" not in result)
print("last error:", bridge.LAST_ERROR["value"])

print("failures:", failures)
sys.exit(1 if failures else 0)