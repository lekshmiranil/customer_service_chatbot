"""Unsupported-claim detection: every line of an answer must be backed by the chunk it cites.

A line passes only when ALL of these hold:
  * it carries a citation like [POL-REF-GL v2, Refund window]
  * the citation names a chunk that is really in the evidence set
  * at least 80 percent of its content words appear in the cited text
  * every number in it appears in the cited text
  * it does not drop or add a negation compared with the closest source sentence
  * it contains no instruction-like text
Lines that fail are never shown to the customer. This check is deterministic and needs no model.
"""
import re
from dataclasses import dataclass, field

from src.rag.index import tokenize
from src.rag.injection_scan import scan_text

CITATION_RE = re.compile(r"\[([A-Za-z0-9][A-Za-z0-9_.-]*) v(\d+(?:\.\d+)*), ([^\[\]]+)\]")
_NEGATION_RE = re.compile(r"\b(?:not|no|never|cannot|without|none|neither|nor)\b|n't", re.IGNORECASE)
_NUMBER_RE = re.compile(r"\d+(?:[.,]\d+)*")
SUPPORT_RATIO = 0.8


@dataclass
class VerifyResult:
    ok: bool
    problems: list = field(default_factory=list)  # dicts: line, reason, detail
    checked: int = 0


def format_citation(chunk):
    section = re.sub(r"[\[\]\r\n]+", " ", chunk.section).strip() or chunk.meta.title
    return f"[{chunk.doc_id} v{chunk.version}, {section}]"


def split_sentences(text):
    return [s.strip() for s in re.split(r"(?<=[.!?])\s+", (text or "").strip()) if s.strip()]


def _numbers(text):
    return {n.replace(",", "") for n in _NUMBER_RE.findall(text or "")}


def _negated(text):
    return bool(_NEGATION_RE.search(text or ""))


def _best_source_sentence(sentence, source_text):
    tokens = set(tokenize(sentence))
    best, best_score = "", -1.0
    for candidate in split_sentences(source_text):
        cand_tokens = set(tokenize(candidate))
        if not cand_tokens:
            continue
        score = len(tokens & cand_tokens) / len(tokens | cand_tokens)
        if score > best_score:
            best, best_score = candidate, score
    return best


def _check_sentence(sentence, cited_chunks):
    """Returns a list of (reason, detail) problems for one sentence."""
    problems = []
    tokens = set(tokenize(sentence))
    if len(tokens) < 2:
        return [("too_little_content", sentence[:60])]
    source_text = " ".join(c.text for c in cited_chunks)
    source_tokens = set(tokenize(source_text))
    missing = sorted(tokens - source_tokens)
    if 1 - len(missing) / len(tokens) < SUPPORT_RATIO:
        problems.append(("unsupported_terms", ", ".join(missing[:6])))
    stray = sorted(_numbers(sentence) - _numbers(source_text))
    if stray:
        problems.append(("number_not_in_source", ", ".join(stray)))
    best = _best_source_sentence(sentence, source_text)
    if best and _negated(sentence) != _negated(best):
        problems.append(("negation_mismatch", sentence[:60]))
    return problems


def verify_answer(body, evidence):
    """`body` is the answer text (one cited statement per line); `evidence` is the list of Chunk objects
    the answer was allowed to use."""
    by_key = {}
    for chunk in evidence:
        by_key.setdefault((chunk.doc_id, chunk.version), []).append(chunk)
    lines = [line.strip() for line in (body or "").splitlines() if line.strip()]
    if not lines:
        return VerifyResult(False, [{"line": "", "reason": "empty_answer", "detail": ""}], 0)

    result = VerifyResult(True)
    for line in lines:
        citations = CITATION_RE.findall(line)
        text = CITATION_RE.sub(" ", line).strip()
        if not re.search(r"[A-Za-z0-9]", text):
            continue
        result.checked += 1
        found = []
        if scan_text(text):
            found.append(("injected_content", text[:60]))
        if not citations:
            found.append(("no_citation", text[:60]))
        cited = []
        for doc_id, version, section in citations:
            matches = [c for c in by_key.get((doc_id, version), [])
                       if c.section.strip().lower() == section.strip().lower()]
            if not matches:
                found.append(("citation_not_in_evidence", f"{doc_id} v{version}, {section}"))
            cited.extend(matches)
        if cited and not found:
            for sentence in split_sentences(text):
                found.extend(_check_sentence(sentence, cited))
        for reason, detail in found:
            result.problems.append({"line": text[:80], "reason": reason, "detail": detail})
    if result.checked == 0:
        result.problems.append({"line": "", "reason": "empty_answer", "detail": "no statement to check"})
    result.ok = not result.problems
    return result