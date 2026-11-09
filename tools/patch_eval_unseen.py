"""One-time patch: add eval_unseen_conversations.json as a third, separate score in eval_multilingual_run.py.
Verifies every anchor, compiles the result and writes nothing if any check fails.
Run from the project root: python -m tools.patch_eval_unseen"""
import os
import shutil
import sys
import time

TARGET = "eval_multilingual_run.py"
STAMP = time.strftime("%Y%m%d_%H%M%S")


def refuse(message):
    print("REFUSED:", message)
    print("Nothing was written.")
    sys.exit(1)


def once(text, old, new, label):
    count = text.count(old)
    if count != 1:
        refuse("%s: anchor found %d times, expected 1" % (label, count))
    return text.replace(old, new)


if not os.path.isfile(TARGET):
    refuse("missing file " + TARGET)
with open(TARGET, "r", encoding="utf-8", newline="") as handle:
    raw = handle.read()
crlf = "\r\n" in raw
text = raw.replace("\r\n", "\n")
if "UNSEEN_FILE" in text:
    refuse("the runner already has UNSEEN_FILE; the patch looks applied")

text = once(
    text,
    'USER_FILE = "eval_user_conversations.json"\n',
    'USER_FILE = "eval_user_conversations.json"\nUNSEEN_FILE = "eval_unseen_conversations.json"\n',
    "USER_FILE line",
)

LOAD_UNSEEN = '''def load_unseen():
    if not os.path.exists(UNSEEN_FILE):
        return None, UNSEEN_FILE + " not found"
    try:
        with open(UNSEEN_FILE, encoding="utf-8") as handle:
            data = json.load(handle)
    except Exception as exc:
        return None, "could not read: %s: %s" % (type(exc).__name__, exc)
    if isinstance(data, dict):
        data = data.get("conversations")
    if not isinstance(data, list):
        return None, "expected a list of conversations"
    good = []
    for number, conv in enumerate(data, 1):
        if isinstance(conv, dict) and isinstance(conv.get("turns"), list) and conv["turns"]:
            conv.setdefault("id", "unseen_%02d" % number)
            good.append(conv)
    return good, "%d of %d conversations usable" % (len(good), len(data))


def score(results):
'''
text = once(text, "def score(results):\n", LOAD_UNSEEN, "def score")

text = once(
    text,
    "    user = [run_conversation(conv, cfg, base) for conv in user_convs] if user_convs else None\n",
    "    user = [run_conversation(conv, cfg, base) for conv in user_convs] if user_convs else None\n"
    "    unseen_convs, unseen_note = load_unseen()\n"
    "    unseen = [run_conversation(conv, cfg, base) for conv in unseen_convs] if unseen_convs else None\n",
    "main user run",
)

text = once(
    text,
    '    lines += ["", "User file: " + user_note, "",\n',
    '    if unseen is not None:\n'
    '        sp, st, stp, stt = score(unseen)\n'
    '        lines.append("| Assistant-written unseen set (written after the code, NOT blind) | %d/%d | %d/%d |" % (sp, st, stp, stt))\n'
    '    else:\n'
    '        lines.append("| Assistant-written unseen set | not run | not run |")\n'
    '    lines += ["", "User file: " + user_note, "",\n',
    "main score table",
)

text = once(
    text,
    '    if user is not None:\n'
    '        lines += ["## User-written conversations", ""]\n'
    '        lines += describe(user)\n',
    '    if user is not None:\n'
    '        lines += ["## User-written conversations", ""]\n'
    '        lines += describe(user)\n'
    '    if unseen is not None:\n'
    '        lines += ["## Assistant-written unseen set (NOT blind; " + unseen_note + ")", ""]\n'
    '        lines += describe(unseen)\n',
    "main describe",
)

text = once(
    text,
    '    for label, results in (("assistant-written", built), ("user-written", user or [])):\n',
    '    for label, results in (("assistant-written", built), ("user-written", user or []),\n'
    '                           ("unseen-set", unseen or [])):\n',
    "print loop",
)

text = once(
    text,
    '    print("report written to", OUT_FILE)\n',
    '    if unseen is not None:\n'
    '        print("unseen-set: %d/%d conversations, %d/%d turn checks" % (sp, st, stp, stt))\n'
    '    else:\n'
    '        print("unseen-set: not run (" + unseen_note + ")")\n'
    '    print("report written to", OUT_FILE)\n',
    "final print",
)

try:
    compile(text, TARGET, "exec")
except SyntaxError as error:
    refuse("the result would not compile: %s" % error)

os.makedirs("backups", exist_ok=True)
shutil.copy2(TARGET, os.path.join("backups", TARGET + ".before_unseen_" + STAMP + ".bak"))
if crlf:
    text = text.replace("\n", "\r\n")
with open(TARGET, "w", encoding="utf-8", newline="") as handle:
    handle.write(text)
print("patched", TARGET, "(backup in backups\\)")