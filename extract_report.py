from pathlib import Path

from src.multimodal.fields import extract_fields
from src.multimodal.ocr import OcrFailed, ocr_image, quality_issues

FOLDER = Path("test_files")
IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg"}


def main():
    files = sorted(p for p in FOLDER.iterdir() if p.suffix.lower() in IMAGE_EXTENSIONS)
    for path in files:
        print(f"=== {path.name} ===")
        try:
            page = ocr_image(path)
        except OcrFailed as error:
            print(f"OCR failed: {error}")
            print()
            continue

        print(f"quality issues: {quality_issues(page)}")
        result = extract_fields(page)
        if not result.fields:
            print("no fields found")
        for item in result.fields:
            print(
                f"{item.kind:10} value={item.value!r} label={item.label!r} "
                f"confidence={item.confidence} flags={list(item.flags)} "
                f"alternatives={list(item.alternatives)}"
            )
        print()


if __name__ == "__main__":
    main()
