"""Appends the safety net, Malayalam cue and holdout section to TASK6_NOTES.md. Refuses to write on any mismatch."""
import sys

PATH = "TASK6_NOTES.md"
HEADING = "## Safety net, Malayalam handoff cues and holdout result (2026-11-04)"
SECTION = """## Safety net, Malayalam handoff cues and holdout result (2026-11-04)
Safety net. When the layer finds no intent twice in a row (the clarification that asks what the customer needs), the second message gets a handoff with the reason repeated_unclear instead of a third question. Any other result resets the count: a recognised request, a greeting or thanks, a question about a missing order ID, or an either/or question. The ticket code treats this handoff like any other (reason customer_unresolved). Optional thresholds.unclear_before_handoff (default 2; values below 2 are ignored) is read by dialogue.py and is not set in config\\multilingual_config.json. Not covered: a customer who keeps getting the "which language?" question, and one who keeps getting either/or questions. Test: test_multilingual_safety_net.py (the language is forced to English so that only the counter is tested).
Malayalam cues. user_06 (a Roman Malayalam request for a person) failed on the first run. A probe showed the message was detected as Malayalam and returned no_intent, so the cause was missing cue vocabulary, not language detection. The project author, a Malayalam speaker, then wrote six further phrasings, all built on the word manushyan. The words manushyan, manushya, manushyanod and manushyanodu were added to the Malayalam human_agent cues, together with the Roman word agent (added by the assistant, not from the author's list, as the Hindi cues already do). All seven phrasings now return a handoff, including "manushyan aano?" (are you a human?), which also hands off, as the English word human already does.
Holdout. Two further phrasings, written by the author without the assistant seeing them and with wording different from the six: user_07 passed and user_08 failed. The user-written set therefore stands at 4/8 conversations: the first five scored 2/5 on the first run, user_06 passes only because its vocabulary was added afterwards (fitted, not unseen), and the holdout scored 1/2. Two phrasings do not give a rate; they show that the Malayalam cue coverage is partial. user_08 was detected as Malayalam (confidence 0.667) and returned no_intent, which points to a missing cue word. It was left unfixed on purpose, as a finding. A probe that sent the same text twice showed the safety net working: a clarification on the first message, a handoff with repeated_unclear on the second, and ticket reason customer_unresolved at function level (the Streamlit screen was not checked for this path).
Further limits. Roman-letter human_agent cues were not added for Tamil, Telugu or Kannada (their human_agent word lists are in native script and each has one Roman phrase). Only the Malayalam human_agent additions above come from a native speaker; the other cue lists are still AI-written and unreviewed. A new Malayalam holdout written by people other than the author would give a better estimate.
"""


def main():
    try:
        with open(PATH, "r", encoding="utf-8", newline="") as handle:
            raw = handle.read()
    except OSError as error:
        print("FAIL cannot read", PATH, error)
        return 1
    if "## Known limits" not in raw or "## Follow-ups after the first evaluation" not in raw:
        print("FAIL an expected heading is missing; nothing written")
        return 1
    if HEADING in raw:
        print("FAIL the section is already present; nothing written")
        return 1
    crlf = "\r\n" in raw
    text = raw.replace("\r\n", "\n").rstrip("\n") + "\n\n" + SECTION
    result = text.replace("\n", "\r\n") if crlf else text
    if result.count(HEADING) != 1 or not result.startswith(raw.rstrip("\r\n")[:200]) or "\\\\multilingual_config" in result:
        print("FAIL the result did not pass its checks; nothing written")
        return 1
    with open(PATH, "w", encoding="utf-8", newline="") as handle:
        handle.write(result)
    print("ok   TASK6_NOTES.md updated")
    return 0


if __name__ == "__main__":
    sys.exit(main())