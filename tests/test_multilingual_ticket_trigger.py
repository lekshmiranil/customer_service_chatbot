"""Checks the ticket reason for answers produced by the multilingual layer. No model, no quota."""
import os
import sys
import tempfile

from src.multilingual import bridge
from src.tickets.chat_bridge import text_trigger

FAILED = 0


def check(label, condition, detail=""):
    global FAILED
    if condition:
        print("ok  ", ascii(label))
    else:
        FAILED += 1
        print("FAIL", ascii(label), ascii(detail))


HANDOFF = {"kind": "answer", "escalated": True, "ml": {"kind": "handoff"}}
HINDI_QUESTION = "mujhe insaan se baat karni hai"
check("handoff in Hindi gives customer_unresolved", text_trigger(HANDOFF, HINDI_QUESTION) == "customer_unresolved")
check("escalated answer without ml keeps low_confidence",
      text_trigger({"kind": "answer", "escalated": True}, "where is my order") == "low_confidence")
check("escalated answer from a query keeps low_confidence",
      text_trigger({"kind": "answer", "escalated": True, "ml": {"kind": "query"}}, "where is my order") == "low_confidence")
check("clarify answer raises no ticket",
      text_trigger({"kind": "answer", "escalated": False, "ml": {"kind": "clarify"}}, HINDI_QUESTION) is None)
check("English request for a person still customer_unresolved",
      text_trigger({"kind": "answer", "escalated": False}, "I want to talk to a human agent") == "customer_unresolved")
check("blocked raises no ticket", text_trigger({"kind": "blocked"}, "I want to talk to a human agent") is None)
check("error gives answer_error", text_trigger({"kind": "error"}, "where is my order") == "answer_error")

with tempfile.TemporaryDirectory() as folder:
    db = os.path.join(folder, "trigger_test.db")
    question = "I want to talk to a human agent"
    layer = bridge.handle_turn("", "", text=question, db_path=db)
    check("layer handoff ok", layer.get("ok") is True and layer.get("kind") == "handoff", layer.get("kind"))
    answer = {"kind": "answer", "escalated": bool(layer.get("escalated")), "ml": {"kind": layer.get("kind")}}
    check("layer handoff gives a ticket reason", text_trigger(answer, question) == "customer_unresolved")
    # Probe, not a check: which of these phrases does the layer treat as a request for a person?
    for phrase in (HINDI_QUESTION, "mujhe agent se baat karni hai", "enikku oru manushyanodu samsarikkanam"):
        probe = bridge.handle_turn("", "", text=phrase, db_path=db)
        print("probe", ascii(phrase), "->", probe.get("kind"), ascii(probe.get("intents")))

sys.exit(1 if FAILED else 0)