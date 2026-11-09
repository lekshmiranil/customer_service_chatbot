"""The decision flow: answer, ask for clarification, or refuse. Deterministic end to end.

Order of work:
  1. strip instruction-like sentences from the question (the question is data too)
  2. relevance check over the documents the user is allowed to read
  3. work out the date the question is about (current, historical, future, unclear)
  4. authorise, apply region and dates, resolve conflicts (policy_select) -- per date checked
  5. rank only the surviving documents; hold back ambiguous or region-dependent topics
  6. build the answer from cited source sentences, verify every line, or refuse
A model may only re-phrase already approved passages (the optional `phraser`); its output
is verified line by line and replaced by the extractive answer if anything is unsupported.
"""
import re
from dataclasses import dataclass, field

from src.rag.dates_nl import check_dates, get_today, parse_question_date
from src.rag.index import BM25Index, STOPWORDS, stem, tokenize
from src.rag.injection_scan import normalize_for_scan, scan_text
from src.rag.metadata import can_access
from src.rag.policy_select import UserContext, chunk_ids_for, detect_products, resolve
from src.rag.verify import format_citation, split_sentences, verify_answer

MIN_COVERAGE = 0.5      # share of the question's content words a passage must match
RELATIVE_SCORE = 0.7    # other passages must score at least this share of the best one
RELATIVE_COVERAGE = 0.75  # ...and cover at least this share of the best passage's coverage
MAX_EVIDENCE_CHUNKS = 3
MAX_LINES = 6
MAX_QUESTION_CHARS = 1000
_FILLER = {
    "long", "often", "take", "takes", "usually", "exactly", "really", "actually", "tell", "explain",
    "describe", "info", "information", "details", "detail", "help", "know", "bought", "purchased",
    "ordered", "previously", "earlier", "before", "compare", "comparison",
}

MSG_NO_EVIDENCE = ("I couldn't find a reliable answer to that in the documents available to you, "
                   "so I won't guess. You can rephrase the question or ask a human agent to follow up.")
MSG_NOT_IN_FORCE = ("I couldn't find a policy on this that is in force for the date you asked about. "
                    "I can only answer from policies that were in force on that date.")
MSG_AMBIGUOUS = ("I found conflicting sources for this question and can't tell which one is correct, "
                 "so I won't pick one. A human agent can confirm the right answer.")
MSG_NEEDS_REGION = ("The answer depends on your region. Please choose your region in the sidebar "
                    "(India, US or EU) and ask again.")
MSG_PERIOD_CHANGED = ("The policy on this topic changed during that period, so the answer depends on the exact "
                      "date. Which single date should I use? Please give it as YYYY-MM-DD.")
MSG_EMPTY = "Please type a question about our products, policies or troubleshooting."
MSG_TOO_LONG = "That question is too long. Please shorten it to a few sentences."
MSG_BLOCKED = "I can only answer questions about our products and policies. Please rephrase your question."
MSG_VERIFY_FAILED = ("I couldn't confirm an answer against the documents, so I won't give one. "
                     "A human agent can help.")


class Knowledge:
    """A loaded corpus plus its search index."""

    def __init__(self, corpus):
        self.corpus = corpus
        self.index = BM25Index(corpus.chunks)


@dataclass
class RagAnswer:
    status: str                      # answered | clarify | refused | error
    text: str                        # what the customer sees
    reason: str = ""                 # short code for logs and tests
    needs: str = ""                  # for clarify: date | exact_date | region
    body: str = ""                   # the verified, cited answer lines only
    citations: list = field(default_factory=list)
    verified: bool = False
    model_used: bool = False
    model_rejected: bool = False
    flagged_question: bool = False
    intent_kind: str = ""
    as_of: str = ""
    stats: dict = field(default_factory=dict)


# ---------------------------------------------------------------- helpers
def clean_question(question):
    """Drops sentences that look like instructions. Returns (cleaned_text, anything_was_dropped)."""
    text = normalize_for_scan(question)
    parts = [p for p in re.split(r"(?<=[.!?;])\s+", text) if p]
    kept = [p for p in parts if not scan_text(p)]
    return " ".join(kept).strip(), len(kept) != len(parts)


def _remove_phrase(text, phrase):
    if not phrase:
        return text
    return re.sub(re.escape(phrase), " ", text, flags=re.IGNORECASE)


def _search_text(question, intent, products, catalog):
    """The question minus date words, product names and filler: what is left must be covered by evidence."""
    text = _remove_phrase(question, intent.matched.split(";")[0] if intent.matched else "")
    if intent.matched and ";" in intent.matched:
        for part in intent.matched.split(";"):
            text = _remove_phrase(text, part.strip())
    for slug in products:
        for alias in catalog.get(slug, {}).get("aliases", []):
            text = re.sub(rf"\b{re.escape(alias)}\b", " ", text, flags=re.IGNORECASE)
    words = [w for w in re.findall(r"[A-Za-z0-9]+", text) if w.lower() not in _FILLER]
    return " ".join(words)


def _citation_dict(chunk):
    meta = chunk.meta
    return {
        "doc_id": chunk.doc_id, "version": chunk.version, "title": meta.title, "section": chunk.section,
        "region": meta.region, "product": meta.product, "chunk_id": chunk.chunk_id,
        "effective_date": meta.effective_date.isoformat(),
        "expiry_date": meta.expiry_date.isoformat() if meta.expiry_date else None,
    }


def _evaluate(knowledge, search_text, ctx, as_of, products):
    """Runs authorisation, dates and conflict rules for one date, then ranks the survivors."""
    corpus, index = knowledge.corpus, knowledge.index
    res = resolve(corpus.docs, ctx, as_of, products)
    winner_ids = chunk_ids_for(corpus.chunks, res.winners.values())
    held_of = {}
    for group, info in res.held.items():
        for meta in info["docs"]:
            held_of[meta.key] = info["reason"]
    held_ids = chunk_ids_for(corpus.chunks, [m for info in res.held.values() for m in info["docs"]])
    hits = index.search(search_text, winner_ids | held_ids, k=8)
    if not hits:
        return {"kind": "none", "hits": [], "keys": (), "res": res}
    top = hits[0].score
    coverage_floor = max(MIN_COVERAGE, RELATIVE_COVERAGE * max(h.coverage for h in hits))
    relevant = [h for h in hits if h.coverage >= coverage_floor and h.score >= RELATIVE_SCORE * top]
    if not relevant:
        return {"kind": "none", "hits": [], "keys": (), "res": res}
    reasons = {held_of[(h.chunk.doc_id, h.chunk.version)] for h in relevant
               if (h.chunk.doc_id, h.chunk.version) in held_of}
    if reasons:
        reason = "ambiguous" if "ambiguous" in reasons else "needs_region"
        return {"kind": "held", "reason": reason, "hits": [], "keys": (), "res": res}
    chosen = relevant[:MAX_EVIDENCE_CHUNKS]
    keys = tuple(sorted((h.chunk.doc_id, h.chunk.version) for h in chosen))
    return {"kind": "ok", "hits": chosen, "keys": keys, "res": res}


def _extract_lines(hits):
    """Source sentences that mention a matched term, each with its citation."""
    lines, seen = [], set()
    for hit in hits:
        sentences = split_sentences(hit.chunk.text)
        picked = [s for s in sentences if set(tokenize(s)) & hit.matched_terms] or sentences[:1]
        for sentence in picked:
            if sentence in seen:
                continue
            seen.add(sentence)
            lines.append((sentence, hit.chunk))
    return lines[:MAX_LINES]


def _original_words(search_text):
    words = []
    for word in re.findall(r"[A-Za-z0-9]+", search_text):
        if word.lower() in STOPWORDS:
            continue
        words.append(word)
    return words


def _notes(search_text, hits, question_wo_dates):
    notes = []
    matched = set()
    for hit in hits:
        matched |= set(hit.matched_terms)
    unmatched = []
    for word in _original_words(search_text):
        term = stem(word.lower())
        if term not in matched and not term.isdigit() and word.lower() not in [u.lower() for u in unmatched]:
            unmatched.append(word)
    if unmatched:
        shown = ", ".join(f"'{w}'" for w in unmatched[:3])
        notes.append(f"Note: I found nothing about {shown} in the documents available to you, "
                     "so this answer does not cover it.")
    evidence_numbers = set()
    for hit in hits:
        evidence_numbers |= {n.replace(",", "") for n in re.findall(r"\d+(?:[.,]\d+)*", hit.chunk.text)}
    stray = []
    for number in re.findall(r"\b\d+(?:\.\d+)?\b", question_wo_dates):
        if number not in evidence_numbers and number not in stray:
            stray.append(number)
    if stray:
        notes.append(f"Note: your question mentions {', '.join(stray[:3])}, which does not appear in the "
                     "policy text I found.")
    return notes


def _refuse(reason, text, intent, **extra):
    return RagAnswer(status="refused", text=text, reason=reason, intent_kind=intent.kind if intent else "",
                     as_of=intent.as_of.isoformat() if intent and intent.as_of else "", **extra)


def _clarify(reason, needs, text, intent, **extra):
    return RagAnswer(status="clarify", text=text, reason=reason, needs=needs,
                     intent_kind=intent.kind if intent else "",
                     as_of=intent.as_of.isoformat() if intent and intent.as_of else "", **extra)


# ---------------------------------------------------------------- main entry
def answer_question(knowledge, question, ctx, today=None, phraser=None):
    today = today or get_today()
    corpus = knowledge.corpus
    raw = question or ""
    if len(raw) > MAX_QUESTION_CHARS:
        return _refuse("question_too_long", MSG_TOO_LONG, None)
    if not raw.strip():
        return _refuse("empty_question", MSG_EMPTY, None)
    cleaned, flagged = clean_question(raw)
    if not cleaned:
        return _refuse("question_blocked", MSG_BLOCKED, None, flagged_question=True)

    intent = parse_question_date(cleaned, today)
    products = detect_products(cleaned, corpus.products)
    search_text = _search_text(cleaned, intent, products, corpus.products)
    extra = {"flagged_question": flagged}

    # Relevance over what this user may read (any date, any region): decides "no evidence" first.
    allowed = {c.chunk_id for c in corpus.chunks if can_access(ctx.role, c.meta.access_level)}
    first = knowledge.index.search(search_text, allowed, k=5)
    if not first or first[0].coverage < MIN_COVERAGE:
        return _refuse("no_evidence", MSG_NO_EVIDENCE, intent, **extra)

    if intent.kind == "future":
        return _refuse("future_date", intent.reason, intent, **extra)
    if intent.kind in ("unresolved", "ambiguous"):
        return _clarify(f"date_{intent.kind}", "date", intent.reason, intent, **extra)

    results = [_evaluate(knowledge, search_text, ctx, d, products) for d in check_dates(intent)]
    stats = {"excluded": results[0]["res"].excluded}
    extra["stats"] = stats
    if len(results) == 2:
        kinds = {r["kind"] for r in results}
        if len(kinds) > 1 or (kinds == {"ok"} and results[0]["keys"] != results[1]["keys"]):
            return _clarify("policy_changed_in_period", "exact_date", MSG_PERIOD_CHANGED, intent, **extra)
    outcome = results[0]

    if outcome["kind"] == "held":
        if outcome["reason"] == "ambiguous":
            return _refuse("ambiguous_sources", MSG_AMBIGUOUS, intent, **extra)
        return _clarify("needs_region", "region", MSG_NEEDS_REGION, intent, **extra)
    if outcome["kind"] == "none":
        status_now = first[0].chunk.meta.status_on(check_dates(intent)[0])
        if status_now in ("expired", "future"):
            return _refuse("not_in_force", MSG_NOT_IN_FORCE, intent, **extra)
        return _refuse("not_applicable", MSG_NO_EVIDENCE, intent, **extra)

    hits = outcome["hits"]
    # Keep only source lines that pass the verifier on their own; an unverifiable line is dropped, not shown.
    lines = [(sentence, chunk) for sentence, chunk in _extract_lines(hits)
             if verify_answer(f"{sentence} {format_citation(chunk)}", [chunk]).ok]
    if not lines:
        return _refuse("verification_failed", MSG_VERIFY_FAILED, intent, **extra)
    evidence = []
    for _, chunk in lines:
        if chunk not in evidence:
            evidence.append(chunk)
    hits = [h for h in hits if h.chunk in evidence]
    extractive = "\n\n".join(f"{sentence} {format_citation(chunk)}" for sentence, chunk in lines)

    body, model_used, model_rejected = extractive, False, False
    if phraser is not None:
        try:
            candidate = phraser(cleaned, evidence)
        except Exception:
            candidate = None
        if candidate and verify_answer(candidate, evidence).ok:
            body, model_used = candidate.strip(), True
        else:
            model_rejected = True
    check = verify_answer(body, evidence)
    if not check.ok:
        return _refuse("verification_failed", MSG_VERIFY_FAILED, intent,
                       model_rejected=model_rejected, **extra)

    question_wo_dates = _remove_phrase(cleaned, intent.matched)
    parts = []
    if intent.kind == "historical":
        if intent.range_end:
            parts.append(f"Based on the policy in force from {intent.as_of.isoformat()} to "
                         f"{intent.range_end.isoformat()} (it did not change in that period):")
        else:
            parts.append(f"Based on the policy in force on {intent.as_of.isoformat()}:")
    parts.append(body)
    parts.extend(_notes(search_text, hits, question_wo_dates))
    seen, citations = set(), []
    for chunk in evidence:
        c = _citation_dict(chunk)
        marker = (c["doc_id"], c["version"], c["section"])
        if marker not in seen:
            seen.add(marker)
            citations.append(c)
    return RagAnswer(status="answered", text="\n\n".join(parts), reason="ok", body=body,
                     citations=citations, verified=True, model_used=model_used,
                     model_rejected=model_rejected, flagged_question=flagged,
                     intent_kind=intent.kind, as_of=intent.as_of.isoformat(), stats=stats)