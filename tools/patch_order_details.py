"""One-time patch for src\\multilingual\\lexicon_cues.py: order-details phrases for order_status, and the bare word
'details' removed from the English product_info words. Verifies anchors, compiles, backs up first."""
import os
import shutil
import sys
import time

TARGET = os.path.join("src", "multilingual", "lexicon_cues.py")


def refuse(message):
    print("REFUSED: " + message + "; nothing was written")
    sys.exit(1)


EDITS = (
    ('"when will it come")',
     '"when will it come", "about my order", "order details", "order info", "order information",\n'
     '                  "details of my order")'),
    ('duration syllabus details"', 'duration syllabus"'),
)

if not os.path.isfile(TARGET):
    refuse(TARGET + " not found; run from the project root")
with open(TARGET, "r", encoding="utf-8", newline="") as handle:
    source = handle.read()
if '"order details"' in source:
    refuse("lexicon_cues.py already contains the order-details cues")
newline = "\r\n" if "\r\n" in source else "\n"
result = source
for old, new in EDITS:
    count = result.count(old)
    if count != 1:
        refuse("anchor %s found %d times (expected 1)" % (ascii(old), count))
    result = result.replace(old, new.replace("\n", newline))
try:
    compile(result, TARGET, "exec")
except SyntaxError as error:
    refuse("patched source does not compile: %s" % error)

os.makedirs("backups", exist_ok=True)
backup = os.path.join("backups", "lexicon_cues.py.before_order_details_" + time.strftime("%Y%m%d_%H%M%S") + ".bak")
shutil.copy2(TARGET, backup)
with open(TARGET, "w", encoding="utf-8", newline="") as handle:
    handle.write(result)
print("ok: patched " + TARGET)
print("ok: backup " + backup)