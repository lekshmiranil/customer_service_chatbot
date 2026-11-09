import json
import os
import sys

from src.multimodal.compare import (
    compare_message,
    compare_message_with_document,
    extract_claims,
)
from src.multimodal.fields import extract_fields
from src.multimodal.ocr import QUALITY_MESSAGES, OcrPage, OcrWord

failures = []


def check(name, actual, expected):
    status = "PASS" if actual == expected else "FAIL"
    print(f"{status}: {name} (got {actual!r}, expected {expected!r})")
    if actual != expected:
        failures.append(name)


def make_page(lines):
    words = []
    for line_index, line in enumerate(lines):
        items = [(text, 92.0) for text in line.split()] if isinstance(line, str) else line
        left = 0
        for text, confidence in items:
            words.append(
                OcrWord(
                    text=text, confidence=confidence, left=left, top=line_index * 30,
                    width=len(text) * 10, height=20, line_key=(0, 0, line_index),
                )
            )
            left += len(text) * 10 + 10
    return OcrPage(
        words=words, width=1000, height=2000, sharpness=500.0,
        rotation_degrees=0.0, elapsed_seconds=0.1,
    )


def run(message, lines):
    page = make_page(lines)
    return compare_message(message, extract_fields(page), page.text)


def verdicts(result):
    return {item.kind: item.verdict for item in result.checks}


def describe(message):
    found = {}
    for claim in extract_claims(message):
        found.setdefault(claim.kind, []).append(claim.display)
    return found


INVOICE = [
    "INVOICE",
    "Order ID: 78231",
    "Date: 03/10/2026",
    "Amount: Rs 4500.00",
    "Product: Wireless Mouse WM-200",
    "Error code: E-502",
]

SCREENSHOT = [
    "YouWeFit Triple Strength Omega 3...",
    "Return window closed on 24 September",
    [("~809.00", 55.0)],
    "Order placed 9 September 2026",
    "Order number 404-9349228-5677929",
    [("Item(s)", 90.0), ("Subtotal:", 90.0), ("2809.00", 60.0)],
    [("Shipping:", 90.0), ("~40.00", 1.0)],
    [("Total:", 90.0), ("2852.25", 36.0)],
    [("Promotion", 90.0), ("Applied:", 90.0), ("-%80.45", 54.0)],
    [("Grand", 90.0), ("Total:", 90.0), ("2771.80", 35.0)],
]

MESSAGES = {
    1: "Hi, I was charged Rs 4500 for order 78231 on 3 Oct 2026 and my payment failed with E-502. Please help.",
    2: "my wireless mouse order 78213 shows error E-502, i paid 4500",
    3: "I was charged 5400 for order 78231, please check",
    4: "Order 404-9349228-5677929 placed on 9 September, I paid Rs 771.80 for the omega 3 capsules",
    5: "I ordered YouWeFit Omega 3 on 12 September and paid 771.80, where is my refund?",
    6: "hi my order hasn't arrived yet, can you check?",
    7: "Pay cheyyan nokkiyappo app shows error e-502",
    8: "I paid \u20b91,771.80 for order 404-9349228-5677929",
}

# Parsing the eight sample messages
check("parse 1", describe(MESSAGES[1]), {
    "order_id": ["78231"], "error_code": ["E-502"], "date": ["3 October 2026"], "amount": ["4500.00"]})
check("parse 2", describe(MESSAGES[2]), {
    "order_id": ["78213"], "error_code": ["E-502"], "amount": ["4500.00"]})
check("parse 3", describe(MESSAGES[3]), {"order_id": ["78231"], "amount": ["5400.00"]})
check("parse 4", describe(MESSAGES[4]), {
    "order_id": ["404-9349228-5677929"], "date": ["9 September"], "amount": ["771.80"]})
check("parse 5", describe(MESSAGES[5]), {"date": ["12 September"], "amount": ["771.80"]})
check("parse 6", describe(MESSAGES[6]), {})
check("parse 7", describe(MESSAGES[7]), {"error_code": ["E-502"]})
check("parse 8", describe(MESSAGES[8]), {
    "order_id": ["404-9349228-5677929"], "amount": ["1771.80"]})

# Parsing edge cases: numbers that are not amounts, words that are not order numbers
check("times and items are not amounts", describe("I was charged 12 times for 3 items"), {})
check("order without digits", describe("my order not delivered"), {})
check("decimal amount and dotted number", describe("paid 4.50 on 5.10"), {"amount": ["4.50"]})
check("numeric date with two-digit year", describe("paid on 22/12/25"), {"date": ["22 December 2025"]})
check("rupee sign after the number", describe("deducted 250 rs from my account"), {"amount": ["250.00"]})
check("duplicate claims collapse", describe("order 78231 and again order 78231"), {"order_id": ["78231"]})

# The eight sample messages against the matching documents
r = run(MESSAGES[1], INVOICE)
check("1 status", r.status, "confirmed")
check("1 verdicts", verdicts(r), {
    "order_id": "match", "date": "match", "amount": "match", "error_code": "match"})

r = run(MESSAGES[2], INVOICE)
check("2 status", r.status, "conflict")
check("2 verdicts", verdicts(r), {"order_id": "conflict", "amount": "match", "error_code": "match"})
check("2 product words", r.product_words, ("wireless", "mouse"))

r = run(MESSAGES[3], INVOICE)
check("3 status", r.status, "conflict")
check("3 verdicts", verdicts(r), {"order_id": "match", "amount": "conflict"})
check("3 reply quotes both amounts", ("5400.00" in r.reply, "4500.00" in r.reply), (True, True))

r = run(MESSAGES[4], SCREENSHOT)
check("4 status", r.status, "confirmed")
check("4 verdicts", verdicts(r), {"order_id": "match", "date": "match", "amount": "match"})
check("4 amount matched with caution", [c.caution for c in r.checks if c.kind == "amount"], [True])
check("4 reply mentions hard-to-read part", "hard to read" in r.reply, True)
check("4 product words", r.product_words, ("omega",))

r = run(MESSAGES[5], SCREENSHOT)
check("5 status", r.status, "conflict")
check("5 verdicts", verdicts(r), {"date": "conflict", "amount": "match"})
check("5 reply quotes the document date", "9 September 2026" in r.reply, True)
check("5 product words", r.product_words, ("youwefit", "omega"))

r = run(MESSAGES[6], SCREENSHOT)
check("6 status", r.status, "needs_confirmation")
check("6 reply names the order in the file", "404-9349228-5677929" in r.reply, True)
check("6 reply asks to confirm", "Is this the order" in r.reply, True)

r = run(MESSAGES[7], INVOICE)
check("7 status", r.status, "confirmed")
check("7 verdicts", verdicts(r), {"error_code": "match"})

r = run(MESSAGES[8], SCREENSHOT)
check("8 status", r.status, "needs_confirmation")
check("8 verdicts", verdicts(r), {"order_id": "match", "amount": "unclear"})
check("8 reply shows both readings", ("2771.80" in r.reply, "771.80" in r.reply), (True, True))

# Other documents
receipt = ["Bill No.: 36260", "Date 22/12/25", "Sub Total 104.76", "Grand Total \u20b9110.00"]
r = run("bill 36260, total 110", receipt)
check("receipt confirmed", (r.status, verdicts(r)), ("confirmed", {"order_id": "match", "amount": "match"}))

r = run("I paid Rs 500 yesterday", ["Shipping: Rs 40.00"])
check("amount with no headline is unverified", (r.status, verdicts(r)), ("needs_confirmation", {"amount": "unverified"}))
check("unverified reply asks for a file", "send a file" in r.reply, True)

r = run("order 78231 please", ["Invoice for the customer", "Thank you"])
check("order not in document is unverified", (r.status, verdicts(r)), ("needs_confirmation", {"order_id": "unverified"}))

# Unreadable page is refused before any comparison
empty = OcrPage(words=[], width=900, height=420, sharpness=100.0,
                rotation_degrees=0.0, elapsed_seconds=1.0)
r = compare_message_with_document("order 78231", empty)
check("unreadable page status", r.status, "needs_better_file")
check("unreadable page reply", r.reply, QUALITY_MESSAGES["no_readable_text"])

# Logs carry no personal or payment values
r = run(MESSAGES[3], INVOICE)
logged = json.dumps(r.log_fields())
check("log has no order number or amounts", any(v in logged for v in ("78231", "5400", "4500")), False)
check("log content", r.log_fields(), {
    "status": "conflict", "claims_checked": 2, "product_words_matched": 0,
    "order_id_verdict": "match", "amount_verdict": "conflict"})

# Date order setting
os.environ["DOCUMENT_DATE_ORDER"] = "MDY"
check("month-first reading", [c.display for c in extract_claims("paid on 03/10/2026")], ["10 March 2026"])
os.environ.pop("DOCUMENT_DATE_ORDER")
check("day-first reading", [c.display for c in extract_claims("paid on 03/10/2026")], ["3 October 2026"])

if failures:
    print(f"\n{len(failures)} check(s) failed: {failures}")
    sys.exit(1)

print("\nAll checks passed.")