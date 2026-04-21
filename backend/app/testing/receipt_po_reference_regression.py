from __future__ import annotations

import json
import re
import sys
import zipfile
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[3]
if str(ROOT / 'backend') not in sys.path:
    sys.path.insert(0, str(ROOT / 'backend'))

from app.services.receipt_service import detect_mime_type, parse_receipt_content  # noqa: E402

REFERENCE_DIR = ROOT / 'backend' / 'app' / 'testing' / 'receipt_parsing'
REFERENCE_MANIFEST_PATH = REFERENCE_DIR / 'po_reference_manifest.json'
SOURCE_ALIAS_MANIFEST_PATH = REFERENCE_DIR / 'source_alias_manifest.json'
DEFAULT_ZIP_PATH = ROOT.parent / 'Kassabonnen testoutput.zip'


@dataclass
class ComparisonRow:
    source_file: str
    source_key: str
    result: str
    score: float
    field_matches: dict[str, Any]
    notes: list[str]


def _load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding='utf-8'))


def _normalize_text(value: Any) -> str:
    text = str(value or '').strip().lower()
    text = re.sub(r'\s+', ' ', text)
    return text


def _normalize_source_key(value: str) -> str:
    name = Path(str(value)).name
    stem = Path(name).stem
    suffix = Path(name).suffix.lower()
    stem = _normalize_text(stem)
    stem = re.sub(r'\s+', ' ', stem).strip()
    suffix = '.jpg' if suffix == '.jpeg' else suffix
    suffix = '.png' if suffix == '.webp' else suffix
    return f'{stem}{suffix}' if suffix else stem


def _load_alias_map() -> tuple[dict[str, str], dict[str, list[str]]]:
    payload = _load_json(SOURCE_ALIAS_MANIFEST_PATH)
    alias_to_key: dict[str, str] = {}
    key_to_aliases: dict[str, list[str]] = {}
    for item in payload.get('items', []):
        key = _normalize_source_key(item.get('source_key'))
        aliases = [_normalize_source_key(alias) for alias in item.get('aliases', [])]
        aliases.append(key)
        clean_aliases = sorted({alias for alias in aliases if alias})
        key_to_aliases[key] = clean_aliases
        for alias in clean_aliases:
            alias_to_key[alias] = key
    return alias_to_key, key_to_aliases


def _canonical_source_key(name: str, alias_map: dict[str, str]) -> str:
    normalized = _normalize_source_key(name)
    canonical = alias_map.get(normalized, normalized)
    stem_only = re.sub(r'\.(png|jpg|jpeg|webp|pdf|eml)$', '', normalized)
    for alias, key in alias_map.items():
        alias_stem = re.sub(r'\.(png|jpg|jpeg|webp|pdf|eml)$', '', alias)
        if alias_stem == stem_only:
            canonical = key
            break
    return canonical


def _parse_decimal(value: Any) -> Decimal | None:
    if value is None or value == '':
        return None
    if isinstance(value, Decimal):
        return value.quantize(Decimal('0.01'))
    try:
        return Decimal(str(value)).quantize(Decimal('0.01'))
    except (InvalidOperation, ValueError):
        return None


def _normalize_store(value: Any) -> str:
    text = _normalize_text(value)
    aliases = {
        'ah': 'albert heijn',
        'albert heijn': 'albert heijn',
        'plus': 'plus',
        'jumbo': 'jumbo',
        'jumbo b.v.': 'jumbo',
        'lidl nederland gmbh': 'lidl',
        'lidl': 'lidl',
        'coolblue b.v.': 'coolblue',
        'coolblue': 'coolblue',
        'picnic b.v.': 'picnic',
        'picnic': 'picnic',
        'bol': 'bol',
        'bol.com': 'bol',
        'karwei': 'karwei',
        'mediamarkt': 'mediamarkt',
        'media markt': 'mediamarkt',
        'action': 'action',
        'gamma': 'gamma',
        'hornbach': 'hornbach',
        'aldi': 'aldi',
    }
    return aliases.get(text, text)


def _extract_date(value: Any) -> str | None:
    text = str(value or '').strip()
    if not text:
        return None
    if 'T' in text:
        return text.split('T', 1)[0]
    m = re.search(r'(\d{4}-\d{2}-\d{2})', text)
    if m:
        return m.group(1)
    m = re.search(r'(\d{2})-(\d{2})-(\d{4})', text)
    if m:
        return f'{m.group(3)}-{m.group(2)}-{m.group(1)}'
    return None


def _normalize_label(value: Any) -> str:
    text = _normalize_text(value)
    text = text.replace('€', '')
    text = re.sub(r'[^a-z0-9]+', ' ', text)
    return re.sub(r'\s+', ' ', text).strip()


def _compare_lines(parsed_lines: list[dict[str, Any]], reference_lines: list[dict[str, Any]]) -> tuple[float, dict[str, Any], list[str]]:
    parsed_norm = []
    for line in parsed_lines or []:
        parsed_norm.append({
            'label': _normalize_label(line.get('normalized_label') or line.get('raw_label')),
            'quantity': float(line.get('quantity') or 0) if line.get('quantity') is not None else None,
            'unit_price': _parse_decimal(line.get('unit_price')),
            'line_total': _parse_decimal(line.get('line_total')),
        })
    reference_norm = []
    for line in reference_lines or []:
        reference_norm.append({
            'label': _normalize_label(line.get('product_name')),
            'quantity': float(line.get('quantity') or 0) if line.get('quantity') is not None else None,
            'unit_price': _parse_decimal(line.get('unit_price')),
            'line_total': _parse_decimal(line.get('line_total')),
        })
    matched = 0
    label_matches = 0
    price_matches = 0
    remaining = parsed_norm.copy()
    notes: list[str] = []
    for ref in reference_norm:
        idx = next((i for i, item in enumerate(remaining) if item['label'] == ref['label']), None)
        if idx is None:
            continue
        item = remaining.pop(idx)
        matched += 1
        label_matches += 1
        qty_ok = ref['quantity'] is None or item['quantity'] is None or abs((item['quantity'] or 0) - (ref['quantity'] or 0)) < 0.01
        unit_ok = ref['unit_price'] is None or item['unit_price'] == ref['unit_price']
        total_ok = ref['line_total'] is None or item['line_total'] == ref['line_total']
        if qty_ok and unit_ok and total_ok:
            price_matches += 1
    ref_count = len(reference_norm)
    parsed_count = len(parsed_norm)
    count_ok = parsed_count == ref_count
    line_score = 0.0
    if ref_count:
        line_score = (label_matches / ref_count) * 0.6 + (price_matches / ref_count) * 0.4
    else:
        line_score = 1.0 if parsed_count == 0 else 0.0
    if not count_ok:
        notes.append(f'LINE_COUNT_MISMATCH: parsed={parsed_count} expected={ref_count}')
    if label_matches < ref_count:
        notes.append(f'LABEL_MATCH_LOW:{label_matches}/{ref_count}')
        notes.append(f'MISSING_LABELS:{max(ref_count - label_matches, 0)}')
    if price_matches < ref_count:
        notes.append(f'PRICE_MATCH_LOW:{price_matches}/{ref_count}')
        notes.append(f'PRICE_MISMATCH_COUNT:{max(ref_count - price_matches, 0)}')
    return line_score, {
        'parsed_line_count': parsed_count,
        'expected_line_count': ref_count,
        'label_matches': label_matches,
        'price_matches': price_matches,
    }, notes


def _iter_input_files(path: Path) -> list[tuple[str, bytes]]:
    if path.suffix.lower() == '.zip':
        with zipfile.ZipFile(path) as archive:
            items = []
            for info in archive.infolist():
                if info.is_dir():
                    continue
                items.append((Path(info.filename).name, archive.read(info.filename)))
            return items
    if path.is_dir():
        return [(candidate.name, candidate.read_bytes()) for candidate in sorted(path.iterdir()) if candidate.is_file()]
    return [(path.name, path.read_bytes())]


def run_receipt_po_reference_regression(input_path: Path | None = None) -> dict[str, Any]:
    alias_map, key_to_aliases = _load_alias_map()
    reference_payload = _load_json(REFERENCE_MANIFEST_PATH)
    reference_receipts = {
        _normalize_source_key(item['source_key']): item
        for item in reference_payload.get('receipts', [])
    }
    status_only_sources = {
        _normalize_source_key(item['source_key']): item
        for item in reference_payload.get('status_only_sources', [])
    }

    target_path = input_path or DEFAULT_ZIP_PATH
    results: list[dict[str, Any]] = []
    failures: list[str] = []
    exact_match = partial_match = mismatch = 0

    for filename, file_bytes in _iter_input_files(target_path):
        source_key = _canonical_source_key(filename, alias_map)
        reference = reference_receipts.get(source_key)
        status_only = status_only_sources.get(source_key)
        mime_type = detect_mime_type(filename, file_bytes)
        parsed = parse_receipt_content(file_bytes, filename, mime_type)
        parsed_store = _normalize_store(parsed.store_name)
        parsed_date = _extract_date(parsed.purchase_at)
        parsed_total = _parse_decimal(parsed.total_amount)
        row_notes: list[str] = []

        if reference is None:
            if status_only is not None:
                result = 'mismatch'
                score = 0.0
                row_notes.append('STATUS_ONLY_REFERENCE')
                failures.append(f'{filename}: only status-only reference exists ({status_only.get("processing_status")})')
            else:
                result = 'mismatch'
                score = 0.0
                row_notes.append('NO_REFERENCE_FOUND')
                failures.append(f'{filename}: no reference found in manifest')
            results.append({
                'source_file': filename,
                'source_key': source_key,
                'mime_type': mime_type,
                'result': result,
                'score': score,
                'store_name': parsed.store_name,
                'purchase_at': parsed.purchase_at,
                'total_amount': str(parsed.total_amount) if parsed.total_amount is not None else None,
                'field_matches': {},
                'notes': row_notes,
            })
            mismatch += 1
            continue

        expected_store = _normalize_store(reference.get('store_name'))
        if filename != reference.get('source_file'):
            row_notes.append('SOURCE_ALIAS_MISMATCH')
        expected_date = _extract_date(reference.get('purchase_date'))
        expected_total = _parse_decimal(reference.get('total_amount'))
        store_ok = parsed_store == expected_store
        date_ok = parsed_date == expected_date
        total_ok = parsed_total == expected_total
        line_score, line_meta, line_notes = _compare_lines(parsed.lines or [], reference.get('lines', []))
        row_notes.extend(line_notes)
        score = (0.15 if store_ok else 0) + (0.15 if date_ok else 0) + (0.20 if total_ok else 0) + (0.50 * line_score)
        if store_ok and date_ok and total_ok and line_score >= 0.999:
            result = 'exact_match'
            exact_match += 1
        elif total_ok and line_meta.get('parsed_line_count') == line_meta.get('expected_line_count') and score >= 0.55:
            result = 'partial_match'
            partial_match += 1
        else:
            result = 'mismatch'
            mismatch += 1
        if not store_ok:
            row_notes.append('STORE_MISMATCH')
            failures.append(f'{filename}: store mismatch parsed={parsed.store_name!r} expected={reference.get("store_name")!r}')
        if not date_ok:
            row_notes.append('DATE_MISMATCH')
            failures.append(f'{filename}: date mismatch parsed={parsed_date!r} expected={expected_date!r}')
        if not total_ok:
            row_notes.append('TOTAL_MISMATCH')
            failures.append(f'{filename}: total mismatch parsed={parsed_total!s} expected={expected_total!s}')
        results.append({
            'source_file': filename,
            'source_key': source_key,
            'reference_source_file': reference.get('source_file'),
            'known_aliases': key_to_aliases.get(source_key, []),
            'mime_type': mime_type,
            'parse_status': parsed.parse_status,
            'result': result,
            'score': round(score, 4),
            'store_name': parsed.store_name,
            'purchase_at': parsed.purchase_at,
            'total_amount': str(parsed.total_amount) if parsed.total_amount is not None else None,
            'field_matches': {
                'store_name': store_ok,
                'purchase_date': date_ok,
                'total_amount': total_ok,
                **line_meta,
            },
            'expected': {
                'store_name': reference.get('store_name'),
                'purchase_date': expected_date,
                'total_amount': str(expected_total) if expected_total is not None else None,
                'expected_line_count': reference.get('line_count'),
                'extraction_status': reference.get('extraction_status'),
            },
            'notes': row_notes,
        })

    return {
        'reference_manifest': str(REFERENCE_MANIFEST_PATH.relative_to(ROOT)),
        'source_alias_manifest': str(SOURCE_ALIAS_MANIFEST_PATH.relative_to(ROOT)),
        'input_path': str(target_path),
        'exact_match_count': exact_match,
        'partial_match_count': partial_match,
        'mismatch_count': mismatch,
        'results': results,
        'failures': failures,
    }


def main() -> int:
    input_path = Path(sys.argv[1]).resolve() if len(sys.argv) > 1 else (DEFAULT_ZIP_PATH.resolve() if DEFAULT_ZIP_PATH.exists() else DEFAULT_ZIP_PATH)
    report = run_receipt_po_reference_regression(input_path if input_path.exists() else None)
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report.get('mismatch_count', 0) == 0 else 1


if __name__ == '__main__':
    raise SystemExit(main())
