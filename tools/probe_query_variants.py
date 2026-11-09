"""Probe: which part of the 'Order ID' suffix lowers retrieval coverage? No Gemini (phraser=None).
Run from the project root: python -m tools.probe_query_variants
"""
from src.multilingual import lexicon
from src.rag.answer import MIN_COVERAGE, _search_text, answer_question, clean_question
from src.rag.dates_nl import get_today, parse_question_date
from src.rag.metadata import can_access
from src.rag.policy_select import UserContext, detect_products
from src.rag.rag_bridge import get_knowledge

ORDER = lexicon.CANONICAL_QUERY["order_status"]
REFUND = lexicon.CANONICAL_QUERY["refund"]

CASES = [
    ("1 order_status plain", ORDER, "customer", "GLOBAL"),
    ("2 + ' Order ID.'", ORDER + " Order ID.", "customer", "GLOBAL"),
    ("3 + ' ORD-12345.'", ORDER + " ORD-12345.", "customer", "GLOBAL"),
    ("4 + ' 12345.'", ORDER + " 12345.", "customer", "GLOBAL"),
    ("5 + ' Order ID: ORD-12345.'", ORDER + " Order ID: ORD-12345.", "customer", "GLOBAL"),
    ("6 + ' Date: 2026-10-01.'", ORDER + " Date: 2026-10-01.", "customer", "GLOBAL"),
    ("7 order_status joined with refund", ORDER + " " + REFUND, "customer", "GLOBAL"),
    ("8 refund plain, region IN", REFUND, "customer", "IN"),
    ("9 refund + Order ID, region IN", REFUND + " Order ID: ORD-12345.", "customer", "IN"),
    ("10 refund + Date, region IN", REFUND + " Date: 2026-10-01.", "customer", "IN"),
]


def coverage_info(knowledge, query, role):
    today = get_today()
    cleaned, _ = clean_question(query)
    intent = parse_question_date(cleaned, today)
    products = detect_products(cleaned, knowledge.corpus.products)
    search_text = _search_text(cleaned, intent, products, knowledge.corpus.products)
    allowed = {c.chunk_id for c in knowledge.corpus.chunks if can_access(role, c.meta.access_level)}
    hits = knowledge.index.search(search_text, allowed, k=5)
    return search_text, (hits[0] if hits else None)


def main():
    knowledge = get_knowledge()
    if knowledge is None:
        print("FAIL: no knowledge loaded")
        return
    print("MIN_COVERAGE = %s" % MIN_COVERAGE)
    for label, query, role, region in CASES:
        print("")
        print("[%s] role=%s region=%s" % (label, role, region))
        try:
            search_text, top = coverage_info(knowledge, query, role)
            print("    search_text: %s" % ascii(search_text))
            if top is None:
                print("    top hit: none")
            else:
                print("    top hit: %s coverage=%.2f matched=%s" % (
                    top.chunk.doc_id, top.coverage, ascii(sorted(top.matched_terms))))
            answer = answer_question(knowledge, query, UserContext(role, region), today=None, phraser=None)
            cited = [c["doc_id"] for c in answer.citations]
            print("    result: %s/%s intent=%s as_of=%s cited=%s" % (
                answer.status, answer.reason, answer.intent_kind, answer.as_of, ascii(cited)))
            notes = [line for line in answer.text.split("\n") if line.startswith("Note:")]
            for note in notes:
                print("    %s" % ascii(note)[:200])
        except Exception as exc:
            print("    EXCEPTION %s" % ascii(repr(exc)))


main()