import argparse
import csv
import re
from pathlib import Path

import cv2
import pandas as pd
import pytesseract


AMOUNT_PATTERN = re.compile(r"(-?\d+[\.,]\d{2})")

IGNORE_PATTERNS = [
    "totaal",
    "subtotaal",
    "btw",
    "pin",
    "visa",
    "mastercard",
    "betaling",
    "wisselgeld",
    "korting",
    "bonus",
    "spaar",
    "retour",
]

SUPPORTED_EXTENSIONS = {
    ".jpg",
    ".jpeg",
    ".png",
    ".bmp",
    ".tif",
    ".tiff",
    ".webp",
}


def preprocess_image(image_path: Path, debug_dir: Path):
    image = cv2.imread(str(image_path))
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)

    gray_path = debug_dir / f"{image_path.stem}_gray.png"
    cv2.imwrite(str(gray_path), gray)

    threshold = cv2.adaptiveThreshold(
        gray,
        255,
        cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
        cv2.THRESH_BINARY,
        31,
        15,
    )

    threshold_path = debug_dir / f"{image_path.stem}_threshold.png"
    cv2.imwrite(str(threshold_path), threshold)

    return threshold



def run_ocr(image, lang: str):
    config = "--oem 3 --psm 6"
    return pytesseract.image_to_string(image, lang=lang, config=config)



def normalize_amount(value: str):
    return value.replace(",", ".")



def should_ignore(line: str):
    line_lower = line.lower()
    return any(pattern in line_lower for pattern in IGNORE_PATTERNS)



def parse_receipt_lines(text: str, source_file: str):
    rows = []

    for idx, raw_line in enumerate(text.splitlines(), start=1):
        line = raw_line.strip()

        if not line:
            continue

        if should_ignore(line):
            continue

        amounts = AMOUNT_PATTERN.findall(line)

        if not amounts:
            continue

        last_amount = amounts[-1]
        amount_index = line.rfind(last_amount)

        item_text = line[:amount_index].strip(" .:-")

        if len(item_text) < 2:
            continue

        parser_confidence = 0.75

        warning = ""

        if len(amounts) > 1:
            warning = "multiple_amounts_detected"
            parser_confidence = 0.55

        rows.append(
            {
                "source_file": source_file,
                "line_no": idx,
                "item_text": item_text,
                "quantity": "",
                "unit_price": "",
                "line_total": normalize_amount(last_amount),
                "currency": "EUR",
                "parser_confidence": parser_confidence,
                "raw_line": raw_line,
                "warning": warning,
            }
        )

    return rows



def process_receipt(image_path: Path, output_dir: Path, lang: str):
    debug_dir = output_dir / "debug_images"
    text_dir = output_dir / "ocr_text"
    per_receipt_dir = output_dir / "per_receipt"

    debug_dir.mkdir(parents=True, exist_ok=True)
    text_dir.mkdir(parents=True, exist_ok=True)
    per_receipt_dir.mkdir(parents=True, exist_ok=True)

    processed_image = preprocess_image(image_path, debug_dir)

    text = run_ocr(processed_image, lang)

    text_file = text_dir / f"{image_path.stem}.txt"
    text_file.write_text(text, encoding="utf-8")

    rows = parse_receipt_lines(text, image_path.name)

    receipt_csv = per_receipt_dir / f"{image_path.stem}.csv"

    if rows:
        pd.DataFrame(rows).to_csv(receipt_csv, index=False)
    else:
        pd.DataFrame(columns=[
            "source_file",
            "line_no",
            "item_text",
            "quantity",
            "unit_price",
            "line_total",
            "currency",
            "parser_confidence",
            "raw_line",
            "warning",
        ]).to_csv(receipt_csv, index=False)

    return rows



def main():
    parser = argparse.ArgumentParser(description="Receipt image to CSV processor")
    parser.add_argument("--input", required=True, help="Input directory with receipt images")
    parser.add_argument("--output", required=True, help="Output directory")
    parser.add_argument("--lang", default="nld+eng", help="Tesseract OCR languages")

    args = parser.parse_args()

    input_dir = Path(args.input)
    output_dir = Path(args.output)

    output_dir.mkdir(parents=True, exist_ok=True)

    all_rows = []
    report_rows = []

    image_files = [
        path for path in input_dir.iterdir()
        if path.suffix.lower() in SUPPORTED_EXTENSIONS
    ]

    for image_file in sorted(image_files):
        try:
            rows = process_receipt(image_file, output_dir, args.lang)

            all_rows.extend(rows)

            report_rows.append(
                {
                    "source_file": image_file.name,
                    "status": "success",
                    "detected_rows": len(rows),
                }
            )

            print(f"[OK] {image_file.name}: {len(rows)} rows")

        except Exception as exc:
            report_rows.append(
                {
                    "source_file": image_file.name,
                    "status": "error",
                    "detected_rows": 0,
                    "error": str(exc),
                }
            )

            print(f"[ERROR] {image_file.name}: {exc}")

    combined_csv = output_dir / "combined_receipts.csv"
    report_csv = output_dir / "processing_report.csv"

    pd.DataFrame(all_rows).to_csv(combined_csv, index=False)
    pd.DataFrame(report_rows).to_csv(report_csv, index=False)

    print(f"\nCombined CSV written to: {combined_csv}")
    print(f"Processing report written to: {report_csv}")


if __name__ == "__main__":
    main()
