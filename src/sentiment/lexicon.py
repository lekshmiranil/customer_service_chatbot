"""Cue lists for the rule-based sentiment classifier (English, Hindi, Malayalam).

Every list holds English words, Hindi in Devanagari and in Roman letters, and Malayalam in its own
script and in Roman letters. A phrase ending in * matches any word that starts with it. Latin phrases
match whole words only. Non-Latin phrases match as substrings, because the word-boundary rules of the
re module do not handle combining vowel signs reliably. The native-script entries should be reviewed
by a native speaker before production use.
"""
import re
import unicodedata

NEGATIVE = (
    "disappointed", "disappointing", "unhappy", "terrible", "awful", "horrible", "worst", "useless",
    "unacceptable", "ridiculous", "disgusting", "pathetic", "poor service", "bad service", "not happy",
    "not satisfied", "dissatisfied", "angry", "upset", "annoyed", "annoying", "scam", "rubbish", "garbage",
    "बहुत खराब", "खराब", "बेकार", "निराश", "नाराज", "परेशान", "घटिया", "धोखा",
    "bahut kharab", "bahut kharaab", "kharab", "kharaab", "bekar", "bekaar", "nirash", "naraz", "pareshan",
    "ghatiya", "dhokha",
    "വളരെ മോശം", "മോശം", "നിരാശ", "ദേഷ്യം", "ശല്യം", "പ്രയോജനമില്ല",
    "valare mosham", "mosham", "nirasha", "deshyam", "upayogamilla",
)

FRUSTRATED = (
    "frustrated", "frustrating", "fed up", "sick of", "tired of", "had enough", "how many times",
    "waste of time", "nobody is helping", "no one is helping", "no one helps", "nobody helps",
    "not listening", "no one is listening", "still not", "still no", "still doesn't", "still hasn't",
    "still haven't", "still waiting", "yet again", "once again", "every time", "third time", "second time",
    "again and again", "i already told", "i have already", "i have asked",
    "तंग आ गया", "तंग आ गई", "थक गया", "थक गई", "कब तक", "बार बार", "कोई सुन नहीं रहा", "अभी तक नहीं",
    "tang aa gaya", "tang aa gayi", "thak gaya", "thak gayi", "kab tak", "baar baar", "koi sun nahi raha",
    "abhi tak nahi",
    "മടുത്തു", "എത്ര തവണ", "വീണ്ടും വീണ്ടും", "ആരും ശ്രദ്ധിക്കുന്നില്ല",
    "madutthu", "madutu", "ethra thavana", "veendum veendum",
)

URGENT = (
    "urgent", "urgently", "immediately", "asap", "right now", "right away", "emergency",
    "as soon as possible", "critical", "need help now", "this instant",
    "जल्दी", "तुरंत", "फौरन", "ज़रूरी", "जरूरी", "आपातकाल",
    "jaldi", "turant", "foran", "zaruri", "zaroori", "jaruri",
    "അടിയന്തരം", "അടിയന്തര", "ഉടൻ", "പെട്ടെന്ന്",
    "adiyanthiram", "udane", "udan", "pettannu",
)

THANKS = (
    "thank you", "thanks", "thank u", "thx", "much appreciated", "appreciat*",
    "धन्यवाद", "शुक्रिया", "dhanyavad", "shukriya", "shukria", "നന്ദി", "nanni",
)

PRAISE = (
    "great", "excellent", "wonderful", "fantastic", "amazing", "brilliant", "perfect", "awesome", "lovely",
    "nice", "good job", "well done", "so helpful", "very helpful", "love how", "love that", "bravo", "genius",
    "congratulations",
    "बहुत बढ़िया", "बढ़िया", "शाबाश", "वाह", "bahut badhiya", "badhiya", "bahut accha", "shabash", "wah",
    "കൊള്ളാം", "ഭേഷ്", "kollam",
)

FAILURE = (
    "again and again", "yet again", "once again", "another", "not working", "doesn't work", "does not work",
    "didn't work", "did not work", "stopped working", "broken", "failed", "failure", "charged twice",
    "duplicate", "lost", "delayed", "delay", "ignored", "wrong", "waiting", "no response", "never arrived",
    "didn't arrive", "did not arrive", "not arrived", "not received", "haven't received", "crashed", "stuck",
    "error", "missing", "damaged",
    "फिर से", "दोबारा", "काम नहीं", "नहीं आया", "अभी तक नहीं", "देर",
    "phir se", "dobara", "kaam nahi", "nahi aaya", "abhi tak nahi",
    "വീണ്ടും", "പ്രവർത്തിക്കുന്നില്ല", "വന്നില്ല", "താമസം",
    "veendum", "pravarthikkunnilla", "vannilla", "thamasam",
)

SARCASM_STRONG = (
    "thanks for nothing", "thank you for nothing", "yeah right", "oh great", "just great", "oh wonderful",
    "oh perfect", "oh brilliant", "what a joke", "nice going", "/s", "🙄", "😒",
    "wah kya service", "वाह क्या सर्विस",
)

RESOLVED = (
    "has been resolved", "been resolved", "is resolved", "was resolved", "got resolved", "been solved",
    "is solved", "was solved", "got solved", "been fixed", "is fixed", "was fixed", "got fixed", "it works now",
    "works now", "working now", "works fine now", "problem is gone", "issue is gone", "all good now",
    "got my refund", "received my refund", "refund received",
    "hal ho gaya", "solve ho gaya", "theek ho gaya", "thik ho gaya", "हल हो गया", "ठीक हो गया",
    "समाधान हो गया", "ശരിയായി", "പരിഹരിച്ചു", "shariyayi", "pariharichu",
)
NOT_RESOLVED_RE = re.compile(r"(?:\bnot|n't|\bnever|\bnahi|\bnahin)\s+(?:\w+\s+){0,2}(?:resolved|solved|fixed|working|works)\b")

SOFTENERS = ("not bad", "no problem", "not a problem", "no worries")

_cache = {}


def _pattern(phrase):
    pattern = _cache.get(phrase)
    if pattern is None:
        prefix = phrase.endswith("*")
        core = unicodedata.normalize("NFC", phrase[:-1] if prefix else phrase).lower()
        if core.isascii():
            body = r"(?<![a-z0-9])" + re.escape(core) + ("" if prefix else r"(?![a-z0-9])")
        else:
            body = re.escape(core)
        pattern = _cache[phrase] = re.compile(body)
    return pattern


def normalize(text):
    value = unicodedata.normalize("NFC", str(text or "")).lower()
    value = value.replace("\u2019", "'").replace("\u2018", "'")
    for phrase in SOFTENERS:
        value = value.replace(phrase, " okay ")
    return value


def hits(text, phrases):
    """The distinct phrases from the list that appear in the already normalised text."""
    return sorted({phrase for phrase in phrases if _pattern(phrase).search(text)})


def has_any(text, phrases):
    return bool(hits(text, phrases))