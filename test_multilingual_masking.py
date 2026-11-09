"""Tests the masking module and checks that the bridge stores masked text. No model, no quota."""
import os
import sqlite3
import sys
import tempfile

from src.multilingual import bridge, masking

FAILED = 0


def check(label, condition, detail=""):
    global FAILED
    if condition:
        print("ok  ", ascii(label))
    else:
        FAILED += 1
        print("FAIL", ascii(label), ascii(detail))


CASES = [
    ("card spaced", "my card is 4111 1111 1111 1111", "my card is [REDACTED_CREDIT_CARD]"),
    ("card hyphen", "card 4111-1111-1111-1111 ok", "card [REDACTED_CREDIT_CARD] ok"),
    ("mobile plain", "call me on 9876543210", "call me on [REDACTED_PHONE]"),
    ("mobile 5+5", "call me on 98765 43210", "call me on [REDACTED_PHONE]"),
    ("mobile +91 spaced", "call me on +91 98765 43210", "call me on [REDACTED_PHONE]"),
    ("mobile +91 joined", "call me on +919876543210", "call me on [REDACTED_PHONE]"),
    ("mobile 0 prefix", "call 09876543210 now", "call [REDACTED_PHONE] now"),
    ("international", "call +44 7911 123456 now", "call [REDACTED_PHONE] now"),
    ("email", "mail me at anu.menon@example.com", "mail me at [REDACTED_EMAIL]"),
    ("order id kept", "where is my order ORD-12345", "where is my order ORD-12345"),
    ("long order id kept", "where is my order ORD-1234567890", "where is my order ORD-1234567890"),
    ("phone-like order id kept", "ORD-9876543210 please", "ORD-9876543210 please"),
    ("date kept", "delivery was promised on 12/11/2026", "delivery was promised on 12/11/2026"),
    ("hindi text kept", "\u092e\u0947\u0930\u093e order ORD-12345 \u0915\u0939\u093e\u0901 \u0939\u0948",
     "\u092e\u0947\u0930\u093e order ORD-12345 \u0915\u0939\u093e\u0901 \u0939\u0948"),
    ("empty", "", ""),
]

for label, text, expected in CASES:
    got = masking.mask(text)
    check("mask " + label, got == expected, got)
    check("idempotent " + label, masking.mask(got) == got, masking.mask(got))
check("mask None", masking.mask(None) == "")

TYPED = "my card is 4111 1111 1111 1111 where is my order ORD-12345"
with tempfile.TemporaryDirectory() as folder:
    db = os.path.join(folder, "masking_test.db")
    result = bridge.handle_turn("", "", text=TYPED, db_path=db)
    check("bridge ok", result.get("ok") is True, result.get("error"))
    check("query keeps the order id", "ORD-12345" in (result.get("query") or ""), result.get("query"))
    conn = sqlite3.connect(db)
    rows = conn.execute("SELECT role, text, meta FROM turns ORDER BY id").fetchall()
    states = conn.execute("SELECT state FROM sessions").fetchall()
    conn.close()
    customer = [row[1] for row in rows if row[0] == "customer"]
    check("customer turn stored", len(customer) == 1, len(customer))
    if customer:
        check("stored text has no card digits", "4111" not in customer[0], customer[0])
        check("stored text has the token", "[REDACTED_CREDIT_CARD]" in customer[0], customer[0])
        check("stored text keeps the order id", "ORD-12345" in customer[0], customer[0])
    check("no card digits in any stored turn or meta", all("4111" not in (row[1] + row[2]) for row in rows))
    check("no card digits in stored state", all("4111" not in (row[0] or "") for row in states))

sys.exit(1 if FAILED else 0)