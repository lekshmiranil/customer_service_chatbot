"""One-time patch: more Roman Malayalam words for language detection, and person words as stems so suffixes such as
'-umayi' still match. Verifies every anchor, compiles the results and writes nothing if any check fails.
Run from the project root: python -m tools.patch_ml_vocab"""
import os
import shutil
import sys
import time

LEXICON = os.path.join("src", "multilingual", "lexicon.py")
PERSON = os.path.join("src", "multilingual", "lexicon_person.py")
STAMP = time.strftime("%Y%m%d_%H%M%S")


def refuse(message):
    print("REFUSED:", message)
    print("Nothing was written.")
    sys.exit(1)


def read(path):
    if not os.path.isfile(path):
        refuse("missing file " + path)
    with open(path, "r", encoding="utf-8", newline="") as handle:
        raw = handle.read()
    return raw.replace("\r\n", "\n"), "\r\n" in raw


def once(text, old, new, label):
    count = text.count(old)
    if count != 1:
        refuse("%s: anchor found %d times, expected 1" % (label, count))
    return text.replace(old, new)


lexicon_text, lexicon_crlf = read(LEXICON)
person_text, person_crlf = read(PERSON)
if "person_stem" in person_text:
    refuse("lexicon_person.py already has person_stem; the patch looks applied")

lexicon_text = once(
    lexicon_text,
    '"cheyth aalod aalodu aale",',
    '"cheyth aalod aalodu aale "\n'
    '          "aanu pinne aayittu cheythu kittumo kittum kittilla enikk manushyanumayi",',
    "lexicon.py ml ROMAN_WORDS end",
)
person_text = once(
    person_text,
    '        "person_exact": "aalod aalodu aale aalu manushyan manushyanod manushyanodu manushya",\n',
    '        "person_exact": "aalod aalodu aale aalu manushyan manushyanod manushyanodu manushya",\n'
    '        "person_stem": "manushy aalod aale",\n',
    "lexicon_person.py groups",
)
person_text = once(
    person_text,
    '        person = _has(keys, table["person_exact"])\n',
    '        person = _has(keys, table["person_exact"], table["person_stem"])\n',
    "lexicon_person.py person check",
)

for path, text in ((LEXICON, lexicon_text), (PERSON, person_text)):
    try:
        compile(text, path, "exec")
    except SyntaxError as error:
        refuse("%s would not compile: %s" % (path, error))

os.makedirs("backups", exist_ok=True)
for path in (LEXICON, PERSON):
    shutil.copy2(path, os.path.join("backups", os.path.basename(path) + ".before_ml_vocab_" + STAMP + ".bak"))
for path, text, crlf in ((LEXICON, lexicon_text, lexicon_crlf), (PERSON, person_text, person_crlf)):
    with open(path, "w", encoding="utf-8", newline="") as handle:
        handle.write(text.replace("\n", "\r\n") if crlf else text)
print("patched", LEXICON, "and", PERSON, "(backups in backups\\)")