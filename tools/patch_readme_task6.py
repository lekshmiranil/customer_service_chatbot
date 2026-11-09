"""Updates the Task 6 section of README.md: adds a short subsection after the Known limits line and the three new
test scripts to the Checks line. Every anchor must occur exactly once. Nothing is written on any mismatch."""
import sys

PATH = "README.md"
LIMITS_LINE = ("Cue lists and replies in five languages are AI-written and not reviewed by a native speaker. "
               "ID formats are assumptions. See TASK6_NOTES.md.")
OLD_CHECKS = "test_multilingual_session.py, then python eval_multilingual_run.py"
NEW_CHECKS = ("test_multilingual_session.py, test_multilingual_masking.py, test_multilingual_safety_net.py, "
              "test_multilingual_ticket_trigger.py, then python eval_multilingual_run.py")
ADDED = [
    "",
    "### Stored text, handoff and tickets",
    "Customer text is masked (card numbers, phone numbers, e-mail addresses) before it is written to "
    "`session_data\\sessions.db`. Order IDs, names and dates are kept because restoring a session needs them. "
    "A request for a person gets a handoff reply in the detected language, and the Task 3 ticket system raises a "
    "ticket with the reason customer_unresolved. After two messages in a row that the layer cannot understand, the "
    "second one is handed off in the same way. Recognising Malayalam requests for a person is partial: it works for "
    "most of the phrasings tested and not for all. TASK6_NOTES.md has the results and the limits.",
]


def main():
    try:
        with open(PATH, "r", encoding="utf-8", newline="") as handle:
            raw = handle.read()
    except OSError as error:
        print("FAIL cannot read", PATH, error)
        return 1
    crlf = "\r\n" in raw
    lines = raw.replace("\r\n", "\n").split("\n")
    if any(line.strip() == "### Stored text, handoff and tickets" for line in lines):
        print("FAIL already updated; nothing written")
        return 1
    limit_hits = [i for i, line in enumerate(lines) if line.strip() == LIMITS_LINE]
    if len(limit_hits) != 1:
        print("FAIL the Known limits line was found", len(limit_hits), "times; nothing written")
        return 1
    after = lines[limit_hits[0] + 1: limit_hits[0] + 7]
    if not any(line.strip() == "### Configuration" for line in after):
        print("FAIL the Configuration heading does not follow the Known limits line; nothing written")
        return 1
    check_hits = [i for i, line in enumerate(lines) if OLD_CHECKS in line and line.startswith("python test_multilingual_")]
    if len(check_hits) != 1:
        print("FAIL the Checks line was found", len(check_hits), "times; nothing written")
        return 1
    if abs(check_hits[0] - limit_hits[0]) > 12:
        print("FAIL the Checks line is not in the same section; nothing written")
        return 1
    lines[check_hits[0]] = lines[check_hits[0]].replace(OLD_CHECKS, NEW_CHECKS, 1)
    lines[limit_hits[0] + 1:limit_hits[0] + 1] = ADDED
    text = "\n".join(lines)
    if text.count("### Stored text, handoff and tickets") != 1 or text.count("test_multilingual_safety_net.py") != 1:
        print("FAIL the result did not pass its checks; nothing written")
        return 1
    with open(PATH, "w", encoding="utf-8", newline="") as handle:
        handle.write(text.replace("\n", "\r\n") if crlf else text)
    print("ok   README.md updated")
    return 0


if __name__ == "__main__":
    sys.exit(main())