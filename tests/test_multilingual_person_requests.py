"""Tests: Roman Malayalam requests for a person and false-positive guards. Prints ok or FAIL lines and exits 1 on
any failure. Run from the project root: python test_multilingual_person_requests.py"""
import sys

from src.multilingual import config, intents, languages

CFG = config.get_config()
LANGS = languages.supported_languages(CFG)
THR = CFG.get("thresholds", {})
MIN_LANGUAGE = float(THR.get("language_confidence", 0.6))
failures = []

PERSON = [
    "vilikkaan pattumo?", "call cheyyattee?", "call cheyyuvoo??", "vilikkatte?",
    "oru aalod phone il samsarikkanam", "phone cheyyaamo?", "phone cheyth samsaarikkaamo?",
    "oru aale call cheyth tharumo?", "vilich samsarikkaan pattumo?", "oru aalod samsarikkanam",
    # spelling variants of the same wording
    "vilikan patumo", "call cheyamo", "phone cheyyamoo", "oru aalod fone il samsarikanam", "VILIKKATTE",
]
NOT_PERSON = [
    "I want to talk about my refund", "phone price evide", "ente phone vannilla", "refund kittumo?",
    "refund ne patti samsarikkanam",
]


def found(text):
    return [r["intent"] for r in intents.analyze(text, LANGS, THR)["requests"]]


def check(label, ok, detail=""):
    if ok:
        print("ok  ", label)
    else:
        failures.append(label)
        print("FAIL", label, detail)


print("language_confidence threshold used:", MIN_LANGUAGE)
for text in PERSON:
    got = found(text)
    check("person intent " + ascii(text), "human_agent" in got, "got " + ascii(got))
    lang = languages.detect(text, CFG, "")
    check("person language " + ascii(text), lang["language"] == "ml" and lang["confidence"] >= MIN_LANGUAGE,
          "got " + ascii((lang["language"], lang["confidence"])))
for text in NOT_PERSON:
    got = found(text)
    check("not a person request " + ascii(text), "human_agent" not in got, "got " + ascii(got))
check("english 'call me' still hands off", "human_agent" in found("call me"))

print("failures:", len(failures))
sys.exit(1 if failures else 0)