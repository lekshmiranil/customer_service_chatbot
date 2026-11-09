import shutil
from pathlib import Path

import pytesseract
from PIL import Image, ImageDraw, ImageFilter, ImageFont

DEFAULT_TESSERACT = r"C:\Program Files\Tesseract-OCR\tesseract.exe"
if shutil.which("tesseract") is None:
    pytesseract.pytesseract.tesseract_cmd = DEFAULT_TESSERACT

OUTPUT_DIR = Path("test_files")

LINES = [
    "INVOICE",
    "Order ID: 78231",
    "Date: 03/10/2026",
    "Amount: Rs 4500.00",
    "Product: Wireless Mouse WM-200",
    "Error code: E-502",
]


def make_image():
    image = Image.new("RGB", (900, 420), "white")
    draw = ImageDraw.Draw(image)
    try:
        font = ImageFont.truetype(r"C:\Windows\Fonts\arial.ttf", 36)
    except OSError:
        font = ImageFont.load_default(size=36)
    y = 20
    for line in LINES:
        draw.text((30, y), line, fill="black", font=font)
        y += 62
    return image


def read_image(image):
    data = pytesseract.image_to_data(
        image, lang="eng", output_type=pytesseract.Output.DICT
    )
    words = []
    confidences = []
    for text, conf in zip(data["text"], data["conf"]):
        if text.strip() and float(conf) >= 0:
            words.append(text)
            confidences.append(float(conf))
    mean_confidence = sum(confidences) / len(confidences) if confidences else 0.0
    return " ".join(words), round(mean_confidence, 1), len(words)


def main():
    OUTPUT_DIR.mkdir(exist_ok=True)

    clean = make_image()
    clean.save(OUTPUT_DIR / "invoice_clean.png")

    variants = [
        ("clean", clean),
        ("blur radius 3", clean.filter(ImageFilter.GaussianBlur(3))),
        ("blur radius 6", clean.filter(ImageFilter.GaussianBlur(6))),
    ]

    for name, image in variants:
        if name != "clean":
            file_name = "invoice_" + name.replace(" ", "_") + ".png"
            image.save(OUTPUT_DIR / file_name)
        text, mean_confidence, word_count = read_image(image)
        print(f"--- {name} ---")
        print(f"words read: {word_count}, mean confidence: {mean_confidence}")
        print(f"text: {text}")
        print()


if __name__ == "__main__":
    main()