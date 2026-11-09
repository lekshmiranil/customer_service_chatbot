from pathlib import Path

from src.multimodal.ocr import QUALITY_MESSAGES, OcrFailed, ocr_image, quality_issues

FOLDER = Path("test_files")
IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg"}
LINES_TO_SHOW = 15


def main():
    files = sorted(p for p in FOLDER.iterdir() if p.suffix.lower() in IMAGE_EXTENSIONS)
    print(f"Images found: {[p.name for p in files]}")
    print()

    for path in files:
        print(f"=== {path.name} ===")
        try:
            page = ocr_image(path)
        except OcrFailed as error:
            print(f"OCR failed: {error}")
            print()
            continue

        issues = quality_issues(page)
        print(
            f"words: {len(page.words)}, mean confidence: {page.mean_confidence:.1f}, "
            f"low-confidence share: {page.low_confidence_share():.0%}"
        )
        print(
            f"sharpness: {page.sharpness}, rotation used: {page.rotation_degrees:g}, "
            f"time: {page.elapsed_seconds}s"
        )
        print(f"notes: {page.notes}")
        print(f"quality issues: {issues}")
        for code in issues:
            print(f"  customer message: {QUALITY_MESSAGES[code]}")
        for line in page.line_texts()[:LINES_TO_SHOW]:
            print(f"    {line}")
        print()


if __name__ == "__main__":
    main()