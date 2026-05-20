from __future__ import annotations

import argparse
import csv
import json
import math
import re
import sys
import tempfile
import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
for candidate in (ROOT, ROOT / "backend", Path("/app")):
    text = str(candidate)
    if candidate.exists() and text not in sys.path:
        sys.path.insert(0, text)

try:
    import cv2  # type: ignore
    import numpy as np  # type: ignore
except Exception:  # pragma: no cover - diagnostic fallback
    cv2 = None  # type: ignore
    np = None  # type: ignore

try:
    from PIL import Image, ImageDraw, ImageFont  # type: ignore
except Exception as exc:  # pragma: no cover - runtime environment issue
    raise SystemExit(f"Pillow is required for R7c-16 overlays: {exc}") from exc

from paddleocr import PaddleOCR  # type: ignore # noqa: E402

from app.services.receipt_service import (  # noqa: E402
    _extract_payload_from_paddle_item,
    _normalize_paddle_collection,
)

PRICE_PATTERN = re.compile(r"\b\d+[\.,]\d{2}\b")
FOOTER_PATTERN = re.compile(
    r"\b(totaal|total|te betalen|terminal|nfc|chip|kaart|pin|datum|periode|bonuskaart|ah\.nl)\b",
    re.I,
)


@dataclass
class OcrBox:
    text: str
    x1: float
    y1: float
    x2: float
    y2: float
    points: list[tuple[float, float]]

    @property
    def center_x(self) -> float:
        return (self.x1 + self.x2) / 2.0

    @property
    def center_y(self) -> float:
        return (self.y1 + self.y2) / 2.0

    @property
    def width(self) -> float:
        return max(0.0, self.x2 - self.x1)

    @property
    def height(self) -> float:
        return max(0.0, self.y2 - self.y1)


MODEL: PaddleOCR | None = None


def get_model() -> PaddleOCR:
    global MODEL
    if MODEL is None:
        print("initializing raw_paddle_current once", flush=True)
        MODEL = PaddleOCR(
            use_doc_orientation_classify=False,
            use_doc_unwarping=False,
            use_textline_orientation=False,
            lang="en",
        )
    return MODEL


def first_present(payload: dict[str, Any], keys: tuple[str, ...]) -> Any:
    for key in keys:
        if key in payload and payload.get(key) is not None:
            return payload.get(key)
    return None


def find_fixture(zip_path: Path, output_dir: Path) -> Path:
    with zipfile.ZipFile(zip_path) as archive:
        for item in archive.infolist():
            if item.is_dir():
                continue
            name = Path(item.filename).name
            if re.search(r"ah\s*foto\s*3", name, re.I):
                out = output_dir / name
                out.write_bytes(archive.read(item))
                return out
    raise SystemExit("AH foto 3 not found in fixtures zip")


def normalize_points(raw_box: Any) -> list[tuple[float, float]]:
    if hasattr(raw_box, "tolist"):
        raw_box = raw_box.tolist()
    if isinstance(raw_box, (list, tuple)) and len(raw_box) == 4 and not isinstance(raw_box[0], (list, tuple)):
        try:
            x1, y1, x2, y2 = [float(v) for v in raw_box]
            return [(x1, y1), (x2, y1), (x2, y2), (x1, y2)]
        except Exception:
            return []
    if not isinstance(raw_box, (list, tuple)):
        return []
    points: list[tuple[float, float]] = []
    for item in raw_box:
        if hasattr(item, "tolist"):
            item = item.tolist()
        if isinstance(item, (list, tuple)) and len(item) >= 2:
            try:
                points.append((float(item[0]), float(item[1])))
            except Exception:
                continue
    return points


def collect_boxes(image_path: Path) -> list[OcrBox]:
    result = get_model().predict(str(image_path))
    collected: list[OcrBox] = []
    for item in _normalize_paddle_collection(result):
        payload = _extract_payload_from_paddle_item(item)
        texts = _normalize_paddle_collection(first_present(payload, ("rec_texts", "texts")))
        boxes = _normalize_paddle_collection(first_present(payload, ("rec_boxes", "dt_polys", "rec_polys")))
        for text, raw_box in zip(texts, boxes):
            text_value = str(text).strip()
            if not text_value:
                continue
            points = normalize_points(raw_box)
            if not points:
                continue
            xs = [point[0] for point in points]
            ys = [point[1] for point in points]
            collected.append(
                OcrBox(
                    text=text_value,
                    x1=min(xs),
                    y1=min(ys),
                    x2=max(xs),
                    y2=max(ys),
                    points=points,
                )
            )
    return collected


def is_price(text: str) -> bool:
    return bool(PRICE_PATTERN.search(text or ""))


def is_footer_or_payment(text: str) -> bool:
    return bool(FOOTER_PATTERN.search(text or ""))


def cluster_lines(boxes: list[OcrBox]) -> list[list[OcrBox]]:
    if not boxes:
        return []
    ordered = sorted(boxes, key=lambda box: (box.center_y, box.x1))
    heights = sorted(box.height for box in boxes if box.height > 0)
    median_height = heights[len(heights) // 2] if heights else 18.0
    threshold = max(10.0, min(28.0, median_height * 0.75))
    lines: list[list[OcrBox]] = []
    for box in ordered:
        if not lines:
            lines.append([box])
            continue
        current = lines[-1]
        avg_y = sum(item.center_y for item in current) / len(current)
        if math.fabs(box.center_y - avg_y) <= threshold:
            current.append(box)
        else:
            lines.append([box])
    for line in lines:
        line.sort(key=lambda item: item.x1)
    return lines


def candidate_pairs(lines: list[list[OcrBox]]) -> list[dict[str, Any]]:
    pairs: list[dict[str, Any]] = []
    for index, line in enumerate(lines, start=1):
        prices = [box for box in line if is_price(box.text)]
        articles = [box for box in line if not is_price(box.text)]
        if not prices or not articles:
            continue
        article_text = " ".join(item.text for item in articles).strip()
        line_text = " ".join(item.text for item in line).strip()
        for price in prices:
            pairs.append(
                {
                    "line_index": index,
                    "article": article_text,
                    "price": price.text,
                    "line_text": line_text,
                    "is_footer_or_payment": is_footer_or_payment(line_text),
                    "price_center_x": round(price.center_x, 2),
                    "line_center_y": round(sum(item.center_y for item in line) / len(line), 2),
                }
            )
    return pairs


def image_size(path: Path) -> tuple[int, int]:
    with Image.open(path) as image:
        return image.size


def order_polygon_points(points: list[tuple[float, float]]) -> list[tuple[float, float]]:
    if len(points) != 4:
        return points
    pts = sorted(points, key=lambda point: (point[1], point[0]))
    top = sorted(pts[:2], key=lambda point: point[0])
    bottom = sorted(pts[2:], key=lambda point: point[0])
    return [top[0], top[1], bottom[1], bottom[0]]


def detect_receipt_polygon(image_path: Path) -> tuple[list[tuple[float, float]], str]:
    width, height = image_size(image_path)
    fallback = [(0.0, 0.0), (float(width), 0.0), (float(width), float(height)), (0.0, float(height))]
    if cv2 is None or np is None:
        return fallback, "fallback_image_corners_cv2_unavailable"

    image = cv2.imread(str(image_path))
    if image is None:
        return fallback, "fallback_image_corners_cv2_read_failed"

    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    blurred = cv2.GaussianBlur(gray, (5, 5), 0)
    edges = cv2.Canny(blurred, 50, 150)
    contours, _hierarchy = cv2.findContours(edges, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    if not contours:
        return fallback, "fallback_image_corners_no_contours"

    contours = sorted(contours, key=cv2.contourArea, reverse=True)[:10]
    image_area = float(width * height)
    for contour in contours:
        area = float(cv2.contourArea(contour))
        if area < image_area * 0.10:
            continue
        peri = cv2.arcLength(contour, True)
        approx = cv2.approxPolyDP(contour, 0.03 * peri, True)
        if len(approx) == 4:
            pts = [(float(point[0][0]), float(point[0][1])) for point in approx]
            return order_polygon_points(pts), "largest_four_point_contour"

    # Conservative fallback: minimum area rectangle around the largest likely contour.
    largest = contours[0]
    rect = cv2.minAreaRect(largest)
    box = cv2.boxPoints(rect)
    pts = [(float(point[0]), float(point[1])) for point in box]
    return order_polygon_points(pts), "min_area_rect_fallback"


def polygon_metrics(polygon: list[tuple[float, float]]) -> dict[str, Any]:
    if len(polygon) != 4:
        return {"polygon_point_count": len(polygon)}
    tl, tr, br, bl = polygon
    top_width = math.dist(tl, tr)
    bottom_width = math.dist(bl, br)
    left_height = math.dist(tl, bl)
    right_height = math.dist(tr, br)
    top_angle = math.degrees(math.atan2(tr[1] - tl[1], tr[0] - tl[0]))
    left_angle = math.degrees(math.atan2(bl[1] - tl[1], bl[0] - tl[0]))
    convergence_ratio = round(min(top_width, bottom_width) / max(top_width, bottom_width), 4) if max(top_width, bottom_width) else 0.0
    return {
        "polygon_point_count": 4,
        "top_width": round(top_width, 2),
        "bottom_width": round(bottom_width, 2),
        "left_height": round(left_height, 2),
        "right_height": round(right_height, 2),
        "top_edge_angle_deg": round(top_angle, 2),
        "left_edge_angle_deg": round(left_angle, 2),
        "width_convergence_ratio": convergence_ratio,
        "perspective_suspected": convergence_ratio < 0.85 or abs(top_angle) > 5.0,
    }


def warp_receipt(image_path: Path, polygon: list[tuple[float, float]], out_path: Path) -> bool:
    if cv2 is None or np is None or len(polygon) != 4:
        Image.open(image_path).save(out_path)
        return False
    image = cv2.imread(str(image_path))
    if image is None:
        Image.open(image_path).save(out_path)
        return False
    ordered = order_polygon_points(polygon)
    tl, tr, br, bl = ordered
    width_a = math.dist(br, bl)
    width_b = math.dist(tr, tl)
    height_a = math.dist(tr, br)
    height_b = math.dist(tl, bl)
    max_width = max(1, int(max(width_a, width_b)))
    max_height = max(1, int(max(height_a, height_b)))
    src = np.array(ordered, dtype="float32")
    dst = np.array(
        [[0, 0], [max_width - 1, 0], [max_width - 1, max_height - 1], [0, max_height - 1]],
        dtype="float32",
    )
    matrix = cv2.getPerspectiveTransform(src, dst)
    warped = cv2.warpPerspective(image, matrix, (max_width, max_height))
    cv2.imwrite(str(out_path), warped)
    return True


def safe_font() -> Any:
    try:
        return ImageFont.truetype("DejaVuSans.ttf", 14)
    except Exception:
        return ImageFont.load_default()


def draw_polygon(draw: ImageDraw.ImageDraw, points: list[tuple[float, float]], color: str, width: int = 4) -> None:
    if len(points) < 2:
        return
    closed = points + [points[0]]
    draw.line(closed, fill=color, width=width)


def draw_box(draw: ImageDraw.ImageDraw, box: OcrBox, color: str, width: int = 2) -> None:
    points = box.points if len(box.points) >= 4 else [(box.x1, box.y1), (box.x2, box.y1), (box.x2, box.y2), (box.x1, box.y2)]
    draw_polygon(draw, points, color, width)


def save_original_overlay(image_path: Path, polygon: list[tuple[float, float]], out_path: Path) -> None:
    image = Image.open(image_path).convert("RGB")
    draw = ImageDraw.Draw(image)
    draw_polygon(draw, polygon, "red", 5)
    image.save(out_path)


def save_ocr_overlay(image_path: Path, boxes: list[OcrBox], out_path: Path) -> None:
    image = Image.open(image_path).convert("RGB")
    draw = ImageDraw.Draw(image)
    font = safe_font()
    for index, box in enumerate(boxes, start=1):
        color = "blue" if not is_price(box.text) else "green"
        draw_box(draw, box, color, 2)
        draw.text((box.x1, max(0, box.y1 - 16)), str(index), fill=color, font=font)
    image.save(out_path)


def save_line_overlay(image_path: Path, lines: list[list[OcrBox]], out_path: Path) -> None:
    image = Image.open(image_path).convert("RGB")
    draw = ImageDraw.Draw(image)
    font = safe_font()
    palette = ["red", "blue", "green", "purple", "orange", "brown", "cyan", "magenta"]
    for index, line in enumerate(lines, start=1):
        color = palette[(index - 1) % len(palette)]
        if not line:
            continue
        min_x = min(box.x1 for box in line)
        max_x = max(box.x2 for box in line)
        min_y = min(box.y1 for box in line)
        max_y = max(box.y2 for box in line)
        draw.rectangle((min_x, min_y, max_x, max_y), outline=color, width=3)
        draw.text((min_x, max(0, min_y - 18)), f"L{index}", fill=color, font=font)
    image.save(out_path)


def save_pair_overlay(image_path: Path, lines: list[list[OcrBox]], pairs: list[dict[str, Any]], out_path: Path) -> None:
    image = Image.open(image_path).convert("RGB")
    draw = ImageDraw.Draw(image)
    font = safe_font()
    for pair in pairs:
        line_index = int(pair.get("line_index") or 0)
        if line_index <= 0 or line_index > len(lines):
            continue
        line = lines[line_index - 1]
        price_boxes = [box for box in line if box.text == pair.get("price")]
        article_boxes = [box for box in line if not is_price(box.text)]
        if not price_boxes or not article_boxes:
            continue
        price = price_boxes[0]
        article_x = sum(box.center_x for box in article_boxes) / len(article_boxes)
        article_y = sum(box.center_y for box in article_boxes) / len(article_boxes)
        color = "red" if pair.get("is_footer_or_payment") else "green"
        draw.line((article_x, article_y, price.center_x, price.center_y), fill=color, width=4)
        draw.text((article_x, max(0, article_y - 18)), f"P{line_index}", fill=color, font=font)
    image.save(out_path)


def line_rows(lines: list[list[OcrBox]]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for index, line in enumerate(lines, start=1):
        line_text = " ".join(box.text for box in line)
        rows.append(
            {
                "line_index": index,
                "line_text": line_text,
                "box_count": len(line),
                "price_count": sum(1 for box in line if is_price(box.text)),
                "footer_or_payment": is_footer_or_payment(line_text),
                "min_y": round(min(box.y1 for box in line), 2) if line else 0,
                "max_y": round(max(box.y2 for box in line), 2) if line else 0,
            }
        )
    return rows


def main() -> int:
    parser = argparse.ArgumentParser(description="R7c-16 AH foto 3 perspective and geometry diagnostics")
    parser.add_argument("--fixtures-zip", required=True)
    parser.add_argument("--json-out", required=True)
    parser.add_argument("--csv-out", required=True)
    parser.add_argument("--out-dir", required=True)
    args = parser.parse_args()

    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    with tempfile.TemporaryDirectory(prefix="r7c16-ah3-") as td:
        image_path = find_fixture(Path(args.fixtures_zip), Path(td))
        width, height = image_size(image_path)
        polygon, polygon_method = detect_receipt_polygon(image_path)
        metrics = polygon_metrics(polygon)

        original_overlay = out_dir / "r7c16_ah3_original_overlay.png"
        warped_preview = out_dir / "r7c16_ah3_warped_preview.png"
        ocr_overlay = out_dir / "r7c16_ah3_ocr_boxes_overlay.png"
        line_overlay = out_dir / "r7c16_ah3_line_clusters_overlay.png"
        pair_overlay = out_dir / "r7c16_ah3_price_pairs_overlay.png"

        save_original_overlay(image_path, polygon, original_overlay)
        warp_applied = warp_receipt(image_path, polygon, warped_preview)

        boxes = collect_boxes(image_path)
        lines = cluster_lines(boxes)
        pairs = candidate_pairs(lines)

        save_ocr_overlay(image_path, boxes, ocr_overlay)
        save_line_overlay(image_path, lines, line_overlay)
        save_pair_overlay(image_path, lines, pairs, pair_overlay)

    rows = line_rows(lines)
    footer_pair_count = sum(1 for pair in pairs if bool(pair.get("is_footer_or_payment")))
    result = {
        "fixture_file": "AH foto 3.jpg",
        "diagnostic_only": True,
        "image": {"width": width, "height": height},
        "receipt_polygon": {
            "method": polygon_method,
            "points": [[round(x, 2), round(y, 2)] for x, y in polygon],
            "metrics": metrics,
            "warp_applied": warp_applied,
        },
        "ocr_summary": {
            "ocr_box_count": len(boxes),
            "line_cluster_count": len(lines),
            "candidate_pair_count": len(pairs),
            "footer_or_payment_pair_count": footer_pair_count,
            "non_footer_candidate_pair_count": len(pairs) - footer_pair_count,
        },
        "line_clusters": rows,
        "candidate_pairs": pairs[:25],
        "outputs": {
            "original_overlay": str(original_overlay),
            "warped_preview": str(warped_preview),
            "ocr_boxes_overlay": str(ocr_overlay),
            "line_clusters_overlay": str(line_overlay),
            "price_pairs_overlay": str(pair_overlay),
        },
    }

    json_out = Path(args.json_out)
    json_out.parent.mkdir(parents=True, exist_ok=True)
    json_out.write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8")

    csv_out = Path(args.csv_out)
    csv_out.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = ["line_index", "line_text", "box_count", "price_count", "footer_or_payment", "min_y", "max_y"]
    with csv_out.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)

    print("R7c-16 AH foto 3 perspective and geometry diagnostics")
    print(f"ocr_box_count: {len(boxes)}")
    print(f"line_cluster_count: {len(lines)}")
    print(f"candidate_pair_count: {len(pairs)}")
    print(f"footer_or_payment_pair_count: {footer_pair_count}")
    print(f"polygon_method: {polygon_method}")
    print(f"perspective_suspected: {metrics.get('perspective_suspected')}")
    print(f"json_written: {json_out}")
    print(f"csv_written: {csv_out}")
    print(f"overlays_written: {out_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
