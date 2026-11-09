"""A forced language that is disabled in the configuration is ignored. No network, no Gemini, no database."""
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


def run(text, cfg, force):
    return dialogue.handle_message(summary.empty_state("en"), text, cfg, force)


cfg = copy.deepcopy(config.get_config())
cfg["languages"] = ["en", "hi", "ml", "te", "kn"]
cfg = config.normalise(cfg)

try:
    state, result = run("where is my order ORD12345", cfg, "ta")
    check("disabled forced language ta is not used", result.get("language") != "ta")
    check("English query still answered", result.get("kind") == "query")
    check("order id kept", "ORD12345" in str(result))
    state, result = run("where is my order ORD12345", cfg, "hi")
    check("enabled forced language hi is used", result.get("language") == "hi")
    state, result = run("where is my order ORD12345", cfg, "xx")
    check("unknown forced language is ignored", result.get("language") not in ("xx", None, ""))
except Exception as error:
    check("no exception: " + type(error).__name__ + " " + ascii(str(error)), False)

if failures:
    print("FAILED: %d" % failures)
    sys.exit(1)
print("all ok")