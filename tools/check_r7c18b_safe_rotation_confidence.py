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
    r'\b(choco|sand|brood|water|melk|kaas|ham|cola|yogh|appel|kip|koffie|thee|bier|sap|rijst|pasta|tomaat|komkommer|banaan|sinas|salade|koek|chips|gehakt|soep|stroopwafel)\b',
    re.I,
)
STORE_PATTERNS = {
    'Albert Heijn': re.compile(r'\b(albert|heijn|ah\b)', re.I),
    'Jumbo': re.compile(r'\bjumbo\b', re.I),
    'Lidl': re.compile(r'\blidl\b', re.I),
    'Aldi': re.compile(r'\baldi\b', re.I),
    'PLUS': re.compile(r'\bplus\b', re.I),
}

MODEL: PaddleOCR | None = None
SAFE_ABS_ANGLE_LIMIT = 45.0
MIN_CONFIDENCE = 0.55
MIN_AFTER_SCORE_DELTA = -2
MIN_AFTER_LINE_RATIO = 0.70


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
            candidates.extend(PRICE_PATTERN.findall(line))
    return candidates[:10]


def score_lines(lines: list[str]) -> dict[str, Any]:
    joined = ' '.join(lines)
    prices = PRICE_PATTERN.findall(joined)
    footer_lines = [line for line in lines if FOOTER_PATTERN.search(line)]
    article_lines = [line for line in lines if ARTICLE_PATTERN.search(line)]
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
        'payment_dominance': round(len(footer_lines) / max(1, len(lines)), 4),
        'article_density': round(len(article_lines) / max(1, len(lines)), 4),
        'parseability_score': parseability_score,
        'store_name': detect_store(lines),
        'date_candidates': detect_dates(lines),
        'total_candidates': detect_total_candidates(lines),
        'sample_lines': lines[:12],
        'sample_article_lines': article_lines[:5],
        'sample_footer_lines': footer_lines[:5],
    }


def normalize_angle(raw: float) -> float:
    while raw <= -90:
        raw += 180
    while raw > 90:
        raw -= 180
    return raw


def median(values: list[float]) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    return ordered[len(ordered) // 2]


def hough_angle_candidates(image: np.ndarray) -> list[float]:
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    edges = cv2.Canny(gray, 50, 150)
    lines = cv2.HoughLines(edges, 1, np.pi / 180, 200)
    if lines is None:
        return []
    candidates: list[float] = []
    for line in lines[:40]:
        _rho, theta = line[0]
        angle = normalize_angle(math.degrees(theta) - 90)
        # keep broad range for diagnostics, but confidence will reject implausible values
        if abs(angle) <= 85:
            candidates.append(round(angle, 2))
    return candidates


def min_area_rect_angle(image: np.ndarray) -> float | None:
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    blur = cv2.GaussianBlur(gray, (5, 5), 0)
    thresh = cv2.threshold(blur, 180, 255, cv2.THRESH_BINARY)[1]
    contours, _ = cv2.findContours(thresh, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    if not contours:
        return None
    contour = max(contours, key=cv2.contourArea)
    if cv2.contourArea(contour) < 1000:
        return None
    rect = cv2.minAreaRect(contour)
    angle = float(rect[-1])
    if angle < -45:
        angle += 90
    elif angle > 45:
        angle -= 90
    return round(normalize_angle(angle), 2)


def estimate_rotation(image: np.ndarray) -> dict[str, Any]:
    hough = hough_angle_candidates(image)
    hough_median = median(hough)
    rect_angle = min_area_rect_angle(image)

    candidate_angles = list(hough)
    if rect_angle is not None:
        candidate_angles.append(rect_angle)

    estimated = median(candidate_angles) if candidate_angles else 0.0
    close = [angle for angle in candidate_angles if abs(angle - estimated) <= 5]
    consensus = len(close) / max(1, len(candidate_angles))
    enough_lines = min(1.0, len(hough) / 10.0)
    plausibility = 1.0 if abs(estimated) <= SAFE_ABS_ANGLE_LIMIT else 0.0
    confidence = round((consensus * 0.55) + (enough_lines * 0.25) + (plausibility * 0.20), 4)

    return {
        'estimated_angle_deg': round(estimated, 2),
        'hough_angle_count': len(hough),
        'hough_angle_median': round(hough_median, 2),
        'min_area_rect_angle': rect_angle,
        'angle_consensus': round(consensus, 4),
        'angle_confidence': confidence,
        'candidate_angles': candidate_angles[:20],
    }


def rotate_image(image: np.ndarray, angle: float) -> np.ndarray:
    height, width = image.shape[:2]
    matrix = cv2.getRotationMatrix2D((width / 2, height / 2), angle, 1.0)
    return cv2.warpAffine(image, matrix, (width, height), borderMode=cv2.BORDER_REPLICATE)


def route_decision(angle_info: dict[str, Any], original: dict[str, Any], rotated: dict[str, Any]) -> dict[str, Any]:
    angle = float(angle_info['estimated_angle_deg'])
    confidence = float(angle_info['angle_confidence'])
    fallback_reasons: list[str] = []

    if abs(angle) > SAFE_ABS_ANGLE_LIMIT:
        fallback_reasons.append('angle_exceeds_safe_limit')
    if confidence < MIN_CONFIDENCE:
        fallback_reasons.append('low_angle_confidence')

    line_ratio = rotated['ocr_line_count'] / max(1, original['ocr_line_count'])
    score_delta = rotated['parseability_score'] - original['parseability_score']
    store_stable = original['store_name'] == rotated['store_name'] or not original['store_name']
    total_stable = (
        bool(set(original['total_candidates']) & set(rotated['total_candidates']))
        if original['total_candidates'] and rotated['total_candidates']
        else original['total_candidates'] == rotated['total_candidates']
    )

    if line_ratio < MIN_AFTER_LINE_RATIO:
        fallback_reasons.append('ocr_line_count_collapse_after_rotation')
    if score_delta < MIN_AFTER_SCORE_DELTA:
        fallback_reasons.append('parseability_score_drop_after_rotation')
    if not store_stable:
        fallback_reasons.append('store_detection_unstable_after_rotation')
    if original['total_candidates'] and not total_stable:
        fallback_reasons.append('total_detection_unstable_after_rotation')

    rotation_allowed = not fallback_reasons
    selected_route = 'rotate_only' if rotation_allowed else 'original'

    regression_prevented = (
        not rotation_allowed
        and (
            line_ratio < MIN_AFTER_LINE_RATIO
            or score_delta < MIN_AFTER_SCORE_DELTA
            or not store_stable
            or abs(angle) > SAFE_ABS_ANGLE_LIMIT
        )
    )

    return {
        'rotation_allowed': rotation_allowed,
        'selected_route': selected_route,
        'fallback_reason': fallback_reasons,
        'regression_prevented': regression_prevented,
        'ocr_line_ratio_after_rotation': round(line_ratio, 4),
        'parseability_score_delta': score_delta,
        'store_stable': store_stable,
        'total_stable': total_stable,
    }


def write_image(path: Path, image: np.ndarray) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    cv2.imwrite(str(path), image)


def benchmark_fixture(image_path: Path, out_dir: Path) -> dict[str, Any]:
    image = cv2.imread(str(image_path))
    if image is None:
        return {'fixture': image_path.name, 'error': 'unable_to_read_image'}

    angle_info = estimate_rotation(image)
    rotated = rotate_image(image, float(angle_info['estimated_angle_deg']))

    safe_name = re.sub(r'[^a-zA-Z0-9_.-]+', '_', image_path.stem)
    fixture_dir = out_dir / safe_name
    original_path = fixture_dir / 'original.png'
    rotated_path = fixture_dir / 'rotate_only_candidate.png'
    write_image(original_path, image)
    write_image(rotated_path, rotated)

    original_lines = collect_lines(original_path)
    rotated_lines = collect_lines(rotated_path)
    original_metrics = score_lines(original_lines)
    rotated_metrics = score_lines(rotated_lines)
    decision = route_decision(angle_info, original_metrics, rotated_metrics)

    return {
        'fixture': image_path.name,
        'diagnostic_only': True,
        **angle_info,
        **decision,
        'original': original_metrics,
        'rotate_only_candidate': rotated_metrics,
        'outputs': {
            'original': str(original_path),
            'rotate_only_candidate': str(rotated_path),
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser(description='R7c-18b safe rotation confidence diagnostics')
    parser.add_argument('--fixtures-zip', required=True)
    parser.add_argument('--json-out', required=True)
    parser.add_argument('--csv-out', required=True)
    parser.add_argument('--out-dir', required=True)
    args = parser.parse_args()

    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    with tempfile.TemporaryDirectory(prefix='r7c18b-') as td:
        fixtures = extract_fixtures(Path(args.fixtures_zip), Path(td))
        results = [benchmark_fixture(path, out_dir) for path in fixtures]

    summary = {
        'fixture_count': len(results),
        'rotation_allowed_count': sum(1 for row in results if row.get('rotation_allowed')),
        'fallback_to_original_count': sum(1 for row in results if row.get('selected_route') == 'original'),
        'regression_prevented_count': sum(1 for row in results if row.get('regression_prevented')),
        'ah_foto_3_allowed': any(row.get('fixture') == 'AH foto 3.jpg' and row.get('rotation_allowed') for row in results),
        'jumbo_foto_1_blocked': any(row.get('fixture') == 'Jumbo foto 1.jpeg' and not row.get('rotation_allowed') for row in results),
    }

    payload = {
        'diagnostic_only': True,
        'benchmark': 'R7c-18b safe rotation confidence diagnostics',
        'safe_rules': {
            'max_abs_angle_deg': SAFE_ABS_ANGLE_LIMIT,
            'min_confidence': MIN_CONFIDENCE,
            'min_after_line_ratio': MIN_AFTER_LINE_RATIO,
            'min_after_score_delta': MIN_AFTER_SCORE_DELTA,
        },
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
        'estimated_angle_deg',
        'angle_confidence',
        'angle_consensus',
        'hough_angle_count',
        'rotation_allowed',
        'selected_route',
        'regression_prevented',
        'fallback_reason',
        'parseability_score_delta',
        'ocr_line_ratio_after_rotation',
        'store_stable',
        'total_stable',
    ]
    with csv_out.open('w', encoding='utf-8', newline='') as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for row in results:
            writer.writerow({key: row.get(key) for key in fieldnames})

    print('R7c-18b safe rotation confidence diagnostics')
    print(f"fixture_count: {summary['fixture_count']}")
    print(f"rotation_allowed_count: {summary['rotation_allowed_count']}")
    print(f"fallback_to_original_count: {summary['fallback_to_original_count']}")
    print(f"regression_prevented_count: {summary['regression_prevented_count']}")
    print(f"ah_foto_3_allowed: {summary['ah_foto_3_allowed']}")
    print(f"jumbo_foto_1_blocked: {summary['jumbo_foto_1_blocked']}")
    print(f"json_written: {json_out}")
    print(f"csv_written: {csv_out}")
    print(f"overlays_written: {out_dir}")
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
