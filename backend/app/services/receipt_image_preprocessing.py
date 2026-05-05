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
DEBUG_ROTATED_PATH = DEBUG_DIR / 'latest-ocr-01-rectified.png'
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


def _save_all_debug_images(original, rectified, final, reason: str) -> None:
    _write_debug_png(DEBUG_ORIGINAL_PATH, original, f'{reason}:original')
    _write_debug_png(DEBUG_ROTATED_PATH, rectified, f'{reason}:rectified')
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


def _order_points(pts):
    rect = np.zeros((4, 2), dtype='float32')
    s = pts.sum(axis=1)
    rect[0] = pts[np.argmin(s)]
    rect[2] = pts[np.argmax(s)]
    diff = np.diff(pts, axis=1)
    rect[1] = pts[np.argmin(diff)]
    rect[3] = pts[np.argmax(diff)]
    return rect


def _four_point_transform(rgb, pts):
    rect = _order_points(pts.astype('float32'))
    tl, tr, br, bl = rect
    max_width = int(max(np.linalg.norm(br - bl), np.linalg.norm(tr - tl)))
    max_height = int(max(np.linalg.norm(tr - br), np.linalg.norm(tl - bl)))
    LOGGER.warning('Receipt preprocessing RECTIFY_TARGET width=%s height=%s ordered_points=%s', max_width, max_height, np.round(rect, 1).tolist())
    if max_width < 250 or max_height < 250:
        LOGGER.warning('Receipt preprocessing RECTIFY_REJECT reason=too_small width=%s height=%s', max_width, max_height)
        return None
    dst = np.array([[0, 0], [max_width - 1, 0], [max_width - 1, max_height - 1], [0, max_height - 1]], dtype='float32')
    matrix = cv2.getPerspectiveTransform(rect, dst)
    warped = cv2.warpPerspective(rgb, matrix, (max_width, max_height), borderValue=(255, 255, 255))
    LOGGER.warning('Receipt preprocessing RECTIFY_APPLIED output_shape=%s stats=%s matrix=%s', _shape_text(warped), _image_stats(warped), np.round(matrix, 3).tolist())
    return warped


def _normalize_portrait(rgb):
    height, width = rgb.shape[:2]
    rotated = False
    if width > height:
        rgb = cv2.rotate(rgb, cv2.ROTATE_90_CLOCKWISE)
        rotated = True
    LOGGER.warning('Receipt preprocessing ORIENTATION_NORMALIZE input_width=%s input_height=%s rotated_to_portrait=%s output_shape=%s', width, height, rotated, _shape_text(rgb))
    return rgb


def _build_paper_mask(rgb):
    gray = cv2.cvtColor(rgb, cv2.COLOR_RGB2GRAY)
    lab = cv2.cvtColor(rgb, cv2.COLOR_RGB2LAB)
    l_chan = lab[:, :, 0]
    gray_threshold = max(95, int(np.percentile(gray, 63)))
    l_threshold = max(110, int(np.percentile(l_chan, 61)))
    mask = cv2.bitwise_or(cv2.inRange(gray, gray_threshold, 255), cv2.inRange(l_chan, l_threshold, 255))
    close_kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (21, 21))
    open_kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (5, 5))
    mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, close_kernel, iterations=2)
    mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, open_kernel, iterations=1)
    LOGGER.warning('Receipt preprocessing MASK thresholds gray=%s lab_l=%s white_ratio=%.4f', gray_threshold, l_threshold, float(np.mean(mask > 0)))
    return mask


def _candidate_score(points, contour, image_shape):
    height, width = image_shape[:2]
    image_area = float(height * width)
    area = float(abs(cv2.contourArea(points.astype('float32'))))
    contour_area = float(cv2.contourArea(contour))
    area_ratio = max(area, contour_area) / image_area if image_area else 0.0
    x, y, bw, bh = cv2.boundingRect(points.astype('int32'))
    aspect = max(float(bw) / float(bh), float(bh) / float(bw)) if bw and bh else 0.0
    center_x = x + bw / 2.0
    center_y = y + bh / 2.0
    center_penalty = abs(center_x - width / 2.0) / width + abs(center_y - height / 2.0) / height
    plausible = 0.03 <= area_ratio <= 0.85 and 1.25 <= aspect <= 8.0 and bw >= 200 and bh >= 200
    score = area_ratio * 2.0 + min(aspect, 5.0) * 0.12 - center_penalty * 0.20
    return plausible, score, area_ratio, aspect, (x, y, bw, bh)


def _detect_receipt_rectangle(rgb):
    LOGGER.warning('Receipt preprocessing RECT_DETECT start input_shape=%s stats=%s', _shape_text(rgb), _image_stats(rgb))
    mask = _build_paper_mask(rgb)
    contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    contours = sorted(contours, key=cv2.contourArea, reverse=True)[:20]
    LOGGER.warning('Receipt preprocessing RECT_CONTOURS count=%s', len(contours))

    best = None
    for index, contour in enumerate(contours):
        if cv2.contourArea(contour) < 100:
            continue
        rect = cv2.minAreaRect(contour)
        box = cv2.boxPoints(rect).astype('float32')
        plausible, score, area_ratio, aspect, bbox = _candidate_score(box, contour, rgb.shape)
        (cx, cy), (rw, rh), rect_angle = rect
        LOGGER.warning(
            'Receipt preprocessing RECT_CANDIDATE index=%s contour_area=%.2f center=(%.1f,%.1f) rect_size=(%.1f,%.1f) rect_angle=%.2f area_ratio=%.4f aspect=%.3f bbox=%s plausible=%s score=%.4f box=%s',
            index,
            float(cv2.contourArea(contour)),
            cx,
            cy,
            rw,
            rh,
            rect_angle,
            area_ratio,
            aspect,
            bbox,
            plausible,
            score,
            np.round(box, 1).tolist(),
        )
        if not plausible:
            continue
        if best is None or score > best[0]:
            best = (score, box, rect)

    if best is None:
        LOGGER.warning('Receipt preprocessing RECT_DETECT result=none')
        return None

    score, box, rect = best
    LOGGER.warning('Receipt preprocessing RECT_DETECT selected score=%.4f rect=%s box=%s', score, rect, np.round(box, 1).tolist())
    return box


def _rectify_receipt_document(rgb):
    points = _detect_receipt_rectangle(rgb)
    if points is None:
        LOGGER.warning('Receipt preprocessing RECTIFY skipped reason=no_document_rectangle')
        return rgb, False
    warped = _four_point_transform(rgb, points)
    if warped is None:
        LOGGER.warning('Receipt preprocessing RECTIFY skipped reason=transform_failed')
        return rgb, False
    normalized = _normalize_portrait(warped)
    return normalized, True


def preprocess_receipt_image_for_ocr(file_bytes: bytes) -> bytes:
    LOGGER.warning('Receipt preprocessing PIPELINE_ENTER variant=document-rectangle-rectifier bytes=%s', len(file_bytes) if file_bytes else 0)
    if cv2 is None or np is None:
        LOGGER.warning('Receipt preprocessing PIPELINE_ABORT reason=cv2_or_np_missing cv2=%s np=%s', cv2 is not None, np is not None)
        return file_bytes

    try:
        image = Image.open(io.BytesIO(file_bytes))
        LOGGER.warning('Receipt preprocessing LOAD pil_size=%s mode=%s format=%s', image.size, image.mode, image.format)
        image = ImageOps.exif_transpose(image).convert('RGB')
        original = np.array(image)
        LOGGER.warning('Receipt preprocessing LOAD_RESULT original_shape=%s stats=%s', _shape_text(original), _image_stats(original))

        rectified, rectified_applied = _rectify_receipt_document(original)
        LOGGER.warning('Receipt preprocessing AFTER_RECTIFY original_shape=%s rectified_shape=%s rectified_applied=%s same_object=%s', _shape_text(original), _shape_text(rectified), rectified_applied, rectified is original)

        final = _resize_max_side(rectified)
        LOGGER.warning('Receipt preprocessing FINAL original_shape=%s rectified_shape=%s final_shape=%s', _shape_text(original), _shape_text(rectified), _shape_text(final))

        _save_all_debug_images(original, rectified, final, 'document-rectangle-rectifier')
        output = _encode_png(final)
        LOGGER.warning('Receipt preprocessing PIPELINE_EXIT output_bytes=%s debug_alias=%s', len(output), DEBUG_OUTPUT_PATH)
        return output
    except Exception as exc:
        LOGGER.exception('Receipt preprocessing PIPELINE_EXCEPTION error=%s', exc)
        return file_bytes
