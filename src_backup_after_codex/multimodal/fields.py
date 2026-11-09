"""Field extraction for the customer chatbot.

Finds order IDs, dates, amounts, error codes and product names in OCR text,
reports how sure the OCR engine was about each value, and flags readings that
could be wrong. A value that is not clearly present in the text is not
returned: nothing here guesses or fills in missing information.
"""

import os
import re
from dataclasses import dataclass, field, replace
from datetime import date
from decimal import Decimal, InvalidOperation

from src.multimodal.ocr import OcrPage

MONTHS = {
    "jan": 1, "feb": 2, "mar": 3, "apr": 4, "may": 5, "jun": 6,
    "jul": 7, "aug": 8, "sep": 9, "oct": 10, "nov": 11, "dec": 12,
}

# Characters that the OCR engine produces when it fails to read a rupee sign.
_JUNK_GLYPHS = "%~?&@=_|`'\"!*;"

_MONTH = r"(jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*\.?"

_ORDER_LABEL = (
    r"(?:order\s*(?:id\b|number\b|no\b|num\b|#)"
    r"|bill\s*(?:no\b|number\b|#)"
    r"|invoice\s*(?:no\b|number\b|#)"
    r"|booking\s*(?:id\b|no\b)"
    r"|reference\s*(?:no\b|number\b|id\b)"
    r"|ref\s*(?:no\b|id\b))"
)
_ORDER_RE = re.compile(
    r"(?<![a-z])" + _ORDER_LABEL + r"\.?[\s:#\-]*([a-z0-9][a-z0-9\-/]{3,29})",
    re.IGNORECASE,
)
_DATE_LIKE_RE = re.compile(r"\d{1,2}[/-]\d{1,2}[/-]\d{2,4}")

_ISO_DATE_RE = re.compile(r"(?<!\d)(\d{4})-(\d{2})-(\d{2})(?!\d)")
_NUMERIC_DATE_RE = re.compile(
    r"(?<![\d/.\-])(\d{1,2})[/.\-](\d{1,2})[/.\-](\d{4}|\d{2})(?![\d/])"
)
_DAY_MONTH_RE = re.compile(
    rf"(?<!\d)(\d{{1,2}})(?:st|nd|rd|th)?\s+{_MONTH},?\s+(\d{{4}})(?!\d)",
    re.IGNORECASE,
)
_MONTH_DAY_RE = re.compile(
    rf"(?<![a-z]){_MONTH}\s+(\d{{1,2}})(?:st|nd|rd|th)?,?\s+(\d{{4}})(?!\d)",
    re.IGNORECASE,
)

_NUMBER_RE = re.compile(
    r"(?<![\w,])(?<!\d\.)(\d{1,3}(?:,\d{2,3})+|\d+)(?:\.(\d{1,2}))?(?!\w)(?![.,]\d)"
)
_CURRENCY_BEFORE_RE = re.compile(r"(?:\brs\.?|\binr|[\u20b9$\u20ac\u00a3])\s*$", re.IGNORECASE)
_NEGATIVE_BEFORE_RE = re.compile(r"[-\u2212][^\w\s]{0,2}$")
_ADJACENT_SYMBOLS_RE = re.compile(r"([^\w\s]{1,2})$")

_AMOUNT_LABELS = (
    r"grand\s*total|sub\s*total|amount\s*paid|marketplace\s*fee|promotion\s*applied|"
    r"total|amount|price|shipping|fee|cgst|sgst|igst|gst|tax|discount|promotion|"
    r"refund|balance|payable|paid|charged|mrp"
)
_AMOUNT_LABEL_RE = re.compile(rf"\b(?:{_AMOUNT_LABELS})\b")
_LABEL_NAMES = {
    "grandtotal": "grand total",
    "subtotal": "subtotal",
    "amountpaid": "amount paid",
    "marketplacefee": "marketplace fee",
    "promotionapplied": "promotion applied",
}

_ERROR_LABEL_RE = re.compile(
    r"(?<![a-z])(?:error\b(?:\s*(?:code|no|number|id)\b)?|err\s*(?:code|no)\b"
    r"|status\s*code|fault\s*code)\.?[\s:#\-]*"
    r"(0x[0-9a-f]{2,8}|[a-z]{1,5}[-_]?\d{2,6}|\d{3,6})(?![a-z0-9])",
    re.IGNORECASE,
)
_BARE_ERROR_RE = re.compile(r"(?<![A-Za-z0-9])((?:ERR|ERROR|E)[-_]?\d{3,5})(?![A-Za-z0-9])")

_PRODUCT_STRONG_RE = re.compile(
    r"^\W*(?:product(?:\s*name)?|model(?:\s*(?:no|number))?)\b[\s:\-]*(.+)$",
    re.IGNORECASE,
)
_PRODUCT_WEAK_RE = re.compile(
    r"^\W*(?:item(?:\s*name)?|description)\b\s*[:\-]\s*(.+)$",
    re.IGNORECASE,
)
_HEADER_WORDS = {
    "qty", "quantity", "price", "amount", "rate", "total", "unit", "mrp",
    "hsn", "sno", "no", "item", "description", "tax", "gst",
}
_GENERIC_VALUES = {
    "details", "detail", "name", "information", "info", "question", "questions",
    "review", "reviews", "image", "images", "code", "type", "category", "list",
    "summary",
}


@dataclass(frozen=True)
class FieldValue:
    kind: str  # order_id, date, amount, error_code, product
    value: str  # normalised: ISO date, amount with two decimals, upper-case code
    raw: str  # the text exactly as read
    confidence: float  # lowest word confidence among the words that make up the value
    label: str  # the label read next to the value, for example "grand total"
    flags: tuple = ()
    alternatives: tuple = ()  # other plausible readings of the same value


@dataclass
class ExtractionResult:
    fields: list = field(default_factory=list)

    def of_kind(self, kind):
        return [item for item in self.fields if item.kind == kind]

    def first(self, kind):
        matches = self.of_kind(kind)
        return matches[0] if matches else None


@dataclass
class _Line:
    text: str
    spans: list  # (start, end, OcrWord)


def _field_min_confidence() -> float:
    raw = os.getenv("FIELD_MIN_CONFIDENCE", "").strip()
    if not raw:
        return 70.0
    try:
        value = float(raw)
    except ValueError:
        raise ValueError(f"FIELD_MIN_CONFIDENCE must be a number, got {raw!r}") from None
    if value <= 0:
        raise ValueError(f"FIELD_MIN_CONFIDENCE must be greater than zero, got {raw!r}")
    return value


def _date_order() -> str:
    raw = os.getenv("DOCUMENT_DATE_ORDER", "DMY").strip().upper()
    if raw not in ("DMY", "MDY"):
        raise ValueError(f"DOCUMENT_DATE_ORDER must be DMY or MDY, got {raw!r}")
    return raw


def _build_lines(page: OcrPage) -> list:
    result = []
    for words in page.lines():
        parts = []
        spans = []
        position = 0
        for word in words:
            if parts:
                position += 1
            start = position
            parts.append(word.text)
            position += len(word.text)
            spans.append((start, position, word))
        result.append(_Line(" ".join(parts), spans))
    return result


def _confidence(line: _Line, start: int, end: int) -> float:
    values = [word.confidence for s, e, word in line.spans if s < end and e > start]
    return round(min(values), 1) if values else 0.0


def _label_before(text: str, start: int, max_words: int = 4) -> str:
    words = re.findall(r"[A-Za-z]+", text[:start])
    return " ".join(word.lower() for word in words[-max_words:])


def _make_date(year: int, month: int, day: int):
    try:
        return date(year, month, day)
    except ValueError:
        return None


def _order_ids(line: _Line) -> list:
    results = []
    for match in _ORDER_RE.finditer(line.text):
        raw = match.group(1)
        value = raw.rstrip("-/").upper()
        if sum(character.isdigit() for character in value) < 3:
            continue
        if _DATE_LIKE_RE.fullmatch(value):
            continue
        label = line.text[match.start():match.start(1)].strip(" :#-.").lower()
        results.append(
            FieldValue(
                "order_id", value, raw,
                _confidence(line, match.start(1), match.end(1)), label,
            )
        )
    return results


def _dates(line: _Line) -> list:
    order = _date_order()
    candidates = []  # (start, end, primary, other)

    for match in _ISO_DATE_RE.finditer(line.text):
        parsed = _make_date(int(match.group(1)), int(match.group(2)), int(match.group(3)))
        if parsed:
            candidates.append((match.start(), match.end(), parsed, None))

    for match in _DAY_MONTH_RE.finditer(line.text):
        month = MONTHS[match.group(2).lower()]
        parsed = _make_date(int(match.group(3)), month, int(match.group(1)))
        if parsed:
            candidates.append((match.start(), match.end(), parsed, None))

    for match in _MONTH_DAY_RE.finditer(line.text):
        month = MONTHS[match.group(1).lower()]
        parsed = _make_date(int(match.group(3)), month, int(match.group(2)))
        if parsed:
            candidates.append((match.start(), match.end(), parsed, None))

    for match in _NUMERIC_DATE_RE.finditer(line.text):
        first_number = int(match.group(1))
        second_number = int(match.group(2))
        year = int(match.group(3))
        if len(match.group(3)) == 2:
            year += 2000
        day_first = _make_date(year, second_number, first_number)
        month_first = _make_date(year, first_number, second_number)
        if order == "DMY":
            primary, other = day_first, month_first
        else:
            primary, other = month_first, day_first
        if primary is None:
            primary, other = other, None
        if primary is None:
            continue
        if other == primary:
            other = None
        candidates.append((match.start(), match.end(), primary, other))

    candidates.sort(key=lambda item: item[0])
    results = []
    accepted_end = -1
    for start, end, primary, other in candidates:
        if start < accepted_end:
            continue
        accepted_end = end
        flags = ("ambiguous_day_month",) if other else ()
        alternatives = (other.isoformat(),) if other else ()
        results.append(
            FieldValue(
                "date", primary.isoformat(), line.text[start:end],
                _confidence(line, start, end), _label_before(line.text, start),
                flags, alternatives,
            )
        )
    return results


def _amount_label(before: str) -> str:
    last = None
    for match in _AMOUNT_LABEL_RE.finditer(before.lower()):
        last = match
    if last is None:
        return ""
    compact = re.sub(r"\s+", "", last.group(0))
    return _LABEL_NAMES.get(compact, compact)


def _amounts(line: _Line) -> list:
    results = []
    for match in _NUMBER_RE.finditer(line.text):
        whole = match.group(1)
        decimals = match.group(2)
        before = line.text[: match.start()]
        has_currency = bool(_CURRENCY_BEFORE_RE.search(before))
        if not (has_currency or (decimals is not None and len(decimals) == 2)):
            continue
        text_number = whole.replace(",", "") + ("." + decimals if decimals else "")
        try:
            number = Decimal(text_number)
        except InvalidOperation:
            continue
        if _NEGATIVE_BEFORE_RE.search(before):
            number = -number

        adjacent = _ADJACENT_SYMBOLS_RE.search(before)
        adjacent_text = adjacent.group(1) if adjacent else ""
        flags = []
        if has_currency:
            flags.append("currency_marked")
        elif any(character in _JUNK_GLYPHS for character in adjacent_text):
            flags.append("currency_symbol_misread")

        results.append(
            FieldValue(
                "amount",
                str(number.quantize(Decimal("0.01"))),
                match.group(0),
                _confidence(line, match.start(), match.end()),
                _amount_label(before),
                tuple(flags),
            )
        )
    return results


def _error_codes(line: _Line) -> list:
    results = []
    seen = set()
    for match in _ERROR_LABEL_RE.finditer(line.text):
        raw = match.group(1)
        value = "0x" + raw[2:].upper() if raw.lower().startswith("0x") else raw.upper()
        seen.add(value)
        label = line.text[match.start():match.start(1)].strip(" :#-.").lower()
        results.append(
            FieldValue(
                "error_code", value, raw,
                _confidence(line, match.start(1), match.end(1)), label,
            )
        )
    for match in _BARE_ERROR_RE.finditer(line.text):
        value = match.group(1).upper()
        if value in seen:
            continue
        seen.add(value)
        results.append(
            FieldValue(
                "error_code", value, match.group(1),
                _confidence(line, match.start(1), match.end(1)), "",
            )
        )
    return results


def _clean_product(value: str):
    value = value.strip(" :-.")[:80].strip()
    if len(value) < 3 or not re.search(r"[A-Za-z]", value):
        return None
    tokens = re.findall(r"[a-z]+", value.lower())
    if tokens and all(token in _HEADER_WORDS for token in tokens):
        return None
    if value.lower() in _GENERIC_VALUES:
        return None
    return value


def _products(line: _Line) -> list:
    for pattern in (_PRODUCT_STRONG_RE, _PRODUCT_WEAK_RE):
        match = pattern.match(line.text)
        if not match:
            continue
        cleaned = _clean_product(match.group(1))
        if cleaned is None:
            return []
        label = line.text[: match.start(1)].strip(" :-.").lower()
        return [
            FieldValue(
                "product", cleaned, match.group(1),
                _confidence(line, match.start(1), match.end(1)), label,
            )
        ]
    return []


def _flag_possible_fusion(fields: list) -> list:
    """If the document shows that rupee signs were misread as junk characters,
    an amount with no currency marker may start with a misread rupee sign that
    was read as a digit. Such amounts get the shorter reading as an alternative."""
    amounts = [item for item in fields if item.kind == "amount"]
    if not any("currency_symbol_misread" in item.flags for item in amounts):
        return fields

    updated = []
    for item in fields:
        if (
            item.kind == "amount"
            and not item.value.startswith("-")
            and "currency_marked" not in item.flags
            and "currency_symbol_misread" not in item.flags
            and "," not in item.raw
        ):
            whole, _, fraction = item.value.partition(".")
            if len(whole) >= 2:
                try:
                    shorter = Decimal(whole[1:] + "." + fraction).quantize(Decimal("0.01"))
                except InvalidOperation:
                    shorter = None
                if shorter is not None and shorter > 0:
                    item = replace(
                        item,
                        flags=item.flags + ("possible_currency_fusion",),
                        alternatives=(str(shorter),),
                    )
        updated.append(item)
    return updated


def _apply_confidence_flags(fields: list) -> list:
    minimum = _field_min_confidence()
    return [
        replace(item, flags=item.flags + ("low_confidence",))
        if item.confidence < minimum
        else item
        for item in fields
    ]


def _dedupe(fields: list) -> list:
    seen = set()
    result = []
    for item in fields:
        key = (item.kind, item.value, item.label)
        if key in seen:
            continue
        seen.add(key)
        result.append(item)
    return result


def extract_fields(page: OcrPage) -> ExtractionResult:
    """Extracts fields from one OCR page. Only values that are present in the
    text are returned; each carries its OCR confidence and any warning flags."""
    fields = []
    for line in _build_lines(page):
        fields.extend(_order_ids(line))
        fields.extend(_dates(line))
        fields.extend(_amounts(line))
        fields.extend(_error_codes(line))
        fields.extend(_products(line))

    fields = _flag_possible_fusion(fields)
    fields = _apply_confidence_flags(fields)
    return ExtractionResult(_dedupe(fields))