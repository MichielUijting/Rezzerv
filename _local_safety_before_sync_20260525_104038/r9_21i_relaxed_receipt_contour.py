from pathlib import Path
import re

p = Path(r"C:\Users\Gebruiker\Rezzerv_Github\backend\app\receipt_ingestion\preprocessing\receipt_image_preprocessing.py")
s = p.read_text(encoding="utf-8")

pattern = """def _find_document_quadrilateral\(image\):
.*?
    return best_quad
"""

replacement = """def _find_document_quadrilateral(image):
    height, width = image.shape[:2]
    image_area = float(height * width)

    ratio = height / 900.0 if height > 900 else 1.0
    small = cv2.resize(image, (int(width / ratio), int(height / ratio)))

    gray = cv2.cvtColor(small, cv2.COLOR_BGR2GRAY)
    gray = cv2.bilateralFilter(gray, 9, 75, 75)

    edges = cv2.Canny(gray, 35, 110)
    edges = cv2.dilate(edges, np.ones((5, 5), np.uint8), iterations=2)
    edges = cv2.morphologyEx(edges, cv2.MORPH_CLOSE, np.ones((9, 9), np.uint8), iterations=2)

    contours, _ = cv2.findContours(edges, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    contours = sorted(contours, key=cv2.contourArea, reverse=True)[:30]

    best_quad = None
    best_score = 0.0

    # Route 1: strict document-scanner contour, when a proper 4-point outline exists.
    for contour in contours:
        area_small = float(cv2.contourArea(contour))
        area = area_small * (ratio ** 2)
        if image_area <= 0 or (area / image_area) < MIN_DOCUMENT_AREA_RATIO:
            continue

        perimeter = cv2.arcLength(contour, True)
        for epsilon in (0.015, 0.02, 0.03, 0.04, 0.06, 0.08):
            approx = cv2.approxPolyDP(contour, epsilon * perimeter, True)
            if len(approx) != 4:
                continue

            quad = approx.reshape(4, 2).astype("float32") * ratio
            x, y, w, h = cv2.boundingRect(quad.astype("int32"))
            if w < 160 or h < 260:
                continue

            aspect = max(w, h) / max(1, min(w, h))
            if aspect < 1.55:
                continue

            rect_area = float(w * h)
            fill = area / rect_area if rect_area else 0.0
            score = area * max(0.2, min(fill, 1.0))

            if score > best_score:
                best_quad = quad
                best_score = score

    if best_quad is not None:
        return best_quad

    # Route 2: relaxed receipt acceptance.
    joined = cv2.dilate(edges, np.ones((23, 23), np.uint8), iterations=2)
    joined = cv2.morphologyEx(joined, cv2.MORPH_CLOSE, np.ones((31, 31), np.uint8), iterations=2)

    relaxed_contours, _ = cv2.findContours(joined, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    relaxed_contours = sorted(relaxed_contours, key=cv2.contourArea, reverse=True)[:10]

    best_box = None
    best_relaxed_score = 0.0

    for contour in relaxed_contours:
        area_small = float(cv2.contourArea(contour))
        area = area_small * (ratio ** 2)
        if image_area <= 0 or (area / image_area) < MIN_DOCUMENT_AREA_RATIO:
            continue

        rect = cv2.minAreaRect(contour)
        box_small = cv2.boxPoints(rect).astype("float32")
        box = box_small * ratio

        x, y, w, h = cv2.boundingRect(box.astype("int32"))
        if w < 160 or h < 260:
            continue

        aspect = max(w, h) / max(1, min(w, h))
        if aspect < 1.45:
            continue

        box_area = float(w * h)
        box_ratio = box_area / image_area if image_area else 0.0
        if box_ratio < 0.06 or box_ratio > 0.92:
            continue

        score = area * aspect
        if score > best_relaxed_score:
            best_box = box
            best_relaxed_score = score

    if best_box is not None:
        return best_box

    # Route 3: last fallback on all meaningful edge pixels except very small noise.
    meaningful = []
    for contour in contours:
        area_small = float(cv2.contourArea(contour))
        area = area_small * (ratio ** 2)
        if image_area > 0 and (area / image_area) >= 0.002:
            meaningful.append(contour)

    if meaningful:
        all_points = np.vstack(meaningful)
        rect = cv2.minAreaRect(all_points)
        box = cv2.boxPoints(rect).astype("float32") * ratio
        x, y, w, h = cv2.boundingRect(box.astype("int32"))
        aspect = max(w, h) / max(1, min(w, h))
        box_ratio = float(w * h) / image_area if image_area else 0.0
        if w >= 160 and h >= 260 and aspect >= 1.45 and 0.06 <= box_ratio <= 0.92:
            return box

    return None
"""

new_s, count = re.subn(pattern, replacement, s, flags=re.S)

if count != 1:
    raise SystemExit(f"R9-21I patchpunt niet uniek gevonden; count={count}")

p.write_text(new_s, encoding="utf-8")
print("R9-21I toegepast: relaxed receipt contour acceptance actief.")
