"""Real-log check for Task 2. Run: python test_logs.py

Runs real requests through handle_request, with the log redirected to a temporary
file, then scans every logged line for values that must never be logged. The
existing tests patch record, so they never prove what is written to the file.
"""

import json
import os
import sys
import tempfile
from pathlib import Path

import pytesseract
from PIL import Image

from src.multimodal.orchestrator import handle_request
from src.pipeline import metrics

FILES = Path("test_files")
REAL_LOG = Path(metrics.METRICS_PATH)

# Fields that hold timestamps, ids and timings, so they cannot hold customer values.
IGNORED_KEYS = {
    "timestamp", "file_id", "size_bytes", "expires_at",
    "seconds", "ocr_seconds", "mean_confidence",
}

# Invented values placed in the customer message.
FORBIDDEN = {
    "order number in the message": "78232",
    "order number in the document": "78231",
    "card number": "4111",
    "phone number": "9876543210",
    "email domain": "example.com",
    "message text": "problem with order",
}

MESSAGE_WITH_PRIVATE_DATA = (
    "I have a problem with order 78232. My card is 4111 1111 1111 1111, "
    "my phone is 9876543210 and my email is x@example.com"
)

checks = 0
failures = 0


def check(name, condition):
    global checks, failures
    checks += 1
    if condition:
        print(f"PASS  {name}")
    else:
        failures += 1
        print(f"FAIL  {name}")


def digit_tokens(path):
    """Tokens of 5+ characters containing a digit, as OCR reads them from the image."""
    text = pytesseract.image_to_string(Image.open(path))
    tokens = set()
    for raw in text.split():
        token = raw.strip(".,:;()[]")
        if len(token) >= 5 and any(char.isdigit() for char in token):
            tokens.add(token.lower())
    return tokens


def main():
    clean = FILES / "invoice_clean.png"
    blurred = FILES / "invoice_blur_radius_6.png"
    hidden_list = sorted(FILES.glob("synthetic_hidden_*.png"))
    hidden = hidden_list[0] if hidden_list else FILES / "synthetic_hidden_MISSING.png"

    runs = [
        ("matching message", "I have a problem with order 78231", clean),
        ("wrong order and private data", MESSAGE_WITH_PRIVATE_DATA, clean),
        ("empty message", "", clean),
        ("blurred image", "I have a problem with order 78231", blurred),
        ("hidden instructions", "I have a problem with my order", hidden),
    ]

    real_size_before = REAL_LOG.stat().st_size if REAL_LOG.exists() else 0
    document_tokens = set()

    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
        uploads = Path(tmp) / "uploads"
        uploads.mkdir()
        os.environ["UPLOAD_DIR"] = str(uploads)
        temp_log = Path(tmp) / "metrics.jsonl"
        original_path = metrics.METRICS_PATH
        metrics.METRICS_PATH = temp_log
        try:
            for label, message, path in runs:
                if not path.exists():
                    check(f"fixture exists: {path.name}", False)
                    continue
                outcome = handle_request(message, path.name, path.read_bytes())
                print(f"      {label}: state={outcome.state} status={outcome.status}")
                check(f"{label}: finished without waiting for a job", outcome.state == "done")
                if path in (clean, hidden):
                    document_tokens |= digit_tokens(path)
        finally:
            metrics.METRICS_PATH = original_path

        lines = []
        if temp_log.exists():
            lines = [line for line in temp_log.read_text(encoding="utf-8").splitlines() if line.strip()]
        events = [json.loads(line) for line in lines]

    real_size_after = REAL_LOG.stat().st_size if REAL_LOG.exists() else 0

    check("events were written to the temporary log", len(events) > 0)
    check("real log was not touched", real_size_after == real_size_before)
    finished = [e for e in events if e.get("type") == "request_finished"]
    check("one request_finished per request", len(finished) == len(runs))

    stripped_blobs = [
        json.dumps({k: v for k, v in event.items() if k not in IGNORED_KEYS}).lower()
        for event in events
    ]
    for label, value in FORBIDDEN.items():
        check(f"log holds no {label}", not any(value.lower() in blob for blob in stripped_blobs))

    check(
        f"log holds none of the {len(document_tokens)} number-like tokens OCR reads in the files",
        not any(token in blob for token in document_tokens for blob in stripped_blobs),
    )
    check("OCR produced number-like tokens to search for", len(document_tokens) > 0)

    long_strings = [
        value for event in events for value in event.values()
        if isinstance(value, str) and len(value) > 120
    ]
    check("no logged text value is longer than 120 characters", not long_strings)

    print("\nEvent types:", sorted({e.get("type") for e in events}))
    print("Keys seen:  ", sorted({key for e in events for key in e}))
    print(f"\n{checks - failures}/{checks} checks passed")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())