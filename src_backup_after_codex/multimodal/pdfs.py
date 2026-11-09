"""PDF reading stage for the customer chatbot.

Turns an accepted PDF into one OcrPage that field extraction and the message
comparison can use, plus the extra material the injection scan needs.

Each page is read in one of two ways:
  text layer  the page has real, visible text, so that text is used directly
              (exact, confidence 100, no OCR).
  OCR         the page is mostly a picture (a scan or a photo), or has too
              little visible text, so the page is rendered to an image and
              read with the OCR stage. Any text layer on such a page is NOT
              used for extraction, because it is not necessarily what the
              customer sees.

Text that a person would not see (invisible render mode, near-transparent,
under 4 pt, white on a white page, or placed outside the page) is never given
to field extraction. It is still collected so the injection scan can look at
it. Hidden text alone does not reject a file, because scanned PDFs often
carry an invisible OCR layer; hidden text that carries instructions does.

Nothing in this module logs text; log_fields() returns counts only.
"""

import io
import time
from dataclasses import dataclass, field, replace

import pymupdf
from PIL import Image

from src.multimodal.ocr import OcrPage, OcrWord, _env_number, ocr_image

TEXT_LAYER_CONFIDENCE = 100.0
MIN_VISIBLE_FONT_POINTS = 4.0
MIN_OPACITY = 0.1
NEAR_WHITE = 0.9
IMAGE_PAGE_COVERAGE = 0.4
MAX_RENDER_ZOOM = 4.0
DEFAULT_MAX_PDF_PAGES = 5


class PdfUnreadable(Exception):
    """The PDF could not be opened for reading."""


@dataclass
class PdfReading:
    page: OcrPage            # what extraction and comparison use
    scan_texts: list         # every text found, visible or hidden, for the injection scan
    rendered_pages: list     # PIL images of the pages that were read with OCR
    page_sources: list       # "text_layer" or "ocr", one per page that was read
    hidden_word_count: int
    complete: bool           # False if reading stopped at the deadline
    notes: list = field(default_factory=list)


def _is_near_white(color) -> bool:
    if not color:
        return False
    values = tuple(color)
    if len(values) == 1:
        return values[0] >= NEAR_WHITE
    if len(values) == 3:
        return all(value >= NEAR_WHITE for value in values)
    if len(values) == 4:  # CMYK
        return all(value <= 1 - NEAR_WHITE for value in values)
    return False


def _span_text(span) -> str:
    return "".join(
        chr(char[0]) if isinstance(char[0], int) else str(char[0]) for char in span["chars"]
    )


def _centre(box):
    return pymupdf.Point((box.x0 + box.x1) / 2, (box.y0 + box.y1) / 2)


def _dark_backgrounds(page) -> list:
    """Rectangles filled with a clearly non-white colour: white text on top of
    one of these is visible (a coloured table header, for example)."""
    rectangles = []
    try:
        drawings = page.get_drawings()
    except Exception:
        return rectangles
    for drawing in drawings:
        fill = drawing.get("fill")
        if fill and not _is_near_white(fill):
            rectangles.append(pymupdf.Rect(drawing["rect"]))
    return rectangles


def _hidden_reason(span, page_rect, backgrounds):
    """Why a person could not see this span, or None if it is visible."""
    if span["type"] == 3:
        return "invisible"
    if span.get("opacity", 1.0) < MIN_OPACITY:
        return "transparent"
    if span["size"] < MIN_VISIBLE_FONT_POINTS:
        return "tiny"
    box = pymupdf.Rect(span["bbox"])
    if not box.intersects(page_rect):
        return "off_page"
    if _is_near_white(span["color"]):
        centre = _centre(box)
        if not any(rectangle.contains(centre) for rectangle in backgrounds):
            return "white"
    return None


def _read_text_layer(page):
    """Returns (visible_words, hidden_word_count, texts_for_scan).

    visible_words are PyMuPDF word tuples. texts_for_scan holds the text of
    every span in drawing order, including hidden and off-page spans, once
    joined with spaces and once joined with nothing (so text split into one
    span per character is still read as a sentence)."""
    backgrounds = _dark_backgrounds(page)
    visible_boxes, hidden_boxes = [], []
    hidden_words = 0
    pieces = []

    try:
        trace = page.get_texttrace()
    except Exception:
        trace = []
    for span in trace:
        text = _span_text(span)
        pieces.append(text)
        if not text.strip():
            continue
        box = pymupdf.Rect(span["bbox"])
        if _hidden_reason(span, page.rect, backgrounds):
            hidden_boxes.append(box)
            hidden_words += len(text.split())
        else:
            visible_boxes.append(box)

    visible_words = []
    for word in page.get_text("words"):
        centre = _centre(pymupdf.Rect(word[:4]))
        in_visible = any(box.contains(centre) for box in visible_boxes)
        in_hidden = any(box.contains(centre) for box in hidden_boxes)
        if in_hidden and not in_visible:
            continue
        visible_words.append(word)

    texts = []
    spaced = " ".join(piece for piece in pieces if piece.strip())
    compact = "".join(pieces)
    if spaced.strip():
        texts.append(spaced)
        if compact != spaced:
            texts.append(compact)
    return visible_words, hidden_words, texts


def _image_coverage(page) -> float:
    area = page.rect.width * page.rect.height
    if area <= 0:
        return 0.0
    try:
        infos = page.get_image_info()
    except Exception:
        return 0.0
    covered = 0.0
    for info in infos:
        box = pymupdf.Rect(info["bbox"]) & page.rect
        if not box.is_empty:
            covered += box.width * box.height
    return min(covered / area, 1.0)


def _words_to_ocr_words(words, page_index) -> list:
    """Groups PyMuPDF words into text lines by vertical position (so a label
    and its value in separate table cells land on one line) and returns
    OcrWords in reading order."""
    ordered = sorted(words, key=lambda w: ((w[1] + w[3]) / 2, w[0]))
    lines = []
    for word in ordered:
        centre = (word[1] + word[3]) / 2
        height = max(word[3] - word[1], 1.0)
        if lines and abs(centre - lines[-1]["centre"]) <= 0.5 * max(height, lines[-1]["height"]):
            line = lines[-1]
            line["words"].append(word)
            line["centre"] += (centre - line["centre"]) / len(line["words"])
            line["height"] = max(line["height"], height)
        else:
            lines.append({"centre": centre, "height": height, "words": [word]})

    result = []
    for line_index, line in enumerate(lines):
        for word in sorted(line["words"], key=lambda w: w[0]):
            result.append(
                OcrWord(
                    text=word[4],
                    confidence=TEXT_LAYER_CONFIDENCE,
                    left=int(word[0]),
                    top=int(word[1]),
                    width=int(word[2] - word[0]),
                    height=int(word[3] - word[1]),
                    line_key=(page_index, 0, line_index),
                )
            )
    return result


def _render_png(page) -> bytes:
    max_side = _env_number("OCR_MAX_SIDE_PIXELS", 2400, int)
    longest = max(page.rect.width, page.rect.height)
    zoom = min(max_side / longest, MAX_RENDER_ZOOM)
    pixmap = page.get_pixmap(
        matrix=pymupdf.Matrix(zoom, zoom), colorspace=pymupdf.csGRAY, alpha=False
    )
    return pixmap.tobytes("png")


def read_pdf(source, deadline=None) -> PdfReading:
    """Reads a stored PDF (a path). deadline is a time.monotonic() value; when
    it has passed, remaining pages that need OCR are skipped and the reading is
    marked incomplete. Raises PdfUnreadable if the file cannot be opened or is
    password protected."""
    max_pages = _env_number("MAX_PDF_PAGES", DEFAULT_MAX_PDF_PAGES, int)
    min_words = _env_number("OCR_MIN_WORDS", 5, int)
    pymupdf.TOOLS.mupdf_display_errors(False)

    try:
        document = pymupdf.open(str(source))
    except Exception as error:
        raise PdfUnreadable(f"The PDF could not be opened: {type(error).__name__}") from None

    started = time.monotonic()
    words, scan_texts, rendered, sources, notes = [], [], [], [], []
    hidden_total = 0
    complete = True
    first_size = None
    sharpness_values = []

    try:
        if document.needs_pass:
            raise PdfUnreadable("The PDF is password protected.")
        page_total = document.page_count
        if page_total > max_pages:
            notes.append(f"only the first {max_pages} of {page_total} pages were read")

        for index in range(min(page_total, max_pages)):
            page = document[index]
            if first_size is None:
                first_size = (int(page.rect.width), int(page.rect.height))

            visible, hidden, texts = _read_text_layer(page)
            hidden_total += hidden
            scan_texts.extend(texts)
            coverage = _image_coverage(page)

            if len(visible) >= min_words and coverage < IMAGE_PAGE_COVERAGE:
                words.extend(_words_to_ocr_words(visible, index))
                sources.append("text_layer")
                notes.append(f"page {index + 1}: text layer, {len(visible)} words")
                continue

            if deadline is not None and time.monotonic() >= deadline:
                complete = False
                notes.append(f"page {index + 1} and later were not read: time limit reached")
                break

            png = _render_png(page)
            ocr_page = ocr_image(io.BytesIO(png))
            with Image.open(io.BytesIO(png)) as opened:
                rendered.append(opened.convert("L"))
            words.extend(replace(word, line_key=(index,) + tuple(word.line_key)) for word in ocr_page.words)
            sharpness_values.append(ocr_page.sharpness)
            sources.append("ocr")
            reason = "mostly an image" if coverage >= IMAGE_PAGE_COVERAGE else "too little visible text"
            notes.append(f"page {index + 1}: read with OCR ({reason}), {len(ocr_page.words)} words")
            scan_texts.append(ocr_page.text)
    finally:
        document.close()

    if hidden_total:
        notes.append(f"{hidden_total} hidden words were ignored for extraction")

    width, height = first_size or (0, 0)
    page = OcrPage(
        words=words,
        width=width,
        height=height,
        sharpness=round(sum(sharpness_values) / len(sharpness_values), 1) if sharpness_values else 0.0,
        rotation_degrees=0.0,
        elapsed_seconds=round(time.monotonic() - started, 2),
        notes=notes,
    )
    return PdfReading(
        page=page,
        scan_texts=scan_texts,
        rendered_pages=rendered,
        page_sources=sources,
        hidden_word_count=hidden_total,
        complete=complete,
        notes=notes,
    )


def log_fields(reading) -> dict:
    """Counts only, safe to log."""
    return {
        "pdf_pages_read": len(reading.page_sources),
        "pdf_text_layer_pages": reading.page_sources.count("text_layer"),
        "pdf_ocr_pages": reading.page_sources.count("ocr"),
        "pdf_hidden_words": reading.hidden_word_count,
        "pdf_complete": reading.complete,
    }