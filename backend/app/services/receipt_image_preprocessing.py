from __future__ import annotations

import io
import logging
import math
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
    if mean < 40 or mean > 248 or std < 8 or dark_ratio > 0.85 or light_ratio < 0.025:
        LOGGER.warning('Receipt preprocessing: hough warp rejected mean=%.2f std=%.2f dark=%.3f light=%.3f', mean, std, dark_ratio, light_ratio)
        return False
    return True


def _line_angle(line):
    x1, y1, x2, y2 = line
    return math.degrees(math.atan2(y2 - y1, x2 - x1))


def _line_length(line):
    x1, y1, x2, y2 = line
    return math.hypot(x2 - x1, y2 - y1)


def _intersect_lines(line_a, line_b):
    x1, y1, x2, y2 = map(float, line_a)
    x3, y3, x4, y4 = map(float, line_b)
    denom = (x1 - x2) * (y3 - y4) - (y1 - y2) * (x3 - x4)
    if abs(denom) < 1e-6:
        return None
    px = ((x1 * y2 - y1 * x2) * (x3 - x4) - (x1 - x2) * (x3 * y4 - y3 * x4)) / denom
    py = ((x1 * y2 - y1 * x2) * (y3 - y4) - (y1 - y2) * (x3 * y4 - y3 * x4)) / denom
    return np.array([px, py], dtype='float32')


def _hough_edges(work_rgb):
    gray = cv2.cvtColor(work_rgb, cv2.COLOR_RGB2GRAY)
    gray = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8)).apply(gray)
    blur = cv2.GaussianBlur(gray, (5, 5), 0)
    median = float(np.median(blur))
    lower = int(max(0, 0.60 * median))
    upper = int(min(255, 1.40 * median))
    edges = cv2.Canny(blur, lower, upper)
    kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (7, 7))
    edges = cv2.morphologyEx(edges, cv2.MORPH_CLOSE, kernel, iterations=1)
    return edges, lower, upper


def _select_hough_lines(lines, width, height):
    if lines is None:
        return []
    min_len = max(width, height) * 0.18
    selected = []
    for raw in lines[:, 0, :]:
        line = tuple(int(v) for v in raw)
        if _line_length(line) < min_len:
            continue
        angle = _line_angle(line)
        selected.append((line, angle, _line_length(line)))
    selected.sort(key=lambda item: item[2], reverse=True)
    return selected[:60]


def _line_family_candidates(selected):
    families = []
    for base_index, (base_line, base_angle, _) in enumerate(selected[:20]):
        parallel = []
        perpendicular = []
        for line, angle, length in selected:
            delta = abs(((angle - base_angle + 90) % 180) - 90)
            perp_delta = abs(delta - 90)
            if delta < 18:
                parallel.append((line, length))
            elif perp_delta < 18:
                perpendicular.append((line, length))
        if len(parallel) >= 2 and len(perpendicular) >= 2:
            families.append((base_index, parallel[:8], perpendicular[:8]))
    return families[:8]


def _quad_from_line_pair(group_a, group_b, width, height):
    best = None
    for i in range(len(group_a)):
        for j in range(i + 1, len(group_a)):
            a1, a2 = group_a[i][0], group_a[j][0]
            for k in range(len(group_b)):
                for l in range(k + 1, len(group_b)):
                    b1, b2 = group_b[k][0], group_b[l][0]
                    pts = [_intersect_lines(a1, b1), _intersect_lines(a1, b2), _intersect_lines(a2, b1), _intersect_lines(a2, b2)]
                    if any(p is None for p in pts):
                        continue
                    pts = np.array(pts, dtype='float32')
                    margin_x = width * 0.08
                    margin_y = height * 0.08
                    if np.any(pts[:, 0] < -margin_x) or np.any(pts[:, 0] > width + margin_x) or np.any(pts[:, 1] < -margin_y) or np.any(pts[:, 1] > height + margin_y):
                        continue
                    area = abs(cv2.contourArea(_order_points(pts)))
                    area_ratio = area / float(width * height)
                    if area_ratio < 0.04 or area_ratio > 0.92:
                        continue
                    x, y, bw, bh = cv2.boundingRect(_order_points(pts).astype('int32'))
                    aspect = max(float(bw) / float(bh), float(bh) / float(bw)) if bw and bh else 0
                    if aspect < 1.15 or aspect > 8.5:
                        continue
                    score = area_ratio * 2.0 + min(aspect, 4.0) * 0.10
                    if best is None or score > best[0]:
                        best = (score, _order_points(pts))
    return best


def _rectify_with_hough(arr):
    work, scale = _resize_for_work(arr)
    height, width = work.shape[:2]
    edges, lower, upper = _hough_edges(work)
    lines = cv2.HoughLinesP(edges, 1, np.pi / 180, threshold=80, minLineLength=int(max(width, height) * 0.16), maxLineGap=45)
    selected = _select_hough_lines(lines, width, height)
    LOGGER.warning('Receipt preprocessing: hough lines=%s selected=%s thresholds=%s/%s', 0 if lines is None else len(lines), len(selected), lower, upper)
    families = _line_family_candidates(selected)
    LOGGER.warning('Receipt preprocessing: hough line families=%s', len(families))

    best = None
    for _, parallel, perpendicular in families:
        candidate = _quad_from_line_pair(parallel, perpendicular, width, height)
        if candidate and (best is None or candidate[0] > best[0]):
            best = candidate
    if best is None:
        return None

    score, points = best
    full_points = points / scale
    warped = _four_point_transform(arr, full_points)
    if not _valid_warp(warped):
        return None
    LOGGER.warning('Receipt preprocessing: hough quad selected score=%.3f points=%s', score, np.round(full_points, 1).tolist())
    return _enhance_for_ocr(warped)


def _fallback_center_crop(arr):
    h, w = arr.shape[:2]
    # Laatste redmiddel: centrale 80% behouden, zodat OCR in elk geval minder achtergrond ziet.
    x1, x2 = int(w * 0.10), int(w * 0.90)
    y1, y2 = int(h * 0.05), int(h * 0.95)
    crop = arr[y1:y2, x1:x2]
    if crop.size == 0:
        return None
    LOGGER.warning('Receipt preprocessing: fallback center crop used')
    return _enhance_for_ocr(crop)


def preprocess_receipt_image_for_ocr(file_bytes: bytes) -> bytes:
    LOGGER.warning('Receipt preprocessing: module entered (hough scanner)')
    if cv2 is None or np is None:
        LOGGER.warning('Receipt preprocessing: cv2/np missing')
        _save_debug_image(file_bytes, 'fallback-dependencies-missing')
        return file_bytes
    try:
        image = Image.open(io.BytesIO(file_bytes))
        image = ImageOps.exif_transpose(image).convert('RGB')
        arr = np.array(image)
        warped = _rectify_with_hough(arr)
        if warped is None:
            warped = _fallback_center_crop(arr)
        if warped is not None:
            result = _encode_png(warped)
            _save_debug_image(result, 'rectified-hough-scanner')
            return result
        LOGGER.warning('Receipt preprocessing: fallback original (hough failed)')
        _save_debug_image(file_bytes, 'fallback-hough-original')
        return file_bytes
    except Exception as exc:
        LOGGER.warning('Hough scanner preprocessing failed: %s', exc)
        _save_debug_image(file_bytes, 'fallback-exception')
        return file_bytes
