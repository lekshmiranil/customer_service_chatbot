"""Probe: language detection and intent result for Roman Malayalam person requests, plus false-positive guards.
Measurement only, writes nothing. Run from the project root: python -m tools.probe_ml_person_requests"""
from src.multilingual import config, intents, languages

CFG = config.get_config()
LANGS = languages.supported_languages(CFG)

SHOULD_HAND_OFF = [
    "vilikkaan pattumo?",
    "call cheyyattee?",
    "call cheyyuvoo??",
    "vilikkatte?",
    "oru aalod phone il samsarikkanam",
    "phone cheyyaamo?",
    "phone cheyth samsaarikkaamo?",
    "oru aale call cheyth tharumo?",
    "vilich samsarikkaan pattumo?",
]
SHOULD_NOT_HAND_OFF = [
    "I want to talk about my refund",
    "phone price evide",
    "ente phone vannilla",
    "refund kittumo?",
    "where is my package",
    "where exactly is my order",
    "call me",
]


def show(label, text):
    detected = languages.detect(text, CFG, "")
    if isinstance(detected, dict):
        lang = {k: detected.get(k) for k in ("language", "confidence", "mixed", "inherited")}
    else:
        lang = detected
    out = intents.analyze(text, LANGS, CFG.get("thresholds", {}))
    found = [(r["intent"], r["score"]) for r in out["requests"]]
    print(label, ascii(text))
    print("     language:", ascii(lang))
    print("     intents:", ascii(found), "unknown clauses:", out["unknown"], "ambiguous:", ascii(out["ambiguous"]))


print("== should become human_agent")
for text in SHOULD_HAND_OFF:
    show("A", text)
print("== must NOT become human_agent (where is my package and where exactly is my order should be order_status)")
for text in SHOULD_NOT_HAND_OFF:
    show("B", text)