"""Document metadata schema, validation and access rules for the RAG assistant.

Every document has a sidecar <name>.meta.json. The sidecar is the ONLY source of
metadata: text inside a document body can never change its access level, dates,
region or version.
"""
import json
import re
from dataclasses import dataclass
from datetime import date
from pathlib import Path

ACCESS_LEVELS = ("public", "customer", "internal", "restricted")  # lowest to highest
REGIONS = ("GLOBAL", "IN", "US", "EU")
DOC_TYPES = ("product", "faq", "policy", "troubleshooting")
REQUIRED_FIELDS = (
    "doc_id", "title", "doc_type", "topic", "version", "product",
    "region", "access_level", "effective_date", "expiry_date",
)

_DATE_RE = re.compile(r"\d{4}-\d{2}-\d{2}")
_ID_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.-]*")
_SLUG_RE = re.compile(r"[a-z0-9][a-z0-9-]*")
_VERSION_RE = re.compile(r"\d+(\.\d+){0,2}")


class MetadataError(ValueError):
    """Raised when a sidecar is missing fields or holds invalid values."""


@dataclass(frozen=True)
class DocMeta:
    doc_id: str
    title: str
    doc_type: str
    topic: str
    version: str
    product: str          # product slug, or "all" for every product
    region: str           # GLOBAL applies everywhere
    access_level: str
    effective_date: date  # first day the document is in force
    expiry_date: object   # last day the document is in force (inclusive), or None

    def is_active_on(self, day):
        if day < self.effective_date:
            return False
        return self.expiry_date is None or day <= self.expiry_date

    def status_on(self, day):
        if day < self.effective_date:
            return "future"
        if self.expiry_date is not None and day > self.expiry_date:
            return "expired"
        return "active"

    @property
    def key(self):
        return (self.doc_id, self.version)


def version_key(version):
    """'2.10' sorts above '2.9'."""
    return tuple(int(part) for part in str(version).split("."))


def access_rank(level):
    return ACCESS_LEVELS.index(level) if level in ACCESS_LEVELS else -1


def can_access(role, doc_level):
    """Fails closed: an unknown role or an unknown document level is denied."""
    role_rank = access_rank(role)
    doc_rank = access_rank(doc_level)
    return role_rank >= 0 and doc_rank >= 0 and role_rank >= doc_rank


def _text(raw, field, errors):
    value = raw.get(field)
    if not isinstance(value, str) or not value.strip():
        errors.append(f"{field} must be a non-empty string")
        return None
    return value.strip()


def _date(raw, field, errors, allow_null=False):
    value = raw.get(field)
    if value is None and allow_null:
        return None
    if not isinstance(value, str) or not _DATE_RE.fullmatch(value):
        errors.append(f"{field} must be YYYY-MM-DD" + (" or null" if allow_null else ""))
        return None
    try:
        return date.fromisoformat(value)
    except ValueError:
        errors.append(f"{field} is not a real date: {value}")
        return None


def validate_metadata(raw):
    """Returns a DocMeta or raises MetadataError listing every problem found."""
    if not isinstance(raw, dict):
        raise MetadataError("metadata must be a JSON object")
    errors = []
    for key in raw:
        if key not in REQUIRED_FIELDS:
            errors.append(f"unknown field: {key}")
    for field in REQUIRED_FIELDS:
        if field not in raw:
            errors.append(f"missing field: {field}")
    if errors:
        raise MetadataError("; ".join(errors))

    doc_id = _text(raw, "doc_id", errors)
    if doc_id and not _ID_RE.fullmatch(doc_id):
        errors.append("doc_id may only use letters, digits, '_', '.', '-'")
    title = _text(raw, "title", errors)
    doc_type = _text(raw, "doc_type", errors)
    if doc_type and doc_type not in DOC_TYPES:
        errors.append(f"doc_type must be one of {DOC_TYPES}")
    topic = _text(raw, "topic", errors)
    if topic and not _SLUG_RE.fullmatch(topic):
        errors.append("topic must be a lowercase slug such as refund-policy")
    version = _text(raw, "version", errors)
    if version and not _VERSION_RE.fullmatch(version):
        errors.append("version must look like 3 or 2.1")
    product = _text(raw, "product", errors)
    if product and not _SLUG_RE.fullmatch(product):
        errors.append("product must be a lowercase slug (or 'all')")
    region = _text(raw, "region", errors)
    if region and region not in REGIONS:
        errors.append(f"region must be one of {REGIONS}")
    access_level = _text(raw, "access_level", errors)
    if access_level and access_level not in ACCESS_LEVELS:
        errors.append(f"access_level must be one of {ACCESS_LEVELS}")
    effective = _date(raw, "effective_date", errors)
    expiry = _date(raw, "expiry_date", errors, allow_null=True)
    if effective and expiry and expiry < effective:
        errors.append("expiry_date is before effective_date")
    if errors:
        raise MetadataError("; ".join(errors))
    return DocMeta(doc_id, title, doc_type, topic, version, product, region,
                   access_level, effective, expiry)


def load_sidecar(path):
    """Reads one .meta.json file (a UTF-8 BOM from Windows editors is tolerated)."""
    path = Path(path)
    try:
        raw = json.loads(path.read_text(encoding="utf-8-sig"))
    except FileNotFoundError:
        raise MetadataError("sidecar file not found")
    except (OSError, ValueError) as exc:
        raise MetadataError(f"sidecar is not valid JSON: {exc}")
    return validate_metadata(raw)