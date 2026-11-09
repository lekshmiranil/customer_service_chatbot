"""High-risk issue detection. It is separate from sentiment, so a calm message still triggers it."""
import re

from src.sentiment.lexicon import has_any, normalize

ACCOUNT_PHRASES = (
    "hacked", "compromised", "unauthorized", "unauthorised", "account takeover", "stolen account",
    "account stolen", "identity theft", "phishing", "fraud*", "someone is using my account",
    "हैक", "धोखाधड़ी", "अनधिकृत", "किसी और ने मेरा अकाउंट",
    "hack ho gaya", "hack hua", "account hack", "dhokhadhadi", "kisi aur ne mera account",
    "ഹാക്ക്", "തട്ടിപ്പ്", "അനധികൃത", "hack aayi", "hack cheythu", "thattippu",
)
ACCOUNT_RES = (
    re.compile(r"\bsomeone(?:\s+else)?\s+(?:has\s+|had\s+|is\s+|was\s+)?(?:logged\s+in|logged\s+into|accessed|using|used|changed|got\s+into)\b"),
    re.compile(r"\b(?:didn't|did\s+not|never)\s+(?:authori[sz]e|approve|make|initiate)\b[^.?!]{0,40}\b(?:transaction|purchase|payment|login|charge)"),
    re.compile(r"\bpassword\s+(?:was\s+|got\s+|has\s+been\s+)?changed\b"),
)

DUPLICATE_PHRASES = (
    "duplicate payment", "duplicate charge", "double payment", "double charge", "double charged",
    "दो बार पैसे", "दो बार कट", "दोहरा भुगतान", "डबल पेमेंट", "दो बार चार्ज",
    "do baar paise", "do baar kat", "do baar charge", "dobara paise kat",
    "രണ്ടു തവണ പണം", "രണ്ട് തവണ പണം", "രണ്ടു തവണ ചാർജ്", "ഇരട്ട പേയ്‌മെന്റ്",
    "randu thavana panam",
)
DUPLICATE_RES = (
    re.compile(r"\b(?:charged|billed|debited|deducted|paid|taken|withdrawn)(?:\s+\w+){0,3}\s+(?:twice|two\s+times|2\s+times|double)\b"),
    re.compile(r"\b(?:twice|two\s+times|double|duplicate)\s+(?:charge|charged|payment|payments|billing|deduction|debit)"),
)

LEGAL_PHRASES = (
    "legal action", "legal notice", "legal case", "legal proceedings", "legal steps", "take legal", "lawyer",
    "attorney", "lawsuit", "sue you", "suing", "i will sue", "i'll sue", "court", "consumer court",
    "consumer forum", "consumer protection", "file a case", "police complaint", "cyber crime", "cybercrime",
    "ombudsman",
    "वकील", "कानूनी", "अदालत", "कोर्ट", "केस करूंगा", "केस करूँगा", "उपभोक्ता फोरम", "पुलिस",
    "vakil", "kanooni", "kanuni", "adalat", "case karunga", "police complaint",
    "വക്കീൽ", "വക്കീല", "കോടതി", "നിയമ നടപടി", "പോലീസ്", "കേസ് കൊടുക്കും",
    "vakkeel", "kodathi", "niyama nadapadi", "case kodukkum",
)


def detect_risks(text):
    """The high-risk categories found in a message, in a fixed order."""
    value = normalize(text)
    found = []
    if has_any(value, ACCOUNT_PHRASES) or any(rx.search(value) for rx in ACCOUNT_RES):
        found.append("account_compromise")
    if has_any(value, DUPLICATE_PHRASES) or any(rx.search(value) for rx in DUPLICATE_RES):
        found.append("duplicate_payment")
    if has_any(value, LEGAL_PHRASES):
        found.append("legal_threat")
    return found