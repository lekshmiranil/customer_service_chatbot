import os
import shutil
import sys

INTENTS_OLD = "        ratio = difflib.SequenceMatcher(None, token, cue).ratio()\n"
INTENTS_NEW = (
    "        if min(len(token), len(cue)) == 4:\n"
    "            letters = iter(cue)\n"
    "            if not (len(token) < len(cue) and all(char in letters for char in token)):\n"
    "                return 0.0\n"
) + INTENTS_OLD

SESSION_OLD = 'check("no customer id gives a new session", e2["status"] == "new")'
SESSION_NEW = (
    'check("same session id without customer id is restored within 24 hours", e2["status"] == "restored")\n'
    'e3 = turn("sF", "", "hello", t0 + timedelta(minutes=41))\n'
    'check("different session id without customer id is a new session", '
    'e3["status"] == "new" and e3["notice"] == "")\n'
    'check("no customer id: no data from another session", '
    'state_of(e3["session_id"])["state"]["slots"]["order_ids"] == [])'
)

EXTRA_OLD = '["nice weather today friend", "i like the blue color", "the old cart is here", "please send more later"]'
EXTRA_NEW = (
    '["nice weather today friend", "i like the blue color", "the old cart is here", '
    '"please send more later", "see you later", "the later one is fine"]'
)

PLAN = [
    ("src/multilingual/intents.py", "intents_before_round3.py", INTENTS_OLD, INTENTS_NEW, "letters = iter(cue)"),
    ("test_multilingual_session.py", "test_session_before_round3.py", SESSION_OLD, SESSION_NEW,
     "same session id without customer id"),
    ("test_multilingual_extra.py", "test_extra_before_round3.py", EXTRA_OLD, EXTRA_NEW, '"see you later"'),
]

problems = []
pending = []
for path, backup_name, old, new, marker in PLAN:
    try:
        with open(path, encoding="utf-8") as handle:
            text = handle.read()
    except Exception as exc:
        problems.append("%s: cannot read (%s)" % (path, type(exc).__name__))
        continue
    if marker in text:
        print("already applied:", path)
    elif text.count(old) == 1:
        pending.append((path, backup_name, text.replace(old, new)))
    else:
        problems.append("%s: anchor found %d times" % (path, text.count(old)))

for path, backup_name, text in pending:
    try:
        compile(text, path, "exec")
    except SyntaxError as exc:
        problems.append("%s: would not compile (%s)" % (path, exc))

if problems:
    print("nothing written:")
    for item in problems:
        print(" -", item)
    sys.exit(1)

for path, backup_name, text in pending:
    shutil.copyfile(path, os.path.join("backups", backup_name))
    with open(path, "w", encoding="utf-8", newline="\n") as handle:
        handle.write(text)
    print("patched:", path, "| backup: backups\\" + backup_name)
if not pending:
    print("nothing to do")