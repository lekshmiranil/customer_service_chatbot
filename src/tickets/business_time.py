"""Business-calendar and SLA clock arithmetic for the ticket workflow (Task 3).

All inputs and outputs are timezone-aware datetimes. Every calculation converts to UTC
before subtracting, because Python's subtraction of two datetimes that share a ZoneInfo
ignores UTC-offset changes and would be wrong across daylight-saving transitions.

Business time counts only the configured working window (for example 09:00-18:00 in the
configured timezone) on configured working days that are not holidays. Calendar time
counts every second. A window is built from local wall-clock times each day, so on a
daylight-saving day a window can be one hour longer or shorter in real time; an
ambiguous local time (clocks going back) uses its first occurrence.
"""
from datetime import datetime, timedelta, timezone

UTC = timezone.utc
BASES = ("business", "calendar")
MAX_SEARCH_DAYS = 3700
EPSILON = 1e-6


def to_utc(moment):
    """Converts an aware datetime to UTC; naive datetimes are refused, never guessed."""
    if not isinstance(moment, datetime) or moment.tzinfo is None or moment.utcoffset() is None:
        raise ValueError("a timezone-aware datetime is required")
    return moment.astimezone(UTC)


def _window(cfg, day):
    start = datetime.combine(day, cfg.work_start, tzinfo=cfg.tz).astimezone(UTC)
    end = datetime.combine(day, cfg.work_end, tzinfo=cfg.tz).astimezone(UTC)
    return start, end


def business_seconds_between(cfg, start, end):
    """Working seconds between two moments, excluding weekends, holidays and hours outside the window."""
    start_utc = to_utc(start)
    end_utc = to_utc(end)
    if end_utc <= start_utc:
        return 0.0
    day = start_utc.astimezone(cfg.tz).date()
    last_day = end_utc.astimezone(cfg.tz).date()
    if (last_day - day).days > MAX_SEARCH_DAYS:
        raise ValueError("time span is too long for a business-time calculation")
    total = 0.0
    while day <= last_day:
        if cfg.is_working_day(day):
            window_start, window_end = _window(cfg, day)
            low = max(window_start, start_utc)
            high = min(window_end, end_utc)
            if high > low:
                total += (high - low).total_seconds()
        day += timedelta(days=1)
    return total


def add_business_seconds(cfg, start, seconds):
    """The moment reached after spending the given working seconds from start."""
    if seconds < 0:
        raise ValueError("seconds must not be negative")
    cursor = to_utc(start)
    remaining = float(seconds)
    day = cursor.astimezone(cfg.tz).date()
    for _ in range(MAX_SEARCH_DAYS):
        if cfg.is_working_day(day):
            window_start, window_end = _window(cfg, day)
            begin = max(window_start, cursor)
            if begin < window_end:
                available = (window_end - begin).total_seconds()
                if remaining <= available:
                    return begin + timedelta(seconds=remaining)
                remaining -= available
        day += timedelta(days=1)
    raise ValueError("no working time was found; check the business hours and holidays")


def next_business_open(cfg, moment):
    """The moment itself when the business is open, otherwise the next opening time."""
    moment_utc = to_utc(moment)
    day = moment_utc.astimezone(cfg.tz).date()
    for _ in range(MAX_SEARCH_DAYS):
        if cfg.is_working_day(day):
            window_start, window_end = _window(cfg, day)
            if moment_utc < window_end:
                return max(window_start, moment_utc)
        day += timedelta(days=1)
    raise ValueError("no working time was found; check the business hours and holidays")


def is_business_open(cfg, moment):
    return next_business_open(cfg, moment) == to_utc(moment)


def elapsed_seconds(cfg, basis, start, end):
    """Elapsed time on the chosen basis: 'business' or 'calendar'."""
    if basis == "calendar":
        return max(0.0, (to_utc(end) - to_utc(start)).total_seconds())
    if basis == "business":
        return business_seconds_between(cfg, start, end)
    raise ValueError(f"unknown basis: {basis!r}")


def deadline_for(cfg, basis, start, allowed_seconds):
    """The moment the allowed time runs out on the chosen basis."""
    if basis == "calendar":
        return to_utc(start) + timedelta(seconds=allowed_seconds)
    if basis == "business":
        return add_business_seconds(cfg, start, allowed_seconds)
    raise ValueError(f"unknown basis: {basis!r}")


def evaluate_sla(cfg, created_at, target, now):
    """SLA clock for one ticket.

    target is {"target_minutes": number, "basis": "business" or "calendar"}.
    state is 'ok', 'warning' (warning fraction of the allowed time consumed) or 'breached'
    (all of the allowed time consumed, which is exactly when now reaches the deadline).
    """
    basis = target["basis"]
    allowed = float(target["target_minutes"]) * 60.0
    elapsed = elapsed_seconds(cfg, basis, created_at, now)
    fraction = cfg.data["sla"]["warning_fraction"]
    if elapsed >= allowed - EPSILON:
        state = "breached"
    elif elapsed >= allowed * fraction - EPSILON:
        state = "warning"
    else:
        state = "ok"
    return {
        "basis": basis,
        "target_minutes": target["target_minutes"],
        "allowed_seconds": allowed,
        "elapsed_seconds": elapsed,
        "remaining_seconds": allowed - elapsed,
        "consumed_fraction": elapsed / allowed,
        "warning_at": deadline_for(cfg, basis, created_at, allowed * fraction),
        "deadline": deadline_for(cfg, basis, created_at, allowed),
        "state": state,
    }