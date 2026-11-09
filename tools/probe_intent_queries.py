"""Probe: canonical query per intent, with and without an order-ID suffix, for roles public and customer.
No Gemini (phraser=None). Run from the project root: python -m tools.probe_intent_queries
"""
from src.multilingual import lexicon
from src.rag.answer import answer_question
from src.rag.policy_select import UserContext
from src.rag.rag_bridge import get_knowledge

SUFFIX = " Order ID: ORD-12345."


def main():
    knowledge = get_knowledge()
    if knowledge is None:
        print("FAIL: no knowledge loaded")
        return
    for role in ("public", "customer"):
        print("")
        print("role: %s" % role)
        for intent, base in sorted(lexicon.CANONICAL_QUERY.items()):
            for label, query in (("plain", base), ("with-id", base + SUFFIX)):
                try:
                    answer = answer_question(knowledge, query, UserContext(role, "GLOBAL"), today=None, phraser=None)
                except Exception as exc:
                    print("  %-15s %-8s EXCEPTION %s" % (intent, label, ascii(repr(exc))))
                    continue
                cited = [c["doc_id"] for c in answer.citations]
                print("  %-15s %-8s %s/%s %s" % (intent, label, answer.status, answer.reason, ascii(cited)))


main()