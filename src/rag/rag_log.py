"""JSON-lines log for the knowledge assistant. Never stores question or answer text."""
import json
import os
import threading
from datetime import datetime, timezone
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
_FORBIDDEN_KEYS = {"question", "text", "answer", "body", "message", "query"}
_lock = threading.Lock()


def log_path():
    return Path(os.environ.get("RAG_LOG_PATH") or (PROJECT_ROOT / "logs" / "rag.jsonl"))


def log_event(event, **fields):
    """Appends one line. Any failure is swallowed: logging must never break an answer."""
    try:
        record = {"ts": datetime.now(timezone.utc).isoformat(timespec="seconds"), "event": event}
        record.update({k: v for k, v in fields.items() if k not in _FORBIDDEN_KEYS})
        path = log_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        with _lock:
            with path.open("a", encoding="utf-8") as handle:
                handle.write(json.dumps(record, default=str) + "\n")
    except Exception:
        pass