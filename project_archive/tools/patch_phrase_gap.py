"""One-time patch: allow one extra word inside a cue phrase of three or more words. Verifies every anchor, compiles
the result and writes nothing if any check fails. Run from the project root: python -m tools.patch_phrase_gap"""
import os
import shutil
import sys
import time

INTENTS = os.path.join("src", "multilingual", "intents.py")
STAMP = time.strftime("%Y%m%d_%H%M%S")


def refuse(message):
    print("REFUSED:", message)
    print("Nothing was written.")
    sys.exit(1)


def once(text, old, new, label):
    count = text.count(old)
    if count != 1:
        refuse("%s: anchor found %d times, expected 1" % (label, count))
    return text.replace(old, new)


if not os.path.isfile(INTENTS):
    refuse("missing file " + INTENTS)
with open(INTENTS, "r", encoding="utf-8", newline="") as handle:
    raw = handle.read()
crlf = "\r\n" in raw
text = raw.replace("\r\n", "\n")
if "def _gapped(" in text:
    refuse("intents.py already has _gapped; the patch looks applied")

OLD_LOOP = '''    for phrase in spec["phrases"]:
        size = len(phrase)
        for start in range(len(keys) - size + 1):
            weights = [_match(keys[start + offset], phrase[offset], cutoff) for offset in range(size)]
            if all(weights):
                found["p:" + " ".join(phrase)] = (min(weights), set(range(start, start + size)))
    return found
'''
NEW_LOOP = '''    for phrase in spec["phrases"]:
        size = len(phrase)
        label = "p:" + " ".join(phrase)
        for start in range(len(keys) - size + 1):
            weights = [_match(keys[start + offset], phrase[offset], cutoff) for offset in range(size)]
            if all(weights):
                found[label] = (min(weights), set(range(start, start + size)))
        if label not in found and size >= 3:
            gapped = _gapped(keys, phrase, cutoff)
            if gapped:
                found[label] = gapped
    return found
'''
GAPPED = '''def _gapped(keys, phrase, cutoff):
    """Best (weight, positions) for the phrase words in order with exactly one extra word between two of them, else
    None. The weight is cut by 10 percent so a phrase with an extra word ranks below the same phrase without one."""
    best = None
    for first in range(len(keys)):
        weight = _match(keys[first], phrase[0], cutoff)
        if not weight:
            continue
        stack = [(first, 1, [weight], [first], False)]
        while stack:
            last, index, weights, positions, gap = stack.pop()
            if index == len(phrase):
                if gap:
                    value = min(weights) * 0.9
                    if best is None or value > best[0]:
                        best = (value, set(positions))
                continue
            for step in (1, 2):
                if step == 2 and gap:
                    continue
                nxt = last + step
                if nxt >= len(keys):
                    continue
                score = _match(keys[nxt], phrase[index], cutoff)
                if score:
                    stack.append((nxt, index + 1, weights + [score], positions + [nxt], gap or step == 2))
    return best


def _hits(keys, spec, cutoff):
'''
text = once(text, OLD_LOOP, NEW_LOOP, "intents.py _hits phrase loop")
text = once(text, "def _hits(keys, spec, cutoff):\n", GAPPED, "intents.py _hits definition")
try:
    compile(text, INTENTS, "exec")
except SyntaxError as error:
    refuse("intents.py would not compile: %s" % error)

os.makedirs("backups", exist_ok=True)
shutil.copy2(INTENTS, os.path.join("backups", "intents.py.before_phrase_gap_" + STAMP + ".bak"))
if crlf:
    text = text.replace("\n", "\r\n")
with open(INTENTS, "w", encoding="utf-8", newline="") as handle:
    handle.write(text)
print("patched", INTENTS, "(backup in backups\\)")