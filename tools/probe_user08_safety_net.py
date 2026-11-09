"""Probe, not a test: sends the user_08 text twice through the bridge and prints only kinds and reasons.
The text itself is not printed. No model, no quota."""
import json
import os
import sys
import tempfile

from src.multilingual import bridge
from src.tickets.chat_bridge import text_trigger

with open("eval_user_conversations.json", "r", encoding="utf-8") as handle:
    data = json.load(handle)
text = ""
for conversation in data.get("conversations", []):
    if conversation.get("id") == "user_08":
        text = conversation["turns"][0]["text"]
if not text:
    print("FAIL user_08 not found")
    sys.exit(1)

with tempfile.TemporaryDirectory() as folder:
    db = os.path.join(folder, "probe.db")
    session = ""
    for number in (1, 2):
        out = bridge.handle_turn(session, "", text=text, db_path=db)
        session = out.get("session_id", session)
        inner = out.get("result") or {}
        answer = {"kind": "answer", "escalated": bool(out.get("escalated")), "ml": {"kind": out.get("kind")}}
        print("turn", number, "| kind", out.get("kind"), "| reason", ascii(inner.get("reason")),
              "| language", out.get("language"), "| languages", inner.get("languages"),
              "| confidence", inner.get("language_confidence"), "| intents", out.get("intents"),
              "| ticket reason", text_trigger(answer, text))