"""Records the first-run score of the user-written evaluation in TASK6_NOTES.md.
Replaces only the tail of the one line that starts with LINE_START. Refuses to write on any mismatch."""
import sys

PATH = "TASK6_NOTES.md"
LINE_START = "Two separate scores are reported."
TAIL_START = "Its score is recorded"
TAIL_MUST_CONTAIN = "has not been copied here"

NEW_TAIL = (
    "On 2026-11-04 the first run of the five user-written conversations scored 2/5 conversations and 2/5 turn "
    "checks (user_01 and user_03 passed). The first-run report is kept in "
    "backups\\eval_results_multilingual_first_run.md and the latest report is in eval_results_multilingual.md. "
    "The three failures have two causes, found by reading the code after the run. user_02 used an intent name "
    "that does not exist (return_request; the layer uses return_exchange) and expected an answer where the layer "
    "asks for the missing order ID, which is its designed behaviour, so both of its failures are errors in the "
    "test expectation. user_04 (a question about a bill) and user_05 (a device fault) fall outside the ten "
    "intents the layer supports (order_status, cancel_order, refund, return_exchange, payment_issue, "
    "delivery_issue, product_info, human_agent, greeting, thanks), which is a scope gap. user_05 returned kind "
    "query with no intent, which is consistent with the fallback in dialogue.py that sends English text of four "
    "or more words with no recognised intent to the knowledge assistant unchanged. Neither the expectations nor "
    "the cue lists were changed to raise this score, and these five conversations are no longer unseen."
)


def main():
    try:
        with open(PATH, "r", encoding="utf-8", newline="") as handle:
            raw = handle.read()
    except OSError as error:
        print("FAIL cannot read", PATH, error)
        return 1
    if "2/5 conversations" in raw:
        print("FAIL the score is already recorded; nothing written")
        return 1
    lines = raw.splitlines(keepends=True)
    hits = [i for i, line in enumerate(lines) if line.startswith(LINE_START)]
    if len(hits) != 1:
        print("FAIL expected exactly one line starting with the anchor, found", len(hits))
        return 1
    old = lines[hits[0]]
    if old.count(TAIL_START) != 1 or TAIL_MUST_CONTAIN not in old[old.index(TAIL_START):]:
        print("FAIL the line does not have the expected tail; nothing written")
        return 1
    body = old.rstrip("\r\n")
    ending = old[len(body):]
    lines[hits[0]] = body[: body.index(TAIL_START)] + NEW_TAIL + ending
    result = "".join(lines)
    checks = [
        "2/5 conversations" in result,
        TAIL_MUST_CONTAIN not in result,
        result.count(LINE_START) == 1,
        len(result.splitlines()) == len(raw.splitlines()),
    ]
    if not all(checks):
        print("FAIL the result did not pass its checks; nothing written", checks)
        return 1
    with open(PATH, "w", encoding="utf-8", newline="") as handle:
        handle.write(result)
    print("ok   TASK6_NOTES.md updated")
    return 0


if __name__ == "__main__":
    sys.exit(main())