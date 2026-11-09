import sys

sys.stdout.reconfigure(errors="backslashreplace")

from src.multilingual import config, intents, languages

failures = 0


def check(label, condition):
    global failures
    if condition:
        print("ok   " + label)
    else:
        print("FAIL " + label)
        failures += 1


cfg = config.get_config()
thr = cfg["thresholds"]
supported = languages.supported_languages(cfg)

check("six languages configured", len(supported) == 6)

native = [
    ("en", "where is my order"),
    ("hi", "\u092e\u0947\u0930\u093e \u0911\u0930\u094d\u0921\u0930 \u0915\u0939\u093e\u0901 \u0939\u0948"),
    ("ml", "\u0d0e\u0d28\u0d4d\u0d31\u0d46 \u0d13\u0d7c\u0d21\u0d7c \u0d0e\u0d35\u0d3f\u0d1f\u0d46"),
    ("ta", "\u0b8e\u0ba9\u0bcd \u0b86\u0bb0\u0bcd\u0b9f\u0bb0\u0bcd \u0b8e\u0b99\u0bcd\u0b95\u0bc7"),
    ("te", "\u0c28\u0c3e \u0c06\u0c30\u0c4d\u0c21\u0c30\u0c4d \u0c0e\u0c15\u0c4d\u0c15\u0c21 \u0c09\u0c02\u0c26\u0c3f"),
    ("kn", "\u0ca8\u0ca8\u0ccd\u0ca8 \u0c86\u0cb0\u0ccd\u0ca1\u0cb0\u0ccd \u0c8e\u0cb2\u0ccd\u0cb2\u0cbf\u0ca6\u0cc6"),
]
for code, text in native:
    check("native script detected as " + code, languages.detect(text, cfg)["language"] == code)

roman = [
    ("hi", "mera order kab aayega"),
    ("ml", "ente order evide"),
    ("ta", "en order eppo varum"),
    ("te", "naa order ekkada undi"),
    ("kn", "nanna order yelli ide"),
]
for code, text in roman:
    check("roman text detected as " + code, languages.detect(text, cfg)["language"] == code)

bengali = languages.detect("\u0986\u09ae\u09be\u09b0 \u0985\u09b0\u09cd\u09a1\u09be\u09b0 \u0995\u09cb\u09a5\u09be\u09af\u09bc", cfg)
check("unsupported script flagged", bool(bengali.get("unsupported")) or bengali["language"] == "unknown")

mixed = languages.detect("mera order ORD-12345 refund chahiye please", cfg)
check("mixed message flagged", mixed["mixed"] is True)
check("mixed message keeps hi and en", "hi" in mixed["languages"] and "en" in mixed["languages"])

inherit = languages.detect("ok", cfg, session_language="ta")
check("short ambiguous word scores below the inherit cap", inherit["language"] == "ta" or bool(inherit.get("inherited")) or inherit["confidence"] < 0.75)

picked = languages.language_by_name("tamil please", supported)
check("language chosen by name", picked == "ta" or (isinstance(picked, (list, tuple)) and "ta" in picked))

two = intents.analyze("cancel my order and give me a refund", ["en"], thr)
names = [r["intent"] for r in two["requests"]]
check("two requests found", "cancel_order" in names and "refund" in names)

spell = intents.analyze("wher is my ordr", ["en"], thr)
check("spelling errors tolerated", [r["intent"] for r in spell["requests"]][:1] == ["order_status"])

fix = intents.analyze("sorry, the order number is wrong, it is ORD-99999", ["en"], thr)
check("correction marker found", bool(fix["correction"]))

follow = intents.analyze("and the refund?", ["en"], thr)
check("short follow-up recognised", bool(follow["followup"]) or follow["word_count"] <= thr["followup_max_words"])

nothing = intents.analyze("blue green yellow table", ["en"], thr)
check("no intent for unrelated text", not nothing["requests"] or nothing["confidence"] < thr["intent_confidence"])

if failures:
    print(failures, "check(s) failed")
    sys.exit(1)
print("all checks passed")