from __future__ import annotations

import argparse
import csv
import json
import re
from pathlib import Path
from typing import Any

PRICE_PATTERN = re.compile(r"\b(\d+[\.,]\d{2})\b")

LINE_PATTERNS = {
    'PAYMENT_TERMINAL': [r'terminal', r'x1j', r'periode'],
    'PAYMENT_CARD': [r'kaart', r'pin', r'maestro', r'visa', r'mastercard'],
    'NFC': [r'nfc', r'chip'],
    'TOTAL_LINE': [r'totaal', r'total', r'te betalen'],
    'DATE_TIME': [r'datum', r'\d{2}[-/]\d{2}[-/]\d{4}', r'\d{2}:\d{2}'],
    'FOOTER': [r'bedankt', r'tot ziens', r'bonuskaart', r'ah\.nl'],
}


def detect_price(text: str) -> str:
    match = PRICE_PATTERN.search(text or '')
    return match.group(1) if match else ''


def classify_line(text: str) -> tuple[str, str]:
    lowered = (text or '').lower()

    for line_type, patterns in LINE_PATTERNS.items():
        for pattern in patterns:
            if re.search(pattern, lowered, re.I):
                return line_type, f'matched:{pattern}'

    contains_price = bool(detect_price(text))
    alpha_count = len(re.findall(r'[a-zA-Z]', text or ''))

    if contains_price and alpha_count >= 3:
        return 'ARTICLE_CANDIDATE', 'price_and_alpha_content'

    return 'UNKNOWN', 'no_semantic_match'


def main() -> int:
    parser = argparse.ArgumentParser(description='R7c-13 AH foto 3 semantic line filtering diagnostics')
    parser.add_argument('--topology-json', required=True)
    parser.add_argument('--json-out', required=True)
    parser.add_argument('--csv-out', required=True)
    args = parser.parse_args()

    topology_payload = json.loads(Path(args.topology_json).read_text(encoding='utf-8'))
    pairs = topology_payload.get('sample_pairs') or []

    rows: list[dict[str, Any]] = []

    for pair in pairs:
        article_text = str(pair.get('article') or '').strip()
        price_value = str(pair.get('price') or '').strip()
        line_text = f'{article_text} {price_value}'.strip()

        line_type, reason = classify_line(line_text)

        rows.append({
            'line_text': line_text,
            'line_type': line_type,
            'contains_price': bool(price_value),
            'price_value': price_value,
            'is_article_candidate': line_type == 'ARTICLE_CANDIDATE',
            'rejection_reason': '' if line_type == 'ARTICLE_CANDIDATE' else reason,
        })

    summary = {
        'fixture_file': 'AH foto 3.jpg',
        'line_count': len(rows),
        'article_candidate_count': sum(1 for row in rows if row['is_article_candidate']),
        'filtered_noise_count': sum(1 for row in rows if not row['is_article_candidate']),
        'diagnostic_only': True,
        'rows': rows,
    }

    json_out = Path(args.json_out)
    json_out.parent.mkdir(parents=True, exist_ok=True)
    json_out.write_text(json.dumps(summary, indent=2, ensure_ascii=False), encoding='utf-8')

    csv_out = Path(args.csv_out)
    csv_out.parent.mkdir(parents=True, exist_ok=True)

    fieldnames = [
        'line_text',
        'line_type',
        'contains_price',
        'price_value',
        'is_article_candidate',
        'rejection_reason',
    ]

    with csv_out.open('w', encoding='utf-8', newline='') as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)

    print('R7c-13 AH foto 3 semantic line filtering diagnostics')
    print(f"line_count: {summary['line_count']}")
    print(f"article_candidate_count: {summary['article_candidate_count']}")
    print(f"filtered_noise_count: {summary['filtered_noise_count']}")
    print(f"json_written: {json_out}")
    print(f"csv_written: {csv_out}")
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
