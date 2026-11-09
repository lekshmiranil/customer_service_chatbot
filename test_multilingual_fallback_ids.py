"""Test for order_ids_from_query, including the real bridge query format."""
import os
import shutil
import sys
import tempfile

failures = 0


def check(label, condition):
    global failures
    if condition:
        print("ok   " + label)
    else:
        print("FAIL " + label)
        failures += 1


try:
    from src.multilingual.fallback import order_ids_from_query
except Exception as exc:
    print("FAIL import order_ids_from_query: " + ascii(repr(exc)))
    sys.exit(1)

check("one id", order_ids_from_query("How do I track my order? Order ID: ORD-12345.") == ["ORD-12345"])
check("no id", order_ids_from_query("How do I track my order?") == [])
check("None input", order_ids_from_query(None) == [])
check("empty input", order_ids_from_query("") == [])
check(
    "two ids, order kept, duplicates removed",
    order_ids_from_query("Order ID: ORD-1. Order ID: ORD-2. Order ID: ORD-1.") == ["ORD-1", "ORD-2"],
)

# Integration: the format must match what the real bridge produces.
tmp = tempfile.mkdtemp()
try:
    from src.multilingual import bridge

    res = bridge.handle_turn("ids-test-1", "", "order details of ORD-12345",
                             db_path=os.path.join(tmp, "ids_test.db"))
    check("bridge turn ok", res.get("ok") is True)
    check("bridge query yields the order id", order_ids_from_query(res.get("query")) == ["ORD-12345"])
except Exception as exc:
    print("FAIL bridge integration raised: " + ascii(repr(exc)))
    failures += 1
finally:
    shutil.rmtree(tmp, ignore_errors=True)

if failures:
    print("FAILED: " + str(failures))
    sys.exit(1)
print("all ok")