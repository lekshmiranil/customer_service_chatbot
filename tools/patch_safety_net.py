"""Adds the repeated-unclear safety net to src\\multilingual\\dialogue.py. Verifies both anchors occur exactly once,
compiles the result and writes nothing on any mismatch."""
import sys

PATH = "src/multilingual/dialogue.py"

FINISH_OLD = (
    "    def finish(result, pending=None, awaiting_value=\"\", intents_done=None, overflow=None):\n"
    "        state[\"slots\"] = slots_new\n"
)
FINISH_NEW = (
    "    def finish(result, pending=None, awaiting_value=\"\", intents_done=None, overflow=None, unclear=False):\n"
    "        state[\"unclear_count\"] = _int(state.get(\"unclear_count\")) + 1 if unclear else 0\n"
    "        state[\"slots\"] = slots_new\n"
)
ASK_OLD = (
    "    def ask_intent(reason):\n"
    "        result = make(\"clarify\")\n"
    "        result[\"reason\"] = reason\n"
    "        result[\"text\"] = replies.render(\"clarify_intent\", lang)\n"
    "        return finish(result, awaiting_value=\"intent\")\n"
)
ASK_NEW = (
    "    def ask_intent(reason):\n"
    "        limit = max(2, _int(thr.get(\"unclear_before_handoff\"), 2))\n"
    "        if _int(state.get(\"unclear_count\")) + 1 >= limit:\n"
    "            result = make(\"handoff\")\n"
    "            result[\"intents\"] = [\"human_agent\"]\n"
    "            result[\"escalated\"] = True\n"
    "            result[\"reason\"] = \"repeated_unclear\"\n"
    "            result[\"query\"] = str(lexicon.CANONICAL_QUERY.get(\"human_agent\", \"\"))\n"
    "            result[\"text\"] = replies.render(\"handoff\", lang)\n"
    "            return finish(result, pending=[], intents_done=[\"human_agent\"], overflow=[])\n"
    "        result = make(\"clarify\")\n"
    "        result[\"reason\"] = reason\n"
    "        result[\"text\"] = replies.render(\"clarify_intent\", lang)\n"
    "        return finish(result, awaiting_value=\"intent\", unclear=True)\n"
)
MARKER = "result[\"reason\"] = \"repeated_unclear\""


def main():
    try:
        with open(PATH, "r", encoding="utf-8", newline="") as handle:
            raw = handle.read()
    except OSError as error:
        print("FAIL cannot read", PATH, error)
        return 1
    crlf = "\r\n" in raw
    text = raw.replace("\r\n", "\n")
    if MARKER in text:
        print("FAIL already patched; nothing written")
        return 1
    problems = []
    for name, old in (("finish", FINISH_OLD), ("ask_intent", ASK_OLD)):
        count = text.count(old)
        if count != 1:
            problems.append(name + " anchor found " + str(count) + " times")
    if problems:
        for line in problems:
            print("FAIL", line)
        print("nothing written")
        return 1
    text = text.replace(ASK_OLD, ASK_NEW, 1).replace(FINISH_OLD, FINISH_NEW, 1)
    if text.count(MARKER) != 1 or text.count("unclear=True") != 1 or text.count("unclear=False") != 1:
        print("FAIL marker counts are wrong; nothing written")
        return 1
    try:
        compile(text, PATH, "exec")
    except SyntaxError as error:
        print("FAIL the result does not compile:", error, "; nothing written")
        return 1
    with open(PATH, "w", encoding="utf-8", newline="") as handle:
        handle.write(text.replace("\n", "\r\n") if crlf else text)
    print("ok   patched", PATH)
    return 0


if __name__ == "__main__":
    sys.exit(main())