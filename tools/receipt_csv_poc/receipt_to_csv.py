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
TOTAL_KEYWORDS = ('totaal', 'te betalen', 'kaartbetaling')
TOTAL_HINT_EXCLUDE_KEYWORDS = ('prijsvoordeel', 'totaal korting', 'btw totaal', 'biw totaal')
SUMMARY_DISCOUNT_KEYWORDS = ('totaal prijsvoordeel', 'totaal korting')


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
    run_result: str
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


def _candidate(line, amount: Decimal, reason: str) -> dict:
    return {
        'line_no': line.line_no,
        'amount': money(amount),
        'raw_line': line.raw_line,
        'reason': reason,
    }


def select_total_hint(total_candidates: list[dict]) -> tuple[dict | None, list[dict]]:
    selected = None
    excluded = []
    for candidate in total_candidates:
        lowered = str(candidate.get('raw_line', '')).lower()
        if any(keyword in lowered for keyword in TOTAL_HINT_EXCLUDE_KEYWORDS):
            excluded.append({**candidate, 'excluded_reason': 'summary_or_tax_total_not_payable_total'})
            continue
        if selected is None:
            selected = {**candidate, 'selected_total_hint_reason': 'first_payable_total_like_line'}
        else:
            previous_amount = to_decimal(selected.get('amount'))
            current_amount = to_decimal(candidate.get('amount'))
            if current_amount == previous_amount:
                selected = {**candidate, 'selected_total_hint_reason': 'later_matching_payable_total_like_line'}
            else:
                excluded.append({**candidate, 'excluded_reason': 'conflicting_total_hint_after_selection'})
    return selected, excluded


def select_discount_total(discount_candidates: list[dict]) -> tuple[Decimal, str, list[dict], list[dict]]:
    summary_candidates = []
    individual_candidates = []
    for candidate in discount_candidates:
        lowered = str(candidate.get('raw_line', '')).lower()
        if any(keyword in lowered for keyword in SUMMARY_DISCOUNT_KEYWORDS):
            summary_candidates.append(candidate)
        else:
            individual_candidates.append(candidate)

    if summary_candidates:
        selected = summary_candidates[-1]
        excluded = [{**candidate, 'excluded_reason': 'summary_discount_total_selected'} for candidate in individual_candidates]
        return to_decimal(selected.get('amount')), 'summary_discount_total', [selected], excluded

    selected_candidates = individual_candidates
    selected_total = sum((to_decimal(item['amount']) for item in selected_candidates), Decimal('0'))
    return selected_total, 'sum_individual_discount_lines', selected_candidates, []


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
            discount_candidates.append(_candidate(line, abs(last_amount), 'discount_keyword'))
        if any(keyword in lowered for keyword in TOTAL_KEYWORDS):
            total_candidates.append(_candidate(line, last_amount, 'total_keyword'))

    selected_total_hint, excluded_total_hints = select_total_hint(total_candidates)
    discount_total, selected_discount_strategy, selected_discount_candidates, excluded_discount_candidates = select_discount_total(discount_candidates)
    net_candidate = gross_sum - discount_total
    selected_total_amount = selected_total_hint.get('amount') if selected_total_hint else ''
    selected_total_decimal = to_decimal(selected_total_amount)
    difference = net_candidate - selected_total_decimal if selected_total_hint else net_candidate

    return {
        'store_hint': store_hint,
        'gross_line_sum': money(gross_sum),
        'discount_total_detected': money(discount_total),
        'net_total_candidate': money(net_candidate),
        'selected_total_hint': selected_total_hint,
        'selected_total_hint_reason': selected_total_hint.get('selected_total_hint_reason') if selected_total_hint else '',
        'net_vs_selected_total_difference': money(difference),
        'all_total_hints': total_candidates,
        'excluded_total_hints': excluded_total_hints,
        'selected_discount_strategy': selected_discount_strategy,
        'selected_discount_candidates': selected_discount_candidates,
        'excluded_discount_candidates': excluded_discount_candidates,
        'all_discount_candidates': discount_candidates,
        'discount_candidate_count': len(discount_candidates),
        'line_count_after_merge': len(rows),
        'totals_strategy': 'diagnostic_gross_minus_selected_discount_vs_selected_total_hint',
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
        'schema_version': 'receipt-ocr-poc-v9-ssot-diagnostic-financials',
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
        run_result='success',
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
    summary = {
        'schema_version': 'receipt-ocr-benchmark-v9-ssot-diagnostic-financials',
        'created_at': datetime.now(timezone.utc).isoformat(),
        'total_receipts': len(report_rows),
        'run_success_count': sum(1 for row in report_rows if row.run_result == 'success'),
        'run_error_count': sum(1 for row in report_rows if row.run_result == 'error'),
        'total_detected_rows': sum(row.detected_rows for row in report_rows),
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
            selected_total = result.totals_diagnostics.get('selected_total_hint') or {}
            selected_total_amount = selected_total.get('amount', '')
            print(f'[OK] {image_file.name}: {len(rows)} rows refined={refined} merged={merged} gross={gross} net={net} selected_total={selected_total_amount} profile={result.profile_name}')
        except Exception as exc:
            print(f'[ERROR] {image_file.name}: {exc}')

    pd.DataFrame([asdict(row) for row in all_rows]).to_csv(output_dir / 'combined_receipts.csv', index=False)
    pd.DataFrame([asdict(row) for row in report_rows]).to_csv(output_dir / 'processing_report.csv', index=False)
    write_benchmark_summary(output_dir, report_rows)

    print(f'Output: {output_dir}')


if __name__ == '__main__':
    main()
