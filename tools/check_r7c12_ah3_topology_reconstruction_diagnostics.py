from __future__ import annotations

import argparse
import csv
import json
import math
import re
import sys
import tempfile
import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
for candidate in (ROOT, ROOT / 'backend', Path('/app')):
    text = str(candidate)
    if candidate.exists() and text not in sys.path:
        sys.path.insert(0, text)

from paddleocr import PaddleOCR  # type: ignore # noqa: E402

from app.services.receipt_service import (  # noqa: E402
    _extract_payload_from_paddle_item,
    _normalize_paddle_collection,
)


PRICE_PATTERN = re.compile(r"\b\d+[\.,]\d{2}\b")
TOTAL_PATTERN = re.compile(r"\b(totaal|total|te betalen)\b", re.I)


@dataclass
class OcrBox:
    text: str
    x1: float
    y1: float
    x2: float
    y2: float

    @property
    def center_y(self) -> float:
        return (self.y1 + self.y2) / 2.0

    @property
    def width(self) -> float:
        return max(0.0, self.x2 - self.x1)


MODEL: PaddleOCR | None = None


def get_model() -> PaddleOCR:
    global MODEL
    if MODEL is None:
        print('initializing raw_paddle_current once', flush=True)
        MODEL = PaddleOCR(
            use_doc_orientation_classify=False,
            use_doc_unwarping=False,
            use_textline_orientation=False,
            lang='en',
        )
    return MODEL


def normalize_name(value: str) -> str:
    value = str(value or '').strip().lower().replace('\\', '/')
    value = value.split('/')[-1]
    return ''.join(ch for ch in value if ch.isalnum())


def find_fixture(zip_path: Path, output_dir: Path) -> Path:
    with zipfile.ZipFile(zip_path) as archive:
        for item in archive.infolist():
            if item.is_dir():
                continue
            name = Path(item.filename).name
            if re.search(r'ah\s*foto\s*3', name, re.I):
                out = output_dir / name
                out.write_bytes(archive.read(item))
                return out
    raise SystemExit('AH foto 3 not found')


def flatten_points(raw_box: Any) -> tuple[float, float, float, float] | None:
    if not isinstance(raw_box, (list, tuple)):
        return None
    points: list[tuple[float, float]] = []
    for item in raw_box:
        if isinstance(item, (list, tuple)) and len(item) >= 2:
            try:
                points.append((float(item[0]), float(item[1])))
            except Exception:
                continue
    if not points:
        return None
    xs = [p[0] for p in points]
    ys = [p[1] for p in points]
    return min(xs), min(ys), max(xs), max(ys)


def collect_boxes(image_path: Path) -> list[OcrBox]:
    result = get_model().predict(str(image_path))
    collected: list[OcrBox] = []

    for item in _normalize_paddle_collection(result):
        payload = _extract_payload_from_paddle_item(item)
        texts = _normalize_paddle_collection(payload.get('rec_texts') or payload.get('texts'))
        boxes = _normalize_paddle_collection(payload.get('rec_boxes') or payload.get('dt_polys') or payload.get('rec_polys'))

        for text, raw_box in zip(texts, boxes):
            text_value = str(text).strip()
            if not text_value:
                continue
            parsed = flatten_points(raw_box)
            if parsed is None:
                continue
            x1, y1, x2, y2 = parsed
            collected.append(OcrBox(text=text_value, x1=x1, y1=y1, x2=x2, y2=y2))

    return collected


def cluster_lines(boxes: list[OcrBox]) -> list[list[OcrBox]]:
    ordered = sorted(boxes, key=lambda box: (box.center_y, box.x1))
    lines: list[list[OcrBox]] = []

    threshold = 18.0

    for box in ordered:
        if not lines:
            lines.append([box])
            continue

        current = lines[-1]
        avg_y = sum(item.center_y for item in current) / len(current)

        if math.fabs(box.center_y - avg_y) <= threshold:
            current.append(box)
        else:
            lines.append([box])

    return lines


def is_price(text: str) -> bool:
    return bool(PRICE_PATTERN.search(text or ''))


def detect_price_anchors(lines: list[list[OcrBox]]) -> list[OcrBox]:
    anchors: list[OcrBox] = []
    for line in lines:
        for box in line:
            if is_price(box.text):
                anchors.append(box)
    return anchors


def candidate_pairs(lines: list[list[OcrBox]]) -> list[dict[str, str]]:
    pairs: list[dict[str, str]] = []

    for line in lines:
        prices = [box for box in line if is_price(box.text)]
        articles = [box for box in line if not is_price(box.text)]

        if not prices or not articles:
            continue

        article_text = ' '.join(item.text for item in sorted(articles, key=lambda item: item.x1))

        for price in prices:
            pairs.append({
                'article': article_text,
                'price': price.text,
            })

    return pairs


def detect_total(lines: list[list[OcrBox]]) -> str:
    for line in lines:
        text = ' '.join(box.text for box in sorted(line, key=lambda item: item.x1))
        if TOTAL_PATTERN.search(text):
            match = PRICE_PATTERN.search(text)
            if match:
                return match.group(0)
    return ''


def detect_store(boxes: list[OcrBox]) -> str:
    combined = ' '.join(box.text for box in boxes)
    if 'albert' in combined.lower() or 'heijn' in combined.lower():
        return 'Albert Heijn'
    return ''


def detect_purchase_at(boxes: list[OcrBox]) -> str:
    combined = ' '.join(box.text for box in boxes)
    match = re.search(r'(\d{2})[-/](\d{2})[-/](\d{4})', combined)
    if not match:
        return ''
    day, month, year = match.groups()
    return f'{year}-{month}-{day}T00:00:00'


def main() -> int:
    parser = argparse.ArgumentParser(description='R7c-12 AH foto 3 topology reconstruction diagnostics')
    parser.add_argument('--fixtures-zip', required=True)
    parser.add_argument('--json-out', required=True)
    parser.add_argument('--csv-out', required=True)
    args = parser.parse_args()

    with tempfile.TemporaryDirectory(prefix='r7c12-ah3-') as td:
        image_path = find_fixture(Path(args.fixtures_zip), Path(td))
        boxes = collect_boxes(image_path)
        lines = cluster_lines(boxes)
        anchors = detect_price_anchors(lines)
        pairs = candidate_pairs(lines)

        result = {
            'fixture_file': 'AH foto 3.jpg',
            'ocr_box_count': len(boxes),
            'raw_ocr_line_count': len(boxes),
            'topology_line_count': len(lines),
            'price_anchor_count': len(anchors),
            'candidate_article_price_pairs': len(pairs),
            'reconstructed_article_line_count': len(pairs),
            'detected_total_amount': detect_total(lines),
            'store_name': detect_store(boxes),
            'purchase_at': detect_purchase_at(boxes),
            'diagnostic_only': True,
            'sample_pairs': pairs[:10],
        }

    json_out = Path(args.json_out)
    json_out.parent.mkdir(parents=True, exist_ok=True)
    json_out.write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding='utf-8')

    csv_out = Path(args.csv_out)
    csv_out.parent.mkdir(parents=True, exist_ok=True)
    with csv_out.open('w', encoding='utf-8', newline='') as handle:
        writer = csv.DictWriter(handle, fieldnames=[
            'fixture_file',
            'ocr_box_count',
            'raw_ocr_line_count',
            'topology_line_count',
            'price_anchor_count',
            'candidate_article_price_pairs',
            'reconstructed_article_line_count',
            'detected_total_amount',
            'store_name',
            'purchase_at',
            'diagnostic_only',
        ])
        writer.writeheader()
        writer.writerow({k: v for k, v in result.items() if k != 'sample_pairs'})

    print('R7c-12 AH foto 3 topology reconstruction diagnostics')
    print(f"ocr_box_count: {result['ocr_box_count']}")
    print(f"topology_line_count: {result['topology_line_count']}")
    print(f"candidate_article_price_pairs: {result['candidate_article_price_pairs']}")
    print(f"detected_total_amount: {result['detected_total_amount']}")
    print(f"json_written: {json_out}")
    print(f"csv_written: {csv_out}")
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
