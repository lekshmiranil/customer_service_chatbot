"""Probe: does one filler word inside a cue phrase still match, grouped by phrase length? Measurement only.
Run from the project root: python -m tools.probe_phrase_gap"""
from src.multilingual import intents, lexicon

LANGS = ["en", "hi", "ml", "ta", "te", "kn"]


def found(text):
    return [r["intent"] for r in intents.analyze(text, LANGS, {})["requests"]]


stats = {}
failures = []
seen = set()
for intent in lexicon.INTENT_ORDER:
    for lang in LANGS:
        cue = lexicon.INTENT_CUES.get(intent, {}).get(lang)
        if not cue:
            continue
        for phrase in cue["p"]:
            low = phrase.lower()
            parts = low.split()
            if lexicon.is_native_text(low) or len(parts) < 2 or (intent, low) in seen:
                continue
            seen.add((intent, low))
            if intent not in found(low):
                continue
            variant = " ".join([parts[0], "please"] + parts[1:])
            ok = intent in found(variant)
            size = len(parts)
            stats.setdefault(size, [0, 0])
            stats[size][0] += 1
            stats[size][1] += 1 if ok else 0
            if not ok and size >= 3:
                failures.append((intent, lang, low, variant, found(variant)))
print("== filler word after the first word, passed/tested by phrase length")
for size in sorted(stats):
    print("  %d words: %d/%d" % (size, stats[size][1], stats[size][0]))
print("== failures among phrases of 3 or more words:", len(failures))
for item in failures[:15]:
    print("  ", ascii(item))