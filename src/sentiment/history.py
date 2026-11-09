"""Adjusts one message's scores using the earlier customer messages of the same conversation."""
from src.sentiment.classify import finalize


def apply_history(current, previous):
    """previous: dicts with a negative_type flag, oldest first. Returns a new result with context_notes."""
    scores = {k: v for k, v in current["scores"].items() if k != "neutral"}
    meta = {"resolved": current["resolved"], "praise_strong": current["praise_strong"]}
    notes = []
    flags = [bool(p.get("negative_type")) for p in previous[-3:]]

    if (current["praise_strong"] and not current["resolved"] and not current["negative_type"]
            and len(flags) >= 2 and all(flags[-2:])):
        scores["sarcastic"] = max(scores.get("sarcastic", 0.0), 0.6)
        scores["positive"] = 0.0
        notes.append("praise after two negative messages is treated as likely sarcasm")
    if current["negative_type"] and sum(flags) >= 2:
        scores["frustrated"] = max(scores.get("frustrated", 0.0), 0.6)
        notes.append("repeated negative messages raise the frustration score")

    result = finalize(scores, meta)
    result["context_notes"] = notes
    return result