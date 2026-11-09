"""Masking for ticket text, handoff summaries and logs (Task 3).

mask_text() redacts what a support agent does not need: secrets, one-time codes,
card numbers (last four digits kept), government-style IDs, bank account numbers,
email addresses (first letter and domain kept) and phone numbers (last four digits
kept). Order numbers and ticket IDs are left alone because agents need them.
mask_text() is idempotent: masking already-masked text changes nothing.
"""
import re

EMAIL_RE = re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b")
PHONE_RE = re.compile(r"(?<!\w)\+?\d[\d\s().-]{8,16}\d(?!\w)")
DATE_LIKE_RE = re.compile(r"^\+?(?:\d{4}-\d{1,2}-\d{1,2}|\d{1,2}[/.-]\d{1,2}[/.-]\d{2,4})")
CARD_RE = re.compile(r"\b(?:\d[ -]?){12,18}\d\b")
GOV_ID_RES = (
    re.compile(r"\b\d{4}\s\d{4}\s\d{4}\b"),
    re.compile(r"\b\d{3}-\d{2}-\d{4}\b"),
)
BEARER_RE = re.compile(r"(?i)\bbearer\s+[A-Za-z0-9._~+/=-]{8,}")
SECRET_ASSIGN_RE = re.compile(
    r"(?i)\b(password|passwd|pwd|passcode|secret|token|api[_ -]?key|access[_ -]?key|authorization)"
    r"(\s*(?:is|=|:)\s*)\S+"
)
SECRET_CODE_RE = re.compile(
    r"(?i)\b(cvv2?|cvc|pin|otp|one[- ]time (?:code|password)|verification code|security code)"
    r"(\W{0,3}(?:is\s+)?[:=]?\s*)\d{3,8}\b"
)
KEY_LIKE_RE = re.compile(r"\b(?:sk|pk|rk|api|key|tok|secret)[-_][A-Za-z0-9_-]{12,}\b")
LONG_TOKEN_RE = re.compile(r"\b[A-Za-z0-9_-]{32,}\b")
ACCOUNT_RE = re.compile(
    r"(?i)\b(account\s*(?:number|no\.?)|a/c(?:\s*no\.?)?|iban)\s*[:#]?\s*(?:is\s+)?"
    r"(\d[\d -]{6,32}\d|[A-Za-z]{2}\d{2}[A-Za-z0-9]{10,30})"
)


def _after_reference(text, start):
    """True when the digits follow the word order or ticket, so they are an ID, not a phone or card."""
    before = text[max(0, start - 15):start].lower()
    return "order" in before or "ticket" in before or "tkt" in before


def mask_email(value):
    local, _, domain = value.partition("@")
    return (local[:1] or "*") + "***@" + domain


def mask_phone(value):
    """Replaces every digit except the last four with *, keeping separators."""
    total = sum(1 for ch in value if ch.isdigit())
    seen = 0
    out = []
    for ch in value:
        if ch.isdigit():
            seen += 1
            out.append(ch if seen > total - 4 else "*")
        else:
            out.append(ch)
    return "".join(out)


def _sensitive_number_spans(text):
    """Spans of card-like and government-ID-like numbers, which are never phone numbers."""
    spans = []
    for match in CARD_RE.finditer(text):
        digits = re.sub(r"\D", "", match.group())
        if 13 <= len(digits) <= 19:
            spans.append((match.start(), match.end()))
    for pattern in GOV_ID_RES:
        spans.extend((match.start(), match.end()) for match in pattern.finditer(text))
    return spans


def find_phone_spans(text, ignore_spans=()):
    """(start, end) of phone-number-like text: 10 to 13 digits, not a date, not an order or ticket ID,
    and not part of a card or government-style ID number."""
    blocked = list(ignore_spans) + _sensitive_number_spans(text)
    spans = []
    for match in PHONE_RE.finditer(text):
        candidate = match.group()
        digits = re.sub(r"\D", "", candidate)
        if not 10 <= len(digits) <= 13:
            continue
        if DATE_LIKE_RE.match(candidate):
            continue
        if _after_reference(text, match.start()):
            continue
        if any(match.start() < end and start < match.end() for start, end in blocked):
            continue
        spans.append((match.start(), match.end()))
    return spans


def _mask_cards(text):
    def replace(match):
        digits = re.sub(r"\D", "", match.group())
        if 13 <= len(digits) <= 19 and not _after_reference(text, match.start()):
            return f"[CARD ending {digits[-4:]}]"
        return match.group()

    return CARD_RE.sub(replace, text)


def _mask_government_ids(text):
    for pattern in GOV_ID_RES:
        def replace(match, _text=text):
            if _after_reference(_text, match.start()):
                return match.group()
            return "[REDACTED_ID]"

        text = pattern.sub(replace, text)
    return text


def mask_text(text):
    """Returns the text with sensitive values masked; never raises on odd input."""
    if text is None:
        return ""
    text = str(text)
    text = BEARER_RE.sub("Bearer [REDACTED]", text)
    text = SECRET_ASSIGN_RE.sub(lambda m: f"{m.group(1)}{m.group(2)}[REDACTED]", text)
    text = SECRET_CODE_RE.sub(lambda m: f"{m.group(1)} [REDACTED]", text)
    text = KEY_LIKE_RE.sub("[REDACTED_KEY]", text)
    text = LONG_TOKEN_RE.sub("[REDACTED_TOKEN]", text)
    text = _mask_cards(text)
    text = _mask_government_ids(text)
    text = ACCOUNT_RE.sub(lambda m: f"{m.group(1)} [REDACTED_ACCOUNT]", text)
    text = EMAIL_RE.sub(lambda m: mask_email(m.group()), text)
    for start, end in reversed(find_phone_spans(text)):
        text = text[:start] + mask_phone(text[start:end]) + text[end:]
    return text