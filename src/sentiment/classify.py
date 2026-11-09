"""Rule-based message classifier: six labels with scores from 0 to 1 and a confidence."""
from src.sentiment import lexicon as L

LABELS = ("positive", "neutral", "negative", "frustrated", "urgent", "sarcastic")
PRIORITY = ("sarcastic", "frustrated", "urgent", "negative", "positive")  # tie order, strongest first
NEGATIVE_TYPES = ("negative", "frustrated", "sarcastic")
FLAG_THRESHOLD = 0.4


def raw_scores(text):
    value = L.normalize(text)
    original = str(text or "")
    letters = [c for c in original if c.isalpha()]
    shouting = len(letters) >= 8 and sum(c.isupper() for c in letters) / len(letters) > 0.6
    exclaim = original.count("!")
    neg = L.hits(value, L.NEGATIVE)
    fru = L.hits(value, L.FRUSTRATED)
    urg = L.hits(value, L.URGENT)
    thanks = L.hits(value, L.THANKS)
    praise = L.hits(value, L.PRAISE)
    fail = L.hits(value, L.FAILURE)
    strong = L.hits(value, L.SARCASM_STRONG)
    resolved = bool(L.hits(value, L.RESOLVED)) and not L.NOT_RESOLVED_RE.search(value)

    negative = 0.45 * len(neg) + (0.2 if fail else 0.0)
    if negative > 0 and exclaim:
        negative += 0.1
    frustrated = 0.55 * len(fru)
    if fru and (exclaim >= 2 or shouting):
        frustrated += 0.15
    urgent = 0.6 * len(urg)
    sarcastic = 0.0
    if strong:
        sarcastic = 0.8
    elif praise and (fail or neg) and not resolved:
        sarcastic = 0.7 if fail else 0.6
    positive = 0.5 * (len(thanks) + len(praise))
    if sarcastic >= FLAG_THRESHOLD:
        positive = 0.0
    elif negative >= FLAG_THRESHOLD or frustrated >= FLAG_THRESHOLD:
        positive *= 0.3
    scores = {"positive": positive, "negative": negative, "frustrated": frustrated,
              "urgent": urgent, "sarcastic": sarcastic}
    return scores, {"praise_strong": bool(praise), "resolved": resolved}


def finalize(scores, meta=None):
    meta = meta or {}
    s = {label: round(min(1.0, max(0.0, float(scores.get(label, 0.0)))), 2) for label in PRIORITY}
    s["neutral"] = round(max(0.0, 0.8 - max(s.values())), 2)
    flags = [label for label in PRIORITY if s[label] >= FLAG_THRESHOLD]
    if flags:
        label = max(flags, key=lambda name: (s[name], -PRIORITY.index(name)))
        second = max([s[name] for name in flags if name != label], default=0.0)
        confidence = max(0.4, min(0.95, s[label] - 0.25 * second))
    else:
        label = "neutral"
        confidence = max(0.4, min(0.8, s["neutral"]))
    return {
        "label": label,
        "confidence": round(confidence, 2),
        "scores": s,
        "flags": flags,
        "negative_type": bool(set(flags) & set(NEGATIVE_TYPES)),
        "urgent": "urgent" in flags,
        "positive": "positive" in flags,
        "resolved": bool(meta.get("resolved")),
        "praise_strong": bool(meta.get("praise_strong")),
    }


def classify_message(text):
    scores, meta = raw_scores(text)
    return finalize(scores, meta)