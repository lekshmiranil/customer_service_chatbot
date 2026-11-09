import os
import sys
import time
from datetime import datetime, timedelta
from pathlib import Path

sys.path.append(str(Path(__file__).parent.parent.parent))

from dotenv import load_dotenv, find_dotenv
load_dotenv(find_dotenv())

from src.pipeline.scheduler import execute_pipeline_update_with_retries

DEFAULT_SCHEDULE_TIME = "01:30"


def get_schedule_time():
    """Reads SCHEDULE_TIME (24-hour HH:MM) from the environment.
    Falls back to the default if it is missing or invalid."""
    raw = os.getenv("SCHEDULE_TIME", DEFAULT_SCHEDULE_TIME)
    try:
        hour, minute = map(int, raw.split(":"))
        if not (0 <= hour < 24 and 0 <= minute < 60):
            raise ValueError
    except ValueError:
        print(f"Invalid SCHEDULE_TIME '{raw}'. Using default {DEFAULT_SCHEDULE_TIME}.")
        hour, minute = map(int, DEFAULT_SCHEDULE_TIME.split(":"))
    return hour, minute


def next_run_time(now: datetime) -> datetime:
    """Returns the next occurrence of the scheduled time (today or tomorrow)."""
    hour, minute = get_schedule_time()
    candidate = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
    if candidate <= now:
        candidate += timedelta(days=1)
    return candidate


def run_forever():
    while True:
        target = next_run_time(datetime.now())
        print(f"Next knowledge base update scheduled for {target:%Y-%m-%d %H:%M}.")

        # Sleep in short chunks so Ctrl+C responds quickly
        while datetime.now() < target:
            remaining = (target - datetime.now()).total_seconds()
            time.sleep(min(30, max(1, remaining)))

        try:
            execute_pipeline_update_with_retries()
        except Exception as e:
            # A crash in one run must not kill the scheduler
            print(f"Scheduled run crashed unexpectedly: {e}")


if __name__ == "__main__":
    if "--now" in sys.argv:
        execute_pipeline_update_with_retries()
    else:
        run_forever()