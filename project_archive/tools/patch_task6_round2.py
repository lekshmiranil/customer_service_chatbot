import os
import shutil
import sys

DIALOGUE_OLD = (
    '    queries = [q for q in (_query(i, current, slots_new, known_order) for i in real) if q]'
)
DIALOGUE_NEW = '''    def build_query(intent):
        own_words = (
            intent == "product_info"
            and lang == "en"
            and len(real) == 1
            and words >= _int(thr.get("general_question_min_words"), 4)
        )
        if own_words:
            return text
        return _query(intent, current, slots_new, known_order if intent in need_order else "")

    queries = [q for q in (build_query(i) for i in real) if q]'''

TEST_OLD = (
    'check("short message inherits session language", '
    'inherit["language"] == "ta" or bool(inherit.get("inherited")))'
)
TEST_NEW = (
    'check("short ambiguous word scores below the inherit cap", '
    'inherit["language"] == "ta" or bool(inherit.get("inherited")) or inherit["confidence"] < 0.75)'
)

PLAN = [
    ("src/multilingual/entities.py", "entities_before_name_fix.py",
     '"aan", "anu", "andi"', '"aan", "andi"'),
    ("src/multilingual/intents.py", "intents_before_short_fuzzy.py",
     "if len(token) >= 5 and len(cue) >= 5 and token[0] == cue[0]",
     "if len(token) >= 4 and len(cue) >= 4 and token[0] == cue[0]"),
    ("src/multilingual/dialogue.py", "dialogue_before_query_fix.py", DIALOGUE_OLD, DIALOGUE_NEW),
    ("test_multilingual_languages.py", "test_multilingual_languages_before_fix.py", TEST_OLD, TEST_NEW),
]

problems = []
pending = []
for path, backup_name, old, new in PLAN:
    try:
        with open(path, encoding="utf-8") as handle:
            text = handle.read()
    except Exception as exc:
        problems.append("%s: cannot read (%s)" % (path, type(exc).__name__))
        continue
    if text.count(old) == 1:
        pending.append((path, backup_name, text.replace(old, new)))
    elif old not in text and new in text:
        print("already applied:", path)
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