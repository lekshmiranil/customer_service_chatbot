import os
import shutil
import sys

path = os.path.join("src", "multilingual", "dialogue.py")
backup = os.path.join("backups", "dialogue_before_tail_fix.py")

with open(path, encoding="utf-8") as handle:
    text = handle.read()

END_ANCHOR = '            result["query"] = text'
SHORT_ANCHOR = '    short = words <= _int(thr.get("followup_max_words"), 5)\n'
LANG_ANCHOR = (
    '    elif conf >= _float(thr.get("language_confidence"), 0.6):\n'
    '        lang = det_lang\n'
)

TAIL = '''
            result["queries"] = [text]
            return finish(result, pending=[], intents_done=[], overflow=[])
        else:
            return ask_intent("low_intent_confidence" if requests else "no_intent")

    overflow = real[max_requests:]
    real = real[:max_requests]
    if overflow:
        notices.append(replies.render("too_many", lang, count=max_requests))

    if any(i in need_order for i in real) and not known_order:
        result = make("clarify")
        result["reason"] = "missing_order_id"
        result["intents"] = list(real)
        result["text"] = replies.render("ask_order_id", lang)
        return finish(result, pending=real, awaiting_value="order_id", overflow=overflow)

    queries = [q for q in (_query(i, current, slots_new, known_order) for i in real) if q]
    if not queries:
        return ask_intent("no_query")

    result = make("query")
    result["intents"] = list(real)
    result["queries"] = queries
    result["query"] = " ".join(queries)
    result["resolved_from"] = resolved_from
    result["text"] = " ".join(x for x in (replies.lead_line(i, lang) for i in real) if x)
    return finish(result, pending=[], intents_done=real, overflow=overflow)
'''

INHERIT = (
    '    elif session_lang and short and det_lang != session_lang\n'
    '            and conf < inherit_cap and not det.get("mixed")):\n'
)

problems = []
done = []

if "inherit_cap" not in text:
    if text.count(SHORT_ANCHOR) != 1:
        problems.append("short-words line not found exactly once")
    if text.count(LANG_ANCHOR) != 1:
        problems.append("language-confidence line not found exactly once")
    if not problems:
        text = text.replace(
            SHORT_ANCHOR,
            SHORT_ANCHOR + '    inherit_cap = _float(thr.get("inherit_confidence"), 0.75)\n',
        )
        text = text.replace(
            LANG_ANCHOR,
            '    elif (session_lang and short and det_lang != session_lang\n'
            '            and conf < inherit_cap and not det.get("mixed")):\n'
            '        lang = session_lang\n'
            '        inherited = True\n' + LANG_ANCHOR,
        )
        done.append("language inheritance")
else:
    print("inheritance patch already present")

if "overflow = real[max_requests:]" not in text:
    stripped = text.rstrip()
    if not stripped.endswith(END_ANCHOR):
        problems.append("file does not end at the expected line: " + ascii(stripped[-80:]))
    else:
        text = stripped + "\n" + TAIL.lstrip("\n") if False else stripped + TAIL
        done.append("restored tail")
else:
    print("tail already present")

if problems:
    print("nothing written:")
    for item in problems:
        print(" -", item)
    sys.exit(1)

try:
    compile(text, path, "exec")
except SyntaxError as exc:
    print("nothing written, syntax error:", exc)
    sys.exit(1)

if not done:
    print("nothing to do")
    sys.exit(0)

shutil.copyfile(path, backup)
with open(path, "w", encoding="utf-8", newline="\n") as handle:
    handle.write(text)
print("written:", ", ".join(done), "| backup:", backup)