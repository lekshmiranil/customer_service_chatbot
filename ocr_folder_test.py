import shutil
import time
from pathlib import Path

import pytesseract
from PIL import Image, ImageFilter, ImageOps, ImageStat

DEFAULT_TESSERACT = r"C:\Program Files\Tesseract-OCR\tesseract.exe"
if shutil.which("tesseract") is None:
    pytesseract.pytesseract.tesseract_cmd = DEFAULT_TESSERACT

FOLDER = Path("test_files")
IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg"}
LOW_WORD_CONFIDENCE = 60
MAX_MEASURE_SIDE = 1600
TEXT_PREVIEW_CHARS = 600


def sharpness(image):
    """Variance of the Laplacian on a downscaled grayscale copy.
    Higher means sharper; blurred images score low."""
    gray = image.convert("L")
    gray.thumbnail((MAX_MEASURE_SIDE, MAX_MEASURE_SIDE))
    laplacian = gray.filter(
        ImageFilter.Kernel((3, 3), (0, 1, 0, 1, -4, 1, 0, 1, 0), scale=1, offset=128)
    )
    return round(ImageStat.Stat(laplacian).var[0], 1)


def read_image(image):
    data = pytesseract.image_to_data(
        image, lang="eng", output_type=pytesseract.Output.DICT
    )
    words = []
    for text, conf in zip(data["text"], data["conf"]):
        if text.strip() and float(conf) >= 0:
            words.append((text, float(conf)))
    return words


def process(path):
    print(f"=== {path.name} ===")
    with Image.open(path) as opened:
        image = ImageOps.exif_transpose(opened).convert("RGB")

    width, height = image.size
    print(f"size: {width}x{height}, sharpness: {sharpness(image)}")

    start = time.perf_counter()
    words = read_image(image)
    elapsed = time.perf_counter() - start

    if not words:
        print("OCR: no words read")
        print(f"time: {elapsed:.1f}s")
        print()
        return

    confidences = [conf for _, conf in words]
    mean_confidence = sum(confidences) / len(confidences)
    low_words = [(text, int(conf)) for text, conf in words if conf < LOW_WORD_CONFIDENCE]

    print(f"OCR: {len(words)} words, mean confidence {mean_confidence:.1f}")
    print(f"words below {LOW_WORD_CONFIDENCE}: {len(low_words)} {low_words[:10]}")
    print(f"time: {elapsed:.1f}s")
    text = " ".join(text for text, _ in words)
    print(f"text: {text[:TEXT_PREVIEW_CHARS]}")
    print()


def main():
    print(f"Looking in: {FOLDER.resolve()}")
    if not FOLDER.is_dir():
        print("This folder does not exist. Run the script from the project root.")
        return

    files = sorted(p for p in FOLDER.iterdir() if p.is_file())
    print(f"Files found: {[p.name for p in files]}")
    print()
    if not files:
        print("The folder is empty.")
        return

    for path in files:
        if path.suffix.lower() not in IMAGE_EXTENSIONS:
            print(f"=== {path.name} === skipped (only PNG and JPG are read here; PDFs come later)")
            print()
            continue
        try:
            process(path)
        except Exception as error:
            print(f"=== {path.name} === failed: {type(error).__name__}: {error}")
            print()


if __name__ == "__main__":
    main()