"""OCR stage for the customer chatbot.

Reads text from an image with Tesseract and reports how sure the engine is
about every word. It does not decide what the text means; field extraction
and the comparison with the customer's message are separate stages.
"""

import os
import shutil
import time
from dataclasses import dataclass, field
from pathlib import Path

import pytesseract
from PIL import Image, ImageFilter, ImageOps, ImageStat

DEFAULT_TESSERACT = r"C:\Program Files\Tesseract-OCR\tesseract.exe"
if shutil.which("tesseract") is None and Path(DEFAULT_TESSERACT).is_file():
    pytesseract.pytesseract.tesseract_cmd = DEFAULT_TESSERACT

RELIABLE_WORD_CONFIDENCE = 60
MIN_IMAGE_WIDTH = 800
SHARPNESS_MEASURE_SIDE = 1600

# Angles tried, in this order, when the upright image yields too little text:
# small tilts first, then quarter turns.
ROTATION_CANDIDATES = (25, -25, 12, -12, 40, -40, 90, 270, 180)

QUALITY_MESSAGES = {
    "no_readable_text": (
        "I could not read any text in this image. Please send a sharper photo "
        "taken straight on in good light, or a screenshot."
    ),
    "low_confidence": (
        "The text in this image is hard to read reliably. Please send a clearer "
        "photo or a screenshot."
    ),
}


class OcrFailed(Exception):
    """The OCR engine could not process the image."""


@dataclass(frozen=True)
class OcrWord:
    text: str
    confidence: float
    left: int
    top: int
    width: int
    height: int
    line_key: tuple


@dataclass
class OcrPage:
    words: list
    width: int
    height: int
    sharpness: float
    rotation_degrees: float
    elapsed_seconds: float
    notes: list = field(default_factory=list)

    @property
    def mean_confidence(self) -> float:
        if not self.words:
            return 0.0
        return sum(word.confidence for word in self.words) / len(self.words)

    @property
    def text(self) -> str:
        return " ".join(word.text for word in self.words)

    def lines(self) -> list:
        grouped = {}
        for word in self.words:
            grouped.setdefault(word.line_key, []).append(word)
        return [sorted(group, key=lambda w: w.left) for group in grouped.values()]

    def line_texts(self) -> list:
        return [" ".join(word.text for word in line) for line in self.lines()]

    def low_confidence_share(self, threshold=RELIABLE_WORD_CONFIDENCE) -> float:
        if not self.words:
            return 0.0
        low = sum(1 for word in self.words if word.confidence < threshold)
        return low / len(self.words)


def _env_number(name, default, cast):
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


def _sharpness(image) -> float:
    """Variance of the Laplacian on a downscaled grayscale copy. Reported as
    information only: dark, low-contrast photos score low even when readable."""
    gray = image.convert("L")
    gray.thumbnail((SHARPNESS_MEASURE_SIDE, SHARPNESS_MEASURE_SIDE))
    laplacian = gray.filter(
        ImageFilter.Kernel((3, 3), (0, 1, 0, 1, -4, 1, 0, 1, 0), scale=1, offset=128)
    )
    return round(ImageStat.Stat(laplacian).var[0], 1)


def _prepare(image):
    gray = image.convert("L")
    max_side = _env_number("OCR_MAX_SIDE_PIXELS", 2400, int)
    if max(gray.size) > max_side:
        gray.thumbnail((max_side, max_side), Image.Resampling.LANCZOS)
    if gray.width < MIN_IMAGE_WIDTH:
        gray = gray.resize((gray.width * 2, gray.height * 2), Image.Resampling.LANCZOS)
    return ImageOps.autocontrast(gray, cutoff=1)


def _run_tesseract(image, timeout) -> list:
    try:
        data = pytesseract.image_to_data(
            image,
            lang="eng",
            config="--psm 3",
            output_type=pytesseract.Output.DICT,
            timeout=timeout,
        )
    except pytesseract.TesseractNotFoundError:
        raise OcrFailed("The OCR engine is not installed or not on PATH.") from None
    except (RuntimeError, pytesseract.TesseractError) as error:
        raise OcrFailed(f"The OCR engine failed: {type(error).__name__}") from None

    words = []
    for index, raw_text in enumerate(data["text"]):
        text = raw_text.strip()
        try:
            confidence = float(data["conf"][index])
        except (TypeError, ValueError):
            continue
        if not text or confidence < 0:
            continue
        words.append(
            OcrWord(
                text=text,
                confidence=confidence,
                left=int(data["left"][index]),
                top=int(data["top"][index]),
                width=int(data["width"][index]),
                height=int(data["height"][index]),
                line_key=(
                    data["block_num"][index],
                    data["par_num"][index],
                    data["line_num"][index],
                ),
            )
        )
    return words


def _reliable_count(words) -> int:
    return sum(1 for word in words if word.confidence >= RELIABLE_WORD_CONFIDENCE)


def ocr_image(source) -> OcrPage:
    """Reads one image (a path or file object). Raises OcrFailed if the image
    cannot be opened or the engine fails."""
    start = time.monotonic()
    call_timeout = _env_number("OCR_CALL_TIMEOUT_SECONDS", 20.0, float)
    search_budget = _env_number("OCR_ROTATION_SEARCH_SECONDS", 12.0, float)
    min_words = _env_number("OCR_MIN_WORDS", 5, int)

    try:
        with Image.open(source) as opened:
            original = ImageOps.exif_transpose(opened).convert("RGB")
    except Exception as error:
        raise OcrFailed(f"The image could not be opened: {type(error).__name__}") from None

    sharpness = _sharpness(original)
    prepared = _prepare(original)
    notes = []

    best_words = _run_tesseract(prepared, call_timeout)
    best_angle = 0.0

    if _reliable_count(best_words) < min_words:
        good_enough = max(min_words * 3, 15)
        for angle in ROTATION_CANDIDATES:
            if time.monotonic() - start > search_budget:
                notes.append("rotation search stopped at its time limit")
                break
            rotated = prepared.rotate(
                angle,
                expand=True,
                resample=Image.Resampling.BICUBIC,
                fillcolor=255,
            )
            candidate = _run_tesseract(rotated, call_timeout)
            if _reliable_count(candidate) > _reliable_count(best_words):
                best_words = candidate
                best_angle = float(angle)
                if _reliable_count(best_words) >= good_enough:
                    break

    if best_angle != 0.0:
        notes.append(f"text was found after rotating the image {best_angle:g} degrees")

    return OcrPage(
        words=best_words,
        width=original.width,
        height=original.height,
        sharpness=sharpness,
        rotation_degrees=best_angle,
        elapsed_seconds=round(time.monotonic() - start, 2),
        notes=notes,
    )


def quality_issues(page: OcrPage) -> list:
    """Returns issue codes (keys of QUALITY_MESSAGES); an empty list means the
    page is readable enough to continue. Thresholds are provisional and come
    from a handful of test images; field-level checks follow in extraction."""
    min_words = _env_number("OCR_MIN_WORDS", 5, int)
    min_mean = _env_number("OCR_MIN_MEAN_CONFIDENCE", 70.0, float)

    if len(page.words) < min_words:
        return ["no_readable_text"]
    if page.mean_confidence < min_mean:
        return ["low_confidence"]
    return []