import copy
import sys

sys.stdout.reconfigure(errors="backslashreplace")

from src.multilingual import config, dialogue, summary

failures = 0


def check(label, condition):
    global failures
    if condition:
        print("ok   " + label)
    else:
        print("FAIL " + label)
        failures += 1


cfg = config.get_config()
need = set(cfg.get("intents_need_order") or [])
TAMIL = "\u0b8e\u0ba9\u0bcd \u0b86\u0bb0\u0bcd\u0b9f\u0bb0\u0bcd \u0b8e\u0b99\u0bcd\u0b95\u0bc7"
BENGALI = "\u0986\u09ae\u09be\u09b0 \u0985\u09b0\u09cd\u09a1\u09be\u09b0 \u0995\u09cb\u09a5\u09be\u09af\u09bc"


def run(messages, state=None):
    state = state if state is not None else summary.empty_state("en")
    results = []
    for message in messages:
        state, result = dialogue.handle_message(state, message, cfg)
        results.append(result)
    return state, results


# Greeting.
state, rs = run(["hello"])
check("greeting is a social reply", rs[0]["kind"] == "social" and rs[0]["intents"] == ["greeting"])

# Mixed Hindi and English, entity preserved exactly.
state, rs = run(["mera order ORD-12345 refund chahiye please"])
r = rs[0]
check("mixed message becomes a query", r["kind"] == "query")
check("mixed message language is hi", r["language"] == "hi")
check("mixed flag set", r["mixed"] is True)
check("refund intent found", "refund" in r["intents"])
check("order id preserved in the English query", "ORD-12345" in r["query"])
check("localized lead line present", bool(r["text"]))

# Language switching in the same conversation.
state, rs = run(["and the refund?"], state)
check("switch from hi to en detected", rs[0]["language"] == "en" and rs[0]["switched"] is True)
check("short follow-up gives refund query", rs[0]["kind"] == "query" and "refund" in rs[0]["intents"])

state, rs = run([TAMIL, "where is my order ORD-12345"])
check("tamil message detected", rs[0]["language"] == "ta")
check("tamil then english is a switch", rs[1]["language"] == "en" and rs[1]["switched"] is True)

# Ambiguous short follow-up resolved from the previous intent.
state, rs = run(["where is my order ORD-12345", "and the refund?", "and ORD-99999?"])
check("follow-up with only an id reuses the last intent", rs[2]["intents"] == ["refund"])
check("follow-up marked as resolved", rs[2]["resolved_from"] == "followup")

# Correction of earlier information.
state, rs = run(["where is my order ORD-11111", "sorry, the order number is ORD-22222"])
orders = state["slots"]["order_ids"]
check("correction stores the new order id", orders[-1:] == ["ORD-22222"])
check("correction removes the old order id", "ORD-11111" not in orders)
check("correction is reported", bool(rs[1]["changes"]) and bool(rs[1]["notices"]))

# Missing order id, then supplied.
if "order_status" in need:
    state, rs = run(["where is my order"])
    check("asks for an order id", rs[0]["kind"] == "clarify" and rs[0]["reason"] == "missing_order_id")
    check("request kept as pending", state.get("pending") == ["order_status"])
    state, rs = run(["ORD-55555"], state)
    check("pending request completed with the id", rs[0]["kind"] == "query" and rs[0]["resolved_from"] == "pending")
    check("supplied id in the query", "ORD-55555" in rs[0]["query"])
else:
    print("skip missing order id (order_status not in intents_need_order)")

# Multiple requests in one message.
state, rs = run(["cancel my order ORD-12345 and give me a refund"])
check("two intents found", set(rs[0]["intents"]) >= {"cancel_order", "refund"})
check("one query per intent", len(rs[0]["queries"]) == len(rs[0]["intents"]))

# Low confidence and unrelated text.
state, rs = run(["xyz qwerty asdf"])
check("unrelated text asks for clarification", rs[0]["kind"] == "clarify")

# Unsupported script then language chosen by name.
state, rs = run([BENGALI])
check("unsupported script asks for language", rs[0]["kind"] == "clarify" and state.get("awaiting") == "language")
state, rs = run(["tamil"], state)
check("language chosen by name is applied", state["language"] == "ta" and state.get("awaiting") != "language")

# Product code preserved.
prefixes = list((cfg.get("entities") or {}).get("product_prefixes") or [])
if prefixes:
    code = prefixes[0] + "-100"
    state, rs = run(["tell me about product " + code])
    check("product code extracted as typed", rs[0]["entities"]["product_codes"] == [code])
    if rs[0]["kind"] == "query":
        check("product code kept in the query", code in rs[0]["query"])

# Human agent request.
state, rs = run(["I want to talk to a human agent"])
check("human request is escalated", rs[0]["kind"] == "handoff" and rs[0]["escalated"] is True)

# Context kept over 12 messages.
messages = [
    "where is my order ORD-66666", "hello", "thanks", "and the refund?",
    "hello", "thanks", "mera order kab aayega", "payment failed",
    "delivery is late", "refund please", "hello", "thanks",
]
state, rs = run(messages)
check("at least 10 messages counted", state["message_count"] >= 10)
check("order id still known after 12 messages", state["slots"]["order_ids"][-1:] == ["ORD-66666"])

# Input state is not changed and odd input does not raise.
original = summary.empty_state("en")
snapshot = copy.deepcopy(original)
dialogue.handle_message(original, "hello", cfg)
check("input state not mutated", original == snapshot)

odd_ok = True
for odd in [None, "", "   ", "????", "a" * 5000, "\u0000\u0001"]:
    try:
        new_state, result = dialogue.handle_message(summary.empty_state("en"), odd, cfg)
        odd_ok = odd_ok and isinstance(result, dict) and isinstance(new_state, dict)
    except Exception as exc:
        print("raised on odd input:", type(exc).__name__, ascii(str(exc)))
        odd_ok = False
check("odd input never raises", odd_ok)

if failures:
    print(failures, "check(s) failed")
    sys.exit(1)
print("all checks passed")