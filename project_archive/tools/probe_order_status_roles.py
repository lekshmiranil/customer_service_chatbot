"""Probe: does the order-tracking FAQ become reachable for other roles? Uses no Gemini (phraser=None).
Run from the project root: python -m tools.probe_order_status_roles
"""
from src.rag.answer import answer_question
from src.rag.metadata import ACCESS_LEVELS, REGIONS
from src.rag.policy_select import UserContext
from src.rag.rag_bridge import get_knowledge

QUERIES = [
    "How do I check my order status and track my order? Order ID: ORD-12345.",
    "How do I check my order status and track my order?",
    "How do I track my order?",
    "track my order ORD-12345",
]


def main():
    knowledge = get_knowledge()
    if knowledge is None:
        print("FAIL: no knowledge loaded")
        return
    print("ACCESS_LEVELS: %s" % ascii(ACCESS_LEVELS))
    print("REGIONS: %s" % ascii(REGIONS))
    roles = list(ACCESS_LEVELS)
    for role in roles:
        print("")
        print("role: %s" % ascii(role))
        for number, query in enumerate(QUERIES, 1):
            try:
                answer = answer_question(knowledge, query, UserContext(role, "GLOBAL"), today=None, phraser=None)
            except Exception as exc:
                print("  [%d] EXCEPTION %s" % (number, ascii(repr(exc))))
                continue
            cited = [c["doc_id"] for c in answer.citations]
            print("  [%d] status=%s reason=%s cited=%s" % (number, answer.status, answer.reason, ascii(cited)))
            print("      text: %s" % ascii(answer.text)[:220])


main()