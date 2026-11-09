"""Tests for the 'I am' name marker in entities.py. Uses no network and no Gemini."""
import sys

from src.multilingual import entities

CFG = {
    "entities": {
        "order_prefixes": ["ORD", "OD", "ODR", "INV", "BKG"],
        "product_prefixes": ["SKU", "PRD", "PROD", "MDL", "CRS"],
    }
}
failures = 0


def check(label, text, names, orders=None):
    global failures
    got = entities.extract(text, CFG)
    good = got["names"] == names and (orders is None or got["order_ids"] == orders)
    if good:
        print("ok   " + label)
    else:
        failures += 1
        print("FAIL %s text=%s names=%s expected=%s orders=%s" % (
            label, ascii(text), ascii(got["names"]), ascii(names), ascii(got["order_ids"])))


check("iam two-word name", "I am Anitha Menon", ["Anitha Menon"])
check("iam contraction", "I'm Ravi, my order ORD12345 is late", ["Ravi"], ["ORD12345"])
check("iam waiting", "I am waiting", [])
check("iam looking", "I am looking for my order", [])
check("iam name then lowercase verb", "I am Anitha calling about my refund", ["Anitha"])
check("iam name then and", "I am Anitha Menon and I want a refund", ["Anitha Menon"])
check("iam name then capital I", "I am Anitha Menon I want a refund", ["Anitha Menon"])
check("iam capitalised non-name Sorry", "I am Sorry", [])
check("iam capitalised non-name From", "I am From Kerala", [])
check("iam in the middle of a word", "Hi am Anitha", [])
check("known limit: lowercase not captured", "i am anitha", [])
check("regression my name is", "my name is Anitha Menon", ["Anitha Menon"])
check("regression ente peru", "ente peru Anitha aanu", ["Anitha"])

items = entities.extract("I am Anitha Menon, order ORD12345", CFG)["items"]
masked = entities.mask("I am Anitha Menon, order ORD12345", items)
if "Anitha" in masked or "ORD12345" in masked:
    failures += 1
    print("FAIL mask left an entity: " + ascii(masked))
else:
    print("ok   mask blanks name and order")

if failures:
    print("FAILED: %d" % failures)
    sys.exit(1)
print("all ok")