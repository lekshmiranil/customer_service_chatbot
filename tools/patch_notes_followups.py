"""Appends a follow-ups section to TASK6_NOTES.md. Refuses to write on any mismatch."""
import sys

PATH = "TASK6_NOTES.md"
HEADING = "## Follow-ups after the first evaluation (2026-11-04)"
SECTION = """## Follow-ups after the first evaluation (2026-11-04)
Masking before storage. src\\multilingual\\masking.py masks card numbers, phone numbers and e-mail addresses in the customer text, the stored query, the bot reply and held_text before they are written to session_data\\sessions.db. Detection still runs on the unmasked text in memory. Order IDs are kept, including long numeric ones (the older mask_sensitive_data in src\\pipeline\\security.py does not mask +91 98765 43210 and damages ORD-1234567890, so it is not used here). The saved session state keeps order IDs, names and dates unmasked because restoring a session needs them. Limits: an unprefixed 10-digit number starting with 6 to 9 is treated as a phone number; 12-digit government ID numbers are not masked. Test: test_multilingual_masking.py.
Tickets. text_trigger (src\\tickets\\chat_bridge.py) reads the raw question and the answer kind, not the multilingual kind. A clarification or a social reply raises no ticket. A handoff from the multilingual layer now gets the reason customer_unresolved in any language (before this change a non-English handoff got low_confidence and its ticket lacked the previous exchange). Unresolved wording in the customer text is still detected in English only, and repeated clarifications are not counted. Test: test_multilingual_ticket_trigger.py (function level; the Streamlit screen was not checked by this test).
Findings from the user-written evaluation. user_02 was an error in the test expectation. user_04 (a question about a bill) and user_05 (a device fault) are outside the ten supported intents. When no intent is found and the text is detected as English with four or more words, the layer sends it unchanged to the knowledge assistant instead of asking for clarification (user_05 shows this).
Malayalam handoff probe. One Malayalam phrase written by the assistant (enikku oru manushyanodu samsarikkanam) was not recognised as a request for a person (kind clarify, no intent). The phrase was not reviewed by a native speaker, so this shows a possible gap, not a measured rate. Two Roman-script Hindi phrases were recognised as handoff.
Database. The six test sessions of customer cust1 (simulated dates, test sentences) were removed from sessions.db on 2026-11-04 after a backup. The test scripts and the evaluation do not write to the real database.
"""


def main():
    try:
        with open(PATH, "r", encoding="utf-8", newline="") as handle:
            raw = handle.read()
    except OSError as error:
        print("FAIL cannot read", PATH, error)
        return 1
    if "## Known limits" not in raw:
        print("FAIL the Known limits heading is missing; nothing written")
        return 1
    if HEADING in raw:
        print("FAIL the section is already present; nothing written")
        return 1
    crlf = "\r\n" in raw
    text = raw.replace("\r\n", "\n").rstrip("\n") + "\n\n" + SECTION
    result = text.replace("\n", "\r\n") if crlf else text
    if result.count(HEADING) != 1 or not result.startswith(raw.rstrip("\r\n")[:200]):
        print("FAIL the result did not pass its checks; nothing written")
        return 1
    with open(PATH, "w", encoding="utf-8", newline="") as handle:
        handle.write(result)
    print("ok   TASK6_NOTES.md updated")
    return 0


if __name__ == "__main__":
    sys.exit(main())