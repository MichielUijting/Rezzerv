from __future__ import annotations

import argparse
import json
import re
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any

from add_amount_region_zone_diagnostics import _image_by_stem

DEFAULT_TARGETS = {
    'Lidl App 1',
    'Lidl App 2',
    'Jumbo foto 1',
    'Jumbo App 1',
}
DISCOUNT_KEYWORDS = ('korting', 'prijsvoordeel', 'voordeel', 'bonus', 'lidl plus', 'actie', 'gratis')
SUMMARY_DISCOUNT_KEYWORDS = ('totaal prijsvoordeel', 'totaal korting', 'uw korting')
PROTECTED_DISCOUNT_CONTEXT = ('totaal', 'btw', 'biw', 'kaart', 'pin', 'betaling', 'terminal')
AMOUNT_PATTERN = re.compile(r'(?<!\d)(-?\d+[\.,]\d{2})(?!\d)')
MAX_ADJACENT_DISTANCE = 2


def _read_key_values(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    if not path.exists():
        return values
    for line in path.read_text(encoding='utf-8').splitlines():
        if '=' in line:
            key, value = line.split('=', 1)
            values[key.strip()] = value.strip()
    return values


def _candidate_run_paths(raw_run_path: str) -> list[Path]:
    raw = Path(raw_run_path)
    candidates = [raw]
    prefix = Path('tools') / 'receipt_csv_poc'
    prefix_parts = prefix.parts
    parts = raw.parts
    if len(parts) > len(prefix_parts) and parts[:len(prefix_parts)] == prefix_parts:
        candidates.append(Path(*parts[len(prefix_parts):]))
    if raw.name:
        candidates.append(Path('test_runs') / raw.name)
    return candidates


def _is_valid_run_dir(path: Path) -> bool:
    return (path / 'json').exists() and (path / 'benchmark_summary.json').exists()


def _find_latest_valid_run(test_runs_dir: Path = Path('test_runs')) -> Path:
    valid_runs = [path for path in test_runs_dir.glob('run_*') if path.is_dir() and _is_valid_run_dir(path)]
    if not valid_runs:
        raise FileNotFoundError(f'No valid run directory found under {test_runs_dir}')
    return sorted(valid_runs, key=lambda path: path.name)[-1]


def _read_latest_run_path(latest_file: Path) -> Path:
    values = _read_key_values(latest_file)
    raw_run_path = values.get('run_path', '')
    if raw_run_path:
        for candidate in _candidate_run_paths(raw_run_path):
            if _is_valid_run_dir(candidate):
                return candidate
        print(f'[WARN] LATEST_PUSHED_RUN points to invalid or incomplete run: {raw_run_path}')
    fallback = _find_latest_valid_run()
    print(f'[INFO] Using latest valid local run instead: {fallback}')
    return fallback


def _money(value: Decimal) -> str:
    return str(value.quantize(Decimal('0.01')))


def _amount(value: Any) -> Decimal:
    if value is None or value == '':
        return Decimal('0')
    text = str(value).strip().replace('€', '').replace('EUR', '').replace('eur', '').replace(' ', '')
    if ',' in text and '.' in text:
        if text.rfind(',') > text.rfind('.'):
            text = text.replace('.', '').replace(',', '.')
        else:
            text = text.replace(',', '')
    else:
        text = text.replace(',', '.')
    try:
        return Decimal(text).quantize(Decimal('0.01'))
    except (InvalidOperation, ValueError):
        match = AMOUNT_PATTERN.search(str(value))
        if match:
            return Decimal(match.group(1).replace(',', '.')).quantize(Decimal('0.01'))
    return Decimal('0')


def _extract_amounts(text: str) -> list[Decimal]:
    return [_amount(match) for match in AMOUNT_PATTERN.findall(text or '')]


def _lower(text: Any) -> str:
    return str(text or '').lower()


def _is_discount_like_line(line: dict[str, Any]) -> bool:
    text = _lower(line.get('normalized_line') or line.get('raw_line'))
    return any(keyword in text for keyword in DISCOUNT_KEYWORDS) or line.get('line_type') == 'discount_line'


def _is_summary_discount_line(line: dict[str, Any]) -> bool:
    text = _lower(line.get('normalized_line') or line.get('raw_line'))
    return any(keyword in text for keyword in SUMMARY_DISCOUNT_KEYWORDS)


def _line_key(line: dict[str, Any]) -> int:
    try:
        return int(line.get('line_no') or 0)
    except Exception:
        return 0


def _article_rows(receipt_json: dict[str, Any]) -> list[dict[str, Any]]:
    rows = []
    for row in receipt_json.get('lines', []):
        if row.get('line_type') != 'product_line':
            continue
        rows.append(row)
    return rows


def _discount_lines(receipt_json: dict[str, Any]) -> list[dict[str, Any]]:
    result = []
    for line in receipt_json.get('classified_lines', []):
        if not _is_discount_like_line(line):
            continue
        amounts = _extract_amounts(line.get('normalized_line') or line.get('raw_line') or '')
        if not amounts:
            continue
        result.append({
            'line_no': _line_key(line),
            'line_type': line.get('line_type'),
            'raw_line': line.get('raw_line'),
            'normalized_line': line.get('normalized_line'),
            'amounts': [_money(abs(amount)) for amount in amounts],
            'selected_discount_amount': _money(abs(amounts[-1])),
            'is_summary_discount_line': _is_summary_discount_line(line),
        })
    return result


def _find_adjacent_discount(article: dict[str, Any], discount_lines: list[dict[str, Any]]) -> tuple[dict[str, Any] | None, str, float]:
    product_line_no = _line_key(article)
    candidates = []
    for discount in discount_lines:
        if discount.get('is_summary_discount_line'):
            continue
        distance = int(discount.get('line_no') or 0) - product_line_no
        if 1 <= distance <= MAX_ADJACENT_DISTANCE:
            confidence = 0.92 if distance == 1 else 0.78
            candidates.append((distance, confidence, discount))
        elif -1 <= distance < 0:
            candidates.append((abs(distance) + 10, 0.55, discount))
    if not candidates:
        return None, 'no_adjacent_non_summary_discount_line', 0.0
    distance, confidence, discount = sorted(candidates, key=lambda item: (item[0], -item[1]))[0]
    reason = 'adjacent_discount_line_after_product' if int(discount.get('line_no') or 0) > product_line_no else 'adjacent_discount_line_before_product'
    return discount, reason, confidence


def _summary_discount_context(discount_lines: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [line for line in discount_lines if line.get('is_summary_discount_line')]


def _build_article_discount(article: dict[str, Any], discount: dict[str, Any], reason: str, confidence: float) -> dict[str, Any]:
    gross = _amount(article.get('line_total'))
    discount_amount = _amount(discount.get('selected_discount_amount'))
    net = gross - discount_amount
    return {
        'product_line_no': _line_key(article),
        'product_text': article.get('item_text'),
        'gross_article_amount': _money(gross),
        'discount_amount': _money(discount_amount),
        'net_article_amount': _money(net),
        'discount_source_line_no': discount.get('line_no'),
        'discount_source_raw_line': discount.get('raw_line'),
        'discount_link_reason': reason,
        'discount_confidence': round(confidence, 3),
        'selected_article_amount_reason': 'diagnostic_only_gross_minus_adjacent_discount',
        'diagnostic_only': True,
        'reconstruction_applied': False,
    }


def build_discount_netto_diagnostics(receipt_json: dict[str, Any]) -> dict[str, Any]:
    articles = _article_rows(receipt_json)
    discounts = _discount_lines(receipt_json)
    article_discounts = []
    rejected_discount_links = []

    for article in articles:
        discount, reason, confidence = _find_adjacent_discount(article, discounts)
        if discount is not None:
            article_discounts.append(_build_article_discount(article, discount, reason, confidence))
        else:
            rejected_discount_links.append({
                'product_line_no': _line_key(article),
                'product_text': article.get('item_text'),
                'gross_article_amount': article.get('line_total'),
                'reject_reason': reason,
                'diagnostic_only': True,
                'reconstruction_applied': False,
            })

    summary_discounts = _summary_discount_context(discounts)
    return {
        'diagnostic_scope': 'article_level_discount_netto_diagnostics',
        'diagnostic_only': True,
        'reconstruction_applied': False,
        'article_discount_count': len(article_discounts),
        'rejected_article_discount_link_count': len(rejected_discount_links),
        'summary_discount_line_count': len(summary_discounts),
        'discount_line_count': len(discounts),
        'article_discounts': article_discounts,
        'summary_discount_lines': summary_discounts,
        'rejected_discount_links': rejected_discount_links,
        'rules': {
            'max_adjacent_distance': MAX_ADJACENT_DISTANCE,
            'summary_discount_lines_are_not_linked_to_single_article': True,
            'csv_output_changed': False,
            'parser_output_changed': False,
        },
    }


def update_targeted_run(input_dir: Path, output_dir: Path, targets: set[str]) -> None:
    json_dir = output_dir / 'json'
    if not json_dir.exists():
        raise FileNotFoundError(f'JSON output directory not found: {json_dir}')

    image_lookup = _image_by_stem(input_dir)
    summary_path = output_dir / 'benchmark_summary.json'
    summary = json.loads(summary_path.read_text(encoding='utf-8')) if summary_path.exists() else {}
    summary.setdefault('discount_netto_diagnostics', {})

    processed = 0
    skipped = 0
    for target in sorted(targets):
        json_path = json_dir / f'{target}.json'
        if not json_path.exists():
            skipped += 1
            continue
        payload = json.loads(json_path.read_text(encoding='utf-8'))
        diagnostics = build_discount_netto_diagnostics(payload)
        payload.setdefault('metadata', {})['discount_netto_diagnostics'] = diagnostics
        json_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding='utf-8')
        source_file = payload.get('metadata', {}).get('source_file') or f'{target}.json'
        summary['discount_netto_diagnostics'][source_file] = diagnostics
        processed += 1

    summary['schema_version'] = 'receipt-ocr-benchmark-v29-discount-netto-diagnostics'
    summary['discount_netto_diagnostics_processed_receipts'] = processed
    summary['discount_netto_diagnostics_skipped_receipts'] = skipped
    summary['discount_netto_diagnostics_targeted_only'] = True
    summary_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding='utf-8')
    print(f'[OK] Discount/netto diagnostics added for {processed} receipts; skipped={skipped}')


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument('--input', default='input_receipts')
    parser.add_argument('--output', default='')
    parser.add_argument('--latest-file', default='LATEST_PUSHED_RUN.txt')
    parser.add_argument('--targets', nargs='*', default=sorted(DEFAULT_TARGETS))
    args = parser.parse_args()

    output_dir = Path(args.output) if args.output else _read_latest_run_path(Path(args.latest_file))
    update_targeted_run(Path(args.input), output_dir, set(args.targets))


if __name__ == '__main__':
    main()
