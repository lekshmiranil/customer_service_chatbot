"""Tests the repeated-unclear safety net. Language is forced to English so that only the counter is tested.
No model, no quota."""
import os
import sys
import tempfile

from src.multilingual import bridge, config, dialogue, summary
from src.tickets.chat_bridge import text_trigger

FAILED = 0


def check(label, condition, detail=""):
    global FAILED
    if condition:
        print("ok  ", ascii(label))
    else:
        FAILED += 1
        print("FAIL", ascii(label), ascii(detail))


CFG = config.get_config()
UNCLEAR = "xyz qwerty asdf"
OTHER = "qwerty xyz"


def run(messages):
    state = summary.empty_state("en")
    results = []
    for text in messages:
        state, result = dialogue.handle_message(state, text, CFG, "en")
        results.append(result)
    return state, results


def brief(result):
    return result.get("kind"), result.get("reason")


state, out = run(["hello", UNCLEAR])
check("first unclear message asks for clarification", brief(out[1])[0] == "clarify", brief(out[1]))
check("first unclear message is counted", state.get("unclear_count") == 1, state.get("unclear_count"))

state, out = run(["hello", UNCLEAR, OTHER])
check("second unclear message in a row hands off", brief(out[2])[0] == "handoff", brief(out[2]))
check("handoff reason is repeated_unclear", out[2].get("reason") == "repeated_unclear", out[2].get("reason"))
check("handoff is escalated with the human_agent intent",
      out[2].get("escalated") is True and out[2].get("intents") == ["human_agent"], out[2].get("intents"))
check("handoff has reply text", bool(out[2].get("text")))
check("count is reset after the handoff", state.get("unclear_count") == 0, state.get("unclear_count"))

state, out = run(["hello", UNCLEAR, OTHER, UNCLEAR])
check("after a handoff the count starts again", brief(out[3])[0] == "clarify", brief(out[3]))

state, out = run(["hello", UNCLEAR, "where is my order ORD-31337", UNCLEAR])
check("a recognised request resets the count", brief(out[2])[0] == "query" and brief(out[3])[0] == "clarify",
      [brief(r) for r in out])

state, out = run(["hello", UNCLEAR, "hello", UNCLEAR])
check("a greeting resets the count", brief(out[3])[0] == "clarify", brief(out[3]))

state, out = run(["hello", UNCLEAR, "where is my order", UNCLEAR])
check("a missing order id question resets the count", brief(out[3])[0] == "clarify", [brief(r) for r in out])

state, out = run(["I want to talk to a human agent"])
check("a direct request still hands off with its own reason",
      brief(out[0])[0] == "handoff" and out[0].get("reason") != "repeated_unclear", brief(out[0]))

with tempfile.TemporaryDirectory() as folder:
    db = os.path.join(folder, "net_test.db")
    session = ""
    last = None
    seen = []
    for text in ("hello", UNCLEAR, OTHER):
        last = bridge.handle_turn(session, "", text=text, db_path=db, force_language="en")
        session = last.get("session_id", session)
        seen.append(last.get("kind"))
    check("bridge: clarify then handoff", seen == ["social", "clarify", "handoff"], seen)
    answer = {"kind": "answer", "escalated": bool(last.get("escalated")), "ml": {"kind": last.get("kind")}}
    check("bridge: the handoff raises a ticket with customer_unresolved",
          text_trigger(answer, OTHER) == "customer_unresolved", text_trigger(answer, OTHER))

sys.exit(1 if FAILED else 0)