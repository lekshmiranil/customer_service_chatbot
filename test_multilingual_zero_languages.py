"""A configuration with no usable language must not crash the layer. No network, no Gemini, no database."""
import copy
import sys

sys.stdout.reconfigure(errors="backslashreplace")

from src.multilingual import config, dialogue, languages, summary

failures = 0


def check(label, condition):
    global failures
    if condition:
        print("ok   " + label)
    else:
        print("FAIL " + label)
        failures += 1


TAMIL = "\u0b8e\u0ba9\u0bcd \u0b86\u0bb0\u0bcd\u0b9f\u0bb0\u0bcd \u0b8e\u0b99\u0bcd\u0b95\u0bc7"

cfg = copy.deepcopy(config.get_config())
cfg["languages"] = ["xx"]
cfg = config.normalise(cfg)

check("supported falls back to en", languages.supported_languages(cfg) == ["en"])
try:
    det = languages.detect(TAMIL, cfg)
    check("Tamil text reported unknown", det["language"] == "unknown")
    det = languages.detect("where is my order", cfg)
    check("English text detected as en", det["language"] == "en")
    state, result = dialogue.handle_message(summary.empty_state("en"), TAMIL, cfg, None)
    check("Tamil text gets a clarification", result.get("kind") == "clarify")
    state, result = dialogue.handle_message(summary.empty_state("en"), "where is my order ORD12345", cfg, None)
    check("English order query answered", result.get("kind") == "query" and result.get("language") == "en")
except Exception as error:
    check("no exception: " + type(error).__name__ + " " + ascii(str(error)), False)

if failures:
    print("FAILED: %d" % failures)
    sys.exit(1)
print("all ok")