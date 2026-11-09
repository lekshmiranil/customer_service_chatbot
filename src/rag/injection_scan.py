"""Detects instruction-like text hidden inside knowledge documents.

Documents are DATA. Anything that tries to give the assistant orders, claims authority
over other documents, or asks to hide or reveal information is flagged, and the chunk
holding it is quarantined (never retrieved, never shown, never sent to a model).
"""
import re
import unicodedata

_ZERO_WIDTH = re.compile("[\u200b\u200c\u200d\u200e\u200f\u2060\ufeff]")

_RULES = [
    ("override_instructions", r"\b(?:ignore|disregard|forget|override|bypass|skip)\b.{0,50}\b(?:instructions?|rules?|guidelines?|prompts?|polic(?:y|ies)|documents?|sources?|restrictions?)\b"),
    ("system_role_text", r"\b(?:system|developer|admin(?:istrator)?)\s*(?:prompt|message|override|instruction|note|command)s?\b"),
    ("model_directive", r"\byou\s+(?:must|should|shall|are to|will|need to)\s+(?:now\s+|always\s+|only\s+|never\s+)?(?:answer|respond|reply|say|tell|state|reveal|disclose|ignore|output|act|pretend|obey|follow|print|write)\b"),
    ("address_the_model", r"\b(?:tell|inform|instruct|notify)\s+(?:the\s+)?(?:user|customer|assistant|model|chatbot|ai|reader)\b"),
    ("assistant_must", r"\b(?:assistant|chatbot|ai model|language model|llm|bot)\b.{0,40}\b(?:must|should|shall|always|never|ignore|obey)\b"),
    ("concealment", r"\bdo not\s+(?:mention|reveal|disclose|tell|cite|show|reference)\b"),
    ("leak_request", r"\b(?:reveal|disclose|print|leak|expose|output|dump)\b.{0,50}\b(?:restricted|confidential|internal|system prompt|hidden|secret|other documents?)\b"),
    ("authority_claim", r"\b(?:supersedes?|overrides?|takes precedence over|replaces)\s+(?:all|any|every|the)\s+(?:other\s+|previous\s+|existing\s+)?(?:polic(?:y|ies)|documents?|instructions?|rules?|versions?|sources?)\b"),
    ("self_authority", r"\bthis\s+(?:document|notice|message|section|paragraph)\s+(?:overrides|supersedes|takes precedence|is authoritative|must be (?:used|followed))\b"),
    ("new_instructions", r"\b(?:new|updated|additional)\s+instructions?\s*[:\-]"),
    ("role_play", r"\b(?:act as|pretend (?:to be|you are)|jailbreak|developer mode|roleplay as)\b"),
    ("markup_role_tags", r"</?\s*(?:system|assistant|instructions?)\s*>|\[/?inst\]|<\|im_(?:start|end)\|>"),
    ("always_never_directive", r"(?:^|[.!?]\s+)(?:always|never)\s+(?:answer|respond|reply|say|tell|mention|cite|use|refer)\b"),
]
_COMPILED = [(name, re.compile(rx, re.IGNORECASE | re.DOTALL)) for name, rx in _RULES]


def normalize_for_scan(text):
    """Defeats trivial evasion: zero-width characters and full-width or look-alike forms."""
    text = _ZERO_WIDTH.sub("", text or "")
    text = unicodedata.normalize("NFKC", text)
    return re.sub(r"\s+", " ", text).strip()


def scan_text(text):
    """Returns the names of every rule the text trips (empty list = clean)."""
    cleaned = normalize_for_scan(text)
    return [name for name, rx in _COMPILED if rx.search(cleaned)]


def is_injected(text):
    return bool(scan_text(text))