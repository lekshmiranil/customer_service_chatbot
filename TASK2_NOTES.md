# Task 2 notes: multimodal file analysis

## What it does
- The customer attaches a PNG, JPG, JPEG or PDF to a conversation.
- The file is stored for a limited time, read with Tesseract OCR, and the extracted fields are compared with what the customer wrote.
- Outcomes include confirmed (the file matches the message), conflict (the file and the message disagree, so the customer is asked to clarify), needs_confirmation, needs_better_file (low-quality image, so another file is requested) and rejected (hidden instructions found in the file).
- If processing takes longer than the budget (default 4 s), the customer is told it moved to a background queue and the result replaces the notice when ready, without any click.
- Files are deleted after the retention period, and an expired file cannot be used.

## Settings
All settings are environment variables listed in `.env.example`: upload folder and retention, upload and PDF limits, OCR limits and confidence, field matching, the hidden-instruction scan, the processing budget and the background queue (workers, queue size, result lifetime).

## Evidence
`eval_run.py` writes `eval_results.md`: 11 of 11 checks pass, covering the matching, blurred, mismatched, delayed (queued and final result), expired-file (stored, refused, deleted) and prompt-injection cases (verdict and deletion), plus a check that the evaluation leaves the real log untouched. The detailed test scripts are `test_intake.py`, `test_fields.py`, `test_compare.py`, `test_injection.py`, `test_pdfs.py`, `test_orchestrator.py`, `test_regression_gate.py`, `test_retention.py`, `test_logs.py` and `test_question_logging.py`.

## Limits
- Results depend on image quality. Blurred or low-contrast files are not guessed at; the customer is asked for a better file.
- OCR needs Tesseract installed on the machine running the app.
- The background queue is bounded by the worker count and queue size settings.