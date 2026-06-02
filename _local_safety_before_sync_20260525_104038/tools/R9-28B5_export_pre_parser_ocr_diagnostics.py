from __future__ import annotations

import argparse
import json
import mimetypes
import os
import tempfile
import zipfile
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path
from typing import Any


# R9-28B5
# Expose existing pre-parser OCR lines and Paddle boxes as SSOT-safe diagnostics/export.
#
# Scope:
# - Diagnostic/export only
# - No parser mutation
# - No OCR engine mutation
# - No database mutation
# - No status determination
# - No UI mutation
# - No receipt_status_baseline_service_v4.py mutation
#
# Purpose:
# Make the existing in-memory OCR source layer visible:
# - Paddle raw text items
# - Paddle bounding boxes
# - Paddle grouped pre-parser OCR lines
# - Tesseract grouped OCR lines
# - Parser input candidate lines
#
# This tool intentionally calls existing receipt_service OCR helpers and writes
# a standalone JSON/MD report. It does not insert rows into Rezzerv tables and
# does not promote diagnostics into parser/status decisions.


IMAGE_SUFFIXES = {".jpg", ".jpeg", ".png", ".bmp", ".tif", ".tiff", ".webp"}


@dataclass
class OcrTextItem:
    index: int
    text: str
    confidence: float | None
    bbox: Any
    bbox_anchor: float | None


def _safe_float(value: Any) -> float | None:
    try:
        if value is None:
            return None
        return float(value)
    except Exception:
        return None


def _load_input(input_path: Path, member: str | None) -> tuple[bytes, str]:
    if not input_path.exists():
        raise FileNotFoundError(str(input_path))

    if zipfile.is_zipfile(input_path):
        with zipfile.ZipFile(input_path, "r") as archive:
            names = archive.namelist()
            if member:
                selected = member
            else:
                candidates = [
                    name for name in names
                    if Path(name).suffix.lower() in IMAGE_SUFFIXES and not name.endswith("/")
                ]
                if not candidates:
                    raise ValueError(f"Geen afbeeldingsbestand gevonden in zip: {input_path}")
                selected = candidates[0]
            return archive.read(selected), Path(selected).name

    return input_path.read_bytes(), input_path.name


def _write_bytes_for_ocr(data: bytes, filename: str) -> Path:
    suffix = Path(filename).suffix.lower() or ".png"
    tmp = tempfile.NamedTemporaryFile(prefix="rezzerv-r9-28b5-", suffix=suffix, delete=False)
    tmp.write(data)
    tmp.flush()
    tmp.close()
    return Path(tmp.name)


def _import_receipt_service():
    # Import private helpers from the existing service. This is deliberately
    # read-only/export-only and avoids changing runtime behavior.
    from app.services import receipt_service as svc  # type: ignore

    required = [
        "_get_paddle_ocr",
        "_extract_payload_from_paddle_item",
        "_normalize_paddle_collection",
        "_group_paddle_texts_to_lines",
        "_ocr_bbox_to_line_anchor",
        "_ocr_image_text_with_tesseract",
    ]
    missing = [name for name in required if not hasattr(svc, name)]
    if missing:
        raise RuntimeError(f"Ontbrekende receipt_service helper(s): {', '.join(missing)}")
    return svc


def _try_preprocess(data: bytes, filename: str) -> tuple[bytes, dict[str, Any]]:
    try:
        from app.receipt_ingestion.preprocessing.receipt_image_preprocessing import apply_receipt_image_preprocessing  # type: ignore

        result = apply_receipt_image_preprocessing(data, filename=filename)
        if isinstance(result, tuple):
            # Supported defensive forms:
            # (bytes, diagnostics) or (bytes, decision, diagnostics)
            if len(result) >= 2 and isinstance(result[0], (bytes, bytearray)):
                out = bytes(result[0])
                diag = {}
                if len(result) == 2:
                    diag = result[1] if isinstance(result[1], dict) else {"decision": repr(result[1])}
                elif len(result) >= 3:
                    diag = {
                        "decision": result[1] if isinstance(result[1], (str, int, float, bool, type(None))) else repr(result[1]),
                        "diagnostics": result[2] if isinstance(result[2], dict) else repr(result[2]),
                    }
                return out, {"preprocessing_available": True, "result_form": "tuple", **diag}
        if isinstance(result, (bytes, bytearray)):
            return bytes(result), {"preprocessing_available": True, "result_form": "bytes"}
    except Exception as exc:
        return data, {
            "preprocessing_available": False,
            "preprocessing_error": type(exc).__name__,
            "preprocessing_error_message": str(exc),
        }

    return data, {"preprocessing_available": True, "result_form": "unknown", "used_original_bytes": True}


def _collect_paddle_raw_items(svc: Any, data: bytes, filename: str) -> dict[str, Any]:
    model = svc._get_paddle_ocr()
    if model is None:
        return {
            "available": False,
            "error": "paddle_model_unavailable",
            "items": [],
            "grouped_lines": [],
            "raw_text_count": 0,
            "bbox_count": 0,
        }

    image_path = _write_bytes_for_ocr(data, filename)
    try:
        try:
            raw_result = model.ocr(str(image_path))
        except TypeError:
            raw_result = model.ocr(str(image_path), cls=True)
        except Exception as exc:
            return {
                "available": False,
                "error": type(exc).__name__,
                "error_message": str(exc),
                "items": [],
                "grouped_lines": [],
                "raw_text_count": 0,
                "bbox_count": 0,
            }

        texts: list[str] = []
        confidences: list[float | None] = []
        boxes: list[Any] = []

        # Prefer the exact helper stack from receipt_service where available.
        collections = []
        try:
            collections = svc._normalize_paddle_collection(raw_result)
        except Exception:
            collections = raw_result if isinstance(raw_result, list) else [raw_result]

        for collection in collections or []:
            if isinstance(collection, dict):
                # PaddleOCR v3/paddlex-like payloads sometimes expose rec_texts/rec_scores/rec_boxes.
                def _first_present(mapping, keys):
                    for key in keys:
                        value = mapping.get(key)
                        if value is not None:
                            return value
                    return []

                def _safe_len(value):
                    try:
                        return len(value)
                    except Exception:
                        return 0

                def _safe_index(value, idx):
                    try:
                        if value is None:
                            return None
                        if idx >= _safe_len(value):
                            return None
                        item = value[idx]
                        if hasattr(item, "tolist"):
                            return item.tolist()
                        return item
                    except Exception:
                        return None

                rec_texts = _first_present(collection, ["rec_texts", "texts"])
                rec_scores = _first_present(collection, ["rec_scores", "scores"])
                rec_boxes = _first_present(collection, ["rec_boxes", "boxes", "dt_polys"])

                if hasattr(rec_texts, "tolist"):
                    rec_texts = rec_texts.tolist()
                if hasattr(rec_scores, "tolist"):
                    rec_scores = rec_scores.tolist()
                if hasattr(rec_boxes, "tolist"):
                    rec_boxes = rec_boxes.tolist()

                for idx, text in enumerate(rec_texts or []):
                    value = str(text).strip()
                    if not value:
                        continue
                    texts.append(value)
                    confidences.append(_safe_float(_safe_index(rec_scores, idx)))
                    boxes.append(_safe_index(rec_boxes, idx))
                continue

            if not isinstance(collection, list):
                collection = [collection]

            for item in collection:
                try:
                    payload = svc._extract_payload_from_paddle_item(item)
                except Exception:
                    payload = None
                if not payload:
                    continue

                # Defensive payload handling: helper may return tuple-like or dict-like.
                if isinstance(payload, dict):
                    text_value = str(payload.get("text") or payload.get("label") or "").strip()
                    confidence = _safe_float(payload.get("confidence") or payload.get("score"))
                    box = payload.get("box") or payload.get("bbox")
                elif isinstance(payload, (list, tuple)):
                    text_value = str(payload[0] if len(payload) > 0 else "").strip()
                    confidence = _safe_float(payload[1] if len(payload) > 1 else None)
                    box = payload[2] if len(payload) > 2 else None
                else:
                    text_value = str(payload).strip()
                    confidence = None
                    box = None

                if text_value:
                    texts.append(text_value)
                    confidences.append(confidence)
                    boxes.append(box)

        grouped_lines = []
        try:
            grouped_lines = svc._group_paddle_texts_to_lines(texts, boxes if boxes else None)
        except Exception as exc:
            grouped_lines = []
            grouping_error = {"grouping_error": type(exc).__name__, "grouping_error_message": str(exc)}
        else:
            grouping_error = {}

        items = []
        for index, text in enumerate(texts):
            box = boxes[index] if index < len(boxes) else None
            try:
                anchor = svc._ocr_bbox_to_line_anchor(box) if box is not None else None
            except Exception:
                anchor = None
            items.append(asdict(OcrTextItem(
                index=index,
                text=text,
                confidence=confidences[index] if index < len(confidences) else None,
                bbox=box,
                bbox_anchor=anchor,
            )))

        return {
            "available": True,
            "raw_result_type": type(raw_result).__name__,
            "raw_text_count": len(texts),
            "bbox_count": len([b for b in boxes if b is not None]),
            "items": items,
            "grouped_lines": grouped_lines,
            "grouped_line_count": len(grouped_lines),
            **grouping_error,
        }
    finally:
        try:
            image_path.unlink(missing_ok=True)
        except Exception:
            pass


def _collect_tesseract_lines(svc: Any, data: bytes, filename: str) -> dict[str, Any]:
    try:
        lines, confidence = svc._ocr_image_text_with_tesseract(data, filename)
    except Exception as exc:
        return {
            "available": False,
            "error": type(exc).__name__,
            "error_message": str(exc),
            "lines": [],
            "line_count": 0,
            "confidence": None,
        }

    return {
        "available": True,
        "lines": lines or [],
        "line_count": len(lines or []),
        "confidence": confidence,
    }


def _choose_parser_input_candidate(paddle: dict[str, Any], tesseract: dict[str, Any]) -> dict[str, Any]:
    paddle_lines = paddle.get("grouped_lines") or []
    tesseract_lines = tesseract.get("lines") or []

    # Diagnostic only: this does not alter runtime parser choice.
    if len(paddle_lines) >= len(tesseract_lines) and paddle_lines:
        return {
            "diagnostic_choice": "paddle_grouped_lines",
            "lines": paddle_lines,
            "line_count": len(paddle_lines),
            "reason": "Paddle grouped lines are available and at least as numerous as Tesseract lines.",
        }
    if tesseract_lines:
        return {
            "diagnostic_choice": "tesseract_lines",
            "lines": tesseract_lines,
            "line_count": len(tesseract_lines),
            "reason": "Tesseract lines available; Paddle grouped lines unavailable or shorter.",
        }
    return {
        "diagnostic_choice": "none",
        "lines": [],
        "line_count": 0,
        "reason": "No OCR lines available from Paddle or Tesseract.",
    }


def build_report(input_path: Path, member: str | None, use_preprocessing: bool) -> dict[str, Any]:
    data, filename = _load_input(input_path, member)

    preprocessing = {"requested": use_preprocessing}
    ocr_data = data
    if use_preprocessing:
        ocr_data, preprocessing = _try_preprocess(data, filename)
        preprocessing["requested"] = True
    else:
        preprocessing["requested"] = False
        preprocessing["used_original_bytes"] = True

    svc = _import_receipt_service()
    paddle = _collect_paddle_raw_items(svc, ocr_data, filename)
    tesseract = _collect_tesseract_lines(svc, ocr_data, filename)
    parser_input_candidate = _choose_parser_input_candidate(paddle, tesseract)

    return {
        "audit": "R9-28B5 pre-parser OCR diagnostics export",
        "created_at": datetime.now().isoformat(timespec="seconds"),
        "scope": "diagnostic/export only; no parser/OCR/database/status/baseline/UI mutation",
        "ssot_compliance": {
            "status_determination": "not_performed",
            "status_service": "receipt_status_baseline_service_v4.py",
            "parse_status_used_as_truth": False,
            "parser_mutated": False,
            "ocr_mutated": False,
            "database_mutated": False,
            "baseline_mutated": False,
            "ui_touched": False,
            "diagnostics_promoted_to_parser": False,
        },
        "input": {
            "input_path": str(input_path),
            "zip_member": member,
            "filename": filename,
            "mime_type_guess": mimetypes.guess_type(filename)[0],
            "original_bytes": len(data),
            "ocr_bytes": len(ocr_data),
        },
        "preprocessing": preprocessing,
        "paddle": paddle,
        "tesseract": tesseract,
        "parser_input_candidate_for_diagnostics_only": parser_input_candidate,
        "next_step_hint": "Use this report for R9-28B6 AH section classification on true pre-parser OCR lines and Paddle boxes.",
    }


def render_markdown(report: dict[str, Any]) -> str:
    lines: list[str] = []
    lines.append("# R9-28B5 — Pre-parser OCR diagnostics export")
    lines.append("")
    lines.append(f"Gemaakt: `{report['created_at']}`")
    lines.append("")
    lines.append("## SSOT-compliance")
    lines.append("")
    for key, value in report["ssot_compliance"].items():
        lines.append(f"- `{key}`: `{value}`")
    lines.append("")
    lines.append("## Input")
    lines.append("")
    for key, value in report["input"].items():
        lines.append(f"- `{key}`: `{value}`")
    lines.append("")
    lines.append("## OCR-samenvatting")
    lines.append("")
    lines.append(f"- Paddle beschikbaar: `{report['paddle'].get('available')}`")
    lines.append(f"- Paddle raw text items: `{report['paddle'].get('raw_text_count')}`")
    lines.append(f"- Paddle bounding boxes: `{report['paddle'].get('bbox_count')}`")
    lines.append(f"- Paddle grouped lines: `{report['paddle'].get('grouped_line_count')}`")
    lines.append(f"- Tesseract beschikbaar: `{report['tesseract'].get('available')}`")
    lines.append(f"- Tesseract lines: `{report['tesseract'].get('line_count')}`")
    lines.append(f"- Diagnostische parser-input keuze: `{report['parser_input_candidate_for_diagnostics_only'].get('diagnostic_choice')}`")
    lines.append("")
    lines.append("## Paddle gegroepeerde regels")
    lines.append("")
    for idx, line in enumerate(report["paddle"].get("grouped_lines") or [], start=1):
        lines.append(f"{idx}. `{line}`")
    lines.append("")
    lines.append("## Tesseract regels")
    lines.append("")
    for idx, line in enumerate(report["tesseract"].get("lines") or [], start=1):
        lines.append(f"{idx}. `{line}`")
    lines.append("")
    lines.append("## Paddle raw items met boxes")
    lines.append("")
    for item in (report["paddle"].get("items") or [])[:200]:
        lines.append(f"- `{item.get('index')}` conf=`{item.get('confidence')}` anchor=`{item.get('bbox_anchor')}` text=`{item.get('text')}` bbox=`{item.get('bbox')}`")
    lines.append("")
    lines.append("## Vervolg")
    lines.append("")
    lines.append(report.get("next_step_hint", ""))
    lines.append("")
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("input", help="Image file or zip file")
    parser.add_argument("--member", default=None, help="Zip member name, e.g. 'AH foto 3.jpg'")
    parser.add_argument("--out", default="/tmp/R9-28B5_ocr_diagnostics", help="Output directory")
    parser.add_argument("--preprocess", action="store_true", help="Run existing receipt image preprocessing before OCR")
    args = parser.parse_args()

    input_path = Path(args.input)
    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)

    report = build_report(input_path, args.member, args.preprocess)

    safe_name = Path(report["input"]["filename"]).stem.replace(" ", "_").replace("/", "_").replace("\\", "_")
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    json_path = out_dir / f"R9-28B5_pre_parser_ocr_diagnostics_{safe_name}_{stamp}.json"
    md_path = out_dir / f"R9-28B5_pre_parser_ocr_diagnostics_{safe_name}_{stamp}.md"

    json_path.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    md_path.write_text(render_markdown(report), encoding="utf-8")

    print("R9-28B5 pre-parser OCR diagnostics export geschreven:")
    print(f"- {json_path}")
    print(f"- {md_path}")
    print("")
    print("SSOT: status_determination=not_performed parse_status_used_as_truth=False parser_mutated=False ocr_mutated=False database_mutated=False baseline_mutated=False ui_touched=False")
    print(f"paddle_available={report['paddle'].get('available')}")
    print(f"paddle_raw_text_count={report['paddle'].get('raw_text_count')}")
    print(f"paddle_bbox_count={report['paddle'].get('bbox_count')}")
    print(f"paddle_grouped_line_count={report['paddle'].get('grouped_line_count')}")
    print(f"tesseract_available={report['tesseract'].get('available')}")
    print(f"tesseract_line_count={report['tesseract'].get('line_count')}")
    print(f"diagnostic_parser_input_choice={report['parser_input_candidate_for_diagnostics_only'].get('diagnostic_choice')}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
