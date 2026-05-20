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

from app.receipt_ingestion.text_layout_regions import box_from_ocr_bbox, build_text_layout_diagnostic

IMAGE_EXTENSIONS = {'.jpg', '.jpeg', '.png', '.webp'}


def normalize_name(value: str) -> str:
    text = str(value or '').strip().lower().replace('\\', '/')
    text = text.split('/')[-1]
    return ''.join(ch for ch in text if ch.isalnum())


def first_present(payload: dict[str, Any], keys: tuple[str, ...]) -> Any:
    for key in keys:
        if key in payload and payload.get(key) is not None:
            return payload.get(key)
    return None


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


def import_paddle_ocr():
    try:
        from paddleocr import PaddleOCR  # type: ignore
    except Exception as exc:
        raise SystemExit('PaddleOCR is required for R7c-8 diagnostics: ' + str(exc))
    return PaddleOCR


def normalize_collection(value: Any) -> list[Any]:
    if value is None:
        return []
    if hasattr(value, 'tolist'):
        try:
            value = value.tolist()
        except Exception:
            pass
    if isinstance(value, (str, bytes, bytearray)):
        return [value]
    try:
        return list(value)
    except TypeError:
        return [value]


def payload_from_item(item: Any) -> dict[str, Any]:
    candidates = [item]
    for attr_name in ('res', 'json', 'result'):
        attr = getattr(item, attr_name, None)
        if attr is None:
            continue
        try:
            candidates.append(attr() if callable(attr) else attr)
        except Exception:
            pass
    to_dict = getattr(item, 'to_dict', None)
    if callable(to_dict):
        try:
            candidates.append(to_dict())
        except Exception:
            pass
    for candidate in candidates:
        if isinstance(candidate, dict):
            if isinstance(candidate.get('res'), dict):
                return candidate['res']
            return candidate
    return {}


def create_paddle_model():
    PaddleOCR = import_paddle_ocr()
    configs = [
        {'use_doc_orientation_classify': False, 'use_doc_unwarping': False, 'use_textline_orientation': False, 'lang': 'en'},
        {'use_angle_cls': True, 'lang': 'en'},
        {'lang': 'en'},
    ]
    last_error: Exception | None = None
    for config in configs:
        try:
            return PaddleOCR(**config)
        except Exception as exc:
            last_error = exc
    raise SystemExit('Could not initialize PaddleOCR: ' + str(last_error))


def analyse_image(model: Any, image_path: Path) -> dict[str, Any]:
    result = model.predict(str(image_path))
    boxes = []
    for item in normalize_collection(result):
        payload = payload_from_item(item)
        texts = normalize_collection(first_present(payload, ('rec_texts', 'texts')))
        scores = normalize_collection(first_present(payload, ('rec_scores', 'scores')))
        raw_boxes = normalize_collection(first_present(payload, ('rec_boxes', 'dt_polys', 'rec_polys')))
        for index, text in enumerate(texts):
            score = scores[index] if index < len(scores) else None
            raw_box = raw_boxes[index] if index < len(raw_boxes) else None
            parsed = box_from_ocr_bbox(text, raw_box, score)
            if parsed is not None:
                boxes.append(parsed)
    diagnostic = build_text_layout_diagnostic(boxes)
    return {
        'text_box_count': len(boxes),
        'diagnostic': diagnostic.__dict__,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description='R7c-8 Paddle OCR text-layout diagnostics, diagnostic-only')
    parser.add_argument('--registry', required=True)
    parser.add_argument('--fixtures-zip', required=True)
    parser.add_argument('--json-out', required=True)
    parser.add_argument('--csv-out', required=True)
    args = parser.parse_args()

    registry = read_registry(Path(args.registry))
    zip_path = Path(args.fixtures_zip)
    model = create_paddle_model()
    results: list[dict[str, Any]] = []
    summary: list[dict[str, Any]] = []

    with tempfile.TemporaryDirectory(prefix='r7c8-layout-') as temp_dir:
        temp_root = Path(temp_dir)
        for row in registry:
            fixture_file = row.get('fixture_file') or ''
            if Path(fixture_file).suffix.lower() not in IMAGE_EXTENSIONS:
                continue
            image_path = extract_fixture(zip_path, fixture_file, temp_root)
            if image_path is None:
                continue
            analysis = analyse_image(model, image_path)
            diagnostic = analysis['diagnostic']
            output_row = {
                'canonical_fixture_id': row.get('canonical_fixture_id'),
                'fixture_file': fixture_file,
                'text_box_count': analysis['text_box_count'],
                'candidate_regions_count': diagnostic['candidate_regions_count'],
                'primary_region_id': diagnostic['primary_region_id'],
                'primary_region_confidence': diagnostic['primary_region_confidence'],
                'multi_text_regions_detected': diagnostic['multi_text_regions_detected'],
                'diagnostic_only': diagnostic['diagnostic_only'],
            }
            summary.append(output_row)
            results.append({**output_row, 'regions': diagnostic['regions']})

    Path(args.json_out).parent.mkdir(parents=True, exist_ok=True)
    Path(args.json_out).write_text(json.dumps(results, indent=2, ensure_ascii=False), encoding='utf-8')

    Path(args.csv_out).parent.mkdir(parents=True, exist_ok=True)
    fieldnames = ['canonical_fixture_id', 'fixture_file', 'text_box_count', 'candidate_regions_count', 'primary_region_id', 'primary_region_confidence', 'multi_text_regions_detected', 'diagnostic_only']
    with Path(args.csv_out).open('w', encoding='utf-8', newline='') as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(summary)

    plus_rows = [row for row in summary if re.search(r'plus foto 2', str(row.get('fixture_file', '')), re.I)]
    plus_multi = any(bool(row.get('multi_text_regions_detected')) for row in plus_rows)

    print('R7c-8 Paddle OCR text-layout diagnostics')
    print(f'- image fixtures analysed: {len(summary)}')
    print(f'- Plus foto 2 multi-text-region detected: {plus_multi}')
    print(f'- JSON written: {args.json_out}')
    print(f'- CSV written: {args.csv_out}')
    print('- diagnostic_only: true')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
