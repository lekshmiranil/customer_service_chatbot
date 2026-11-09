import os
from datetime import datetime, time


def _parse_time(time_str: str) -> time:
    """Parses an 'HH:MM' 24-hour string into a time object."""
    hour, minute = map(int, time_str.split(":"))
    return time(hour=hour, minute=minute)


def is_within_maintenance_window() -> bool:
    """
    Checks whether the current local time falls within the configured
    maintenance window. Configured via MAINTENANCE_WINDOW_START and
    MAINTENANCE_WINDOW_END env vars (24-hour HH:MM format).
    Handles windows that cross midnight (e.g. 22:00-02:00).
    """
    start_str = os.getenv("MAINTENANCE_WINDOW_START", "02:00")
    end_str = os.getenv("MAINTENANCE_WINDOW_END", "04:00")

    window_start = _parse_time(start_str)
    window_end = _parse_time(end_str)
    now = datetime.now().time()

    if window_start <= window_end:
        # Normal case: window does not cross midnight
        return window_start <= now <= window_end
    else:
        # Window crosses midnight (e.g. 22:00 to 02:00)
        return now >= window_start or now <= window_end