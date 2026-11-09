"""Tone only. It builds an opening line and a notice line. The answer text, the policy wording, the
Sources and the refusal wording are never changed: apply_tone adds a line in front and nothing else."""

MESSAGES = {
    "en": {
        "empathy": "I am sorry for the inconvenience. I will help you resolve this.",
        "thanks": "Thank you for your message.",
        "priority": "I understand this is important, and it is being treated with priority.",
        "composed": "I understand your concern and I am taking it seriously.",
        "on_call": "This has been passed to our on-call team, who will pick it up outside business hours.",
        "next_day": "This has been scheduled for our team on the next working day.",
        "now": "This has been passed to our support team.",
    },
    "hi": {
        "empathy": "असुविधा के लिए हमें खेद है। हम इसे सुलझाने में आपकी मदद करेंगे।",
        "thanks": "आपके संदेश के लिए धन्यवाद।",
        "priority": "हम इसे प्राथमिकता से देख रहे हैं।",
        "composed": "हम आपकी बात गंभीरता से ले रहे हैं।",
        "on_call": "आपका मामला हमारी ऑन-कॉल टीम को भेज दिया गया है।",
        "next_day": "आपका मामला अगले कार्य दिवस के लिए निर्धारित किया गया है।",
        "now": "आपका मामला हमारी सहायता टीम को भेज दिया गया है।",
    },
    "ml": {
        "empathy": "ബുദ്ധിമുട്ടുണ്ടായതിൽ ഖേദിക്കുന്നു. ഇത് പരിഹരിക്കാൻ ഞങ്ങൾ സഹായിക്കാം.",
        "thanks": "നിങ്ങളുടെ സന്ദേശത്തിന് നന്ദി.",
        "priority": "ഞങ്ങൾ ഇത് മുൻഗണനയോടെ പരിശോധിക്കുന്നു.",
        "composed": "നിങ്ങളുടെ കാര്യം ഞങ്ങൾ ഗൗരവമായി എടുക്കുന്നു.",
        "on_call": "നിങ്ങളുടെ അഭ്യർത്ഥന ഞങ്ങളുടെ ഓൺ-കോൾ ടീമിന് കൈമാറി.",
        "next_day": "നിങ്ങളുടെ അഭ്യർത്ഥന അടുത്ത പ്രവൃത്തി ദിവസത്തേക്ക് ഷെഡ്യൂൾ ചെയ്തിട്ടുണ്ട്.",
        "now": "നിങ്ങളുടെ അഭ്യർത്ഥന ഞങ്ങളുടെ സപ്പോർട്ട് ടീമിന് കൈമാറി.",
    },
}


def detect_language(text):
    """en, hi or ml by script. Hindi or Malayalam written in Roman letters is treated as English."""
    value = str(text or "")
    devanagari = sum(1 for c in value if "\u0900" <= c <= "\u097f")
    malayalam = sum(1 for c in value if "\u0d00" <= c <= "\u0d7f")
    if malayalam and malayalam >= devanagari:
        return "ml"
    if devanagari:
        return "hi"
    return "en"


def profile_for(result, risks=()):
    flags = set(result.get("flags", []))
    if risks:
        return "priority"
    if "sarcastic" in flags:
        return "composed"
    if flags & {"frustrated", "negative"}:
        return "empathy"
    if "urgent" in flags:
        return "priority"
    if "positive" in flags:
        return "thanks"
    return "neutral"


def opening_line(profile, language="en"):
    return MESSAGES.get(language, MESSAGES["en"]).get(profile, "")


def notice_line(key, language="en"):
    return MESSAGES.get(language, MESSAGES["en"]).get(key, "")


def apply_tone(text, opening):
    """The original text, unchanged, with the opening line in front of it."""
    text = str(text or "")
    return f"{opening}\n\n{text}" if opening else text