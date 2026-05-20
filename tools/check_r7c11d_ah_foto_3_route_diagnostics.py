from __future__ import annotations

import argparse
import csv
import json
import re
import subprocess
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

from app.services.receipt_service import (  # noqa: E402
    _extract_payload_from_paddle_item,
    _group_paddle_texts_to_lines,
    _normalize_paddle_collection,
    _parse_result_from_text_lines,
)

PADDLE_CACHE: dict[str, Any] = {}
ROUTES = ['raw_paddle_current', 'paddle_orientation_enabled', 'paddle_unwarping_enabled', 'tesseract_psm6_current', 'tesseract_psm4', 'tesseract_psm11']


def find_ah_foto_3(zip_path: Path, output_dir: Path) -> Path:
    with zipfile.ZipFile(zip_path) as archive:
        for item in archive.infolist():
            name = Path(item.filename).name
            if item.is_dir():
                continue
            if re.search(r'ah\s*foto\s*3', name, re.I):
                out = output_dir / name
                out.write_bytes(archive.read(item))
                return out
    raise SystemExit('AH foto 3 not found in fixtures zip')


def get_paddle(route: str):
    if route in PADDLE_CACHE:
        return PADDLE_CACHE[route]
    from paddleocr import PaddleOCR  # type: ignore
    print(f'initializing {route}', flush=True)
    if route == 'raw_paddle_current':
        model = PaddleOCR(use_doc_orientation_classify=False, use_doc_unwarping=False, use_textline_orientation=False, lang='en')
    elif route == 'paddle_orientation_enabled':
        model = PaddleOCR(use_doc_orientation_classify=True, use_doc_unwarping=False, use_textline_orientation=True, lang='en')
    elif route == 'paddle_unwarping_enabled':
        model = PaddleOCR(use_doc_orientation_classify=True, use_doc_unwarping=True, use_textline_orientation=True, lang='en')
    else:
        raise ValueError(route)
    PADDLE_CACHE[route] = model
    return model


def first_present(payload: dict[str, Any], keys: tuple[str, ...]) -> Any:
    for key in keys:
        if key in payload and payload.get(key) is not None:
            return payload.get(key)
    return None


def normalize_list(value: Any) -> list[Any]:
    return _normalize_paddle_collection(value)


def paddle_lines(image_path: Path, route: str) -> list[str]:
    result = get_paddle(route).predict(str(image_path))
    texts: list[str] = []
    boxes: list[Any] = []
    for item in normalize_list(result):
        payload = _extract_payload_from_paddle_item(item)
        current_texts = normalize_list(first_present(payload, ('rec_texts', 'texts')))
        current_boxes = normalize_list(first_present(payload, ('rec_boxes', 'dt_polys', 'rec_polys')))
        clean = [str(text) for text in current_texts if str(text).strip()]
        texts.extend(clean)
        boxes.extend(current_boxes[:len(clean)])
    return _group_paddle_texts_to_lines(texts, boxes if boxes else None)


def tesseract_lines(image_path: Path, psm: int) -> list[str]:
    command = ['tesseract', str(image_path), 'stdout', '-l', 'nld+eng', '--psm', str(psm)]
    completed = subprocess.run(command, capture_output=True, text=True, check=False, timeout=90)
    if completed.returncode != 0:
        raise RuntimeError((completed.stderr or '').strip() or 'tesseract failed')
    return [line.strip() for line in (completed.stdout or '').splitlines() if line.strip()]


def parse_lines(lines: list[str]) -> dict[str, Any]:
    result = _parse_result_from_text_lines(lines, 'AH foto 3.jpg', rich_confidence=0.84, partial_confidence=0.64, review_confidence=0.36) if lines else None
    if result is None:
        return {'store_name': '', 'purchase_at': '', 'total_amount': '', 'article_line_count': 0, 'parse_status': 'failed'}
    return {
        'store_name': result.store_name or '',
        'purchase_at': result.purchase_at or '',
        'total_amount': str(result.total_amount) if result.total_amount is not None else '',
        'article_line_count': len(result.lines or []),
        'parse_status': result.parse_status or '',
    }


def score(parsed: dict[str, Any], ocr_count: int) -> float:
    value = 0.0
    if parsed['store_name']:
        value += 0.25
    if parsed['purchase_at']:
        value += 0.15
    if parsed['total_amount']:
        value += 0.35
    value += min(0.20, int(parsed['article_line_count'] or 0) * 0.01)
    if ocr_count >= 10:
        value += 0.05
    return round(min(1.0, value), 4)


def analyse(image_path: Path, route: str) -> dict[str, Any]:
    if route.startswith('paddle') or route == 'raw_paddle_current':
        lines = paddle_lines(image_path, route)
    elif route == 'tesseract_psm6_current':
        lines = tesseract_lines(image_path, 6)
    elif route == 'tesseract_psm4':
        lines = tesseract_lines(image_path, 4)
    elif route == 'tesseract_psm11':
        lines = tesseract_lines(image_path, 11)
    else:
        raise ValueError(route)
    parsed = parse_lines(lines)
    return {'fixture_file': 'AH foto 3.jpg', 'route_name': route, 'ocr_line_count': len(lines), **parsed, 'route_quality_score': score(parsed, len(lines)), 'diagnostic_only': True}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument('--fixtures-zip', required=True)
    parser.add_argument('--json-out', required=True)
    parser.add_argument('--csv-out', required=True)
    args = parser.parse_args()
    with tempfile.TemporaryDirectory(prefix='r7c11d-ah3-') as td:
        image_path = find_ah_foto_3(Path(args.fixtures_zip), Path(td))
        results = []
        for route in ROUTES:
            print(f'running AH foto 3 via {route}', flush=True)
            try:
                results.append(analyse(image_path, route))
            except Exception as exc:
                results.append({'fixture_file': 'AH foto 3.jpg', 'route_name': route, 'ocr_line_count': 0, 'store_name': '', 'purchase_at': '', 'total_amount': '', 'article_line_count': 0, 'parse_status': f'error: {exc}', 'route_quality_score': 0.0, 'diagnostic_only': True})
    Path(args.json_out).parent.mkdir(parents=True, exist_ok=True)
    Path(args.json_out).write_text(json.dumps(results, indent=2, ensure_ascii=False), encoding='utf-8')
    fields = ['fixture_file', 'route_name', 'ocr_line_count', 'store_name', 'purchase_at', 'total_amount', 'article_line_count', 'parse_status', 'route_quality_score', 'diagnostic_only']
    with Path(args.csv_out).open('w', encoding='utf-8', newline='') as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(results)
    best = sorted(results, key=lambda row: float(row['route_quality_score']), reverse=True)[0]
    print('R7c-11d AH foto 3 route diagnostics')
    print(f"best_route: {best['route_name']}")
    print(f"best_total_amount: {best['total_amount']}")
    print(f"json_written: {args.json_out}")
    print(f"csv_written: {args.csv_out}")
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
