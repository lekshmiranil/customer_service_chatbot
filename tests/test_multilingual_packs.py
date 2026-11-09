"""Language packs: add, replace, reject and switch off a language through files and configuration.
Synthetic language 'zz' with invented words: this tests the mechanism, not the quality of any language."""
import copy
import json
import os
import sys
import tempfile

sys.stdout.reconfigure(errors="backslashreplace")

from src.multilingual import config, dialogue, entities, languages, lexicon, packs, replies, summary

failures = 0


def check(label, condition):
    global failures
    if condition:
        print("ok   " + label)
    else:
        print("FAIL " + label)
        failures += 1


def make_pack(code, name, **over):
    pack = {
        "code": code,
        "name": name,
        "text": {key: "[" + code + "] " + replies.TEXT[key]["en"] for key in replies.TEXT},
        "labels": {key: code + "-" + key for key in replies.LABELS},
    }
    pack.update(over)
    return pack


def write(folder, file_name, content):
    with open(os.path.join(folder, file_name), "w", encoding="utf-8") as handle:
        handle.write(content if isinstance(content, str) else json.dumps(content, ensure_ascii=False))


def config_with(codes):
    cfg = copy.deepcopy(config.get_config())
    cfg["languages"] = list(codes)
    return config.normalise(cfg)


ZZ_TEXT = "kwelt zorp vrim ORD12345"
base_codes = ["en", "hi", "ml", "ta", "te", "kn"]
cfg_zz = config_with(base_codes + ["zz"])
before_langs = tuple(replies.LANGS)

check("before loading, zz is not supported", "zz" not in languages.supported_languages(cfg_zz))

with tempfile.TemporaryDirectory() as folder:
    write(folder, "zz.json", make_pack(
        "zz", "Zzlang",
        roman_words="zorp kwelt vrim zzhello mivo tosh",
        cues={"order_status": {"w": "kwelt", "p": ["vrim kwelt tosh"]}, "greeting": {"w": "zzhello"}},
        name_markers=[["zzname"]],
        name_words=["zzlang"],
    ))
    bad_missing = make_pack("qq", "Qqlang")
    del bad_missing["text"]["thanks"]
    write(folder, "bad_missing.json", bad_missing)
    bad_placeholder = make_pack("ww", "Wwlang")
    bad_placeholder["text"]["restored"] = "[ww] restored {nope}"
    write(folder, "bad_placeholder.json", bad_placeholder)
    write(folder, "bad_overlap.json", make_pack("oo", "Oolang", script_range=[0x0B80, 0x0BFF]))
    write(folder, "bad_field.json", make_pack("pp", "Pplang", colour="red"))
    write(folder, "bad_json.json", "{ this is not json")

    report = packs.load_packs(folder)
    print("info rejected: " + ascii(report["rejected"]))
    check("only the valid pack loaded", report["loaded"] == ["zz"])
    check("five invalid packs rejected", len(report["rejected"]) == 5)
    check("missing reply key rejected", "bad_missing.json" in report["rejected"])
    check("placeholder mismatch rejected", "bad_placeholder.json" in report["rejected"])
    check("script overlap rejected", "bad_overlap.json" in report["rejected"])
    check("unknown field rejected", "bad_field.json" in report["rejected"])
    check("broken JSON rejected", "bad_json.json" in report["rejected"])
    check("rejected packs left no trace", all(code not in lexicon.LANG_NAMES for code in ("qq", "ww", "oo", "pp")))
    check("replies.LANGS gained only zz", tuple(replies.LANGS) == before_langs + ("zz",))

    check("zz supported after loading", "zz" in languages.supported_languages(cfg_zz))
    check("reply text for zz", replies.render("greeting", "zz").startswith("[zz] "))
    check("label for zz", replies.label("order_status", "zz") == "zz-order_status")
    check("no reply gaps for any language", replies.missing() == [])
    check("language list names zz", "Zzlang" in replies.render("clarify_language", "en"))
    check("language named by the customer", languages.language_by_name("zzlang", ["en", "zz"]) == "zz")
    check("name marker from the pack", entities.extract("zzname Tilo", cfg_zz)["names"] == ["Tilo"])
    check("built-in name marker still works", entities.extract("my name is Anitha", cfg_zz)["names"] == ["Anitha"])

    det = languages.detect("kwelt zorp vrim", cfg_zz)
    check("zz detected from Roman words", det["language"] == "zz")
    try:
        state, result = dialogue.handle_message(summary.empty_state("en"), ZZ_TEXT, cfg_zz, "")
        check("zz message gives language zz", result.get("language") == "zz")
        check("zz message gives order_status", "order_status" in (result.get("intents") or []))
        check("zz message is a query", result.get("kind") == "query")
        check("order id kept", "ORD12345" in str(result))
    except Exception as error:
        check("no exception: " + type(error).__name__ + " " + ascii(str(error)), False)

    tamil = "\u0b8e\u0ba9\u0bcd \u0b86\u0bb0\u0bcd\u0b9f\u0bb0\u0bcd \u0b8e\u0b99\u0bcd\u0b95\u0bc7"
    check("Tamil still detected", languages.detect(tamil, cfg_zz)["language"] == "ta")
    check("English still detected", languages.detect("where is my order", cfg_zz)["language"] == "en")

    cfg_off = config_with(base_codes)
    check("zz switched off through the configuration", "zz" not in languages.supported_languages(cfg_off))
    check("switched-off zz is not detected", languages.detect("kwelt zorp vrim", cfg_off)["language"] != "zz")

with tempfile.TemporaryDirectory() as folder:
    saved = replies.TEXT["greeting"]["en"]
    write(folder, "en.json", {"code": "en", "text": {"greeting": "Synthetic hello!"}})
    report = packs.load_packs(folder)
    check("partial pack replaces one reply of an existing language", report["loaded"] == ["en"]
          and replies.render("greeting", "en") == "Synthetic hello!")
    check("other English replies untouched", replies.render("thanks", "en") != "")
    replies.TEXT["greeting"]["en"] = saved
    check("test restored the English greeting", replies.render("greeting", "en") == saved)

check("a missing folder is not an error", packs.load_packs(os.path.join(tempfile.gettempdir(), "no_such_pack_folder")) == {"loaded": [], "rejected": {}})

if failures:
    print("FAILED: %d" % failures)
    sys.exit(1)
print("all ok")