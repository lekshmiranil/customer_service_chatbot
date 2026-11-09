"""Test for src.multilingual.fallback.order_data_notice (pure function)."""
import sys

failures = 0


def check(label, condition):
    global failures
    if condition:
        print("ok   " + label)
    else:
        print("FAIL " + label)
        failures += 1


try:
    from src.multilingual.fallback import order_data_notice
except Exception as exc:
    print("FAIL import order_data_notice: " + ascii(repr(exc)))
    sys.exit(1)

text = order_data_notice(["order_status"], ["ORD-12345"], "refused")
check("order_status + order id + refused: notice returned", isinstance(text, str) and text != "")
check("notice says order data is not available", "not available" in text.lower())
check("notice says the support team will check", "support team" in text.lower())
check("notice is plain ASCII English", text.isascii())
check("notice does not echo the order id", "ORD-12345" not in text)

multi = order_data_notice(["order_status", "refund"], ["ORD-12345"], "refused")
check("multiple requests including order_status: notice returned", multi != "")

check("no order id known: empty", order_data_notice(["order_status"], [], "refused") == "")
check("order ids None: empty", order_data_notice(["order_status"], None, "refused") == "")
check("not refused (answered): empty", order_data_notice(["order_status"], ["ORD-12345"], "answered") == "")
check("not refused (clarify): empty", order_data_notice(["order_status"], ["ORD-12345"], "clarify") == "")
check("rag_status None: empty", order_data_notice(["order_status"], ["ORD-12345"], None) == "")
check("refund only: empty", order_data_notice(["refund"], ["ORD-12345"], "refused") == "")
check("intents None: empty", order_data_notice(None, ["ORD-12345"], "refused") == "")
check("tuple inputs accepted", order_data_notice(("order_status",), ("ORD-12345",), "refused") != "")

if failures:
    print("FAILED: " + str(failures))
    sys.exit(1)
print("all ok")