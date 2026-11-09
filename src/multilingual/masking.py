"""Masks card numbers, phone numbers and e-mail addresses in customer text before it is stored.
Standard library only. A digit run that follows a letter, a digit or a hyphen is never masked, so order IDs such
as ORD-1234567890 are kept. Order IDs, product codes, dates and names are not masked here.
Known limits: a 10-digit number that starts with 6 to 9 and has no prefix looks like a phone number; 12-digit
government ID numbers are not masked."""
import re

EMAIL_TOKEN = "[REDACTED_EMAIL]"
CARD_TOKEN = "[REDACTED_CREDIT_CARD]"
PHONE_TOKEN = "[REDACTED_PHONE]"

_EMAIL_RE = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}", re.ASCII)
_CARD_RE = re.compile(r"(?<![\w-])\d(?:[ -]?\d){12,18}(?![\w-])", re.ASCII)
_INTL_RE = re.compile(r"(?<![\w-])\+\d{1,3}(?:[ -]?\d{2,5}){2,4}(?![\w-])", re.ASCII)
_MOBILE_RE = re.compile(r"(?<![\w-])(?:\+91[ -]?|91[ -]?|0)?[6-9]\d{4}[ -]?\d{5}(?![\w-])", re.ASCII)


def _intl(match):
    digits = sum(1 for char in match.group(0) if char.isdigit())
    return PHONE_TOKEN if digits >= 9 else match.group(0)


def mask(text):
    """Returns the text with e-mail addresses, card numbers and phone numbers replaced by tokens."""
    if text is None:
        return ""
    out = str(text)
    out = _EMAIL_RE.sub(EMAIL_TOKEN, out)
    out = _CARD_RE.sub(CARD_TOKEN, out)
    out = _INTL_RE.sub(_intl, out)
    out = _MOBILE_RE.sub(PHONE_TOKEN, out)
    return out