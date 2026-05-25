from __future__ import annotations

import argparse
import gc
import importlib
import importlib.util
import inspect
import json
import re
import sys
import zipfile
from dataclasses import asdict, is_dataclass
from datetime import datetime
from pathlib import Path
from typing import Any


# R9-28B6C3
# Resource-safe batch selection via existing Rezzerv receipt ingestion store detection.
#
# Difference from R9-28B6C2:
# - First pass: all image members are classified by the existing inleesproces/store detection.
# - Heavy R9-28B5/R9-28B6 OCR diagnostics run ONLY for members that the existing parser detects as AH.
# - Optional --max-selected-diagnostics to limit OCR diagnostics during resource checks.
#
# Still forbidden:
# - filename-based store classification
# - new OCR marker AH classifier
# - receipt-specific parser rules
# - parser mutation
# - OCR engine mutation
# - database mutation
# - status determination
# - UI mutation
# - receipt_status_baseline_service_v4.py mutation


IMAGE_SUFFIXES = {".jpg", ".jpeg", ".png", ".bmp", ".tif", ".tiff", ".webp"}


def _load_module(path: Path, name: str):
    if not path.exists():
        raise FileNotFoundError(f"Benodigd toolbestand ontbreekt: {path}")
    spec = importlib.util.spec_from_file_location(name, str(path))
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Kan module niet laden: {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


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
    if depth > 6:
        return repr(value)
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if is_dataclass(value):
        return _jsonable(asdict(value), depth + 1)
    if isinstance(value, dict):
        return {str(k): _jsonable(v, depth + 1) for k, v in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [_jsonable(v, depth + 1) for v in list(value)[:80]]
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
        for item in list(value)[:80]:
            nested = _deep_find_fields(item, keys, depth + 1)
            for nk, nv in nested.items():
                found.setdefault(nk, nv)
    return found


def _normalize_store_value(value: Any) -> str:
    if value is None:
        return ""
    return re.sub(r"\s+", " ", str(value).strip()).lower()


def _is_existing_parser_ah_detection(fields: dict[str, Any]) -> bool:
    # This evaluates only fields returned by the existing parser/store detection.
    values = [
        fields.get("store_name"),
        fields.get("store_chain"),
        fields.get("store"),
        fields.get("retailer"),
        fields.get("chain"),
        fields.get("merchant"),
        fields.get("shop_name"),
    ]
    normalized = " | ".join(_normalize_store_value(v) for v in values if v is not None)
    if not normalized:
        return False
    return bool(
        re.search(r"\balbert\s+hei[jin]{1,2}\b", normalized)
        or "ah to go" in normalized
        or re.search(r"(^|\W)ah($|\W)", normalized)
    )


def _call_existing_parse_receipt_content(data: bytes, filename: str) -> dict[str, Any]:
    svc = importlib.import_module("app.services.receipt_service")
    if not hasattr(svc, "parse_receipt_content"):
        raise RuntimeError("app.services.receipt_service.parse_receipt_content ontbreekt")

    fn = svc.parse_receipt_content
    sig = inspect.signature(fn)

    candidates = [
        ("bytes_filename_kwargs", lambda: fn(data, filename=filename)),
        ("bytes_filename_positional", lambda: fn(data, filename)),
        ("bytes_only", lambda: fn(data)),
        ("content_filename_kwargs", lambda: fn(content=data, filename=filename)),
        ("file_bytes_filename_kwargs", lambda: fn(file_bytes=data, filename=filename)),
        ("raw_bytes_filename_kwargs", lambda: fn(raw_bytes=data, filename=filename)),
    ]

    attempts = []
    last_error = None
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
            attempts.append({"call_style": label, "error": str(exc)})
            continue
        except Exception as exc:
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


def _run_b5_b6_for_selected(zip_path: Path, member: str, out_dir: Path, preprocess: bool, b5: Any, b6: Any) -> dict[str, Any]:
    safe = _safe_stem(member)
    member_dir = out_dir / "per_member" / safe
    member_dir.mkdir(parents=True, exist_ok=True)

    b5_report = b5.build_report(zip_path, member, preprocess)
    b5_json = member_dir / f"R9-28B5_{safe}.json"
    b5_md = member_dir / f"R9-28B5_{safe}.md"
    b5_json.write_text(json.dumps(b5_report, indent=2, ensure_ascii=False), encoding="utf-8")
    b5_md.write_text(b5.render_markdown(b5_report), encoding="utf-8")

    b6_report = b6.build_report(b5_json)
    b6_json = member_dir / f"R9-28B6_{safe}.json"
    b6_md = member_dir / f"R9-28B6_{safe}.md"
    b6_json.write_text(json.dumps(b6_report, indent=2, ensure_ascii=False), encoding="utf-8")
    b6_md.write_text(b6.render_md(b6_report), encoding="utf-8")

    return {
        "b5": b5_report,
        "b6": b6_report,
    }


def _summarize_member(member: str, detection: dict[str, Any], parse_call: dict[str, Any], diagnostics: dict[str, Any] | None) -> dict[str, Any]:
    base = {
        "member": member,
        "store_detection": detection,
        "parse_call_summary": {
            "ok": parse_call.get("ok"),
            "call_style": parse_call.get("call_style"),
            "error_type": parse_call.get("error_type"),
            "error_message": parse_call.get("error_message"),
        },
        "selected_for_ah_reconstruction": bool(detection.get("is_ah")),
        "diagnostics_executed": diagnostics is not None,
    }

    if diagnostics is None:
        return {
            **base,
            "ocr_summary": None,
            "reconstructed_article_count": 0,
            "reconstructed_article_sum": 0,
            "reconstructed_articles": [],
            "suspicious_findings": [],
            "suspicious_finding_count": 0,
            "pass_batch_diagnostic": None if detection.get("is_ah") else False,
        }

    b5_report = diagnostics["b5"]
    b6_report = diagnostics["b6"]
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
        **base,
        "ocr_summary": {
            "paddle_available": b5_report.get("paddle", {}).get("available"),
            "paddle_raw_text_count": b5_report.get("paddle", {}).get("raw_text_count"),
            "paddle_bbox_count": b5_report.get("paddle", {}).get("bbox_count"),
            "paddle_grouped_line_count": b5_report.get("paddle", {}).get("grouped_line_count"),
            "tesseract_line_count": b5_report.get("tesseract", {}).get("line_count"),
        },
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
    diagnostics_run = [i for i in selected if i.get("diagnostics_executed")]
    failure_types: dict[str, int] = {}

    for item in diagnostics_run:
        for finding in item.get("suspicious_findings", []) or []:
            kind = finding.get("type", "unknown")
            failure_types[kind] = failure_types.get(kind, 0) + 1

    selection_pass = True if expected_ah_count is None else len(selected) == expected_ah_count
    if not selection_pass:
        failure_types["existing_parser_ah_selection_count_mismatch"] = 1

    skipped_diagnostics = len(selected) - len(diagnostics_run)
    if skipped_diagnostics:
        failure_types["selected_ah_diagnostics_not_executed"] = skipped_diagnostics

    return {
        "image_member_count": len(items),
        "ah_member_count_detected_by_existing_parser": len(selected),
        "expected_ah_count": expected_ah_count,
        "selection_pass": selection_pass,
        "diagnostics_executed_for_selected_ah_count": len(diagnostics_run),
        "passed_count": sum(1 for item in diagnostics_run if item.get("pass_batch_diagnostic")),
        "failed_or_suspicious_count": sum(1 for item in diagnostics_run if not item.get("pass_batch_diagnostic")),
        "failure_types": failure_types,
        "total_reconstructed_articles": sum(int(item.get("reconstructed_article_count") or 0) for item in diagnostics_run),
    }


def build_report(zip_path: Path, out_dir: Path, preprocess: bool, expected_ah_count: int | None, max_selected_diagnostics: int | None) -> dict[str, Any]:
    root = Path.cwd()
    b5 = _load_module(root / "tools/R9-28B5_export_pre_parser_ocr_diagnostics.py", "r9_28b5_export_pre_parser_ocr_diagnostics")
    b6 = _load_module(root / "tools/R9-28B6_ah_paddle_box_reconstruction.py", "r9_28b6_ah_paddle_box_reconstruction")

    members = _all_image_members(zip_path)
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "per_member").mkdir(parents=True, exist_ok=True)

    summaries: list[dict[str, Any]] = []
    selected_diagnostics_done = 0

    for member in members:
        safe = _safe_stem(member)
        member_dir = out_dir / "per_member" / safe
        member_dir.mkdir(parents=True, exist_ok=True)

        data, filename = _read_member(zip_path, member)
        parse_call = _call_existing_parse_receipt_content(data, filename)
        detection = _store_detection_from_existing_parser(parse_call)

        parse_json = {
            "member": member,
            "filename": filename,
            "store_detection": detection,
            "parse_call": {k: v for k, v in parse_call.items() if k != "result"},
            "parse_result_jsonable": parse_call.get("result_jsonable"),
        }
        (member_dir / f"existing_parser_store_detection_{safe}.json").write_text(
            json.dumps(parse_json, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )

        diagnostics = None
        if detection.get("is_ah"):
            if max_selected_diagnostics is None or selected_diagnostics_done < max_selected_diagnostics:
                diagnostics = _run_b5_b6_for_selected(zip_path, member, out_dir, preprocess, b5, b6)
                selected_diagnostics_done += 1
                gc.collect()

        summaries.append(_summarize_member(member, detection, parse_call, diagnostics))
        del data
        gc.collect()

    aggregate = _aggregate(summaries, expected_ah_count)

    return {
        "audit": "R9-28B6C3 resource-safe existing parser store detection batch",
        "created_at": datetime.now().isoformat(timespec="seconds"),
        "scope": "batch diagnostics; store selection via existing inleesproces/parser; heavy diagnostics only for existing-parser AH receipts; no parser/OCR/database/status/baseline/UI mutation",
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
            "resource_safety": "R9-28B5/R9-28B6 diagnostics are executed only for selected AH receipts.",
        },
        "input": {
            "zip_path": str(zip_path),
            "preprocess_for_selected_b5_diagnostics": preprocess,
            "expected_ah_count": expected_ah_count,
            "max_selected_diagnostics": max_selected_diagnostics,
        },
        "aggregate": aggregate,
        "members": summaries,
        "next_step_hint": "If selection finds all AH receipts, run diagnostics for all selected AH receipts. If memory still fails, process selected AH one-by-one with the same existing store-detection selection report.",
    }


def render_markdown(report: dict[str, Any]) -> str:
    lines = [
        "# R9-28B6C3 — Resource-safe AH-selectie via bestaande winkelherkenning",
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
        "| Member | Geselecteerd als AH | Store/chain uit bestaande parser | Parse ok | Call style | Diagnostics uitgevoerd | Artikelen | Som | Suspicious |",
        "|---|---:|---|---:|---|---:|---:|---:|---:|",
    ]
    for m in report["members"]:
        d = m["store_detection"]
        p = m["parse_call_summary"]
        lines.append(
            f"| `{m['member']}` | `{d.get('is_ah')}` | `{d.get('store_chain_detected')}` | "
            f"`{p.get('ok')}` | `{p.get('call_style')}` | `{m.get('diagnostics_executed')}` | "
            f"`{m.get('reconstructed_article_count')}` | `{m.get('reconstructed_article_sum')}` | `{m.get('suspicious_finding_count')}` |"
        )

    selected = [m for m in report["members"] if m.get("selected_for_ah_reconstruction") and m.get("diagnostics_executed")]
    lines += [
        "",
        "## Gereconstrueerde AH-artikelen per geselecteerde AH-bon met diagnostics",
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
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("zip_path")
    parser.add_argument("--out", default="/tmp/R9-28B6C3_existing_store_batch")
    parser.add_argument("--expected-ah-count", type=int, default=4)
    parser.add_argument("--preprocess", action="store_true")
    parser.add_argument("--max-selected-diagnostics", type=int, default=None)
    args = parser.parse_args()

    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)

    report = build_report(
        zip_path=Path(args.zip_path),
        out_dir=out_dir,
        preprocess=args.preprocess,
        expected_ah_count=args.expected_ah_count,
        max_selected_diagnostics=args.max_selected_diagnostics,
    )

    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    json_path = out_dir / f"R9-28B6C3_existing_store_detection_batch_{stamp}.json"
    md_path = out_dir / f"R9-28B6C3_existing_store_detection_batch_{stamp}.md"
    json_path.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    md_path.write_text(render_markdown(report), encoding="utf-8")

    print("R9-28B6C3 resource-safe existing parser store-detection batch geschreven:")
    print(f"- {json_path}")
    print(f"- {md_path}")
    print("SSOT: no parser/OCR/database/status/baseline/UI mutation")
    print("Guardrail: AH selection from existing parse_receipt_content/store detection only")
    print("Resource safety: R9-28B5/R9-28B6 only for selected AH receipts")
    print(f"image_member_count={report['aggregate']['image_member_count']}")
    print(f"ah_member_count_detected_by_existing_parser={report['aggregate']['ah_member_count_detected_by_existing_parser']}")
    print(f"expected_ah_count={report['aggregate']['expected_ah_count']}")
    print(f"selection_pass={report['aggregate']['selection_pass']}")
    print(f"diagnostics_executed_for_selected_ah_count={report['aggregate']['diagnostics_executed_for_selected_ah_count']}")
    print(f"passed_count={report['aggregate']['passed_count']}")
    print(f"failed_or_suspicious_count={report['aggregate']['failed_or_suspicious_count']}")
    print(f"failure_types={report['aggregate']['failure_types']}")
    if not report["aggregate"]["selection_pass"]:
        raise SystemExit(2)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
