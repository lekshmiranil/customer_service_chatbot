"""Checks for src\\tickets\\masking.py, extract.py and priority.py (temporary files only)."""
import copy
import json
import sys
import tempfile
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from src.tickets.business_time import add_business_seconds
from src.tickets.config import DEFAULT_CONFIG, get_config, reset_cache
from src.tickets.extract import (
    extract_ticket_fields,
    follow_up_questions,
    follow_up_text,
    merge_fields,
    missing_mandatory,
)
from src.tickets.masking import mask_email, mask_phone, mask_text
from src.tickets.priority import LEVELS, compute_priority, queue_sort_key

IST = ZoneInfo("Asia/Kolkata")
total = 0
problems = 0


def check(name, got, expected):
    global total, problems
    total += 1
    if got == expected:
        print(f"ok   {name}")
    else:
        problems += 1
        print(f"FAIL {name}: got {got!r}, expected {expected!r}")


def raises(name, exception_type, function):
    global total, problems
    total += 1
    try:
        function()
    except exception_type:
        print(f"ok   {name}")
    except Exception as error:
        problems += 1
        print(f"FAIL {name}: raised {type(error).__name__} instead of {exception_type.__name__}")
    else:
        problems += 1
        print(f"FAIL {name}: nothing was raised")


def at(year, month, day, hour=0, minute=0):
    return datetime(year, month, day, hour, minute, tzinfo=IST)


def write_config(folder, name, data):
    path = Path(folder) / name
    path.write_text(json.dumps(data, indent=2), encoding="utf-8")
    return path


def turn(role, text, **extra):
    return {"role": role, "text": text, "at": "2026-10-21T10:00:00+05:30", **extra}


def value(result, name):
    field = result["fields"].get(name)
    return field["value"] if field else None


def source(result, name):
    field = result["fields"].get(name)
    return field["source"] if field else None


reset_cache()

# ------------------------------------------------------------------ masking
check("email masked", mask_text("Please write to jane.doe@example.com"), "Please write to j***@example.com")
check("mask_email direct", mask_email("a@b.co"), "a***@b.co")
masked_phone = mask_text("Call +91 98765 43210 now")
check("phone keeps last four", "3210" in masked_phone, True)
check("phone hides the rest", "98765" in masked_phone, False)
check("mask_phone direct", mask_phone("+91 98765 43210"), "+** ***** *3210")
masked_card = mask_text("my card is 4111 1111 1111 1111 expiring soon")
check("card shows last four only", "[CARD ending 1111]" in masked_card, True)
check("card number hidden", "4111 1111" in masked_card, False)
masked_password = mask_text("my password is hunter2xyz")
check("password hidden", "hunter2xyz" in masked_password, False)
check("password label kept", "password is [REDACTED]" in masked_password, True)
check("password word alone is untouched", mask_text("password reset is not working"), "password reset is not working")
check("one-time code hidden", "482913" in mask_text("my OTP is 482913"), False)
check("cvv hidden", "123" in mask_text("cvv 123"), False)
check("order and ticket ids kept", mask_text("order 78231 and ticket TKT-000123"), "order 78231 and ticket TKT-000123")
check("ten-digit order id kept", mask_text("order 1234567890 is late"), "order 1234567890 is late")
check("date is not a phone number", mask_text("on 2026-10-21 10:30 it broke"), "on 2026-10-21 10:30 it broke")
check("api key hidden", "sk-abcdef" in mask_text("my key is sk-abcdef1234567890abcd ok"), False)
check("long token hidden", "9f86d081884c7d659a2f" in mask_text("hash 9f86d081884c7d659a2feaa0c55ad015a3bf4f1b"), False)
check("government style id hidden", "1234 5678 9012" in mask_text("id 1234 5678 9012"), False)
sample = ("Mail jane.doe@example.com, call +91 98765 43210, card 4111 1111 1111 1111, "
          "password is hunter2xyz, order 78231")
check("masking is idempotent", mask_text(mask_text(sample)), mask_text(sample))
check("masking keeps the order id", "order 78231" in mask_text(sample), True)
check("None becomes empty text", mask_text(None), "")

with tempfile.TemporaryDirectory() as tmp:
    base = copy.deepcopy(DEFAULT_CONFIG)
    base["holidays"] = [{"date": "2026-10-22", "name": "Test holiday"}]
    cfg = get_config(write_config(tmp, "base.json", base))

    # -------------------------------------------------------------- extraction
    conv_a = [
        turn("customer", "Hi, my name is Priya Nair. I am very upset, my order 78231 has not arrived "
                         "and I was charged twice for Rs 4500!!"),
        turn("bot", "Sorry about that. Your reference order 99999 is noted."),
        turn("customer", "You can reach me at priya.nair@example.com or +91 98765 43210. Please email me. "
                         "The product is a Bluetooth speaker. Error code E-502 appeared at checkout.",
             attachment={"file_id": "f1", "status": "needs_better_file", "kind": "image"}),
    ]
    a = extract_ticket_fields(cfg, conv_a)
    check("A name", value(a, "customer_name"), "Priya Nair")
    check("A name is stated", source(a, "customer_name"), "stated")
    check("A order id ignores bot text", value(a, "order_id"), "78231")
    check("A no other orders", "other_order_ids" in a["fields"], False)
    check("A email", value(a, "contact_email"), "priya.nair@example.com")
    check("A phone", value(a, "contact_phone"), "+91 98765 43210")
    check("A stated contact method", (value(a, "contact_method"), source(a, "contact_method")), ("email", "stated"))
    check("A product", value(a, "product"), "Bluetooth speaker")
    check("A error codes", value(a, "error_codes"), ["E-502"])
    check("A amounts", value(a, "amounts"), ["Rs 4500"])
    check("A description is the first message", value(a, "issue_description").startswith("Hi, my name is Priya"), True)
    check("A category (tie broken in the documented order)", (value(a, "issue_category"), source(a, "issue_category")),
          ("payment", "inferred"))
    check("A severity", (value(a, "severity"), source(a, "severity")), ("high", "inferred"))
    check("A sentiment", value(a, "sentiment"), "very_negative")
    check("A impact", value(a, "impact"), "single_customer")
    check("A inferred fields explain themselves", "charged twice" in a["fields"]["severity"]["reason"], True)
    check("A nothing missing", missing_mandatory(cfg, a["fields"]), [])
    check("A evidence types", [item["type"] for item in a["evidence"]], ["message", "message", "attachment"])
    leaked = [item for item in a["evidence"]
              if item["type"] == "message" and ("priya.nair@example.com" in item["excerpt"] or "98765" in item["excerpt"])]
    check("A evidence excerpts are masked", leaked, [])
    check("A attachment evidence has no file content", a["evidence"][2]["file_id"], "f1")

    b = extract_ticket_fields(cfg, [turn("customer", "Hello, my package never arrived")])
    check("B category", value(b, "issue_category"), "delivery")
    check("B severity", value(b, "severity"), "high")
    check("B no order id invented", value(b, "order_id"), None)
    check("B no contact invented", (value(b, "contact_email"), value(b, "contact_phone")), (None, None))
    check("B missing fields", missing_mandatory(cfg, b["fields"]), ["order_id", "contact"])

    c = extract_ticket_fields(cfg, [turn("customer", "I have a question about something else, please advise me")])
    check("C general category", value(c, "issue_category"), "general")
    check("C low severity", value(c, "severity"), "low")
    check("C neutral sentiment", value(c, "sentiment"), "neutral")
    check("C general needs only contact", missing_mandatory(cfg, c["fields"]), ["contact"])

    d = extract_ticket_fields(cfg, [turn("customer", "My order 111111 and order 222222 are both late please check")])
    check("D main order", value(d, "order_id"), "111111")
    check("D other order", value(d, "other_order_ids"), ["222222"])
    check("D two orders mean wider impact", value(d, "impact"), "multiple_orders")

    e = extract_ticket_fields(cfg, [
        turn("customer", "My order 11111 is late and I need some help please"),
        turn("bot", "Could you confirm the order number?"),
        turn("customer", "Sorry, the order number is 22222"),
    ])
    check("E corrected order id wins", value(e, "order_id"), "22222")
    check("E earlier order id is kept aside", value(e, "other_order_ids"), ["11111"])

    f = extract_ticket_fields(cfg, [turn("customer", "order 1234567890 is late, call me on 9876543210 please")])
    check("F ten-digit order id", value(f, "order_id"), "1234567890")
    check("F phone is not the order id", value(f, "contact_phone"), "9876543210")
    check("F call me", value(f, "contact_method"), "phone")

    g = extract_ticket_fields(cfg, [turn("customer", "My order 55555 is late, mail is jo@example.com")])
    check("G single contact detail gives an inferred method", (value(g, "contact_method"), source(g, "contact_method")),
          ("email", "inferred"))
    check("H no customer text gives no fields", extract_ticket_fields(cfg, [turn("bot", "Hello")])["fields"], {})

    # ----------------------------------------------------------- merge and questions
    stored = {
        "order_id": {"value": "11111", "source": "stated", "turn": 0, "reason": None},
        "customer_name": {"value": "Ann", "source": "stated", "turn": 0, "reason": None},
        "severity": {"value": "low", "source": "inferred", "turn": None, "reason": "x"},
        "contact_method": {"value": "phone", "source": "stated", "turn": 0, "reason": None},
        "error_codes": {"value": ["E1"], "source": "stated", "turn": 0, "reason": None},
        "issue_description": {"value": "first words", "source": "stated", "turn": 0, "reason": None},
    }
    fresh = {
        "order_id": {"value": "22222", "source": "stated", "turn": 2, "reason": None},
        "severity": {"value": "high", "source": "inferred", "turn": None, "reason": "y"},
        "contact_method": {"value": "email", "source": "inferred", "turn": None, "reason": "z"},
        "error_codes": {"value": ["E2"], "source": "stated", "turn": 2, "reason": None},
        "issue_description": {"value": "later words", "source": "stated", "turn": 2, "reason": None},
        "product": {"value": "Speaker", "source": "stated", "turn": 2, "reason": None},
    }
    merged = merge_fields(stored, fresh)
    check("merge: newer stated value wins", merged["order_id"]["value"], "22222")
    check("merge: old value is kept in history", merged["order_id"]["previous_values"], ["11111"])
    check("merge: missing new value keeps the old one", merged["customer_name"]["value"], "Ann")
    check("merge: inferred is recomputed", merged["severity"]["value"], "high")
    check("merge: stated beats inferred", merged["contact_method"]["value"], "phone")
    check("merge: lists are combined", merged["error_codes"]["value"], ["E1", "E2"])
    check("merge: description keeps the first wording", merged["issue_description"]["value"], "first words")
    check("merge: new fields are added", merged["product"]["value"], "Speaker")
    check("merge does not change its input", stored["order_id"]["value"], "11111")

    check("questions for two missing fields", [q["field"] for q in follow_up_questions(["order_id", "contact"])],
          ["order_id", "contact"])
    check("questions skip fields asked twice",
          [q["field"] for q in follow_up_questions(["order_id", "contact"], {"order_id": 2})], ["contact"])
    check("no questions when all were asked twice",
          follow_up_questions(["order_id", "contact"], {"order_id": 2, "contact": 2}), [])
    check("questions are limited and ordered",
          [q["field"] for q in follow_up_questions(["customer_name", "order_id", "issue_description"])],
          ["issue_description", "order_id"])
    check("follow-up text mentions the order number",
          "order number" in follow_up_text(follow_up_questions(["order_id"])), True)
    check("follow-up text is empty with no questions", follow_up_text([]), "")

    # ----------------------------------------------------------------- priority
    created = at(2026, 10, 21, 10)

    def priority(config, severity, impact, sentiment, now, category="general"):
        return compute_priority(config, severity=severity, impact=impact, sentiment=sentiment,
                                issue_category=category, created_at=created, now=now)

    p1 = priority(cfg, "low", "single_customer", "very_negative", created)
    check("sentiment alone cannot raise a low issue", p1["priority"], "low")
    check("sentiment points are still recorded", p1["points"]["sentiment"], 10)

    p2 = priority(cfg, "critical", "single_customer", "neutral", created)
    check("critical severity gives at least high", p2["priority"], "high")
    p3 = priority(cfg, "critical", "widespread", "neutral", created)
    check("critical and widespread: priority", p3["priority"], "high")
    check("critical and widespread: sla class", p3["sla_class"], "critical")
    check("critical sla class uses the calendar clock", p3["sla_target"]["basis"], "calendar")
    p3b = priority(cfg, "critical", "widespread", "very_negative", created)
    check("sentiment can lift one level", p3b["priority"], "critical")

    p4 = priority(cfg, "low", "single_customer", "neutral", at(2026, 11, 11, 10))
    check("breached sla forces high", p4["priority"], "high")
    check("breach is reported", p4["sla"]["state"], "breached")
    check("breach floor is recorded", "sla_breached_floor" in p4["rules_applied"], True)

    p5a = priority(cfg, "medium", "single_customer", "neutral", created, "order")
    check("medium severity alone stays low", p5a["priority"], "low")
    p5b = priority(cfg, "medium", "single_customer", "neutral", at(2026, 10, 21, 15), "order")
    check("waiting time lifts it to medium", p5b["priority"], "medium")
    check("waiting points", p5b["points"]["waiting"], 5)

    warning_moment = add_business_seconds(cfg, created, 48600)
    check("warning moment skips the holiday", warning_moment, at(2026, 10, 23, 14, 30))
    p6 = priority(cfg, "medium", "multiple_orders", "neutral", warning_moment, "order")
    check("75 percent warning state", p6["sla"]["state"], "warning")
    check("75 percent sla points", p6["points"]["sla"], 12)
    check("waiting points at 13.5 working hours", p6["points"]["waiting"], 5)
    check("warning priority", p6["priority"], "medium")
    check("reasons explain every factor", len(p6["reasons"]) >= 6, True)
    check("priority is deterministic", priority(cfg, "medium", "multiple_orders", "neutral", warning_moment, "order"), p6)

    live_path = write_config(tmp, "live.json", base)
    before = priority(get_config(live_path), "medium", "multiple_orders", "neutral", warning_moment, "order")
    changed = copy.deepcopy(base)
    changed["sla"]["policies"]["medium"]["target_minutes"] = 600
    write_config(tmp, "live.json", changed)
    after = priority(get_config(live_path), "medium", "multiple_orders", "neutral", warning_moment, "order")
    check("runtime change: before", (before["sla"]["state"], before["priority"]), ("warning", "medium"))
    check("runtime change: after", (after["sla"]["state"], after["priority"]), ("breached", "high"))

    capped = copy.deepcopy(base)
    capped["priority"]["sentiment_points"]["very_negative"] = 50
    capped_cfg = get_config(write_config(tmp, "capped.json", capped))
    p8 = priority(capped_cfg, "low", "single_customer", "very_negative", created)
    check("sentiment cap limits the raise to one level", p8["priority"], "medium")
    check("sentiment cap is recorded", "sentiment_cap" in p8["rules_applied"], True)

    raises("unknown severity is refused", ValueError, lambda: priority(cfg, "catastrophic", "single_customer", "neutral", created))
    p12 = priority(cfg, "low", "mystery", "neutral", created)
    check("unknown impact counts zero", p12["points"]["impact"], 0)
    check("unknown impact is explained", any("not in the configured table" in r for r in p12["reasons"]), True)
    check("levels are ordered", LEVELS, ("low", "medium", "high", "critical"))

    queue = [
        ("low", 10, "2026-10-21T04:30:00+00:00", "T-3"),
        ("high", 50, "2026-10-21T04:35:00+00:00", "T-2"),
        ("high", 50, "2026-10-21T04:30:00+00:00", "T-1"),
        ("critical", 5, "2026-10-21T05:00:00+00:00", "T-0"),
    ]
    ordered = [item[3] for item in sorted(queue, key=lambda item: queue_sort_key(*item))]
    check("queue order: priority, score, age, id", ordered, ["T-0", "T-1", "T-2", "T-3"])

print(f"checks run: {total}, problems: {problems}")
sys.exit(1 if problems else 0)