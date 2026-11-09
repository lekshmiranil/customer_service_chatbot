"""The single entry point the Streamlit app calls: ask(question, role, region).

Loads the corpus once, reloads it when any file in the corpus folder changes, never raises,
and writes one log line per question (no question or answer text is logged).
"""
import os
import threading
import time
from pathlib import Path

from src.rag.answer import Knowledge, RagAnswer, answer_question
from src.rag.corpus_loader import load_corpus
from src.rag.metadata import ACCESS_LEVELS, REGIONS
from src.rag.policy_select import UserContext
from src.rag.rag_log import log_event

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
MSG_UNAVAILABLE = "The knowledge base isn't available right now. A human agent can help with your question."
MSG_ERROR = "Something went wrong while answering. A human agent can help with your question."

_lock = threading.Lock()
_state = {"fingerprint": None, "knowledge": None}


def corpus_dir():
    return Path(os.environ.get("RAG_CORPUS_DIR") or (PROJECT_ROOT / "rag_corpus"))


def _fingerprint(folder):
    if not folder.is_dir():
        return None
    return tuple(sorted((p.name, p.stat().st_size, p.stat().st_mtime_ns) for p in folder.glob("*") if p.is_file()))


def get_knowledge():
    """Returns the loaded Knowledge, or None when the corpus folder is missing or holds no usable document."""
    folder = corpus_dir()
    fingerprint = _fingerprint(folder)
    with _lock:
        if fingerprint != _state["fingerprint"] or _state["knowledge"] is None:
            knowledge = None
            if fingerprint:
                corpus = load_corpus(folder)
                if corpus.docs:
                    knowledge = Knowledge(corpus)
                log_event("corpus_load", documents=len(corpus.docs), chunks=len(corpus.chunks),
                          rejected=len(corpus.rejected), quarantined=len(corpus.quarantined),
                          rejected_files=[r["file"] for r in corpus.rejected][:20])
            _state["fingerprint"] = fingerprint
            _state["knowledge"] = knowledge
        return _state["knowledge"]


def corpus_summary():
    knowledge = get_knowledge()
    if knowledge is None:
        return {"available": False, "documents": 0, "chunks": 0, "rejected": 0, "quarantined": 0}
    c = knowledge.corpus
    return {"available": True, "documents": len(c.docs), "chunks": len(c.chunks),
            "rejected": len(c.rejected), "quarantined": len(c.quarantined)}


def ask(question, role="public", region="GLOBAL", phraser=None, today=None):
    started = time.time()
    role_used = (role or "").strip().lower()
    role_fixed = role_used not in ACCESS_LEVELS
    if role_fixed:
        role_used = "public"  # an unknown role gets the least access, never more
    region_used = (region or "").strip().upper()
    if region_used not in REGIONS:
        region_used = "GLOBAL"
    try:
        knowledge = get_knowledge()
        if knowledge is None:
            answer = RagAnswer(status="refused", text=MSG_UNAVAILABLE, reason="no_corpus")
        else:
            answer = answer_question(knowledge, question, UserContext(role_used, region_used),
                                     today=today, phraser=phraser)
    except Exception as exc:
        answer = RagAnswer(status="error", text=MSG_ERROR, reason=f"exception:{type(exc).__name__}")
    log_event(
        "ask", status=answer.status, reason=answer.reason, needs=answer.needs, role=role_used,
        region=region_used, role_normalized=role_fixed, question_chars=len(question or ""),
        flagged_question=answer.flagged_question, intent=answer.intent_kind, as_of=answer.as_of,
        cited=[f"{c['doc_id']} v{c['version']}" for c in answer.citations], verified=answer.verified,
        model_used=answer.model_used, model_rejected=answer.model_rejected,
        excluded=answer.stats.get("excluded") if answer.stats else None,
        latency_ms=round((time.time() - started) * 1000),
    )
    return answer