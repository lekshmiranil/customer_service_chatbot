"""Masked event log for the ticket workflow (Task 3).

Writes one JSON line per event to logs\\tickets.jsonl (override with TICKET_LOG_PATH). Callers pass
only ids, statuses, reason codes and field names; every string value is masked again here as a
second safety net, so conversation text, contact details and payment data cannot reach the log.
log_event() never raises, so a logging problem cannot break ticket processing.
"""
import json
import os
from datetime import datetime, timezone
from pathlib import Path

from src.tickets.masking import mask_text

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_LOG_PATH = PROJECT_ROOT / "logs" / "tickets.jsonl"


def _clean(value):
    if isinstance(value, str):
        return mask_text(value)[:300]
    if isinstance(value, dict):
        return {str(key): _clean(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_clean(item) for item in list(value)[:50]]
    if isinstance(value, (bool, int, float)) or value is None:
        return value
    return mask_text(str(value))[:300]


def log_path():
    from_env = os.getenv("TICKET_LOG_PATH")
    return Path(from_env) if from_env else DEFAULT_LOG_PATH


def log_event(event_type, **fields):
    entry = {
        "timestamp": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "type": event_type,
        **_clean(fields),
    }
    try:
        target = log_path()
        target.parent.mkdir(parents=True, exist_ok=True)
        with open(target, "a", encoding="utf-8") as handle:
            handle.write(json.dumps(entry) + "\n")
    except (OSError, TypeError, ValueError) as error:
        print(f"Warning: could not write the ticket log: {type(error).__name__}")