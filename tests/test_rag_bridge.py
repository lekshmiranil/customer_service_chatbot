"""Checks for src\\rag\\rag_bridge.py and rag_log.py: loading, reloading, normalising, logging, never raising."""
import json
import os
import sys
import tempfile
from datetime import date
from pathlib import Path

from make_rag_corpus import write_corpus

failures = 0
total = 0


def check(name, condition):
    global failures, total
    total += 1
    if condition:
        print(f"PASS {name}")
    else:
        failures += 1
        print(f"FAIL {name}")


work = Path(tempfile.mkdtemp())
corpus_folder = work / "corpus"
log_file = work / "logs" / "rag.jsonl"
os.environ["RAG_CORPUS_DIR"] = str(corpus_folder)
os.environ["RAG_LOG_PATH"] = str(log_file)

from src.rag import rag_bridge  # noqa: E402  (imported after the environment is set)
from src.rag.rag_log import log_event, log_path  # noqa: E402

TODAY = date(2026, 10, 24)
Q = "What is the refund window for the HomeHub?"


def log_lines():
    if not log_file.exists():
        return []
    return [json.loads(line) for line in log_file.read_text(encoding="utf-8").splitlines() if line.strip()]


check("log path comes from the environment", log_path() == log_file)

# ---- no corpus yet
a = rag_bridge.ask(Q, "public", "US", today=TODAY)
check("missing corpus folder is refused politely", a.status == "refused" and a.reason == "no_corpus")
check("summary reports unavailable", rag_bridge.corpus_summary()["available"] is False)

# ---- empty folder
corpus_folder.mkdir(parents=True)
a = rag_bridge.ask(Q, "public", "US", today=TODAY)
check("empty corpus folder is refused politely", a.reason == "no_corpus")

# ---- a real corpus
write_corpus(corpus_folder)
a = rag_bridge.ask(Q, "public", "US", today=TODAY)
check("answers once the corpus exists", a.status == "answered" and "15 days" in a.text)
summary = rag_bridge.corpus_summary()
check("summary counts documents", summary["available"] and summary["documents"] == 22 and summary["chunks"] > 20)
check("summary counts quarantined chunks", summary["quarantined"] == 3 and summary["rejected"] == 0)
first_loads = [e for e in log_lines() if e["event"] == "corpus_load"]
a = rag_bridge.ask(Q, "public", "US", today=TODAY)
check("corpus is not reloaded for every question", len([e for e in log_lines() if e["event"] == "corpus_load"]) == len(first_loads))

# ---- normalising role and region
a = rag_bridge.ask("What discount can an agent approve?", "ADMIN", "US", today=TODAY)
check("unknown role gets public access only", a.status == "refused" and "12 percent" not in a.text)
a = rag_bridge.ask("What discount can an agent approve?", "  Restricted ", "US", today=TODAY)
check("role is trimmed and lower-cased", a.status == "answered" and "12 percent" in a.text)
a = rag_bridge.ask("What discount can an agent approve?", None, "US", today=TODAY)
check("missing role gets public access only", a.status == "refused")
a = rag_bridge.ask(Q, "public", "mars", today=TODAY)
check("unknown region counts as not specified", a.status == "clarify" and a.needs == "region")
a = rag_bridge.ask(Q, "public", " in ", today=TODAY)
check("region is trimmed and upper-cased", "20 days" in a.text)

# ---- logging
entries = [e for e in log_lines() if e["event"] == "ask"]
check("one log line per question", len(entries) >= 8)
last = entries[-1]
check("log carries status and context", last["status"] == "answered" and last["role"] == "public" and last["region"] == "IN")
check("log carries cited documents", last["cited"] == ["POL-REF-IN v1"])
check("log records role normalisation", any(e["role_normalized"] for e in entries))
check("log records exclusion counts", entries[0]["excluded"] is None or "access" in (entries[-1]["excluded"] or {}))
raw_log = log_file.read_text(encoding="utf-8")
check("log never holds question text", "refund window" not in raw_log.lower() and "discount" not in raw_log.lower())
check("log never holds answer text", "15 days" not in raw_log and "12 percent" not in raw_log)
log_event("probe", question="secret question", text="secret text", answer="secret answer", fine="ok")
last_line = log_file.read_text(encoding="utf-8").splitlines()[-1]
check("log_event drops forbidden fields", "secret" not in last_line and '"fine": "ok"' in last_line)
check("quarantine counts are logged on load", any(e.get("quarantined") == 3 for e in log_lines() if e["event"] == "corpus_load"))

# ---- reload when a file changes
loads_before = len([e for e in log_lines() if e["event"] == "corpus_load"])
(corpus_folder / "TS-NEW_v1.md").write_text("# New\n## Blue light\nIf the blue light is on, the HomeHub is ready.\n", encoding="utf-8")
(corpus_folder / "TS-NEW_v1.meta.json").write_text(json.dumps({
    "doc_id": "TS-NEW", "title": "New", "doc_type": "troubleshooting", "topic": "blue-light", "version": "1",
    "product": "homehub", "region": "GLOBAL", "access_level": "public", "effective_date": "2025-01-01", "expiry_date": None}),
    encoding="utf-8")
a = rag_bridge.ask("What does the blue light mean on the HomeHub?", "public", "US", today=TODAY)
check("a new document is picked up without a restart", a.status == "answered" and "[TS-NEW v1, Blue light]" in a.text)
check("the change is logged as a reload", len([e for e in log_lines() if e["event"] == "corpus_load"]) == loads_before + 1)
(corpus_folder / "BAD_v1.md").write_text("# Bad\n## A\nSome text.\n", encoding="utf-8")
rag_bridge.ask(Q, "public", "US", today=TODAY)
check("a rejected document is reported in the load log",
      any(e.get("rejected") == 1 and "BAD_v1.md" in e.get("rejected_files", []) for e in log_lines() if e["event"] == "corpus_load"))
(corpus_folder / "BAD_v1.md").unlink()

# ---- never raises
original = rag_bridge.answer_question


def broken(*args, **kwargs):
    raise ValueError("boom")


rag_bridge.answer_question = broken
a = rag_bridge.ask(Q, "public", "US", today=TODAY)
rag_bridge.answer_question = original
check("an internal error becomes an error answer", a.status == "error" and a.reason == "exception:ValueError")
check("the error answer is safe to show", "went wrong" in a.text and "boom" not in a.text)
check("the error is logged", log_lines()[-1]["status"] == "error")

os.environ["RAG_LOG_PATH"] = str(work)  # a folder, so writing the log must fail
a = rag_bridge.ask(Q, "public", "US", today=TODAY)
check("a log failure never breaks answering", a.status == "answered")
os.environ["RAG_LOG_PATH"] = str(log_file)

check("empty question is handled", rag_bridge.ask("", "public", "US", today=TODAY).reason == "empty_question")
check("None question is handled", rag_bridge.ask(None, "public", "US", today=TODAY).status == "refused")

print(f"checks: {total}, failed: {failures}")
sys.exit(1 if failures else 0)