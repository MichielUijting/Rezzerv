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

PRICE_PATTERN = re.compile(r'\b\d+[\.,]\d{2}\b')
FOOTER_PATTERN = re.compile(
    r'\b(totaal|total|te betalen|terminal|nfc|chip|kaart|pin|datum|periode|bonus|btw|v\s?pay|betaling)\b',
    re.I,
)
ARTICLE_PATTERN = re.compile(
    r'\b(choco|sand|brood|water|melk|kaas|ham|cola|yogh|appel|kip|koffie|thee)\b',
    re.I,
)

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


def find_fixture(zip_path: Path, workdir: Path) -> Path:
    with zipfile.ZipFile(zip_path) as archive:
        for item in archive.infolist():
            if item.is_dir():
                continue
            name = Path(item.filename).name
            if re.search(r'ah\s*foto\s*3', name, re.I):
                out = workdir / name
                out.write_bytes(archive.read(item))
                return out
    raise SystemExit('AH foto 3 not found in fixtures zip')


def normalize_points(raw_box: Any) -> list[tuple[float, float]]:
    if hasattr(raw_box, 'tolist'):
        raw_box = raw_box.tolist()
    if not isinstance(raw_box, (list, tuple)):
        return []
    points: list[tuple[float, float]] = []
    for item in raw_box:
        if hasattr(item, 'tolist'):
            item = item.tolist()
        if isinstance(item, (list, tuple)) and len(item) >= 2:
            try:
                points.append((float(item[0]), float(item[1])))
            except Exception:
                continue
    return points


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


def score_lines(lines: list[str]) -> dict[str, Any]:
    joined = ' '.join(lines)
    price_anchor_count = len(PRICE_PATTERN.findall(joined))
    footer_lines = [line for line in lines if FOOTER_PATTERN.search(line)]
    article_lines = [line for line in lines if ARTICLE_PATTERN.search(line)]
    parseability = 'LOW'
    if len(article_lines) >= 3 and price_anchor_count >= 3:
        parseability = 'HIGH'
    elif len(article_lines) >= 1 and price_anchor_count >= 2:
        parseability = 'MEDIUM'

    total_candidates = [line for line in lines if re.search(r'\b5[\.,]40\b', line)]

    return {
        'ocr_line_count': len(lines),
        'price_anchor_count': price_anchor_count,
        'article_like_line_count': len(article_lines),
        'footer_payment_line_count': len(footer_lines),
        'parseability': parseability,
        'detected_total_candidates': total_candidates[:5],
        'sample_article_lines': article_lines[:5],
        'sample_footer_lines': footer_lines[:5],
    }


def rotate_only(image: np.ndarray) -> np.ndarray:
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    edges = cv2.Canny(gray, 50, 150)
    lines = cv2.HoughLines(edges, 1, np.pi / 180, 200)
    angle = 0.0
    if lines is not None:
        rho, theta = lines[0][0]
        angle = math.degrees(theta) - 90
    height, width = image.shape[:2]
    matrix = cv2.getRotationMatrix2D((width / 2, height / 2), angle, 1.0)
    return cv2.warpAffine(image, matrix, (width, height), borderMode=cv2.BORDER_REPLICATE)


def crop_receipt(image: np.ndarray) -> np.ndarray:
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    blur = cv2.GaussianBlur(gray, (5, 5), 0)
    thresh = cv2.threshold(blur, 180, 255, cv2.THRESH_BINARY)[1]
    contours, _ = cv2.findContours(thresh, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    if not contours:
        return image
    contour = max(contours, key=cv2.contourArea)
    x, y, w, h = cv2.boundingRect(contour)
    return image[y:y + h, x:x + w]


def perspective_correct(image: np.ndarray) -> np.ndarray:
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    blur = cv2.GaussianBlur(gray, (5, 5), 0)
    edges = cv2.Canny(blur, 50, 150)
    contours, _ = cv2.findContours(edges, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    if not contours:
        return image

    contours = sorted(contours, key=cv2.contourArea, reverse=True)
    for contour in contours:
        peri = cv2.arcLength(contour, True)
        approx = cv2.approxPolyDP(contour, 0.03 * peri, True)
        if len(approx) == 4:
            pts = approx.reshape(4, 2).astype('float32')
            rect = np.zeros((4, 2), dtype='float32')
            s = pts.sum(axis=1)
            rect[0] = pts[np.argmin(s)]
            rect[2] = pts[np.argmax(s)]
            diff = np.diff(pts, axis=1)
            rect[1] = pts[np.argmin(diff)]
            rect[3] = pts[np.argmax(diff)]

            (tl, tr, br, bl) = rect
            width_a = np.linalg.norm(br - bl)
            width_b = np.linalg.norm(tr - tl)
            height_a = np.linalg.norm(tr - br)
            height_b = np.linalg.norm(tl - bl)
            max_width = max(int(width_a), int(width_b), 1)
            max_height = max(int(height_a), int(height_b), 1)

            dst = np.array([
                [0, 0],
                [max_width - 1, 0],
                [max_width - 1, max_height - 1],
                [0, max_height - 1],
            ], dtype='float32')

            matrix = cv2.getPerspectiveTransform(rect, dst)
            return cv2.warpPerspective(image, matrix, (max_width, max_height))

    return image


def contrast_enhance(image: np.ndarray) -> np.ndarray:
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
    enhanced = clahe.apply(gray)
    return cv2.cvtColor(enhanced, cv2.COLOR_GRAY2BGR)


def save_image(path: Path, image: np.ndarray) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    cv2.imwrite(str(path), image)


def benchmark_route(name: str, image: np.ndarray, out_dir: Path) -> dict[str, Any]:
    route_path = out_dir / f'{name}.png'
    save_image(route_path, image)
    lines = collect_lines(route_path)
    metrics = score_lines(lines)
    metrics['route'] = name
    metrics['output_file'] = str(route_path)
    return metrics


def main() -> int:
    parser = argparse.ArgumentParser(description='R7c-17 geometry normalization benchmark')
    parser.add_argument('--fixtures-zip', required=True)
    parser.add_argument('--json-out', required=True)
    parser.add_argument('--csv-out', required=True)
    parser.add_argument('--out-dir', required=True)
    args = parser.parse_args()

    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    with tempfile.TemporaryDirectory(prefix='r7c17-') as td:
        fixture = find_fixture(Path(args.fixtures_zip), Path(td))
        original = cv2.imread(str(fixture))
        if original is None:
            raise SystemExit('Unable to load fixture image')

        routes: list[tuple[str, np.ndarray]] = []

        routes.append(('original', original))

        rotated = rotate_only(original)
        routes.append(('rotate_only', rotated))

        rotate_crop = crop_receipt(rotated)
        routes.append(('rotate_crop', rotate_crop))

        rotate_perspective = perspective_correct(rotate_crop)
        routes.append(('rotate_perspective', rotate_perspective))

        rotate_perspective_contrast = contrast_enhance(rotate_perspective)
        routes.append(('rotate_perspective_contrast', rotate_perspective_contrast))

        results: list[dict[str, Any]] = []
        for name, image in routes:
            results.append(benchmark_route(name, image, out_dir))

    best_route = sorted(
        results,
        key=lambda item: (
            item['article_like_line_count'],
            item['price_anchor_count'],
            -item['footer_payment_line_count'],
        ),
        reverse=True,
    )[0]

    payload = {
        'fixture_file': 'AH foto 3.jpg',
        'diagnostic_only': True,
        'routes': results,
        'best_route': best_route,
    }

    json_out = Path(args.json_out)
    json_out.parent.mkdir(parents=True, exist_ok=True)
    json_out.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding='utf-8')

    csv_out = Path(args.csv_out)
    csv_out.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = [
        'route',
        'ocr_line_count',
        'price_anchor_count',
        'article_like_line_count',
        'footer_payment_line_count',
        'parseability',
        'output_file',
    ]
    with csv_out.open('w', encoding='utf-8', newline='') as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for row in results:
            writer.writerow({key: row.get(key) for key in fieldnames})

    print('R7c-17 geometry normalization benchmark')
    print(f"best_route: {best_route['route']}")
    print(f"best_parseability: {best_route['parseability']}")
    print(f"article_like_line_count: {best_route['article_like_line_count']}")
    print(f"price_anchor_count: {best_route['price_anchor_count']}")
    print(f"json_written: {json_out}")
    print(f"csv_written: {csv_out}")
    print(f"images_written: {out_dir}")
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
