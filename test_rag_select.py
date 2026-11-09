"""Checks for src\\rag\\policy_select.py and src\\rag\\index.py on the synthetic corpus."""
import sys
import tempfile
from datetime import date

from make_rag_corpus import write_corpus
from src.rag.corpus_loader import load_corpus
from src.rag.dates_nl import parse_question_date
from src.rag.index import BM25Index
from src.rag.metadata import DocMeta
from src.rag.policy_select import UserContext, chunk_ids_for, detect_products, resolve

TODAY = date(2026, 10, 24)
failures = 0
total = 0


def check(name, condition):
    global failures, total
    total += 1
    if condition:
        print(f"PASS {name}")
    else:
        failures += 1
        print(f"FAIL {name}")


with tempfile.TemporaryDirectory() as tmp:
    write_corpus(tmp)
    corpus = load_corpus(tmp)
index = BM25Index(corpus.chunks)


def run(question, role="public", region="GLOBAL", as_of=None):
    """Mirrors the answer flow: products -> resolve -> search only the winners."""
    as_of = as_of or TODAY
    products = detect_products(question, corpus.products)
    res = resolve(corpus.docs, UserContext(role, region), as_of, products)
    ids = chunk_ids_for(corpus.chunks, res.winners.values())
    hits = index.search(question, ids)
    return res, hits


def winner(res, topic, product):
    meta = res.winners.get((topic, product))
    return meta.key if meta else None


def top_text(hits):
    return hits[0].chunk.text if hits else ""


# ---- refund policy: conflict, region override, dates
res, hits = run("What is the refund window for the HomeHub?", region="US")
check("current US refund is global v2", winner(res, "refund-policy", "homehub") == ("POL-REF-GL", "2"))
check("current US refund text says 15 days", "15 days" in top_text(hits))
res, hits = run("What is the refund window for the HomeHub?", region="IN")
check("current IN refund is the India document", winner(res, "refund-policy", "homehub") == ("POL-REF-IN", "1"))
check("current IN refund text says 20 days", "20 days" in top_text(hits))
res, hits = run("What is the refund window for the HomeHub?", region="EU")
check("current EU refund falls back to global v2", winner(res, "refund-policy", "homehub") == ("POL-REF-GL", "2"))
res, hits = run("What is the refund window for the HomeHub?", region="GLOBAL")
check("unspecified region holds the refund topic back", ("refund-policy", "homehub") in res.held and
      res.held[("refund-policy", "homehub")]["reason"] == "needs_region")
check("held refund topic is not a winner", winner(res, "refund-policy", "homehub") is None)
check("warranty has no regional variant so unspecified region still answers",
      winner(res, "warranty-policy", "homehub") == ("POL-WAR-GL", "2"))

res, hits = run("refund window HomeHub", region="IN", as_of=date(2025, 2, 10))
check("IN before its own document uses global v2", winner(res, "refund-policy", "homehub") == ("POL-REF-GL", "2"))
res, hits = run("refund window HomeHub", region="IN", as_of=date(2025, 3, 1))
check("India document applies on its effective day", winner(res, "refund-policy", "homehub") == ("POL-REF-IN", "1"))
res, hits = run("refund window HomeHub", region="US", as_of=date(2024, 6, 1))
check("2024 US refund is global v1", winner(res, "refund-policy", "homehub") == ("POL-REF-GL", "1"))
check("2024 US refund text says 30 days", "30 days" in top_text(hits))
res, _ = run("refund window HomeHub", region="US", as_of=date(2024, 12, 31))
check("last day of v1 still uses v1", winner(res, "refund-policy", "homehub") == ("POL-REF-GL", "1"))
res, _ = run("refund window HomeHub", region="US", as_of=date(2025, 1, 1))
check("first day of v2 uses v2", winner(res, "refund-policy", "homehub") == ("POL-REF-GL", "2"))
res, _ = run("refund window HomeHub", region="US", as_of=date(2026, 12, 31))
check("future v3 is ignored before it starts", winner(res, "refund-policy", "homehub") == ("POL-REF-GL", "2"))
res, _ = run("refund window HomeHub", region="US", as_of=date(2027, 2, 1))
check("v3 applies on its effective day", winner(res, "refund-policy", "homehub") == ("POL-REF-GL", "3"))
res, _ = run("refund window HomeHub", region="US", as_of=date(2022, 6, 1))
check("before any version there is no winner", winner(res, "refund-policy", "homehub") is None)
res, _ = run("refund window HomeHub", region="US")
check("current lookup never selects the future version", all(m.key != ("POL-REF-GL", "3") for m in res.winners.values()))
check("current lookup never selects the expired version", all(m.key != ("POL-REF-GL", "1") for m in res.winners.values()))
check("superseded and future documents are counted", res.excluded["not_yet_effective"] >= 1 and res.excluded["expired"] >= 3)

# ---- warranty, trade-in, CarePlus
res, hits = run("How long is the HomeHub warranty?")
check("current warranty is v2", winner(res, "warranty-policy", "homehub") == ("POL-WAR-GL", "2"))
check("current warranty says 24 months", "24 months" in top_text(hits))
res, hits = run("How long is the HomeHub warranty?", as_of=date(2025, 6, 1))
check("2025 warranty is v1 with 12 months", winner(res, "warranty-policy", "homehub") == ("POL-WAR-GL", "1") and "12 months" in top_text(hits))
res, _ = run("HomeHub warranty", as_of=date(2025, 12, 31))
check("warranty v1 on its last day", winner(res, "warranty-policy", "homehub") == ("POL-WAR-GL", "1"))
res, _ = run("HomeHub warranty", as_of=date(2026, 1, 1))
check("warranty v2 on its first day", winner(res, "warranty-policy", "homehub") == ("POL-WAR-GL", "2"))
res, _ = run("HomeHub trade-in credit")
check("expired trade-in has no current winner", winner(res, "trade-in-program", "homehub") is None)
res, hits = run("HomeHub trade-in credit", as_of=date(2025, 6, 1))
check("trade-in applies in its window", winner(res, "trade-in-program", "homehub") == ("POL-TRD-GL", "1") and "40 dollars" in top_text(hits))
res, _ = run("HomeHub trade-in credit", as_of=date(2025, 10, 1))
check("trade-in is gone the day after expiry", winner(res, "trade-in-program", "homehub") is None)
res, hits = run("How often does CarePlus cover accidental damage?")
check("current CarePlus is v1 (once per year)", winner(res, "careplus-benefits", "careplus") == ("POL-CP-GL", "1") and "once per year" in top_text(hits))
res, hits = run("How often does CarePlus cover accidental damage?", as_of=date(2026, 12, 1))
check("CarePlus v2 applies from its effective date", winner(res, "careplus-benefits", "careplus") == ("POL-CP-GL", "2") and "twice per year" in top_text(hits))
res, _ = run("CarePlus accidental damage", as_of=date(2024, 6, 1))
check("CarePlus has no winner before v1", winner(res, "careplus-benefits", "careplus") is None)
res, hits = run("What should I do when the HomeHub Wi-Fi light blinks amber?")
check("current troubleshooting is v2 (15 seconds)", winner(res, "wifi-troubleshooting", "homehub") == ("TS-WIFI-GL", "2") and "15 seconds" in top_text(hits))
res, hits = run("What should I do when the HomeHub Wi-Fi light blinks amber?", as_of=date(2025, 6, 1))
check("2025 troubleshooting is v1 (10 seconds)", winner(res, "wifi-troubleshooting", "homehub") == ("TS-WIFI-GL", "1") and "10 seconds" in top_text(hits))

# ---- ambiguity
res, _ = run("Can I cancel my HomeHub order?")
held = res.held.get(("cancellation-policy", "homehub"))
check("tied documents are held as ambiguous", held is not None and held["reason"] == "ambiguous")
check("tied group lists both documents", held is not None and {m.doc_id for m in held["docs"]} == {"POL-CAN-A", "POL-CAN-B"})
check("tied group has no winner", winner(res, "cancellation-policy", "homehub") is None)
res, _ = run("Can I cancel my HomeHub order?", as_of=date(2026, 2, 1))
check("before both documents there is nothing to tie", ("cancellation-policy", "homehub") not in res.held)

# ---- access
def winner_ids(role, region="US"):
    return {m.doc_id for m in run("anything", role, region)[0].winners.values()}


check("public sees no customer document", "FAQ-ORD-GL" not in winner_ids("public"))
check("public sees no internal document", not ({"TS-FW-INT", "INT-ESC-GL"} & winner_ids("public")))
check("public sees no restricted document", "RST-DISC-GL" not in winner_ids("public"))
check("customer sees the customer document", "FAQ-ORD-GL" in winner_ids("customer"))
check("customer sees no internal document", not ({"TS-FW-INT", "INT-ESC-GL"} & winner_ids("customer")))
check("internal sees internal documents", {"TS-FW-INT", "INT-ESC-GL"} <= winner_ids("internal"))
check("internal sees no restricted document", "RST-DISC-GL" not in winner_ids("internal"))
check("restricted sees the restricted document", "RST-DISC-GL" in winner_ids("restricted"))
check("unknown role sees nothing", winner_ids("hacker") == set())
res, hits = run("What discount can an agent approve?", "public", "US")
check("public discount question retrieves nothing", hits == [])
res, hits = run("What discount can an agent approve?", "internal", "US")
check("internal discount question retrieves nothing", all(h.chunk.doc_id != "RST-DISC-GL" for h in hits))
res, hits = run("What discount can an agent approve?", "restricted", "US")
check("restricted role retrieves the discount limit", hits and hits[0].chunk.doc_id == "RST-DISC-GL" and "12 percent" in top_text(hits))
check("access exclusions are counted for logs", run("x", "public", "US")[0].excluded["access"] >= 4)

# ---- region filtering
check("EU document is hidden from IN users", "FAQ-EU-EU" not in winner_ids("public", "IN"))
check("EU document is shown to EU users", "FAQ-EU-EU" in winner_ids("public", "EU"))
check("EU document is hidden when region is unspecified", "FAQ-EU-EU" not in winner_ids("public", "GLOBAL"))

# ---- product detection
check("homehub detected", detect_products("refund for the HomeHub?", corpus.products) == ["homehub"])
check("alias router detected", detect_products("my router blinks", corpus.products) == ["homehub"])
check("two words alias detected", detect_products("does Care Plus cover it", corpus.products) == ["careplus"])
check("two products detected", sorted(detect_products("HomeHub and CarePlus", corpus.products)) == ["careplus", "homehub"])
check("no product detected", detect_products("what are your opening hours", corpus.products) == [])
check("alias must match whole words", detect_products("superrouters", corpus.products) == [])
res, _ = run("CarePlus price")
check("product named in question filters other products", all(m.product in ("careplus", "all") for m in res.winners.values()))

# ---- synthetic rules
def mk(doc_id, version, region, access, eff, exp, topic="t-topic", product="homehub"):
    return DocMeta(doc_id, "T", "policy", topic, version, product, region, access,
                   date.fromisoformat(eff), date.fromisoformat(exp) if exp else None)


ctx = UserContext("public", "IN")
docs = [mk("G", "5", "GLOBAL", "public", "2026-05-01", None), mk("R", "1", "IN", "public", "2025-01-01", None)]
check("region document beats a newer global one", resolve(docs, ctx, TODAY).winners[("t-topic", "homehub")].doc_id == "R")
docs = [mk("A", "1", "GLOBAL", "public", "2025-01-01", None), mk("B", "1", "GLOBAL", "public", "2025-06-01", None)]
check("latest effective date wins", resolve(docs, ctx, TODAY).winners[("t-topic", "homehub")].doc_id == "B")
docs = [mk("A", "2.9", "GLOBAL", "public", "2025-01-01", None), mk("A", "2.10", "GLOBAL", "public", "2025-01-01", None)]
check("higher version wins on equal date", resolve(docs, ctx, TODAY).winners[("t-topic", "homehub")].version == "2.10")
docs = [mk("A", "1", "GLOBAL", "public", "2025-01-01", None), mk("B", "1", "GLOBAL", "restricted", "2025-01-01", None)]
res = resolve(docs, ctx, TODAY)
check("a restricted twin cannot make a public group ambiguous", res.winners[("t-topic", "homehub")].doc_id == "A" and not res.held)
docs = [mk("A", "1", "GLOBAL", "public", "2025-01-01", None), mk("B", "9", "GLOBAL", "restricted", "2026-01-01", None)]
check("a newer restricted version never replaces what the user may see", resolve(docs, ctx, TODAY).winners[("t-topic", "homehub")].doc_id == "A")
docs = [mk("A", "1", "GLOBAL", "public", "2025-01-01", None, product="homehub"),
        mk("B", "1", "GLOBAL", "public", "2025-01-01", None, product="careplus")]
res = resolve(docs, ctx, TODAY)
check("different products never conflict", len(res.winners) == 2 and not res.held)
check("empty document list resolves to nothing", resolve([], ctx, TODAY).winners == {})

# ---- retrieval
res, hits = run("What is the capital of France?", "restricted", "US")
check("unrelated question matches nothing", hits == [])
res, hits = run("What is the refund window for the HomeHub?", region="US")
check("hits carry coverage", hits and 0 < hits[0].coverage <= 1)
check("hits come only from winning documents", all(h.chunk.doc_id == "POL-REF-GL" and h.chunk.version == "2" for h in hits if h.chunk.meta.topic == "refund-policy"))
check("search respects the allowed id set", index.search("refund window", allowed_chunk_ids=set()) == [])
check("search is deterministic", [h.chunk.chunk_id for h in index.search("refund window")] == [h.chunk.chunk_id for h in index.search("refund window")])
check("empty question returns nothing", index.search("   ") == [] and index.search("what is the") == [])
check("shipping answer survives injection removal", any("3 to 5 business days" in h.chunk.text for h in run("How long does HomeHub shipping take?")[1]))
check("password answer survives injection removal", any("Reset password" in h.chunk.text for h in run("How do I reset my HomeHub password?")[1]))

print(f"checks: {total}, failed: {failures}")
sys.exit(1 if failures else 0)