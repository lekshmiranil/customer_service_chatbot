from dotenv import load_dotenv
import os

load_dotenv()  # Loads variables from .env

import json
import time
from pathlib import Path

EVAL_DATASET_PATH = Path("dataset/eval_qa.json")

# Configurable via .env:
#   EVAL_RETRY_DELAYS_SECONDS  comma-separated waits between attempts for one
#                              question (default "5,15" -> up to 3 attempts)
EVAL_RETRY_DELAYS_SECONDS = [
    float(x) for x in os.getenv("EVAL_RETRY_DELAYS_SECONDS", "5,15").split(",") if x.strip()
]

TRANSIENT_MARKERS = (
    "503", "UNAVAILABLE", "500", "INTERNAL", "504", "DEADLINE_EXCEEDED",
    "429", "RESOURCE_EXHAUSTED", "timed out", "timeout", "connection",
)
DAILY_QUOTA_MARKERS = ("PerDay", "per_day", "requests_per_day")


class EvaluationInconclusiveError(Exception):
    """Raised when the evaluation could not produce a valid quality verdict
    because the model or network was unavailable. This is an infrastructure
    problem, not a content quality failure."""


def _is_infrastructure_error(exc: Exception) -> bool:
    message = str(exc)
    return any(marker.lower() in message.lower() for marker in TRANSIENT_MARKERS)


def _is_daily_quota_error(exc: Exception) -> bool:
    message = str(exc)
    return any(marker.lower() in message.lower() for marker in DAILY_QUOTA_MARKERS)


def create_default_eval_set():
    """Creates a default evaluation set if one doesn't exist."""
    if not EVAL_DATASET_PATH.exists():
        EVAL_DATASET_PATH.parent.mkdir(parents=True, exist_ok=True)
        default_evals = [
            {
                "question": "What is the return policy?",
                "expected_keywords": ["return", "days", "refund"]
            }
        ]
        with open(EVAL_DATASET_PATH, "w") as f:
            json.dump(default_evals, f, indent=4)


def _ask_with_backoff(chain, question: str) -> str:
    """Asks one question, retrying transient infrastructure errors with backoff.
    Returns the lowercased answer text.
    Raises EvaluationInconclusiveError if the model stays unavailable or the
    daily quota is exhausted. Any other exception propagates unchanged."""
    max_attempts = len(EVAL_RETRY_DELAYS_SECONDS) + 1

    for attempt in range(1, max_attempts + 1):
        try:
            response = chain.invoke({"query": question})
            return response.get("result", "").lower()
        except Exception as e:
            if not _is_infrastructure_error(e):
                raise

            if _is_daily_quota_error(e):
                raise EvaluationInconclusiveError(
                    f"Daily model quota exhausted while evaluating '{question}': {e}"
                ) from e

            if attempt == max_attempts:
                raise EvaluationInconclusiveError(
                    f"Model unavailable after {max_attempts} attempts "
                    f"while evaluating '{question}': {e}"
                ) from e

            delay = EVAL_RETRY_DELAYS_SECONDS[attempt - 1]
            print(
                f"Transient model error on '{question}' "
                f"(attempt {attempt}/{max_attempts}). Retrying in {delay:.0f}s..."
            )
            time.sleep(delay)

    # Unreachable, kept so the function always returns or raises.
    raise EvaluationInconclusiveError(f"Evaluation ended unexpectedly for '{question}'.")


QUALITY_BASELINE_PATH = Path("dataset/quality_baseline.json")

# Result of the most recent passing evaluation. It becomes the baseline only
# after the update has been deployed and has survived the health window.
_last_evaluation = None


def _eval_set_fingerprint() -> str:
    import hashlib
    return hashlib.sha256(EVAL_DATASET_PATH.read_bytes()).hexdigest()


def _load_quality_baseline():
    """Returns the baseline dict, or None if it is missing, unreadable, or was
    recorded for a different evaluation set (scores would not be comparable)."""
    try:
        with open(QUALITY_BASELINE_PATH, "r") as f:
            baseline = json.load(f)
    except FileNotFoundError:
        return None
    except (OSError, ValueError) as e:
        print(f"Quality baseline unreadable ({e}); regression check skipped.")
        return None

    if not isinstance(baseline.get("score"), (int, float)):
        print("Quality baseline has no valid score; regression check skipped.")
        return None

    if baseline.get("eval_set_sha256") != _eval_set_fingerprint():
        print("Quality baseline was recorded for a different evaluation set; regression check skipped.")
        return None

    return baseline


def commit_quality_baseline():
    """Records the last passing evaluation as the baseline for future updates.
    Call only after the update is deployed and verified stable. Mock runs
    never write a baseline."""
    if _last_evaluation is None:
        return

    if os.getenv("DRY_RUN_LLM", "false").strip().lower() == "true":
        print("Dry run: quality baseline not updated.")
        return

    QUALITY_BASELINE_PATH.parent.mkdir(parents=True, exist_ok=True)
    temp_path = QUALITY_BASELINE_PATH.with_suffix(".tmp")
    with open(temp_path, "w") as f:
        json.dump(_last_evaluation, f, indent=4)
    temp_path.replace(QUALITY_BASELINE_PATH)
    print(f"Quality baseline updated to {_last_evaluation['score'] * 100}%.")


def run_quality_evaluation(qa_chain_func) -> bool:

    """
    Runs test questions through the QA chain to check accuracy and grounding.
    Returns True if the update passes the quality threshold and does not score
    below the currently deployed knowledge base, False otherwise.
    An empty evaluation set cannot verify anything, so it fails the gate.
    Raises EvaluationInconclusiveError if the model was unavailable, so that
    an outage is not reported as a quality failure.
    """
    global _last_evaluation
    _last_evaluation = None

    create_default_eval_set()

    with open(EVAL_DATASET_PATH, "r") as f:
        eval_cases = json.load(f)

    passed_tests = 0
    total_tests = len(eval_cases)

    if total_tests == 0:
        print("Quality evaluation has no test cases; an update cannot be verified, so it is rejected.")
        return False

    # Build the chain ONCE, reuse it for every question: avoids reloading
    # the embedding model and FAISS index repeatedly, which is slow and
    # memory-heavy.
    chain = qa_chain_func()

    for case in eval_cases:
        question = case["question"]
        expected_keywords = case["expected_keywords"]

        try:
            answer = _ask_with_backoff(chain, question)

            # Check if expected keywords exist in the response (basic grounding/accuracy proxy)
            matches = sum(1 for kw in expected_keywords if kw.lower() in answer)
            if matches >= len(expected_keywords) * 0.5:  # At least 50% keyword match
                passed_tests += 1
        except EvaluationInconclusiveError:
            # No valid verdict is possible; stop immediately rather than
            # spending more quota on the remaining questions.
            raise
        except Exception as e:
            print(f"Eval test failed for question '{question}': {e}")

    success_rate = passed_tests / total_tests
    print(f"Quality Evaluation Score: {success_rate * 100}%")

    # Require at least 70% pass rate to approve update
    if success_rate < 0.7:
        return False

    # Reject updates that score below the currently deployed knowledge base
    baseline = _load_quality_baseline()
    if baseline is not None and success_rate + 1e-9 < baseline["score"]:
        print(
            f"Quality regression: score {success_rate * 100}% is below the "
            f"deployed baseline of {baseline['score'] * 100}%."
        )
        return False

    _last_evaluation = {
        "score": success_rate,
        "passed": passed_tests,
        "total": total_tests,
        "eval_set_sha256": _eval_set_fingerprint(),
    }
    return True