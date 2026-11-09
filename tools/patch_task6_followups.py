"""Two edits: (1) bridge.py stores masked text, (2) chat_bridge.py gives a handoff from the multilingual layer
the reason customer_unresolved. Verifies every anchor in both files first, compiles both results and writes
nothing unless every check passes."""
import sys

EDITS = {
    "src/multilingual/bridge.py": [
        (
            "from src.multilingual import config, dialogue, replies, session_store, summary",
            "from src.multilingual import config, dialogue, masking, replies, session_store, summary",
        ),
        (
            "        new_state, result = dialogue.handle_message(state, text, cfg, force_language)",
            "        new_state, result = dialogue.handle_message(state, text, cfg, force_language)\n"
            "        if isinstance(new_state, dict) and new_state.get(\"held_text\"):\n"
            "            new_state[\"held_text\"] = masking.mask(new_state[\"held_text\"])",
        ),
        (
            "            \"query\": result.get(\"query\"),",
            "            \"query\": masking.mask(result.get(\"query\")),",
        ),
        (
            "conn, active_id, \"customer\", str(text or \"\"), lang, when, None, limit",
            "conn, active_id, \"customer\", masking.mask(text), lang, when, None, limit",
        ),
        (
            "        reply = result.get(\"text\") or result.get(\"query\") or \"\"",
            "        reply = masking.mask(result.get(\"text\") or result.get(\"query\") or \"\")",
        ),
    ],
    "src/tickets/chat_bridge.py": [
        (
            "    if kind == \"answer\" and answer.get(\"escalated\"):\n"
            "        return \"low_confidence\"",
            "    if kind == \"answer\" and answer.get(\"escalated\"):\n"
            "        info = answer.get(\"ml\")\n"
            "        if isinstance(info, dict) and info.get(\"kind\") == \"handoff\":\n"
            "            return \"customer_unresolved\"  # the multilingual layer sent the customer to a person\n"
            "        return \"low_confidence\"",
        ),
    ],
}
MARKERS = {"src/multilingual/bridge.py": ("masking.mask(", 4), "src/tickets/chat_bridge.py": ("info.get(\"kind\") == \"handoff\"", 1)}


def main():
    prepared = {}
    problems = []
    for path, edits in EDITS.items():
        try:
            with open(path, "r", encoding="utf-8", newline="") as handle:
                raw = handle.read()
        except OSError as error:
            problems.append(path + ": cannot read " + str(error))
            continue
        crlf = "\r\n" in raw
        text = raw.replace("\r\n", "\n")
        marker, _ = MARKERS[path]
        if marker in text:
            problems.append(path + ": already patched")
            continue
        for old, _new in edits:
            count = text.count(old)
            if count != 1:
                problems.append(path + ": anchor found " + str(count) + " times: " + ascii(old[:70]))
        if any(p.startswith(path + ": anchor") for p in problems):
            continue
        for old, new in edits:
            text = text.replace(old, new, 1)
        marker, expected = MARKERS[path]
        if text.count(marker) != expected:
            problems.append(path + ": marker count is " + str(text.count(marker)) + ", expected " + str(expected))
            continue
        try:
            compile(text, path, "exec")
        except SyntaxError as error:
            problems.append(path + ": result does not compile: " + str(error))
            continue
        prepared[path] = text.replace("\n", "\r\n") if crlf else text
    if problems or len(prepared) != len(EDITS):
        for line in problems:
            print("FAIL", line)
        print("nothing written")
        return 1
    for path, content in prepared.items():
        with open(path, "w", encoding="utf-8", newline="") as handle:
            handle.write(content)
        print("ok   patched", path)
    return 0


if __name__ == "__main__":
    sys.exit(main())