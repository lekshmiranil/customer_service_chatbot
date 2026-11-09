"""One-time patch: append the retrieval-query notes to TASK6_NOTES.md and EXPECTATION_LOG.md.

Run from the project root:  python -m tools.patch_task6_notes
Refuses and writes nothing if a file is missing, does not end with the expected last
line, or already contains the new text. Backups go to backups\\.
"""
import shutil
import sys
from pathlib import Path

ROOT = Path.cwd()
BACKUPS = ROOT / "backups"
TAG = ".before_retrieval_notes"

NOTES_TAIL = "The assistant-written sets show regressions, not generalisation."
LOG_TAIL = "- unseen_04 and unseen_07 were written by the assistant, not blind."

NOTES_GUARD = "## Order-details gap, retrieval query and order-data notice (2026-11-07)"
LOG_GUARD = "- customer role, manual Streamlit check: EXPECTATION ERROR (mine)."

NOTES_ADD = '''
## Order-details gap, retrieval query and order-data notice (2026-11-07)
How it was found. A manual Streamlit check of 'order details of ORD-12345' ended in the notice 'I couldn't find a reliable answer...' and a ticket (TKT-000019). No evaluation set had flagged it. The order-details wording gap (fixed in lexicon_cues.py, test_multilingual_order_details.py) and the retrieval gaps below were found by manual use and probes, so the evaluation sets under-cover ordinary customer wording and the knowledge-assistant step.
Probe findings (the probes used no Gemini request). 1. FAQ-ORD-GL ('How do I track my order?') has access level customer; for role public every wording is refused with no_evidence. The role comes from the sidebar selector (default public). test_rag_select.py and eval_rag_run.py assert that FAQ-ORD-GL is customer-only, so its access level was not changed. 2. The ID suffix breaks retrieval: for role customer the plain canonical question answered from FAQ-ORD-GL (coverage 0.73); with '+ORD-12345.' it gave 0.48 and with '+Order ID: ORD-12345.' 0.41, both below MIN_COVERAGE 0.5 (answer.py). Refund with 'Order ID: ORD-12345.' in region IN was refused (top hit POL-CAN-A, coverage 0.22); refund without it answered from POL-REF-IN. 3. The 'Date: ...' extra was treated as a policy date by the knowledge assistant; refund with a date in region IN was answered from POL-WAR-GL (warranty policy), a wrong-policy answer. 4. The old canonical order_status wording added the note I found nothing about 'check'.
Open findings, not fixed. 5. Multiple requests are joined into one retrieval query; order_status plus refund was answered only from FAQ-ORD-GL with no mention of refund. A fix means one retrieval per request, which is one Gemini request each when Gemini is on; to be decided later and tested with Gemini off. 6. Without any ID, four intents get no knowledge answer in region GLOBAL for roles public and customer: delivery_issue, payment_issue, return_exchange and product_info. The cause is unverified (assumption: the canonical wording does not match the corpus; product_info asks about course fees, duration and certificate). Asked without an ID, cancel_order gives ambiguous_sources and refund gives needs_region. Not changed: a wording is changed only after a probe shows that a passage exists.
Changes made. The canonical order_status question is now 'How do I track my order?' (a deliberate fit to one FAQ, stated in test_multilingual_retrieval_query.py). The layer returns a new field retrieval_query (the canonical question only, with no order ID, product code or date) from dialogue.py and bridge.py, and main.py sends it to the knowledge assistant. The field query is unchanged and still carries the order ID, product code and date, as do the stored state and the lead line (existing tests expect this). New module src\\multilingual\\fallback.py with order_data_notice and order_ids_from_query. When the knowledge assistant refuses an order_status request that has an order ID, main.py replaces only the answer text with an English notice that order details are not available in this chat and that the support team will check; escalated, kind and rag_status stay unchanged, so the ticket is kept. Applied with tools\\patch_retrieval_query.py (backups in backups\\*.before_retrieval_query).
Verification. test_multilingual_retrieval_query.py: 7 FAIL and 7 ok before the change, 14/14 after. test_multilingual_fallback.py (14 checks) and test_multilingual_fallback_ids.py (7 checks, including the real bridge query format) pass. All test_*.py exit 0. Evaluation unchanged: assistant-written 15/15 (42/42), user-written 6/8, unseen set 16/18 (40/42). Streamlit, fresh sessions: 'i need to know about my order' and 'enikk order details venam' ask for the order ID; 'order details of ORD-12345' at role public shows the notice and raises a ticket; at role customer it answers from FAQ-ORD-GL with the source line and raises no ticket. main.py has no automated test, so this Streamlit check is its only verification.
Process deviations. test_multilingual_fallback.py and test_multilingual_fallback_ids.py were not shown failing before their module existed: the import failure of the first test was shown afterwards by moving the module away, and the second was never shown failing. backups\\fallback.py.before_ids holds the new version, not the first one.
Limits recorded. The order date no longer acts as a policy date (the date stays in the query, the state and the lead line). Knowledge answers stay English, and so does the new notice. The notice is shown for any refusal of an order_status request with an order ID, not only for role public. Multiple requests are answered from one joined retrieval (open finding 5). Four intents return no knowledge answer in the current corpus (open finding 6). The Streamlit check covered one wording per case and the roles public and customer; the roles internal and restricted, other regions and Gemini on were not checked.
'''

LOG_ADD = '''- customer role, manual Streamlit check: EXPECTATION ERROR (mine). Expected no ticket for 'order details of ORD-12345' at role customer. The first customer run showed 'This matches your earlier request, so it was added to ticket TKT-000019' because the page had not been reloaded after the public run, so the session still had an open ticket (main.py record_text_exchange keeps adding exchanges while ticket_open is set; the rest of that function was not seen). Two runs in fresh sessions raised no ticket. Not a defect of the retrieval_query patch.
- Order-details gap and retrieval gaps (findings 1 to 6 in TASK6_NOTES.md): found by manual use and probes, not by any evaluation set. No expectation in the evaluation sets was added or changed; the sets still do not exercise the knowledge-assistant step.
- test_multilingual_retrieval_query.py: the canonical order_status wording is fitted to one FAQ (FAQ-ORD-GL) on purpose. The check 'customer: no nothing-about note' was vacuous while that answer was refused and is meaningful now that the FAQ answers.
- Process: the fallback tests were not shown failing first (see TASK6_NOTES.md).'''

TARGETS = [
    ("TASK6_NOTES.md", NOTES_TAIL, NOTES_GUARD, NOTES_ADD),
    ("EXPECTATION_LOG.md", LOG_TAIL, LOG_GUARD, LOG_ADD),
]


def refuse(message):
    print("REFUSED: " + message)
    print("Nothing was written.")
    sys.exit(1)


state = []
for name, tail, guard, add in TARGETS:
    path = ROOT / name
    if not path.is_file():
        refuse("file not found: " + str(path))
    raw = path.read_bytes()
    bom = raw.startswith(b"\xef\xbb\xbf")
    try:
        text = raw.decode("utf-8-sig")
    except UnicodeDecodeError:
        refuse(name + " is not valid UTF-8")
    crlf = "\r\n" in text
    if crlf and text.count("\n") != text.count("\r\n"):
        refuse(name + " has mixed line endings")
    norm = text.replace("\r\n", "\n")
    if guard in norm:
        refuse(name + " already contains the new text")
    if not norm.rstrip().endswith(tail):
        refuse(name + " does not end with the expected last line")
    new = norm.rstrip() + "\n" + add.rstrip("\n") + "\n"
    if guard not in new:
        refuse(name + ": guard text missing from the new content")
    state.append({"name": name, "path": path, "raw": raw, "bom": bom, "crlf": crlf, "new": new, "guard": guard})
    print("checks ok: " + name)

BACKUPS.mkdir(exist_ok=True)
for item in state:
    if (BACKUPS / (item["name"] + TAG)).exists():
        refuse("backup already exists: " + item["name"] + TAG)
for item in state:
    shutil.copy2(item["path"], BACKUPS / (item["name"] + TAG))
print("backups written to " + str(BACKUPS))

written = []
try:
    for item in state:
        out = item["new"]
        if item["crlf"]:
            out = out.replace("\n", "\r\n")
        data = out.encode("utf-8")
        if item["bom"]:
            data = b"\xef\xbb\xbf" + data
        item["path"].write_bytes(data)
        written.append(item)
except Exception as exc:
    for item in written:
        item["path"].write_bytes(item["raw"])
    print("WRITE FAILED, originals restored: " + repr(exc))
    sys.exit(1)

for item in state:
    check = item["path"].read_text(encoding="utf-8-sig").replace("\r\n", "\n")
    if item["guard"] not in check:
        print("VERIFY FAILED for " + item["name"])
        sys.exit(1)
print("patched and verified: " + ", ".join(i["name"] for i in state))