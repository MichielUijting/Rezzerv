"""
Technical Design Reference:
- TD Section: TD-03 Receipt ingestion en parsers
- Module Role: Receipt source parsing and data extraction
- Runtime Type: production
- Used By: see docs/technical/PYTHON-MODULE-CATALOG.md
- Depends On: see generated inventory
- Reads Data: see generated inventory
- Writes Data: see generated inventory
- Status Authority: no
- Refactor Status: classify
"""

from __future__ import annotations

import io
import logging
import os
import re
import subprocess
import tempfile
from pathlib import Path
from statistics import median
from typing import Any

from app.receipt_ingestion.service_parts.ah_photo_bbox_article_reconstruction import apply_ah_photo_bbox_article_reconstruction
from app.receipt_ingestion.service_parts.generic_receipt_layout_reconstruction import apply_generic_receipt_layout_reconstruction
from app.receipt_ingestion.service_parts.plus_photo_line_grouping_fallback import apply_plus_photo_line_grouping_fallback
from app.receipt_ingestion.service_parts.plus_photo_preprocessed_fallback_ocr import guarded_plus_preprocessed_ocr_fallback
from app.receipt_ingestion.service_parts.text_extraction import _normalize_text_lines

try:
    from paddleocr import PaddleOCR
except Exception:  # pragma: no cover
    PaddleOCR = None

try:
    from PIL import Image
except Exception:  # pragma: no cover
    Image = None

LOGGER = logging.getLogger(__name__)
_PADDLE_OCR_INSTANCE = None
_LAST_PADDLE_BBOX_PAYLOAD: dict[str, dict[str, Any]] = {}


def get_last_paddle_bbox_payload(filename: str | None) -> dict[str, Any] | None:
    """Return last Paddle OCR texts/boxes captured for this filename.

    Runtime Type: internal cache.
    This does not run OCR and does not modify parser decisions.
    """
    if not filename:
        return None
    return _LAST_PADDLE_BBOX_PAYLOAD.get(str(filename))


_PLUS_IMAGE_EXTENSIONS = {'.jpg', '.jpeg', '.png', '.webp', '.bmp', '.tif', '.tiff'}
_PLUS_ROW_STOP_TOKENS = ('subtotaal', 'totaal', 'btw', 'pin', 'contactless', 'contactiess', 'transactie', 'wisselgeld')
_PLUS_ROW_DISCOUNT_TOKENS = ('actie', 'korting', 'voordeel', 'plus geeft')
_PLUS_AMOUNT_TOKEN_RE = re.compile(r'(?<!\d)(?:[€CE£]?-?\d{1,6}(?:[\.,]\s?\d{2})|0[\.,]\s?25)(?!\d)', re.IGNORECASE)
_PLUS_QTY_TOKEN_RE = re.compile(r'(?<![A-Za-z0-9])\d{1,3}\s*[xX]\b')


def _get_paddle_ocr():
    global _PADDLE_OCR_INSTANCE
    if _PADDLE_OCR_INSTANCE is not None:
        return _PADDLE_OCR_INSTANCE
    if PaddleOCR is None:
        return None

    constructors = [
        {
            'use_doc_orientation_classify': False,
            'use_doc_unwarping': False,
            'use_textline_orientation': False,
            'lang': 'en',
        },
        {
            'use_angle_cls': True,
            'lang': 'en',
        },
        {
            'lang': 'en',
        },
    ]
    for kwargs in constructors:
        try:
            _PADDLE_OCR_INSTANCE = PaddleOCR(**kwargs)
            break
        except TypeError:
            continue
        except Exception as exc:  # pragma: no cover - runtime dependency/model download issue
            LOGGER.warning('PaddleOCR initialisatie mislukt: %s', exc)
            return None
    return _PADDLE_OCR_INSTANCE


def _ocr_bbox_to_line_anchor(bbox: Any) -> tuple[float, float, float] | None:
    if bbox is None:
        return None
    try:
        if isinstance(bbox, (list, tuple)) and len(bbox) == 4 and not isinstance(bbox[0], (list, tuple)):
            x1, y1, x2, y2 = [float(v) for v in bbox]
            return ((y1 + y2) / 2.0, x1, max(1.0, y2 - y1))
        points = []
        for point in bbox:
            if not isinstance(point, (list, tuple)) or len(point) < 2:
                continue
            points.append((float(point[0]), float(point[1])))
        if not points:
            return None
        xs = [pt[0] for pt in points]
        ys = [pt[1] for pt in points]
        return ((min(ys) + max(ys)) / 2.0, min(xs), max(1.0, max(ys) - min(ys)))
    except Exception:
        return None


def _extract_payload_from_paddle_item(item: Any) -> dict[str, Any]:
    candidates: list[Any] = [item]
    for attr_name in ('res', 'json', 'result'):
        attr = getattr(item, attr_name, None)
        if attr is None:
            continue
        try:
            value = attr() if callable(attr) else attr
        except TypeError:
            value = attr
        candidates.append(value)
    to_dict = getattr(item, 'to_dict', None)
    if callable(to_dict):
        try:
            candidates.append(to_dict())
        except Exception:
            pass
    for candidate in candidates:
        if isinstance(candidate, dict):
            if isinstance(candidate.get('res'), dict):
                return candidate['res']
            return candidate
    return {}


def _group_paddle_texts_to_lines(texts: list[str], boxes: list[Any] | None) -> list[str]:
    if not texts:
        return []
    if not boxes or len(boxes) != len(texts):
        return [re.sub(r'\s+', ' ', text).strip() for text in texts if str(text).strip()]

    fragments: list[tuple[float, float, float, str]] = []
    heights: list[float] = []
    for text_value, box in zip(texts, boxes):
        normalized_text = re.sub(r'\s+', ' ', str(text_value or '')).strip()
        if not normalized_text:
            continue
        anchor = _ocr_bbox_to_line_anchor(box)
        if anchor is None:
            fragments.append((float(len(fragments) * 100), float(len(fragments)), 10.0, normalized_text))
            continue
        center_y, min_x, height = anchor
        heights.append(height)
        fragments.append((center_y, min_x, height, normalized_text))

    if not fragments:
        return []

    fragments.sort(key=lambda item: (item[0], item[1]))
    merge_threshold = max(12.0, (median(heights) if heights else 12.0) * 0.7)
    grouped: list[list[tuple[float, float, float, str]]] = []
    for fragment in fragments:
        if not grouped:
            grouped.append([fragment])
            continue
        current_group = grouped[-1]
        current_y = sum(part[0] for part in current_group) / len(current_group)
        if abs(fragment[0] - current_y) <= merge_threshold:
            current_group.append(fragment)
        else:
            grouped.append([fragment])

    result_lines: list[str] = []
    for group in grouped:
        group.sort(key=lambda item: item[1])
        merged = ' '.join(part[3] for part in group).strip()
        merged = re.sub(r'\s+', ' ', merged)
        if merged:
            result_lines.append(merged)
    return result_lines


def _normalize_paddle_collection(value: Any) -> list[Any]:
    if value is None:
        return []
    if hasattr(value, 'tolist'):
        try:
            value = value.tolist()
        except Exception:
            pass
    if isinstance(value, (str, bytes, bytearray)):
        return [value]
    try:
        return list(value)
    except TypeError:
        return [value]


def _is_plus_image_line_set(filename: str, lines: list[str]) -> bool:
    suffix = Path(filename or '').suffix.lower()
    if suffix not in _PLUS_IMAGE_EXTENSIONS:
        return False
    head = ' '.join(str(line or '').lower() for line in lines[:20])
    return 'plus' in head or 'pluspunten' in head or 'piuspunten' in head


def _clean_plus_amount_token(value: str) -> str:
    token = re.sub(r'\s+', '', str(value or '').strip())
    token = token.replace('£', '€')
    token = re.sub(r'^(?=[0-9])', '', token)
    return token


def _split_plus_parallel_qty_line(line: str) -> list[str] | None:
    normalized = re.sub(r'\b0[\.,]\s+25\b', '0,25', re.sub(r'\s+', ' ', str(line or '')).strip())
    lowered = normalized.lower()
    if any(token in lowered for token in _PLUS_ROW_STOP_TOKENS + _PLUS_ROW_DISCOUNT_TOKENS):
        return None
    amount_matches = list(_PLUS_AMOUNT_TOKEN_RE.finditer(normalized))
    if len(amount_matches) < 4:
        return None
    first_amount = amount_matches[0]
    label_part = normalized[:first_amount.start()].strip(' .:-')
    qty_matches = list(_PLUS_QTY_TOKEN_RE.finditer(label_part))
    if len(qty_matches) < 2:
        return None
    labels: list[str] = []
    for index, qty_match in enumerate(qty_matches):
        start = qty_match.start()
        end = qty_matches[index + 1].start() if index + 1 < len(qty_matches) else len(label_part)
        label = re.sub(r'\s+', ' ', label_part[start:end]).strip(' .:-')
        if label:
            labels.append(label)
    if len(labels) < 2:
        return None
    if len(amount_matches) < len(labels) * 2:
        return None
    amounts = [_clean_plus_amount_token(match.group(0)) for match in amount_matches]
    rows: list[str] = []
    for index, label in enumerate(labels):
        unit = amounts[index]
        total = amounts[index + len(labels)]
        rows.append(f'{label} {unit} {total}')
    return rows if len(rows) >= 2 else None


def _split_plus_statiegeld_line(line: str) -> list[str] | None:
    normalized = re.sub(r'\b0[\.,]\s+25\b', '0,25', re.sub(r'\s+', ' ', str(line or '')).strip())
    if 'statiegeld' not in normalized.lower():
        return None
    match = re.match(
        r'^(?P<label>.*?\b\d{1,3}\s*[xX]\b.*?)\s+'
        r'(?P<unit>[€CE£]?\d{1,6}[\.,]\d{2})\s+'
        r'Statiegeld\s+'
        r'(?P<total>[€CE£]?\d{1,6}[\.,]\d{2})\s+'
        r'(?P<deposit>[€CE£]?0[\.,]\d{2})$',
        normalized,
        flags=re.IGNORECASE,
    )
    if not match:
        return None
    label = re.sub(r'\s+', ' ', match.group('label')).strip(' .:-')
    if not label:
        return None
    return [
        f"{label} {_clean_plus_amount_token(match.group('unit'))} {_clean_plus_amount_token(match.group('total'))}",
        f"Statiegeld {_clean_plus_amount_token(match.group('deposit'))}",
    ]


def _apply_plus_merged_text_line_split(filename: str, lines: list[str]) -> list[str]:
    if not lines or not _is_plus_image_line_set(filename, lines):
        return lines
    expanded: list[str] = []
    changed = False
    for line in lines:
        split_rows = _split_plus_statiegeld_line(line) or _split_plus_parallel_qty_line(line)
        if split_rows:
            expanded.extend(split_rows)
            changed = True
        else:
            expanded.append(line)
    return expanded if changed else lines


def _ocr_image_text_with_paddle(file_bytes: bytes, filename: str) -> tuple[list[str], float | None]:
    model = _get_paddle_ocr()
    if model is None:
        return [], None

    suffix = Path(filename).suffix.lower() or '.png'
    try:
        with tempfile.TemporaryDirectory(prefix='rezzerv-paddleocr-') as temp_dir:
            image_path = Path(temp_dir) / f'image{suffix}'
            image_path.write_bytes(file_bytes)
            result = model.predict(str(image_path))
    except Exception as exc:  # pragma: no cover - runtime dependency/model download issue
        LOGGER.warning('PaddleOCR verwerking mislukt voor %s: %s', filename, exc)
        return [], None

    texts: list[str] = []
    scores: list[float] = []
    boxes: list[Any] = []
    for item in _normalize_paddle_collection(result):
        payload = _extract_payload_from_paddle_item(item)
        current_texts = _normalize_paddle_collection(payload.get('rec_texts') or payload.get('texts'))
        current_scores = _normalize_paddle_collection(payload.get('rec_scores') or payload.get('scores'))
        current_boxes = payload.get('rec_boxes')
        if current_boxes is None:
            current_boxes = payload.get('dt_polys')
        if current_boxes is None:
            current_boxes = payload.get('rec_polys')
        current_boxes = _normalize_paddle_collection(current_boxes)
        normalized_texts = [str(text) for text in current_texts if str(text).strip()]
        texts.extend(normalized_texts)
        for score in current_scores:
            try:
                scores.append(float(score))
            except (TypeError, ValueError):
                continue
        boxes.extend(current_boxes[: len(normalized_texts)])

    # PLUS-01L-c bbox payload cache:
    # Store Paddle texts/boxes so receipt_service can build a structured PLUS result
    # without running OCR again and without forcing bbox rows through text parsing.
    _LAST_PADDLE_BBOX_PAYLOAD[str(filename)] = {
        'texts': list(texts),
        'boxes': list(boxes),
    }

    line_candidates = _group_paddle_texts_to_lines(texts, boxes if boxes else None)
    line_candidates = _apply_plus_merged_text_line_split(filename, line_candidates)
    plus_fallback_lines = apply_plus_photo_line_grouping_fallback(
        filename=filename,
        texts=texts,
        boxes=boxes,
        current_lines=line_candidates,
    )
    if plus_fallback_lines is not None:
        line_candidates = plus_fallback_lines
    else:
        ah_bbox_lines = apply_ah_photo_bbox_article_reconstruction(
            filename=filename,
            texts=texts,
            boxes=boxes,
            current_lines=line_candidates,
        )
        if ah_bbox_lines is not None:
            line_candidates = ah_bbox_lines
        else:
            generic_layout_lines = apply_generic_receipt_layout_reconstruction(
                filename=filename,
                texts=texts,
                boxes=boxes,
                current_lines=line_candidates,
            )
            if generic_layout_lines is not None:
                line_candidates = generic_layout_lines
            else:
                preprocessed_result = guarded_plus_preprocessed_ocr_fallback(
                    model=model,
                    file_bytes=file_bytes,
                    filename=filename,
                    runtime_texts=texts,
                    runtime_boxes=boxes,
                    runtime_lines=line_candidates,
                )
                if preprocessed_result.get('fallback_lines'):
                    line_candidates = list(preprocessed_result['fallback_lines'])
                    pre_scores = preprocessed_result.get('preprocessed_scores') or []
                    if pre_scores:
                        scores = [float(score) for score in pre_scores]
    confidence = round(sum(scores) / len(scores), 4) if scores else None
    return line_candidates, confidence


def _ocr_image_text_with_tesseract(file_bytes: bytes, filename: str) -> tuple[list[str], float | None]:
    if Image is None:
        return [], None
    try:
        image = Image.open(io.BytesIO(file_bytes))
    except Exception:
        return [], None
    with tempfile.TemporaryDirectory(prefix='rezzerv-tesseract-') as temp_dir:
        image_path = Path(temp_dir) / 'receipt.png'
        image.save(image_path)
        base_path = Path(temp_dir) / 'out'
        cmd = [
            'tesseract',
            str(image_path),
            str(base_path),
            '-l',
            os.getenv('TESSERACT_LANG', 'nld+eng'),
            '--psm',
            '6',
            'tsv',
        ]
        try:
            subprocess.run(cmd, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=20)
        except Exception:
            return [], None
        tsv_path = base_path.with_suffix('.tsv')
        if not tsv_path.exists():
            return [], None
        rows = tsv_path.read_text(encoding='utf-8', errors='ignore').splitlines()

    grouped: dict[tuple[str, str, str], list[tuple[int, str]]] = {}
    confidences: list[float] = []
    for raw in rows[1:]:
        parts = raw.split('\t')
        if len(parts) < 12:
            continue
        conf_raw = parts[10]
        text = parts[11].strip()
        if not text:
            continue
        try:
            conf = float(conf_raw)
            if conf >= 0:
                confidences.append(conf / 100.0)
        except ValueError:
            pass
        key = (parts[1], parts[2], parts[4])
        try:
            left = int(parts[6])
        except ValueError:
            left = len(grouped.get(key, []))
        grouped.setdefault(key, []).append((left, text))

    lines: list[str] = []
    for key in sorted(grouped.keys(), key=lambda item: tuple(int(x) if str(x).isdigit() else 0 for x in item)):
        words = [text for _, text in sorted(grouped[key], key=lambda item: item[0])]
        line = re.sub(r'\s+', ' ', ' '.join(words)).strip()
        if line:
            lines.append(line)
    return lines, round(sum(confidences) / len(confidences), 4) if confidences else None


def warm_receipt_ocr_runtime() -> dict[str, bool]:
    """Best-effort warm-up for heavy OCR runtimes after backend startup.

    Keeps the existing lazy path intact: failures are reported but never block
    application startup.
    """
    paddle_ready = _get_paddle_ocr() is not None
    return {
        'paddle_ready': bool(paddle_ready),
        'tesseract_ready': Image is not None,
    }
