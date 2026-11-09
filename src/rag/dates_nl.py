"""Works out which date a customer's question is about.

Result kinds:
  current     no date in the question (or the date is today): use policies in force today
  historical  one date, or a period (range_end set): use policies in force then
  future      the question names a date after today
  unresolved  the question is historical but has no usable date, or part of a date is missing
  ambiguous   the question holds two or more dates, or a date that can be read two ways
For unresolved, ambiguous and future the reason field holds a message that can be shown to the customer.
"""
import calendar
import os
import re
from dataclasses import dataclass
from datetime import date, datetime, timedelta

MONTHS = {
    "january": 1, "jan": 1, "february": 2, "feb": 2, "march": 3, "mar": 3,
    "april": 4, "apr": 4, "may": 5, "june": 6, "jun": 6, "july": 7, "jul": 7,
    "august": 8, "aug": 8, "september": 9, "sept": 9, "sep": 9, "october": 10,
    "oct": 10, "november": 11, "nov": 11, "december": 12, "dec": 12,
}
_MONTH = "|".join(sorted(MONTHS, key=len, reverse=True))
_NUMBER_WORDS = {
    "a": 1, "an": 1, "one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6,
    "seven": 7, "eight": 8, "nine": 9, "ten": 10, "eleven": 11, "twelve": 12,
}
_NUM = r"(\d{1,3}|an?|one|two|three|four|five|six|seven|eight|nine|ten|eleven|twelve)"
_LEAD = r"(?:in|during|throughout|back in|for)"

_PATTERNS = [
    ("iso", re.compile(r"\b(\d{4})-(\d{2})-(\d{2})\b")),
    ("dmy_text", re.compile(rf"\b(\d{{1,2}})(?:st|nd|rd|th)?\s+(?:of\s+)?({_MONTH})\.?,?\s+(\d{{4}})\b")),
    ("mdy_text", re.compile(rf"\b({_MONTH})\.?\s+(\d{{1,2}})(?:st|nd|rd|th)?,?\s+(\d{{4}})\b")),
    ("numeric", re.compile(r"\b(\d{1,2})[/.-](\d{1,2})[/.-](\d{4})\b")),
    ("month_year", re.compile(rf"\b{_LEAD}\s+({_MONTH})\.?,?\s+(\d{{4}})\b")),
    ("year_only", re.compile(rf"\b{_LEAD}\s+(\d{{4}})\b")),
    ("day_month_no_year", re.compile(rf"\b(\d{{1,2}})(?:st|nd|rd|th)?\s+(?:of\s+)?({_MONTH})\b")),
    ("day_before_yesterday", re.compile(r"\bday before yesterday\b")),
    ("yesterday", re.compile(r"\byesterday\b")),
    ("ago", re.compile(rf"\b{_NUM}\s+(day|week|month|year)s?\s+ago\b")),
    ("last_period", re.compile(r"\blast\s+(week|month|year)\b")),
]

_HISTORICAL_CUES = re.compile(
    r"\b(used to|previously|back then|in the past|at that time|at the time of|at the time i|"
    r"when i (?:bought|purchased|ordered|signed up|subscribed|registered|joined)|"
    r"earlier version|older version|old policy|previous policy|former policy|"
    r"before the (?:change|update))\b"
)


@dataclass(frozen=True)
class DateIntent:
    kind: str
    as_of: object = None      # date, or None when unresolved/ambiguous
    range_end: object = None  # last day of a period, or None for a single date
    matched: str = ""
    reason: str = ""

    @property
    def usable(self):
        return self.kind in ("current", "historical")


def get_today():
    """Today in India. RAG_TODAY (YYYY-MM-DD) overrides it for demos and tests."""
    forced = os.environ.get("RAG_TODAY", "").strip()
    if forced:
        return date.fromisoformat(forced)
    try:
        from zoneinfo import ZoneInfo
        return datetime.now(ZoneInfo("Asia/Kolkata")).date()
    except Exception:
        return date.today()


def check_dates(intent):
    """The dates a policy lookup must be evaluated on (two dates for a period)."""
    dates = [intent.as_of]
    if intent.range_end and intent.range_end != intent.as_of:
        dates.append(intent.range_end)
    return dates


def _add_months(day, months):
    index = day.year * 12 + (day.month - 1) + months
    year, month = divmod(index, 12)
    month += 1
    return date(year, month, min(day.day, calendar.monthrange(year, month)[1]))


def _real_date(year, month, day):
    try:
        return date(year, month, day)
    except ValueError:
        return None


def _span(match):
    return match.start(), match.end()


def _candidate(name, match, today):
    """Returns (start, end, ambiguous_msg, invalid_msg, missing_msg)."""
    text = match.group(0)
    g = match.groups()
    if name == "iso":
        d = _real_date(int(g[0]), int(g[1]), int(g[2]))
        return (d, d, None, None if d else f"'{text}' is not a real calendar date.", None)
    if name == "dmy_text":
        d = _real_date(int(g[2]), MONTHS[g[1]], int(g[0]))
        return (d, d, None, None if d else f"'{text}' is not a real calendar date.", None)
    if name == "mdy_text":
        d = _real_date(int(g[2]), MONTHS[g[0]], int(g[1]))
        return (d, d, None, None if d else f"'{text}' is not a real calendar date.", None)
    if name == "numeric":
        first, second, year = int(g[0]), int(g[1]), int(g[2])
        if first > 12 and second <= 12:
            day, month = first, second
        elif second > 12 and first <= 12:
            day, month = second, first
        elif first <= 12 and second <= 12:
            if first != second:
                return (None, None, f"'{text}' could be day/month or month/day.", None, None)
            day, month = first, second
        else:
            return (None, None, None, f"'{text}' is not a real calendar date.", None)
        d = _real_date(year, month, day)
        return (d, d, None, None if d else f"'{text}' is not a real calendar date.", None)
    if name == "month_year":
        month, year = MONTHS[g[0]], int(g[1])
        return (date(year, month, 1), date(year, month, calendar.monthrange(year, month)[1]), None, None, None)
    if name == "year_only":
        year = int(g[0])
        if 1990 <= year <= 2100:
            return (date(year, 1, 1), date(year, 12, 31), None, None, None)
        return None
    if name == "day_month_no_year":
        return (None, None, None, None, f"'{text}' has no year.")
    if name == "day_before_yesterday":
        d = today - timedelta(days=2)
        return (d, d, None, None, None)
    if name == "yesterday":
        d = today - timedelta(days=1)
        return (d, d, None, None, None)
    if name == "ago":
        raw, unit = g
        count = int(raw) if raw.isdigit() else _NUMBER_WORDS[raw]
        if unit == "day":
            d = today - timedelta(days=count)
        elif unit == "week":
            d = today - timedelta(weeks=count)
        elif unit == "month":
            d = _add_months(today, -count)
        else:
            d = _add_months(today, -12 * count)
        return (d, d, None, None, None)
    if name == "last_period":
        unit = g[0]
        if unit == "week":
            return (today - timedelta(days=7), today - timedelta(days=1), None, None, None)
        if unit == "month":
            first = _add_months(today.replace(day=1), -1)
            return (first, first.replace(day=calendar.monthrange(first.year, first.month)[1]), None, None, None)
        return (date(today.year - 1, 1, 1), date(today.year - 1, 12, 31), None, None, None)
    return None


def parse_question_date(question, today=None):
    today = today or get_today()
    working = (question or "").lower()
    found = []  # (start, end, matched text)
    for name, pattern in _PATTERNS:
        for match in list(pattern.finditer(working)):
            result = _candidate(name, match, today)
            a, b = _span(match)
            if result is None:
                continue
            working = working[:a] + " " * (b - a) + working[b:]
            start, end, ambiguous, invalid, missing = result
            if ambiguous:
                return DateIntent("ambiguous", matched=match.group(0), reason=(
                    f"{ambiguous} Please give the date as YYYY-MM-DD, for example 2025-03-12."))
            if invalid:
                return DateIntent("unresolved", matched=match.group(0), reason=(
                    f"{invalid} Please give the date again as YYYY-MM-DD."))
            if missing:
                return DateIntent("unresolved", matched=match.group(0), reason=(
                    f"{missing} Which year do you mean? Please give the full date, for example 2025-03-12."))
            found.append((start, end, match.group(0)))

    distinct = sorted({(s, e) for s, e, _ in found})
    if len(distinct) > 1:
        return DateIntent("ambiguous", matched="; ".join(t for _, _, t in found), reason=(
            "Your question mentions more than one date. Which single date should I use for the policy?"))
    if len(distinct) == 1:
        start, end, text = found[0]
        if start > today:
            return DateIntent("future", as_of=start, matched=text, reason=(
                "That date is in the future. I can only answer from policies that are in force today "
                "or were in force on a past date."))
        if end >= today:
            end = today
        if start == end == today:
            return DateIntent("current", as_of=today, matched=text)
        return DateIntent("historical", as_of=start, range_end=None if start == end else end, matched=text)

    if _HISTORICAL_CUES.search(working):
        return DateIntent("unresolved", reason=(
            "That sounds like a question about an earlier policy. On which date should I look? "
            "Please give it as YYYY-MM-DD, for example 2025-03-12."))
    return DateIntent("current", as_of=today)