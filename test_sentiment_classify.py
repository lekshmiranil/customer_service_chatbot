import sys

from src.sentiment.classify import classify_message
from src.sentiment.history import apply_history
from src.sentiment.risk import detect_risks
from src.sentiment.tone import apply_tone, detect_language, notice_line, opening_line, profile_for

failures = 0


def check(label, condition):
    global failures
    if not condition:
        failures += 1
    print(("ok   " if condition else "FAIL ") + label)


CASES = [
    ("Thank you so much, this was very helpful", "positive"),
    ("Great service, thank you!", "positive"),
    ("Excellent, is the item still in stock?", "positive"),
    ("Thanks, it works now", "positive"),
    ("Where can I find my invoice?", "neutral"),
    ("My order has not arrived yet.", "neutral"),
    ("This is terrible service, I am very disappointed", "negative"),
    ("I am so frustrated, nobody is helping me!!", "frustrated"),
    ("Thanks, but it still doesn't work", "frustrated"),
    ("I need this immediately, it is urgent", "urgent"),
    ("Oh great, another delay. Thanks a lot.", "sarcastic"),
    ("Wow, excellent service, my parcel is delayed again", "sarcastic"),
    ("Thanks for nothing", "sarcastic"),
    ("यह बहुत खराब सर्विस है", "negative"),
    ("bahut kharab service, mai pareshan hoon", "negative"),
    ("വളരെ മോശം സർവീസ്", "negative"),
    ("मुझे तुरंत मदद चाहिए", "urgent"),
    ("mujhe jaldi madad chahiye", "urgent"),
    ("ഉടൻ സഹായം വേണം", "urgent"),
    ("वाह क्या सर्विस है, फिर से पैसे कट गए", "sarcastic"),
]
for text, expected in CASES:
    result = classify_message(text)
    check(f"label {expected}: {ascii(text[:40])}", result["label"] == expected)

result = classify_message("This is terrible service, I am very disappointed")
check("six score keys", set(result["scores"]) == {"positive", "neutral", "negative", "frustrated", "urgent", "sarcastic"})
check("confidence between 0 and 1", 0.0 <= result["confidence"] <= 1.0)
check("empty text is neutral", classify_message("")["label"] == "neutral")
check("None text is neutral", classify_message(None)["label"] == "neutral")

# history
neg = [{"negative_type": True}, {"negative_type": True}]
alone = apply_history(classify_message("Great, wonderful."), [])
check("praise alone stays positive", alone["label"] == "positive")
after = apply_history(classify_message("Great, wonderful."), neg)
check("praise after two negatives is sarcastic", after["label"] == "sarcastic" and after["negative_type"])
check("history note is recorded", bool(after["context_notes"]))
resolved = apply_history(classify_message("Great, the problem is solved"), neg)
check("a solved message is not sarcasm", resolved["label"] != "sarcastic")
boost = apply_history(classify_message("This is terrible"), neg)
check("repeated negatives raise frustration", "frustrated" in boost["flags"])

# risk
RISKS = [
    ("My account was hacked", ["account_compromise"]),
    ("Someone else has logged into my account without my permission", ["account_compromise"]),
    ("I was charged twice for the same order", ["duplicate_payment"]),
    ("There is a duplicate payment on my card", ["duplicate_payment"]),
    ("I will take legal action if this continues", ["legal_threat"]),
    ("I am consulting a lawyer about this", ["legal_threat"]),
    ("मेरा अकाउंट हैक हो गया है", ["account_compromise"]),
    ("mere paise do baar kat gaye", ["duplicate_payment"]),
    ("എനിക്ക് വക്കീലിനെ കാണേണ്ടി വരും", ["legal_threat"]),
    ("Where is my order?", []),
    ("What is the issue with my invoice?", []),
    ("Thank you for your courtesy", []),
]
for text, expected in RISKS:
    check(f"risk {expected}: {ascii(text[:40])}", detect_risks(text) == expected)

# tone
check("english detected", detect_language("Where is my order?") == "en")
check("hindi detected", detect_language("मुझे मदद चाहिए") == "hi")
check("malayalam detected", detect_language("സഹായം വേണം") == "ml")
check("roman hindi is treated as english", detect_language("mujhe madad chahiye") == "en")
policy = "Refunds are available within 30 days of delivery. [POL-REF-GL v2, Refund window]"
refusal = "I couldn't find a reliable answer to that in the documents available to you, so I won't guess."
for profile in ("empathy", "priority", "composed", "thanks"):
    for language in ("en", "hi", "ml"):
        opening = opening_line(profile, language)
        check(f"opening exists: {profile} {language}", bool(opening))
        combined = apply_tone(policy, opening)
        check(f"policy text unchanged: {profile} {language}", combined.endswith(policy) and combined.count(policy) == 1)
        check(f"refusal text unchanged: {profile} {language}", apply_tone(refusal, opening).endswith(refusal))
check("neutral has no opening", opening_line("neutral", "en") == "")
check("no opening leaves the text alone", apply_tone(policy, "") == policy)
check("profile for risk", profile_for(classify_message("Hello"), ["legal_threat"]) == "priority")
check("profile for sarcasm", profile_for(classify_message("Thanks for nothing")) == "composed")
check("notice lines exist", all(notice_line(k, l) for k in ("on_call", "next_day", "now") for l in ("en", "hi", "ml")))

print("failures:", failures)
sys.exit(1 if failures else 0)