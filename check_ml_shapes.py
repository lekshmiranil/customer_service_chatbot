import os
import shutil
import sys
import tempfile
import traceback

sys.stdout.reconfigure(errors="backslashreplace")

from src.multilingual import config, dialogue, entities, replies, session_store, summary

cfg = config.get_config()


def section(title, fn):
    print("==", title)
    try:
        fn()
    except Exception:
        print(traceback.format_exc())


def shapes():
    print("empty_slots:", ascii(entities.empty_slots()))
    print("empty_state:", ascii(summary.empty_state("en")))
    found = entities.extract("my name is Anu, order ORD-12345 on 12/11/2026 code AB-100", cfg)
    print("extract:", type(found).__name__, ascii(found))
    print("update_slots:", ascii(entities.update_slots(entities.empty_slots(), found)))
    print("mask:", ascii(entities.mask("order ORD-12345 please", found["items"] if isinstance(found, dict) else found)))


def store():
    tmp = tempfile.mkdtemp()
    conn = None
    try:
        conn = session_store.connect(os.path.join(tmp, "s.db"))
        now = session_store.utc_now()
        res = session_store.resolve_session(conn, "s1", "cust1", now, cfg)
        print("resolve_session:", ascii(res))
        print("get_session:", ascii(session_store.get_session(conn, "s1")))
        print("session_status:", ascii(session_store.session_status(conn, "s1", now, cfg)))
    finally:
        if conn is not None:
            conn.close()
        shutil.rmtree(tmp, ignore_errors=True)


def dialogue_run():
    msgs = [
        "hello",
        "mera order ORD-12345 kab aayega",
        "and the refund?",
        "sorry, the order number is ORD-99999",
        "ok",
        "xyz qwerty asdf",
        "\u0986\u09ae\u09be\u09b0 \u0985\u09b0\u09cd\u09a1\u09be\u09b0 \u0995\u09cb\u09a5\u09be\u09af\u09bc",
        "\u0b8e\u0ba9\u0bcd \u0b86\u0bb0\u0bcd\u0b9f\u0bb0\u0bcd \u0b8e\u0b99\u0bcd\u0b95\u0bc7",
        "cancel and refund both",
        "I want to know about the warranty of product code AB-100",
        "talk to a human agent",
    ]
    state = summary.empty_state("en")
    for number, msg in enumerate(msgs, 1):
        state, r = dialogue.handle_message(state, msg, cfg)
        print(number, ascii(msg))
        print("   kind=%s lang=%s conf=%s intents=%s reason=%s resolved=%s switched=%s"
              % (r["kind"], r["language"], r["language_confidence"], r["intents"],
                 r["reason"], r["resolved_from"], r["switched"]))
        print("   query=%s" % ascii(r["query"]))
        print("   text=%s" % ascii(r["text"])[:90])
        print("   notices=%s" % ascii(r["notices"])[:90])
    print("final state:", ascii(state))


section("shapes", shapes)
section("session store", store)
section("dialogue", dialogue_run)
print("replies count:", replies.count(), "missing:", replies.missing())