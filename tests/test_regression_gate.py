import json
import os
import sys
import tempfile
from pathlib import Path

from src.pipeline import evaluator

os.environ["DRY_RUN_LLM"] = "false"

QUESTIONS = [
    {"question": f"Question {i}?", "expected_keywords": ["alpha"]}
    for i in range(1, 6)
]

failures = []


def check(name, actual, expected):
    status = "PASS" if actual == expected else "FAIL"
    print(f"{status}: {name} (got {actual!r}, expected {expected!r})")
    if actual != expected:
        failures.append(name)


def make_chain_func(correct_count):
    answers = iter(["alpha"] * correct_count + ["nothing"] * (5 - correct_count))

    class Chain:
        def invoke(self, inputs):
            return {"result": next(answers)}

    return lambda: Chain()


def write_eval(path, cases):
    path.write_text(json.dumps(cases), encoding="utf-8")


def write_baseline(path, score, eval_path):
    path.write_text(json.dumps({
        "score": score,
        "passed": int(score * 5),
        "total": 5,
        "eval_set_sha256": evaluator._eval_set_fingerprint(),
    }), encoding="utf-8")


with tempfile.TemporaryDirectory() as tmp:
    tmp_dir = Path(tmp)
    eval_path = tmp_dir / "eval.json"
    baseline_path = tmp_dir / "quality_baseline.json"
    evaluator.EVAL_DATASET_PATH = eval_path
    evaluator.QUALITY_BASELINE_PATH = baseline_path

    write_eval(eval_path, QUESTIONS)

    check("no baseline, 4/5 passes absolute threshold",
          evaluator.run_quality_evaluation(make_chain_func(4)), True)

    check("3/5 fails absolute threshold",
          evaluator.run_quality_evaluation(make_chain_func(3)), False)

    write_baseline(baseline_path, 1.0, eval_path)
    check("baseline 100%, 4/5 is rejected as a regression",
          evaluator.run_quality_evaluation(make_chain_func(4)), False)
    check("rejected run leaves nothing to commit",
          evaluator._last_evaluation, None)

    check("baseline 100%, 5/5 passes",
          evaluator.run_quality_evaluation(make_chain_func(5)), True)
    evaluator.commit_quality_baseline()
    saved = json.loads(baseline_path.read_text(encoding="utf-8"))
    check("commit writes the new baseline score", saved["score"], 1.0)

    write_baseline(baseline_path, 0.8, eval_path)
    check("baseline 80%, 4/5 equal score passes",
          evaluator.run_quality_evaluation(make_chain_func(4)), True)

    write_baseline(baseline_path, 1.0, eval_path)
    write_eval(eval_path, QUESTIONS[:4])
    check("baseline for a different eval set is ignored",
          evaluator.run_quality_evaluation(make_chain_func(3)), True)

    write_eval(eval_path, [])
    check("empty eval set is rejected",
          evaluator.run_quality_evaluation(make_chain_func(0)), False)

if failures:
    print(f"\n{len(failures)} check(s) failed: {failures}")
    sys.exit(1)

print("\nAll checks passed.")