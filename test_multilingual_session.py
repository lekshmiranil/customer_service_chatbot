import os
import shutil
import sys
import tempfile
from datetime import timedelta

sys.stdout.reconfigure(errors="backslashreplace")

from src.multilingual import bridge, config, session_store

failures = 0


def check(label, condition):
    global failures
    if condition:
        print("ok   " + label)
    else:
        print("FAIL " + label)
        failures += 1


cfg = config.get_config()
tmp = tempfile.mkdtemp()
db = os.path.join(tmp, "s.db")
t0 = session_store.utc_now()


def turn(sid, cust, text, when):
    return bridge.handle_turn(sid, cust, text, now=when, cfg=cfg, db_path=db)


def state_of(sid):
    conn = session_store.connect(db)
    try:
        return session_store.get_session(conn, sid)
    finally:
        conn.close()


# Isolation between simultaneous customers.
a = turn("sA", "custA", "where is my order ORD-11111", t0)
b = turn("sB", "custB", "where is my order ORD-22222", t0 + timedelta(minutes=1))
check("turn a ok", a["ok"] and a["session_id"] == "sA")
check("turn b ok", b["ok"] and b["session_id"] == "sB")
slots_a = state_of("sA")["state"]["slots"]
slots_b = state_of("sB")["state"]["slots"]
check("session A holds only its order id", slots_a["order_ids"] == ["ORD-11111"])
check("session B holds only its order id", slots_b["order_ids"] == ["ORD-22222"])

# Activity inside 30 minutes keeps the session.
a2 = turn("sA", "custA", "and the refund?", t0 + timedelta(minutes=29))
check("29 minutes later still active", a2["status"] == "active" and a2["notice"] == "")
check("follow-up resolved to a refund query", a2["kind"] == "query" and "refund" in a2["intents"])

# 31 minutes of inactivity ends the session; return within 24 hours restores.
a3 = turn("sA", "custA", "hello", t0 + timedelta(minutes=60))
check("after 31 idle minutes the session is restored", a3["status"] == "restored")
check("restored notice shown", a3["notice"] == "restored" and bool(a3["notice_text"]))
check("restore notice mentions the earlier order id", "ORD-11111" in a3["notice_text"])
old = state_of("sA")
check("old session was ended", bool(old["ended_at"]) and bool(old["end_reason"]))

# Return after more than 24 hours starts a new session.
c1 = turn("sC", "custC", "where is my order ORD-33333", t0)
c2 = turn("sC", "custC", "hello", t0 + timedelta(hours=25))
check("25 hours later a new session starts", c2["status"] == "new")
check("expired notice shown", c2["notice"] == "expired_new" and bool(c2["notice_text"]))
slots_c = state_of(c2["session_id"])["state"]["slots"]
check("new session has no old order id", slots_c["order_ids"] == [])

# Return at 23 hours restores.
d1 = turn("sD", "custD", "where is my order ORD-44444", t0)
d2 = turn("sD", "custD", "hello", t0 + timedelta(hours=23))
check("23 hours later the session is restored", d2["status"] == "restored")

# No customer id: nothing to restore.
e1 = turn("sE", "", "where is my order ORD-55555", t0)
e2 = turn("sE", "", "hello", t0 + timedelta(minutes=40))
check("same session id without customer id is restored within 24 hours", e2["status"] == "restored")
e3 = turn("sF", "", "hello", t0 + timedelta(minutes=41))
check("different session id without customer id is a new session", e3["status"] == "new" and e3["notice"] == "")
check("no customer id: no data from another session", state_of(e3["session_id"])["state"]["slots"]["order_ids"] == [])

# Context kept for at least 10 messages.
texts = [
    "where is my order ORD-66666", "and the refund?", "hello", "thanks",
    "cancel my order", "mera order kab aayega", "payment failed", "delivery is late",
    "refund please", "hello", "thanks", "where is my order",
]
last = None
for number, message in enumerate(texts):
    last = turn("sL", "custL", message, t0 + timedelta(minutes=number))
conn = session_store.connect(db)
try:
    stored = session_store.count_turns(conn, "sL")
finally:
    conn.close()
check("at least 10 customer messages kept (20 turns)", stored >= 20)
check("order id still known after 12 messages",
      state_of("sL")["state"]["slots"]["order_ids"][-1:] == ["ORD-66666"])

# Sweep closes idle sessions.
bridge.sweep(now=t0 + timedelta(hours=2), cfg=cfg, db_path=db)
check("sweep ended idle session B", bool(state_of("sB")["ended_at"]))

# The bridge never raises.
bad_db = os.path.join(db, "no.db")
bridge.LAST_ERROR = ""
bad = bridge.handle_turn("sX", "", None, now=t0, cfg=cfg, db_path=bad_db)
check("bad database path returns ok False", bad["ok"] is False)
check("LAST_ERROR is set", bool(bridge.LAST_ERROR))
empty = bridge.handle_turn("sY", "custY", "", now=t0, cfg=cfg, db_path=db)
check("empty text returns a clarification", empty["ok"] and empty["clarify"])

shutil.rmtree(tmp, ignore_errors=True)
if failures:
    print(failures, "check(s) failed")
    sys.exit(1)
print("all checks passed")