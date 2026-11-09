"""Request orchestrator for the customer chatbot's file analysis.

One call, handle_request(message, filename, data), takes a customer's message
and one uploaded file through intake, reading (OCR or PDF text), the injection
scan and the comparison with the message, and returns a RequestOutcome whose
reply is ready to show.

Time budget: the customer waits at most PROCESSING_BUDGET_SECONDS (default 30).
If the work is not finished by then it keeps running in a background worker,
the customer is told so straight away, and check_job(job_id) returns the result
later. The budget limits how long the customer waits; it does not cancel the
work. A hard limit (JOB_HARD_LIMIT_SECONDS) stops a PDF from reading further
pages, and every OCR call has its own timeout.

Replies come from fixed templates (here and in compare.py). Nothing in this
module logs text from the message or the file, or any extracted value.
"""

import threading
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass

from src.multimodal.compare import compare_message_with_document
from src.multimodal.injection import reject_if_injected, reject_pdf_if_injected
from src.multimodal.intake import UploadRejected, accept_upload, delete_upload
from src.multimodal.ocr import OcrFailed, _env_number, ocr_image
from src.multimodal.pdfs import PdfUnreadable, log_fields as pdf_log_fields, read_pdf
from src.pipeline import metrics

BACKGROUND_NOTICE = (
    "Your file is taking longer than expected to process, so I have moved it to "
    "the background. You do not need to upload it again. Please use Check result "
    "in a moment to see the outcome."
)
STILL_WORKING = "I am still working on your file. Please check again in a few seconds."
UNKNOWN_JOB = "I could not find that request any more. Please upload the file again."
BUSY = "Many files are being processed right now. Please try again in a few minutes."
UNREADABLE = "I could not read this file. Please send a clearer photo, a screenshot or a plain PDF."
PARTIAL_PDF = (
    "I could only read part of this PDF in the time available. Please send fewer "
    "pages, or a screenshot of the page that shows the order."
)
FAILED = "Something went wrong while processing your file. Please try again, or contact support."


@dataclass(frozen=True)
class RequestOutcome:
    state: str       # "done" or "queued"
    status: str      # confirmed, conflict, needs_confirmation, needs_better_file,
                     # rejected, busy, unavailable, error, or queued
    reply: str
    job_id: str = ""


@dataclass
class _Job:
    job_id: str
    done: threading.Event
    outcome: RequestOutcome = None
    background: bool = False
    finished_at: float = 0.0


_LOCK = threading.Lock()
_JOBS = {}
_EXECUTOR = None


def _executor():
    global _EXECUTOR
    with _LOCK:
        if _EXECUTOR is None:
            workers = _env_number("JOB_WORKERS", 2, int)
            _EXECUTOR = ThreadPoolExecutor(max_workers=workers, thread_name_prefix="file-job")
        return _EXECUTOR


def _log(event_type, **fields):
    try:
        metrics.record(event_type, **fields)
    except Exception as error:
        print(f"Metrics logging failed: {error}")


def _prune_jobs():
    """Forgets finished jobs older than JOB_RESULT_TTL_MINUTES. Caller holds _LOCK."""
    ttl = _env_number("JOB_RESULT_TTL_MINUTES", 60.0, float) * 60
    now = time.monotonic()
    for job_id in [j for j, job in _JOBS.items() if job.done.is_set() and now - job.finished_at > ttl]:
        del _JOBS[job_id]


def _open_job_count() -> int:
    return sum(1 for job in _JOBS.values() if not job.done.is_set())


def _process(message, upload, started):
    """Reads the file, rejects hidden instructions and compares with the
    message. Returns (status, reply, log_fields)."""
    hard_deadline = started + _env_number("JOB_HARD_LIMIT_SECONDS", 120.0, float)
    extra = {}
    try:
        if upload.kind == "pdf":
            reading = read_pdf(upload.path, deadline=hard_deadline)
            extra.update(pdf_log_fields(reading))
            reject_pdf_if_injected(reading, upload)
            page = reading.page
            if not reading.complete:
                return "needs_better_file", PARTIAL_PDF, extra
        else:
            page = ocr_image(str(upload.path))
            extra.update(ocr_seconds=page.elapsed_seconds, mean_confidence=round(page.mean_confidence, 1))
            reject_if_injected(page, upload)
    except UploadRejected as rejected:
        extra["reason"] = rejected.code
        return "rejected", rejected.customer_message, extra
    except (OcrFailed, PdfUnreadable):
        extra["reason"] = "unreadable"
        return "needs_better_file", UNREADABLE, extra

    result = compare_message_with_document(message, page)
    for key, value in result.log_fields().items():
        extra["comparison_status" if key == "status" else key] = value
    return result.status, result.reply, extra


def _run_job(job, message, upload, delay):
    started = time.monotonic()
    extra = {}
    try:
        if delay:
            time.sleep(delay)  # test hook: PROCESSING_SIMULATED_DELAY_SECONDS
        status, reply, extra = _process(message, upload, started)
    except Exception as error:
        status, reply, extra = "error", FAILED, {"error_type": type(error).__name__}

    with _LOCK:
        job.outcome = RequestOutcome("done", status, reply)
        job.finished_at = time.monotonic()
        background = job.background
    job.done.set()
    _log(
        "request_finished",
        status=status,
        kind=upload.kind,
        seconds=round(time.monotonic() - started, 2),
        background=background,
        **extra,
    )


def handle_request(message, filename, data) -> RequestOutcome:
    """Takes one message and one uploaded file through the whole pipeline.
    Never raises for customer-caused problems; they come back as outcomes."""
    started = time.monotonic()
    budget = _env_number("PROCESSING_BUDGET_SECONDS", 30.0, float)
    delay = _env_number("PROCESSING_SIMULATED_DELAY_SECONDS", 0.0, float)
    max_open = _env_number("MAX_QUEUED_JOBS", 20, int)

    try:
        upload = accept_upload(filename, data)
    except UploadRejected as rejected:
        return RequestOutcome("done", "rejected", rejected.customer_message)

    job = _Job(job_id=uuid.uuid4().hex, done=threading.Event())
    with _LOCK:
        _prune_jobs()
        if _open_job_count() >= max_open:
            busy = True
        else:
            busy = False
            _JOBS[job.job_id] = job
    if busy:
        delete_upload(upload.file_id)
        _log("request_finished", status="busy", kind=upload.kind, seconds=0.0, background=False)
        return RequestOutcome("done", "busy", BUSY)

    _executor().submit(_run_job, job, message, upload, delay)

    remaining = max(budget - (time.monotonic() - started), 0.0)
    if job.done.wait(timeout=remaining):
        return job.outcome

    with _LOCK:
        job.background = True
    if job.done.is_set():
        return job.outcome
    _log("request_queued", kind=upload.kind, waited_seconds=round(budget, 1))
    return RequestOutcome("queued", "queued", BACKGROUND_NOTICE, job.job_id)


def check_job(job_id) -> RequestOutcome:
    """Returns the result of a request that was moved to the background, or a
    'still working' outcome if it is not finished."""
    with _LOCK:
        _prune_jobs()
        job = _JOBS.get(job_id) if isinstance(job_id, str) else None
    if job is None:
        return RequestOutcome("done", "unavailable", UNKNOWN_JOB)
    if job.done.is_set():
        return job.outcome
    return RequestOutcome("queued", "queued", STILL_WORKING, job_id)