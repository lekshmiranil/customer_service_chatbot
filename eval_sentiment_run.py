"""Task 5 evaluation: sarcasm, calm high-risk complaints, after-hours requests and simulated time changes.
Uses a temporary database, a fixed clock and no model. Writes eval_results_sentiment.md."""
import sys
from pathlib import Path

from sentiment_sim import fri, mon, new_db, outcome, run, sat, tue
from src.tickets.config import get_config

NEG = "This is terrible service, I am very upset"
URGENT_NEG = "This is urgent, my order is delayed and I am very upset"
PLAIN_NEG = "I am disappointed with the packaging of my order"
DUP = "Hello, I noticed my payment was charged twice. Could you please check?"


def E(escalations=(), queues=(), label=None, count=None):
    return {"escalations": sorted(escalations), "queues": sorted(queues), "label": label, "count": count}


SCENARIOS = [
    ("sarcasm-strong-phrase", "sarcasm", [(mon(10, 0), "msg", "Oh great, another delay. Thanks a lot.")], E(label="sarcastic")),
    ("sarcasm-praise-with-failure", "sarcasm", [(mon(10, 0), "msg", "Wow, excellent service, my parcel is delayed again")], E(label="sarcastic")),
    ("sarcasm-thanks-for-nothing", "sarcasm", [(mon(10, 0), "msg", "Thanks for nothing")], E(label="sarcastic")),
    ("sarcasm-hindi", "sarcasm", [(mon(10, 0), "msg", "वाह क्या सर्विस है, फिर से पैसे कट गए")], E(label="sarcastic")),
    ("sarcasm-with-risk", "sarcasm", [(mon(10, 0), "msg", "Great, another duplicate charge. Thanks.")],
     E(["high_risk:duplicate_payment"], ["priority_support"], "sarcastic")),
    ("sarcasm-from-history", "sarcasm",
     [(mon(10, 0), "msg", "This is terrible"), (mon(10, 2), "msg", "Still not working, I am fed up"), (mon(10, 4), "msg", "Great, wonderful.")],
     E(["repeated_negative"], ["priority_support"], "sarcastic")),
    ("genuine-praise-not-sarcasm", "sarcasm", [(mon(10, 0), "msg", "Great service, thank you!")], E(label="positive", count=0)),
    ("calm-duplicate-payment", "calm high-risk", [(mon(10, 0), "msg", DUP)], E(["high_risk:duplicate_payment"], ["priority_support"], "neutral")),
    ("calm-account-compromise", "calm high-risk",
     [(mon(10, 0), "msg", "Good morning. Someone else has logged into my account without my permission, please advise.")],
     E(["high_risk:account_compromise"], ["priority_support"], "neutral")),
    ("calm-legal-threat", "calm high-risk",
     [(mon(10, 0), "msg", "I would like to inform you that I will be consulting a lawyer regarding this matter.")],
     E(["high_risk:legal_threat"], ["priority_support"], "neutral")),
    ("calm-hindi-account", "calm high-risk", [(mon(10, 0), "msg", "मेरा अकाउंट हैक हो गया है")], E(["high_risk:account_compromise"], ["priority_support"])),
    ("calm-roman-hindi-duplicate", "calm high-risk", [(mon(10, 0), "msg", "mere paise do baar kat gaye")], E(["high_risk:duplicate_payment"], ["priority_support"])),
    ("calm-malayalam-legal", "calm high-risk", [(mon(10, 0), "msg", "എനിക്ക് വക്കീലിനെ കാണേണ്ടി വരും")], E(["high_risk:legal_threat"], ["priority_support"])),
    ("after-hours-urgent", "after hours", [(tue(20, 0), "msg", URGENT_NEG)], E([], ["on_call"], count=1)),
    ("after-hours-normal", "after hours", [(tue(20, 0), "msg", PLAIN_NEG)], E([], ["next_working_day"], count=1)),
    ("after-hours-weekend", "after hours", [(sat(11, 0), "msg", PLAIN_NEG)], E([], ["next_working_day"], count=1)),
    ("after-hours-plain-question", "after hours", [(tue(20, 0), "msg", "Where can I find my invoice?")], E(count=0)),
    ("after-hours-calm-high-risk", "after hours", [(tue(20, 0), "msg", DUP)], E(["high_risk:duplicate_payment"], ["on_call"], count=1)),
    ("after-hours-upgrade-to-urgent", "after hours", [(tue(20, 0), "msg", PLAIN_NEG), (tue(20, 5), "msg", URGENT_NEG)], E([], ["next_working_day", "on_call"], count=2)),
    ("business-hours-single-complaint", "after hours", [(mon(10, 0), "msg", PLAIN_NEG)], E(count=0)),
    ("timeout-before-15", "time change", [(mon(10, 0), "msg", NEG), (mon(10, 14), "tick", "")], E(count=0)),
    ("timeout-exactly-15", "time change", [(mon(10, 0), "msg", NEG), (mon(10, 15), "tick", "")], E(count=0)),
    ("timeout-after-16", "time change", [(mon(10, 0), "msg", NEG), (mon(10, 16), "tick", "")], E(["unresolved_timeout"], ["priority_support"], count=1)),
    ("timeout-only-once", "time change", [(mon(10, 0), "msg", NEG), (mon(10, 16), "tick", ""), (mon(11, 0), "tick", ""), (mon(15, 0), "tick", "")], E(["unresolved_timeout"], ["priority_support"], count=1)),
    ("timeout-human-reply", "time change", [(mon(10, 0), "msg", NEG), (mon(10, 5), "human", ""), (mon(10, 40), "tick", "")], E(count=0)),
    ("timeout-solved", "time change", [(mon(10, 0), "msg", NEG), (mon(10, 5), "msg", "Thanks, it works now"), (mon(10, 40), "tick", "")], E(count=0)),
    ("timeout-crosses-closing", "time change", [(fri(17, 50), "msg", NEG), (fri(18, 10), "tick", "")], E(["unresolved_timeout"], ["next_working_day"], count=1)),
    ("timeout-urgent-crosses-closing", "time change",
     [(fri(17, 50), "msg", "This is terrible and urgent, please fix it immediately"), (fri(18, 10), "tick", "")], E(["unresolved_timeout"], ["on_call"], count=1)),
    ("timeout-weekend", "time change", [(sat(11, 0), "msg", NEG), (sat(11, 20), "tick", "")], E(["unresolved_timeout"], ["next_working_day"], count=2)),
    ("repeated-three", "repeated negative", [(mon(10, 0), "msg", NEG), (mon(10, 3), "msg", NEG), (mon(10, 6), "msg", NEG)], E(["repeated_negative"], ["priority_support"], count=1)),
    ("repeated-two-only", "repeated negative", [(mon(10, 0), "msg", NEG), (mon(10, 3), "msg", NEG)], E(count=0)),
    ("repeated-reset-by-thanks", "repeated negative",
     [(mon(10, 0), "msg", NEG), (mon(10, 1), "msg", NEG), (mon(10, 2), "msg", "Thanks, it works now"), (mon(10, 3), "msg", NEG)], E(count=0)),
    ("repeated-after-hours", "repeated negative", [(tue(20, 0), "msg", PLAIN_NEG), (tue(20, 1), "msg", PLAIN_NEG), (tue(20, 2), "msg", PLAIN_NEG)],
     E(["repeated_negative"], ["next_working_day"], count=2)),
    ("repeated-and-timeout", "repeated negative", [(mon(10, 0), "msg", NEG), (mon(10, 8), "msg", NEG), (mon(10, 16), "msg", NEG)],
     E(["repeated_negative", "unresolved_timeout"], ["priority_support"], count=2)),
]


def evaluate(name, steps, expected):
    db, conversation = new_db(), "eval-" + name
    results = run(db, conversation, steps, get_config())
    o = outcome(db, conversation)
    problems = []
    if o["escalations"] != expected["escalations"]:
        problems.append(f"escalations {o['escalations']}")
    if o["queues"] != expected["queues"]:
        problems.append(f"queues {o['queues']}")
    if expected["label"] and (not results or results[-1]["label"] != expected["label"]):
        problems.append(f"label {results[-1]['label'] if results else None}")
    if expected["count"] is not None and o["count"] != expected["count"]:
        problems.append(f"count {o['count']}")
    for row in o["rows"]:
        if not (row["reason"] and row["condition_code"] and row["summary"]):
            problems.append("missing reason, condition or summary")
            break
    return problems, o


lines = []
failed = 0
for name, category, steps, expected in SCENARIOS:
    problems, o = evaluate(name, steps, expected)
    ok = not problems
    failed += 0 if ok else 1
    print(("ok   " if ok else "FAIL ") + name + ("" if ok else ": " + "; ".join(problems)))
    wanted = f"{expected['escalations']} / {expected['queues']}" + (f" / {expected['label']}" if expected["label"] else "")
    actual = f"{o['escalations']} / {o['queues']}" + ("" if ok else " (" + "; ".join(problems) + ")")
    lines.append(f"| {name} | {category} | {wanted} | {actual} | {'yes' if ok else 'no'} |")

report = [
    "# Task 5 evaluation: sentiment, risk and escalation",
    "",
    f"Fixed clock in October 2026, Indian business hours from the ticket configuration. No model and no network were used. "
    f"Scenarios: {len(SCENARIOS)}. Passed: {len(SCENARIOS) - failed}.",
    "",
    "| Scenario | Category | Expected (escalations / queues / label) | Actual | Pass |",
    "|---|---|---|---|---|",
] + lines
Path("eval_results_sentiment.md").write_text("\n".join(report) + "\n", encoding="utf-8")
print("scenarios:", len(SCENARIOS), "failed:", failed)
sys.exit(1 if failed else 0)