from ...services import receipt_service as _svc
from ...services.receipt_service import *

import os
import re
from pathlib import Path
from typing import Any

from sqlalchemy import text

from .image.receipt_photo_normalizer import ReceiptPhotoNormalizer

# Feature flag
RECEIPT_PHOTO_NORMALIZATION_ENABLED = str(os.getenv("RECEIPT_PHOTO_NORMALIZATION_ENABLED", "true")).lower() in {"1", "true", "yes", "on"}

_normalizer = ReceiptPhotoNormalizer()
_original_parse = _svc.parse_receipt_content
_original_ingest = _svc.ingest_receipt

_AMOUNT_PATTERN = re.compile(r"(-?\d{1,6}(?:[\.,]\d{2}))")
_NON_ARTICLE_MARKERS = {
    "totaal", "subtotaal", "subtotal", "te betalen", "betaling", "betaald", "pin", "pinnen",
    "contant", "wisselgeld", "btw", "bonnr", "transactie", "terminal", "autorisatie", "kaart",
    "datum", "tijd", "saldo", "statiegeld", "zegels", "spaarzegels",
}


def _as_bytes(value: Any) -> bytes:
    if isinstance(value, bytes):
        return value
    if isinstance(value, bytearray):
        return bytes(value)
    return b""


def _parse_call_context(args: tuple[Any, ...], kwargs: dict[str, Any]) -> tuple[bytes, str, str]:
    file_bytes = _as_bytes(args[0]) if len(args) >= 1 else _as_bytes(kwargs.get("file_bytes") or kwargs.get("payload") or kwargs.get("content"))
    filename = str(args[1] if len(args) >= 2 else kwargs.get("filename") or kwargs.get("file_name") or kwargs.get("original_filename") or "receipt")
    mime_type = str(args[2] if len(args) >= 3 else kwargs.get("mime_type") or _svc.detect_mime_type(filename, file_bytes))
    return file_bytes, filename, mime_type


def _extract_ingest_context(args: tuple[Any, ...], kwargs: dict[str, Any]) -> tuple[Any, bytes, str, str]:
    engine = kwargs.get("engine")
    for arg in args:
        if hasattr(arg, "begin"):
            engine = arg
            break
    file_bytes = b""
    filename = str(kwargs.get("filename") or kwargs.get("file_name") or kwargs.get("original_filename") or "receipt")
    mime_type = str(kwargs.get("mime_type") or "")
    for arg in args:
        if isinstance(arg, (bytes, bytearray)) and not file_bytes:
            file_bytes = _as_bytes(arg)
        elif isinstance(arg, str) and filename == "receipt" and any(arg.lower().endswith(ext) for ext in _svc.SUPPORTED_EXTENSIONS):
            filename = arg
        elif isinstance(arg, str) and "/" in arg and not mime_type:
            mime_type = arg
    if not mime_type:
        mime_type = _svc.detect_mime_type(filename, file_bytes)
    return engine, file_bytes, filename, mime_type


def _extract_text_lines(file_bytes: bytes, filename: str, mime_type: str) -> list[str]:
    suffix = Path(filename).suffix.lower()
    try:
        if mime_type == "application/pdf" or suffix == ".pdf":
            text_value = _svc._preprocess_pdf_text(_svc._extract_pdf_text(file_bytes))
            return _svc._normalize_text_lines(text_value)
        if mime_type.startswith("image/") or suffix in {".png", ".jpg", ".jpeg", ".webp"}:
            lines, _ = _svc._ocr_image_text_with_paddle(file_bytes, filename)
            if not lines:
                lines, _ = _svc._ocr_image_text_with_tesseract(file_bytes, filename)
            return [str(line).strip() for line in lines if str(line).strip()]
        text_value = file_bytes.decode("utf-8", errors="ignore")
        if mime_type == "text/html" or suffix in {".html", ".htm"}:
            text_value = _svc._html_to_text(text_value)
        return _svc._normalize_text_lines(text_value)
    except Exception:
        return []


def _clean_candidate_label(value: str) -> str:
    cleaned = re.sub(r"\s+", " ", str(value or "")).strip(" -:\t")
    cleaned = re.sub(r"(?i)\b(?:eur|euro)\b", "", cleaned).strip(" -:\t")
    return re.sub(r"\s+", " ", cleaned).strip(" -:\t")[:180]


def _normalize_label(value: str) -> str:
    helper = getattr(_svc, "normalize_household_article_name", None)
    try:
        if helper:
            normalized = helper(value)
            if normalized:
                return str(normalized)[:180]
    except Exception:
        pass
    return re.sub(r"\s+", " ", str(value or "").strip()).lower()[:180]


def _is_probable_article_line(raw_line: str, label: str) -> bool:
    lowered = raw_line.lower()
    normalized_label = re.sub(r"[^a-z0-9]+", "", label.lower())
    if not label or len(label) < 2:
        return False
    if not re.search(r"[A-Za-zÀ-ÿ]", label):
        return False
    if any(marker in lowered for marker in _NON_ARTICLE_MARKERS):
        return False
    if normalized_label.isdigit():
        return False
    return True


def _line_candidates_from_text(lines: list[str]) -> list[dict[str, Any]]:
    candidates: list[dict[str, Any]] = []
    for index, raw_line in enumerate(lines):
        line = re.sub(r"\s+", " ", str(raw_line or "")).strip()
        matches = list(_AMOUNT_PATTERN.finditer(line))
        if not matches:
            continue
        match = matches[-1]
        amount = _svc._parse_decimal(match.group(1))
        if amount is None:
            continue
        label = _clean_candidate_label(line[: match.start()])
        if not _is_probable_article_line(line, label):
            continue
        candidates.append({
            "source_index": index,
            "raw_line": line,
            "raw_label": label,
            "normalized_label": _normalize_label(label),
            "line_total": amount,
        })
    return candidates


def _line_amount(line: dict[str, Any]):
    for key in ("line_total", "unit_price"):
        value = line.get(key)
        if value is None or value == "":
            continue
        parsed = _svc._parse_decimal(str(value))
        if parsed is not None:
            return parsed
    return None


def _choose_label_candidate(line: dict[str, Any], candidates: list[dict[str, Any]], used: set[int]) -> tuple[int | None, dict[str, Any] | None]:
    target_amount = _line_amount(line)
    if target_amount is not None:
        for idx, candidate in enumerate(candidates):
            if idx not in used and candidate.get("line_total") == target_amount:
                return idx, candidate
    for idx, candidate in enumerate(candidates):
        if idx not in used:
            return idx, candidate
    return None, None


def _enrich_parse_result_labels(parsed: Any, file_bytes: bytes, filename: str, mime_type: str):
    lines = getattr(parsed, "lines", None)
    if not lines:
        return parsed
    if any(str(line.get("raw_label") or line.get("normalized_label") or "").strip() for line in lines if isinstance(line, dict)):
        return parsed
    candidates = _line_candidates_from_text(_extract_text_lines(file_bytes, filename, mime_type))
    if not candidates:
        return parsed
    used: set[int] = set()
    for line in lines:
        if not isinstance(line, dict) or str(line.get("raw_label") or line.get("normalized_label") or "").strip():
            continue
        idx, candidate = _choose_label_candidate(line, candidates, used)
        if candidate is None or idx is None:
            continue
        used.add(idx)
        line["raw_label"] = candidate["raw_label"]
        line["normalized_label"] = candidate["normalized_label"]
        line.setdefault("source_text", candidate["raw_line"])
    return parsed


def _extract_receipt_table_id(value: Any) -> str | None:
    if isinstance(value, dict):
        for key in ("receipt_table_id", "id"):
            if key in value and value.get(key):
                return str(value.get(key))
        for child in value.values():
            found = _extract_receipt_table_id(child)
            if found:
                return found
    if isinstance(value, (list, tuple)):
        for child in value:
            found = _extract_receipt_table_id(child)
            if found:
                return found
    return None


def _persist_line_labels(engine: Any, receipt_table_id: str | None, file_bytes: bytes, filename: str, mime_type: str) -> None:
    if engine is None or not receipt_table_id or not file_bytes:
        return
    candidates = _line_candidates_from_text(_extract_text_lines(file_bytes, filename, mime_type))
    if not candidates:
        return
    with engine.begin() as conn:
        rows = conn.execute(text("""
            SELECT id, raw_label, normalized_label, line_total, unit_price
            FROM receipt_table_lines
            WHERE receipt_table_id = :receipt_table_id
              AND COALESCE(is_deleted, 0) = 0
            ORDER BY line_index ASC, created_at ASC, id ASC
        """), {"receipt_table_id": receipt_table_id}).mappings().all()
        used: set[int] = set()
        for row in rows:
            if str(row.get("raw_label") or row.get("normalized_label") or "").strip():
                continue
            idx, candidate = _choose_label_candidate(dict(row), candidates, used)
            if candidate is None or idx is None:
                continue
            used.add(idx)
            conn.execute(text("""
                UPDATE receipt_table_lines
                SET raw_label = :raw_label,
                    normalized_label = :normalized_label,
                    corrected_raw_label = COALESCE(corrected_raw_label, :raw_label),
                    updated_at = CURRENT_TIMESTAMP
                WHERE id = :line_id
            """), {
                "line_id": row["id"],
                "raw_label": candidate["raw_label"],
                "normalized_label": candidate["normalized_label"],
            })


def parse_receipt_content(*args, **kwargs):
    file_bytes, filename, mime_type = _parse_call_context(args, kwargs)
    try:
        if RECEIPT_PHOTO_NORMALIZATION_ENABLED:
            image_path = kwargs.get("image_path") or kwargs.get("file_path")
            if image_path:
                result = _normalizer.normalize(image_path, kwargs.get("mime_type") or mime_type)
                if result.success and result.ocr_ready_path:
                    kwargs["image_path"] = result.ocr_ready_path
        parsed = _original_parse(*args, **kwargs)
    except Exception:
        parsed = _original_parse(*args, **kwargs)
    return _enrich_parse_result_labels(parsed, file_bytes, filename, mime_type)


def ingest_receipt(*args, **kwargs):
    engine, file_bytes, filename, mime_type = _extract_ingest_context(args, kwargs)
    result = _original_ingest(*args, **kwargs)
    try:
        _persist_line_labels(engine, _extract_receipt_table_id(result), file_bytes, filename, mime_type)
    except Exception:
        pass
    return result


# monkey patch legacy service module
_svc.parse_receipt_content = parse_receipt_content
_svc.ingest_receipt = ingest_receipt
