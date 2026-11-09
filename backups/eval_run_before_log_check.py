"""Evaluation run for Task 2. Run: python eval_run.py

Runs the five scenarios named in the brief (blurred image, mismatched invoice,
delayed processing, expired file, prompt-injection attempt) plus a matching
baseline through the real pipeline. Uploads and the metrics log are redirected
to a temporary folder. Writes eval_results.md, a table with no customer values.
"""

import os
import sys
import tempfile
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

from src.multimodal.intake import UploadUnavailable, get_upload, purge_expired
from src.multimodal.orchestrator import check_job, handle_request
from src.pipeline import metrics

FILES = Path("test_files")
RESULTS_PATH = Path("eval_results.md")
ENV_NAMES = (
    "UPLOAD_DIR",
    "UPLOAD_RETENTION_HOURS",
    "PROCESSING_BUDGET_SECONDS",
    "PROCESSING_SIMULATED_DELAY_SECONDS",
)

rows = []


def add_row(scenario, requirement, expected, observed, passed):
    rows.append((scenario, requirement, expected, observed, "PASS" if passed else "FAIL"))
    print(f"{'PASS' if passed else 'FAIL'}  {scenario}: expected {expected}, observed {observed}")


def names_in(directory):
    return sorted(p.name for p in Path(directory).iterdir())


def wait_for_result(job_id, seconds=30):
    deadline = time.time() + seconds
    outcome = check_job(job_id)
    while outcome.state != "done" and time.time() < deadline:
        time.sleep(0.5)
        outcome = check_job(job_id)
    return outcome


def run_scenarios(uploads):
    clean = FILES / "invoice_clean.png"
    blurred = FILES / "invoice_blur_radius_6.png"
    hidden_list = sorted(FILES.glob("synthetic_hidden_*.png"))
    hidden = hidden_list[0] if hidden_list else FILES / "synthetic_hidden_MISSING.png"

    for path in (clean, blurred, hidden):
        if not path.exists():
            add_row(f"fixture {path.name}", "fixture present", "file exists", "missing", False)
            return

    # Baseline
    outcome = handle_request("I have a problem with order 78231", clean.name, clean.read_bytes())
    add_row(
        "Matching invoice (baseline)",
        "Compare OCR fields with the message",
        "done / confirmed",
        f"{outcome.state} / {outcome.status}",
        (outcome.state, outcome.status) == ("done", "confirmed"),
    )

    # 1. Blurred image
    outcome = handle_request("I have a problem with order 78231", blurred.name, blurred.read_bytes())
    add_row(
        "Blurred image",
        "Low quality: ask for another file",
        "done / needs_better_file",
        f"{outcome.state} / {outcome.status}",
        (outcome.state, outcome.status) == ("done", "needs_better_file"),
    )

    # 2. Mismatched invoice
    outcome = handle_request("I have a problem with order 78232", clean.name, clean.read_bytes())
    add_row(
        "Mismatched invoice",
        "Conflict: request clarification",
        "done / conflict",
        f"{outcome.state} / {outcome.status}",
        (outcome.state, outcome.status) == ("done", "conflict"),
    )

    # 3. Delayed processing
    os.environ["PROCESSING_BUDGET_SECONDS"] = "2"
    os.environ["PROCESSING_SIMULATED_DELAY_SECONDS"] = "4"
    started = time.time()
    outcome = handle_request("I have a problem with order 78231", clean.name, clean.read_bytes())
    waited = time.time() - started
    queued_ok = outcome.state == "queued" and bool(outcome.job_id)
    add_row(
        "Delayed processing: customer wait",
        "Over budget: move to background queue and notify",
        "queued, wait under 4 s",
        f"{outcome.state}, wait {waited:.1f} s",
        queued_ok and waited < 4,
    )
    if queued_ok:
        final = wait_for_result(outcome.job_id)
        add_row(
            "Delayed processing: final result",
            "Customer gets the result later",
            "done / confirmed",
            f"{final.state} / {final.status}",
            (final.state, final.status) == ("done", "confirmed"),
        )
    os.environ.pop("PROCESSING_BUDGET_SECONDS", None)
    os.environ.pop("PROCESSING_SIMULATED_DELAY_SECONDS", None)

    # 4. Expired file
    before = set(names_in(uploads))
    outcome = handle_request("I have a problem with order 78231", clean.name, clean.read_bytes())
    new_files = sorted(set(names_in(uploads)) - before)
    sidecars = [name for name in new_files if name.endswith(".json")]
    stored = outcome.state == "done" and len(sidecars) == 1
    add_row(
        "Expired file: stored",
        "Upload is kept during retention",
        "stored (image + sidecar)",
        f"{len(new_files)} files",
        stored and len(new_files) == 2,
    )
    if sidecars:
        file_id = Path(sidecars[0]).stem
        future = datetime.now(timezone.utc) + timedelta(hours=25)
        try:
            get_upload(file_id, now=future)
            refused = False
        except UploadUnavailable:
            refused = True
        add_row(
            "Expired file: access",
            "Expired file cannot be used",
            "refused after 25 h",
            "refused" if refused else "served",
            refused,
        )
        purge_expired(now=future)
        left = names_in(uploads)
        add_row(
            "Expired file: deletion",
            "Delete after retention period",
            "upload folder empty",
            f"{len(left)} files left",
            left == [],
        )

    # 5. Prompt-injection image
    outcome = handle_request("I have a problem with my order", hidden.name, hidden.read_bytes())
    left = names_in(uploads)
    add_row(
        "Prompt-injection image: verdict",
        "Reject hidden instructions",
        "done / rejected",
        f"{outcome.state} / {outcome.status}",
        (outcome.state, outcome.status) == ("done", "rejected"),
    )
    add_row(
        "Prompt-injection image: file",
        "Rejected file is deleted",
        "upload folder empty",
        f"{len(left)} files left",
        left == [],
    )


def write_results():
    passed = sum(1 for row in rows if row[4] == "PASS")
    lines = [
        "# Task 2 evaluation results",
        "",
        f"Run: {datetime.now().strftime('%Y-%m-%d %H:%M')}. Synthetic files only; no customer values.",
        "",
        "| Scenario | Brief requirement | Expected | Observed | Result |",
        "|---|---|---|---|---|",
    ]
    for row in rows:
        lines.append("| " + " | ".join(row) + " |")
    lines += ["", f"{passed}/{len(rows)} checks passed.", ""]
    RESULTS_PATH.write_text("\n".join(lines), encoding="utf-8")


def main():
    saved_env = {name: os.environ.get(name) for name in ENV_NAMES}
    real_log = Path(metrics.METRICS_PATH)
    real_size_before = real_log.stat().st_size if real_log.exists() else 0
    original_path = metrics.METRICS_PATH

    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
        uploads = Path(tmp) / "uploads"
        uploads.mkdir()
        os.environ["UPLOAD_DIR"] = str(uploads)
        os.environ["UPLOAD_RETENTION_HOURS"] = "24"
        metrics.METRICS_PATH = Path(tmp) / "metrics.jsonl"
        try:
            run_scenarios(uploads)
        finally:
            metrics.METRICS_PATH = original_path
            for name, value in saved_env.items():
                if value is None:
                    os.environ.pop(name, None)
                else:
                    os.environ[name] = value

    real_size_after = real_log.stat().st_size if real_log.exists() else 0
    add_row(
        "Real log untouched",
        "Evaluation does not pollute the real log",
        "same size",
        "same size" if real_size_after == real_size_before else "changed",
        real_size_after == real_size_before,
    )

    write_results()
    failures = sum(1 for row in rows if row[4] == "FAIL")
    print(f"\n{len(rows) - failures}/{len(rows)} checks passed. Table written to {RESULTS_PATH}")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())