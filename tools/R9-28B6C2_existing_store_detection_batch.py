from __future__ import annotations

import argparse
import importlib
import inspect
import json
import re
import sys
import zipfile
from dataclasses import asdict, is_dataclass
from datetime import datetime
from pathlib import Path
from typing import Any


# R9-28B6C2
# Batch selection via existing Rezzerv receipt ingestion store detection.
#
# Scope:
# - Batch diagnostics only
# - Store/chain selection uses existing inleesproces/parser output
# - No filename-based chain classification
# - No newly invented AH content marker classifier
# - No receipt-specific rule introduction
# - No parser mutation
# - No OCR engine mutation
# - No database mutation
# - No status determination
# - No UI mutation
# - No receipt_status_baseline_service_v4.py mutation
#
# Purpose:
# Select AH receipts exactly through existing Rezzerv store-detection/parser
# behavior, then run the same diagnostic R9-28B5/R9-28B6 reconstruction on all
# receipts whose existing parser output identifies the store as Albert Heijn/AH.
#
# Important:
# This tool calls existing parser functions for classification only. It does not
# persist parse results and does not use parse_status as PO status.


IMAGE_SUFFIXES = {".jpg", ".jpeg", ".png", ".bmp", ".tif", ".tiff", ".webp"}


def _load_module(path: Path, name: str):
    if not path.exists():
        raise FileNotFoundError(f"Benodigd toolbestand ontbreekt: {path}")
    spec = importlib.util.spec_from_file_location(name, str(path))  # type: ignore[attr-defined]
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Kan module niet laden: {path}")
    module = importlib.util.module_from_spec(spec)  # type: ignore[attr-defined]
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


# importlib.util is not always imported by "import importlib" in older environments.
import importlib.util  # noqa: E402


def _all_image_members(zip_path: Path) -> list[str]:
    with zipfile.ZipFile(zip_path, "r") as z:
        return sorted([
            n for n in z.namelist()
            if not n.endswith("/") and Path(n).suffix.lower() in IMAGE_SUFFIXES
        ])


def _read_member(zip_path: Path, member: str) -> tuple[bytes, str]:
    with zipfile.ZipFile(zip_path, "r") as z:
        return z.read(member), Path(member).name


def _jsonable(value: Any, depth: int = 0) -> Any:
    if depth > 8:
        return repr(value)
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if is_dataclass(value):
        return _jsonable(asdict(value), depth + 1)
    if isinstance(value, dict):
        return {str(k): _jsonable(v, depth + 1) for k, v in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [_jsonable(v, depth + 1) for v in list(value)[:200]]
    if hasattr(value, "__dict__"):
        return _jsonable(vars(value), depth + 1)
    return repr(value)


def _deep_find_fields(value: Any, keys: set[str], depth: int = 0) -> dict[str, Any]:
    found: dict[str, Any] = {}
    if depth > 8 or value is None:
        return found
    if is_dataclass(value):
        value = asdict(value)
    elif hasattr(value, "__dict__") and not isinstance(value, (str, bytes, bytearray)):
        value = vars(value)

    if isinstance(value, dict):
        for k, v in value.items():
            lk = str(k).lower()
            if lk in keys and lk not in found:
                found[lk] = v
            nested = _deep_find_fields(v, keys, depth + 1)
            for nk, nv in nested.items():
                found.setdefault(nk, nv)
    elif isinstance(value, (list, tuple)):
        for item in value[:100]:
            nested = _deep_find_fields(item, keys, depth + 1)
            for nk, nv in nested.items():
                found.setdefault(nk, nv)
    return found


def _normalize_store_value(value: Any) -> str:
    if value is None:
        return ""
    return re.sub(r"\s+", " ", str(value).strip()).lower()


def _is_existing_parser_ah_detection(fields: dict[str, Any]) -> bool:
    # This is not OCR-content detection. It only evaluates store fields that came
    # back from the existing parser/inleesproces.
    store_values = [
        fields.get("store_name"),
        fields.get("store_chain"),
        fields.get("store"),
        fields.get("retailer"),
        fields.get("chain"),
        fields.get("merchant"),
        fields.get("shop_name"),
    ]
    normalized = " | ".join(_normalize_store_value(v) for v in store_values if v is not None)
    if not normalized:
        return False
    return bool(
        re.search(r"\balbert\s+hei[jin]{1,2}\b", normalized)
        or re.search(r"\bah\b", normalized)
        or "ah to go" in normalized
    )


def _call_existing_parse_receipt_content(data: bytes, filename: str) -> dict[str, Any]:
    svc = importlib.import_module("app.services.receipt_service")
    if not hasattr(svc, "parse_receipt_content"):
        raise RuntimeError("app.services.receipt_service.parse_receipt_content ontbreekt")

    fn = svc.parse_receipt_content
    sig = inspect.signature(fn)

    attempts: list[tuple[str, Any]] = []
    last_error: str | None = None

    # Build cautious call attempts based on common Rezzerv patterns.
    candidates = [
        ("bytes_filename_kwargs", lambda: fn(data, filename=filename)),
        ("bytes_filename_positional", lambda: fn(data, filename)),
        ("bytes_only", lambda: fn(data)),
        ("content_filename_kwargs", lambda: fn(content=data, filename=filename)),
        ("file_bytes_filename_kwargs", lambda: fn(file_bytes=data, filename=filename)),
        ("raw_bytes_filename_kwargs", lambda: fn(raw_bytes=data, filename=filename)),
    ]

    for label, caller in candidates:
        try:
            result = caller()
            return {
                "call_style": label,
                "signature": str(sig),
                "ok": True,
                "result": result,
                "result_jsonable": _jsonable(result),
            }
        except TypeError as exc:
            last_error = f"{label}: {exc}"
            attempts.append((label, str(exc)))
            continue
        except Exception as exc:
            # If the function was entered but OCR/parser failed for a receipt,
            # keep this as the actual existing parser outcome.
            return {
                "call_style": label,
                "signature": str(sig),
                "ok": False,
                "error_type": type(exc).__name__,
                "error_message": str(exc),
                "attempts": attempts,
            }

    return {
        "call_style": None,
        "signature": str(sig),
        "ok": False,
        "error_type": "NoCompatibleCallStyle",
        "error_message": last_error or "Geen compatible call-style gevonden",
        "attempts": attempts,
    }


def _store_detection_from_existing_parser(parse_call: dict[str, Any]) -> dict[str, Any]:
    if not parse_call.get("ok"):
        return {
            "source": "existing_parse_receipt_content",
            "is_ah": False,
            "store_chain_detected": None,
            "store_fields": {},
            "parse_call_ok": False,
            "parse_call_error": parse_call.get("error_message"),
            "rule_id": "EXISTING_REZZERV_STORE_DETECTION_ONLY",
            "reason": "Bestaande parser-call faalde; geen eigen OCR-marker fallback toegepast.",
        }

    result = parse_call.get("result")
    fields = _deep_find_fields(result, {
        "store_name", "store_chain", "store", "retailer", "chain", "merchant", "shop_name",
        "store_id", "store_slug", "source_store_name",
    })
    is_ah = _is_existing_parser_ah_detection(fields)
    store_chain = fields.get("store_chain") or fields.get("chain") or fields.get("retailer") or fields.get("store_name") or fields.get("store")

    return {
        "source": "existing_parse_receipt_content",
        "is_ah": is_ah,
        "store_chain_detected": store_chain,
        "store_fields": _jsonable(fields),
        "parse_call_ok": True,
        "parse_call_style": parse_call.get("call_style"),
        "parse_signature": parse_call.get("signature"),
        "rule_id": "EXISTING_REZZERV_STORE_DETECTION_ONLY",
        "reason": "AH-selectie gebaseerd op bestaande parser/storevelden, niet op bestandsnaam en niet op nieuwe OCR-markerregels.",
    }


def _safe_stem(name: str) -> str:
    return re.sub(r"[^A-Za-z0-9_.-]+", "_", Path(name).stem)


def _summarize(member: str, detection: dict[str, Any], b5_report: dict[str, Any], b6_report: dict[str, Any] | None, parse_call: dict[str, Any]) -> dict[str, Any]:
    if b6_report is None:
        return {
            "member": member,
            "store_detection": detection,
            "parse_call_summary": {
                "ok": parse_call.get("ok"),
                "call_style": parse_call.get("call_style"),
                "error_type": parse_call.get("error_type"),
                "error_message": parse_call.get("error_message"),
            },
            "ocr_summary": {
                "paddle_available": b5_report.get("paddle", {}).get("available"),
                "paddle_raw_text_count": b5_report.get("paddle", {}).get("raw_text_count"),
                "paddle_bbox_count": b5_report.get("paddle", {}).get("bbox_count"),
                "paddle_grouped_line_count": b5_report.get("paddle", {}).get("grouped_line_count"),
                "tesseract_line_count": b5_report.get("tesseract", {}).get("line_count"),
            },
            "selected_for_ah_reconstruction": False,
            "reconstructed_article_count": 0,
            "reconstructed_article_sum": 0,
            "reconstructed_articles": [],
            "suspicious_findings": [],
            "suspicious_finding_count": 0,
            "pass_batch_diagnostic": None,
        }

    articles = b6_report.get("reconstructed_articles", []) or []
    suspicious = []
    for a in articles:
        name = str(a.get("article_name") or "")
        amount = a.get("amount")
        amount_text = str(a.get("amount_text") or "")
        if not name.strip():
            suspicious.append({"type": "empty_article_name", "article": a})
        if amount is None:
            suspicious.append({"type": "missing_amount", "article": a})
        if re.search(r"\b(totaal|subtotaal|betalen|pin|nfc|chip|btw|over|terminal|transactie)\b", name, re.IGNORECASE):
            suspicious.append({"type": "non_article_term_in_article_name", "article": a})
        if amount_text in {"0,00", "0.00"}:
            suspicious.append({"type": "zero_amount_article_candidate", "article": a})

    return {
        "member": member,
        "store_detection": detection,
        "parse_call_summary": {
            "ok": parse_call.get("ok"),
            "call_style": parse_call.get("call_style"),
            "error_type": parse_call.get("error_type"),
            "error_message": parse_call.get("error_message"),
        },
        "ocr_summary": {
            "paddle_available": b5_report.get("paddle", {}).get("available"),
            "paddle_raw_text_count": b5_report.get("paddle", {}).get("raw_text_count"),
            "paddle_bbox_count": b5_report.get("paddle", {}).get("bbox_count"),
            "paddle_grouped_line_count": b5_report.get("paddle", {}).get("grouped_line_count"),
            "tesseract_line_count": b5_report.get("tesseract", {}).get("line_count"),
        },
        "selected_for_ah_reconstruction": True,
        "reconstruction_summary": b6_report.get("summary", {}),
        "reconstructed_article_count": len(articles),
        "reconstructed_article_sum": round(sum(float(a.get("amount") or 0) for a in articles), 2),
        "reconstructed_articles": articles,
        "suspicious_findings": suspicious,
        "suspicious_finding_count": len(suspicious),
        "pass_batch_diagnostic": len(articles) > 0 and len(suspicious) == 0,
    }


def _aggregate(items: list[dict[str, Any]], expected_ah_count: int | None) -> dict[str, Any]:
    selected = [i for i in items if i.get("selected_for_ah_reconstruction")]
    failure_types: dict[str, int] = {}
    for item in selected:
        for finding in item.get("suspicious_findings", []) or []:
            kind = finding.get("type", "unknown")
            failure_types[kind] = failure_types.get(kind, 0) + 1

    selection_pass = True if expected_ah_count is None else len(selected) == expected_ah_count
    if not selection_pass:
        failure_types["existing_parser_ah_selection_count_mismatch"] = 1

    return {
        "image_member_count": len(items),
        "ah_member_count_detected_by_existing_parser": len(selected),
        "expected_ah_count": expected_ah_count,
        "selection_pass": selection_pass,
        "passed_count": sum(1 for item in selected if item.get("pass_batch_diagnostic")),
        "failed_or_suspicious_count": sum(1 for item in selected if not item.get("pass_batch_diagnostic")),
        "failure_types": failure_types,
        "total_reconstructed_articles": sum(int(item.get("reconstructed_article_count") or 0) for item in selected),
    }


def build_report(zip_path: Path, out_dir: Path, preprocess: bool, expected_ah_count: int | None) -> dict[str, Any]:
    root = Path.cwd()
    b5 = _load_module(root / "tools/R9-28B5_export_pre_parser_ocr_diagnostics.py", "r9_28b5_export_pre_parser_ocr_diagnostics")
    b6 = _load_module(root / "tools/R9-28B6_ah_paddle_box_reconstruction.py", "r9_28b6_ah_paddle_box_reconstruction")

    members = _all_image_members(zip_path)
    per_member_dir = out_dir / "per_member"
    per_member_dir.mkdir(parents=True, exist_ok=True)

    summaries: list[dict[str, Any]] = []

    for member in members:
        safe = _safe_stem(member)
        member_dir = per_member_dir / safe
        member_dir.mkdir(parents=True, exist_ok=True)

        data, filename = _read_member(zip_path, member)

        # Existing inleesproces/parser is the only source for store/chain selection.
        parse_call = _call_existing_parse_receipt_content(data, filename)
        detection = _store_detection_from_existing_parser(parse_call)

        parse_json = {
            "member": member,
            "filename": filename,
            "store_detection": detection,
            "parse_call": {
                k: v for k, v in parse_call.items()
                if k != "result"  # keep JSON size manageable
            },
            "parse_result_jsonable": parse_call.get("result_jsonable"),
        }
        (member_dir / f"existing_parser_store_detection_{safe}.json").write_text(
            json.dumps(parse_json, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )

        # R9-28B5 remains diagnostic source export; it is not used for chain selection.
        b5_report = b5.build_report(zip_path, member, preprocess)
        b5_json = member_dir / f"R9-28B5_{safe}.json"
        b5_md = member_dir / f"R9-28B5_{safe}.md"
        b5_json.write_text(json.dumps(b5_report, indent=2, ensure_ascii=False), encoding="utf-8")
        b5_md.write_text(b5.render_markdown(b5_report), encoding="utf-8")

        if detection["is_ah"]:
            b6_report = b6.build_report(b5_json)
            b6_json = member_dir / f"R9-28B6_{safe}.json"
            b6_md = member_dir / f"R9-28B6_{safe}.md"
            b6_json.write_text(json.dumps(b6_report, indent=2, ensure_ascii=False), encoding="utf-8")
            b6_md.write_text(b6.render_md(b6_report), encoding="utf-8")
        else:
            b6_report = None

        summaries.append(_summarize(member, detection, b5_report, b6_report, parse_call))

    aggregate = _aggregate(summaries, expected_ah_count)

    return {
        "audit": "R9-28B6C2 existing parser store detection batch selection",
        "created_at": datetime.now().isoformat(timespec="seconds"),
        "scope": "batch diagnostics only; store selection via existing inleesproces/parser; no filename/OCR-marker AH classifier; no parser/OCR/database/status/baseline/UI mutation",
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
        "guardrails": {
            "existing_store_detection_used": True,
            "filename_based_chain_classification_allowed": False,
            "new_ocr_marker_chain_classifier_allowed": False,
            "filename_specific_parser_rules_allowed": False,
            "member_specific_rules_allowed": False,
            "hardcoded_receipt_ids_allowed": False,
            "selection_method": "existing app receipt parser/store-detection output from parse_receipt_content",
            "note": "Filenames are used only as zip member handles for loading files, never to decide store chain or parser behavior.",
        },
        "input": {
            "zip_path": str(zip_path),
            "preprocess_for_b5_diagnostics": preprocess,
            "expected_ah_count": expected_ah_count,
        },
        "aggregate": aggregate,
        "members": summaries,
        "next_step_hint": "If existing parser does not detect all 4 AH receipts, fix/reuse the existing store-detection path first. Do not build separate AH selection logic.",
    }


def render_markdown(report: dict[str, Any]) -> str:
    lines = [
        "# R9-28B6C2 — AH-selectie via bestaande winkelherkenning",
        "",
        f"Gemaakt: `{report['created_at']}`",
        "",
        "## SSOT-compliance",
        "",
    ]
    for k, v in report["ssot_compliance"].items():
        lines.append(f"- `{k}`: `{v}`")

    lines += [
        "",
        "## Guardrails",
        "",
    ]
    for k, v in report["guardrails"].items():
        lines.append(f"- `{k}`: `{v}`")

    lines += [
        "",
        "## Batchsamenvatting",
        "",
    ]
    for k, v in report["aggregate"].items():
        lines.append(f"- `{k}`: `{v}`")

    lines += [
        "",
        "## Bestaande winkelherkenning per image-member",
        "",
        "| Member | Geselecteerd als AH | Store/chain uit bestaande parser | Parse ok | Call style | OCR items | Boxes |",
        "|---|---:|---|---:|---|---:|---:|",
    ]
    for m in report["members"]:
        d = m["store_detection"]
        p = m["parse_call_summary"]
        o = m["ocr_summary"]
        lines.append(
            f"| `{m['member']}` | `{d.get('is_ah')}` | `{d.get('store_chain_detected')}` | "
            f"`{p.get('ok')}` | `{p.get('call_style')}` | `{o.get('paddle_raw_text_count')}` | `{o.get('paddle_bbox_count')}` |"
        )

    selected = [m for m in report["members"] if m.get("selected_for_ah_reconstruction")]
    lines += [
        "",
        "## Gereconstrueerde AH-artikelen per door bestaande parser herkende AH-bon",
        "",
    ]
    for m in selected:
        lines.append(f"### `{m['member']}`")
        for a in m["reconstructed_articles"]:
            lines.append(f"- `{a.get('article_name')}` — `{a.get('amount_text')}`")
        if m["suspicious_findings"]:
            lines.append("")
            lines.append("Suspicious findings:")
            for f in m["suspicious_findings"]:
                lines.append(f"- `{f.get('type')}`")
        lines.append("")

    lines += [
        "## Vervolg",
        "",
        report["next_step_hint"],
        "",
    ]
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("zip_path")
    parser.add_argument("--out", default="/tmp/R9-28B6C2_existing_store_batch")
    parser.add_argument("--expected-ah-count", type=int, default=4)
    parser.add_argument("--preprocess", action="store_true")
    args = parser.parse_args()

    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)

    report = build_report(
        zip_path=Path(args.zip_path),
        out_dir=out_dir,
        preprocess=args.preprocess,
        expected_ah_count=args.expected_ah_count,
    )

    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    json_path = out_dir / f"R9-28B6C2_existing_store_detection_batch_{stamp}.json"
    md_path = out_dir / f"R9-28B6C2_existing_store_detection_batch_{stamp}.md"
    json_path.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    md_path.write_text(render_markdown(report), encoding="utf-8")

    print("R9-28B6C2 existing parser store-detection batch geschreven:")
    print(f"- {json_path}")
    print(f"- {md_path}")
    print("SSOT: no parser/OCR/database/status/baseline/UI mutation")
    print("Guardrail: AH selection from existing parse_receipt_content/store detection only")
    print(f"image_member_count={report['aggregate']['image_member_count']}")
    print(f"ah_member_count_detected_by_existing_parser={report['aggregate']['ah_member_count_detected_by_existing_parser']}")
    print(f"expected_ah_count={report['aggregate']['expected_ah_count']}")
    print(f"selection_pass={report['aggregate']['selection_pass']}")
    print(f"passed_count={report['aggregate']['passed_count']}")
    print(f"failed_or_suspicious_count={report['aggregate']['failed_or_suspicious_count']}")
    print(f"failure_types={report['aggregate']['failure_types']}")
    if not report["aggregate"]["selection_pass"]:
        raise SystemExit(2)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
