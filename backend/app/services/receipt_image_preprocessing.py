from __future__ import annotations

import io
import logging
from pathlib import Path

from PIL import Image, ImageOps

LOGGER = logging.getLogger(__name__)

try:
    import cv2
    import numpy as np
except Exception:
    cv2 = None
    np = None

DEBUG_DIR = Path('/app/data/receipts/debug')
DEBUG_OUTPUT_PATH = DEBUG_DIR / 'latest-ocr-preprocessed.png'
DEBUG_ORIGINAL_PATH = DEBUG_DIR / 'latest-ocr-00-original.png'
DEBUG_ROTATED_PATH = DEBUG_DIR / 'latest-ocr-01-rotated.png'
DEBUG_FINAL_PATH = DEBUG_DIR / 'latest-ocr-02-final.png'
MAX_OCR_SIDE = 2600


def _shape_text(rgb) -> str:
    if rgb is None:
        return 'None'
    height, width = rgb.shape[:2]
    channels = rgb.shape[2] if len(rgb.shape) > 2 else 1
    return f'{width}x{height}x{channels}'


def _image_stats(rgb) -> str:
    if rgb is None:
        return 'None'
    gray = cv2.cvtColor(rgb, cv2.COLOR_RGB2GRAY) if len(rgb.shape) == 3 else rgb
    return 'mean=%.2f std=%.2f min=%s max=%s' % (
        float(np.mean(gray)),
        float(np.std(gray)),
        int(np.min(gray)),
        int(np.max(gray)),
    )


def _encode_png(rgb) -> bytes:
    image = Image.fromarray(rgb)
    buffer = io.BytesIO()
    image.save(buffer, format='PNG')
    return buffer.getvalue()


def _write_debug_png(path: Path, rgb, reason: str) -> None:
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(_encode_png(rgb))
        LOGGER.warning('Receipt preprocessing DEBUG_WRITE path=%s reason=%s shape=%s stats=%s', path, reason, _shape_text(rgb), _image_stats(rgb))
    except Exception as exc:
        LOGGER.warning('Receipt preprocessing DEBUG_WRITE_FAILED path=%s reason=%s error=%s', path, reason, exc)


def _save_all_debug_images(original, rotated, final, reason: str) -> None:
    _write_debug_png(DEBUG_ORIGINAL_PATH, original, f'{reason}:original')
    _write_debug_png(DEBUG_ROTATED_PATH, rotated, f'{reason}:rotated')
    _write_debug_png(DEBUG_FINAL_PATH, final, f'{reason}:final')
    _write_debug_png(DEBUG_OUTPUT_PATH, final, f'{reason}:ocr-input-alias')


def _resize_max_side(rgb, max_side: int = MAX_OCR_SIDE):
    height, width = rgb.shape[:2]
    largest = max(height, width)
    if largest <= max_side:
        LOGGER.warning('Receipt preprocessing RESIZE skipped shape=%s max_side=%s', _shape_text(rgb), max_side)
        return rgb
    scale = max_side / float(largest)
    resized = cv2.resize(rgb, (int(width * scale), int(height * scale)), interpolation=cv2.INTER_AREA)
    LOGGER.warning('Receipt preprocessing RESIZE applied from_shape=%s to_shape=%s scale=%.4f max_side=%s', _shape_text(rgb), _shape_text(resized), scale, max_side)
    return resized


def _rotate_keep_bounds(rgb, angle: float):
    height, width = rgb.shape[:2]
    center = (width / 2.0, height / 2.0)
    matrix = cv2.getRotationMatrix2D(center, angle, 1.0)
    cos = abs(matrix[0, 0])
    sin = abs(matrix[0, 1])
    new_width = int((height * sin) + (width * cos))
    new_height = int((height * cos) + (width * sin))
    matrix[0, 2] += (new_width / 2.0) - center[0]
    matrix[1, 2] += (new_height / 2.0) - center[1]
    LOGGER.warning(
        'Receipt preprocessing ROTATE_EXEC input_shape=%s angle=%.2f output_size=%sx%s matrix=%s',
        _shape_text(rgb),
        angle,
        new_width,
        new_height,
        np.round(matrix, 3).tolist(),
    )
    rotated = cv2.warpAffine(rgb, matrix, (new_width, new_height), flags=cv2.INTER_LINEAR, borderValue=(255, 255, 255))
    LOGGER.warning('Receipt preprocessing ROTATE_RESULT output_shape=%s stats=%s', _shape_text(rotated), _image_stats(rotated))
    return rotated


def _normalize_line_angle(angle: float) -> float:
    original = angle
    while angle <= -90:
        angle += 180
    while angle > 90:
        angle -= 180
    if angle > 45:
        angle -= 90
    elif angle < -45:
        angle += 90
    normalized = float(angle)
    LOGGER.warning('Receipt preprocessing ANGLE_NORMALIZE raw=%.2f normalized=%.2f', original, normalized)
    return normalized


def _dominant_text_angle(rgb) -> float:
    gray = cv2.cvtColor(rgb, cv2.COLOR_RGB2GRAY)
    gray = cv2.GaussianBlur(gray, (5, 5), 0)
    edges = cv2.Canny(gray, 50, 150)
    nonzero_edges = int(np.count_nonzero(edges))
    min_line_length = max(80, max(rgb.shape[:2]) // 8)
    LOGGER.warning('Receipt preprocessing ANGLE_INPUT shape=%s stats=%s edge_pixels=%s minLineLength=%s', _shape_text(rgb), _image_stats(rgb), nonzero_edges, min_line_length)

    lines = cv2.HoughLinesP(edges, 1, np.pi / 180, threshold=80, minLineLength=min_line_length, maxLineGap=40)
    if lines is None:
        LOGGER.warning('Receipt preprocessing ANGLE_DECISION skipped reason=no_hough_lines')
        return 0.0

    accepted_angles = []
    rejected_count = 0
    raw_line_count = int(len(lines))
    LOGGER.warning('Receipt preprocessing ANGLE_LINES raw_line_count=%s', raw_line_count)

    for index, raw in enumerate(lines[:, 0, :]):
        x1, y1, x2, y2 = [int(v) for v in raw]
        length = float(np.hypot(x2 - x1, y2 - y1))
        raw_angle = float(np.degrees(np.arctan2(y2 - y1, x2 - x1)))
        normalized_angle = _normalize_line_angle(raw_angle)
        accepted = length >= 80 and abs(normalized_angle) <= 45
        if accepted:
            accepted_angles.append(normalized_angle)
        else:
            rejected_count += 1
        if index < 20:
            LOGGER.warning(
                'Receipt preprocessing ANGLE_LINE index=%s p1=(%s,%s) p2=(%s,%s) length=%.2f raw_angle=%.2f normalized=%.2f accepted=%s',
                index,
                x1,
                y1,
                x2,
                y2,
                length,
                raw_angle,
                normalized_angle,
                accepted,
            )

    if not accepted_angles:
        LOGGER.warning('Receipt preprocessing ANGLE_DECISION skipped reason=no_usable_line_angles raw_line_count=%s rejected=%s', raw_line_count, rejected_count)
        return 0.0

    median_angle = float(np.median(accepted_angles))
    mean_angle = float(np.mean(accepted_angles))
    LOGGER.warning(
        'Receipt preprocessing ANGLE_DECISION detected median=%.2f mean=%.2f accepted=%s rejected=%s all_accepted=%s',
        median_angle,
        mean_angle,
        len(accepted_angles),
        rejected_count,
        [round(a, 2) for a in accepted_angles[:30]],
    )
    return median_angle


def _correct_rotation(rgb):
    LOGGER.warning('Receipt preprocessing ROTATION_STAGE start input_shape=%s', _shape_text(rgb))
    angle = _dominant_text_angle(rgb)
    if abs(angle) < 2.0:
        LOGGER.warning('Receipt preprocessing ROTATION_STAGE not_applied detected_angle=%.2f threshold=2.0', angle)
        return rgb, angle, 0.0, False
    applied_angle = -angle
    LOGGER.warning('Receipt preprocessing ROTATION_STAGE applying detected_angle=%.2f applied_angle=%.2f', angle, applied_angle)
    rotated = _rotate_keep_bounds(rgb, applied_angle)
    return rotated, angle, applied_angle, True


def preprocess_receipt_image_for_ocr(file_bytes: bytes) -> bytes:
    LOGGER.warning('Receipt preprocessing PIPELINE_ENTER variant=rotation-only-stable bytes=%s', len(file_bytes) if file_bytes else 0)
    if cv2 is None or np is None:
        LOGGER.warning('Receipt preprocessing PIPELINE_ABORT reason=cv2_or_np_missing cv2=%s np=%s', cv2 is not None, np is not None)
        return file_bytes

    try:
        image = Image.open(io.BytesIO(file_bytes))
        LOGGER.warning('Receipt preprocessing LOAD pil_size=%s mode=%s format=%s', image.size, image.mode, image.format)
        image = ImageOps.exif_transpose(image).convert('RGB')
        original = np.array(image)
        LOGGER.warning('Receipt preprocessing LOAD_RESULT original_shape=%s stats=%s', _shape_text(original), _image_stats(original))

        rotated, detected_angle, applied_angle, rotation_applied = _correct_rotation(original)
        LOGGER.warning(
            'Receipt preprocessing AFTER_ROTATION original_shape=%s rotated_shape=%s detected_angle=%.2f applied_angle=%.2f rotation_applied=%s same_object=%s',
            _shape_text(original),
            _shape_text(rotated),
            detected_angle,
            applied_angle,
            rotation_applied,
            rotated is original,
        )

        final = _resize_max_side(rotated)
        LOGGER.warning('Receipt preprocessing FINAL original_shape=%s rotated_shape=%s final_shape=%s warp_disabled=True', _shape_text(original), _shape_text(rotated), _shape_text(final))

        _save_all_debug_images(original, rotated, final, 'rotation-only-stable')
        output = _encode_png(final)
        LOGGER.warning('Receipt preprocessing PIPELINE_EXIT output_bytes=%s debug_alias=%s', len(output), DEBUG_OUTPUT_PATH)
        return output
    except Exception as exc:
        LOGGER.exception('Receipt preprocessing PIPELINE_EXCEPTION error=%s', exc)
        return file_bytes
