"""One-time patch: Roman Malayalam person requests. Verifies every anchor, compiles the results and writes nothing
if any check fails. Run from the project root: python -m tools.patch_person_requests"""
import os
import shutil
import sys
import time

INTENTS = os.path.join("src", "multilingual", "intents.py")
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


def write(path, text, crlf):
    if crlf:
        text = text.replace("\n", "\r\n")
    with open(path, "w", encoding="utf-8", newline="") as handle:
        handle.write(text)


intents_text, intents_crlf = read(INTENTS)
lexicon_text, lexicon_crlf = read(LEXICON)
person_text, _ = read(PERSON)

if "lexicon_person" in intents_text:
    refuse("intents.py already uses lexicon_person; the patch looks applied")
try:
    compile(person_text, PERSON, "exec")
except SyntaxError as error:
    refuse("lexicon_person.py does not compile: %s" % error)

OLD_UNKNOWN = (
    "        if not strong:\n"
    "            unknown += 1\n"
    "            continue\n"
)
NEW_UNKNOWN = (
    "        if not strong:\n"
    "            if lexicon_person.person_request(keys, langs):\n"
    "                if not any(r[\"intent\"] == \"human_agent\" for r in requests):\n"
    "                    requests.append({\"intent\": \"human_agent\", \"score\": 0.75, \"clause\": clause})\n"
    "                continue\n"
    "            unknown += 1\n"
    "            continue\n"
)
intents_text = once(intents_text, OLD_UNKNOWN, NEW_UNKNOWN, "intents.py unknown branch")
intents_text = once(
    intents_text,
    "from src.multilingual import languages, lexicon\n",
    "from src.multilingual import languages, lexicon, lexicon_person\n",
    "intents.py import",
)

OLD_ML = '"cheyyu cheyyam cheyyamo kittiyilla vannilla panam thirich njan",'
NEW_ML = (
    '"cheyyu cheyyam cheyyamo kittiyilla vannilla panam thirich njan "\n'
    '          "vilikkaan vilikkam vilikkatte vilich vilichu samsarikkaan samsarikkam samsarikkamo samsarikkatte "\n'
    '          "samsaarikkaamo pattumo tharumo tharuvo cheyyatte cheyyattee cheyyuvo cheyyuvoo cheyyumo cheyyaamo "\n'
    '          "cheyth aalod aalodu aale",'
)
lexicon_text = once(lexicon_text, OLD_ML, NEW_ML, "lexicon.py ROMAN_WORDS ml")

for path, text in ((INTENTS, intents_text), (LEXICON, lexicon_text)):
    try:
        compile(text, path, "exec")
    except SyntaxError as error:
        refuse("%s would not compile: %s" % (path, error))

os.makedirs("backups", exist_ok=True)
for path in (INTENTS, LEXICON):
    shutil.copy2(path, os.path.join("backups", os.path.basename(path) + ".before_person_requests_" + STAMP + ".bak"))
write(INTENTS, intents_text, intents_crlf)
write(LEXICON, lexicon_text, lexicon_crlf)
print("patched", INTENTS, "and", LEXICON, "(backups in backups\\)")

try:
    from src.multilingual import intents
    out = intents.analyze("vilikkaan pattumo?", ["en", "hi", "ml", "ta", "te", "kn"], {})
    print("post-check intents for 'vilikkaan pattumo?':", ascii([r["intent"] for r in out["requests"]]))
except Exception as error:
    print("post-check raised:", ascii(repr(error)))