"""Tests: one extra word inside an English cue phrase. Prints ok or FAIL lines and exits 1 on any failure.
Run from the project root: python test_multilingual_phrase_gap.py"""
import sys

from src.multilingual import config, intents, languages

CFG = config.get_config()
LANGS = languages.supported_languages(CFG)
THR = CFG.get("thresholds", {})
failures = []


def found(text):
    return [r["intent"] for r in intents.analyze(text, LANGS, THR)["requests"]]


def check(label, ok, detail=""):
    if ok:
        print("ok  ", label)
    else:
        failures.append(label)
        print("FAIL", label, detail)


for text in ["where is my order", "where exactly is my order", "where is my new order",
             "when will it really arrive"]:
    got = found(text)
    check("order_status " + ascii(text), "order_status" in got, "got " + ascii(got))
got = found("where is the refund")
check("no order_status for 'where is the refund'", "order_status" not in got, "got " + ascii(got))

print("failures:", len(failures))
sys.exit(1 if failures else 0)