import sys

sys.stdout.reconfigure(errors="backslashreplace")

from src.multilingual import config, dialogue, entities, intents, summary

failures = 0


def check(label, condition, detail=""):
    global failures
    if condition:
        print("ok   " + label)
    else:
        print("FAIL " + label + ((" | " + detail) if detail else ""))
        failures += 1


cfg = config.get_config()
thr = cfg["thresholds"]


def names(text):
    return entities.extract(text, cfg)["names"]


# Names, including a name that is also a Malayalam word.
check("full name after marker", names("my name is Anu Menon, order ORD-12345") == ["Anu Menon"], ascii(names("my name is Anu Menon, order ORD-12345")))
check("single name after marker", names("my name is Anu") == ["Anu"], ascii(names("my name is Anu")))
check("hindi marker and stop word", names("mera naam Priya hai") == ["Priya"], ascii(names("mera naam Priya hai")))
check("malayalam marker and stop word", names("ente peru Anu aanu") == ["Anu"], ascii(names("ente peru Anu aanu")))
check("known limit: no name without a marker", names("this is Anu Menon") == [])


# Spelling.
def first_intent(text):
    found = intents.analyze(text, ["en"], thr)
    return found["requests"][0]["intent"] if found["requests"] else ""


for sample in ["wher is my ordr", "wher is my order", "where is my ordr"]:
    check("spelling: " + ascii(sample), first_intent(sample) == "order_status", "got " + ascii(first_intent(sample)))

for sample in ["nice weather today friend", "i like the blue color", "the old cart is here", "please send more later"]:
    found = intents.analyze(sample, ["en"], thr)
    check("no false intent: " + ascii(sample), not found["requests"], ascii(found["requests"]))


def run(messages, state):
    results = []
    for message in messages:
        state, result = dialogue.handle_message(state, message, cfg)
        results.append(result)
    return state, results


# Short low-confidence messages keep the session language.
tamil_state = summary.empty_state("ta")
tamil_state["message_count"] = 2
state, rs = run(["ok"], tamil_state)
check("'ok' in a tamil session keeps tamil", rs[0]["language"] == "ta", ascii(rs[0]["language"]))

tamil_state = summary.empty_state("ta")
tamil_state["message_count"] = 2
state, rs = run(["and the refund?"], tamil_state)
check("clear english sentence still switches", rs[0]["language"] == "en" and rs[0]["switched"] is True, ascii((rs[0]["language"], rs[0]["switched"])))

# Order ID only where it belongs.
state, rs = run(["where is my order ORD-12345", "and the refund?"], summary.empty_state("en"))
check("refund query keeps the order id", "ORD-12345" in rs[1]["query"], ascii(rs[1]["query"]))

state, rs = run(["where is my order ORD-12345", "I want to know about the warranty of product code AB-100"], summary.empty_state("en"))
check("product question is a query", rs[1]["kind"] == "query", ascii(rs[1]["kind"]))
check("product query keeps the customer's words", "warranty" in rs[1]["query"], ascii(rs[1]["query"]))
check("product query has no order id", "ORD-12345" not in rs[1]["query"], ascii(rs[1]["query"]))
check("product code kept", "AB-100" in rs[1]["query"], ascii(rs[1]["query"]))

if failures:
    print(failures, "check(s) failed")
    sys.exit(1)
print("all checks passed")