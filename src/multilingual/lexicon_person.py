"""Co-occurrence cues for a request to talk to a person, for wording that has no single safe cue word
(Roman Malayalam 'vilikkaan pattumo', 'phone cheyyaamo'). Data and one function. Save as UTF-8.
The Malayalam words come from the customer's own phrasings. Not reviewed by a native speaker."""
from src.multilingual import lexicon

_RAW = {
    "ml": {
        "call_exact": "call phone fone",
        "call_stem": "vilikk vilich",
        "talk_stem": "samsarikk samsaarikk samsarich",
        "person_exact": "aalod aalodu aale aalu manushyan manushyanod manushyanodu manushya",
        "person_stem": "manushy aalod aale",
        "ask_stem": "pattum cheyyam cheyyaam cheyyatt cheyyuv cheyyum tharum tharuv",
        "call_ask_ending": "atte amo umo uvo",
    },
}


def _canon_set(text):
    return tuple(sorted({lexicon.canon(word) for word in text.split()}))


_TABLE = {lang: {name: _canon_set(words) for name, words in groups.items()} for lang, groups in _RAW.items()}


def _has(keys, exact=(), stems=()):
    for key in keys:
        if key in exact:
            return True
        for stem in stems:
            if key.startswith(stem):
                return True
    return False


def person_request(keys, langs):
    """True when the clause keys (lexicon.canon forms) ask for a call or a talk with a person. Call this only for a
    clause in which no other intent was found."""
    for lang in langs:
        table = _TABLE.get(lang)
        if not table:
            continue
        call = _has(keys, table["call_exact"], table["call_stem"])
        talk = _has(keys, (), table["talk_stem"])
        person = _has(keys, table["person_exact"], table["person_stem"])
        ask = _has(keys, (), table["ask_stem"])
        if call and ask:
            return True
        if talk and (call or person):
            return True
        for key in keys:
            if any(key.startswith(stem) for stem in table["call_stem"]) and key.endswith(table["call_ask_ending"]):
                return True
    return False