"""Removing or restricting languages through the configuration. No network, no Gemini, no database."""
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
HINDI = "\u092e\u0947\u0930\u093e \u0911\u0930\u094d\u0921\u0930 \u0915\u0939\u093e\u0901 \u0939\u0948"
MALAYALAM = "\u0d0e\u0d28\u0d4d\u0d31\u0d46 \u0d13\u0d7c\u0d21\u0d7c \u0d0e\u0d35\u0d3f\u0d1f\u0d46"


def with_languages(codes):
    cfg = copy.deepcopy(config.get_config())
    cfg["languages"] = list(codes)
    return config.normalise(cfg)


def run(text, cfg, force=None):
    return dialogue.handle_message(summary.empty_state("en"), text, cfg, force)


def safe(label, function):
    try:
        return function()
    except Exception as error:
        check(label + " raised " + type(error).__name__ + ": " + ascii(str(error)), False)
        return None


full = with_languages(["en", "hi", "ml", "ta", "te", "kn"])
check("baseline: Tamil detected as ta", languages.detect(TAMIL, full)["language"] == "ta")

no_ta = with_languages(["en", "hi", "ml", "te", "kn"])
check("ta removed: supported list has 5", languages.supported_languages(no_ta) == ["en", "hi", "ml", "te", "kn"])
det = safe("ta removed: detect", lambda: languages.detect(TAMIL, no_ta))
if det:
    check("ta removed: Tamil script reported unknown", det["language"] == "unknown")
out = safe("ta removed: handle_message", lambda: run(TAMIL, no_ta))
if out:
    state, result = out
    check("ta removed: customer is asked to clarify", result.get("kind") == "clarify")
    check("ta removed: reason unsupported_language", result.get("reason") == "unsupported_language")
check("ta removed: Hindi still detected", languages.detect(HINDI, no_ta)["language"] == "hi")
check("ta removed: Malayalam still detected", languages.detect(MALAYALAM, no_ta)["language"] == "ml")

only_en = with_languages(["en"])
check("en only: Hindi reported unknown", languages.detect(HINDI, only_en)["language"] == "unknown")
out = safe("en only: English message", lambda: run("where is my order ORD12345", only_en))
if out:
    check("en only: English order query answered", out[1].get("kind") == "query")
    check("en only: order id kept", "ORD12345" in str(out[1]))

out = safe("ta removed: Roman Tamil message", lambda: run("en order eppo varum", no_ta))
if out:
    check("ta removed: Roman Tamil is not labelled ta", out[1].get("language") != "ta")

check("unknown code is ignored", languages.supported_languages(with_languages(["en", "xx"])) == ["en"])
check("empty list falls back to the six defaults", len(languages.supported_languages(with_languages([]))) == 6)

none_ok = with_languages(["xx"])
check("zero usable languages: normalise keeps the list", none_ok["languages"] == ["xx"])
safe("zero usable languages: detect on Tamil", lambda: languages.detect(TAMIL, none_ok))
safe("zero usable languages: detect on English", lambda: languages.detect("where is my order", none_ok))
safe("zero usable languages: handle_message", lambda: run(TAMIL, none_ok))

forced = safe("ta removed: force_language ta", lambda: run("where is my order", no_ta, "ta"))
if forced:
    print("info force_language=ta with ta removed: language=%s kind=%s" % (
        ascii(forced[1].get("language")), ascii(forced[1].get("kind"))))

if failures:
    print("FAILED: %d" % failures)
    sys.exit(1)
print("all ok")