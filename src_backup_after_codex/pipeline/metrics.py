import json
import math
from datetime import datetime, timedelta
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
METRICS_PATH = PROJECT_ROOT / "logs" / "metrics.jsonl"


def record(event_type: str, **fields):
    """Appends one JSON line describing an event.
    Never raises, so a monitoring problem can't break the chatbot or pipeline."""
    entry = {
        "timestamp": datetime.now().isoformat(timespec="seconds"),
        "type": event_type,
        **fields,
    }
    try:
        METRICS_PATH.parent.mkdir(parents=True, exist_ok=True)
        with open(METRICS_PATH, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry) + "\n")
    except OSError as e:
        print(f"Warning: could not write metrics: {e}")


def _read_events(hours=None):
    if not METRICS_PATH.exists():
        return []
    cutoff = datetime.now() - timedelta(hours=hours) if hours else None
    events = []
    with open(METRICS_PATH, encoding="utf-8") as f:
        for line in f:
            try:
                event = json.loads(line)
                if cutoff and datetime.fromisoformat(event["timestamp"]) < cutoff:
                    continue
            except (json.JSONDecodeError, KeyError, ValueError):
                continue
            events.append(event)
    return events


def _percentile(values, pct):
    if not values:
        return None
    ordered = sorted(values)
    index = max(0, math.ceil(pct / 100 * len(ordered)) - 1)
    return ordered[index]


def _average(values):
    return round(sum(values) / len(values), 3) if values else None


def summarize(hours=None):
    """Summarizes chatbot and pipeline activity, optionally for the last N hours."""
    events = _read_events(hours)
    queries = [e for e in events if e["type"] == "query"]
    attempts = [e for e in events if e["type"] == "pipeline_attempt"]

    latencies = [e["latency_ms"] for e in queries if e.get("latency_ms") is not None]
    confidences = [e["confidence"] for e in queries if e.get("confidence") is not None]
    failures = [e for e in queries if e.get("failed")]
    escalations = [e for e in queries if e.get("escalated")]

    reasons = {}
    for e in escalations:
        reason = e.get("reason", "unknown")
        reasons[reason] = reasons.get(reason, 0) + 1

    outcomes = {}
    for e in attempts:
        outcome = e.get("outcome", "unknown")
        outcomes[outcome] = outcomes.get(outcome, 0) + 1

    return {
        "queries": len(queries),
        "failures": len(failures),
        "failure_rate": round(len(failures) / len(queries), 3) if queries else 0,
        "latency_ms_avg": _average(latencies),
        "latency_ms_p95": _percentile(latencies, 95),
        "confidence_avg": _average(confidences),
        "confidence_min": min(confidences) if confidences else None,
        "escalations": len(escalations),
        "escalation_reasons": reasons,
        "pipeline_attempts": len(attempts),
        "pipeline_outcomes": outcomes,
    }