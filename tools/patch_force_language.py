"""One-time patch for src\\multilingual\\dialogue.py: a force_language that is not in the configured language list
is ignored. Verifies the anchor, compiles, backs up first, refuses to write on any mismatch."""
import os
import re
import shutil
import sys
import time

TARGET = os.path.join("src", "multilingual", "dialogue.py")


def refuse(message):
    print("REFUSED: " + message + "; nothing was written")
    sys.exit(1)


if not os.path.isfile(TARGET):
    refuse(TARGET + " not found; run from the project root")
with open(TARGET, "r", encoding="utf-8", newline="") as handle:
    source = handle.read()
if "force_language not in languages.supported_languages" in source:
    refuse("dialogue.py already contains the check")

pattern = re.compile(r"^([ \t]*)return _handle\(state, text, cfg, force_language\)[ \t]*(\r?\n)", re.MULTILINE)
matches = list(pattern.finditer(source))
if len(matches) != 1:
    refuse("anchor 'return _handle(...)' found %d times (expected 1)" % len(matches))
match = matches[0]
indent, newline = match.group(1), match.group(2)
added = (
    indent + "if force_language and force_language not in languages.supported_languages(cfg):" + newline
    + indent + "    force_language = \"\"" + newline
)
result = source[:match.start()] + added + source[match.start():]

try:
    compile(result, TARGET, "exec")
except SyntaxError as error:
    refuse("patched source does not compile: %s" % error)

os.makedirs("backups", exist_ok=True)
backup = os.path.join("backups", "dialogue.py.before_force_language_" + time.strftime("%Y%m%d_%H%M%S") + ".bak")
shutil.copy2(TARGET, backup)
with open(TARGET, "w", encoding="utf-8", newline="") as handle:
    handle.write(result)
print("ok: patched " + TARGET)
print("ok: backup " + backup)