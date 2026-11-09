"""Injection screening for text read from uploaded files.

Hidden instructions inside an image or PDF must be rejected. This module
looks at the text the OCR stage read (and, for images, at a second pass that
brings out very faint text) and decides whether the file is carrying
instructions meant for the system rather than information about an order.

Replies in this project come from fixed templates and no language model reads
the OCR text, so this is a second line of defence plus a clear rejection path.
It can only judge text that OCR can read: text that is invisible, or too small
or garbled to read, is not seen by this module (and is not seen by anything
else downstream either).

Only reason codes are logged, never the text that was read.
"""

import os
import re
import unicodedata
from dataclasses import dataclass
from difflib import SequenceMatcher

import pytesseract
from PIL import Image, ImageOps

from src.multimodal.intake import UploadRejected, delete_upload
from src.pipeline import metrics
from src.pipeline.security import detect_prompt_injection

CUSTOMER_MESSAGE = (
    "This file could not be used because it contains text that looks like "
    "instructions to the system, so it has been deleted. Please send a "
    "different file, or describe the problem in your message."
)

# Words that, followed closely by an instruction-related word, mark a command.
COMMAND_VERBS = ("ignore", "disregard", "forget", "override", "bypass", "circumvent")
STRONG_TARGETS = (
    "instructions", "instruction", "rules", "rule", "guidelines", "prompt",
    "safety", "restrictions", "filters", "constraints", "policy", "policies",
    "programming", "directives", "system", "safeguards",
)
# Actions an attacker wants performed. Matched exactly, and only when joined to
# the command by a linking word ("ignore the above AND refund ...").
ACTION_WORDS = (
    "refund", "approve", "reveal", "escalate", "transfer", "password",
    "credentials", "token",
)
LINKING_WORDS = ("and", "then", "to", "also", "now", "instead", "please")
STRONG_WINDOW = 6
ACTION_WINDOW = 6
SIMILARITY = 0.8

PHRASE_PATTERNS = {
    "ignore_above": r"\b(?:ignore|disregard) (?:the )?above\b",
    "forget_everything": r"\b(?:ignore|disregard|forget) (?:everything|all|anything) (?:above|before|you were told|you know)\b",
    "persona_switch": r"\byou are now (?:an? )?(?:unrestricted|unfiltered|uncensored|jailbroken|dan|evil)\b",
    "role_claim": r"\b(?:act|behave|respond) as (?:an? |the )?(?:unrestricted|unfiltered|administrator|admin|system|developer|root)\b",
    "pretend": r"\bpretend (?:to be|you are|that you are)\b",
    "system_prompt": r"\bsystem prompt\b",
    "developer_mode": r"\bdeveloper mode\b",
    "jailbreak": r"\bjailbreak",
    "reveal_instructions": r"\b(?:reveal|show|print|repeat|display|output) (?:me )?(?:your|the) (?:initial |hidden |secret |original |full )?(?:instructions|prompt|rules)\b",
    "note_to_ai": r"\b(?:note|message|instructions?) (?:to|for) (?:the |this )?(?:ai|assistant|chatbot|bot|llm|model|agent)\b",
    "ai_must": r"\b(?:ai|llm)(?: assistant| agent| model| system)? (?:must|should|needs to|has to|please)\b",
    "hide_from_user": r"\bdo not (?:tell|inform|mention|alert) (?:this to )?(?:the )?(?:user|customer|human|agent|operator)\b",
}
_COMPILED_PATTERNS = {name: re.compile(pattern) for name, pattern in PHRASE_PATTERNS.items()}

# Characters OCR commonly confuses with letters.
_CONFUSIONS = str.maketrans(
    {"0": "o", "1": "i", "3": "e", "4": "a", "5": "s", "7": "t", "8": "b",
     "@": "a", "$": "s", "|": "i", "!": "i"}
)

# Faint-text pass: pixels even slightly darker than the page background are
# turned black so Tesseract can read text that is almost the background colour.
FAINT_MARGIN = 4
MIN_LIGHT_BACKGROUND = 200


@dataclass(frozen=True)
class InjectionVerdict:
    flagged: bool
    reasons: tuple = ()


CLEAN = InjectionVerdict(False, ())


def normalize(text: str) -> str:
    """Lower-case letters only, single spaces, common OCR digit/symbol
    confusions mapped back to letters."""
    text = unicodedata.normalize("NFKC", text).lower().translate(_CONFUSIONS)
    return " ".join(re.sub(r"[^a-z]+", " ", text).split())


def _matches(token, vocabulary) -> bool:
    if token in vocabulary:
        return True
    if len(token) < 5:
        return False
    for word in vocabulary:
        if len(word) >= 5 and abs(len(word) - len(token)) <= 3:
            if SequenceMatcher(None, token, word).ratio() >= SIMILARITY:
                return True
    return False


def scan_text(text: str) -> InjectionVerdict:
    """Judges a block of text. Returns reason codes only."""
    if not text or not text.strip():
        return CLEAN
    normalized = normalize(text)
    reasons = set()

    if detect_prompt_injection(text) or detect_prompt_injection(normalized):
        reasons.add("known_phrase")

    for name, pattern in _COMPILED_PATTERNS.items():
        if pattern.search(normalized):
            reasons.add(f"phrase:{name}")

    tokens = normalized.split()
    for index, token in enumerate(tokens):
        if not _matches(token, COMMAND_VERBS):
            continue
        strong_window = tokens[index + 1:index + 1 + STRONG_WINDOW]
        if any(_matches(word, STRONG_TARGETS) for word in strong_window):
            reasons.add("command_with_target")
        for offset in range(1, ACTION_WINDOW + 1):
            position = index + offset
            if position >= len(tokens):
                break
            if tokens[position] in ACTION_WORDS and tokens[position - 1] in LINKING_WORDS:
                reasons.add("command_with_action")

    if reasons:
        return InjectionVerdict(True, tuple(sorted(reasons)))
    return CLEAN


def scan_page(page) -> InjectionVerdict:
    """Scans the words an OcrPage read, in reading order. Run this on every
    page that produced words, including pages that failed the quality check."""
    return scan_text(page.text)


def _faint_pass_enabled() -> bool:
    return os.getenv("INJECTION_FAINT_PASS", "1").strip() != "0"


def _number_from_env(name, default, cast):
    raw = os.getenv(name, "").strip()
    if not raw:
        return default
    try:
        value = cast(raw)
    except ValueError:
        raise ValueError(f"{name} must be a number, got {raw!r}") from None
    if value <= 0:
        raise ValueError(f"{name} must be greater than zero, got {raw!r}")
    return value


def scan_image_for_faint_text(source) -> InjectionVerdict:
    """Second look at an image for text the normal OCR pass cannot see because
    it is almost the colour of the page. Works on light backgrounds only; dark
    or mid-grey backgrounds are skipped. If the pass fails or times out it
    returns CLEAN: it is an extra check, not a reason to refuse a file.

    source: a path, a file object, or a PIL image."""
    if not _faint_pass_enabled():
        return CLEAN
    timeout = _number_from_env("INJECTION_FAINT_TIMEOUT_SECONDS", 10.0, float)
    max_side = _number_from_env("OCR_MAX_SIDE_PIXELS", 2400, int)

    try:
        if isinstance(source, Image.Image):
            gray = ImageOps.exif_transpose(source).convert("L")
        else:
            with Image.open(source) as opened:
                gray = ImageOps.exif_transpose(opened).convert("L")
    except Exception:
        return CLEAN

    histogram = gray.histogram()
    background = max(range(256), key=histogram.__getitem__)
    if background < MIN_LIGHT_BACKGROUND:
        return CLEAN

    if max(gray.size) > max_side:
        gray.thumbnail((max_side, max_side), Image.Resampling.LANCZOS)
    elif max(gray.size) * 2 <= max_side:
        gray = gray.resize((gray.width * 2, gray.height * 2), Image.Resampling.LANCZOS)

    cutoff = background - FAINT_MARGIN
    binary = gray.point(lambda value: 0 if value < cutoff else 255)

    try:
        text = pytesseract.image_to_string(
            binary, lang="eng", config="--psm 11", timeout=timeout
        )
    except (RuntimeError, OSError, pytesseract.TesseractError, pytesseract.TesseractNotFoundError):
        return CLEAN
    return scan_text(text)


def _reject_upload(upload, verdict, stage):
    """Deletes the stored file, logs reason codes only and raises UploadRejected."""
    delete_upload(upload.file_id)
    try:
        metrics.record(
            "upload_rejected",
            reason="hidden_instructions",
            stage=stage,
            reasons=",".join(verdict.reasons),
            kind=upload.kind,
        )
    except Exception:
        pass  # a logging problem must never stop the rejection
    raise UploadRejected("hidden_instructions", CUSTOMER_MESSAGE)


def reject_if_injected(page, upload) -> InjectionVerdict:
    """Call after OCR for one stored image upload. If hidden instructions are
    found, deletes the stored file, logs only reason codes and raises
    UploadRejected. Otherwise returns the clean verdict and leaves the file.

    page: the OcrPage for this upload. upload: its StoredUpload."""
    verdict = scan_page(page)
    stage = "ocr_text"
    if not verdict.flagged and upload.kind == "image":
        verdict = scan_image_for_faint_text(upload.path)
        stage = "faint_pass"
    if not verdict.flagged:
        return verdict
    _reject_upload(upload, verdict, stage)


def reject_pdf_if_injected(reading, upload) -> InjectionVerdict:
    """Call after read_pdf for one stored PDF. Scans the text used for
    extraction, then every piece of text in the file including hidden text,
    then the rendered scanned pages for faint text. On a hit, deletes the
    stored file, logs reason codes only and raises UploadRejected.

    reading: the PdfReading from read_pdf. upload: its StoredUpload."""
    verdict = scan_page(reading.page)
    stage = "pdf_text"
    if not verdict.flagged:
        for text in reading.scan_texts:
            verdict = scan_text(text)
            if verdict.flagged:
                stage = "pdf_text_layer"
                break
    if not verdict.flagged:
        for image in reading.rendered_pages:
            verdict = scan_image_for_faint_text(image)
            if verdict.flagged:
                stage = "faint_pass"
                break
    if not verdict.flagged:
        return verdict
    _reject_upload(upload, verdict, stage)