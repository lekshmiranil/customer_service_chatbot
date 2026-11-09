"""One-time patch: retrieval_query for the knowledge assistant call.

Run from the project root:  python -m tools.patch_retrieval_query
Checks every anchor and guard, compiles the result in memory, backs up to
backups\\, and writes nothing if any check fails.
"""
import shutil
import sys
from pathlib import Path

ROOT = Path.cwd()
BACKUPS = ROOT / "backups"
TAG = ".before_retrieval_query"

FILES = {
    "lexicon": ROOT / "src" / "multilingual" / "lexicon.py",
    "dialogue": ROOT / "src" / "multilingual" / "dialogue.py",
    "bridge": ROOT / "src" / "multilingual" / "bridge.py",
    "main": ROOT / "src" / "main.py",
}

# Each guard matches only NEW text; it must be absent before patching.
GUARDS = {
    "lexicon": '"How do I track my order?"',
    "dialogue": "retrieval_query",
    "bridge": "retrieval_query",
    "main": "order_data_notice",
}

EDITS = [
    ("lexicon", "canonical order_status wording",
     '"order_status": "How do I check my order status and track my order?",',
     '"order_status": "How do I track my order?",'),

    ("dialogue", "make() default dict",
     '        "query": "",\n        "queries": [],\n',
     '        "query": "",\n        "queries": [],\n        "retrieval_query": "",\n'),

    ("dialogue", "build_query block",
     '    def build_query(intent):\n'
     '        own_words = (\n'
     '            intent == "product_info"\n'
     '            and lang == "en"\n'
     '            and len(real) == 1\n'
     '            and words >= _int(thr.get("general_question_min_words"), 4)\n'
     '        )\n'
     '        if own_words:\n'
     '            return text\n'
     '        return _query(intent, current, slots_new, known_order if intent in need_order else "")\n',
     '    def is_own_words(intent):\n'
     '        return (\n'
     '            intent == "product_info"\n'
     '            and lang == "en"\n'
     '            and len(real) == 1\n'
     '            and words >= _int(thr.get("general_question_min_words"), 4)\n'
     '        )\n'
     '\n'
     '    def build_query(intent):\n'
     '        if is_own_words(intent):\n'
     '            return text\n'
     '        return _query(intent, current, slots_new, known_order if intent in need_order else "")\n'
     '\n'
     '    def build_retrieval_query(intent):\n'
     '        # Question sent to the knowledge assistant: no order ID, product code or date.\n'
     '        if is_own_words(intent):\n'
     '            return text\n'
     '        return str(lexicon.CANONICAL_QUERY.get(intent, "")).strip()\n'),

    ("dialogue", "result fields",
     '    result["queries"] = queries\n    result["query"] = " ".join(queries)\n',
     '    result["queries"] = queries\n'
     '    result["query"] = " ".join(queries)\n'
     '    result["retrieval_query"] = " ".join(\n'
     '        q for q in (build_retrieval_query(i) for i in real) if q\n'
     '    )\n'),

    ("bridge", "_failure dict",
     '        "query": "",\n        "queries": [],\n',
     '        "query": "",\n        "queries": [],\n        "retrieval_query": "",\n'),

    ("bridge", "handle_turn return dict",
     '            "query": result.get("query", ""),\n'
     '            "queries": list(result.get("queries") or []),\n',
     '            "query": result.get("query", ""),\n'
     '            "queries": list(result.get("queries") or []),\n'
     '            "retrieval_query": result.get("retrieval_query", ""),\n'),

    ("main", "answer_text_question call",
     'answer = ask_existing(layer["query"])  # plain English query built from intent and preserved entities',
     'from src.multilingual.fallback import order_data_notice, order_ids_from_query\n'
     '        # retrieval_query is the canonical question only; order ID, product code and date stay in layer["query"].\n'
     '        answer = ask_existing(layer.get("retrieval_query") or layer["query"])\n'
     '        notice = order_data_notice(\n'
     '            layer.get("intents"), order_ids_from_query(layer.get("query")), answer.get("rag_status")\n'
     '        )\n'
     '        if notice:\n'
     '            answer["text"] = notice  # text only: escalated, kind and rag_status stay unchanged'),
]


def refuse(message):
    print("REFUSED: " + message)
    print("Nothing was written.")
    sys.exit(1)


state = {}
for key, path in FILES.items():
    if not path.is_file():
        refuse("file not found: " + str(path))
    raw = path.read_bytes()
    bom = raw.startswith(b"\xef\xbb\xbf")
    try:
        text = raw.decode("utf-8-sig")
    except UnicodeDecodeError:
        refuse(path.name + " is not valid UTF-8")
    crlf = "\r\n" in text
    if crlf and text.count("\n") != text.count("\r\n"):
        refuse(path.name + " has mixed line endings")
    norm = text.replace("\r\n", "\n")
    if GUARDS[key] in norm:
        refuse(path.name + " already contains the new text (guard " + repr(GUARDS[key]) + ")")
    state[key] = {"raw": raw, "bom": bom, "crlf": crlf, "text": norm}

for key, label, old, new in EDITS:
    count = state[key]["text"].count(old)
    if count != 1:
        refuse(FILES[key].name + " / " + label + ": anchor found " + str(count) + " times, expected 1")
    state[key]["text"] = state[key]["text"].replace(old, new)
    print("anchor ok: " + FILES[key].name + " / " + label)

for key, path in FILES.items():
    if GUARDS[key] not in state[key]["text"]:
        refuse(path.name + ": new text missing after edit")
    try:
        compile(state[key]["text"], str(path), "exec")
    except SyntaxError as exc:
        refuse(path.name + " would not compile: " + str(exc))
print("all four results compile")

BACKUPS.mkdir(exist_ok=True)
for key, path in FILES.items():
    if (BACKUPS / (path.name + TAG)).exists():
        refuse("backup already exists: " + str(BACKUPS / (path.name + TAG)))
for key, path in FILES.items():
    shutil.copy2(path, BACKUPS / (path.name + TAG))
print("backups written to " + str(BACKUPS))

written = []
try:
    for key, path in FILES.items():
        out = state[key]["text"]
        if state[key]["crlf"]:
            out = out.replace("\n", "\r\n")
        data = out.encode("utf-8")
        if state[key]["bom"]:
            data = b"\xef\xbb\xbf" + data
        path.write_bytes(data)
        written.append(key)
except Exception as exc:
    for key in written:
        FILES[key].write_bytes(state[key]["raw"])
    print("WRITE FAILED, originals restored: " + repr(exc))
    sys.exit(1)

for key, path in FILES.items():
    if GUARDS[key] not in path.read_text(encoding="utf-8-sig").replace("\r\n", "\n"):
        print("VERIFY FAILED for " + path.name)
        sys.exit(1)
print("patched and verified: " + ", ".join(p.name for p in FILES.values()))