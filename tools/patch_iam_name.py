"""One-time patch: add an 'I am' / "I'm" name marker to src\\multilingual\\entities.py.
Verifies every anchor, compiles the result, backs up first, refuses to write on any mismatch."""
import os
import shutil
import sys
import time

TARGET = os.path.join("src", "multilingual", "entities.py")
BACKUPS = "backups"


def refuse(message):
    print("REFUSED: " + message + "; nothing was written")
    sys.exit(1)


DEF_OLD = "def _name_span(match, text):\n"
DEF_NEW = r'''_IAM_RE = re.compile(
    r"(?<![\w'\u2019])(?i:i\s+am|i['\u2019]m)(?![\w'\u2019])[\s:,\-]*"
    r"([A-Z][A-Za-z'\u2019.\-]*(?:\s+[A-Z][A-Za-z'\u2019.\-]*){0,2})"
)
_IAM_STOP = {
    "a", "an", "the", "not", "very", "so", "also", "just", "still", "sorry", "here", "new",
    "from", "in", "at", "waiting", "looking", "trying", "calling", "writing", "having", "facing",
    "getting", "unable", "happy", "angry", "upset", "confused", "frustrated", "disappointed", "annoyed",
}


def _name_span(match, text, extra_stop=()):
'''

COND_OLD = "        if not word or word.lower() in NAME_STOP or any(char.isdigit() for char in word):\n"
COND_NEW = (
    "        if not word or word.lower() in NAME_STOP or word.lower() in extra_stop "
    "or any(char.isdigit() for char in word):\n"
)

LOOP_OLD = (
    "    for match in _NAME_RE.finditer(text):\n"
    "        span = _name_span(match, text)\n"
    "        if span:\n"
    "            add(\"name\", span[0], span[1])\n"
)
LOOP_NEW = LOOP_OLD + (
    "    for match in _IAM_RE.finditer(text):\n"
    "        span = _name_span(match, text, _IAM_STOP)\n"
    "        if span:\n"
    "            add(\"name\", span[0], span[1])\n"
)

if not os.path.isfile(TARGET):
    refuse(TARGET + " not found; run from the project root")
with open(TARGET, "r", encoding="utf-8", newline="") as handle:
    source = handle.read()
if "_IAM_RE" in source:
    refuse("entities.py already contains _IAM_RE")
crlf = "\r\n" in source


def fit(text):
    return text.replace("\n", "\r\n") if crlf else text


edits = []
for label, old, new in (("def", DEF_OLD, DEF_NEW), ("condition", COND_OLD, COND_NEW), ("loop", LOOP_OLD, LOOP_NEW)):
    old_fit = fit(old)
    count = source.count(old_fit)
    if count != 1:
        refuse("anchor '%s' found %d times (expected 1)" % (label, count))
    edits.append((source.index(old_fit), old_fit, fit(new)))

result = source
for position, old_fit, new_fit in sorted(edits, reverse=True):
    result = result[:position] + new_fit + result[position + len(old_fit):]

try:
    compile(result, TARGET, "exec")
except SyntaxError as error:
    refuse("patched source does not compile: %s" % error)

os.makedirs(BACKUPS, exist_ok=True)
stamp = time.strftime("%Y%m%d_%H%M%S")
backup = os.path.join(BACKUPS, "entities.py.before_iam_name_" + stamp + ".bak")
shutil.copy2(TARGET, backup)
with open(TARGET, "w", encoding="utf-8", newline="") as handle:
    handle.write(result)
print("ok: patched " + TARGET)
print("ok: backup " + backup)