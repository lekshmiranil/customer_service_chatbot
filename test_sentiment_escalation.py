import sys

from sentiment_sim import UTC, fri, mon, new_db, outcome, run, sat, tue
from src.sentiment.bridge import check_timeouts
from src.tickets.business_time import next_business_open
from src.tickets.config import get_config

failures = 0


def check(label, condition):
    global failures
    if not condition:
        failures += 1
    print(("ok   " if condition else "FAIL ") + label)


cfg = get_config()
NEG = "This is terrible service, I am very upset"
db = new_db()

# repeated negative messages
run(db, "c1", [(mon(10, 0), "msg", NEG), (mon(10, 3), "msg", NEG)], cfg)
check("two negatives do not escalate", outcome(db, "c1")["escalations"] == [])
run(db, "c1", [(mon(10, 6), "msg", NEG)], cfg)
o = outcome(db, "c1")
check("third negative escalates", o["escalations"] == ["repeated_negative"])
row = o["rows"][0]
check("row stores a reason", bool(row["reason"]))
check("row stores the activated condition", "repeated_negative" in row["condition_code"])
check("row stores a conversation summary", "customer message" in row["summary"])
check("business hours use the live queue", row["queue"] == "priority_support")
run(db, "c1", [(mon(10, 7), "msg", NEG)], cfg)
check("repeated escalation is recorded once", outcome(db, "c1")["count"] == 1)

# a thankful message resets the count
run(db, "c2", [(mon(10, 0), "msg", NEG), (mon(10, 1), "msg", NEG), (mon(10, 2), "msg", "Thanks, it works now"),
               (mon(10, 3), "msg", NEG)], cfg)
check("a solved message resets repeated negatives", outcome(db, "c2")["escalations"] == [])

# calm high-risk messages
run(db, "c3", [(mon(10, 0), "msg", "Hello, I noticed my payment was charged twice. Could you please check?")], cfg)
o = outcome(db, "c3")
check("calm duplicate payment escalates", o["escalations"] == ["high_risk:duplicate_payment"])
run(db, "c4", [(mon(10, 0), "msg", "Good morning. Someone else has logged into my account without my permission.")], cfg)
check("calm account compromise escalates", outcome(db, "c4")["escalations"] == ["high_risk:account_compromise"])
run(db, "c5", [(mon(10, 0), "msg", "I will be consulting a lawyer regarding this matter.")], cfg)
check("calm legal threat escalates", outcome(db, "c5")["escalations"] == ["high_risk:legal_threat"])
run(db, "c6", [(mon(10, 0), "msg", "Calm note: charged twice, write to test.user@example.com")], cfg)
check("summary hides the full email address", "test.user@example.com" not in outcome(db, "c6")["rows"][0]["summary"])

# 15-minute rule with simulated time
run(db, "t1", [(mon(10, 0), "msg", NEG), (mon(10, 14), "tick", "")], cfg)
check("no escalation before 15 minutes", outcome(db, "t1")["escalations"] == [])
run(db, "t1", [(mon(10, 15), "tick", "")], cfg)
check("no escalation at exactly 15 minutes", outcome(db, "t1")["escalations"] == [])
run(db, "t1", [(mon(10, 16), "tick", "")], cfg)
o = outcome(db, "t1")
check("escalation after more than 15 minutes", o["escalations"] == ["unresolved_timeout"])
check("timeout row has reason and condition", bool(o["rows"][0]["reason"]) and "observed" in o["rows"][0]["condition_code"])
run(db, "t1", [(mon(10, 40), "tick", ""), (mon(12, 0), "tick", "")], cfg)
check("timeout escalates once", outcome(db, "t1")["count"] == 1)
check("background rows start unnotified", o["rows"][0]["notified"] == 0)

run(db, "t2", [(mon(10, 0), "msg", NEG), (mon(10, 5), "human", ""), (mon(10, 40), "tick", "")], cfg)
check("a human reply stops the clock", outcome(db, "t2")["escalations"] == [])
run(db, "t3", [(mon(10, 0), "msg", NEG), (mon(10, 5), "msg", "Thanks, it works now"), (mon(10, 40), "tick", "")], cfg)
check("a solved message stops the clock", outcome(db, "t3")["escalations"] == [])
run(db, "t4", [(mon(10, 0), "msg", "Where can I find my invoice?"), (mon(11, 0), "tick", "")], cfg)
check("a neutral conversation never times out", outcome(db, "t4")["count"] == 0)

# after-hours handling
URGENT_NEG = "This is urgent, my order is delayed and I am very upset"
PLAIN_NEG = "I am disappointed with the packaging of my order"
run(db, "a1", [(tue(20, 0), "msg", URGENT_NEG)], cfg)
check("urgent complaint after hours enters the on-call queue", outcome(db, "a1")["queues"] == ["on_call"])
run(db, "a2", [(tue(20, 0), "msg", PLAIN_NEG)], cfg)
o = outcome(db, "a2")
check("normal complaint after hours waits for the next working day", o["queues"] == ["next_working_day"])
expected = next_business_open(cfg, tue(20, 0)).astimezone(UTC).isoformat(timespec="seconds")
check("scheduled for the next business opening", o["rows"][0]["scheduled_for"] == expected)
run(db, "a3", [(sat(11, 0), "msg", PLAIN_NEG)], cfg)
check("weekend complaint waits for the next working day", outcome(db, "a3")["queues"] == ["next_working_day"])
run(db, "a4", [(tue(20, 0), "msg", "Where can I find my invoice?")], cfg)
check("a plain question after hours creates nothing", outcome(db, "a4")["count"] == 0)
run(db, "a5", [(mon(10, 0), "msg", PLAIN_NEG)], cfg)
check("a complaint in business hours creates no queue entry", outcome(db, "a5")["count"] == 0)
run(db, "a6", [(tue(20, 0), "msg", PLAIN_NEG), (tue(20, 5), "msg", URGENT_NEG)], cfg)
check("a normal complaint that becomes urgent also enters on-call", outcome(db, "a6")["queues"] == ["next_working_day", "on_call"])
run(db, "a7", [(tue(20, 0), "msg", "I noticed a duplicate payment on my card.")], cfg)
o = outcome(db, "a7")
check("calm high-risk after hours escalates to on-call", o["escalations"] == ["high_risk:duplicate_payment"] and o["queues"] == ["on_call"])
check("queue entry keeps reason and summary", all(r["reason"] and r["summary"] for r in outcome(db, "a1")["rows"]))

# time change across closing
run(db, "f1", [(fri(17, 50), "msg", NEG), (fri(18, 10), "tick", "")], cfg)
o = outcome(db, "f1")
check("timeout after closing is scheduled for the next working day", o["escalations"] == ["unresolved_timeout"] and o["queues"] == ["next_working_day"])
run(db, "f2", [(fri(17, 50), "msg", "This is terrible and urgent, please fix it immediately"), (fri(18, 10), "tick", "")], cfg)
check("urgent timeout after closing goes on-call", outcome(db, "f2")["queues"] == ["on_call"])
run(db, "f3", [(mon(10, 0), "msg", NEG), (mon(10, 8), "msg", NEG), (mon(10, 16), "msg", NEG)], cfg)
check("repeated and timeout conditions can both fire", outcome(db, "f3")["escalations"] == ["repeated_negative", "unresolved_timeout"])
check("check_timeouts returns new rows only", check_timeouts(now=mon(12, 0), cfg=cfg, db_path=db, only="f3") == [])

print("failures:", failures)
sys.exit(1 if failures else 0)