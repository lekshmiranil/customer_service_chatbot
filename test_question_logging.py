"""Checks that answer_question never logs question text. Run: python test_question_logging.py"""

import ast
import sys
import time
from pathlib import Path

QUESTION = (
    "I am Priya Nair of 12 Main Street, card 378282246310005, "
    "email x@example.com, where is my refund for order 4111"
)
PRIVATE = ["Priya", "Nair", "Main Street", "378282246310005", "example.com", "4111"]

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


class Chain:
    def __init__(self, fail):
        self.fail = fail

    def invoke(self, payload):
        if self.fail:
            raise RuntimeError("simulated failure")
        return {"result": "ok"}


def load_answer_question(injection, fail):
    source = Path("src/main.py").read_text(encoding="utf-8")
    tree = ast.parse(source)
    node = next(
        (n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == "answer_question"),
        None,
    )
    if node is None:
        return None, []
    logged = []
    namespace = {
        "time": time,
        "record": lambda event, **fields: logged.append((event, fields)),
        "mask_sensitive_data": lambda text: text,
        "detect_prompt_injection": lambda text: injection,
        "retrieval_confidence": lambda db, q: 0.9,
        "vectordb": None,
        "chain": Chain(fail),
        "CONFIDENCE_THRESHOLD": 0.4,
    }
    exec(ast.get_source_segment(source, node), namespace)
    return namespace["answer_question"], logged


def main():
    function, _ = load_answer_question(False, False)
    check("answer_question found in src/main.py", function is not None)
    if function is None:
        return 1

    paths = [
        ("injection blocked", True, False),
        ("normal answer", False, False),
        ("error", False, True),
    ]
    for label, injection, fail in paths:
        function, logged = load_answer_question(injection, fail)
        function(QUESTION)
        check(f"{label}: one log event", len(logged) == 1)
        text = repr(logged).lower()
        check(f"{label}: no question text in the log", not any(p.lower() in text for p in PRIVATE))
        fields = logged[0][1] if logged else {}
        check(f"{label}: only the length is logged", fields.get("question_chars") == len(QUESTION))

    print(f"\n{checks - failures}/{checks} checks passed")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())