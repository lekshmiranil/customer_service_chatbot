import os
import json
import time
import shutil
import sys
from pathlib import Path

sys.path.append(str(Path(__file__).parent.parent.parent))

from src.pipeline.ingestion import (
    process_incoming_documents,
    create_version_snapshot,
    rollback_version,
    load_manifest,
    save_manifest,
    backup_staging,
    restore_staging
)
from src.pipeline.evaluator import run_quality_evaluation, EvaluationInconclusiveError
from src.pipeline.maintenance import is_within_maintenance_window
from src.langchain_helper import create_vector_db, get_qa_chain
from src.pipeline.access_control import authorize
from src.pipeline.metrics import record as record_metric

ACTIVE_DB_PATH = "faiss_index"
CANDIDATE_DB_PATH = "faiss_candidate"

PROJECT_ROOT = Path(__file__).resolve().parents[2]
IN_PROGRESS_MARKER = PROJECT_ROOT / "dataset" / "update_in_progress.json"


def _parse_retry_delays(env_value: str) -> list:
    """Parses a comma-separated list of minutes (e.g. '15,30,60') into a list of seconds."""
    return [int(float(part.strip()) * 60) for part in env_value.split(",") if part.strip()]


RETRY_DELAYS = _parse_retry_delays(os.getenv("RETRY_DELAY_MINUTES", "15,30,60"))
HEALTH_CHECK_WINDOW_SECONDS = int(os.getenv("HEALTH_CHECK_WINDOW_SECONDS", "300"))
HEALTH_CHECK_POLL_SECONDS = int(os.getenv("HEALTH_CHECK_POLL_SECONDS", "30"))

DAILY_QUOTA_MARKERS = ("perday", "per_day", "requests_per_day")


def _is_daily_quota_exhausted(exc: Exception) -> bool:
    """True if the inconclusive evaluation was caused by the daily quota,
    which no amount of short-term retrying can fix."""
    message = str(exc).lower()
    return any(marker in message for marker in DAILY_QUOTA_MARKERS)


def _write_marker(documents_before, snapshot_version):
    """Records that an update attempt is in flight, with everything needed to
    undo it. Written atomically so a kill mid-write can't leave a corrupt file."""
    IN_PROGRESS_MARKER.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = IN_PROGRESS_MARKER.with_suffix(".tmp")
    with open(tmp_path, "w", encoding="utf-8") as f:
        json.dump(
            {
                "started_at": time.strftime("%Y-%m-%d %H:%M:%S"),
                "documents_before": documents_before,
                "snapshot_version": snapshot_version,
            },
            f,
            indent=4,
        )
    os.replace(tmp_path, IN_PROGRESS_MARKER)


def _clear_marker():
    """Removes the in-flight marker. Safe to call when it doesn't exist."""
    try:
        IN_PROGRESS_MARKER.unlink()
    except FileNotFoundError:
        pass


def _rollback_and_restore(snapshot_version, documents_before):
    """
    Undo a failed attempt: restore the vector index from this attempt's
    snapshot (if one was taken), put the staging folder back, and restore
    the document registry so the files are treated as pending again.
    Clears the in-flight marker once the state is consistent again.
    """
    if os.path.exists(CANDIDATE_DB_PATH):
        shutil.rmtree(CANDIDATE_DB_PATH, ignore_errors=True)
    if snapshot_version is not None:
        rollback_version(snapshot_version, ACTIVE_DB_PATH)
    restore_staging()
    manifest = load_manifest()
    manifest["documents"] = documents_before
    save_manifest(manifest)
    _clear_marker()


def _recover_from_interrupted_update() -> bool:
    """
    If a previous run was killed mid-update (crash, power loss, killed
    process), its marker file is still present. Restore the pre-update state
    before doing anything else. Returns False if recovery failed, in which
    case the caller must not start a new update.
    """
    if not IN_PROGRESS_MARKER.exists():
        return True

    print("Found an unfinished update from a previous run. Restoring the last known-good state...")
    try:
        with open(IN_PROGRESS_MARKER, "r", encoding="utf-8") as f:
            state = json.load(f)
        _rollback_and_restore(
            state.get("snapshot_version"),
            state.get("documents_before", {}),
        )
    except Exception as e:
        print(f"Recovery from the interrupted update FAILED: {e}")
        print("Refusing to start a new update on an unknown state. Inspect dataset/update_in_progress.json and fix manually.")
        return False

    record_metric("pipeline_recovery", outcome="recovered_from_interrupted_update")
    print("Recovery complete. Continuing with a fresh update attempt.")
    return True


def _validate_maintenance_config() -> bool:
    """Fails fast on an invalid MAINTENANCE_WINDOW_START/END value, before any
    quota is spent on the quality evaluation."""
    try:
        is_within_maintenance_window()
    except Exception as e:
        print(f"Invalid maintenance window configuration: {e}")
        print("Check MAINTENANCE_WINDOW_START and MAINTENANCE_WINDOW_END in .env (HH:MM, hours 00-23).")
        return False
    return True


def _handle_failure_and_maybe_retry(attempt: int, reason: str):
    """
    Sleeps for the next retry delay if attempts remain and returns the new
    attempt count. Returns None if retries are exhausted.
    """
    attempt += 1
    if attempt <= len(RETRY_DELAYS):
        sleep_time = RETRY_DELAYS[attempt - 1]
        print(f"{reason} Retrying in {sleep_time / 60:.2f} minutes...")
        time.sleep(sleep_time)
        return attempt
    print(f"{reason} Maximum retry limits reached. Update aborted.")
    return None


def execute_pipeline_update_with_retries(token=None):
    if not authorize(token, "run_update"):
        print("Access denied: valid admin credentials are required to run a pipeline update.")
        return False

    if not _recover_from_interrupted_update():
        return False

    if not _validate_maintenance_config():
        return False

    attempt = 0

    while attempt <= len(RETRY_DELAYS):
        documents_before = load_manifest().get("documents", {})
        snapshot_version = None
        backup_staging()
        _write_marker(documents_before, snapshot_version)
        attempt_start = time.time()

        try:
            print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] Starting pipeline update attempt {attempt + 1}...")

            # Step 1: Process incoming documents (deduplicate, stage, quarantine)
            staged_files = process_incoming_documents()
            if not staged_files:
                print("No new or modified documents to process. Pipeline sync skipped.")
                _clear_marker()
                return True

            # Step 2: Snapshot the current index before changing anything
            snapshot_path = create_version_snapshot(ACTIVE_DB_PATH)
            if snapshot_path:
                snapshot_version = load_manifest().get("version", 0)
                _write_marker(documents_before, snapshot_version)

            # Step 3: Build the candidate vector database without touching active index
            print("Building candidate vector database index...")
            candidate_vectordb = create_vector_db(target_path=CANDIDATE_DB_PATH)

            # Step 4: Quality gate
            print("Running quality and grounding evaluation tests on candidate index...")
            passed_quality = run_quality_evaluation(lambda: get_qa_chain(candidate_vectordb))

            if not passed_quality:
                print("UPDATE REJECTED: New knowledge base failed quality/grounding thresholds.")
                if os.path.exists(CANDIDATE_DB_PATH):
                    shutil.rmtree(CANDIDATE_DB_PATH, ignore_errors=True)
                _rollback_and_restore(snapshot_version, documents_before)
                record_metric(
                    "pipeline_attempt",
                    outcome="quality_rejected",
                    attempt_number=attempt + 1,
                    duration_seconds=round(time.time() - attempt_start, 1),
                )
                new_attempt = _handle_failure_and_maybe_retry(attempt, "Update failed the quality gate.")
                if new_attempt is None:
                    return False
                attempt = new_attempt
                continue

            # Step 4.5: Hold the approved update until the maintenance window opens
            if not is_within_maintenance_window():
                print("Update approved but outside maintenance window. Waiting for window to open...")
                while not is_within_maintenance_window():
                    time.sleep(60)
                print("Maintenance window is now open. Proceeding with activation.")

            # Step 5: Activate candidate index into ACTIVE_DB_PATH
            print("Activating approved knowledge base index...")
            if os.path.exists(ACTIVE_DB_PATH):
                shutil.rmtree(ACTIVE_DB_PATH)
            shutil.copytree(CANDIDATE_DB_PATH, ACTIVE_DB_PATH)
            if os.path.exists(CANDIDATE_DB_PATH):
                shutil.rmtree(CANDIDATE_DB_PATH, ignore_errors=True)

            print(f"Update passed quality gate. Activated! Starting {HEALTH_CHECK_WINDOW_SECONDS}s health observation window...")

            chain = get_qa_chain()  # built once, reused for every ping
            health_check_passed = True
            observation_start = time.time()

            while time.time() - observation_start < HEALTH_CHECK_WINDOW_SECONDS:
                try:
                    test_res = chain.invoke({"query": "System Health Check"})
                    if not test_res:
                        health_check_passed = False
                        break
                except Exception as e:
                    print(f"Health check query exception detected: {e}")
                    health_check_passed = False
                    break
                time.sleep(HEALTH_CHECK_POLL_SECONDS)

            if not health_check_passed:
                print("HEALTH CHECK FAILED within observation window! Automatically rolling back...")
                _rollback_and_restore(snapshot_version, documents_before)
                record_metric(
                    "pipeline_attempt",
                    outcome="health_check_failed",
                    attempt_number=attempt + 1,
                    duration_seconds=round(time.time() - attempt_start, 1),
                )
                new_attempt = _handle_failure_and_maybe_retry(attempt, "Update failed the health check.")
                if new_attempt is None:
                    return False
                attempt = new_attempt
                continue

            print("Pipeline update successfully deployed and verified stable!")
            from src.pipeline.evaluator import commit_quality_baseline
            commit_quality_baseline()
            _clear_marker()

            record_metric(
                "pipeline_attempt",
                outcome="success",
                attempt_number=attempt + 1,
                duration_seconds=round(time.time() - attempt_start, 1),
            )
            return True

        except KeyboardInterrupt:
            print("Pipeline interrupted. Restoring previous state...")
            _rollback_and_restore(snapshot_version, documents_before)
            raise

        except EvaluationInconclusiveError as e:
            print(f"EVALUATION INCONCLUSIVE: the model was unavailable, so no quality verdict was possible. Details: {e}")
            _rollback_and_restore(snapshot_version, documents_before)
            record_metric(
                "pipeline_attempt",
                outcome="eval_inconclusive",
                attempt_number=attempt + 1,
                duration_seconds=round(time.time() - attempt_start, 1),
            )
            if _is_daily_quota_exhausted(e):
                print("Daily model quota is exhausted; retrying today cannot succeed. Update aborted. Run again after the quota resets.")
                return False
            new_attempt = _handle_failure_and_maybe_retry(attempt, "Evaluation could not run.")
            if new_attempt is None:
                return False
            attempt = new_attempt
            continue

        except Exception as e:
            print(f"Pipeline update failed with error: {e}")
            _rollback_and_restore(snapshot_version, documents_before)
            record_metric(
                "pipeline_attempt",
                outcome="crashed",
                attempt_number=attempt + 1,
                duration_seconds=round(time.time() - attempt_start, 1),
            )
            new_attempt = _handle_failure_and_maybe_retry(attempt, "Attempt crashed.")
            if new_attempt is None:
                return False
            attempt = new_attempt
            continue

    return False


if __name__ == "__main__":
    execute_pipeline_update_with_retries()
