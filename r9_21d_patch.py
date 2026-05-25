from pathlib import Path

p = Path(
    r"C:\Users\Gebruiker\Rezzerv_Github\backend\app\receipt_ingestion\preprocessing\receipt_image_preprocessing.py"
)

s = p.read_text(encoding="utf-8")

marker = """
def _rotate_landscape_to_portrait(image):
    height, width = image.shape[:2]
    if height > 0 and (width / height) >= LANDSCAPE_ASPECT_LIMIT:
        return cv2.rotate(image, cv2.ROTATE_90_COUNTERCLOCKWISE), True
    return image, False
"""

insert = """
def _rotate_landscape_to_portrait(image):
    height, width = image.shape[:2]
    if height > 0 and (width / height) >= LANDSCAPE_ASPECT_LIMIT:
        return cv2.rotate(image, cv2.ROTATE_90_COUNTERCLOCKWISE), True
    return image, False


MIN_FOREGROUND_AREA_RATIO = 0.08


def _find_receipt_foreground_contour(image):
    height, width = image.shape[:2]
    image_area = float(height * width)

    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)

    blur = cv2.GaussianBlur(gray, (5, 5), 0)

    mask = cv2.adaptiveThreshold(
        blur,
        255,
        cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
        cv2.THRESH_BINARY,
        51,
        -6,
    )

    kernel = np.ones((7, 7), np.uint8)

    mask = cv2.morphologyEx(
        mask,
        cv2.MORPH_CLOSE,
        kernel,
        iterations=2,
    )

    contours, _ = cv2.findContours(
        mask,
        cv2.RETR_EXTERNAL,
        cv2.CHAIN_APPROX_SIMPLE,
    )

    best = None
    best_area = 0.0

    for contour in contours:
        area = float(cv2.contourArea(contour))

        if image_area <= 0:
            continue

        ratio = area / image_area

        if ratio < MIN_FOREGROUND_AREA_RATIO:
            continue

        x, y, w, h = cv2.boundingRect(contour)

        if w < 120 or h < 180:
            continue

        aspect = max(w, h) / max(1, min(w, h))

        if aspect < 1.5:
            continue

        if area > best_area:
            best = contour
            best_area = area

    return best


def _isolate_receipt_foreground(image):
    contour = _find_receipt_foreground_contour(image)

    if contour is None:
        return image, False

    mask = np.zeros(image.shape[:2], dtype=np.uint8)

    cv2.drawContours(
        mask,
        [contour],
        -1,
        255,
        thickness=cv2.FILLED,
    )

    white = np.full_like(image, 255)

    isolated = np.where(
        mask[:, :, None] == 255,
        image,
        white,
    )

    x, y, w, h = cv2.boundingRect(contour)

    pad = max(12, int(min(w, h) * 0.03))

    x0 = max(0, x - pad)
    y0 = max(0, y - pad)
    x1 = min(image.shape[1], x + w + pad)
    y1 = min(image.shape[0], y + h + pad)

    cropped = isolated[y0:y1, x0:x1]

    return cropped, True
"""

if marker not in s:
    raise SystemExit("Marker niet gevonden")

s = s.replace(marker, insert)

old = """
    image, rotated = _rotate_landscape_to_portrait(image)
"""

new = """
    image, isolated = _isolate_receipt_foreground(image)

    if isolated:
        applied_steps.append("foreground_isolation")

    image, rotated = _rotate_landscape_to_portrait(image)
"""

if old not in s:
    raise SystemExit("Tweede marker niet gevonden")

s = s.replace(old, new)

p.write_text(s, encoding="utf-8")

print("R9-21D foreground isolation patch toegepast.")
