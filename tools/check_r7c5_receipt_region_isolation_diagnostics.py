from __future__ import annotations

import argparse
import csv
import json
import math
import tempfile
import zipfile
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

IMAGE_EXTENSIONS = {'.jpg', '.jpeg', '.png', '.webp'}
REQUIRED_REGISTRY_COLUMNS = {
    'canonical_fixture_id',
    'fixture_file',
    'store_slug',
    'baseline_receipt_id',
}


@dataclass(frozen=True)
class RegionCandidate:
    x: int
    y: int
    width: int
    height: int
    area_ratio: float
    aspect_ratio: float
    center_bias: float
    edge_touch: bool
    score: float


@dataclass(frozen=True)
class DiagnosticRow:
    canonical_fixture_id: str
    fixture_file: str
    store_slug: str
    image_width: int | None
    image_height: int | None
    candidate_regions_count: int
    primary_region_bbox: str
    primary_region_confidence: float
    multiple_receipt_regions_detected: bool
    edge_receipt_detected: bool
    diagnostic_only: bool
    status: str
    reason: str


def read_registry(path: Path) -> list[dict[str, str]]:
    with path.open('r', encoding='utf-8-sig', newline='') as handle:
        reader = csv.DictReader(handle)
        columns = set(reader.fieldnames or [])
        missing = REQUIRED_REGISTRY_COLUMNS - columns
        if missing:
            raise SystemExit(f'Missing required registry columns: {sorted(missing)}')
        return [dict(row) for row in reader]


def normalize_filename(value: str) -> str:
    text = str(value or '').strip().lower().replace('\\', '/')
    text = text.split('/')[-1]
    return ''.join(ch for ch in text if ch.isalnum())


def locate_fixture_file(fixture_name: str, fixture_dir: Path | None, fixture_zip: Path | None, tmp_dir: Path) -> Path | None:
    target = normalize_filename(fixture_name)

    if fixture_dir:
        for path in fixture_dir.rglob('*'):
            if path.is_file() and normalize_filename(path.name) == target:
                return path

    if fixture_zip:
        with zipfile.ZipFile(fixture_zip) as zf:
            for info in zf.infolist():
                if info.is_dir():
                    continue
                if normalize_filename(Path(info.filename).name) == target:
                    out = tmp_dir / Path(info.filename).name
                    out.write_bytes(zf.read(info))
                    return out
    return None


def import_cv2() -> Any:
    try:
        import cv2  # type: ignore
    except Exception as exc:  # pragma: no cover - local dependency guard
        raise SystemExit(
            'OpenCV is required for R7c-5 image diagnostics. Run this inside the backend container '
            'or install opencv-python in the local Python environment. Original error: ' + str(exc)
        )
    return cv2


def candidate_score(
    *,
    x: int,
    y: int,
    width: int,
    height: int,
    image_width: int,
    image_height: int,
) -> RegionCandidate:
    area = width * height
    area_ratio = area / max(1, image_width * image_height)
    aspect_ratio = height / max(1, width)
    region_center_x = x + width / 2
    region_center_y = y + height / 2
    dx = abs(region_center_x - image_width / 2) / max(1, image_width / 2)
    dy = abs(region_center_y - image_height / 2) / max(1, image_height / 2)
    center_bias = max(0.0, 1.0 - math.sqrt(dx * dx + dy * dy) / math.sqrt(2))
    edge_margin_x = max(8, int(image_width * 0.02))
    edge_margin_y = max(8, int(image_height * 0.02))
    edge_touch = x <= edge_margin_x or y <= edge_margin_y or x + width >= image_width - edge_margin_x or y + height >= image_height - edge_margin_y

    verticality = min(1.0, aspect_ratio / 2.0) if aspect_ratio >= 1.0 else aspect_ratio * 0.35
    size_score = min(1.0, area_ratio / 0.35)
    edge_penalty = 0.18 if edge_touch else 0.0
    score = max(0.0, min(1.0, (0.50 * size_score) + (0.30 * verticality) + (0.20 * center_bias) - edge_penalty))

    return RegionCandidate(
        x=x,
        y=y,
        width=width,
        height=height,
        area_ratio=round(area_ratio, 4),
        aspect_ratio=round(aspect_ratio, 4),
        center_bias=round(center_bias, 4),
        edge_touch=edge_touch,
        score=round(score, 4),
    )


def analyze_image(path: Path) -> tuple[int, int, list[RegionCandidate]]:
    cv2 = import_cv2()
    image = cv2.imread(str(path))
    if image is None:
        raise ValueError(f'Could not read image: {path}')
    image_height, image_width = image.shape[:2]

    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    blurred = cv2.GaussianBlur(gray, (5, 5), 0)
    edges = cv2.Canny(blurred, 50, 150)
    kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (15, 15))
    closed = cv2.morphologyEx(edges, cv2.MORPH_CLOSE, kernel, iterations=2)
    contours, _ = cv2.findContours(closed, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

    min_area_ratio = 0.025
    candidates: list[RegionCandidate] = []
    for contour in contours:
        x, y, width, height = cv2.boundingRect(contour)
        area_ratio = (width * height) / max(1, image_width * image_height)
        if area_ratio < min_area_ratio:
            continue
        if width < image_width * 0.12 or height < image_height * 0.12:
            continue
        candidates.append(candidate_score(x=x, y=y, width=width, height=height, image_width=image_width, image_height=image_height))

    candidates.sort(key=lambda item: item.score, reverse=True)
    return image_width, image_height, candidates[:8]


def bbox_text(candidate: RegionCandidate | None) -> str:
    if candidate is None:
        return ''
    return f'{candidate.x},{candidate.y},{candidate.width},{candidate.height}'


def diagnostic_from_candidates(row: dict[str, str], image_width: int, image_height: int, candidates: list[RegionCandidate]) -> DiagnosticRow:
    primary = candidates[0] if candidates else None
    strong_candidates = [candidate for candidate in candidates if candidate.score >= 0.42]
    edge_candidates = [candidate for candidate in strong_candidates if candidate.edge_touch]
    secondary_candidates = [candidate for candidate in strong_candidates[1:] if primary and candidate.score >= max(0.35, primary.score * 0.55)]
    multiple = len(strong_candidates) >= 2 or bool(edge_candidates and secondary_candidates)

    reason_parts: list[str] = []
    if multiple:
        reason_parts.append('multiple candidate receipt regions detected')
    if edge_candidates:
        reason_parts.append('candidate region touches image edge')
    if primary is None:
        reason_parts.append('no region candidate detected')
    if not reason_parts:
        reason_parts.append('single dominant candidate region')

    return DiagnosticRow(
        canonical_fixture_id=row['canonical_fixture_id'],
        fixture_file=row['fixture_file'],
        store_slug=row['store_slug'],
        image_width=image_width,
        image_height=image_height,
        candidate_regions_count=len(candidates),
        primary_region_bbox=bbox_text(primary),
        primary_region_confidence=primary.score if primary else 0.0,
        multiple_receipt_regions_detected=multiple,
        edge_receipt_detected=bool(edge_candidates),
        diagnostic_only=True,
        status='analyzed',
        reason='; '.join(reason_parts),
    )


def skipped_row(row: dict[str, str], reason: str) -> DiagnosticRow:
    return DiagnosticRow(
        canonical_fixture_id=row['canonical_fixture_id'],
        fixture_file=row['fixture_file'],
        store_slug=row['store_slug'],
        image_width=None,
        image_height=None,
        candidate_regions_count=0,
        primary_region_bbox='',
        primary_region_confidence=0.0,
        multiple_receipt_regions_detected=False,
        edge_receipt_detected=False,
        diagnostic_only=True,
        status='skipped',
        reason=reason,
    )


def main() -> int:
    parser = argparse.ArgumentParser(description='R7c-5 receipt region isolation diagnostics, supermarket-only')
    parser.add_argument('--registry', required=True, help='R7c-3 canonical supermarket registry CSV')
    parser.add_argument('--fixtures-dir', default='', help='Directory containing supermarket fixtures')
    parser.add_argument('--fixtures-zip', default='', help='ZIP containing supermarket fixtures')
    parser.add_argument('--json-out', default='', help='Optional diagnostics JSON output')
    parser.add_argument('--csv-out', default='', help='Optional diagnostics CSV output')
    args = parser.parse_args()

    registry = read_registry(Path(args.registry))
    fixture_dir = Path(args.fixtures_dir) if args.fixtures_dir else None
    fixture_zip = Path(args.fixtures_zip) if args.fixtures_zip else None
    if fixture_dir and not fixture_dir.exists():
        raise SystemExit(f'Missing fixtures dir: {fixture_dir}')
    if fixture_zip and not fixture_zip.exists():
        raise SystemExit(f'Missing fixtures ZIP: {fixture_zip}')
    if not fixture_dir and not fixture_zip:
        raise SystemExit('Provide --fixtures-dir or --fixtures-zip')

    diagnostics: list[DiagnosticRow] = []
    with tempfile.TemporaryDirectory(prefix='r7c5_regions_') as tmp:
        tmp_dir = Path(tmp)
        for row in registry:
            fixture_file = row['fixture_file']
            suffix = Path(fixture_file).suffix.lower()
            if suffix not in IMAGE_EXTENSIONS:
                diagnostics.append(skipped_row(row, f'unsupported for image diagnostics: {suffix or "no extension"}'))
                continue
            located = locate_fixture_file(fixture_file, fixture_dir, fixture_zip, tmp_dir)
            if located is None:
                diagnostics.append(skipped_row(row, 'fixture file not found'))
                continue
            try:
                image_width, image_height, candidates = analyze_image(located)
                diagnostics.append(diagnostic_from_candidates(row, image_width, image_height, candidates))
            except Exception as exc:
                diagnostics.append(skipped_row(row, f'image analysis failed: {exc}'))

    analyzed = [row for row in diagnostics if row.status == 'analyzed']
    multiple = [row for row in analyzed if row.multiple_receipt_regions_detected]
    edge = [row for row in analyzed if row.edge_receipt_detected]
    skipped = [row for row in diagnostics if row.status == 'skipped']

    output = {
        'diagnostic_only': True,
        'scope': 'supermarket',
        'registry_count': len(registry),
        'analyzed_count': len(analyzed),
        'skipped_count': len(skipped),
        'multiple_receipt_regions_count': len(multiple),
        'edge_receipt_detected_count': len(edge),
        'rows': [asdict(row) for row in diagnostics],
    }

    print('R7c-5 receipt region isolation diagnostics')
    print(f'- Registry fixtures: {len(registry)}')
    print(f'- Analyzed image fixtures: {len(analyzed)}')
    print(f'- Skipped fixtures: {len(skipped)}')
    print(f'- Multiple receipt regions detected: {len(multiple)}')
    print(f'- Edge receipt detected: {len(edge)}')
    if multiple:
        print('\nMultiple-region candidates:')
        for row in multiple:
            print(f'- {row.fixture_file}: confidence={row.primary_region_confidence}, bbox={row.primary_region_bbox}, reason={row.reason}')

    if args.json_out:
        path = Path(args.json_out)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(output, indent=2, ensure_ascii=False), encoding='utf-8')
        print(f'- JSON written: {path}')

    if args.csv_out:
        path = Path(args.csv_out)
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open('w', encoding='utf-8', newline='') as handle:
            fieldnames = list(asdict(diagnostics[0]).keys()) if diagnostics else list(DiagnosticRow.__dataclass_fields__.keys())
            writer = csv.DictWriter(handle, fieldnames=fieldnames)
            writer.writeheader()
            for row in diagnostics:
                writer.writerow(asdict(row))
        print(f'- CSV written: {path}')

    print('\nR7c-5 diagnostics completed. No parser, OCR, SSOT, or backend behavior was changed.')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
