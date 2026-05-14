from __future__ import annotations

import argparse
import json
import math
from pathlib import Path
from typing import Any

import cv2
import numpy as np

from add_amount_region_zone_diagnostics import _image_by_stem, _should_run_for_image, build_amount_region_zone_diagnostics
from add_ocr_region_diagnostics import extract_ocr_regions
from add_ocr_structural_normalization import build_ocr_structural_normalization
from add_shadow_reconstruction_output import build_shadow_reconstruction_output

DEFAULT_TARGETS = {
    'AH foto 2',
    'AH foto 3',
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


def _box_dict(x: int, y: int, w: int, h: int) -> dict[str, int]:
    return {'left': x, 'top': y, 'width': w, 'height': h, 'right': x + w, 'bottom': y + h, 'center_x': x + w // 2, 'center_y': y + h // 2}


def _detect_document_box(image: np.ndarray) -> tuple[dict[str, int], float]:
    h, w = image.shape[:2]
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    blur = cv2.GaussianBlur(gray, (5, 5), 0)
    edges = cv2.Canny(blur, 45, 150)
    contours, _ = cv2.findContours(edges, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    if not contours:
        return _box_dict(0, 0, w, h), 0.25
    contours = sorted(contours, key=cv2.contourArea, reverse=True)[:12]
    image_area = max(1, h * w)
    best = None
    best_score = 0.0
    for contour in contours:
        x, y, cw, ch = cv2.boundingRect(contour)
        area_ratio = (cw * ch) / image_area
        aspect = ch / max(1, cw)
        if area_ratio < 0.08:
            continue
        aspect_score = 1.0 if 1.2 <= aspect <= 8.0 else 0.45
        score = min(1.0, area_ratio * 1.55) * 0.75 + aspect_score * 0.25
        if score > best_score:
            best_score = score
            best = _box_dict(x, y, cw, ch)
    if best is None:
        return _box_dict(0, 0, w, h), 0.30
    pad = 18
    x0 = max(0, best['left'] - pad)
    y0 = max(0, best['top'] - pad)
    x1 = min(w, best['right'] + pad)
    y1 = min(h, best['bottom'] + pad)
    return _box_dict(x0, y0, x1 - x0, y1 - y0), round(float(best_score), 3)


def _crop(image: np.ndarray, box: dict[str, int]) -> np.ndarray:
    return image[box['top']:box['bottom'], box['left']:box['right']].copy()


def _local_contrast_score(gray: np.ndarray) -> float:
    return round(float(np.std(gray) / 128.0), 3)


def _sharpness_score(gray: np.ndarray) -> float:
    var = cv2.Laplacian(gray, cv2.CV_64F).var()
    return round(float(min(1.0, var / 650.0)), 3)


def _background_noise_score(gray: np.ndarray) -> float:
    blur = cv2.GaussianBlur(gray, (17, 17), 0)
    noise = np.mean(np.abs(gray.astype('float32') - blur.astype('float32')))
    return round(float(min(1.0, noise / 55.0)), 3)


def _backside_bleedthrough_score(gray: np.ndarray) -> float:
    mid = np.logical_and(gray > 120, gray < 215).mean()
    edges = cv2.Canny(gray, 35, 120).mean() / 255.0
    return round(float(min(1.0, mid * 1.25 + edges * 0.35)), 3)


def _estimate_text_scale(regions: list[dict[str, Any]]) -> float:
    heights = [int(region.get('height') or 0) for region in regions if int(region.get('height') or 0) > 4]
    if not heights:
        return 0.0
    median = float(np.median(heights))
    return round(median / 18.0, 3)


def _clahe(image: np.ndarray) -> np.ndarray:
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    clahe = cv2.createCLAHE(clipLimit=2.4, tileGridSize=(8, 8))
    return clahe.apply(gray)


def _adaptive_threshold(gray: np.ndarray) -> np.ndarray:
    return cv2.adaptiveThreshold(gray, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY, 31, 11)


def _sharpen(gray: np.ndarray) -> np.ndarray:
    kernel = np.array([[0, -1, 0], [-1, 5, -1], [0, -1, 0]])
    return cv2.filter2D(gray, -1, kernel)


def _deskew(gray: np.ndarray) -> tuple[np.ndarray, float]:
    edges = cv2.Canny(gray, 50, 150)
    lines = cv2.HoughLinesP(edges, 1, np.pi / 180, threshold=70, minLineLength=max(40, gray.shape[1] // 6), maxLineGap=12)
    angles = []
    if lines is not None:
        for line in lines[:, 0]:
            x1, y1, x2, y2 = line
            angle = math.degrees(math.atan2(y2 - y1, x2 - x1))
            if -18 <= angle <= 18:
                angles.append(angle)
    angle = float(np.median(angles)) if angles else 0.0
    if abs(angle) < 0.5:
        return gray, round(angle, 2)
    h, w = gray.shape[:2]
    matrix = cv2.getRotationMatrix2D((w // 2, h // 2), angle, 1.0)
    rotated = cv2.warpAffine(gray, matrix, (w, h), flags=cv2.INTER_CUBIC, borderMode=cv2.BORDER_REPLICATE)
    return rotated, round(angle, 2)


def _scale_to_text(gray: np.ndarray) -> np.ndarray:
    h, w = gray.shape[:2]
    factor = 1.75 if min(h, w) < 1300 else 1.25
    return cv2.resize(gray, (int(w * factor), int(h * factor)), interpolation=cv2.INTER_CUBIC)


def _write_variant(output_dir: Path, image_path: Path, variant: str, image: np.ndarray) -> Path:
    out = output_dir / 'debug_images' / 'document_isolation_enhancement' / f'{image_path.stem}_{variant}.png'
    out.parent.mkdir(parents=True, exist_ok=True)
    cv2.imwrite(str(out), image)
    return out


def _evaluate_variant(image_path: Path, receipt_json: dict[str, Any], output_dir: Path, variant: str, image: np.ndarray, box: dict[str, int], confidence: float) -> dict[str, Any]:
    variant_path = _write_variant(output_dir, image_path, variant, image)
    gray = image if len(image.shape) == 2 else cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    regions = extract_ocr_regions(variant_path, 'nld+eng')
    zone_diag = build_amount_region_zone_diagnostics(variant_path, receipt_json, 'nld+eng', output_dir / 'debug_images' / 'document_isolation_zone')
    temp_payload = json.loads(json.dumps(receipt_json, ensure_ascii=False))
    temp_payload.setdefault('metadata', {})['amount_region_zone_diagnostics'] = zone_diag
    structural = build_ocr_structural_normalization(temp_payload)
    temp_payload.setdefault('metadata', {})['ocr_structural_normalization'] = structural
    shadow = build_shadow_reconstruction_output(temp_payload)
    best_zone = zone_diag.get('best_article_zone_variant', {})
    return {
        'variant': variant,
        'isolated_document_confidence': confidence,
        'isolated_document_box': box,
        'background_noise_score': _background_noise_score(gray),
        'backside_bleedthrough_score': _backside_bleedthrough_score(gray),
        'local_contrast_score': _local_contrast_score(gray),
        'text_sharpness_score': _sharpness_score(gray),
        'normalized_text_scale': _estimate_text_scale(regions),
        'ocr_region_count_after_isolation': len(regions),
        'article_zone_amount_count_after_isolation': int(best_zone.get('article_zone_amount_count', 0) or 0),
        'normalized_group_count_after_isolation': int(structural.get('normalized_group_count', 0) or 0),
        'shadow_candidate_count_after_isolation': int(shadow.get('generated_row_count', 0) or 0),
        'debug_image_written': str(variant_path).replace('\\', '/'),
        'diagnostic_only': True,
        'reconstruction_applied': False,
    }


def build_document_isolation_enhancement_diagnostics(image_path: Path, receipt_json: dict[str, Any], output_dir: Path) -> dict[str, Any]:
    image = cv2.imread(str(image_path))
    if image is None:
        raise FileNotFoundError(f'Cannot read image: {image_path}')
    h, w = image.shape[:2]
    box, confidence = _detect_document_box(image)
    isolated = _crop(image, box)
    isolated_gray = cv2.cvtColor(isolated, cv2.COLOR_BGR2GRAY)
    contrast = _clahe(isolated)
    threshold = _adaptive_threshold(contrast)
    sharpened = _sharpen(contrast)
    deskewed, skew_angle = _deskew(contrast)
    scaled = _scale_to_text(contrast)
    threshold_scaled = _scale_to_text(threshold)

    variants = [
        _evaluate_variant(image_path, receipt_json, output_dir, 'isolated_document', isolated_gray, box, confidence),
        _evaluate_variant(image_path, receipt_json, output_dir, 'isolated_local_contrast', contrast, box, confidence),
        _evaluate_variant(image_path, receipt_json, output_dir, 'isolated_adaptive_threshold', threshold, box, confidence),
        _evaluate_variant(image_path, receipt_json, output_dir, 'isolated_sharpened', sharpened, box, confidence),
        _evaluate_variant(image_path, receipt_json, output_dir, 'isolated_deskewed', deskewed, box, confidence),
        _evaluate_variant(image_path, receipt_json, output_dir, 'isolated_scaled_contrast', scaled, box, confidence),
        _evaluate_variant(image_path, receipt_json, output_dir, 'isolated_contrast_threshold_scaled', threshold_scaled, box, confidence),
    ]
    best = max(
        variants,
        key=lambda item: (
            int(item.get('shadow_candidate_count_after_isolation', 0)),
            int(item.get('normalized_group_count_after_isolation', 0)),
            int(item.get('article_zone_amount_count_after_isolation', 0)),
            int(item.get('ocr_region_count_after_isolation', 0)),
        ),
        default={},
    )
    return {
        'diagnostic_scope': 'document_isolation_and_local_enhancement_before_ocr',
        'diagnostic_only': True,
        'reconstruction_applied': False,
        'image_file': image_path.name,
        'original_image_size': {'width': w, 'height': h},
        'estimated_skew_angle': skew_angle,
        'best_variant': {
            'variant': best.get('variant', ''),
            'isolated_document_confidence': best.get('isolated_document_confidence', 0),
            'ocr_region_count_after_isolation': best.get('ocr_region_count_after_isolation', 0),
            'article_zone_amount_count_after_isolation': best.get('article_zone_amount_count_after_isolation', 0),
            'normalized_group_count_after_isolation': best.get('normalized_group_count_after_isolation', 0),
            'shadow_candidate_count_after_isolation': best.get('shadow_candidate_count_after_isolation', 0),
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
    summary.setdefault('document_isolation_enhancement_diagnostics', {})
    processed = 0
    skipped = 0
    for target in sorted(targets):
        json_path = json_dir / f'{target}.json'
        image_path = image_lookup.get(target)
        if image_path is None or not json_path.exists() or not _should_run_for_image(image_path):
            skipped += 1
            continue
        payload = json.loads(json_path.read_text(encoding='utf-8'))
        diagnostics = build_document_isolation_enhancement_diagnostics(image_path, payload, output_dir)
        payload.setdefault('metadata', {})['document_isolation_enhancement_diagnostics'] = diagnostics
        json_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding='utf-8')
        summary['document_isolation_enhancement_diagnostics'][payload.get('metadata', {}).get('source_file', image_path.name)] = diagnostics
        processed += 1
    summary['schema_version'] = 'receipt-ocr-benchmark-v31-document-isolation-enhancement-diagnostics'
    summary['document_isolation_enhancement_diagnostics_processed_receipts'] = processed
    summary['document_isolation_enhancement_diagnostics_skipped_receipts'] = skipped
    summary['document_isolation_enhancement_diagnostics_targeted_only'] = True
    summary_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding='utf-8')
    print(f'[OK] Document isolation/enhancement diagnostics added for {processed} receipts; skipped={skipped}')


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
