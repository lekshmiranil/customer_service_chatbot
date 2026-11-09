"""Order-details wording that wrongly became product_info or fell through to the knowledge assistant (found in the
Streamlit check on 2026-11-07). Written BEFORE the fix. No network, no Gemini, no database."""
import sys

sys.stdout.reconfigure(errors="backslashreplace")

from src.multilingual import config, dialogue, intents, languages, summary

failures = 0
CFG = config.get_config()
THR = CFG["thresholds"]
LANGS = languages.supported_languages(CFG)


def check(label, condition):
    global failures
    if condition:
        print("ok   " + label)
    else:
        print("FAIL " + label)
        failures += 1


def found(text):
    return [r["intent"] for r in intents.analyze(text, LANGS, THR)["requests"]]


def run(text):
    return dialogue.handle_message(summary.empty_state("en"), text, CFG, "")[1]


try:
    for text in ("i need to know about my order", "order details of", "enikk order details venam",
                 "I want the order details", "order information please"):
        check("order_status for " + ascii(text), "order_status" in found(text) and "product_info" not in found(text))

    for text in ("i need to know about my order", "enikk order details venam"):
        check("no ID: not sent to the knowledge assistant: " + ascii(text), run(text).get("kind") != "query")

    result = run("order details of ORD-12345")
    check("with ID: query for order_status", result.get("kind") == "query" and "order_status" in (result.get("intents") or []))
    check("with ID: order id kept", "ORD-12345" in str(result))
    check("with ID: not product_info", "product_info" not in (result.get("intents") or []))

    check("regression: course details still product_info", "product_info" in found("course details please"))
    check("regression: product details still product_info", "product_info" in found("product details"))
    check("regression: cancel my order", found("cancel my order") == ["cancel_order"])
    check("regression: where is my order", found("where is my order") == ["order_status"])
    print("info tell me about my order -> " + ascii(found("tell me about my order")) + " (tie expected, not judged)")
except Exception as error:
    check("no exception: " + type(error).__name__ + " " + ascii(str(error)), False)

if failures:
    print("FAILED: %d" % failures)
    sys.exit(1)
print("all ok")