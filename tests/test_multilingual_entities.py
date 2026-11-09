import sys

sys.stdout.reconfigure(errors="backslashreplace")

from src.multilingual import config, entities

failures = 0


def check(label, condition):
    global failures
    if condition:
        print("ok   " + label)
    else:
        print("FAIL " + label)
        failures += 1


cfg = config.get_config()

text = "my name is Anu Menon, order ORD-12345 delivered on 12/11/2026"
found = entities.extract(text, cfg)
check("order id kept exactly as typed", found["order_ids"] == ["ORD-12345"])
check("date kept exactly as typed", found["dates"] == ["12/11/2026"])
check("name found after marker", any(str(n).startswith("Anu") for n in found["names"]))

iso = entities.extract("delivery on 2026-11-12", cfg)
check("iso date kept", iso["dates"] == ["2026-11-12"])

lower = entities.extract("order ord-12345 please", cfg)
check("lowercase order id still found", len(lower["order_ids"]) == 1)

prefixes = list((cfg.get("entities") or {}).get("product_prefixes") or [])
if prefixes:
    code = prefixes[0] + "-100"
    prod = entities.extract("is " + code + " in stock", cfg)
    check("product code with first configured prefix", prod["product_codes"] == [code])
else:
    print("skip product code (no prefixes configured)")

none = entities.extract("where is my parcel", cfg)
check("no entities in plain text", not none["order_ids"] and not none["dates"])

masked = entities.mask(text, found["items"])
if isinstance(masked, (list, tuple)):
    masked = masked[0]
check("mask removes the order id", "ORD-12345" not in masked)
check("mask keeps other words", "delivered" in masked)

slots = entities.empty_slots()
slots, _ = entities.update_slots(slots, found)
check("slots store the order id", slots["order_ids"] == ["ORD-12345"])

fixed = entities.extract("sorry, the correct order is ORD-99999", cfg)
slots2, changes = entities.update_slots(slots, fixed, correction=True)
check("correction replaces order id", slots2["order_ids"][-1] == "ORD-99999")
check("correction reported as a change", bool(changes))
check("old order id removed on correction", "ORD-12345" not in slots2["order_ids"])

same = entities.same("ORD-12345", "ord-12345")
check("same() compares ids without case", same is True)

if failures:
    print(failures, "check(s) failed")
    sys.exit(1)
print("all checks passed")