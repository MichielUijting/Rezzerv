from __future__ import annotations

import argparse
import csv
import json
import re
import sys
import tempfile
import zipfile
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
for candidate in (ROOT, ROOT / 'backend', Path('/app')):
    candidate_text = str(candidate)
    if candidate.exists() and candidate_text not in sys.path:
        sys.path.insert(0, candidate_text)

from app.receipt_ingestion.text_layout_regions import (  # noqa: E402
    box_from_ocr_bbox,
    build_text_layout_diagnostic,
    select_primary_text_region,
)
from app.services.receipt_service import (  # noqa: E402
    _extract_payload_from_paddle_item,
    _group_paddle_texts_to_lines,
    _normalize_paddle_collection,
    _parse_result_from_text_lines,
    _get_paddle_ocr,
)

IMAGE_EXTENSIONS = {'.jpg', '.jpeg', '.png', '.webp'}


def normalize_name(value: str) -> str:
    text = str(value or '').strip().lower().replace('\\', '/')
    text = text.split('/')[-1]
    return ''.join(ch for ch in text if ch.isalnum())


def read_registry(path: Path) -> list[dict[str, str]]:
    with path.open('r', encoding='utf-8-sig', newline='') as handle:
        return list(csv.DictReader(handle))


def extract_fixture(zip_path: Path, fixture_file: str, output_dir: Path) -> Path | None:
    target = normalize_name(fixture_file)
    with zipfile.ZipFile(zip_path) as archive:
        for item in archive.infolist():
            if item.is_dir():
                continue
            if normalize_name(Path(item.filename).name) != target:
                continue
            output_path = output_dir / Path(item.filename).name
            output_path.write_bytes(archive.read(item))
            return output_path
    return None


def first_present(payload: dict[str, Any], keys: tuple[str, ...]) -> Any:
    for key in keys:
        if key in payload and payload.get(key) is not None:
            return payload.get(key)
    return None


def collect_paddle_payload(image_path: Path) -> tuple[list[str], list[Any], list[Any]]:
    model = _get_paddle_ocr()
    if model is None:
        raise SystemExit('PaddleOCR unavailable in backend runtime')
    result = model.predict(str(image_path))
    texts: list[str] = []
    scores: list[Any] = []
    boxes: list[Any] = []
    for item in _normalize_paddle_collection(result):
        payload = _extract_payload_from_paddle_item(item)
        current_texts = _normalize_paddle_collection(first_present(payload, ('rec_texts', 'texts')))
        current_scores = _normalize_paddle_collection(first_present(payload, ('rec_scores', 'scores')))
        current_boxes = _normalize_paddle_collection(first_present(payload, ('rec_boxes', 'dt_polys', 'rec_polys')))
        normalized_texts = [str(text) for text in current_texts if str(text).strip()]
        texts.extend(normalized_texts)
        scores.extend(current_scores[: len(normalized_texts)])
        boxes.extend(current_boxes[: len(normalized_texts)])
    return texts, scores, boxes


def parse_preview(lines: list[str], filename: str) -> dict[str, Any]:
    result = _parse_result_from_text_lines(
        lines,
        filename,
        rich_confidence=0.84,
        partial_confidence=0.64,
        review_confidence=0.36,
    ) if lines else None
    if result is None:
        return {
            'total_amount': '',
            'line_count': 0,
            'store_name': '',
            'purchase_at': '',
            'parse_status': 'failed',
        }
    return {
        'total_amount': str(result.total_amount) if result.total_amount is not None else '',
        'line_count': len(result.lines or []),
        'store_name': result.store_name or '',
        'purchase_at': result.purchase_at or '',
        'parse_status': result.parse_status or '',
    }


def box_inside_bbox(box: Any, selected_bbox: Any) -> bool:
    parsed = box_from_ocr_bbox('x', box, None)
    if parsed is None or not isinstance(selected_bbox, (list, tuple)) or len(selected_bbox) != 4:
        return False
    x_min, y_min, x_max, y_max = [float(value) for value in selected_bbox]
    margin_x = max(8.0, (x_max - x_min) * 0.03)
    margin_y = max(8.0, (y_max - y_min) * 0.03)
    return (
        parsed.x_center >= x_min - margin_x
        and parsed.x_center <= x_max + margin_x
        and parsed.y_center >= y_min - margin_y
        and parsed.y_center <= y_max + margin_y
    )


def analyse_fixture(image_path: Path, fixture_file: str) -> dict[str, Any]:
    texts, scores, boxes = collect_paddle_payload(image_path)
    layout_boxes = []
    for text, score, box in zip(texts, scores, boxes):
        parsed = box_from_ocr_bbox(text, box, score)
        if parsed is not None:
            layout_boxes.append(parsed)

    diagnostic = build_text_layout_diagnostic(layout_boxes)
    selection = select_primary_text_region(diagnostic.regions)
    selected_bbox = selection.get('selected_bbox')

    current_lines = _group_paddle_texts_to_lines(texts, boxes if boxes else None)
    selected_texts: list[str] = []
    selected_boxes: list[Any] = []
    for text, box in zip(texts, boxes):
        if box_inside_bbox(box, selected_bbox):
            selected_texts.append(text)
            selected_boxes.append(box)
    primary_region_lines = _group_paddle_texts_to_lines(selected_texts, selected_boxes if selected_boxes else None)

    current = parse_preview(current_lines, fixture_file)
    primary = parse_preview(primary_region_lines, fixture_file)
    current_total = current['total_amount']
    primary_total = primary['total_amount']

    return {
        'fixture_file': fixture_file,
        'text_box_count': len(layout_boxes),
        'candidate_regions_count': diagnostic.candidate_regions_count,
        'multi_text_regions_detected': diagnostic.multi_text_regions_detected,
        'selected_region_id': selection.get('selected_region_id'),
        'selected_bbox': selection.get('selected_bbox'),
        'selection_confidence': selection.get('selection_confidence'),
        'current_total_amount': current_total,
        'primary_region_total_amount': primary_total,
        'current_line_count': current['line_count'],
        'primary_region_line_count': primary['line_count'],
        'current_store_name': current['store_name'],
        'primary_region_store_name': primary['store_name'],
        'current_parse_status': current['parse_status'],
        'primary_region_parse_status': primary['parse_status'],
        'total_changed': bool(current_total != primary_total),
        'diagnostic_only': True,
        'current_ocr_line_count': len(current_lines),
        'primary_region_ocr_line_count': len(primary_region_lines),
        'selection_reason': selection.get('reason'),
        'regions': diagnostic.regions,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description='R7c-10 primary text region parse preview, diagnostic-only')
    parser.add_argument('--registry', required=True)
    parser.add_argument('--fixtures-zip', required=True)
    parser.add_argument('--json-out', required=True)
    parser.add_argument('--csv-out', required=True)
    args = parser.parse_args()

    registry = read_registry(Path(args.registry))
    zip_path = Path(args.fixtures_zip)
    results: list[dict[str, Any]] = []
    summary_rows: list[dict[str, Any]] = []

    with tempfile.TemporaryDirectory(prefix='r7c10-primary-preview-') as temp_dir:
        temp_root = Path(temp_dir)
        for row in registry:
            fixture_file = row.get('fixture_file') or ''
            if Path(fixture_file).suffix.lower() not in IMAGE_EXTENSIONS:
                continue
            image_path = extract_fixture(zip_path, fixture_file, temp_root)
            if image_path is None:
                continue
            result = analyse_fixture(image_path, fixture_file)
            result['canonical_fixture_id'] = row.get('canonical_fixture_id')
            results.append(result)
            summary_rows.append({
                'canonical_fixture_id': row.get('canonical_fixture_id'),
                'fixture_file': fixture_file,
                'multi_text_regions_detected': result['multi_text_regions_detected'],
                'selected_region_id': result['selected_region_id'],
                'selection_confidence': result['selection_confidence'],
                'current_total_amount': result['current_total_amount'],
                'primary_region_total_amount': result['primary_region_total_amount'],
                'current_line_count': result['current_line_count'],
                'primary_region_line_count': result['primary_region_line_count'],
                'total_changed': result['total_changed'],
                'diagnostic_only': True,
            })

    json_out = Path(args.json_out)
    json_out.parent.mkdir(parents=True, exist_ok=True)
    json_out.write_text(json.dumps(results, indent=2, ensure_ascii=False), encoding='utf-8')

    csv_out = Path(args.csv_out)
    csv_out.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = [
        'canonical_fixture_id',
        'fixture_file',
        'multi_text_regions_detected',
        'selected_region_id',
        'selection_confidence',
        'current_total_amount',
        'primary_region_total_amount',
        'current_line_count',
        'primary_region_line_count',
        'total_changed',
        'diagnostic_only',
    ]
    with csv_out.open('w', encoding='utf-8', newline='') as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(summary_rows)

    plus_rows = [row for row in summary_rows if re.search(r'plus foto 2', str(row.get('fixture_file', '')), re.I)]
    print('R7c-10 primary text region parse preview')
    print(f'- image fixtures analysed: {len(summary_rows)}')
    if plus_rows:
        plus = plus_rows[0]
        print(f"- Plus foto 2 current_total_amount: {plus['current_total_amount']}")
        print(f"- Plus foto 2 primary_region_total_amount: {plus['primary_region_total_amount']}")
        print(f"- Plus foto 2 total_changed: {plus['total_changed']}")
    print(f'- JSON written: {json_out}')
    print(f'- CSV written: {csv_out}')
    print('- diagnostic_only: true')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
