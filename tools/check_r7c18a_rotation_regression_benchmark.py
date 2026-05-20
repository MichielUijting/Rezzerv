from __future__ import annotations

import argparse
import csv
import json
import math
import re
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

import cv2  # type: ignore
import numpy as np  # type: ignore
from paddleocr import PaddleOCR  # type: ignore

from app.services.receipt_service import (  # noqa: E402
    _extract_payload_from_paddle_item,
    _normalize_paddle_collection,
)

IMAGE_EXTENSIONS = {'.jpg', '.jpeg', '.png', '.bmp', '.webp'}
PRICE_PATTERN = re.compile(r'\b\d+[\.,]\d{2}\b')
DATE_PATTERN = re.compile(r'\b\d{2}[-/]\d{2}[-/]\d{4}\b')
TOTAL_PATTERN = re.compile(r'\b(totaal|total|te betalen|subtotaal)\b', re.I)
FOOTER_PATTERN = re.compile(
    r'\b(totaal|total|te betalen|terminal|nfc|chip|kaart|pin|datum|periode|bonus|btw|v\s?pay|betaling|autorisatie|transactie)\b',
    re.I,
)
ARTICLE_PATTERN = re.compile(
    r'\b(choco|sand|brood|water|melk|kaas|ham|cola|yogh|appel|kip|koffie|thee|bier|sap|rijst|pasta|tomaat|komkommer|banaan|sinas|salade|koek|chips)\b',
    re.I,
)
STORE_PATTERNS = {
    'Albert Heijn': re.compile(r'\b(albert|heijn|ah\b)', re.I),
    'Jumbo': re.compile(r'\bjumbo\b', re.I),
    'Lidl': re.compile(r'\blidl\b', re.I),
    'Aldi': re.compile(r'\baldi\b', re.I),
}

MODEL: PaddleOCR | None = None


def get_model() -> PaddleOCR:
    global MODEL
    if MODEL is None:
        MODEL = PaddleOCR(
            use_doc_orientation_classify=False,
            use_doc_unwarping=False,
            use_textline_orientation=False,
            lang='en',
        )
    return MODEL


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


def collect_lines(image_path: Path) -> list[str]:
    result = get_model().predict(str(image_path))
    lines: list[str] = []
    for item in _normalize_paddle_collection(result):
        payload = _extract_payload_from_paddle_item(item)
        texts = _normalize_paddle_collection(payload.get('rec_texts') or payload.get('texts'))
        for text in texts:
            value = str(text).strip()
            if value:
                lines.append(value)
    return lines


def rotate_only(image: np.ndarray) -> tuple[np.ndarray, float]:
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    edges = cv2.Canny(gray, 50, 150)
    lines = cv2.HoughLines(edges, 1, np.pi / 180, 200)
    angle = 0.0
    if lines is not None:
        candidate_angles: list[float] = []
        for line in lines[:20]:
            _rho, theta = line[0]
            raw_angle = math.degrees(theta) - 90
            if abs(raw_angle) <= 75:
                candidate_angles.append(raw_angle)
        if candidate_angles:
            candidate_angles.sort()
            angle = candidate_angles[len(candidate_angles) // 2]
    height, width = image.shape[:2]
    matrix = cv2.getRotationMatrix2D((width / 2, height / 2), angle, 1.0)
    rotated = cv2.warpAffine(image, matrix, (width, height), borderMode=cv2.BORDER_REPLICATE)
    return rotated, round(angle, 2)


def detect_store(lines: list[str]) -> str:
    text = ' '.join(lines)
    for store, pattern in STORE_PATTERNS.items():
        if pattern.search(text):
            return store
    return ''


def detect_dates(lines: list[str]) -> list[str]:
    return DATE_PATTERN.findall(' '.join(lines))[:5]


def detect_total_candidates(lines: list[str]) -> list[str]:
    candidates: list[str] = []
    for line in lines:
        if TOTAL_PATTERN.search(line):
            prices = PRICE_PATTERN.findall(line)
            candidates.extend(prices)
    return candidates[:10]


def score_lines(lines: list[str]) -> dict[str, Any]:
    joined = ' '.join(lines)
    prices = PRICE_PATTERN.findall(joined)
    footer_lines = [line for line in lines if FOOTER_PATTERN.search(line)]
    article_lines = [line for line in lines if ARTICLE_PATTERN.search(line)]
    article_density = round(len(article_lines) / max(1, len(lines)), 4)
    payment_dominance = round(len(footer_lines) / max(1, len(lines)), 4)

    parseability_score = (
        len(article_lines) * 3
        + len(prices)
        + (2 if detect_store(lines) else 0)
        + (2 if detect_total_candidates(lines) else 0)
        - len(footer_lines)
    )

    return {
        'ocr_line_count': len(lines),
        'price_anchor_count': len(prices),
        'article_like_line_count': len(article_lines),
        'footer_payment_line_count': len(footer_lines),
        'article_density': article_density,
        'payment_dominance': payment_dominance,
        'parseability_score': parseability_score,
        'store_name': detect_store(lines),
        'date_candidates': detect_dates(lines),
        'total_candidates': detect_total_candidates(lines),
        'sample_article_lines': article_lines[:5],
        'sample_footer_lines': footer_lines[:5],
        'sample_lines': lines[:12],
    }


def classify_delta(original: dict[str, Any], rotated: dict[str, Any]) -> tuple[str, bool, dict[str, Any]]:
    deltas = {
        'ocr_line_count_delta': rotated['ocr_line_count'] - original['ocr_line_count'],
        'price_anchor_delta': rotated['price_anchor_count'] - original['price_anchor_count'],
        'article_like_line_delta': rotated['article_like_line_count'] - original['article_like_line_count'],
        'footer_payment_line_delta': rotated['footer_payment_line_count'] - original['footer_payment_line_count'],
        'parseability_score_delta': rotated['parseability_score'] - original['parseability_score'],
        'store_stable': original['store_name'] == rotated['store_name'],
        'total_stable': bool(set(original['total_candidates']) & set(rotated['total_candidates'])) if original['total_candidates'] and rotated['total_candidates'] else original['total_candidates'] == rotated['total_candidates'],
    }

    regression = False
    if original['ocr_line_count'] >= 5 and rotated['ocr_line_count'] < max(3, int(original['ocr_line_count'] * 0.5)):
        regression = True
    if original['store_name'] and original['store_name'] != rotated['store_name']:
        regression = True
    if original['total_candidates'] and not deltas['total_stable']:
        regression = True
    if deltas['article_like_line_delta'] < -1 and deltas['parseability_score_delta'] < 0:
        regression = True

    if regression:
        winner = 'original'
    elif deltas['parseability_score_delta'] > 0 or deltas['article_like_line_delta'] > 0:
        winner = 'rotate_only'
    elif deltas['parseability_score_delta'] < 0:
        winner = 'original'
    else:
        winner = 'tie'

    return winner, regression, deltas


def write_image(path: Path, image: np.ndarray) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    cv2.imwrite(str(path), image)


def benchmark_fixture(image_path: Path, out_dir: Path) -> dict[str, Any]:
    original_image = cv2.imread(str(image_path))
    if original_image is None:
        return {
            'fixture': image_path.name,
            'error': 'unable_to_read_image',
            'regression_detected': True,
        }

    rotated_image, angle = rotate_only(original_image)
    safe_name = re.sub(r'[^a-zA-Z0-9_.-]+', '_', image_path.stem)
    fixture_dir = out_dir / safe_name
    write_image(fixture_dir / 'original.png', original_image)
    write_image(fixture_dir / 'rotate_only.png', rotated_image)

    original_lines = collect_lines(fixture_dir / 'original.png')
    rotated_lines = collect_lines(fixture_dir / 'rotate_only.png')

    original_metrics = score_lines(original_lines)
    rotated_metrics = score_lines(rotated_lines)
    winner, regression, deltas = classify_delta(original_metrics, rotated_metrics)

    return {
        'fixture': image_path.name,
        'diagnostic_only': True,
        'rotation_angle_deg': angle,
        'winner': winner,
        'regression_detected': regression,
        'original': original_metrics,
        'rotate_only': rotated_metrics,
        'delta': deltas,
        'outputs': {
            'original': str(fixture_dir / 'original.png'),
            'rotate_only': str(fixture_dir / 'rotate_only.png'),
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser(description='R7c-18a rotation-only regression benchmark')
    parser.add_argument('--fixtures-zip', required=True)
    parser.add_argument('--json-out', required=True)
    parser.add_argument('--csv-out', required=True)
    parser.add_argument('--out-dir', required=True)
    args = parser.parse_args()

    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    with tempfile.TemporaryDirectory(prefix='r7c18a-') as td:
        fixtures = extract_fixtures(Path(args.fixtures_zip), Path(td))
        results = [benchmark_fixture(path, out_dir) for path in fixtures]

    summary = {
        'fixture_count': len(results),
        'rotate_only_wins': sum(1 for row in results if row.get('winner') == 'rotate_only'),
        'original_wins': sum(1 for row in results if row.get('winner') == 'original'),
        'ties': sum(1 for row in results if row.get('winner') == 'tie'),
        'regression_count': sum(1 for row in results if row.get('regression_detected')),
    }

    payload = {
        'diagnostic_only': True,
        'benchmark': 'R7c-18a rotation-only regression benchmark',
        'summary': summary,
        'results': results,
    }

    json_out = Path(args.json_out)
    json_out.parent.mkdir(parents=True, exist_ok=True)
    json_out.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding='utf-8')

    csv_out = Path(args.csv_out)
    csv_out.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = [
        'fixture',
        'rotation_angle_deg',
        'winner',
        'regression_detected',
        'original_ocr_line_count',
        'rotated_ocr_line_count',
        'original_price_anchor_count',
        'rotated_price_anchor_count',
        'original_article_like_line_count',
        'rotated_article_like_line_count',
        'original_footer_payment_line_count',
        'rotated_footer_payment_line_count',
        'parseability_score_delta',
        'store_stable',
        'total_stable',
    ]
    with csv_out.open('w', encoding='utf-8', newline='') as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for row in results:
            original = row.get('original') or {}
            rotated = row.get('rotate_only') or {}
            delta = row.get('delta') or {}
            writer.writerow({
                'fixture': row.get('fixture'),
                'rotation_angle_deg': row.get('rotation_angle_deg'),
                'winner': row.get('winner'),
                'regression_detected': row.get('regression_detected'),
                'original_ocr_line_count': original.get('ocr_line_count'),
                'rotated_ocr_line_count': rotated.get('ocr_line_count'),
                'original_price_anchor_count': original.get('price_anchor_count'),
                'rotated_price_anchor_count': rotated.get('price_anchor_count'),
                'original_article_like_line_count': original.get('article_like_line_count'),
                'rotated_article_like_line_count': rotated.get('article_like_line_count'),
                'original_footer_payment_line_count': original.get('footer_payment_line_count'),
                'rotated_footer_payment_line_count': rotated.get('footer_payment_line_count'),
                'parseability_score_delta': delta.get('parseability_score_delta'),
                'store_stable': delta.get('store_stable'),
                'total_stable': delta.get('total_stable'),
            })

    print('R7c-18a rotation-only regression benchmark')
    print(f"fixture_count: {summary['fixture_count']}")
    print(f"rotate_only_wins: {summary['rotate_only_wins']}")
    print(f"original_wins: {summary['original_wins']}")
    print(f"ties: {summary['ties']}")
    print(f"regression_count: {summary['regression_count']}")
    print(f"json_written: {json_out}")
    print(f"csv_written: {csv_out}")
    print(f"overlays_written: {out_dir}")
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
