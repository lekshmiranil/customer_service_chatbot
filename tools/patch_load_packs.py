"""One-time patch for src\\multilingual\\dialogue.py: load language packs at import, after the reply texts are merged.
Verifies the anchor, compiles, backs up first, refuses to write on any mismatch."""
import os
import shutil
import sys
import time

TARGET = os.path.join("src", "multilingual", "dialogue.py")


def refuse(message):
    print("REFUSED: " + message + "; nothing was written")
    sys.exit(1)


OLD = "for _key, _table in _EXTRA.items():\n    replies.TEXT.setdefault(_key, _table)\n"
NEW = OLD + "\nfrom src.multilingual import packs as _packs  # noqa: E402\n\n_packs.load_packs()\n"

if not os.path.isfile(TARGET):
    refuse(TARGET + " not found; run from the project root")
with open(TARGET, "r", encoding="utf-8", newline="") as handle:
    source = handle.read()
if "_packs.load_packs()" in source:
    refuse("dialogue.py already loads the packs")
crlf = "\r\n" in source
old_fit = OLD.replace("\n", "\r\n") if crlf else OLD
new_fit = NEW.replace("\n", "\r\n") if crlf else NEW
count = source.count(old_fit)
if count != 1:
    refuse("anchor found %d times (expected 1)" % count)
result = source.replace(old_fit, new_fit)
try:
    compile(result, TARGET, "exec")
except SyntaxError as error:
    refuse("patched source does not compile: %s" % error)

os.makedirs("backups", exist_ok=True)
backup = os.path.join("backups", "dialogue.py.before_load_packs_" + time.strftime("%Y%m%d_%H%M%S") + ".bak")
shutil.copy2(TARGET, backup)
with open(TARGET, "w", encoding="utf-8", newline="") as handle:
    handle.write(result)
print("ok: patched " + TARGET)
print("ok: backup " + backup)