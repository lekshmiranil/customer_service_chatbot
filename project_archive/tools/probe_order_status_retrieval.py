"""Probe: does the Task 4 RAG layer retrieve the order-tracking FAQ for different wordings?

Uses no Gemini (phraser=None). Prints the decision and answer fields for each query.
Run from the project root: python -m tools.probe_order_status_retrieval
"""
import dataclasses

from src.rag.answer import answer_question
from src.rag.policy_select import UserContext
from src.rag.rag_bridge import get_knowledge

QUERIES = [
    "How do I check my order status and track my order? Order ID: ORD-12345.",
    "How do I check my order status and track my order?",
    "How do I track my order?",
    "how to track my order",
    "track my order ORD-12345",
    "Where can I see the delivery status of my order?",
]


def fields(answer):
    if dataclasses.is_dataclass(answer):
        return dataclasses.asdict(answer)
    try:
        return dict(vars(answer))
    except TypeError:
        return {"repr": repr(answer)}


def main():
    knowledge = get_knowledge()
    if knowledge is None:
        print("FAIL: no knowledge loaded (corpus missing or empty)")
        return
    corpus = knowledge.corpus
    print("corpus: documents=%d chunks=%d rejected=%d quarantined=%d"
          % (len(corpus.docs), len(corpus.chunks), len(corpus.rejected), len(corpus.quarantined)))
    ctx = UserContext("public", "GLOBAL")
    for number, query in enumerate(QUERIES, 1):
        print("")
        print("[%d] query: %s" % (number, ascii(query)))
        try:
            answer = answer_question(knowledge, query, ctx, today=None, phraser=None)
        except Exception as exc:
            print("    EXCEPTION: %s" % ascii(repr(exc)))
            continue
        for key, value in sorted(fields(answer).items()):
            print("    %s: %s" % (key, ascii(value)[:300]))


main()