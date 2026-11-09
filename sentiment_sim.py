"""Helpers shared by the Task 5 tests: simulated clock and a scripted conversation runner."""
import os
import tempfile
from datetime import datetime, timedelta, timezone

from src.sentiment.bridge import analyze_and_decide, check_timeouts, list_rows, record_human_reply
from src.tickets.config import get_config

IST = timezone(timedelta(hours=5, minutes=30))
UTC = timezone.utc


def ist(year, month, day, hour=0, minute=0, second=0):
    """A moment given in Indian time, returned as UTC."""
    return datetime(year, month, day, hour, minute, second, tzinfo=IST).astimezone(UTC)


def mon(hour, minute, second=0):
    return ist(2026, 10, 26, hour, minute, second)


def tue(hour, minute, second=0):
    return ist(2026, 10, 27, hour, minute, second)


def fri(hour, minute, second=0):
    return ist(2026, 10, 30, hour, minute, second)


def sat(hour, minute, second=0):
    return ist(2026, 10, 31, hour, minute, second)


def new_db():
    return os.path.join(tempfile.mkdtemp(), "sentiment_test.db")


def run(db, conversation, steps, cfg=None):
    """steps: (moment, action, text) with action msg, human or tick. Returns the results of the msg steps."""
    config = cfg if cfg is not None else get_config()
    results = []
    for moment, action, text in steps:
        if action == "msg":
            results.append(analyze_and_decide(conversation, text, now=moment, cfg=config, db_path=db))
        elif action == "human":
            record_human_reply(conversation, now=moment, db_path=db)
        else:
            check_timeouts(now=moment, cfg=config, db_path=db, only=conversation)
    return results


def outcome(db, conversation):
    rows = list_rows(conversation, db_path=db)
    return {
        "escalations": sorted({r["code"] for r in rows if r["kind"] == "escalation"}),
        "queues": sorted({r["queue"] for r in rows}),
        "count": len(rows),
        "rows": rows,
    }