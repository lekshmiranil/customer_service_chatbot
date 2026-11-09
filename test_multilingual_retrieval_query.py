"""Retrieval question for the knowledge assistant. The order ID, product code and date stay in the query and in
state, but the text used for retrieval must not carry them (an unmatched ID lowers coverage below the floor and
the 'Date' label pulls the wrong policy). Written BEFORE the fix. No network, no Gemini, no database.
The canonical wording check is fitted to one finding: FAQ-ORD-GL has the heading 'How do I track my order?'."""
import sys

sys.stdout.reconfigure(errors="backslashreplace")

from src.multilingual import config, dialogue, lexicon, summary
from src.rag.answer import answer_question
from src.rag.policy_select import UserContext
from src.rag.rag_bridge import get_knowledge

failures = 0
CFG = config.get_config()


def check(label, condition):
    global failures
    if condition:
        print("ok   " + label)
    else:
        print("FAIL " + label)
        failures += 1


def run(text):
    return dialogue.handle_message(summary.empty_state("en"), text, CFG, "")[1]


def ask(knowledge, question, role, region):
    return answer_question(knowledge, question, UserContext(role, region), today=None, phraser=None)


try:
    r = run("order details of ORD-12345")
    check("order_status query produced", r.get("kind") == "query" and "order_status" in (r.get("intents") or []))
    check("query still keeps the order id", "ORD-12345" in str(r.get("query")))
    rq = str(r.get("retrieval_query") or "")
    check("retrieval_query exists", bool(rq))
    check("retrieval_query has no order id", bool(rq) and "ORD" not in rq and "12345" not in rq)
    check("retrieval_query is the canonical question", rq == lexicon.CANONICAL_QUERY["order_status"])
    check("canonical order_status wording (fitted to FAQ-ORD-GL)",
          lexicon.CANONICAL_QUERY["order_status"] == "How do I track my order?")

    r2 = run("I want a refund for order ORD-12345")
    check("refund request found", r2.get("kind") == "query" and "refund" in (r2.get("intents") or []))
    check("refund: query keeps the order id", "ORD-12345" in str(r2.get("query")))
    rq2 = str(r2.get("retrieval_query") or "")
    check("refund: retrieval_query exists and has no order id", bool(rq2) and "12345" not in rq2)

    knowledge = get_knowledge()
    check("corpus loaded", knowledge is not None)
    if knowledge is not None:
        question = rq or str(r.get("query"))
        a = ask(knowledge, question, "customer", "GLOBAL")
        check("customer: tracking FAQ answers", a.status == "answered" and [c["doc_id"] for c in a.citations] == ["FAQ-ORD-GL"])
        check("customer: no 'nothing about' note", "Note:" not in a.text)
        p = ask(knowledge, question, "public", "GLOBAL")
        check("public: still refused (access level unchanged)", p.status == "refused" and not p.citations)
        question2 = rq2 or str(r2.get("query"))
        b = ask(knowledge, question2, "customer", "IN")
        check("refund IN: answered from the India policy",
              b.status == "answered" and "POL-REF-IN" in [c["doc_id"] for c in b.citations])
except Exception as exc:
    print("FAIL exception: " + ascii(repr(exc)))
    failures += 1

print("")
print("FAILED: %d" % failures if failures else "all ok")
sys.exit(1 if failures else 0)