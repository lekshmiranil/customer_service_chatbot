import os
import shutil
import sys

path = os.path.join("src", "multilingual", "dialogue.py")
backup = os.path.join("backups", "dialogue_before_tail_fix.py")

with open(path, encoding="utf-8") as handle:
    text = handle.read()

if "overflow = real[max_requests:]" in text:
    print("tail already present, nothing changed")
    sys.exit(0)

stripped = text.rstrip()
if not stripped.endswith('resolved_from = "pending"'):
    print("unexpected end of file, nothing changed:", ascii(stripped[-100:]))
    sys.exit(1)

TAIL = '''    else:
        if pending and (has_entity or analysis.get("yes") or short):
            real = list(pending)
            resolved_from = "pending"
        elif last and short and (analysis.get("followup") or has_entity):
            if len(last) > 1:
                return ask_between(last[0], last[1], "ambiguous_followup")
            real = list(last)
            resolved_from = "followup"
        elif lang == "en" and words >= _int(thr.get("general_question_min_words"), 4) and not requests:
            result = make("query")
            result["reason"] = "general_question"
            result["query"] = text
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

shutil.copyfile(path, backup)
with open(path, "w", encoding="utf-8", newline="\n") as handle:
    handle.write(stripped + "\n" + TAIL)
print("tail restored, backup saved to", backup)