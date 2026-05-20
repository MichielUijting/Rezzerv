from __future__ import annotations

import argparse
import csv
import json
from collections import Counter
from pathlib import Path
from typing import Any
from urllib.error import URLError, HTTPError
from urllib.request import urlopen

REQUIRED_REGISTRY_COLUMNS = {
    'canonical_fixture_id',
    'baseline_receipt_id',
    'store_slug',
    'source_kind',
    'fixture_file',
    'expected_total',
    'expected_line_count',
    'target_status',
}

SSOT_SUMMARY_FIELDS = {
    'backend_status_counts',
    'po_norm_status_counts',
    'verschil',
}

DEFAULT_ENDPOINT_CANDIDATES = [
    '/api/receipt-status-baseline/validate',
    '/api/receipt-status-baseline/diagnose',
    '/api/receipt-status-baseline',
    '/api/dev/receipt-status-baseline/validate',
    '/api/dev/receipt-status-baseline/diagnose',
    '/api/dev/receipt-status-baseline',
    '/api/receipts/status-baseline/validate',
    '/api/receipts/status-baseline/diagnose',
]


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open('r', encoding='utf-8-sig', newline='') as handle:
        reader = csv.DictReader(handle)
        columns = set(reader.fieldnames or [])
        missing = REQUIRED_REGISTRY_COLUMNS - columns
        if missing:
            raise SystemExit(f'Missing canonical registry columns: {sorted(missing)}')
        return [dict(row) for row in reader]


def normalize_filename(value: Any) -> str:
    text = str(value or '').strip().lower().replace('\\', '/')
    text = text.split('/')[-1]
    return ''.join(ch for ch in text if ch.isalnum())


def normalize_receipt_id(value: Any) -> str:
    return str(value or '').strip().upper()


def load_status_payload(args: argparse.Namespace) -> dict[str, Any]:
    if args.status_json:
        path = Path(args.status_json)
        if not path.exists():
            raise SystemExit(f'Missing status JSON: {path}')
        return json.loads(path.read_text(encoding='utf-8-sig'))

    backend_url = str(args.backend_url or '').rstrip('/')
    if not backend_url:
        raise SystemExit('Provide either --status-json or --backend-url')

    candidates = [args.status_endpoint] if args.status_endpoint else DEFAULT_ENDPOINT_CANDIDATES
    failures: list[str] = []
    for endpoint in candidates:
        url = backend_url + endpoint
        try:
            with urlopen(url, timeout=args.timeout_seconds) as response:
                if response.status != 200:
                    failures.append(f'{url} -> HTTP {response.status}')
                    continue
                return json.loads(response.read().decode('utf-8'))
        except (HTTPError, URLError, TimeoutError, json.JSONDecodeError) as exc:
            failures.append(f'{url} -> {exc}')
    raise SystemExit('Could not load SSOT status payload from backend. Tried:\n- ' + '\n- '.join(failures))


def extract_summary(payload: dict[str, Any]) -> dict[str, Any]:
    summary = payload.get('summary') or payload.get('validation_summary') or {}
    if not isinstance(summary, dict):
        raise SystemExit('SSOT payload does not contain a dict summary/validation_summary')
    missing = SSOT_SUMMARY_FIELDS - set(summary)
    if missing:
        raise SystemExit(f'SSOT summary missing required fields: {sorted(missing)}')
    return summary


def extract_details(payload: dict[str, Any]) -> list[dict[str, Any]]:
    details = payload.get('details')
    if isinstance(details, list):
        return [item for item in details if isinstance(item, dict)]
    # diagnose endpoint shape
    combined: list[dict[str, Any]] = []
    for key in ('criterion_mismatches', 'mapping_mismatches', 'technical_parse_status_mismatches'):
        value = payload.get(key)
        if isinstance(value, list):
            combined.extend(item for item in value if isinstance(item, dict))
    return combined


def detail_keys(detail: dict[str, Any]) -> list[str]:
    keys: list[str] = []
    for key in ('matched_original_filename', 'source_file', 'original_filename'):
        normalized = normalize_filename(detail.get(key))
        if normalized and normalized not in keys:
            keys.append(normalized)
    receipt_id = normalize_receipt_id(detail.get('receipt_id'))
    if receipt_id and receipt_id not in keys:
        keys.append(receipt_id)
    return keys


def build_detail_index(details: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    index: dict[str, dict[str, Any]] = {}
    for detail in details:
        for key in detail_keys(detail):
            # Keep first match stable. The SSOT payload itself remains the source of truth.
            index.setdefault(key, detail)
    return index


def registry_key(row: dict[str, str]) -> str:
    return normalize_filename(row.get('fixture_file'))


def validate_ssot_payload(summary: dict[str, Any], details: list[dict[str, Any]]) -> list[str]:
    failures: list[str] = []
    if int(summary.get('verschil') or 0) != 0:
        failures.append(f"SSOT verschil must be 0, got {summary.get('verschil')!r}")
    if summary.get('backend_status_counts') != summary.get('po_norm_status_counts'):
        failures.append('backend_status_counts must equal po_norm_status_counts')
    for detail in details:
        if 'po_norm_status_label' not in detail and 'actual_status_label' not in detail:
            failures.append(f"Detail missing po_norm_status_label/actual_status_label for {detail.get('source_file') or detail.get('receipt_id')}")
        if str(detail.get('technical_parse_status') or '').strip() and detail.get('po_norm_status'):
            # Diagnostic only: allowed to differ, but never used as status truth.
            continue
    return failures


def main() -> int:
    parser = argparse.ArgumentParser(description='R7c-4 SSOT-compliant supermarket regression runner')
    parser.add_argument('--registry', required=True, help='R7c-3 canonical supermarket registry CSV')
    parser.add_argument('--status-json', default='', help='Optional JSON export from SSOT baseline endpoint')
    parser.add_argument('--backend-url', default='', help='Backend base URL, e.g. http://localhost:8011')
    parser.add_argument('--status-endpoint', default='', help='Optional explicit SSOT endpoint path')
    parser.add_argument('--timeout-seconds', type=int, default=10)
    parser.add_argument('--json-out', default='', help='Optional JSON result output path')
    parser.add_argument('--csv-out', default='', help='Optional CSV summary output path')
    args = parser.parse_args()

    registry = read_csv(Path(args.registry))
    payload = load_status_payload(args)
    summary = extract_summary(payload)
    details = extract_details(payload)
    detail_index = build_detail_index(details)

    failures = validate_ssot_payload(summary, details)
    rows: list[dict[str, Any]] = []
    missing_details: list[str] = []
    status_counter: Counter[str] = Counter()

    for fixture in registry:
        key = registry_key(fixture)
        detail = detail_index.get(key)
        if detail is None:
            missing_details.append(fixture['fixture_file'])
            rows.append({
                'canonical_fixture_id': fixture['canonical_fixture_id'],
                'fixture_file': fixture['fixture_file'],
                'baseline_receipt_id': fixture['baseline_receipt_id'],
                'expected_total': fixture['expected_total'],
                'expected_line_count': fixture['expected_line_count'],
                'po_norm_status_label': '',
                'technical_parse_status': '',
                'source_file': '',
                'matched_original_filename': '',
                'result': 'missing_ssot_detail',
                'failed_criteria': 'MISSING_SSOT_DETAIL',
            })
            continue
        label = detail.get('po_norm_status_label') or detail.get('actual_status_label') or ''
        status_counter[str(label)] += 1
        failed_criteria = detail.get('failed_criteria') or []
        rows.append({
            'canonical_fixture_id': fixture['canonical_fixture_id'],
            'fixture_file': fixture['fixture_file'],
            'baseline_receipt_id': fixture['baseline_receipt_id'],
            'expected_total': fixture['expected_total'],
            'actual_total': detail.get('total_amount', ''),
            'expected_line_count': fixture['expected_line_count'],
            'actual_line_count': detail.get('line_count', ''),
            'po_norm_status_label': label,
            'technical_parse_status': detail.get('technical_parse_status', ''),
            'source_file': detail.get('source_file', ''),
            'matched_original_filename': detail.get('matched_original_filename', ''),
            'result': detail.get('result', ''),
            'failed_criteria': ','.join(str(item) for item in failed_criteria),
        })

    if missing_details:
        failures.append(f'Missing SSOT details for supermarket fixtures: {missing_details}')

    output = {
        'policy_source': payload.get('policy_source', 'receipt_status_baseline_service_v4.py'),
        'policy_mode': payload.get('policy_mode', ''),
        'summary': summary,
        'registry_count': len(registry),
        'matched_detail_count': len(registry) - len(missing_details),
        'missing_detail_count': len(missing_details),
        'supermarket_status_counts': dict(status_counter),
        'rows': rows,
        'failures': failures,
    }

    print('R7c-4 SSOT supermarket regression runner')
    print(f"- Policy source: {output['policy_source']}")
    print(f"- Registry fixtures: {output['registry_count']}")
    print(f"- Matched SSOT details: {output['matched_detail_count']}")
    print(f"- Missing SSOT details: {output['missing_detail_count']}")
    print(f"- backend_status_counts: {summary.get('backend_status_counts')}")
    print(f"- po_norm_status_counts: {summary.get('po_norm_status_counts')}")
    print(f"- verschil: {summary.get('verschil')}")
    print(f"- Supermarket status counts: {dict(status_counter)}")

    if args.json_out:
        path = Path(args.json_out)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(output, indent=2, ensure_ascii=False), encoding='utf-8')
        print(f'- JSON written: {path}')

    if args.csv_out:
        path = Path(args.csv_out)
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open('w', encoding='utf-8', newline='') as handle:
            fieldnames = [
                'canonical_fixture_id', 'fixture_file', 'baseline_receipt_id',
                'expected_total', 'actual_total', 'expected_line_count', 'actual_line_count',
                'po_norm_status_label', 'technical_parse_status', 'source_file', 'matched_original_filename',
                'result', 'failed_criteria',
            ]
            writer = csv.DictWriter(handle, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(rows)
        print(f'- CSV written: {path}')

    if failures:
        print('\nR7c-4 SSOT supermarket regression runner failed:')
        for failure in failures:
            print('-', failure)
        return 1

    print('\nR7c-4 SSOT supermarket regression runner passed.')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
