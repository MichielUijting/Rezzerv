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
)
from app.services.receipt_service import (  # noqa: E402
    _extract_payload_from_paddle_item,
    _group_paddle_texts_to_lines,
    _normalize_paddle_collection,
    _parse_result_from_text_lines,
    _run_tesseract_ocr,
)

IMAGE_EXTENSIONS = {'.jpg', '.jpeg', '.png', '.webp'}

ROUTES = [
    'raw_paddle_current',
    'paddle_orientation_enabled',
    'paddle_unwarping_enabled',
    'tesseract_psm6_current',
    'tesseract_psm4',
    'tesseract_psm11',
]


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


def create_paddle(route_name: str):
    from paddleocr import PaddleOCR  # type: ignore

    if route_name == 'raw_paddle_current':
        return PaddleOCR(
            use_doc_orientation_classify=False,
            use_doc_unwarping=False,
            use_textline_orientation=False,
            lang='en',
        )
    if route_name == 'paddle_orientation_enabled':
        return PaddleOCR(
            use_doc_orientation_classify=True,
            use_doc_unwarping=False,
            use_textline_orientation=True,
            lang='en',
        )
    if route_name == 'paddle_unwarping_enabled':
        return PaddleOCR(
            use_doc_orientation_classify=True,
            use_doc_unwarping=True,
            use_textline_orientation=True,
            lang='en',
        )
    raise ValueError(route_name)


def first_present(payload: dict[str, Any], keys: tuple[str, ...]) -> Any:
    for key in keys:
        if key in payload and payload.get(key) is not None:
            return payload.get(key)
    return None


def collect_paddle_lines(image_path: Path, route_name: str) -> tuple[list[str], dict[str, Any]]:
    model = create_paddle(route_name)
    result = model.predict(str(image_path))

    texts: list[str] = []
    boxes: list[Any] = []
    scores: list[Any] = []

    for item in _normalize_paddle_collection(result):
        payload = _extract_payload_from_paddle_item(item)
        current_texts = _normalize_paddle_collection(first_present(payload, ('rec_texts', 'texts')))
        current_boxes = _normalize_paddle_collection(first_present(payload, ('rec_boxes', 'dt_polys', 'rec_polys')))
        current_scores = _normalize_paddle_collection(first_present(payload, ('rec_scores', 'scores')))
        texts.extend([str(text) for text in current_texts if str(text).strip()])
        boxes.extend(current_boxes[: len(current_texts)])
        scores.extend(current_scores[: len(current_texts)])

    grouped_lines = _group_paddle_texts_to_lines(texts, boxes if boxes else None)

    layout_boxes = []
    for text, score, box in zip(texts, scores, boxes):
        parsed = box_from_ocr_bbox(text, box, score)
        if parsed is not None:
            layout_boxes.append(parsed)

    diagnostic = build_text_layout_diagnostic(layout_boxes)

    return grouped_lines, {
        'ocr_line_count': len(grouped_lines),
        'region_count': diagnostic.candidate_regions_count,
        'selection_confidence': diagnostic.primary_region_confidence,
    }


def collect_tesseract_lines(image_path: Path, psm: int) -> tuple[list[str], dict[str, Any]]:
    text = _run_tesseract_ocr(str(image_path), config=f'--psm {psm}') or ''
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    return lines, {
        'ocr_line_count': len(lines),
        'region_count': 0,
        'selection_confidence': 0.0,
    }


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
            'store_name': '',
            'purchase_at': '',
            'total_amount': '',
            'article_line_count': 0,
            'parse_status': 'failed',
        }

    return {
        'store_name': result.store_name or '',
        'purchase_at': result.purchase_at or '',
        'total_amount': str(result.total_amount) if result.total_amount is not None else '',
        'article_line_count': len(result.lines or []),
        'parse_status': result.parse_status or '',
    }


def route_quality_score(parsed: dict[str, Any], metrics: dict[str, Any]) -> float:
    score = 0.0
    if parsed.get('store_name'):
        score += 0.25
    if parsed.get('purchase_at'):
        score += 0.15
    if parsed.get('total_amount'):
        score += 0.35
    article_count = int(parsed.get('article_line_count') or 0)
    score += min(0.20, article_count * 0.01)
    if float(metrics.get('selection_confidence') or 0.0) > 0.25:
        score += 0.05
    return round(min(1.0, score), 4)


def analyse_route(image_path: Path, fixture_file: str, route_name: str) -> dict[str, Any]:
    if route_name.startswith('paddle_') or route_name == 'raw_paddle_current':
        lines, metrics = collect_paddle_lines(image_path, route_name)
    elif route_name == 'tesseract_psm6_current':
        lines, metrics = collect_tesseract_lines(image_path, 6)
    elif route_name == 'tesseract_psm4':
        lines, metrics = collect_tesseract_lines(image_path, 4)
    elif route_name == 'tesseract_psm11':
        lines, metrics = collect_tesseract_lines(image_path, 11)
    else:
        raise ValueError(route_name)

    parsed = parse_preview(lines, fixture_file)
    quality = route_quality_score(parsed, metrics)

    return {
        'fixture_file': fixture_file,
        'route_name': route_name,
        'ocr_line_count': metrics['ocr_line_count'],
        'store_name': parsed['store_name'],
        'purchase_at': parsed['purchase_at'],
        'total_amount': parsed['total_amount'],
        'article_line_count': parsed['article_line_count'],
        'parse_status': parsed['parse_status'],
        'region_count': metrics['region_count'],
        'selection_confidence': metrics['selection_confidence'],
        'route_quality_score': quality,
        'diagnostic_only': True,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description='R7c-11 image preprocessing route diagnostics')
    parser.add_argument('--registry', required=True)
    parser.add_argument('--fixtures-zip', required=True)
    parser.add_argument('--json-out', required=True)
    parser.add_argument('--csv-out', required=True)
    args = parser.parse_args()

    registry = read_registry(Path(args.registry))
    zip_path = Path(args.fixtures_zip)

    results: list[dict[str, Any]] = []

    with tempfile.TemporaryDirectory(prefix='r7c11-routes-') as temp_dir:
        temp_root = Path(temp_dir)

        for row in registry:
            fixture_file = row.get('fixture_file') or ''
            if Path(fixture_file).suffix.lower() not in IMAGE_EXTENSIONS:
                continue

            image_path = extract_fixture(zip_path, fixture_file, temp_root)
            if image_path is None:
                continue

            for route_name in ROUTES:
                try:
                    result = analyse_route(image_path, fixture_file, route_name)
                    result['canonical_fixture_id'] = row.get('canonical_fixture_id')
                    results.append(result)
                except Exception as exc:
                    results.append({
                        'canonical_fixture_id': row.get('canonical_fixture_id'),
                        'fixture_file': fixture_file,
                        'route_name': route_name,
                        'ocr_line_count': 0,
                        'store_name': '',
                        'purchase_at': '',
                        'total_amount': '',
                        'article_line_count': 0,
                        'parse_status': f'error: {exc}',
                        'region_count': 0,
                        'selection_confidence': 0.0,
                        'route_quality_score': 0.0,
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
        'route_name',
        'ocr_line_count',
        'store_name',
        'purchase_at',
        'total_amount',
        'article_line_count',
        'parse_status',
        'region_count',
        'selection_confidence',
        'route_quality_score',
        'diagnostic_only',
    ]

    with csv_out.open('w', encoding='utf-8', newline='') as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(results)

    ah_rows = [row for row in results if re.search(r'ah foto 3', str(row.get('fixture_file', '')), re.I)]
    ah_rows = sorted(ah_rows, key=lambda row: float(row.get('route_quality_score') or 0.0), reverse=True)

    print('R7c-11 image preprocessing route diagnostics')
    print(f'- route results: {len(results)}')
    if ah_rows:
        best = ah_rows[0]
        print(f"- AH foto 3 best route: {best['route_name']}")
        print(f"- AH foto 3 best total_amount: {best['total_amount']}")
        print(f"- AH foto 3 best route_quality_score: {best['route_quality_score']}")
    print(f'- JSON written: {json_out}')
    print(f'- CSV written: {csv_out}')
    print('- diagnostic_only: true')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
