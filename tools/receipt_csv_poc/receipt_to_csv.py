from __future__ import annotations

import argparse
import json
import re
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from pathlib import Path

import pandas as pd
import pytesseract
from PIL import Image

from line_classifier import classify_lines, summarize_line_types
from profiles import get_profile_for_store
from profiles.base import PARSEABLE_LINE_TYPES

AMOUNT_PATTERN = re.compile(r'(?<!\d)(-?\d+[\.,]\d{2})(?!\d)')
SUPPORTED_EXTENSIONS = {'.jpg', '.jpeg', '.png', '.bmp', '.tif', '.tiff', '.webp'}
DISCOUNT_KEYWORDS = ('korting', 'voordeel', 'lidl plus', 'bonus')
TOTAL_KEYWORDS = ('totaal', 'te betalen')
RECONCILIATION_TOLERANCE = Decimal('0.02')


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
    refinement_diagnostics: dict
    totals_diagnostics: dict


def normalize_decimal(value: str) -> str:
    return value.replace(',', '.').strip()


def to_decimal(value: str | int | float | Decimal | None) -> Decimal:
    if value is None or value == '':
        return Decimal('0')
    try:
        return Decimal(str(value).replace(',', '.'))
    except (InvalidOperation, ValueError):
        return Decimal('0')


def money(value: Decimal) -> str:
    return str(value.quantize(Decimal('0.01')))


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


def parse_receipt_lines(text: str, source_file: str, store_hint: str, profile_name: str, classified_lines, product_block):
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
                store_hint=store_hint,
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


def extract_amounts(line: str) -> list[Decimal]:
    return [to_decimal(amount) for amount in AMOUNT_PATTERN.findall(line)]


def _reconciliation_status(diff: Decimal, total_hint: str, discount_count: int) -> tuple[str, float, list[str]]:
    warnings: list[str] = []
    if not total_hint:
        warnings.append('missing_total_hint')
    if diff.copy_abs() <= RECONCILIATION_TOLERANCE and total_hint:
        confidence = 0.95 if discount_count else 0.90
        return 'balanced', confidence, warnings
    if total_hint and diff.copy_abs() <= Decimal('0.10'):
        warnings.append('small_rounding_or_ocr_difference')
        return 'near_balance', 0.72, warnings
    if total_hint:
        warnings.append('gross_discount_net_mismatch')
    return 'needs_review', 0.35, warnings


def compute_totals_diagnostics(rows: list[ReceiptLine], classified_lines: list, store_hint: str) -> dict:
    gross_sum = sum((to_decimal(row.line_total) for row in rows), Decimal('0'))
    discount_candidates = []
    total_candidates = []

    for line in classified_lines:
        normalized = line.normalized_line or ''
        lowered = normalized.lower()
        amounts = extract_amounts(normalized)
        if not amounts:
            continue
        last_amount = amounts[-1]
        if any(keyword in lowered for keyword in DISCOUNT_KEYWORDS):
            discount_candidates.append({
                'line_no': line.line_no,
                'amount': money(abs(last_amount)),
                'raw_line': line.raw_line,
                'reason': 'discount_keyword',
            })
        if any(keyword in lowered for keyword in TOTAL_KEYWORDS):
            total_candidates.append({
                'line_no': line.line_no,
                'amount': money(last_amount),
                'raw_line': line.raw_line,
                'reason': 'total_keyword',
            })

    discount_total = sum((to_decimal(item['amount']) for item in discount_candidates), Decimal('0'))
    net_candidate = gross_sum - discount_total
    best_total_hint = total_candidates[-1]['amount'] if total_candidates else ''
    hinted_total = to_decimal(best_total_hint)
    difference = net_candidate - hinted_total if best_total_hint else net_candidate
    status, confidence, warnings = _reconciliation_status(difference, best_total_hint, len(discount_candidates))

    return {
        'store_hint': store_hint,
        'gross_line_sum': money(gross_sum),
        'discount_total_detected': money(discount_total),
        'net_total_candidate': money(net_candidate),
        'total_amount_hints': total_candidates,
        'best_total_amount_hint': best_total_hint,
        'net_vs_best_total_difference': money(difference),
        'financial_reconciliation_status': status,
        'financial_reconciliation_confidence': confidence,
        'financial_reconciliation_warnings': warnings,
        'discount_candidates': discount_candidates,
        'discount_candidate_count': len(discount_candidates),
        'line_count_after_merge': len(rows),
        'totals_strategy': 'gross_minus_detected_discounts_vs_best_total_hint',
    }


def process_receipt(image_path: Path, output_dir: Path, lang: str):
    text = pytesseract.image_to_string(Image.open(image_path), lang=lang)

    store_hint = detect_store_hint(text, image_path.name)
    profile = get_profile_for_store(store_hint)

    classified_lines = classify_lines(text)
    classified_lines, refinement_diagnostics = profile.refine_classified_lines(classified_lines)
    line_type_counts = summarize_line_types(classified_lines)

    product_block = profile.detect_product_block(classified_lines)

    rows = parse_receipt_lines(
        text,
        image_path.name,
        store_hint,
        profile.profile_name,
        classified_lines,
        product_block,
    )

    merged_rows, merge_diagnostics = profile.merge_quantity_lines(rows, classified_lines)
    totals_diagnostics = compute_totals_diagnostics(merged_rows, classified_lines, store_hint)

    metadata = {
        'source_file': image_path.name,
        'created_at': datetime.now(timezone.utc).isoformat(),
        'store_hint': store_hint,
        'profile_name': profile.profile_name,
        'detected_rows': len(merged_rows),
        'line_type_counts': line_type_counts,
        'product_block': product_block,
        'merge_diagnostics': merge_diagnostics,
        'refinement_diagnostics': refinement_diagnostics,
        'totals_diagnostics': totals_diagnostics,
    }

    json_dir = output_dir / 'json'
    csv_dir = output_dir / 'per_receipt'
    json_dir.mkdir(parents=True, exist_ok=True)
    csv_dir.mkdir(parents=True, exist_ok=True)

    json_payload = {
        'schema_version': 'receipt-ocr-poc-v8-financial-reconciliation',
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
        refinement_diagnostics=refinement_diagnostics,
        totals_diagnostics=totals_diagnostics,
    )


def list_image_files(input_dir: Path):
    return sorted([p for p in input_dir.iterdir() if p.suffix.lower() in SUPPORTED_EXTENSIONS])


def write_benchmark_summary(output_dir: Path, report_rows: list[ReceiptResult]):
    status_counts: dict[str, int] = {}
    for row in report_rows:
        status = row.totals_diagnostics.get('financial_reconciliation_status', 'unknown')
        status_counts[status] = status_counts.get(status, 0) + 1

    summary = {
        'schema_version': 'receipt-ocr-benchmark-v8-financial-reconciliation',
        'created_at': datetime.now(timezone.utc).isoformat(),
        'total_receipts': len(report_rows),
        'success_count': sum(1 for row in report_rows if row.status == 'success'),
        'error_count': sum(1 for row in report_rows if row.status == 'error'),
        'total_detected_rows': sum(row.detected_rows for row in report_rows),
        'financial_reconciliation_status_counts': status_counts,
        'profiles_used': {},
        'merge_diagnostics': {},
        'refinement_diagnostics': {},
        'totals_diagnostics': {},
    }

    for row in report_rows:
        summary['profiles_used'][row.source_file] = row.profile_name
        summary['merge_diagnostics'][row.source_file] = row.merge_diagnostics
        summary['refinement_diagnostics'][row.source_file] = row.refinement_diagnostics
        summary['totals_diagnostics'][row.source_file] = row.totals_diagnostics

    (output_dir / 'benchmark_summary.json').write_text(
        json.dumps(summary, ensure_ascii=False, indent=2),
        encoding='utf-8',
    )


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--input', default='input_receipts')
    parser.add_argument('--output', default='output_csv')
    parser.add_argument('--lang', default='nld+eng')
    args = parser.parse_args()

    input_dir = Path(args.input)
    output_dir = Path(args.output)
    output_dir.mkdir(parents=True, exist_ok=True)

    all_rows = []
    report_rows = []

    for image_file in list_image_files(input_dir):
        try:
            rows, result = process_receipt(image_file, output_dir, args.lang)
            all_rows.extend(rows)
            report_rows.append(result)
            refined = result.refinement_diagnostics.get('refined_lines_count', 0)
            merged = result.merge_diagnostics.get('merged_quantity_lines_count', 0)
            gross = result.totals_diagnostics.get('gross_line_sum', '0.00')
            net = result.totals_diagnostics.get('net_total_candidate', '0.00')
            recon = result.totals_diagnostics.get('financial_reconciliation_status', 'unknown')
            print(f'[OK] {image_file.name}: {len(rows)} rows refined={refined} merged={merged} gross={gross} net={net} recon={recon} profile={result.profile_name}')
        except Exception as exc:
            print(f'[ERROR] {image_file.name}: {exc}')

    pd.DataFrame([asdict(row) for row in all_rows]).to_csv(output_dir / 'combined_receipts.csv', index=False)
    pd.DataFrame([asdict(row) for row in report_rows]).to_csv(output_dir / 'processing_report.csv', index=False)
    write_benchmark_summary(output_dir, report_rows)

    print(f'Output: {output_dir}')


if __name__ == '__main__':
    main()
