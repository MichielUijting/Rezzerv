from __future__ import annotations

import argparse
import json
import math
from pathlib import Path

import cv2
import numpy as np
from PIL import Image

from add_amount_region_zone_diagnostics import _image_by_stem, _should_run_for_image, build_amount_region_zone_diagnostics
from add_ocr_region_diagnostics import extract_ocr_regions
from add_ocr_product_cluster_diagnostics import build_ocr_product_clusters

DEFAULT_TARGETS = {
    'AH foto 2',
    'Aldi foto 2',
    'Plus foto 2',
    'plus foto 1',
}


def _read_key_values(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    if not path.exists():
        return values
    for line in path.read_text(encoding='utf-8').splitlines():
        if '=' in line:
            key, value = line.split('=', 1)
            values[key.strip()] = value.strip()
    return values


def _candidate_run_paths(raw_run_path: str) -> list[Path]:
    raw = Path(raw_run_path)
    candidates = [raw]
    prefix = Path('tools') / 'receipt_csv_poc'
    parts = raw.parts
    prefix_parts = prefix.parts
    if len(parts) > len(prefix_parts) and parts[:len(prefix_parts)] == prefix_parts:
        candidates.append(Path(*parts[len(prefix_parts):]))
    if raw.name:
        candidates.append(Path('test_runs') / raw.name)
    return candidates


def _is_valid_run_dir(path: Path) -> bool:
    return (path / 'json').exists() and (path / 'benchmark_summary.json').exists()


def _find_latest_valid_run(test_runs_dir: Path = Path('test_runs')) -> Path:
    valid_runs = [path for path in test_runs_dir.glob('run_*') if path.is_dir() and _is_valid_run_dir(path)]
    if not valid_runs:
        raise FileNotFoundError(f'No valid run directory found under {test_runs_dir}')
    return sorted(valid_runs, key=lambda path: path.name)[-1]


def _read_latest_run_path(latest_file: Path) -> Path:
    values = _read_key_values(latest_file)
    raw_run_path = values.get('run_path', '')
    if raw_run_path:
        for candidate in _candidate_run_paths(raw_run_path):
            if _is_valid_run_dir(candidate):
                return candidate
        print(f'[WARN] LATEST_PUSHED_RUN points to invalid or incomplete run: {raw_run_path}')
    fallback = _find_latest_valid_run()
    print(f'[INFO] Using latest valid local run instead: {fallback}')
    return fallback


def _order_points(points: np.ndarray) -> np.ndarray:
    rect = np.zeros((4, 2), dtype='float32')
    s = points.sum(axis=1)
    rect[0] = points[np.argmin(s)]
    rect[2] = points[np.argmax(s)]
    diff = np.diff(points, axis=1)
    rect[1] = points[np.argmin(diff)]
    rect[3] = points[np.argmax(diff)]
    return rect


def _four_point_transform(image: np.ndarray, points: np.ndarray) -> np.ndarray:
    rect = _order_points(points)
    tl, tr, br, bl = rect
    width_a = np.linalg.norm(br - bl)
    width_b = np.linalg.norm(tr - tl)
    max_width = max(1, int(max(width_a, width_b)))
    height_a = np.linalg.norm(tr - br)
    height_b = np.linalg.norm(tl - bl)
    max_height = max(1, int(max(height_a, height_b)))
    dst = np.array([[0, 0], [max_width - 1, 0], [max_width - 1, max_height - 1], [0, max_height - 1]], dtype='float32')
    matrix = cv2.getPerspectiveTransform(rect, dst)
    return cv2.warpPerspective(image, matrix, (max_width, max_height))


def _detect_document_contour(image: np.ndarray) -> tuple[np.ndarray | None, float]:
    ratio_area = image.shape[0] * image.shape[1]
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    gray = cv2.GaussianBlur(gray, (5, 5), 0)
    edged = cv2.Canny(gray, 50, 160)
    contours, _ = cv2.findContours(edged, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    contours = sorted(contours, key=cv2.contourArea, reverse=True)[:8]
    best_quad = None
    best_confidence = 0.0
    for contour in contours:
        perimeter = cv2.arcLength(contour, True)
        approx = cv2.approxPolyDP(contour, 0.025 * perimeter, True)
        area = cv2.contourArea(approx)
        area_ratio = area / ratio_area if ratio_area else 0
        if len(approx) == 4 and area_ratio > 0.10:
            confidence = min(1.0, area_ratio * 1.25)
            if confidence > best_confidence:
                best_confidence = confidence
                best_quad = approx.reshape(4, 2).astype('float32')
    return best_quad, round(best_confidence, 3)


def _estimate_skew_angle(image: np.ndarray) -> float:
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY) if len(image.shape) == 3 else image
    edges = cv2.Canny(gray, 50, 150)
    lines = cv2.HoughLinesP(edges, 1, np.pi / 180, threshold=80, minLineLength=max(40, image.shape[1] // 8), maxLineGap=12)
    if lines is None:
        return 0.0
    angles = []
    for line in lines[:, 0]:
        x1, y1, x2, y2 = line
        angle = math.degrees(math.atan2(y2 - y1, x2 - x1))
        if -25 <= angle <= 25:
            angles.append(angle)
    if not angles:
        return 0.0
    return round(float(np.median(angles)), 2)


def _rotate_image(image: np.ndarray, angle: float) -> np.ndarray:
    if abs(angle) < 0.5:
        return image.copy()
    h, w = image.shape[:2]
    center = (w // 2, h // 2)
    matrix = cv2.getRotationMatrix2D(center, angle, 1.0)
    return cv2.warpAffine(image, matrix, (w, h), flags=cv2.INTER_CUBIC, borderMode=cv2.BORDER_REPLICATE)


def _crop_content(image: np.ndarray) -> np.ndarray:
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY) if len(image.shape) == 3 else image
    _, thresh = cv2.threshold(gray, 245, 255, cv2.THRESH_BINARY_INV)
    coords = cv2.findNonZero(thresh)
    if coords is None:
        return image.copy()
    x, y, w, h = cv2.boundingRect(coords)
    pad = 16
    x0 = max(0, x - pad)
    y0 = max(0, y - pad)
    x1 = min(image.shape[1], x + w + pad)
    y1 = min(image.shape[0], y + h + pad)
    if (x1 - x0) < 50 or (y1 - y0) < 50:
        return image.copy()
    return image[y0:y1, x0:x1].copy()


def _write_image(path: Path, image: np.ndarray) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    cv2.imwrite(str(path), image)
    return path


def _evaluate_image_variant(image_path: Path, receipt_json: dict, output_dir: Path, variant_name: str, image: np.ndarray, metadata: dict) -> dict[str, object]:
    debug_path = output_dir / 'debug_images' / 'document_normalization' / f'{image_path.stem}_{variant_name}.png'
    _write_image(debug_path, image)
    regions = extract_ocr_regions(debug_path, 'nld+eng')
    zone_diag = build_amount_region_zone_diagnostics(debug_path, receipt_json, 'nld+eng', output_dir / 'debug_images' / 'document_normalization_zone')
    temp_payload = json.loads(json.dumps(receipt_json, ensure_ascii=False))
    temp_payload.setdefault('metadata', {})['amount_region_zone_diagnostics'] = zone_diag
    clusters = build_ocr_product_clusters(temp_payload)
    best_zone = zone_diag.get('best_article_zone_variant', {})
    return {
        'variant': variant_name,
        'detected_document_confidence': metadata.get('detected_document_confidence', 0.0),
        'corrected_image_size': {'width': int(image.shape[1]), 'height': int(image.shape[0])},
        'skew_angle': metadata.get('skew_angle', 0.0),
        'perspective_transform_applied': bool(metadata.get('perspective_transform_applied', False)),
        'crop_normalization_applied': bool(metadata.get('crop_normalization_applied', False)),
        'rotation_correction_applied': bool(metadata.get('rotation_correction_applied', False)),
        'ocr_region_count_after_correction': len(regions),
        'amount_region_count_after_correction': sum(1 for region in regions if region.get('amounts')),
        'article_zone_amount_count_after_correction': int(best_zone.get('article_zone_amount_count', 0) or 0),
        'cluster_alignment_candidate_count_after_correction': int(clusters.get('linked_amount_candidate_count', 0) or 0),
        'debug_image_written': str(debug_path).replace('\\', '/'),
        'diagnostic_only': True,
        'reconstruction_applied': False,
    }


def build_document_normalization_diagnostics(image_path: Path, receipt_json: dict, output_dir: Path) -> dict[str, object]:
    image = cv2.imread(str(image_path))
    if image is None:
        raise FileNotFoundError(f'Cannot read image: {image_path}')

    variants = []
    variants.append(_evaluate_image_variant(image_path, receipt_json, output_dir, 'original_reference', image, {
        'detected_document_confidence': 0.0,
        'skew_angle': _estimate_skew_angle(image),
        'perspective_transform_applied': False,
        'crop_normalization_applied': False,
        'rotation_correction_applied': False,
    }))

    quad, confidence = _detect_document_contour(image)
    if quad is not None:
        perspective = _four_point_transform(image, quad)
        variants.append(_evaluate_image_variant(image_path, receipt_json, output_dir, 'perspective_corrected', perspective, {
            'detected_document_confidence': confidence,
            'skew_angle': _estimate_skew_angle(perspective),
            'perspective_transform_applied': True,
            'crop_normalization_applied': False,
            'rotation_correction_applied': False,
        }))
    else:
        perspective = image.copy()

    crop = _crop_content(perspective)
    variants.append(_evaluate_image_variant(image_path, receipt_json, output_dir, 'crop_normalized', crop, {
        'detected_document_confidence': confidence,
        'skew_angle': _estimate_skew_angle(crop),
        'perspective_transform_applied': quad is not None,
        'crop_normalization_applied': True,
        'rotation_correction_applied': False,
    }))

    skew_angle = _estimate_skew_angle(crop)
    rotated = _rotate_image(crop, skew_angle)
    variants.append(_evaluate_image_variant(image_path, receipt_json, output_dir, 'rotation_corrected', rotated, {
        'detected_document_confidence': confidence,
        'skew_angle': skew_angle,
        'perspective_transform_applied': quad is not None,
        'crop_normalization_applied': True,
        'rotation_correction_applied': abs(skew_angle) >= 0.5,
    }))

    best = max(
        variants,
        key=lambda item: (
            int(item.get('cluster_alignment_candidate_count_after_correction', 0)),
            int(item.get('article_zone_amount_count_after_correction', 0)),
            int(item.get('amount_region_count_after_correction', 0)),
            int(item.get('ocr_region_count_after_correction', 0)),
        ),
        default={},
    )
    return {
        'diagnostic_scope': 'document_detection_perspective_crop_rotation_diagnostics',
        'diagnostic_only': True,
        'reconstruction_applied': False,
        'image_file': image_path.name,
        'best_variant': {
            'variant': best.get('variant', ''),
            'detected_document_confidence': best.get('detected_document_confidence', 0.0),
            'skew_angle': best.get('skew_angle', 0.0),
            'perspective_transform_applied': best.get('perspective_transform_applied', False),
            'ocr_region_count_after_correction': best.get('ocr_region_count_after_correction', 0),
            'article_zone_amount_count_after_correction': best.get('article_zone_amount_count_after_correction', 0),
            'cluster_alignment_candidate_count_after_correction': best.get('cluster_alignment_candidate_count_after_correction', 0),
        },
        'variants': variants,
    }


def update_targeted_run(input_dir: Path, output_dir: Path, targets: set[str]) -> None:
    json_dir = output_dir / 'json'
    if not json_dir.exists():
        raise FileNotFoundError(f'JSON output directory not found: {json_dir}')

    image_lookup = _image_by_stem(input_dir)
    summary_path = output_dir / 'benchmark_summary.json'
    summary = json.loads(summary_path.read_text(encoding='utf-8')) if summary_path.exists() else {}
    summary.setdefault('document_normalization_diagnostics', {})

    processed = 0
    skipped = 0
    for target in sorted(targets):
        json_path = json_dir / f'{target}.json'
        image_path = image_lookup.get(target)
        if image_path is None or not json_path.exists() or not _should_run_for_image(image_path):
            skipped += 1
            continue
        payload = json.loads(json_path.read_text(encoding='utf-8'))
        diagnostics = build_document_normalization_diagnostics(image_path, payload, output_dir)
        payload.setdefault('metadata', {})['document_normalization_diagnostics'] = diagnostics
        json_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding='utf-8')
        summary['document_normalization_diagnostics'][payload.get('metadata', {}).get('source_file', image_path.name)] = diagnostics
        processed += 1

    summary['schema_version'] = 'receipt-ocr-benchmark-v23-document-normalization-diagnostics'
    summary['document_normalization_diagnostics_processed_receipts'] = processed
    summary['document_normalization_diagnostics_skipped_receipts'] = skipped
    summary['document_normalization_diagnostics_targeted_only'] = True
    summary_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding='utf-8')
    print(f'[OK] Document normalization diagnostics added for {processed} receipts; skipped={skipped}')


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument('--input', default='input_receipts')
    parser.add_argument('--output', default='')
    parser.add_argument('--latest-file', default='LATEST_PUSHED_RUN.txt')
    parser.add_argument('--targets', nargs='*', default=sorted(DEFAULT_TARGETS))
    args = parser.parse_args()

    output_dir = Path(args.output) if args.output else _read_latest_run_path(Path(args.latest_file))
    update_targeted_run(Path(args.input), output_dir, set(args.targets))


if __name__ == '__main__':
    main()
