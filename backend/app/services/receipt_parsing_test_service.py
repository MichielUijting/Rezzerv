from __future__ import annotations

import json
import unicodedata
from decimal import Decimal
from pathlib import Path
from typing import Any

from app.services.receipt_service import parse_receipt_content

FIXTURE_ROOT = Path(__file__).resolve().parents[1] / 'testing' / 'receipt_parsing'
BASELINE_PATH = FIXTURE_ROOT / 'receipt_parsing_baseline.json'


def _normalize_label(value: str | None) -> str:
    normalized = unicodedata.normalize('NFKD', str(value or ''))
    normalized = ''.join(ch for ch in normalized if not unicodedata.combining(ch))
    normalized = normalized.lower().strip()
    normalized = ''.join(ch if ch.isalnum() else ' ' for ch in normalized)
    return ' '.join(normalized.split())


def _normalize_amount(value: Any) -> str | None:
    if value is None or value == '':
        return None
    try:
        return f"{Decimal(str(value)).quantize(Decimal('0.01')):.2f}"
    except Exception:
        return None


def _load_baseline() -> list[dict[str, Any]]:
    return json.loads(BASELINE_PATH.read_text(encoding='utf-8'))


def run_receipt_parsing_baseline_results() -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []
    for entry in _load_baseline():
        fixture_filename = str(entry.get('fixture_file') or '').strip()
        fixture_path = FIXTURE_ROOT / 'fixtures' / fixture_filename
        fixture_bytes = fixture_path.read_bytes()
        parse_result = parse_receipt_content(fixture_bytes, fixture_filename, 'text/plain')

        expected_store = entry.get('store_chain')
        expected_datetime = entry.get('purchase_datetime')
        expected_total = _normalize_amount(entry.get('total_eur'))
        expected_count = int(entry.get('line_item_count') or 0)
        expected_labels = [_normalize_label(item.get('name')) for item in entry.get('line_items', [])]

        actual_store = parse_result.store_name
        actual_datetime = parse_result.purchase_at
        actual_total = _normalize_amount(parse_result.total_amount)
        actual_count = len(parse_result.lines)
        actual_labels = [_normalize_label(line.get('normalized_label') or line.get('raw_label')) for line in parse_result.lines]

        matches: list[str] = []
        mismatches: list[str] = []
        if actual_store == expected_store:
            matches.append('store')
        else:
            mismatches.append(f"store verwacht={expected_store} actueel={actual_store}")
        if actual_datetime == expected_datetime:
            matches.append('purchase_datetime')
        else:
            mismatches.append(f"purchase_datetime verwacht={expected_datetime} actueel={actual_datetime}")
        if actual_total == expected_total:
            matches.append('total_eur')
        else:
            mismatches.append(f"total_eur verwacht={expected_total} actueel={actual_total}")
        if actual_count == expected_count:
            matches.append('line_item_count')
        else:
            mismatches.append(f"line_item_count verwacht={expected_count} actueel={actual_count}")
        if actual_labels == expected_labels:
            matches.append('line_labels')
        else:
            missing = [label for label in expected_labels if label not in actual_labels]
            extra = [label for label in actual_labels if label not in expected_labels]
            label_parts: list[str] = []
            if missing:
                label_parts.append('ontbrekend=' + ', '.join(missing[:5]))
            if extra:
                label_parts.append('extra=' + ', '.join(extra[:5]))
            mismatches.append('line_labels ' + ('; '.join(label_parts) if label_parts else 'volgorde afwijkend'))

        passed = not mismatches
        results.append({
            'name': entry['receipt_id'],
            'status': 'passed' if passed else 'failed',
            'error': None if passed else ' | '.join(mismatches),
            'details': {
                'expected': {
                    'store': expected_store,
                    'purchase_datetime': expected_datetime,
                    'total_eur': expected_total,
                    'line_item_count': expected_count,
                    'line_labels': expected_labels,
                },
                'actual': {
                    'store': actual_store,
                    'purchase_datetime': actual_datetime,
                    'total_eur': actual_total,
                    'line_item_count': actual_count,
                    'line_labels': actual_labels,
                    'parse_status': parse_result.parse_status,
                    'confidence_score': parse_result.confidence_score,
                },
                'matches': matches,
                'mismatches': mismatches,
            },
        })
    return results
