"""Language packs: one JSON file per language in config\\languages (or the folder named in MULTILINGUAL_PACKS_DIR).
A pack adds a new language or replaces fields of an existing one without editing Python. A pack is validated
completely first; an invalid pack is rejected as a whole and reported, the other packs still load.

Pack fields (all JSON, UTF-8):
  code          required, 2 to 8 lowercase letters
  name          display name; required for a new code
  text          {reply key: template}; a new code needs every key of replies.TEXT; placeholders must match English
  labels        {intent: short name}; a new code needs every intent of replies.LABELS
  roman_words   one string of space separated Roman-letter words typical for the language
  cues          {intent: {"w": "words", "p": ["phrase", ...]}}
  markers       {"correction"|"followup"|"plural"|"yes": "words"}
  person        {call_exact, call_stem, talk_stem, person_exact, person_stem, ask_stem, call_ask_ending: "words"}
  name_markers  [["my", "name"], ...] phrases that introduce a name
  name_stop     ["word", ...] words that end a name
  name_words    ["word", ...] words a customer uses to name the language
  script_range  [low, high] code point range of the script, must not overlap another language
Each field you give replaces that field for the language. Plain Python, standard library only. Never raises."""
import json
import os
import re
import string
from pathlib import Path

from src.multilingual import config, entities, intents, languages, lexicon, lexicon_person, replies

PERSON_KEYS = ("call_exact", "call_stem", "talk_stem", "person_exact", "person_stem", "ask_stem", "call_ask_ending")
KNOWN_FIELDS = {
    "code", "name", "text", "labels", "roman_words", "cues", "markers", "person",
    "name_markers", "name_stop", "name_words", "script_range",
}
_CODE_RE = re.compile(r"[a-z]{2,8}")


def packs_dir(path=None):
    return Path(path or os.getenv("MULTILINGUAL_PACKS_DIR", "").strip() or (config.ROOT / "config" / "languages"))


def _text(value):
    return isinstance(value, str) and bool(value.strip())


def _fields(template):
    try:
        return {name for _, name, _, _ in string.Formatter().parse(template) if name is not None}
    except ValueError:
        return None


def _is_new(code):
    return code not in lexicon.LANG_NAMES


def validate(data):
    """None when the pack is valid, else the reason as a string."""
    if not isinstance(data, dict):
        return "the pack is not a JSON object"
    unknown = sorted(set(data) - KNOWN_FIELDS)
    if unknown:
        return "unknown field(s): " + ", ".join(unknown)
    code = data.get("code")
    if not isinstance(code, str) or not _CODE_RE.fullmatch(code):
        return "code must be 2 to 8 lowercase letters"
    new = _is_new(code)
    if "name" in data and not _text(data["name"]):
        return "name must be a non-empty string"
    if new and "name" not in data:
        return "a new language needs a name"

    text = data.get("text")
    if text is not None:
        if not isinstance(text, dict):
            return "text must be an object"
        for key, value in text.items():
            if key not in replies.TEXT:
                return "unknown reply key: " + str(key)
            if not _text(value):
                return "empty reply text for key " + key
            if _fields(value) is None or _fields(value) != _fields(replies.TEXT[key]["en"]):
                return "placeholders of reply '%s' do not match the English template" % key
    if new:
        missing = [key for key in replies.TEXT if not _text((text or {}).get(key))]
        if missing:
            return "a new language needs every reply key; missing: " + ", ".join(missing)

    labels = data.get("labels")
    if labels is not None:
        if not isinstance(labels, dict):
            return "labels must be an object"
        for key, value in labels.items():
            if key not in replies.LABELS:
                return "unknown label intent: " + str(key)
            if not _text(value):
                return "empty label for " + key
    if new:
        missing = [key for key in replies.LABELS if not _text((labels or {}).get(key))]
        if missing:
            return "a new language needs every label; missing: " + ", ".join(missing)

    if "roman_words" in data and not isinstance(data["roman_words"], str):
        return "roman_words must be one string"
    cues = data.get("cues")
    if cues is not None:
        if not isinstance(cues, dict):
            return "cues must be an object"
        for intent, entry in cues.items():
            if intent not in lexicon.INTENT_ORDER:
                return "unknown intent in cues: " + str(intent)
            if not isinstance(entry, dict) or set(entry) - {"w", "p"}:
                return "cues for %s must be an object with w and p only" % intent
            words, phrases = entry.get("w", ""), entry.get("p", [])
            if not isinstance(words, str) or not isinstance(phrases, list) or not all(_text(p) for p in phrases):
                return "cues for %s: w must be a string and p a list of strings" % intent
            if not words.strip() and not phrases:
                return "cues for %s are empty" % intent
    markers = data.get("markers")
    if markers is not None:
        if not isinstance(markers, dict):
            return "markers must be an object"
        for kind, words in markers.items():
            if kind not in lexicon.MARKERS:
                return "unknown marker kind: " + str(kind)
            if not _text(words):
                return "empty marker words for " + kind
    person = data.get("person")
    if person is not None:
        if not isinstance(person, dict) or set(person) != set(PERSON_KEYS):
            return "person must have exactly these keys: " + ", ".join(PERSON_KEYS)
        if not all(_text(value) for value in person.values()):
            return "person values must be non-empty strings"
    name_markers = data.get("name_markers")
    if name_markers is not None:
        if not isinstance(name_markers, list) or not name_markers:
            return "name_markers must be a non-empty list"
        for phrase in name_markers:
            if not isinstance(phrase, list) or not phrase or not all(_text(word) for word in phrase):
                return "each name marker must be a non-empty list of words"
    for field in ("name_stop", "name_words"):
        value = data.get(field)
        if value is not None and (not isinstance(value, list) or not all(_text(item) for item in value)):
            return field + " must be a list of strings"
    span = data.get("script_range")
    if span is not None:
        if (not isinstance(span, list) or len(span) != 2 or not all(isinstance(n, int) and not isinstance(n, bool) for n in span)
                or span[0] > span[1] or span[0] <= 0x024F):
            return "script_range must be [low, high] code points above 0x024F"
        for other, (low, high) in languages.SCRIPT_RANGES.items():
            if other != code and span[0] <= high and low <= span[1]:
                return "script_range overlaps the range of " + other
    return None


def _apply(data):
    code = data["code"]
    new = _is_new(code)
    if "name" in data:
        lexicon.LANG_NAMES[code] = data["name"].strip()
        lexicon.NAME_WORDS[data["name"].strip().lower()] = code
    if new:
        replies.LANGS = tuple(replies.LANGS) + (code,)
        replies.LANGUAGE_LIST = replies.LANGUAGE_LIST + ", " + lexicon.LANG_NAMES[code]
    for key, value in (data.get("text") or {}).items():
        replies.TEXT[key][code] = value.strip()
    for key, value in (data.get("labels") or {}).items():
        replies.LABELS[key][code] = value.strip()
    if "roman_words" in data:
        lexicon.ROMAN_WORDS[code] = data["roman_words"].strip()
    for intent, entry in (data.get("cues") or {}).items():
        lexicon.INTENT_CUES.setdefault(intent, {})[code] = {
            "w": str(entry.get("w", "")).strip(), "p": tuple(p.strip() for p in entry.get("p", [])),
        }
    for kind, words in (data.get("markers") or {}).items():
        lexicon.MARKERS[kind][code] = words.strip()
    if data.get("person"):
        lexicon_person._TABLE[code] = {key: lexicon_person._canon_set(data["person"][key]) for key in PERSON_KEYS}
    for word in data.get("name_words") or []:
        lexicon.NAME_WORDS[word.strip().lower()] = code
    if data.get("script_range"):
        languages.SCRIPT_RANGES[code] = (data["script_range"][0], data["script_range"][1])
    changed_names = False
    for phrase in data.get("name_markers") or []:
        words = tuple(word.strip() for word in phrase)
        if words not in entities.NAME_MARKERS:
            entities.NAME_MARKERS = tuple(entities.NAME_MARKERS) + (words,)
            changed_names = True
    for word in data.get("name_stop") or []:
        entities.NAME_STOP.add(word.strip().lower())
    if changed_names:
        entities._NAME_RE = re.compile(
            r"(?<!\w)(?:" + "|".join(entities._marker_pattern(words) for words in entities.NAME_MARKERS)
            + r")(?!\w)[\s:,\-]*(\S+(?:\s+\S+){0,2})",
            re.IGNORECASE,
        )


def _clear_caches():
    languages._ROMAN_CACHE.clear()
    intents._INDEX_CACHE.clear()
    intents._MARKER_CACHE.clear()
    lexicon._KEYWORDS = None


def load_packs(directory=None):
    """Load every *.json pack in the folder. Returns {"loaded": [codes], "rejected": {file name: reason}}."""
    report = {"loaded": [], "rejected": {}}
    try:
        folder = packs_dir(directory)
        if not folder.is_dir():
            return report
        for path in sorted(folder.glob("*.json")):
            try:
                with open(path, "r", encoding="utf-8-sig") as handle:
                    data = json.load(handle)
            except (OSError, ValueError) as error:
                report["rejected"][path.name] = "cannot read the file: " + str(error)
                continue
            reason = validate(data)
            if reason:
                report["rejected"][path.name] = reason
                continue
            try:
                _apply(data)
                report["loaded"].append(data["code"])
            except Exception as error:  # a failure while applying may leave this one language partly applied
                report["rejected"][path.name] = "apply failed: " + type(error).__name__ + ": " + str(error)
        if report["loaded"]:
            _clear_caches()
    except Exception as error:
        report["rejected"]["(folder)"] = type(error).__name__ + ": " + str(error)
    return report