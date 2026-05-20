from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any
import re


@dataclass(frozen=True)
class TextBox:
    text: str
    confidence: float | None
    x_min: float
    y_min: float
    x_max: float
    y_max: float

    @property
    def width(self) -> float:
        return max(1.0, self.x_max - self.x_min)

    @property
    def height(self) -> float:
        return max(1.0, self.y_max - self.y_min)

    @property
    def x_center(self) -> float:
        return (self.x_min + self.x_max) / 2.0

    @property
    def y_center(self) -> float:
        return (self.y_min + self.y_max) / 2.0


@dataclass(frozen=True)
class TextRegion:
    region_id: str
    bbox: tuple[float, float, float, float]
    text_count: int
    line_count: int
    confidence: float | None
    x_center: float
    y_min: float
    y_max: float
    top_texts: list[str]
    score: float


@dataclass(frozen=True)
class TextLayoutDiagnostic:
    candidate_regions_count: int
    primary_region_id: str | None
    primary_region_confidence: float
    multi_text_regions_detected: bool
    regions: list[dict[str, Any]]
    diagnostic_only: bool = True


def normalize_text(value: Any) -> str:
    return re.sub(r'\s+', ' ', str(value or '')).strip()


def box_from_ocr_bbox(text: Any, bbox: Any, confidence: Any = None) -> TextBox | None:
    normalized_text = normalize_text(text)
    if not normalized_text or bbox is None:
        return None
    try:
        if isinstance(bbox, (list, tuple)) and len(bbox) == 4 and not isinstance(bbox[0], (list, tuple)):
            x1, y1, x2, y2 = [float(value) for value in bbox]
            x_min, x_max = sorted((x1, x2))
            y_min, y_max = sorted((y1, y2))
        else:
            points: list[tuple[float, float]] = []
            for point in bbox:
                if not isinstance(point, (list, tuple)) or len(point) < 2:
                    continue
                points.append((float(point[0]), float(point[1])))
            if not points:
                return None
            xs = [point[0] for point in points]
            ys = [point[1] for point in points]
            x_min, x_max = min(xs), max(xs)
            y_min, y_max = min(ys), max(ys)
        parsed_confidence = None
        if confidence is not None:
            try:
                parsed_confidence = float(confidence)
            except (TypeError, ValueError):
                parsed_confidence = None
        if x_max <= x_min or y_max <= y_min:
            return None
        return TextBox(normalized_text, parsed_confidence, x_min, y_min, x_max, y_max)
    except Exception:
        return None


def cluster_text_regions(boxes: list[TextBox]) -> list[TextRegion]:
    clean_boxes = [box for box in boxes if box.text]
    if not clean_boxes:
        return []

    widths = [box.width for box in clean_boxes]
    median_width = sorted(widths)[len(widths) // 2]
    x_threshold = max(90.0, median_width * 2.4)

    clusters: list[list[TextBox]] = []
    for box in sorted(clean_boxes, key=lambda item: item.x_center):
        best_cluster_index: int | None = None
        best_distance = float('inf')
        for index, cluster in enumerate(clusters):
            center = sum(item.x_center for item in cluster) / len(cluster)
            distance = abs(box.x_center - center)
            if distance < best_distance:
                best_distance = distance
                best_cluster_index = index
        if best_cluster_index is None or best_distance > x_threshold:
            clusters.append([box])
        else:
            clusters[best_cluster_index].append(box)

    regions: list[TextRegion] = []
    total_boxes = len(clean_boxes)
    for index, cluster in enumerate(clusters, start=1):
        cluster = sorted(cluster, key=lambda item: (item.y_center, item.x_center))
        x_min = min(item.x_min for item in cluster)
        y_min = min(item.y_min for item in cluster)
        x_max = max(item.x_max for item in cluster)
        y_max = max(item.y_max for item in cluster)
        x_center = sum(item.x_center for item in cluster) / len(cluster)
        confidences = [item.confidence for item in cluster if item.confidence is not None]
        confidence = round(sum(confidences) / len(confidences), 4) if confidences else None
        y_values = sorted(item.y_center for item in cluster)
        line_count = 0
        last_y: float | None = None
        line_threshold = max(12.0, sum(item.height for item in cluster) / len(cluster) * 0.75)
        for y_value in y_values:
            if last_y is None or abs(y_value - last_y) > line_threshold:
                line_count += 1
                last_y = y_value
        text_share = len(cluster) / max(1, total_boxes)
        vertical_span = y_max - y_min
        score = round((text_share * 0.65) + (min(1.0, vertical_span / 1200.0) * 0.25) + (min(1.0, line_count / 18.0) * 0.10), 4)
        regions.append(
            TextRegion(
                region_id=f'region_{index}',
                bbox=(round(x_min, 2), round(y_min, 2), round(x_max, 2), round(y_max, 2)),
                text_count=len(cluster),
                line_count=line_count,
                confidence=confidence,
                x_center=round(x_center, 2),
                y_min=round(y_min, 2),
                y_max=round(y_max, 2),
                top_texts=[item.text for item in cluster[:8]],
                score=score,
            )
        )

    regions.sort(key=lambda region: region.score, reverse=True)
    return regions


def select_primary_text_region(regions: list[dict[str, Any]]) -> dict[str, Any]:
    ranked = sorted(
        [region for region in regions if isinstance(region, dict)],
        key=lambda region: (
            float(region.get('score') or 0.0),
            int(region.get('text_count') or 0),
            int(region.get('line_count') or 0),
        ),
        reverse=True,
    )
    if not ranked:
        return {
            'selected_region_id': None,
            'selected_bbox': None,
            'selected_score': 0.0,
            'selected_text_count': 0,
            'selected_line_count': 0,
            'selection_confidence': 0.0,
            'multi_text_regions_detected': False,
            'competing_region_count': 0,
            'reason': 'no text regions available',
            'diagnostic_only': True,
        }
    selected = ranked[0]
    selected_score = float(selected.get('score') or 0.0)
    competing = [
        region for region in ranked[1:]
        if int(region.get('text_count') or 0) >= 3
        and float(region.get('score') or 0.0) >= max(0.12, selected_score * 0.22)
    ]
    second_score = float(competing[0].get('score') or 0.0) if competing else 0.0
    confidence = min(1.0, selected_score) if not competing else max(0.0, min(1.0, (selected_score - second_score) / max(selected_score, 0.0001)))
    return {
        'selected_region_id': selected.get('region_id'),
        'selected_bbox': selected.get('bbox'),
        'selected_score': round(selected_score, 4),
        'selected_text_count': int(selected.get('text_count') or 0),
        'selected_line_count': int(selected.get('line_count') or 0),
        'selection_confidence': round(confidence, 4),
        'multi_text_regions_detected': bool(competing),
        'competing_region_count': len(competing),
        'reason': 'single dominant text region' if not competing else 'primary region selected from multiple competing text regions',
        'diagnostic_only': True,
    }


def build_text_layout_diagnostic(boxes: list[TextBox]) -> TextLayoutDiagnostic:
    regions = cluster_text_regions(boxes)
    selection = select_primary_text_region([asdict(region) for region in regions])
    primary_confidence = regions[0].confidence if regions and regions[0].confidence is not None else 0.0
    return TextLayoutDiagnostic(
        candidate_regions_count=len(regions),
        primary_region_id=selection['selected_region_id'],
        primary_region_confidence=primary_confidence,
        multi_text_regions_detected=bool(selection['multi_text_regions_detected']),
        regions=[asdict(region) for region in regions],
    )
