"""Comparison of the customer's message with the evidence read from a document.

Reads the details a customer states in a message (order numbers, dates, amounts,
error codes), checks each one against the fields extracted from the uploaded
document, and builds a reply from fixed templates. Nothing here invents a
value: a reply only repeats values taken from the message or from the document's
extracted fields.
"""

import os
import re
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal, InvalidOperation

from src.multimodal.fields import ExtractionResult, extract_fields
from src.multimodal.ocr import QUALITY_MESSAGES, OcrPage, quality_issues

MONTH_NAMES = (
    "January", "February", "March", "April", "May", "June",
    "July", "August", "September", "October", "November", "December",
)
_MONTH_NUMBER = {name[:3].lower(): index + 1 for index, name in enumerate(MONTH_NAMES)}

KIND_ORDER = ("order_id", "date", "amount", "error_code")
NOUNS = {
    "order_id": "order number",
    "date": "date",
    "amount": "amount",
    "error_code": "error code",
    "product": "product",
}

# Document amount labels that name the figure a customer is likely to mean,
# most important first.
HEADLINE_PRIORITY = ("grand total", "amount paid", "payable", "total", "amount", "paid", "charged")

# Flags that make a document value too uncertain to call a mismatch a conflict.
UNRELIABLE_FLAGS = {"low_confidence", "possible_currency_fusion"}

_MONTH_PATTERN = (
    r"(jan(?:uary)?|feb(?:ruary)?|mar(?:ch)?|apr(?:il)?|may|june?|july?|aug(?:ust)?"
    r"|sep(?:t(?:ember)?)?|oct(?:ober)?|nov(?:ember)?|dec(?:ember)?)\b\.?"
)

_MSG_ORDER_RE = re.compile(
    r"(?<![a-z])(?:order|booking|invoice|bill|ref(?:erence)?)(?![a-z])"
    r"\s*(?:(?:id|number|no|num)\b|#)?\.?\s*[:#\-]?\s*"
    r"([a-z0-9][a-z0-9\-/]{3,29})",
    re.IGNORECASE,
)
_DATE_LIKE_RE = re.compile(r"\d{1,2}[/-]\d{1,2}[/-]\d{2,4}")
_YEAR_RE = re.compile(r"(?:19|20)\d{2}")

_MSG_ERROR_LABEL_RE = re.compile(
    r"(?<![a-z])(?:error(?:\s*(?:code|no|number))?|err(?:\s*(?:code|no))?|status\s*code)\b\.?[\s:#\-]*"
    r"(0x[0-9a-f]{2,8}|[a-z]{1,5}[-_]?\d{2,6}|\d{3,6})(?![a-z0-9])",
    re.IGNORECASE,
)
_MSG_ERROR_BARE_RE = re.compile(
    r"(?<![a-z0-9])((?:err|error|e)[-_]?\d{3,5})(?![a-z0-9])", re.IGNORECASE
)

_ISO_DATE_RE = re.compile(r"(?<![\d\-])(20\d{2})-(\d{2})-(\d{2})(?!\d)")
_NUMERIC_DATE_RE = re.compile(
    r"(?<![\d/.\-])(\d{1,2})([/.\-])(\d{1,2})\2(\d{4}|\d{2})(?![\d/])"
)
_DAY_MONTH_RE = re.compile(
    r"(?<!\d)(\d{1,2})(?:st|nd|rd|th)?\s+(?:of\s+)?" + _MONTH_PATTERN
    + r"(?:,?\s+(20\d{2}))?(?!\d)",
    re.IGNORECASE,
)
_MONTH_DAY_RE = re.compile(
    r"(?<![a-z])" + _MONTH_PATTERN + r"\s+(\d{1,2})(?:st|nd|rd|th)?(?!\d)(?:,?\s+(20\d{2}))?",
    re.IGNORECASE,
)

_NUMBER = r"\d{1,3}(?:,\d{2,3})+(?:\.\d{1,2})?|\d+(?:\.\d{1,2})?"
_AMOUNT_PRE_RE = re.compile(
    r"(?:\brs\.?|\binr\b|\u20b9|\brupees?\b)\s*(" + _NUMBER + r")(?!\d)", re.IGNORECASE
)
_AMOUNT_POST_RE = re.compile(
    r"(?<![\w.,])(" + _NUMBER + r")\s*(?:rs\b|rupees?\b|inr\b|/-)", re.IGNORECASE
)
_AMOUNT_VERB_RE = re.compile(
    r"\b(?:paid|pay|payment|charged|debited|deducted|billed|cost|costs|amount|total"
    r"|refunded|refund|worth|price)\b[^\d\n]{0,15}?(" + _NUMBER + r")(?!\d)"
    r"(?!\s*(?:times?|items?|x\b|days?|hours?|units?|pcs|pieces|orders?|months?|years?|weeks?|people|%))",
    re.IGNORECASE,
)

_STOPWORDS = {
    "about", "after", "again", "also", "amount", "arrived", "been", "before", "bill",
    "bought", "button", "cannot", "charged", "check", "code", "could", "date",
    "delivered", "delivery", "does", "done", "error", "failed", "from", "have", "help",
    "here", "into", "invoice", "item", "items", "just", "like", "message", "need",
    "number", "order", "orders", "ordered", "paid", "payment", "placed", "please",
    "price", "product", "purchase", "purchased", "received", "refund", "refunded",
    "return", "shows", "shown", "still", "that", "them", "then", "there", "this",
    "total", "tried", "trying", "want", "were", "what", "when", "where", "which",
    "will", "with", "would", "your", "yours", "yesterday", "today",
} | {name.lower() for name in MONTH_NAMES}


@dataclass(frozen=True)
class Claim:
    kind: str
    display: str
    keys: tuple  # canonical forms; for dates, (year or None, month, day) readings


@dataclass(frozen=True)
class FieldCheck:
    kind: str
    claim: str
    verdict: str  # match, conflict, unclear, unverified
    document_values: tuple = ()
    caution: bool = False  # matched, but the document reading was uncertain


@dataclass
class ComparisonResult:
    status: str  # confirmed, conflict, needs_confirmation, needs_better_file
    reply: str
    checks: list = field(default_factory=list)
    product_words: tuple = ()

    def log_fields(self) -> dict:
        """Values that are safe to write to logs: no order numbers, dates,
        amounts or error codes, only statuses and verdict labels."""
        fields = {
            "status": self.status,
            "claims_checked": len(self.checks),
            "product_words_matched": len(self.product_words),
        }
        grouped = {}
        for check in self.checks:
            grouped.setdefault(check.kind, []).append(check.verdict)
        for kind, verdicts in grouped.items():
            fields[f"{kind}_verdict"] = ",".join(verdicts)
        return fields


def _date_order() -> str:
    raw = os.getenv("DOCUMENT_DATE_ORDER", "DMY").strip().upper()
    if raw not in ("DMY", "MDY"):
        raise ValueError(f"DOCUMENT_DATE_ORDER must be DMY or MDY, got {raw!r}")
    return raw


def _canon(value: str) -> str:
    return re.sub(r"[^A-Z0-9]", "", value.upper())


def _to_decimal(text):
    try:
        return Decimal(text.replace(",", ""))
    except InvalidOperation:
        return None


def _amount_key(value: Decimal) -> str:
    return str(value.copy_abs().quantize(Decimal("0.01")))


def _valid_date(year, month, day) -> bool:
    try:
        date(2000 if year is None else year, month, day)
    except ValueError:
        return False
    return True


def _format_date(year, month, day) -> str:
    text = f"{day} {MONTH_NAMES[month - 1]}"
    return f"{text} {year}" if year else text


def _format_iso(text: str) -> str:
    try:
        year, month, day = (int(part) for part in text.split("-"))
    except ValueError:
        return text
    return _format_date(year, month, day)


def _blank(text: str, start: int, end: int) -> str:
    return text[:start] + " " * (end - start) + text[end:]


def extract_claims(message: str) -> list:
    """Finds the order numbers, dates, amounts and error codes stated in a
    customer message. Only values that are clearly written are returned."""
    work = message
    claims = []

    # 1. Order numbers (blanked afterwards so they cannot be read as dates or amounts)
    seen = set()
    for match in _MSG_ORDER_RE.finditer(message):
        token = match.group(1).rstrip("-/")
        digits = sum(character.isdigit() for character in token)
        if digits < 3 or _DATE_LIKE_RE.fullmatch(token) or _YEAR_RE.fullmatch(token):
            continue
        work = _blank(work, match.start(1), match.end(1))
        key = _canon(token)
        if key in seen:
            continue
        seen.add(key)
        claims.append(Claim("order_id", token.upper(), (key,)))

    # 2. Error codes
    seen = set()
    for pattern in (_MSG_ERROR_LABEL_RE, _MSG_ERROR_BARE_RE):
        for match in pattern.finditer(work):
            token = match.group(1)
            work = _blank(work, match.start(1), match.end(1))
            key = _canon(token)
            if key in seen:
                continue
            seen.add(key)
            claims.append(Claim("error_code", token.upper(), (key,)))

    # 3. Dates
    order = _date_order()

    def collect(pattern, build):
        nonlocal work
        found = []
        for match in pattern.finditer(work):
            readings = build(match)
            if readings:
                found.append((match.start(), match.end(), readings))
        for start, end, _ in found:
            work = _blank(work, start, end)
        return found

    def build_iso(match):
        reading = (int(match.group(1)), int(match.group(2)), int(match.group(3)))
        return (reading,) if _valid_date(*reading) else None

    def build_numeric(match):
        first, second = int(match.group(1)), int(match.group(3))
        year = int(match.group(4))
        if len(match.group(4)) == 2:
            year += 2000
        day_first = (year, second, first)
        month_first = (year, first, second)
        ordered = [day_first, month_first] if order == "DMY" else [month_first, day_first]
        readings = []
        for reading in ordered:
            if _valid_date(*reading) and reading not in readings:
                readings.append(reading)
        return tuple(readings) or None

    def build_day_month(match):
        year = int(match.group(3)) if match.group(3) else None
        reading = (year, _MONTH_NUMBER[match.group(2).lower()[:3]], int(match.group(1)))
        return (reading,) if _valid_date(*reading) else None

    def build_month_day(match):
        year = int(match.group(3)) if match.group(3) else None
        reading = (year, _MONTH_NUMBER[match.group(1).lower()[:3]], int(match.group(2)))
        return (reading,) if _valid_date(*reading) else None

    found_dates = []
    found_dates += collect(_ISO_DATE_RE, build_iso)
    found_dates += collect(_NUMERIC_DATE_RE, build_numeric)
    found_dates += collect(_DAY_MONTH_RE, build_day_month)
    found_dates += collect(_MONTH_DAY_RE, build_month_day)
    found_dates.sort(key=lambda item: item[0])

    seen = set()
    for _, _, readings in found_dates:
        if readings in seen:
            continue
        seen.add(readings)
        claims.append(Claim("date", _format_date(*readings[0]), readings))

    # 4. Amounts
    seen = set()

    def add_amount(text, minimum_digits):
        value = _to_decimal(text)
        if value is None or value <= 0:
            return
        whole = text.replace(",", "").split(".")[0]
        if "." not in text and len(whole) < minimum_digits:
            return
        key = _amount_key(value)
        if key in seen:
            return
        seen.add(key)
        claims.append(Claim("amount", key, (key,)))

    for match in _AMOUNT_PRE_RE.finditer(work):
        add_amount(match.group(1), 1)
    for match in _AMOUNT_POST_RE.finditer(work):
        add_amount(match.group(1), 1)
    for match in _AMOUNT_VERB_RE.finditer(work):
        add_amount(match.group(1), 2)

    claims.sort(key=lambda claim: KIND_ORDER.index(claim.kind))
    return claims


def _product_words(message: str, document_text: str) -> tuple:
    """Distinctive words of the message that also appear in the document text.
    This is supporting evidence only; it never produces a conflict."""
    document_tokens = set(re.findall(r"[a-z]{4,}", document_text.lower()))
    found = []
    for token in re.findall(r"[a-z]{4,}", message.lower()):
        if token in _STOPWORDS or token in found:
            continue
        if token in document_tokens:
            found.append(token)
    return tuple(found)


def _key_for(kind: str, text: str):
    if kind in ("order_id", "error_code"):
        return _canon(text)
    if kind == "amount":
        value = _to_decimal(text)
        return None if value is None else _amount_key(value)
    if kind == "date":
        try:
            year, month, day = (int(part) for part in text.split("-"))
        except ValueError:
            return None
        return (year, month, day)
    return None


def _document_keys(item, use_alternatives: bool) -> list:
    texts = list(item.alternatives) if use_alternatives else [item.value]
    keys = [_key_for(item.kind, text) for text in texts]
    return [key for key in keys if key is not None]


def _key_match(kind: str, claim_key, document_key) -> bool:
    if kind == "date":
        return (
            claim_key[1] == document_key[1]
            and claim_key[2] == document_key[2]
            and (claim_key[0] is None or claim_key[0] == document_key[0])
        )
    if kind == "error_code":
        if claim_key == document_key:
            return True
        # "error 502" agrees with a document code such as E502
        return claim_key.isdigit() and not document_key.isdigit() and document_key.endswith(claim_key)
    return claim_key == document_key


def _claim_matches(claim: Claim, document_keys: list) -> bool:
    return any(
        _key_match(claim.kind, claim_key, document_key)
        for claim_key in claim.keys
        for document_key in document_keys
    )


def _display_values(item, with_alternatives: bool) -> list:
    texts = [item.value] + (list(item.alternatives) if with_alternatives else [])
    if item.kind == "date":
        texts = [_format_iso(text) for text in texts]
    return texts


def _check_claim(claim: Claim, document_fields: list) -> FieldCheck:
    kind = claim.kind
    fields = [item for item in document_fields if item.kind == kind]
    if not fields:
        return FieldCheck(kind, claim.display, "unverified")

    pool = fields
    headline = []
    if kind == "amount":
        headline = [item for item in fields if item.label in HEADLINE_PRIORITY]
        if headline:
            pool = headline

    for use_alternatives in (False, True):
        for item in pool:
            if _claim_matches(claim, _document_keys(item, use_alternatives)):
                caution = use_alternatives or "low_confidence" in item.flags
                return FieldCheck(kind, claim.display, "match", (), caution)

    if kind == "amount" and not headline:
        return FieldCheck(kind, claim.display, "unverified")

    if kind == "amount":
        reference = [min(headline, key=lambda item: HEADLINE_PRIORITY.index(item.label))]
    else:
        reference = pool[:2]

    unreliable = any(set(item.flags) & UNRELIABLE_FLAGS for item in reference)
    values = []
    for item in reference:
        for text in _display_values(item, unreliable):
            if text not in values:
                values.append(text)
    verdict = "unclear" if unreliable else "conflict"
    return FieldCheck(kind, claim.display, verdict, tuple(values))


def _document_text_of(check: FieldCheck) -> str:
    return " or ".join(check.document_values)


def _no_claims_reply(extraction: ExtractionResult) -> str:
    def reliable_values(kind):
        values = []
        for item in extraction.of_kind(kind):
            if set(item.flags) & UNRELIABLE_FLAGS:
                continue
            if item.value not in values:
                values.append(item.value)
        return values

    order_ids = reliable_values("order_id")
    if not order_ids:
        return (
            "I could not find an order number in the file that I can rely on. "
            "Could you tell me your order number?"
        )
    dates = reliable_values("date")
    label = "order number" if len(order_ids) == 1 else "order numbers"
    sentence = f"I can see {label} {' and '.join(order_ids[:2])} in your file"
    if len(dates) == 1:
        sentence += f", dated {_format_iso(dates[0])}"
    return sentence + ". Is this the order you are asking about?"


def _build_reply(status: str, checks: list) -> str:
    conflicts = [check for check in checks if check.verdict == "conflict"]
    unclear = [check for check in checks if check.verdict == "unclear"]
    unverified = [check for check in checks if check.verdict == "unverified"]
    matches = [check for check in checks if check.verdict == "match"]

    def match_listing():
        return ", ".join(f"{NOUNS[check.kind]} {check.claim}" for check in matches)

    unverified_sentences = [
        f"I could not find the {NOUNS[check.kind]} in the document, so I could not check "
        f"the {NOUNS[check.kind]} you gave ({check.claim})."
        for check in unverified
    ]
    caution_sentence = (
        "Part of the document was hard to read, so please tell me if any matched figure looks wrong."
    )

    parts = []
    if status == "confirmed":
        parts.append("Thank you. These details in your message match the document: " + match_listing() + ".")
        parts.extend(unverified_sentences)
        if any(check.caution for check in matches):
            parts.append(caution_sentence)
        return " ".join(parts)

    for check in conflicts:
        parts.append(
            f"The {NOUNS[check.kind]} in your message ({check.claim}) does not match the "
            f"document, which shows {_document_text_of(check)}."
        )
    for check in unclear:
        parts.append(
            f"I could not read the {NOUNS[check.kind]} in the document reliably "
            f"(it appears as {_document_text_of(check)}), and your message says {check.claim}."
        )
    if matches:
        parts.append("These details do match the document: " + match_listing() + ".")
    parts.extend(unverified_sentences)

    if conflicts:
        parts.append(
            "Could you tell me which is correct? If the document is the wrong one, "
            "please send the right file."
        )
    elif unclear:
        parts.append("Could you confirm the details, or send a clearer image of the document?")
    else:
        parts.append("Could you send a file that shows these details?")
    return " ".join(parts)


def compare_message(message: str, extraction: ExtractionResult, document_text: str = "") -> ComparisonResult:
    """Compares the details in a customer message with extracted document fields."""
    claims = extract_claims(message)
    words = _product_words(message, document_text)
    checks = [_check_claim(claim, extraction.fields) for claim in claims]
    
    if not checks:
        return ComparisonResult("needs_confirmation", _no_claims_reply(extraction), [], words)
    verdicts = {check.verdict for check in checks}
    if "conflict" in verdicts:
        status = "conflict"
    elif "unclear" in verdicts:
        status = "needs_confirmation"
    elif "match" in verdicts:
        status = "confirmed"
    else:
        status = "needs_confirmation"
    return ComparisonResult(status, _build_reply(status, checks), checks, words)


def compare_message_with_document(message: str, page: OcrPage) -> ComparisonResult:
    """Full comparison for one OCR page: unreadable pages are refused first."""
    issues = quality_issues(page)
    if issues:
        return ComparisonResult("needs_better_file", QUALITY_MESSAGES[issues[0]])
    return compare_message(message, extract_fields(page), page.text)
