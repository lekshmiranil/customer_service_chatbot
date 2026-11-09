"""Checks for src\\rag\\dates_nl.py: which date a question refers to."""
import sys
from datetime import date

from src.rag.dates_nl import check_dates, parse_question_date

TODAY = date(2026, 10, 24)
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


def parse(question):
    return parse_question_date(question, TODAY)


def is_single(question, expected):
    intent = parse(question)
    return intent.kind == "historical" and intent.as_of == expected and intent.range_end is None


def is_period(question, start, end):
    intent = parse(question)
    return intent.kind == "historical" and intent.as_of == start and intent.range_end == end


check("plain question is current", parse("What is the refund window?").kind == "current")
check("current uses today", parse("What is the refund window?").as_of == TODAY)
check("today is current", parse("What is the policy today?").kind == "current")
check("ISO date", is_single("What was the refund window as of 2025-03-12?", date(2025, 3, 12)))
check("day month year", is_single("What was the refund window on 12 March 2025?", date(2025, 3, 12)))
check("ordinal day", is_single("refund policy on 12th March 2025", date(2025, 3, 12)))
check("day of month year", is_single("policy on 3rd of June 2025", date(2025, 6, 3)))
check("month day year", is_single("policy on March 12, 2025", date(2025, 3, 12)))
check("abbreviated month", is_single("policy on 5 Sep 2025", date(2025, 9, 5)))
check("sept spelling", is_single("policy on 5 sept 2025", date(2025, 9, 5)))
check("numeric day first", is_single("policy on 25/03/2025", date(2025, 3, 25)))
check("numeric month first when unambiguous", is_single("policy on 03/25/2025", date(2025, 3, 25)))
check("numeric same day and month", is_single("policy on 05/05/2025", date(2025, 5, 5)))
check("numeric ambiguous asks", parse("policy on 03/04/2025").kind == "ambiguous")
check("numeric impossible is unresolved", parse("policy on 31/02/2025").kind == "unresolved")
check("ISO impossible is unresolved", parse("policy on 2025-02-30").kind == "unresolved")
check("leap day accepted", is_single("policy on 29 February 2024", date(2024, 2, 29)))
check("non leap day rejected", parse("policy on 29 February 2025").kind == "unresolved")
check("yesterday", is_single("what was the policy yesterday", date(2026, 10, 23)))
check("day before yesterday", is_single("policy day before yesterday", date(2026, 10, 22)))
check("days ago", is_single("policy 3 days ago", date(2026, 10, 21)))
check("weeks ago", is_single("policy two weeks ago", date(2026, 10, 10)))
check("months ago", is_single("policy 2 months ago", date(2026, 8, 24)))
check("months ago clamps day", parse_question_date("policy 1 month ago", date(2026, 3, 31)).as_of == date(2026, 2, 28))
check("years ago", is_single("policy 2 years ago", date(2024, 10, 24)))
check("last month is a period", is_period("policy last month", date(2026, 9, 1), date(2026, 9, 30)))
check("last year is a period", is_period("policy last year", date(2025, 1, 1), date(2025, 12, 31)))
check("last week is a period", is_period("policy last week", date(2026, 10, 17), date(2026, 10, 23)))
check("month and year is a period", is_period("policy in March 2025", date(2025, 3, 1), date(2025, 3, 31)))
check("year alone is a period", is_period("policy in 2024", date(2024, 1, 1), date(2024, 12, 31)))
check("current month period ends today", is_period("policy in October 2026", date(2026, 10, 1), TODAY))
check("a year number without a lead word is ignored", parse("HomeHub X1 2024 refund").kind == "current")
check("future date is flagged", parse("policy on 1 January 2027").kind == "future")
check("future date gives a reason", "future" in parse("policy on 1 January 2027").reason)
check("future month is flagged", parse("policy in March 2027").kind == "future")
check("today's date written out is current", parse("policy on 2026-10-24").kind == "current")
check("history cue without date asks", parse("What was the policy when I bought it?").kind == "unresolved")
check("used to asks", parse("What used to be the refund window?").kind == "unresolved")
check("cue with a date is resolved", is_single("what used to be the policy on 2025-03-12", date(2025, 3, 12)))
check("day and month without year asks", parse("policy on 12 March").kind == "unresolved")
check("missing year reason mentions year", "year" in parse("policy on 12 March").reason)
check("two dates is ambiguous", parse("policy on 12 March 2025 and 1 June 2025").kind == "ambiguous")
check("same date twice is fine", is_single("policy on 2025-03-12 (12 March 2025)", date(2025, 3, 12)))
check("period check dates has two entries", len(check_dates(parse("policy in March 2025"))) == 2)
check("single date check dates has one entry", len(check_dates(parse("policy on 2025-03-12"))) == 1)
check("empty question is current", parse("").kind == "current")

print(f"checks: {total}, failed: {failures}")
sys.exit(1 if failures else 0)