from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
if str(ROOT / 'backend') not in sys.path:
    sys.path.insert(0, str(ROOT / 'backend'))

from app.main import compute_receipt_quality

CASES = [
    {
        'name': 'Plus explained 0.28',
        'receipt': {'store_name': 'Plus', 'purchase_at': '2026-04-01 12:00', 'total_amount': 10.00, 'line_total_sum': 9.72, 'discount_total': 0.0, 'line_discount_sum': 0.28, 'line_count': 3, 'parse_status': 'parsed'},
        'lines': [
            {'line_index': 1, 'display_label': 'Product A', 'display_quantity': 1, 'display_unit_price': 3.00, 'display_line_total': 3.00},
            {'line_index': 2, 'display_label': 'Korting', 'display_quantity': 1, 'display_unit_price': -0.28, 'display_line_total': -0.28, 'discount_amount': 0.28, 'is_promo_effect': True},
            {'line_index': 3, 'display_label': 'Product B', 'display_quantity': 1, 'display_unit_price': 6.72, 'display_line_total': 6.72},
        ],
        'expected_status': 'Gecontroleerd',
        'expected_source': 'explained_override',
    },
    {
        'name': 'AH explained 0.30',
        'receipt': {'store_name': 'Albert Heijn', 'purchase_at': '2026-04-01 12:00', 'total_amount': 15.00, 'line_total_sum': 14.70, 'discount_total': 0.0, 'line_discount_sum': 0.30, 'line_count': 2, 'parse_status': 'parsed'},
        'lines': [
            {'line_index': 1, 'display_label': 'Bonus', 'display_quantity': 1, 'display_unit_price': -0.30, 'display_line_total': -0.30, 'discount_amount': 0.30, 'is_promo_effect': True},
            {'line_index': 2, 'display_label': 'Artikelen', 'display_quantity': 1, 'display_unit_price': 15.00, 'display_line_total': 15.00},
        ],
        'expected_status': 'Gecontroleerd',
        'expected_source': 'explained_override',
    },
    {
        'name': 'Picnic explained 0.40',
        'receipt': {'store_name': 'Picnic', 'purchase_at': '2026-04-01 12:00', 'total_amount': 20.00, 'line_total_sum': 19.60, 'discount_total': 0.0, 'line_discount_sum': 0.40, 'line_count': 2, 'parse_status': 'parsed'},
        'lines': [
            {'line_index': 1, 'display_label': 'Actie product', 'display_quantity': 2, 'display_unit_price': 10.00, 'display_line_total': 19.60, 'discount_amount': 0.40},
            {'line_index': 2, 'display_label': 'Korting', 'display_quantity': 1, 'display_unit_price': 0.00, 'display_line_total': 0.00, 'discount_amount': 0.40, 'is_promo_effect': True},
        ],
        'expected_status': 'Gecontroleerd',
        'expected_source': 'explained_override',
    },
    {
        'name': 'Jumbo material mismatch',
        'receipt': {'store_name': 'Jumbo', 'purchase_at': '2026-04-01 12:00', 'total_amount': 10.00, 'line_total_sum': 7.00, 'discount_total': 0.0, 'line_discount_sum': 0.0, 'line_count': 2, 'parse_status': 'parsed'},
        'lines': [
            {'line_index': 1, 'display_label': 'Artikel 1', 'display_quantity': 1, 'display_unit_price': 3.00, 'display_line_total': 3.00},
            {'line_index': 2, 'display_label': 'Artikel 2', 'display_quantity': 1, 'display_unit_price': 4.00, 'display_line_total': 4.00},
        ],
        'expected_status': 'Controle nodig',
        'expected_source': 'material_rule',
    },
]


def main() -> int:
    failures: list[str] = []
    results = []
    for case in CASES:
        quality = compute_receipt_quality(case['receipt'], case['lines'])
        row = {
            'name': case['name'],
            'recommended_status': quality['recommended_status'],
            'decision_source': quality['final_review_decision_source'],
            'review_blocking_rules': quality['review_blocking_rules'],
        }
        results.append(row)
        if quality['recommended_status'] != case['expected_status']:
            failures.append(f"{case['name']}: expected status {case['expected_status']} got {quality['recommended_status']}")
        if quality['final_review_decision_source'] != case['expected_source']:
            failures.append(f"{case['name']}: expected source {case['expected_source']} got {quality['final_review_decision_source']}")
        if not quality['review_rule_trace']:
            failures.append(f"{case['name']}: review_rule_trace ontbreekt")

    print(json.dumps({'results': results, 'failures': failures}, indent=2, ensure_ascii=False))
    return 1 if failures else 0


if __name__ == '__main__':
    raise SystemExit(main())
