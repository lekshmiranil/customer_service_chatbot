"""Probe: how well does the Roman-script matcher cope with spelling variants of its own cue words and phrases?
Measurement only, writes nothing. Run from the project root: python -m tools.probe_spelling_variants"""
from src.multilingual import intents, lexicon

LANGS = ["en", "hi", "ml", "ta", "te", "kn"]
MAX_SHOWN = 5
USER_08_TEXT = "vilich samsarikkaan pattumo?"


def found(text):
    out = intents.analyze(text, LANGS, {})
    return [r["intent"] for r in out["requests"]]


def v_double_vowel(w):
    for i, ch in enumerate(w):
        if ch in "aiu":
            return w[:i] + ch + w[i:]
    return None


def v_single_vowel(w):
    for pair, single in (("aa", "a"), ("ii", "i"), ("uu", "u"), ("ee", "i"), ("oo", "u")):
        if pair in w:
            return w.replace(pair, single, 1)
    return None


def v_ee(w):
    return w.replace("i", "ee", 1) if "i" in w else None


def v_oo(w):
    return w.replace("u", "oo", 1) if "u" in w else None


def v_aspirate(w):
    for i, ch in enumerate(w):
        if ch in "tdkgb" and (i + 1 >= len(w) or w[i + 1] != "h"):
            return w[:i + 1] + "h" + w[i + 1:]
    return None


def v_vw(w):
    if "v" in w:
        return w.replace("v", "w", 1)
    if "w" in w:
        return w.replace("w", "v", 1)
    return None


def v_double_consonant(w):
    for i in range(1, len(w)):
        ch = w[i]
        if ch.isalpha() and ch not in "aeiouh" and w[i - 1] != ch and (i + 1 >= len(w) or w[i + 1] != ch):
            return w[:i] + ch + w[i:]
    return None


def v_swap(w):
    if len(w) >= 6 and w[2] != w[3]:
        return w[:2] + w[3] + w[2] + w[4:]
    return None


def v_delete(w):
    if len(w) >= 6:
        return w[:2] + w[3:]
    return None


def v_vowel_sub(w):
    if len(w) < 6:
        return None
    table = {"a": "e", "e": "a", "i": "e", "o": "u", "u": "o"}
    for i in range(1, len(w)):
        if w[i] in table:
            return w[:i] + table[w[i]] + w[i + 1:]
    return None


WORD_KINDS = [
    ("double_vowel", v_double_vowel), ("single_vowel", v_single_vowel), ("ee_for_i", v_ee), ("oo_for_u", v_oo),
    ("aspirate_added", v_aspirate), ("v_w_swap", v_vw), ("double_consonant", v_double_consonant),
    ("typo_swap", v_swap), ("typo_delete", v_delete), ("typo_vowel_sub", v_vowel_sub),
]


def phrase_filler(words):
    return " ".join([words[0], "please"] + words[1:])


def phrase_drop_last(words):
    return " ".join(words[:-1]) if len(words) >= 3 else None


PHRASE_KINDS = [("phrase_filler_word", phrase_filler), ("phrase_drop_last", phrase_drop_last)]


def trace(text):
    print("== trace of", ascii(text))
    keys = intents._keys(text)
    print("keys:", ascii(keys))
    out = intents.analyze(text, LANGS, {})
    print("requests:", ascii([(r["intent"], r["score"]) for r in out["requests"]]),
          "unknown clauses:", out["unknown"], "ambiguous:", ascii(out["ambiguous"]))
    index = intents._build(LANGS)
    for token in keys:
        best = (0.0, "", "")
        for intent, spec in index.items():
            for cue in spec["words"]:
                weight = intents._match(token, cue, 0.8)
                if weight > best[0]:
                    best = (round(weight, 3), cue, intent)
        print("token", ascii(token), "best single-word cue", ascii(best))
    shown = 0
    for intent, spec in index.items():
        for phrase in spec["phrases"]:
            matched = [p for p in phrase if any(intents._match(t, p, 0.8) for t in keys)]
            if matched and len(matched) < len(phrase) and shown < 10:
                print("partial phrase", intent, ascii(phrase), "matched only", ascii(matched))
                shown += 1


def main():
    trace(USER_08_TEXT)
    words, phrases = [], []
    seen_w, seen_p = set(), set()
    for intent in lexicon.INTENT_ORDER:
        for lang in LANGS:
            cue = lexicon.INTENT_CUES.get(intent, {}).get(lang)
            if not cue:
                continue
            for w in cue["w"].split():
                low = w.lower()
                if lexicon.is_native_text(low) or len(low) < 3 or (intent, low) in seen_w:
                    continue
                seen_w.add((intent, low))
                words.append((intent, lang, low))
            for p in cue["p"]:
                low = p.lower()
                if lexicon.is_native_text(low) or len(low.split()) < 2 or (intent, low) in seen_p:
                    continue
                seen_p.add((intent, low))
                phrases.append((intent, lang, low))
    stats, fails, base_fail = {}, {}, []
    for intent, lang, word in words:
        if intent not in found(word):
            base_fail.append(("word", intent, lang, word, found(word)))
            continue
        for kind, fn in WORD_KINDS:
            variant = fn(word)
            if not variant or variant == word:
                continue
            ok = intent in found(variant)
            stats.setdefault(kind, [0, 0])
            stats[kind][0] += 1
            stats[kind][1] += 1 if ok else 0
            if not ok:
                fails.setdefault(kind, []).append((intent, lang, word, variant, found(variant)))
    for intent, lang, phrase in phrases:
        if intent not in found(phrase):
            base_fail.append(("phrase", intent, lang, phrase, found(phrase)))
            continue
        parts = phrase.split()
        for kind, fn in PHRASE_KINDS:
            variant = fn(parts)
            if not variant:
                continue
            ok = intent in found(variant)
            stats.setdefault(kind, [0, 0])
            stats[kind][0] += 1
            stats[kind][1] += 1 if ok else 0
            if not ok:
                fails.setdefault(kind, []).append((intent, lang, phrase, variant, found(variant)))
    print("== counts: roman words", len(words), "roman phrases", len(phrases))
    print("== baseline failures (the unmodified cue is not found):", len(base_fail))
    for item in base_fail[:10]:
        print("  BASE", ascii(item))
    print("== variant results (passed/tested)")
    for kind in [k for k, _ in WORD_KINDS] + [k for k, _ in PHRASE_KINDS]:
        if kind in stats:
            print("  %-20s %d/%d" % (kind, stats[kind][1], stats[kind][0]))
    for kind, items in fails.items():
        print("== first failures:", kind)
        for item in items[:MAX_SHOWN]:
            print("  ", ascii(item))


main()