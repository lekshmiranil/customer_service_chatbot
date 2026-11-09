"""Rule-based conversation summary and the state carried into a restored session. No model, no Streamlit.
The summary is structured data. replies.py turns it into a sentence in the customer's language."""
from src.multilingual import entities


def empty_state(language="en"):
    return {
        "slots": entities.empty_slots(), "language": language, "languages": [], "intents_handled": [],
        "open_requests": [], "message_count": 0, "carried_messages": 0, "pending": None,
        "last_intents": [], "restored": False,
    }


def build(state, ended_at="", reason=""):
    state = state or {}
    slots = state.get("slots") or {}
    return {
        "name": str(slots.get("name") or ""),
        "order_ids": list(slots.get("order_ids") or []),
        "product_codes": list(slots.get("product_codes") or []),
        "dates": list(slots.get("dates") or []),
        "corrections": list(slots.get("corrections") or [])[-5:],
        "languages": list(state.get("languages") or []),
        "language": str(state.get("language") or ""),
        "intents_handled": list(state.get("intents_handled") or []),
        "open_requests": list(state.get("open_requests") or []),
        "message_count": int(state.get("message_count") or 0) + int(state.get("carried_messages") or 0),
        "ended_at": str(ended_at or ""),
        "reason": str(reason or ""),
    }


def has_content(summary):
    return bool(summary) and int(summary.get("message_count") or 0) > 0


def carry_state(summary, default_language="en"):
    """The starting state of a session restored from a summary: remembered values, languages and open requests."""
    summary = summary or {}
    state = empty_state(summary.get("language") or default_language)
    slots = state["slots"]
    slots["name"] = str(summary.get("name") or "")
    slots["order_ids"] = list(summary.get("order_ids") or [])
    slots["product_codes"] = list(summary.get("product_codes") or [])
    slots["dates"] = list(summary.get("dates") or [])
    slots["corrections"] = list(summary.get("corrections") or [])
    state["languages"] = list(summary.get("languages") or [])
    state["intents_handled"] = list(summary.get("intents_handled") or [])
    state["open_requests"] = list(summary.get("open_requests") or [])
    state["carried_messages"] = int(summary.get("message_count") or 0)
    state["restored"] = True
    return state


def text(summary):
    """A short English description, used in logs and in the evaluation report."""
    summary = summary or {}
    parts = []
    if summary.get("name"):
        parts.append("customer " + summary["name"])
    if summary.get("order_ids"):
        parts.append("orders " + ", ".join(summary["order_ids"]))
    if summary.get("product_codes"):
        parts.append("products " + ", ".join(summary["product_codes"]))
    if summary.get("dates"):
        parts.append("dates " + ", ".join(summary["dates"]))
    if summary.get("intents_handled"):
        parts.append("handled " + ", ".join(summary["intents_handled"]))
    if summary.get("open_requests"):
        parts.append("open " + ", ".join(summary["open_requests"]))
    if summary.get("languages"):
        parts.append("languages " + ", ".join(summary["languages"]))
    if summary.get("corrections"):
        parts.append("corrections " + str(len(summary["corrections"])))
    return "; ".join(parts) if parts else "no details"