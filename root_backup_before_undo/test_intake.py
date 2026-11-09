import io
import json
import os
import sys
import tempfile
import time
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

from PIL import Image

from src.multimodal import intake

failures = []
events = []
intake.record = lambda event_type, **fields: events.append((event_type, fields))


def check(name, actual, expected):
    status = "PASS" if actual == expected else "FAIL"
    print(f"{status}: {name} (got {actual!r}, expected {expected!r})")
    if actual != expected:
        failures.append(name)


def expect_reject(name, filename, data, code):
    try:
        intake.accept_upload(filename, data)
    except intake.UploadRejected as error:
        check(name, error.code, code)
    else:
        check(name, "accepted", code)


def make_image_bytes(image_format, size=(60, 40)):
    buffer = io.BytesIO()
    Image.new("RGB", size, "white").save(buffer, format=image_format)
    return buffer.getvalue()


def make_pdf(catalog_extra=b"", loose_stream=b""):
    """Build a one-page PDF from raw bytes.

    catalog_extra goes inside the catalog dictionary.
    loose_stream, if given, becomes an extra stream object that no page uses.
    """
    body = (
        b"%PDF-1.4\n"
        b"1 0 obj\n<< /Type /Catalog /Pages 2 0 R " + catalog_extra + b">>\nendobj\n"
        b"2 0 obj\n<< /Type /Pages /Kids [3 0 R] /Count 1 >>\nendobj\n"
        b"3 0 obj\n<< /Type /Page /Parent 2 0 R /MediaBox [0 0 200 200] >>\nendobj\n"
    )
    if loose_stream:
        body += (
            b"4 0 obj\n<< /Length " + str(len(loose_stream)).encode("ascii") + b" >>\n"
            b"stream\n" + loose_stream + b"\nendstream\nendobj\n"
        )
    return body + b"trailer\n<< /Root 1 0 R >>\n%%EOF\n"


CLEAN_PDF = make_pdf()
JS_PDF = make_pdf(catalog_extra=b"/OpenAction << /S /JavaScript /JS (app.alert(1)) >> ")
OBFUSCATED_PDF = make_pdf(catalog_extra=b"/AdditionalThing << /S /J#61vaScript >> ")
STREAM_PDF = make_pdf(loose_stream=b"/js /aa /launch")

with tempfile.TemporaryDirectory() as tmp:
    tmp_dir = Path(tmp)
    os.environ["UPLOAD_DIR"] = str(tmp_dir / "main")
    os.environ["UPLOAD_RETENTION_HOURS"] = "24"

    png = make_image_bytes("PNG")
    jpeg = make_image_bytes("JPEG")

    stored = intake.accept_upload("secret_invoice_4111.png", png)
    check("valid PNG accepted as image", stored.kind, "image")
    check("stored file exists", stored.path.is_file(), True)
    check("stored file has png suffix", stored.path.suffix, ".png")
    metadata_text = (tmp_dir / "main" / f"{stored.file_id}.json").read_text(encoding="utf-8")
    check("metadata does not contain the filename", "secret_invoice" in metadata_text, False)

    stored_jpeg = intake.accept_upload("photo.jpeg", jpeg)
    check("valid JPEG accepted and stored as png", stored_jpeg.mime, "image/png")

    expect_reject("fake exe named .png", "secret_invoice.png", b"MZ" + b"\x00" * 200, "unsupported_type")
    expect_reject("png content named .jpg", "secret_invoice.jpg", png, "extension_mismatch")
    expect_reject("gif extension", "animation.gif", png, "unsupported_type")
    expect_reject("empty file", "empty.png", b"", "empty_file")
    expect_reject("truncated png", "broken.png", png[: len(png) // 2], "corrupt_image")

    os.environ["MAX_UPLOAD_BYTES"] = "1000"
    expect_reject("file over size limit", "big.pdf", CLEAN_PDF + b"0" * 2000, "too_large")
    os.environ.pop("MAX_UPLOAD_BYTES")

    os.environ["MAX_IMAGE_PIXELS"] = "100"
    expect_reject("image over pixel limit", "huge.png", make_image_bytes("PNG", (20, 20)), "too_many_pixels")
    os.environ.pop("MAX_IMAGE_PIXELS")

    stored_pdf = intake.accept_upload("bill.pdf", CLEAN_PDF)
    check("clean PDF accepted", stored_pdf.kind, "pdf")
    expect_reject("PDF with JavaScript", "bill.pdf", JS_PDF, "pdf_active_content")
    expect_reject("PDF with obfuscated JavaScript name", "bill.pdf", OBFUSCATED_PDF, "pdf_active_content")
    check("PDF with marker bytes only inside a stream is accepted",
          intake.accept_upload("bill.pdf", STREAM_PDF).kind, "pdf")

    check("fresh upload can be read", intake.get_upload(stored.file_id).file_id, stored.file_id)

    # Retention: expiry on read, and the cleanup sweep
    os.environ["UPLOAD_DIR"] = str(tmp_dir / "retention")
    first = intake.accept_upload("a.png", png)
    second = intake.accept_upload("b.pdf", CLEAN_PDF)
    later = datetime.now(timezone.utc) + timedelta(hours=25)

    try:
        intake.get_upload(first.file_id, now=later)
    except intake.UploadUnavailable as error:
        check("expired upload is refused", error.code, "expired")
    else:
        check("expired upload is refused", "returned", "expired")
    check("expired upload was deleted on read", list((tmp_dir / "retention").glob(f"{first.file_id}.*")), [])

    try:
        intake.get_upload("../secret")
    except intake.UploadUnavailable as error:
        check("path traversal id is refused", error.code, "not_found")
    else:
        check("path traversal id is refused", "returned", "not_found")

    check("purge removes the remaining expired upload", intake.purge_expired(now=later), 1)
    check("retention folder is empty after purge", list((tmp_dir / "retention").iterdir()), [])

    # Orphans: files with no metadata expire by age; other files are left alone
    os.environ["UPLOAD_DIR"] = str(tmp_dir / "orphans")
    orphan_dir = tmp_dir / "orphans"
    orphan_dir.mkdir()
    old_orphan = orphan_dir / (uuid.uuid4().hex + ".png")
    fresh_orphan = orphan_dir / (uuid.uuid4().hex + ".png")
    foreign = orphan_dir / "notes.txt"
    for path in (old_orphan, fresh_orphan, foreign):
        path.write_bytes(b"x")
    old_time = time.time() - 48 * 3600
    os.utime(old_orphan, (old_time, old_time))
    check("purge removes the old orphan only", intake.purge_expired(), 1)
    check("old orphan gone", old_orphan.exists(), False)
    check("fresh orphan kept", fresh_orphan.exists(), True)
    check("unrelated file kept", foreign.exists(), True)

    check("no event contains the customer's filename", "secret_invoice" in json.dumps(events), False)

if failures:
    print(f"\n{len(failures)} check(s) failed: {failures}")
    sys.exit(1)

print("\nAll checks passed.")