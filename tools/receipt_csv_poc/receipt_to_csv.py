import argparse
import json
import re
import shutil
import sys
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable, Optional

import cv2
import numpy as np
import pandas as pd
import pytesseract

from line_classifier import classify_lines, summarize_line_types


AMOUNT_PATTERN = re.compile(r"(?<!\d)(-?\d{1,4}[\.,]\d{2})(?!\d)")
QUANTITY_MULTIPLIER_PATTERN = re.compile(
    r"(?P<quantity>\d+(?:[\.,]\d+)?)\s*[xX]\s*(?P<unit_price>\d+[\.,]\d{2})"
)
WEIGHT_PRICE_PATTERN = re.compile(
    r"(?P<quantity>\d+[\.,]\d{3})\s*(?P<unit>kg|g|l|ml)\s*[xX]\s*(?P<unit_price>\d+[\.,]\d{2})",
    re.IGNORECASE,
)

DISCOUNT_PATTERNS = [
    "korting",
    "bonus",
    "actie",
    "prijsvoordeel",
    "gratis",
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

CSV_COLUMNS = [
    "source_file",
    "store_hint",
    "line_no",
    "line_type",
    "classifier_reason",
    "item_text",
    "quantity",
    "unit",
    "unit_price",
    "line_total",
    "currency",
    "parser_confidence",
    "raw_line",
    "warning",
]

PARSEABLE_LINE_TYPES = {"product_line", "quantity_line"}


@dataclass
class ReceiptLine:
    source_file: str
    store_hint: str
    line_no: int
    line_type: str
    classifier_reason: str
    item_text: str
    quantity: str
    unit: str
    unit_price: str
    line_total: str
    currency: str
    parser_confidence: float
    raw_line: str
    warning: str


@dataclass
class ReceiptResult:
    source_file: str
    status: str
    store_hint: str
    detected_rows: int
    ocr_line_count: int
    total_amount_hint: str
    parse_confidence_avg: float
    warnings: list[str]
    line_type_counts: dict[str, int]
    ignored_line_count: int
    error: str = ""



def normalize_decimal(value: str) -> str:
    return value.replace(",", ".").strip()



def detect_store_hint(text: str, filename: str) -> str:
    combined = f"{filename}\n{text}".lower()
    candidates = {
        "plus": ["plus", "pluspunten", "pluspunten digital", "plussen digital"],
        "albert_heijn": ["albert heijn", "ah ", "bonus box"],
        "jumbo": ["jumbo"],
        "lidl": ["lidl", "lidl plus"],
        "aldi": ["aldi", "alot"],
    }

    for store, markers in candidates.items():
        if any(marker in combined for marker in markers):
            return store
    return "unknown"



def is_discount_line(line: str) -> bool:
    lowered = line.lower()
    return any(pattern in lowered for pattern in DISCOUNT_PATTERNS)



def ensure_tesseract_available() -> Optional[str]:
    binary = shutil.which("tesseract")
    if not binary:
        return "Tesseract OCR is niet gevonden in PATH. Installeer Tesseract of voeg tesseract.exe toe aan PATH."
    return None



def safe_imread(image_path: Path):
    image = cv2.imread(str(image_path))
    if image is None:
        raise ValueError(f"Kan afbeelding niet lezen: {image_path}")
    return image



def rotate_if_landscape(image: np.ndarray) -> np.ndarray:
    height, width = image.shape[:2]
    if width > height * 1.25:
        return cv2.rotate(image, cv2.ROTATE_90_CLOCKWISE)
    return image



def crop_to_largest_receipt_like_contour(gray: np.ndarray, original: np.ndarray):
    """Best-effort crop. If no reliable contour is found, return original image."""
    blurred = cv2.GaussianBlur(gray, (5, 5), 0)
    edged = cv2.Canny(blurred, 50, 150)
    contours, _ = cv2.findContours(edged, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

    if not contours:
        return original, False

    height, width = gray.shape[:2]
    image_area = height * width

    candidates = []
    for contour in contours:
        area = cv2.contourArea(contour)
        if area < image_area * 0.10:
            continue
        x, y, w, h = cv2.boundingRect(contour)
        if h < height * 0.30:
            continue
        candidates.append((area, x, y, w, h))

    if not candidates:
        return original, False

    _, x, y, w, h = sorted(candidates, reverse=True)[0]
    padding = 8
    x1 = max(0, x - padding)
    y1 = max(0, y - padding)
    x2 = min(width, x + w + padding)
    y2 = min(height, y + h + padding)
    return original[y1:y2, x1:x2], True



def preprocess_variants(image_path: Path, debug_dir: Path) -> dict[str, np.ndarray]:
    image = safe_imread(image_path)
    image = rotate_if_landscape(image)

    gray_initial = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    cropped, did_crop = crop_to_largest_receipt_like_contour(gray_initial, image)
    gray = cv2.cvtColor(cropped, cv2.COLOR_BGR2GRAY)

    # Upscale improves OCR for small receipt fonts.
    scale = 2 if max(gray.shape[:2]) < 2200 else 1
    if scale > 1:
        gray = cv2.resize(gray, None, fx=scale, fy=scale, interpolation=cv2.INTER_CUBIC)

    denoised = cv2.fastNlMeansDenoising(gray, None, 12, 7, 21)

    clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
    normalized = clahe.apply(denoised)

    adaptive = cv2.adaptiveThreshold(
        normalized,
        255,
        cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
        cv2.THRESH_BINARY,
        31,
        15,
    )

    otsu = cv2.threshold(normalized, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)[1]

    variants = {
        "gray": gray,
        "normalized": normalized,
        "adaptive_threshold": adaptive,
        "otsu_threshold": otsu,
    }

    debug_dir.mkdir(parents=True, exist_ok=True)
    for name, variant in variants.items():
        cv2.imwrite(str(debug_dir / f"{image_path.stem}_{name}.png"), variant)

    metadata = {
        "did_crop": did_crop,
        "scale": scale,
        "height": int(gray.shape[0]),
        "width": int(gray.shape[1]),
    }
    (debug_dir / f"{image_path.stem}_preprocess.json").write_text(
        json.dumps(metadata, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    return variants



def run_ocr(image: np.ndarray, lang: str, psm: int) -> str:
    config = f"--oem 3 --psm {psm}"
    return pytesseract.image_to_string(image, lang=lang, config=config)



def score_ocr_text(text: str) -> int:
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    amount_count = sum(1 for line in lines if AMOUNT_PATTERN.search(line))
    alpha_count = sum(1 for line in lines if re.search(r"[A-Za-zÀ-ÿ]", line))
    noise_penalty = sum(1 for line in lines if len(line) > 90)
    return amount_count * 5 + alpha_count - noise_penalty



def choose_best_ocr(variants: dict[str, np.ndarray], lang: str):
    attempts = []
    for variant_name, image in variants.items():
        for psm in (6, 4):
            text = run_ocr(image, lang=lang, psm=psm)
            attempts.append(
                {
                    "variant": variant_name,
                    "psm": psm,
                    "score": score_ocr_text(text),
                    "text": text,
                }
            )

    attempts.sort(key=lambda item: item["score"], reverse=True)
    return attempts[0], attempts



def extract_total_amount_hint(text: str) -> str:
    total_lines = [line for line in text.splitlines() if "totaal" in line.lower()]
    for line in total_lines:
        amounts = AMOUNT_PATTERN.findall(line)
        if amounts:
            return normalize_decimal(amounts[-1])
    return ""



def parse_quantity_and_unit(line: str):
    quantity = ""
    unit = ""
    unit_price = ""

    weight_match = WEIGHT_PRICE_PATTERN.search(line)
    if weight_match:
        quantity = normalize_decimal(weight_match.group("quantity"))
        unit = weight_match.group("unit").lower()
        unit_price = normalize_decimal(weight_match.group("unit_price"))
        return quantity, unit, unit_price

    multiplier_match = QUANTITY_MULTIPLIER_PATTERN.search(line)
    if multiplier_match:
        quantity = normalize_decimal(multiplier_match.group("quantity"))
        unit = "stuk"
        unit_price = normalize_decimal(multiplier_match.group("unit_price"))

    return quantity, unit, unit_price



def warning_for_line(line: str, line_type: str, amount_count: int) -> tuple[str, float]:
    warning = ""
    confidence = 0.78

    if amount_count > 1:
        warning = "multiple_amounts_detected"
        confidence = 0.62

    if line_type == "quantity_line":
        warning = f"{warning};quantity_line_requires_merge" if warning else "quantity_line_requires_merge"
        confidence = min(confidence, 0.55)

    if is_discount_line(line):
        warning = f"{warning};discount_keyword" if warning else "discount_keyword"
        confidence = min(confidence, 0.58)

    if any(char in line for char in "{}[]~^_"):
        warning = f"{warning};ocr_noise" if warning else "ocr_noise"
        confidence = min(confidence, 0.45)

    return warning, confidence



def parse_receipt_lines(text: str, source_file: str, store_hint: str, classified_lines=None) -> list[ReceiptLine]:
    rows: list[ReceiptLine] = []
    classified_lines = classified_lines or classify_lines(text)

    for classified in classified_lines:
        line = classified.normalized_line
        if not line:
            continue

        if classified.line_type not in PARSEABLE_LINE_TYPES:
            continue

        amounts = AMOUNT_PATTERN.findall(line)
        if not amounts:
            continue

        last_amount = amounts[-1]
        amount_index = line.rfind(last_amount)
        item_text = line[:amount_index].strip(" .:-|_€")

        if len(item_text) < 2:
            continue

        warning, confidence = warning_for_line(line, classified.line_type, len(amounts))
        quantity, unit, unit_price = parse_quantity_and_unit(line)

        rows.append(
            ReceiptLine(
                source_file=source_file,
                store_hint=store_hint,
                line_no=classified.line_no,
                line_type=classified.line_type,
                classifier_reason=classified.reason,
                item_text=item_text,
                quantity=quantity,
                unit=unit,
                unit_price=unit_price,
                line_total=normalize_decimal(last_amount),
                currency="EUR",
                parser_confidence=round(confidence, 3),
                raw_line=classified.raw_line,
                warning=warning,
            )
        )

    return rows



def write_rows_csv(rows: Iterable[ReceiptLine], csv_path: Path):
    csv_path.parent.mkdir(parents=True, exist_ok=True)
    dict_rows = [asdict(row) for row in rows]
    if dict_rows:
        pd.DataFrame(dict_rows).to_csv(csv_path, index=False)
    else:
        pd.DataFrame(columns=CSV_COLUMNS).to_csv(csv_path, index=False)



def write_rows_json(rows: Iterable[ReceiptLine], json_path: Path, metadata: dict, classified_lines):
    json_path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "schema_version": "receipt-ocr-poc-v2-line-classifier",
        "metadata": metadata,
        "classified_lines": [asdict(line) for line in classified_lines],
        "lines": [asdict(row) for row in rows],
    }
    json_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")



def process_receipt(image_path: Path, output_dir: Path, lang: str):
    debug_dir = output_dir / "debug_images"
    text_dir = output_dir / "ocr_text"
    attempts_dir = output_dir / "ocr_attempts"
    per_receipt_dir = output_dir / "per_receipt"
    json_dir = output_dir / "json"

    debug_dir.mkdir(parents=True, exist_ok=True)
    text_dir.mkdir(parents=True, exist_ok=True)
    attempts_dir.mkdir(parents=True, exist_ok=True)
    per_receipt_dir.mkdir(parents=True, exist_ok=True)
    json_dir.mkdir(parents=True, exist_ok=True)

    variants = preprocess_variants(image_path, debug_dir)
    best_attempt, attempts = choose_best_ocr(variants, lang)
    text = best_attempt["text"]

    text_file = text_dir / f"{image_path.stem}.txt"
    text_file.write_text(text, encoding="utf-8")

    attempt_summary = []
    for attempt in attempts:
        attempt_summary.append(
            {
                "variant": attempt["variant"],
                "psm": attempt["psm"],
                "score": attempt["score"],
            }
        )
        attempt_file = attempts_dir / f"{image_path.stem}_{attempt['variant']}_psm{attempt['psm']}.txt"
        attempt_file.write_text(attempt["text"], encoding="utf-8")

    classified_lines = classify_lines(text)
    line_type_counts = summarize_line_types(classified_lines)
    ignored_line_count = sum(
        count for line_type, count in line_type_counts.items()
        if line_type not in PARSEABLE_LINE_TYPES
    )

    store_hint = detect_store_hint(text, image_path.name)
    rows = parse_receipt_lines(text, image_path.name, store_hint, classified_lines)

    receipt_csv = per_receipt_dir / f"{image_path.stem}.csv"
    write_rows_csv(rows, receipt_csv)

    warnings = sorted({row.warning for row in rows if row.warning})
    confidence_avg = round(float(np.mean([row.parser_confidence for row in rows])), 3) if rows else 0.0

    metadata = {
        "source_file": image_path.name,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "store_hint": store_hint,
        "ocr_variant": best_attempt["variant"],
        "ocr_psm": best_attempt["psm"],
        "ocr_score": best_attempt["score"],
        "ocr_attempts": attempt_summary,
        "total_amount_hint": extract_total_amount_hint(text),
        "detected_rows": len(rows),
        "parse_confidence_avg": confidence_avg,
        "warnings": warnings,
        "line_type_counts": line_type_counts,
        "ignored_line_count": ignored_line_count,
    }

    write_rows_json(rows, json_dir / f"{image_path.stem}.json", metadata, classified_lines)

    result = ReceiptResult(
        source_file=image_path.name,
        status="success",
        store_hint=store_hint,
        detected_rows=len(rows),
        ocr_line_count=len([line for line in text.splitlines() if line.strip()]),
        total_amount_hint=metadata["total_amount_hint"],
        parse_confidence_avg=confidence_avg,
        warnings=warnings,
        line_type_counts=line_type_counts,
        ignored_line_count=ignored_line_count,
    )

    return rows, result



def list_image_files(input_dir: Path) -> list[Path]:
    if not input_dir.exists():
        input_dir.mkdir(parents=True, exist_ok=True)
        return []
    return sorted(path for path in input_dir.iterdir() if path.suffix.lower() in SUPPORTED_EXTENSIONS)



def write_benchmark_summary(output_dir: Path, report_rows: list[ReceiptResult]):
    all_line_type_counts = {}
    for row in report_rows:
        for line_type, count in row.line_type_counts.items():
            all_line_type_counts[line_type] = all_line_type_counts.get(line_type, 0) + count

    summary = {
        "schema_version": "receipt-ocr-benchmark-v2-line-classifier",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "total_receipts": len(report_rows),
        "success_count": sum(1 for row in report_rows if row.status == "success"),
        "error_count": sum(1 for row in report_rows if row.status == "error"),
        "total_detected_rows": sum(row.detected_rows for row in report_rows),
        "total_ignored_lines": sum(row.ignored_line_count for row in report_rows),
        "line_type_counts": all_line_type_counts,
        "by_store_hint": {},
    }

    for row in report_rows:
        bucket = summary["by_store_hint"].setdefault(
            row.store_hint,
            {
                "receipts": 0,
                "detected_rows": 0,
                "ignored_lines": 0,
                "avg_confidence_values": [],
                "line_type_counts": {},
            },
        )
        bucket["receipts"] += 1
        bucket["detected_rows"] += row.detected_rows
        bucket["ignored_lines"] += row.ignored_line_count
        if row.parse_confidence_avg:
            bucket["avg_confidence_values"].append(row.parse_confidence_avg)
        for line_type, count in row.line_type_counts.items():
            bucket["line_type_counts"][line_type] = bucket["line_type_counts"].get(line_type, 0) + count

    for bucket in summary["by_store_hint"].values():
        values = bucket.pop("avg_confidence_values")
        bucket["avg_parse_confidence"] = round(float(np.mean(values)), 3) if values else 0.0

    (output_dir / "benchmark_summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8"
    )



def main():
    parser = argparse.ArgumentParser(description="Standalone receipt image OCR to CSV/JSON processor")
    parser.add_argument("--input", default="input_receipts", help="Input directory with receipt images")
    parser.add_argument("--output", default="output_csv", help="Output directory")
    parser.add_argument("--lang", default="eng", help="Tesseract OCR languages, e.g. eng or nld+eng")
    parser.add_argument("--self-check", action="store_true", help="Only check local dependencies")

    args = parser.parse_args()

    tesseract_error = ensure_tesseract_available()
    if tesseract_error:
        print(f"[ERROR] {tesseract_error}")
        sys.exit(2)

    if args.self_check:
        print("[OK] Tesseract gevonden")
        print(f"[OK] Python: {sys.version.split()[0]}")
        return

    input_dir = Path(args.input)
    output_dir = Path(args.output)
    output_dir.mkdir(parents=True, exist_ok=True)

    all_rows: list[ReceiptLine] = []
    report_rows: list[ReceiptResult] = []

    image_files = list_image_files(input_dir)
    if not image_files:
        print(f"[WARN] Geen kassabonafbeeldingen gevonden in: {input_dir.resolve()}")
        print("Plaats .jpg/.png/.jpeg-bestanden in input_receipts en start opnieuw.")

    for image_file in image_files:
        try:
            rows, result = process_receipt(image_file, output_dir, args.lang)
            all_rows.extend(rows)
            report_rows.append(result)
            print(
                f"[OK] {image_file.name}: {len(rows)} product/quantity rows, "
                f"ignored={result.ignored_line_count}, store={result.store_hint}, "
                f"confidence={result.parse_confidence_avg}"
            )

        except Exception as exc:
            result = ReceiptResult(
                source_file=image_file.name,
                status="error",
                store_hint=detect_store_hint("", image_file.name),
                detected_rows=0,
                ocr_line_count=0,
                total_amount_hint="",
                parse_confidence_avg=0.0,
                warnings=[],
                line_type_counts={},
                ignored_line_count=0,
                error=str(exc),
            )
            report_rows.append(result)
            print(f"[ERROR] {image_file.name}: {exc}")

    combined_csv = output_dir / "combined_receipts.csv"
    report_csv = output_dir / "processing_report.csv"

    write_rows_csv(all_rows, combined_csv)
    pd.DataFrame([asdict(row) for row in report_rows]).to_csv(report_csv, index=False)
    write_benchmark_summary(output_dir, report_rows)

    print(f"\nCombined CSV written to: {combined_csv}")
    print(f"Processing report written to: {report_csv}")
    print(f"Benchmark summary written to: {output_dir / 'benchmark_summary.json'}")


if __name__ == "__main__":
    main()
