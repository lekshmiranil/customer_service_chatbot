"""Small background worker and processing path for customer uploads."""

from concurrent.futures import ThreadPoolExecutor
import threading
import time
from src.multimodal.compare import compare_message_with_document
from src.multimodal.injection import reject_if_injected, reject_pdf_if_injected
from src.multimodal.intake import get_upload, purge_expired
from src.multimodal.ocr import OcrFailed, ocr_image, quality_issues, QUALITY_MESSAGES
from src.multimodal.pdfs import PdfUnreadable, read_pdf

_EXECUTOR = ThreadPoolExecutor(max_workers=2, thread_name_prefix="upload-ocr")
_CLEANUP_STARTED = False


def _retention_cleanup():
    while True:
        try:
            purge_expired()
        except Exception:
            pass  # cleanup failures must not interrupt customer requests
        time.sleep(60)


def _start_cleanup():
    global _CLEANUP_STARTED
    if not _CLEANUP_STARTED:
        _CLEANUP_STARTED = True
        threading.Thread(target=_retention_cleanup, name="upload-retention", daemon=True).start()


_start_cleanup()


def process_upload(file_id: str, message: str) -> str:
    """Read one unexpired upload, reject embedded instructions, compare evidence."""
    upload = get_upload(file_id)
    try:
        if upload.kind == "pdf":
            reading = read_pdf(upload.path)
            reject_pdf_if_injected(reading, upload)
            if not reading.complete:
                return "I could not finish reading this PDF. Please send the relevant page as a screenshot or a shorter PDF."
            page = reading.page
        else:
            page = ocr_image(upload.path)
            reject_if_injected(page, upload)
    except (OcrFailed, PdfUnreadable):
        return "I could not read this file. Please upload a clearer image or an unprotected PDF."

    issues = quality_issues(page)
    if issues:
        return QUALITY_MESSAGES[issues[0]]
    result = compare_message_with_document(message, page)
    return result.reply


def submit_upload(file_id: str, message: str):
    """Submit processing and return a Future for UI polling."""
    return _EXECUTOR.submit(process_upload, file_id, message)


def accept_and_submit(filename, data: bytes, message: str):
    """Validate/store upload before putting its opaque id on the worker queue."""
    from src.multimodal.intake import accept_upload

    purge_expired()
    upload = accept_upload(filename, data)
    return upload, submit_upload(upload.file_id, message)
