"""Checks for src\\rag\\metadata.py: validation, active windows, version order, access ranks."""
import json
import sys
import tempfile
from datetime import date
from pathlib import Path

from src.rag.metadata import (ACCESS_LEVELS, MetadataError, can_access, load_sidecar,
                              validate_metadata, version_key)

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


def good(**changes):
    raw = {
        "doc_id": "POL-X", "title": "Title", "doc_type": "policy", "topic": "refund-policy",
        "version": "1", "product": "homehub", "region": "GLOBAL", "access_level": "public",
        "effective_date": "2025-01-01", "expiry_date": None,
    }
    raw.update(changes)
    return raw


def rejects(raw, fragment):
    try:
        validate_metadata(raw)
    except MetadataError as exc:
        return fragment in str(exc)
    return False


meta = validate_metadata(good())
check("valid metadata loads", meta.doc_id == "POL-X" and meta.expiry_date is None)
check("null expiry accepted", validate_metadata(good(expiry_date=None)).expiry_date is None)
check("dated expiry accepted", validate_metadata(good(expiry_date="2026-06-30")).expiry_date == date(2026, 6, 30))

missing = good()
del missing["region"]
check("missing field rejected", rejects(missing, "missing field: region"))
check("unknown field rejected", rejects(good(acess_level="public"), "unknown field: acess_level"))
check("bad region rejected", rejects(good(region="MARS"), "region must be one of"))
check("bad access level rejected", rejects(good(access_level="secret"), "access_level must be one of"))
check("bad doc type rejected", rejects(good(doc_type="memo"), "doc_type must be one of"))
check("bad version rejected", rejects(good(version="v3"), "version must look like"))
check("bad topic rejected", rejects(good(topic="Refund Policy"), "topic must be a lowercase slug"))
check("bad date format rejected", rejects(good(effective_date="01/02/2025"), "effective_date must be YYYY-MM-DD"))
check("impossible date rejected", rejects(good(effective_date="2025-02-30"), "not a real date"))
check("expiry before effective rejected", rejects(good(expiry_date="2024-12-31"), "expiry_date is before effective_date"))
check("empty doc_id rejected", rejects(good(doc_id="  "), "doc_id must be a non-empty string"))
check("non-object rejected", rejects([], "must be a JSON object"))
try:
    validate_metadata(good(region="MARS", access_level="secret"))
    check("all problems are listed together", False)
except MetadataError as exc:
    check("all problems are listed together", "region" in str(exc) and "access_level" in str(exc))

windowed = validate_metadata(good(effective_date="2025-01-01", expiry_date="2025-06-30"))
check("day before effective is future", windowed.status_on(date(2024, 12, 31)) == "future")
check("effective day is active", windowed.is_active_on(date(2025, 1, 1)))
check("expiry day is still active", windowed.is_active_on(date(2025, 6, 30)))
check("day after expiry is expired", windowed.status_on(date(2025, 7, 1)) == "expired")
check("open-ended document stays active", meta.is_active_on(date(2099, 1, 1)))

check("version 2.10 sorts above 2.9", version_key("2.10") > version_key("2.9"))
check("version 10 sorts above 9", version_key("10") > version_key("9"))

check("access levels are ordered", ACCESS_LEVELS == ("public", "customer", "internal", "restricted"))
check("public cannot read customer", not can_access("public", "customer"))
check("customer reads public", can_access("customer", "public"))
check("internal reads customer", can_access("internal", "customer"))
check("internal cannot read restricted", not can_access("internal", "restricted"))
check("restricted reads everything", all(can_access("restricted", lv) for lv in ACCESS_LEVELS))
check("unknown role is denied", not can_access("admin", "public"))
check("unknown document level is denied", not can_access("restricted", "top-secret"))
check("empty role is denied", not can_access("", "public"))

with tempfile.TemporaryDirectory() as tmp:
    path = Path(tmp) / "a.meta.json"
    path.write_text(json.dumps(good()), encoding="utf-8-sig")
    check("sidecar with BOM loads", load_sidecar(path).doc_id == "POL-X")
    path.write_text("{not json", encoding="utf-8")
    try:
        load_sidecar(path)
        check("broken JSON rejected", False)
    except MetadataError as exc:
        check("broken JSON rejected", "not valid JSON" in str(exc))
    try:
        load_sidecar(Path(tmp) / "missing.meta.json")
        check("missing sidecar rejected", False)
    except MetadataError as exc:
        check("missing sidecar rejected", "not found" in str(exc))

print(f"checks: {total}, failed: {failures}")
sys.exit(1 if failures else 0)