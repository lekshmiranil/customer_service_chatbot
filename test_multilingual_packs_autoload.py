"""End to end: a pack file in a folder is loaded automatically when the bridge is imported, a language that is in the
configuration but has no pack is not used, and loading twice does not duplicate a language. Runs fresh Python
processes. Synthetic language 'zz'. No network, no Gemini; the database is a temporary file."""
import json
import os
import subprocess
import sys
import tempfile

sys.stdout.reconfigure(errors="backslashreplace")

from src.multilingual import dialogue, replies  # dialogue merges the extra reply keys (e.g. 'updated')

failures = 0


def check(label, condition):
    global failures
    if condition:
        print("ok   " + label)
    else:
        print("FAIL " + label)
        failures += 1


def child(code, env_extra):
    env = dict(os.environ)
    env.update(env_extra)
    env["PYTHONIOENCODING"] = "utf-8"
    done = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, encoding="utf-8", env=env)
    lines = [line for line in done.stdout.splitlines() if line.strip()]
    try:
        return json.loads(lines[-1])
    except (IndexError, ValueError):
        print("info child failed, stderr: " + ascii(done.stderr[-600:]))
        return None


TURN = (
    "import json\n"
    "from src.multilingual import bridge\n"
    "r = bridge.handle_turn('s1', 'c1', 'kwelt zorp vrim ORD12345')\n"
    "print(json.dumps({'ok': r['ok'], 'language': r['language'], 'kind': r['kind'], 'intents': r['intents'],"
    " 'error': bridge.LAST_ERROR, 'has_id': 'ORD12345' in json.dumps(r['result'])}))\n"
)
TWICE = (
    "import json\n"
    "from src.multilingual import dialogue, packs, replies\n"
    "packs.load_packs()\n"
    "report = packs.load_packs()\n"
    "print(json.dumps({'langs': list(replies.LANGS), 'rejected': report['rejected']}))\n"
)

pack = {
    "code": "zz",
    "name": "Zzlang",
    "text": {key: "[zz] " + replies.TEXT[key]["en"] for key in replies.TEXT},
    "labels": {key: "zz-" + key for key in replies.LABELS},
    "roman_words": "zorp kwelt vrim zzhello mivo tosh",
    "cues": {"order_status": {"w": "kwelt", "p": ["vrim kwelt tosh"]}},
}

with tempfile.TemporaryDirectory() as work:
    packs_folder = os.path.join(work, "packs")
    empty_folder = os.path.join(work, "empty")
    os.makedirs(packs_folder)
    os.makedirs(empty_folder)
    with open(os.path.join(packs_folder, "zz.json"), "w", encoding="utf-8") as handle:
        json.dump(pack, handle, ensure_ascii=False)
    cfg_path = os.path.join(work, "cfg.json")
    with open(cfg_path, "w", encoding="utf-8") as handle:
        json.dump({"languages": ["en", "hi", "ml", "ta", "te", "kn", "zz"]}, handle)
    base = {"MULTILINGUAL_CONFIG_PATH": cfg_path, "MULTILINGUAL_DB_PATH": os.path.join(work, "s.db")}

    got = child(TURN, dict(base, MULTILINGUAL_PACKS_DIR=packs_folder))
    check("child with pack ran", got is not None and got.get("ok") is True)
    if got:
        print("info with pack: " + ascii(got))
        check("pack loaded at import: language zz", got["language"] == "zz")
        check("pack loaded at import: order_status", "order_status" in got["intents"])
        check("pack loaded at import: kind query", got["kind"] == "query")
        check("order id kept end to end", got["has_id"] is True)

    got = child(TURN, dict(base, MULTILINGUAL_PACKS_DIR=empty_folder, MULTILINGUAL_DB_PATH=os.path.join(work, "t.db")))
    check("child without pack ran", got is not None and got.get("ok") is True)
    if got:
        print("info without pack: " + ascii(got))
        check("language in config but no pack: zz not used", got["language"] != "zz")

    got = child(TWICE, dict(base, MULTILINGUAL_PACKS_DIR=packs_folder))
    check("double-load child ran", got is not None)
    if got:
        check("zz appears once after three loads", got["langs"].count("zz") == 1)
        check("no rejection when loaded again", got["rejected"] == {})

if failures:
    print("FAILED: %d" % failures)
    sys.exit(1)
print("all ok")