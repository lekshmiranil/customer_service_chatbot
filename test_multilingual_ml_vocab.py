"""Tests: Roman Malayalam vocabulary and person-word suffixes, plus English guards. Prints ok or FAIL lines and exits 1
on any failure. Run from the project root: python test_multilingual_ml_vocab.py"""
import sys

from src.multilingual import config, intents, languages

CFG = config.get_config()
LANGS = languages.supported_languages(CFG)
THR = CFG.get("thresholds", {})
MIN_LANGUAGE = float(THR.get("language_confidence", 0.6))
failures = []


def check(label, ok, detail=""):
    if ok:
        print("ok  ", ascii(label))
    else:
        failures.append(label)
        print("FAIL", ascii(label), ascii(detail))


def found(text):
    return [r["intent"] for r in intents.analyze(text, LANGS, THR)["requests"]]


def lang(text):
    result = languages.detect(text, CFG, "")
    return result["language"], result["confidence"]


for text in ["refund venam, pinne delivery late aanu ORD-45550", "refund kittumo?", "ente order kittilla"]:
    got = lang(text)
    check("language ml " + text, got[0] == "ml" and got[1] >= MIN_LANGUAGE, got)

for text in ["enikk oru manushyanumayi samsarikkanam", "oru manushyanodu samsarikkanam"]:
    check("person request " + text, "human_agent" in found(text), found(text))

check("refund and delivery both found", {"refund", "delivery_issue"} <= set(found("refund venam, pinne delivery late aanu")),
      found("refund venam, pinne delivery late aanu"))
for text in ["I want to talk about my refund", "refund ne patti samsarikkanam"]:
    check("not a person request " + text, "human_agent" not in found(text), found(text))
for text in ["I want a refund for my late delivery", "where is my order and why is it late"]:
    got = lang(text)
    check("english stays english " + text, got[0] == "en", got)

print("failures:", len(failures))
sys.exit(1 if failures else 0)