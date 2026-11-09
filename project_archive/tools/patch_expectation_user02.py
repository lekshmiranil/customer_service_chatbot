"""One-time patch: corrects the user_02 expectation in eval_user_conversations.json and records it in
EXPECTATION_LOG.md as an expectation error. Refuses on any mismatch."""
import json
import os
import shutil
import sys
import time

TARGET = "eval_user_conversations.json"
LOG = "EXPECTATION_LOG.md"
OLD = '{"kind": "query", "intents": ["return_request"]}'
NEW = '{"kind": "clarify", "intents": ["return_exchange"]}'


def refuse(message):
    print("REFUSED: " + message + "; nothing was written")
    sys.exit(1)


if not os.path.isfile(TARGET):
    refuse(TARGET + " not found; run from the project root")
with open(TARGET, "r", encoding="utf-8", newline="") as handle:
    source = handle.read()
count = source.count(OLD)
if count != 1:
    refuse("anchor found %d times (expected 1)" % count)
result = source.replace(OLD, NEW)
try:
    json.loads(result)
except ValueError as error:
    refuse("patched JSON does not parse: %s" % error)

os.makedirs("backups", exist_ok=True)
backup = os.path.join("backups", TARGET + ".before_user02_" + time.strftime("%Y%m%d_%H%M%S") + ".bak")
shutil.copy2(TARGET, backup)
with open(TARGET, "w", encoding="utf-8", newline="") as handle:
    handle.write(result)

entry = """
# Expectation log (2026-11-07)

- user_02: EXPECTATION ERROR, corrected after seeing the result. Original expectation: kind query, intent
  return_request. Problems: return_request is not one of the ten intents, and the message has no order ID, so the
  layer correctly asks for it (kind clarify, intent return_exchange). Counted as an expectation error, not a pass:
  user-written 5/8 as first run, 6/8 only after this correction.
- user_04 (billing) and user_05 (device fault): real capability gaps, outside the ten intents. Not changed.
- unseen_04: OPEN. Hindi and English mixed sentence reported as en with mixed True; expected hi. Which language the
  reply should use is undecided. Expectation not changed.
- unseen_07: OPEN. 'and that one?' with one order in context resolves to that order; expected clarify. Whether that
  is acceptable is undecided. Expectation not changed.
- unseen_04 and unseen_07 were written by the assistant, not blind.
"""
with open(LOG, "a", encoding="utf-8", newline="\n") as handle:
    handle.write(entry)
print("ok: patched " + TARGET)
print("ok: backup " + backup)
print("ok: wrote " + LOG)