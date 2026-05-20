from __future__ import annotations

import argparse
import csv
import json
import mimetypes
import sys
import tempfile
import zipfile
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
for candidate in (ROOT, ROOT / 'backend', Path('/app')):
    text = str(candidate)
    if candidate.exists() and text not in sys.path:
        sys.path.insert(0, text)

from app.services.receipt_service import parse_receipt_content  # noqa: E402
from app.receipt_ingestion.preprocessing.safe_rotation import apply_safe_rotation_preprocessing  # noqa: E402

IMAGE_EXTENSIONS = {'.jpg', '.jpeg', '.png', '.bmp', '.webp'}


def extract_fixtures(zip_path: Path, workdir: Path) -> list[Path]:
    images: list[Path] = []
    with zipfile.ZipFile(zip_path) as archive:
        for item in archive.infolist():
            if item.is_dir():
                continue
            name = Path(item.filename).name
            if Path(name).suffix.lower() not in IMAGE_EXTENSIONS:
                continue
            out = workdir / name
            out.write_bytes(archive.read(item))
            images.append(out)
    return sorted(images, key=lambda path: path.name.lower())


def detect_mime(path: Path) -> str:
    guessed, _ = mimetypes.guess_type(path.name)
    if guessed:
        return guessed
    if path.suffix.lower() in {'.jpg', '.jpeg'}:
        return 'image/jpeg'
    if path.suffix.lower() == '.png':
        return 'image/png'
    if path.suffix.lower() == '.webp':
        return 'image/webp'
    return 'application/octet-stream'


def normalize_amount(value: Any) -> str | None:
    if value is None:
        return None
    return f'{float(value):.2f}'


def parse_fixture(path: Path) -> dict[str, Any]:
    file_bytes = path.read_bytes()
    rotation_decision = None
    try:
        _bytes, rotation_decision_obj = apply_safe_rotation_preprocessing(file_bytes, path.name)
        rotation_decision = rotation_decision_obj.to_dict()
    except Exception as exc:
        rotation_decision = {
            'preprocessing_step': 'safe_rotation',
            'rotation_allowed': False,
            'selected_route': 'original',
            'fallback_reason': [f'rotation_diagnostic_failed:{exc.__class__.__name__}'],
        }

    result = parse_receipt_content(file_bytes, path.name, detect_mime(path))
    lines = result.lines or []
    return {
        'fixture': path.name,
        'is_receipt': bool(result.is_receipt),
        'parse_status': result.parse_status,
        'store_name': result.store_name,
        'purchase_at': result.purchase_at,
        'total_amount': normalize_amount(result.total_amount),
        'line_count': len(lines),
        'confidence_score': result.confidence_score,
        'safe_rotation': rotation_decision,
        'line_labels': [str(line.get('raw_label') or line.get('normalized_label') or '') for line in lines[:12]],
    }


def load_baseline(path: Path | None) -> dict[str, dict[str, Any]]:
    if not path or not path.exists():
        return {}
    payload = json.loads(path.read_text(encoding='utf-8'))
    rows = payload.get('results') if isinstance(payload, dict) else payload
    if not isinstance(rows, list):
        return {}
    return {str(row.get('fixture')): row for row in rows if row.get('fixture')}


def regression_checks(row: dict[str, Any], baseline: dict[str, Any] | None) -> list[str]:
    failures: list[str] = []
    fixture = str(row.get('fixture') or '')
    rotation = row.get('safe_rotation') or {}

    if not row.get('is_receipt'):
        failures.append('not_detected_as_receipt')
    if not row.get('store_name'):
        failures.append('store_missing')
    if not row.get('total_amount'):
        failures.append('total_missing')

    fixture_lower = fixture.lower()
    if fixture_lower == 'ah foto 3.jpg' and rotation.get('selected_route') != 'rotate_only':
        failures.append('ah_foto_3_expected_rotate_only')
    if fixture_lower == 'jumbo foto 1.jpeg' and rotation.get('selected_route') != 'original':
        failures.append('jumbo_foto_1_must_fallback_original')
    if fixture_lower == 'plus foto 1.jpeg' and rotation.get('selected_route') != 'original':
        failures.append('plus_foto_1_must_fallback_original')

    if baseline:
        if baseline.get('store_name') and row.get('store_name') != baseline.get('store_name'):
            failures.append('store_changed_vs_baseline')
        if baseline.get('total_amount') and row.get('total_amount') != baseline.get('total_amount'):
            failures.append('total_changed_vs_baseline')
        baseline_lines = int(baseline.get('line_count') or 0)
        current_lines = int(row.get('line_count') or 0)
        if baseline_lines >= 2 and current_lines < max(1, baseline_lines - 2):
            failures.append('line_count_regression_vs_baseline')
        baseline_route = ((baseline.get('safe_rotation') or {}).get('selected_route'))
        current_route = rotation.get('selected_route')
        if baseline_route and current_route != baseline_route:
            failures.append('safe_rotation_route_changed_vs_baseline')

    return failures


def main() -> int:
    parser = argparse.ArgumentParser(description='R7c-19 production OCR quality regression gate')
    parser.add_argument('--fixtures-zip', required=True)
    parser.add_argument('--json-out', required=True)
    parser.add_argument('--csv-out', required=True)
    parser.add_argument('--baseline-json')
    parser.add_argument('--fail-on-regression', action='store_true')
    args = parser.parse_args()

    baseline = load_baseline(Path(args.baseline_json) if args.baseline_json else None)

    with tempfile.TemporaryDirectory(prefix='r7c19-') as td:
        fixtures = extract_fixtures(Path(args.fixtures_zip), Path(td))
        results = []
        for fixture in fixtures:
            try:
                row = parse_fixture(fixture)
            except Exception as exc:
                row = {
                    'fixture': fixture.name,
                    'is_receipt': False,
                    'parse_status': 'crashed',
                    'store_name': None,
                    'purchase_at': None,
                    'total_amount': None,
                    'line_count': 0,
                    'confidence_score': None,
                    'safe_rotation': None,
                    'line_labels': [],
                    'exception': f'{exc.__class__.__name__}: {exc}',
                }
            failures = regression_checks(row, baseline.get(row['fixture']))
            row['quality_gate_passed'] = not failures
            row['regression_failures'] = failures
            results.append(row)

    summary = {
        'fixture_count': len(results),
        'passed_count': sum(1 for row in results if row.get('quality_gate_passed')),
        'failed_count': sum(1 for row in results if not row.get('quality_gate_passed')),
        'rotation_allowed_count': sum(1 for row in results if (row.get('safe_rotation') or {}).get('selected_route') == 'rotate_only'),
        'fallback_original_count': sum(1 for row in results if (row.get('safe_rotation') or {}).get('selected_route') == 'original'),
        'ah_foto_3_rotate_only': any(row.get('fixture') == 'AH foto 3.jpg' and (row.get('safe_rotation') or {}).get('selected_route') == 'rotate_only' for row in results),
        'jumbo_foto_1_original': any(row.get('fixture') == 'Jumbo foto 1.jpeg' and (row.get('safe_rotation') or {}).get('selected_route') == 'original' for row in results),
        'plus_foto_1_original': any(row.get('fixture') == 'PLUS foto 1.jpeg' and (row.get('safe_rotation') or {}).get('selected_route') == 'original' for row in results),
    }

    payload = {
        'diagnostic_only': True,
        'gate': 'R7c-19 production OCR quality regression gate',
        'baseline_used': bool(baseline),
        'summary': summary,
        'results': results,
    }

    json_out = Path(args.json_out)
    json_out.parent.mkdir(parents=True, exist_ok=True)
    json_out.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding='utf-8')

    csv_out = Path(args.csv_out)
    csv_out.parent.mkdir(parents=True, exist_ok=True)
    fields = [
        'fixture', 'quality_gate_passed', 'regression_failures', 'parse_status',
        'store_name', 'purchase_at', 'total_amount', 'line_count', 'confidence_score',
        'safe_rotation_route', 'safe_rotation_angle', 'safe_rotation_confidence', 'safe_rotation_fallback_reason',
    ]
    with csv_out.open('w', encoding='utf-8', newline='') as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for row in results:
            rotation = row.get('safe_rotation') or {}
            writer.writerow({
                'fixture': row.get('fixture'),
                'quality_gate_passed': row.get('quality_gate_passed'),
                'regression_failures': ';'.join(row.get('regression_failures') or []),
                'parse_status': row.get('parse_status'),
                'store_name': row.get('store_name'),
                'purchase_at': row.get('purchase_at'),
                'total_amount': row.get('total_amount'),
                'line_count': row.get('line_count'),
                'confidence_score': row.get('confidence_score'),
                'safe_rotation_route': rotation.get('selected_route'),
                'safe_rotation_angle': rotation.get('estimated_angle_deg'),
                'safe_rotation_confidence': rotation.get('angle_confidence'),
                'safe_rotation_fallback_reason': ';'.join(rotation.get('fallback_reason') or []),
            })

    print('R7c-19 production OCR quality regression gate')
    print(f"fixture_count: {summary['fixture_count']}")
    print(f"passed_count: {summary['passed_count']}")
    print(f"failed_count: {summary['failed_count']}")
    print(f"rotation_allowed_count: {summary['rotation_allowed_count']}")
    print(f"fallback_original_count: {summary['fallback_original_count']}")
    print(f"json_written: {json_out}")
    print(f"csv_written: {csv_out}")

    if args.fail_on_regression and summary['failed_count']:
        return 2
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
