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

DEBUG_OUTPUT_PATH = Path('/app/data/receipts/debug/latest-ocr-preprocessed.png')
MAX_WORK_SIDE = 1600


def _encode_png(arr) -> bytes:
    out = Image.fromarray(arr)
    buffer = io.BytesIO()
    out.save(buffer, format='PNG')
    return buffer.getvalue()


def _save_debug_image(image_bytes: bytes, reason: str) -> None:
    try:
        DEBUG_OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
        DEBUG_OUTPUT_PATH.write_bytes(image_bytes)
        LOGGER.warning('Receipt preprocessing: debug image saved path=%s reason=%s', DEBUG_OUTPUT_PATH, reason)
    except Exception as exc:
        LOGGER.warning('Receipt preprocessing: debug image save failed: %s', exc)


def _order_points(pts):
    rect = np.zeros((4, 2), dtype='float32')
    s = pts.sum(axis=1)
    rect[0] = pts[np.argmin(s)]
    rect[2] = pts[np.argmax(s)]
    diff = np.diff(pts, axis=1)
    rect[1] = pts[np.argmin(diff)]
    rect[3] = pts[np.argmax(diff)]
    return rect


def _resize_for_work(rgb):
    height, width = rgb.shape[:2]
    largest = max(height, width)
    if largest <= MAX_WORK_SIDE:
        return rgb, 1.0
    scale = MAX_WORK_SIDE / float(largest)
    resized = cv2.resize(rgb, (int(width * scale), int(height * scale)), interpolation=cv2.INTER_AREA)
    return resized, scale


def _four_point_transform(image, pts):
    rect = _order_points(pts.astype('float32'))
    tl, tr, br, bl = rect
    max_width = int(max(np.linalg.norm(br - bl), np.linalg.norm(tr - tl)))
    max_height = int(max(np.linalg.norm(tr - br), np.linalg.norm(tl - bl)))
    if max_width < 180 or max_height < 180:
        return None
    dst = np.array([[0, 0], [max_width - 1, 0], [max_width - 1, max_height - 1], [0, max_height - 1]], dtype='float32')
    matrix = cv2.getPerspectiveTransform(rect, dst)
    return cv2.warpPerspective(image, matrix, (max_width, max_height), borderValue=(255, 255, 255))


def _enhance_for_ocr(rgb):
    lab = cv2.cvtColor(rgb, cv2.COLOR_RGB2LAB)
    l_chan, a_chan, b_chan = cv2.split(lab)
    clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
    l_chan = clahe.apply(l_chan)
    enhanced = cv2.merge((l_chan, a_chan, b_chan))
    return cv2.cvtColor(enhanced, cv2.COLOR_LAB2RGB)


def _valid_warp(warped, allow_forced: bool = False) -> bool:
    if warped is None:
        return False
    h, w = warped.shape[:2]
    if w < 180 or h < 180:
        return False
    gray = cv2.cvtColor(warped, cv2.COLOR_RGB2GRAY)
    mean = float(np.mean(gray))
    std = float(np.std(gray))
    dark_ratio = float(np.mean(gray < 55))
    light_ratio = float(np.mean(gray > 170))
    if allow_forced:
        if mean < 25 or mean > 252 or std < 4 or dark_ratio > 0.92:
            LOGGER.warning('Receipt preprocessing: forced warp rejected mean=%.2f std=%.2f dark=%.3f light=%.3f', mean, std, dark_ratio, light_ratio)
            return False
        return True
    if mean < 40 or mean > 248 or std < 8 or dark_ratio > 0.85 or light_ratio < 0.04:
        LOGGER.warning('Receipt preprocessing: scanner warp rejected mean=%.2f std=%.2f dark=%.3f light=%.3f', mean, std, dark_ratio, light_ratio)
        return False
    return True


def _contour_to_points(contour):
    peri = cv2.arcLength(contour, True)
    for eps in (0.015, 0.02, 0.025, 0.03, 0.04, 0.06, 0.08):
        approx = cv2.approxPolyDP(contour, eps * peri, True)
        if len(approx) == 4:
            return approx.reshape(4, 2).astype('float32'), 'approx4'
    return cv2.boxPoints(cv2.minAreaRect(contour)).astype('float32'), 'minAreaRect'


def _score_candidate(points, contour, image_shape):
    h, w = image_shape[:2]
    image_area = float(h * w)
    area = float(abs(cv2.contourArea(points.astype('float32'))))
    contour_area = float(cv2.contourArea(contour))
    area_ratio = max(area, contour_area) / image_area if image_area else 0.0
    if area_ratio < 0.01 or area_ratio > 0.96:
        return None
    x, y, bw, bh = cv2.boundingRect(points.astype('int32'))
    if bw < 80 or bh < 80:
        return None
    aspect = max(float(bw) / float(bh), float(bh) / float(bw))
    if aspect < 1.05 or aspect > 10.0:
        return None
    center_x = x + bw / 2.0
    center_y = y + bh / 2.0
    center_penalty = abs(center_x - w / 2.0) / w + abs(center_y - h / 2.0) / h
    return area_ratio * 2.0 + min(aspect, 4.0) * 0.12 - center_penalty * 0.25


def _scanner_contours(work_rgb):
    gray = cv2.cvtColor(work_rgb, cv2.COLOR_RGB2GRAY)
    clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
    gray = clahe.apply(gray)
    blur = cv2.bilateralFilter(gray, 9, 75, 75)
    median = float(np.median(blur))
    lower = int(max(0, 0.66 * median))
    upper = int(min(255, 1.33 * median))
    edges = cv2.Canny(blur, lower, upper)
    close_kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (9, 9))
    edges = cv2.morphologyEx(edges, cv2.MORPH_CLOSE, close_kernel, iterations=2)
    contours, _ = cv2.findContours(edges, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    LOGGER.warning('Receipt preprocessing: scanner edge contours=%s thresholds=%s/%s', len(contours), lower, upper)
    return contours


def _scanner_mask_contours(work_rgb):
    gray = cv2.cvtColor(work_rgb, cv2.COLOR_RGB2GRAY)
    lab = cv2.cvtColor(work_rgb, cv2.COLOR_RGB2LAB)
    l_chan = lab[:, :, 0]
    threshold_gray = max(90, int(np.percentile(gray, 62)))
    threshold_l = max(105, int(np.percentile(l_chan, 60)))
    mask = cv2.bitwise_or(cv2.inRange(gray, threshold_gray, 255), cv2.inRange(l_chan, threshold_l, 255))
    close_kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (17, 17))
    open_kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (5, 5))
    mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, close_kernel, iterations=2)
    mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, open_kernel, iterations=1)
    contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    LOGGER.warning('Receipt preprocessing: scanner mask contours=%s thresholds=%s/%s', len(contours), threshold_gray, threshold_l)
    return contours


def _forced_min_area_rect(arr, work, scale):
    all_contours = []
    for contours in (_scanner_contours(work), _scanner_mask_contours(work)):
        all_contours.extend(contours)
    if not all_contours:
        return None
    contours = sorted(all_contours, key=cv2.contourArea, reverse=True)
    for index, contour in enumerate(contours[:8]):
        if cv2.contourArea(contour) < 50:
            continue
        points = cv2.boxPoints(cv2.minAreaRect(contour)).astype('float32') / scale
        warped = _four_point_transform(arr, points)
        if _valid_warp(warped, allow_forced=True):
            LOGGER.warning('Receipt preprocessing: FORCED minAreaRect fallback used index=%s', index)
            return _enhance_for_ocr(warped)
    return None


def _rectify_with_scanner_pattern(arr):
    work, scale = _resize_for_work(arr)
    candidates = []
    for source_name, contours in (('edges', _scanner_contours(work)), ('mask', _scanner_mask_contours(work))):
        for contour in sorted(contours, key=cv2.contourArea, reverse=True)[:30]:
            points, method = _contour_to_points(contour)
            score = _score_candidate(points, contour, work.shape)
            if score is None:
                score = 0.01
            full_points = points / scale
            candidates.append((score, source_name, method, full_points))
    candidates.sort(key=lambda item: item[0], reverse=True)
    LOGGER.warning('Receipt preprocessing: scanner candidates=%s', len(candidates))
    for score, source_name, method, points in candidates[:15]:
        warped = _four_point_transform(arr, points)
        if not _valid_warp(warped):
            continue
        LOGGER.warning('Receipt preprocessing: scanner contour selected source=%s method=%s score=%.3f', source_name, method, score)
        return _enhance_for_ocr(warped)
    forced = _forced_min_area_rect(arr, work, scale)
    if forced is not None:
        return forced
    return None


def preprocess_receipt_image_for_ocr(file_bytes: bytes) -> bytes:
    LOGGER.warning('Receipt preprocessing: module entered (opencv scanner pattern)')
    if cv2 is None or np is None:
        LOGGER.warning('Receipt preprocessing: cv2/np missing')
        _save_debug_image(file_bytes, 'fallback-dependencies-missing')
        return file_bytes
    try:
        image = Image.open(io.BytesIO(file_bytes))
        image = ImageOps.exif_transpose(image).convert('RGB')
        arr = np.array(image)
        warped = _rectify_with_scanner_pattern(arr)
        if warped is not None:
            result = _encode_png(warped)
            _save_debug_image(result, 'rectified-opencv-scanner-pattern')
            return result
        LOGGER.warning('Receipt preprocessing: fallback (no valid scanner contour)')
        _save_debug_image(file_bytes, 'fallback-no-valid-scanner-contour')
        return file_bytes
    except Exception as exc:
        LOGGER.warning('OpenCV scanner preprocessing failed: %s', exc)
        _save_debug_image(file_bytes, 'fallback-exception')
        return file_bytes
