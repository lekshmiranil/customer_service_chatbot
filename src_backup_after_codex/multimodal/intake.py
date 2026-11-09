"""Upload intake for the customer chatbot.

Validates untrusted files, rejects unsafe ones, stores accepted ones under a
random name with an expiry time, and deletes them once the retention period
has passed. Nothing here reads text out of a file; that is the OCR stage.
"""

import hashlib
import io
import json
import os
import re
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path

import filetype
import pymupdf
from PIL import Image, ImageOps

from src.pipeline.metrics import record

PROJECT_ROOT = Path(__file__).resolve().parents[2]

ALLOWED_TYPES = {
    "png": "image/png",
    "jpg": "image/jpeg",
    "jpeg": "image/jpeg",
    "pdf": "application/pdf",
}

FILE_ID_PATTERN = re.compile(r"[0-9a-f]{32}")

# PDF names that start code or pull in outside content. Stream bodies are
# removed before scanning because compressed data can contain these bytes by chance.
PDF_ACTIVE_CONTENT = re.compile(
    rb"/(javascript|js|launch|openaction|aa|embeddedfile|richmedia|gotor|submitform)(?![a-z0-9])",
    re.IGNORECASE,
)
PDF_STREAM_BODY = re.compile(rb"stream\r?\n.*?endstream", re.DOTALL)
PDF_NAME_ESCAPE = re.compile(rb"#([0-9A-Fa-f]{2})")


class UploadRejected(Exception):
    """The file was refused. customer_message is safe to show to the customer."""

    def __init__(self, code, customer_message):
        super().__init__(customer_message)
        self.code = code
        self.customer_message = customer_message


class UploadUnavailable(Exception):
    """The stored file is gone or past its retention period."""

    def __init__(self, code):
        super().__init__(code)
        self.code = code
        self.customer_message = "This file is no longer available. Please upload it again."


@dataclass(frozen=True)
class StoredUpload:
    file_id: str
    kind: str  # "image" or "pdf"
    mime: str
    size_bytes: int
    sha256: str
    created_at: str
    expires_at: str
    path: Path


def _env_number(name, default, cast):
    raw = os.getenv(name, "").strip()
    if not raw:
        return default
    try:
        value = cast(raw)
    except ValueError:
        raise ValueError(f"{name} must be a number, got {raw!r}") from None
    if value <= 0:
        raise ValueError(f"{name} must be greater than zero, got {raw!r}")
    return value


def _upload_dir() -> Path:
    configured = os.getenv("UPLOAD_DIR", "").strip()
    path = Path(configured) if configured else Path("uploads")
    if not path.is_absolute():
        path = PROJECT_ROOT / path
    path.mkdir(parents=True, exist_ok=True)
    return path


def _suffix_for(kind):
    return {"image": ".png", "pdf": ".pdf"}[kind]


def _log(event_type, **fields):
    try:
        record(event_type, **fields)
    except Exception as error:
        print(f"Metrics logging failed: {error}")


def _reject(code, customer_message, **log_fields):
    _log("upload_rejected", reason=code, **log_fields)
    raise UploadRejected(code, customer_message)


def _safe_extension(filename) -> str:
    suffix = Path(str(filename or "")).suffix.lower().lstrip(".")
    return re.sub(r"[^a-z0-9]", "", suffix)[:8]

ACTIVE_CONTENT_MESSAGE = (
    "This PDF contains active content and cannot be accepted. "
    "Please send a screenshot or a plain PDF."
)


def _active_content_marker(raw):
    """Name of the first active-content marker in raw PDF text, or None."""
    decoded = PDF_NAME_ESCAPE.sub(lambda m: bytes([int(m.group(1), 16)]), raw)
    match = PDF_ACTIVE_CONTENT.search(decoded)
    return match.group(1).decode("ascii", "replace").lower() if match else None


def _inspect_pdf_structure(data, log_context):
    """Opens the PDF with PyMuPDF and refuses password-protected, empty,
    over-long and over-complex files. Then reads every object's dictionary,
    including objects packed inside compressed object streams, which the raw
    byte scan cannot see, and refuses active content found there."""
    max_pages = _env_number("MAX_PDF_PAGES", 5, int)
    max_objects = _env_number("MAX_PDF_OBJECTS", 20000, int)
    unreadable = "The PDF could not be opened. Please upload it again or send a screenshot."

    pymupdf.TOOLS.mupdf_display_errors(False)
    try:
        document = pymupdf.open(stream=data, filetype="pdf")
    except Exception as error:
        _reject("corrupt_pdf", unreadable, error_type=type(error).__name__, **log_context)

    try:
        if document.needs_pass:
            _reject(
                "pdf_encrypted",
                "This PDF is password protected. Please send an unprotected copy or a screenshot.",
                **log_context,
            )
        pages = document.page_count
        if pages < 1:
            _reject("corrupt_pdf", unreadable, error_type="no_pages", **log_context)
        if pages > max_pages:
            _reject(
                "too_many_pages",
                f"This PDF has {pages} pages and at most {max_pages} can be processed. "
                "Please send only the pages that show the order, or screenshots.",
                pages=pages,
                **log_context,
            )
        objects = document.xref_length()
        if objects > max_objects:
            _reject(
                "pdf_too_complex",
                "This PDF is too complex to process. Please send a screenshot or a simpler PDF.",
                objects=objects,
                **log_context,
            )
        for xref in range(1, objects):
            try:
                definition = document.xref_object(xref, compressed=False)
            except Exception:
                continue
            marker = _active_content_marker(definition.encode("utf-8", "replace"))
            if marker:
                _reject(
                    "pdf_active_content",
                    ACTIVE_CONTENT_MESSAGE,
                    marker=marker,
                    found_in="object_scan",
                    **log_context,
                )
    finally:
        document.close()


def _check_pdf(data, log_context):
    """First scan: raw bytes outside stream bodies. Second check: PyMuPDF
    reads the structure and every object, including packed ones."""
    marker = _active_content_marker(PDF_STREAM_BODY.sub(b"", data))
    if marker:
        _reject("pdf_active_content", ACTIVE_CONTENT_MESSAGE, marker=marker, **log_context)
    _inspect_pdf_structure(data, log_context)

def _sanitize_image(data, log_context) -> bytes:
    """Decodes the image and re-encodes it as a clean PNG without metadata."""
    max_pixels = _env_number("MAX_IMAGE_PIXELS", 25_000_000, int)
    try:
        with Image.open(io.BytesIO(data)) as probe:
            width, height = probe.size
            if width * height > max_pixels:
                _reject(
                    "too_many_pixels",
                    "The image is too large to process. Please upload a smaller version.",
                    width=width,
                    height=height,
                    **log_context,
                )
            probe.verify()

        with Image.open(io.BytesIO(data)) as opened:
            opened.load()
            image = ImageOps.exif_transpose(opened)

        has_alpha = image.mode in ("RGBA", "LA") or (
            image.mode == "P" and "transparency" in image.info
        )
        if has_alpha:
            rgba = image.convert("RGBA")
            flattened = Image.new("RGB", rgba.size, "white")
            flattened.paste(rgba, mask=rgba.getchannel("A"))
        else:
            flattened = image.convert("RGB")

        buffer = io.BytesIO()
        flattened.save(buffer, format="PNG")
        return buffer.getvalue()
    except UploadRejected:
        raise
    except Exception as error:
        _reject(
            "corrupt_image",
            "The image could not be opened. Please upload it again or send a different file.",
            error_type=type(error).__name__,
            **log_context,
        )


def accept_upload(filename, data: bytes) -> StoredUpload:
    """Validates and stores one upload. Raises UploadRejected if it is unsafe."""
    max_bytes = _env_number("MAX_UPLOAD_BYTES", 5 * 1024 * 1024, int)
    retention_hours = _env_number("UPLOAD_RETENTION_HOURS", 24.0, float)

    size = len(data)
    extension = _safe_extension(filename)
    context = {"size_bytes": size, "extension": extension}

    if size == 0:
        _reject("empty_file", "The file is empty. Please upload it again.", **context)
    if size > max_bytes:
        _reject(
            "too_large",
            f"The file is larger than {max_bytes / 1048576:g} MB. Please upload a smaller file.",
            **context,
        )

    expected_mime = ALLOWED_TYPES.get(extension)
    guessed = filetype.guess(data)
    detected_mime = guessed.mime if guessed else None

    if expected_mime is None or detected_mime not in set(ALLOWED_TYPES.values()):
        _reject(
            "unsupported_type",
            "Only PNG, JPG and PDF files can be uploaded.",
            detected_mime=detected_mime,
            **context,
        )
    if detected_mime != expected_mime:
        _reject(
            "extension_mismatch",
            "The file does not match its file type. Please upload the original PNG, JPG or PDF.",
            detected_mime=detected_mime,
            **context,
        )

    if detected_mime == "application/pdf":
        _check_pdf(data, context)
        kind, stored_mime, stored_bytes = "pdf", "application/pdf", data
    else:
        kind, stored_mime = "image", "image/png"
        stored_bytes = _sanitize_image(data, context)

    file_id = uuid.uuid4().hex
    now = datetime.now(timezone.utc)
    expires_at = now + timedelta(hours=retention_hours)

    directory = _upload_dir()
    data_path = directory / f"{file_id}{_suffix_for(kind)}"
    meta_path = directory / f"{file_id}.json"
    temp_path = directory / f"{file_id}.part"

    temp_path.write_bytes(stored_bytes)
    temp_path.replace(data_path)

    metadata = {
        "file_id": file_id,
        "kind": kind,
        "mime": stored_mime,
        "size_bytes": len(stored_bytes),
        "sha256": hashlib.sha256(stored_bytes).hexdigest(),
        "created_at": now.isoformat(),
        "expires_at": expires_at.isoformat(),
    }
    try:
        meta_path.write_text(json.dumps(metadata, indent=2), encoding="utf-8")
    except OSError:
        data_path.unlink(missing_ok=True)
        raise

    _log(
        "upload_accepted",
        file_id=file_id,
        kind=kind,
        size_bytes=len(stored_bytes),
        expires_at=metadata["expires_at"],
    )
    return StoredUpload(
        file_id=file_id,
        kind=kind,
        mime=stored_mime,
        size_bytes=metadata["size_bytes"],
        sha256=metadata["sha256"],
        created_at=metadata["created_at"],
        expires_at=metadata["expires_at"],
        path=data_path,
    )


def get_upload(file_id, now=None) -> StoredUpload:
    """Returns a stored upload, or raises UploadUnavailable if it is missing or
    expired. An expired file is deleted on the spot. now must be timezone-aware."""
    now = now or datetime.now(timezone.utc)
    if not isinstance(file_id, str) or not FILE_ID_PATTERN.fullmatch(file_id):
        raise UploadUnavailable("not_found")

    directory = _upload_dir()
    try:
        metadata = json.loads((directory / f"{file_id}.json").read_text(encoding="utf-8"))
        expires_at = datetime.fromisoformat(metadata["expires_at"])
        kind = metadata["kind"]
        path = directory / f"{file_id}{_suffix_for(kind)}"
    except (OSError, ValueError, KeyError):
        raise UploadUnavailable("not_found") from None

    if expires_at <= now:
        delete_upload(file_id)
        _log("upload_expired", file_id=file_id)
        raise UploadUnavailable("expired")
    if not path.is_file():
        raise UploadUnavailable("not_found")

    return StoredUpload(
        file_id=file_id,
        kind=kind,
        mime=metadata["mime"],
        size_bytes=metadata["size_bytes"],
        sha256=metadata["sha256"],
        created_at=metadata["created_at"],
        expires_at=metadata["expires_at"],
        path=path,
    )


def delete_upload(file_id) -> bool:
    """Deletes a stored file and its metadata. Returns True if anything was removed."""
    if not isinstance(file_id, str) or not FILE_ID_PATTERN.fullmatch(file_id):
        return False
    removed = False
    for path in _upload_dir().glob(f"{file_id}.*"):
        path.unlink(missing_ok=True)
        removed = True
    return removed


def _expiry_from_sidecar(meta_path):
    try:
        metadata = json.loads(meta_path.read_text(encoding="utf-8"))
        return datetime.fromisoformat(metadata["expires_at"])
    except (OSError, ValueError, KeyError):
        return None


def purge_expired(now=None) -> int:
    """Deletes every upload past its retention period, including files whose
    metadata is missing or unreadable (those expire by file age). Returns the
    number of uploads removed. now must be timezone-aware."""
    now = now or datetime.now(timezone.utc)
    retention = timedelta(hours=_env_number("UPLOAD_RETENTION_HOURS", 24.0, float))
    directory = _upload_dir()

    groups = {}
    for path in directory.iterdir():
        if path.is_file() and FILE_ID_PATTERN.fullmatch(path.stem):
            groups.setdefault(path.stem, []).append(path)

    removed = 0
    for file_id, paths in groups.items():
        expires_at = _expiry_from_sidecar(directory / f"{file_id}.json")
        if expires_at is None:
            newest = max(p.stat().st_mtime for p in paths)
            expires_at = datetime.fromtimestamp(newest, timezone.utc) + retention
        if expires_at <= now:
            for path in paths:
                path.unlink(missing_ok=True)
            removed += 1

    if removed:
        _log("upload_purged", count=removed)
    return removed