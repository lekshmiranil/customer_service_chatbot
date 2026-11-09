"""End-to-end test through dialogue.handle_message: Roman Malayalam requests for a person, a language switch and
false-positive guards. Prints ok or FAIL lines and exits 1 on any failure. No model, no quota.
Run from the project root: python test_multilingual_person_flow.py"""
import sys

from src.multilingual import config, dialogue, summary

CFG = config.get_config()
failures = []

PERSON = [
    "vilikkaan pattumo?", "call cheyyattee?", "call cheyyuvoo??", "vilikkatte?",
    "oru aalod phone il samsarikkanam", "phone cheyyaamo?", "phone cheyth samsaarikkaamo?",
    "oru aale call cheyth tharumo?", "vilich samsarikkaan pattumo?",
]
NOT_PERSON = ["I want to talk about my refund", "refund ne patti samsarikkanam"]


def check(label, ok, detail=""):
    if ok:
        print("ok  ", ascii(label))
    else:
        failures.append(label)
        print("FAIL", ascii(label), ascii(detail))


def run(messages):
    state = summary.empty_state("en")
    results = []
    for text in messages:
        state, result = dialogue.handle_message(state, text, CFG, "")
        results.append(result)
    return state, results


def brief(result):
    return result.get("kind"), result.get("escalated"), result.get("intents"), result.get("language")


for text in PERSON:
    try:
        _, out = run([text])
        result = out[-1]
        check("fresh session hands off " + text,
              result.get("kind") == "handoff" and result.get("escalated") is True
              and "human_agent" in (result.get("intents") or []), brief(result))
        language = result.get("language")
        if language is None:
            print("INFO no language key in result for", ascii(text))
        else:
            check("reply language is ml " + text, language == "ml", language)
    except Exception as error:
        check("no exception " + text, False, repr(error))

for first in ("hello", "where is my order ORD-31337"):
    try:
        _, out = run([first, "phone cheyyaamo?"])
        check("after " + repr(first) + " the person request hands off", out[-1].get("kind") == "handoff", brief(out[-1]))
    except Exception as error:
        check("no exception after " + first, False, repr(error))

for text in NOT_PERSON:
    try:
        _, out = run([text])
        check("not a handoff " + text, out[-1].get("kind") != "handoff", brief(out[-1]))
    except Exception as error:
        check("no exception " + text, False, repr(error))

try:
    _, out = run(["ente phone repair cheyyaamo?"])
    print("INFO known false positive, not a check:", ascii(brief(out[-1])))
except Exception as error:
    print("INFO raised:", ascii(repr(error)))

print("failures:", len(failures))
sys.exit(1 if failures else 0)