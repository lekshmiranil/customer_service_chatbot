"""Reply templates in six languages for the multilingual layer.

Standard library only. No function in this module raises.
Unknown language codes fall back to English.
"""

LANGS = ("en", "hi", "ml", "ta", "te", "kn")

LANGUAGE_LIST = "English, \u0939\u093f\u0928\u094d\u0926\u0940, \u0d2e\u0d32\u0d2f\u0d3e\u0d33\u0d02, \u0ba4\u0bae\u0bbf\u0bb4\u0bcd, \u0c24\u0c46\u0c32\u0c41\u0c17\u0c41, \u0c95\u0ca8\u0ccd\u0ca8\u0ca1"

TEXT = {
    "clarify_language": {
        "en": "I am not sure which language you are using. Please tell me your preferred language ({languages}).",
        "hi": "मुझे समझ नहीं आया कि आप किस भाषा में लिख रहे हैं। कृपया अपनी पसंदीदा भाषा बताएं ({languages})।",
        "ml": "നിങ്ങൾ ഏത് ഭാഷയാണ് ഉപയോഗിക്കുന്നതെന്ന് എനിക്ക് മനസ്സിലായില്ല. ദയവായി ഇഷ്ടപ്പെട്ട ഭാഷ പറയൂ ({languages}).",
        "ta": "நீங்கள் எந்த மொழியில் எழுதுகிறீர்கள் என்று எனக்குப் புரியவில்லை. உங்களுக்கு விருப்பமான மொழியைச் சொல்லுங்கள் ({languages}).",
        "te": "మీరు ఏ భాషలో రాస్తున్నారో నాకు అర్థం కాలేదు. దయచేసి మీకు ఇష్టమైన భాషను చెప్పండి ({languages}).",
        "kn": "ನೀವು ಯಾವ ಭಾಷೆಯಲ್ಲಿ ಬರೆಯುತ್ತಿದ್ದೀರಿ ಎಂದು ನನಗೆ ಅರ್ಥವಾಗಲಿಲ್ಲ. ದಯವಿಟ್ಟು ನಿಮ್ಮ ಆದ್ಯತೆಯ ಭಾಷೆಯನ್ನು ತಿಳಿಸಿ ({languages}).",
    },
    "clarify_intent": {
        "en": "I did not fully understand your request. Could you tell me in a few words what you need help with, for example order status, refund, cancellation or delivery?",
        "hi": "मैं आपकी बात पूरी तरह नहीं समझ पाया। कृपया कुछ शब्दों में बताएं कि आपको किसमें मदद चाहिए, जैसे ऑर्डर की स्थिति, रिफंड, रद्दीकरण या डिलीवरी।",
        "ml": "നിങ്ങളുടെ ആവശ്യം എനിക്ക് പൂർണമായി മനസ്സിലായില്ല. ഓർഡർ നില, റീഫണ്ട്, റദ്ദാക്കൽ, ഡെലിവറി എന്നിവ പോലെ, എന്തിനാണ് സഹായം വേണ്ടതെന്ന് ചുരുങ്ങിയ വാക്കുകളിൽ പറയാമോ?",
        "ta": "உங்கள் கோரிக்கை எனக்கு முழுமையாகப் புரியவில்லை. ஆர்டர் நிலை, பணத்திருப்பம், ரத்து, டெலிவரி போன்ற எதற்கு உதவி தேவை என்பதைச் சில வார்த்தைகளில் சொல்ல முடியுமா?",
        "te": "మీ అభ్యర్థన నాకు పూర్తిగా అర్థం కాలేదు. ఆర్డర్ స్థితి, రీఫండ్, రద్దు, డెలివరీ వంటి వాటిలో మీకు ఏ సహాయం కావాలో కొన్ని పదాలలో చెప్పగలరా?",
        "kn": "ನಿಮ್ಮ ವಿನಂತಿ ನನಗೆ ಸಂಪೂರ್ಣವಾಗಿ ಅರ್ಥವಾಗಲಿಲ್ಲ. ಆರ್ಡರ್ ಸ್ಥಿತಿ, ರಿಫಂಡ್, ರದ್ದತಿ, ಡೆಲಿವರಿ ಮುಂತಾದವುಗಳಲ್ಲಿ ಯಾವುದಕ್ಕೆ ಸಹಾಯ ಬೇಕು ಎಂದು ಕೆಲವು ಪದಗಳಲ್ಲಿ ಹೇಳಬಹುದೇ?",
    },
    "clarify_between": {
        "en": "Do you mean {first} or {second}? Please tell me which one.",
        "hi": "क्या आपका मतलब {first} से है या {second} से? कृपया बताएं।",
        "ml": "നിങ്ങൾ ഉദ്ദേശിച്ചത് {first} ആണോ {second} ആണോ? ദയവായി പറയൂ.",
        "ta": "நீங்கள் {first} பற்றிக் கேட்கிறீர்களா அல்லது {second} பற்றியா? தயவுசெய்து சொல்லுங்கள்.",
        "te": "మీరు {first} గురించా లేదా {second} గురించా? దయచేసి చెప్పండి.",
        "kn": "ನೀವು {first} ಬಗ್ಗೆಯೋ ಅಥವಾ {second} ಬಗ್ಗೆಯೋ? ದಯವಿಟ್ಟು ತಿಳಿಸಿ.",
    },
    "ask_order_id": {
        "en": "Please share your order ID so that I can help.",
        "hi": "मदद के लिए कृपया अपना ऑर्डर आईडी बताएं।",
        "ml": "സഹായിക്കാൻ ദയവായി നിങ്ങളുടെ ഓർഡർ ഐഡി നൽകൂ.",
        "ta": "உதவ, உங்கள் ஆர்டர் ஐடியைப் பகிருங்கள்.",
        "te": "సహాయం చేయడానికి దయచేసి మీ ఆర్డర్ ఐడీని ఇవ్వండి.",
        "kn": "ಸಹಾಯ ಮಾಡಲು ದಯವಿಟ್ಟು ನಿಮ್ಮ ಆರ್ಡರ್ ಐಡಿ ನೀಡಿ.",
    },
    "lead": {
        "en": "I understand you need help with {label}.",
        "hi": "मैं समझ गया कि आपको {label} में मदद चाहिए।",
        "ml": "നിങ്ങൾക്ക് {label} സംബന്ധിച്ച് സഹായം വേണമെന്ന് മനസ്സിലായി.",
        "ta": "{label} தொடர்பாக உங்களுக்கு உதவி தேவை என்பதைப் புரிந்துகொண்டேன்.",
        "te": "మీకు {label} విషయంలో సహాయం కావాలని అర్థమైంది.",
        "kn": "ನಿಮಗೆ {label} ಬಗ್ಗೆ ಸಹಾಯ ಬೇಕು ಎಂದು ಅರ್ಥವಾಯಿತು.",
    },
    "too_many": {
        "en": "I can handle up to {count} requests at a time, so I will start with the first {count}.",
        "hi": "मैं एक बार में {count} अनुरोध संभाल सकता हूँ, इसलिए पहले {count} से शुरू करता हूँ।",
        "ml": "ഒരു സമയം {count} അഭ്യർത്ഥനകൾ വരെ കൈകാര്യം ചെയ്യാൻ എനിക്ക് കഴിയും, അതിനാൽ ആദ്യത്തെ {count} എണ്ണത്തിൽ തുടങ്ങാം.",
        "ta": "ஒரே நேரத்தில் {count} கோரிக்கைகள் வரை கையாள முடியும், எனவே முதல் {count} கோரிக்கைகளிலிருந்து தொடங்குகிறேன்.",
        "te": "ఒకేసారి {count} అభ్యర్థనల వరకు నేను చూసుకోగలను, కాబట్టి మొదటి {count} వాటితో మొదలుపెడతాను.",
        "kn": "ಒಂದು ಬಾರಿಗೆ {count} ವಿನಂತಿಗಳವರೆಗೆ ನಾನು ನಿಭಾಯಿಸಬಲ್ಲೆ, ಆದ್ದರಿಂದ ಮೊದಲ {count} ರಿಂದ ಆರಂಭಿಸುತ್ತೇನೆ.",
    },
    "greeting": {
        "en": "Hello! How can I help you today?",
        "hi": "नमस्ते! मैं आपकी कैसे मदद कर सकता हूँ?",
        "ml": "നമസ്കാരം! ഞാൻ എങ്ങനെ സഹായിക്കണം?",
        "ta": "வணக்கம்! நான் எப்படி உதவலாம்?",
        "te": "నమస్కారం! నేను ఎలా సహాయం చేయగలను?",
        "kn": "ನಮಸ್ಕಾರ! ನಾನು ಹೇಗೆ ಸಹಾಯ ಮಾಡಲಿ?",
    },
    "thanks": {
        "en": "You are welcome. Is there anything else I can help with?",
        "hi": "आपका स्वागत है। क्या मैं और कुछ मदद कर सकता हूँ?",
        "ml": "സ്വാഗതം. മറ്റെന്തെങ്കിലും സഹായം വേണോ?",
        "ta": "மகிழ்ச்சி. வேறு ஏதாவது உதவி வேண்டுமா?",
        "te": "సంతోషం. ఇంకేమైనా సహాయం కావాలా?",
        "kn": "ಸ್ವಾಗತ. ಬೇರೆ ಏನಾದರೂ ಸಹಾಯ ಬೇಕೇ?",
    },
    "restored": {
        "en": "Welcome back. Here is where we stopped: {summary}",
        "hi": "वापसी पर स्वागत है। हम यहाँ रुके थे: {summary}",
        "ml": "വീണ്ടും സ്വാഗതം. നമ്മൾ നിർത്തിയത് ഇവിടെയാണ്: {summary}",
        "ta": "மீண்டும் வருக. நாம் நிறுத்திய இடம் இது: {summary}",
        "te": "తిరిగి స్వాగతం. మనం ఆపిన చోట ఇది: {summary}",
        "kn": "ಮತ್ತೆ ಸ್ವಾಗತ. ನಾವು ನಿಲ್ಲಿಸಿದ ಸ್ಥಳ ಇದು: {summary}",
    },
    "expired_new": {
        "en": "Your earlier session has ended, so we are starting a new one. How can I help you?",
        "hi": "आपका पिछला सत्र समाप्त हो गया है, इसलिए हम नया सत्र शुरू कर रहे हैं। मैं आपकी कैसे मदद कर सकता हूँ?",
        "ml": "നിങ്ങളുടെ മുൻ സെഷൻ അവസാനിച്ചതിനാൽ പുതിയ സെഷൻ ആരംഭിക്കുകയാണ്. ഞാൻ എങ്ങനെ സഹായിക്കണം?",
        "ta": "உங்கள் முந்தைய அமர்வு முடிந்துவிட்டது, எனவே புதிய அமர்வைத் தொடங்குகிறோம். நான் எப்படி உதவலாம்?",
        "te": "మీ మునుపటి సెషన్ ముగిసింది, కాబట్టి కొత్త సెషన్ ప్రారంభిస్తున్నాము. నేను ఎలా సహాయం చేయగలను?",
        "kn": "ನಿಮ್ಮ ಹಿಂದಿನ ಸೆಷನ್ ಮುಗಿದಿದೆ, ಆದ್ದರಿಂದ ಹೊಸ ಸೆಷನ್ ಆರಂಭಿಸುತ್ತಿದ್ದೇವೆ. ನಾನು ಹೇಗೆ ಸಹಾಯ ಮಾಡಲಿ?",
    },
    "handoff": {
        "en": "I will connect you with a human agent.",
        "hi": "मैं आपको किसी मानव एजेंट से जोड़ रहा हूँ।",
        "ml": "ഞാൻ നിങ്ങളെ ഒരു ഹ്യൂമൻ ഏജന്റുമായി ബന്ധിപ്പിക്കാം.",
        "ta": "உங்களை ஒரு மனித முகவருடன் இணைக்கிறேன்.",
        "te": "నేను మిమ్మల్ని ఒక మానవ ఏజెంట్‌తో కలుపుతున్నాను.",
        "kn": "ನಾನು ನಿಮ್ಮನ್ನು ಮಾನವ ಏಜೆಂಟ್‌ಗೆ ಸಂಪರ್ಕಿಸುತ್ತಿದ್ದೇನೆ.",
    },
}

LABELS = {
    "order_status": {
        "en": "order status",
        "hi": "ऑर्डर की स्थिति",
        "ml": "ഓർഡർ നില",
        "ta": "ஆர்டர் நிலை",
        "te": "ఆర్డర్ స్థితి",
        "kn": "ಆರ್ಡರ್ ಸ್ಥಿತಿ",
    },
    "cancel_order": {
        "en": "order cancellation",
        "hi": "ऑर्डर रद्द करना",
        "ml": "ഓർഡർ റദ്ദാക്കൽ",
        "ta": "ஆர்டர் ரத்து",
        "te": "ఆర్డర్ రద్దు",
        "kn": "ಆರ್ಡರ್ ರದ್ದತಿ",
    },
    "refund": {
        "en": "a refund",
        "hi": "रिफंड",
        "ml": "റീഫണ്ട്",
        "ta": "பணத்திருப்பம்",
        "te": "రీఫండ్",
        "kn": "ರಿಫಂಡ್",
    },
    "return_exchange": {
        "en": "a return or exchange",
        "hi": "वापसी या एक्सचेंज",
        "ml": "തിരികെ നൽകൽ അല്ലെങ്കിൽ മാറ്റൽ",
        "ta": "திருப்பி அனுப்புதல் அல்லது மாற்றம்",
        "te": "రిటర్న్ లేదా ఎక్స్‌చేంజ్",
        "kn": "ಹಿಂತಿರುಗಿಸುವಿಕೆ ಅಥವಾ ವಿನಿಮಯ",
    },
    "payment_issue": {
        "en": "a payment issue",
        "hi": "भुगतान की समस्या",
        "ml": "പേയ്‌മെന്റ് പ്രശ്നം",
        "ta": "பணம் செலுத்துதல் சிக்கல்",
        "te": "చెల్లింపు సమస్య",
        "kn": "ಪಾವತಿ ಸಮಸ್ಯೆ",
    },
    "delivery_issue": {
        "en": "a delivery issue",
        "hi": "डिलीवरी की समस्या",
        "ml": "ഡെലിവറി പ്രശ്നം",
        "ta": "டெலிவரி சிக்கல்",
        "te": "డెలివరీ సమస్య",
        "kn": "ಡೆಲಿವರಿ ಸಮಸ್ಯೆ",
    },
    "product_info": {
        "en": "product information",
        "hi": "उत्पाद की जानकारी",
        "ml": "ഉൽപ്പന്ന വിവരം",
        "ta": "பொருள் தகவல்",
        "te": "ఉత్పత్తి సమాచారం",
        "kn": "ಉತ್ಪನ್ನ ಮಾಹಿತಿ",
    },
    "human_agent": {
        "en": "a human agent",
        "hi": "मानव एजेंट",
        "ml": "ഹ്യൂമൻ ഏജന്റ്",
        "ta": "மனித முகவர்",
        "te": "మానవ ఏజెంట్",
        "kn": "ಮಾನವ ಏಜೆಂಟ್",
    },
}


def _lang(lang):
    return lang if lang in LANGS else "en"


def _fill(template, values):
    try:
        return template.format(**values)
    except Exception:
        return template


def render(key, lang="en", **values):
    """Return the template for key in lang with values filled in.

    Unknown key returns an empty string. Unknown language falls back to English.
    """
    try:
        table = TEXT.get(key)
        if not table:
            return ""
        values.setdefault("languages", LANGUAGE_LIST)
        return _fill(table.get(_lang(lang)) or table["en"], values)
    except Exception:
        return ""


def label(intent, lang="en"):
    """Localized short name of an intent. Empty string for intents without one."""
    table = LABELS.get(intent)
    if not table:
        return ""
    return table.get(_lang(lang)) or table["en"]


def lead_line(intent, lang="en"):
    """One localized line such as 'I understand you need help with a refund.'

    Greeting and thanks return their full reply. Intents without a label return ''.
    """
    if intent in ("greeting", "thanks"):
        return render(intent, lang)
    name = label(intent, lang)
    if not name:
        return ""
    return render("lead", lang, label=name)


def clarify_between(first, second, lang="en"):
    """Ask the customer to choose between two intents."""
    first_label = label(first, lang)
    second_label = label(second, lang)
    if not first_label or not second_label:
        return render("clarify_intent", lang)
    return render("clarify_between", lang, first=first_label, second=second_label)


def count():
    """Number of template strings, labels included."""
    total = sum(len(table) for table in TEXT.values())
    return total + sum(len(table) for table in LABELS.values())


def missing():
    """List of (key, language) pairs without text. Should be empty."""
    gaps = []
    for group in (TEXT, LABELS):
        for key, table in group.items():
            for code in LANGS:
                if not str(table.get(code, "")).strip():
                    gaps.append((key, code))
    return gaps