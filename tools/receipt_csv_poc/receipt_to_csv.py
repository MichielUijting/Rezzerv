from __future__ import annotations

import argparse
import json
import re
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
import pytesseract
from PIL import Image

from line_classifier import classify_lines, summarize_line_types
from profiles import get_profile_for_store
from profiles.base import PARSEABLE_LINE_TYPES

AMOUNT_PATTERN = re.compile(r'(?<!\d)(-?\d+[\.,]\d{2})(?!\d)')
SUPPORTED_EXTENSIONS = {'.jpg', '.jpeg', '.png', '.bmp', '.tif', '.tiff', '.webp'}


@dataclass
class ReceiptLine:
    source_file: str
    store_hint: str
    profile_name: str
    line_no: int
    line_type: str
    item_text: str
    quantity: str
    unit: str
    unit_price: str
    line_total: str
    parser_confidence: float
    raw_line: str
    warning: str


@dataclass
class ReceiptResult:
    source_file: str
    status: str
    store_hint: str
    profile_name: str
    detected_rows: int
    ignored_line_count: int
    line_type_counts: dict
    merge_diagnostics: dict


def normalize_decimal(value: str) -> str:
    return value.replace(',', '.').strip()


def detect_store_hint(text: str, filename: str) -> str:
    combined = f'{filename}\n{text}'.lower()
    if 'lidl' in combined:
        return 'lidl'
    if 'jumbo' in combined:
        return 'jumbo'
    if 'aldi' in combined:
        return 'aldi'
    if 'plus' in combined:
        return 'plus'
    return 'unknown'


def parse_quantity(line: str):
    quantity = ''
    unit = ''
    unit_price = ''

    match = re.search(r'(\d+[\.,]?\d*)\s*[xX]\s*(\d+[\.,]\d{2})', line)
    if match:
        quantity = normalize_decimal(match.group(1))
        unit = 'stuk'
        unit_price = normalize_decimal(match.group(2))

    weight_match = re.search(r'(\d+[\.,]\d+)\s*(kg|g|l|ml)\s*[xX]\s*(\d+[\.,]\d{2})', line, re.IGNORECASE)
    if weight_match:
        quantity = normalize_decimal(weight_match.group(1))
        unit = weight_match.group(2)
        unit_price = normalize_decimal(weight_match.group(3))

    return quantity, unit, unit_price


def parse_receipt_lines(text: str, source_file: str, profile_name: str, classified_lines, product_block):
    rows = []

    for classified in classified_lines:
        if classified.line_type not in PARSEABLE_LINE_TYPES:
            continue

        if product_block.get('start_line') and classified.line_no < product_block['start_line']:
            continue

        if product_block.get('end_line') and classified.line_no > product_block['end_line']:
            continue

        line = classified.normalized_line
        amounts = AMOUNT_PATTERN.findall(line)
        if not amounts:
            continue

        last_amount = normalize_decimal(amounts[-1])
        item_text = line.replace(amounts[-1], '').strip()
        quantity, unit, unit_price = parse_quantity(line)

        rows.append(
            ReceiptLine(
                source_file=source_file,
                store_hint=profile_name,
                profile_name=profile_name,
                line_no=classified.line_no,
                line_type=classified.line_type,
                item_text=item_text,
                quantity=quantity,
                unit=unit,
                unit_price=unit_price,
                line_total=last_amount,
                parser_confidence=0.75,
                raw_line=classified.raw_line,
                warning='quantity_line_requires_merge' if classified.line_type == 'quantity_line' else '',
            )
        )

    return rows


def process_receipt(image_path: Path, output_dir: Path):
    text = pytesseract.image_to_string(Image.open(image_path), lang='nld+eng')

    classified_lines = classify_lines(text)
    line_type_counts = summarize_line_types(classified_lines)

    store_hint = detect_store_hint(text, image_path.name)
    profile = get_profile_for_store(store_hint)

    product_block = profile.detect_product_block(classified_lines)

    rows = parse_receipt_lines(
        text,
        image_path.name,
        profile.profile_name,
        classified_lines,
        product_block,
    )

    merged_rows, merge_diagnostics = profile.merge_quantity_lines(rows, classified_lines)

    metadata = {
        'source_file': image_path.name,
        'created_at': datetime.now(timezone.utc).isoformat(),
        'store_hint': store_hint,
        'profile_name': profile.profile_name,
        'detected_rows': len(merged_rows),
        'line_type_counts': line_type_counts,
        'product_block': product_block,
        'merge_diagnostics': merge_diagnostics,
    }

    json_dir = output_dir / 'json'
    csv_dir = output_dir / 'per_receipt'
    json_dir.mkdir(parents=True, exist_ok=True)
    csv_dir.mkdir(parents=True, exist_ok=True)

    json_payload = {
        'schema_version': 'receipt-ocr-poc-v5-quantity-merge',
        'metadata': metadata,
        'classified_lines': [asdict(line) for line in classified_lines],
        'lines': [asdict(row) for row in merged_rows],
    }

    (json_dir / f'{image_path.stem}.json').write_text(
        json.dumps(json_payload, ensure_ascii=False, indent=2),
        encoding='utf-8',
    )

    pd.DataFrame([asdict(row) for row in merged_rows]).to_csv(
        csv_dir / f'{image_path.stem}.csv',
        index=False,
    )

    return merged_rows, ReceiptResult(
        source_file=image_path.name,
        status='success',
        store_hint=store_hint,
        profile_name=profile.profile_name,
        detected_rows=len(merged_rows),
        ignored_line_count=sum(v for k, v in line_type_counts.items() if k not in PARSEABLE_LINE_TYPES),
        line_type_counts=line_type_counts,
        merge_diagnostics=merge_diagnostics,
    )


def list_image_files(input_dir: Path):
    return sorted([p for p in input_dir.iterdir() if p.suffix.lower() in SUPPORTED_EXTENSIONS])


def write_benchmark_summary(output_dir: Path, report_rows: list[ReceiptResult]):
    summary = {
        'schema_version': 'receipt-ocr-benchmark-v5-quantity-merge',
        'created_at': datetime.now(timezone.utc).isoformat(),
        'total_receipts': len(report_rows),
        'profiles_used': {},
        'merge_diagnostics': {},
    }

    for row in report_rows:
        summary['profiles_used'][row.source_file] = row.profile_name
        summary['merge_diagnostics'][row.source_file] = row.merge_diagnostics

    (output_dir / 'benchmark_summary.json').write_text(
        json.dumps(summary, ensure_ascii=False, indent=2),
        encoding='utf-8',
    )


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--input', default='input_receipts')
    parser.add_argument('--output', default='output_csv')
    args = parser.parse_args()

    input_dir = Path(args.input)
    timestamp = datetime.now().strftime('run_%Y%m%d_%H%M%S')
    output_dir = Path('test_runs') / timestamp
    output_dir.mkdir(parents=True, exist_ok=True)

    all_rows = []
    report_rows = []

    for image_file in list_image_files(input_dir):
        try:
            rows, result = process_receipt(image_file, output_dir)
            all_rows.extend(rows)
            report_rows.append(result)
            print(f'[OK] {image_file.name}: {len(rows)} rows merged={result.merge_diagnostics.get("merged_quantity_lines_count",0)} profile={result.profile_name}')
        except Exception as exc:
            print(f'[ERROR] {image_file.name}: {exc}')

    pd.DataFrame([asdict(row) for row in all_rows]).to_csv(output_dir / 'combined_receipts.csv', index=False)
    pd.DataFrame([asdict(row) for row in report_rows]).to_csv(output_dir / 'processing_report.csv', index=False)
    write_benchmark_summary(output_dir, report_rows)

    print(f'Output: {output_dir}')


if __name__ == '__main__':
    main()
