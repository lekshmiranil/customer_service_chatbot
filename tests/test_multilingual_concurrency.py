"""Concurrency test: 8 customers run at the same time (threads) on ONE database file. Checks that every turn
succeeds, that no customer's order ID appears in another customer's query or saved state, and that no turn is lost.
Prints ok or FAIL lines and exits 1 on any failure. No model, no quota.
Run from the project root: python test_multilingual_concurrency.py"""
import os
import shutil
import sys
import tempfile
import threading
from datetime import timedelta

from src.multilingual import bridge, config, session_store

CFG = config.get_config()
COUNT = 8
MESSAGES = ["where is my order ORD-{n}", "and the refund?", "hello", "thanks", "and the refund?",
            "where is my order"]
CHECK_QUERY = (0, 1, 4)  # message numbers whose query must contain the customer's own order ID
failures = []
lock = threading.Lock()


def check(label, ok, detail=""):
    if ok:
        print("ok  ", ascii(label))
    else:
        failures.append(label)
        print("FAIL", ascii(label), ascii(detail))


def order_of(i):
    return "ORD-%d" % (70000 + i)


tmp = tempfile.mkdtemp()
db = os.path.join(tmp, "concurrent.db")
t0 = session_store.utc_now()
barrier = threading.Barrier(COUNT)
outcome = {}


def worker(i):
    session = "conc_s%d" % i
    customer = "conc_c%d" % i
    rows = []
    try:
        barrier.wait(timeout=30)
        for number, template in enumerate(MESSAGES):
            text = template.format(n=70000 + i)
            when = t0 + timedelta(minutes=number)
            try:
                result = bridge.handle_turn(session, customer, text, now=when, cfg=CFG, db_path=db)
            except Exception as exc:
                result = {"ok": False, "error": type(exc).__name__ + ": " + str(exc)}
            if result.get("ok"):
                session = result["session_id"]
            rows.append((number, result))
    except Exception as exc:
        rows.append((-1, {"ok": False, "error": "worker: " + type(exc).__name__ + ": " + str(exc)}))
    with lock:
        outcome[i] = (session, rows)


threads = [threading.Thread(target=worker, args=(i,)) for i in range(COUNT)]
bridge.LAST_ERROR = ""
for thread in threads:
    thread.start()
for thread in threads:
    thread.join(timeout=120)

check("all workers finished", len(outcome) == COUNT, "finished %d of %d" % (len(outcome), COUNT))
for i in sorted(outcome):
    session, rows = outcome[i]
    own = order_of(i)
    others = [order_of(j) for j in range(COUNT) if j != i]
    bad = [(n, r.get("error")) for n, r in rows if not r.get("ok")]
    check("customer %d: every turn ok" % i, not bad and len(rows) == len(MESSAGES), bad)
    for n, result in rows:
        query = result.get("query") or ""
        if n in CHECK_QUERY:
            check("customer %d message %d query has own order" % (i, n), own in query, query)
        leaked = [o for o in others if o in query]
        check("customer %d message %d query has no other order" % (i, n), not leaked, leaked)
    conn = None
    try:
        conn = session_store.connect(db)
        row = session_store.get_session(conn, session) or {}
        state = row.get("state") or {}
        orders = (state.get("slots") or {}).get("order_ids") or []
        check("customer %d saved orders are only its own" % i, orders == [own], orders)
        check("customer %d saved customer id" % i, row.get("customer_id") == "conc_c%d" % i, row.get("customer_id"))
        stored = session_store.count_turns(conn, session)
        check("customer %d no turn lost (>= %d stored)" % (i, 2 * len(MESSAGES)), stored >= 2 * len(MESSAGES), stored)
    except Exception as exc:
        check("customer %d state readable" % i, False, type(exc).__name__ + ": " + str(exc))
    finally:
        if conn is not None:
            try:
                conn.close()
            except Exception:
                pass

if failures:
    print("bridge.LAST_ERROR:", ascii(bridge.LAST_ERROR))
shutil.rmtree(tmp, ignore_errors=True)
print("failures:", len(failures))
sys.exit(1 if failures else 0)

# --- At the very bottom of your test script ---

if __name__ == "__main__":
    if failures:
        print("bridge.LAST_ERROR:", ascii(bridge.LAST_ERROR))
    shutil.rmtree(tmp, ignore_errors=True)
    print("failures:", len(failures))
    sys.exit(1 if failures else 0)
