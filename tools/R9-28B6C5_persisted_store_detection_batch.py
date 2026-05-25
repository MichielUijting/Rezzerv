from __future__ import annotations

import argparse
import importlib.util
import json
import re
import sqlite3
import sys
import zipfile
from datetime import datetime
from pathlib import Path
from typing import Any


# R9-28B6C5
# Batch selection via existing persisted Rezzerv store detection.
#
# Scope:
# - Uses existing runtime database results from the inleesproces.
# - Does NOT rerun parse_receipt_content for all images.
# - Does NOT infer store chain from filename.
# - Does NOT introduce new OCR-marker chain detection.
# - Does NOT mutate parser/OCR/database/status/baseline/UI.
#
# Purpose:
# Select AH receipts based on already persisted store fields produced by the app:
# receipt_tables.store_name / store_chain / reference joined to raw_receipts metadata.
# Then optionally run R9-28B5/R9-28B6 diagnostics for selected AH receipts, one-by-one.


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


def _columns(conn: sqlite3.Connection, table: str) -> list[str]:
    try:
        return [row[1] for row in conn.execute(f"PRAGMA table_info({table})").fetchall()]
    except Exception:
        return []


def _has_table(conn: sqlite3.Connection, table: str) -> bool:
    row = conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name=?", (table,)).fetchone()
    return row is not None


def _q(name: str) -> str:
    return '"' + name.replace('"', '""') + '"'


def _first_existing(cols: list[str], candidates: list[str]) -> str | None:
    lowered = {c.lower(): c for c in cols}
    for c in candidates:
        if c.lower() in lowered:
            return lowered[c.lower()]
    return None


def _all_image_members(zip_path: Path) -> list[str]:
    with zipfile.ZipFile(zip_path, "r") as z:
        return sorted([
            n for n in z.namelist()
            if not n.endswith("/") and Path(n).suffix.lower() in IMAGE_SUFFIXES
        ])


def _normalize(v: Any) -> str:
    return re.sub(r"\s+", " ", str(v or "").strip()).lower()


def _is_ah_from_existing_store_fields(row: dict[str, Any]) -> bool:
    values = [
        row.get("store_name"),
        row.get("store_chain"),
        row.get("reference"),
        row.get("raw_original_filename"),
        row.get("raw_filename"),
    ]
    # This evaluates fields already stored by the existing inleesproces.
    # It is not OCR-content detection and not parser logic.
    text = " | ".join(_normalize(v) for v in values if v is not None)
    return bool(
        re.search(r"\balbert\s+hei[jin]{1,2}\b", text)
        or "ah to go" in text
        or re.search(r"(^|\W)ah($|\W)", text)
    )


def _safe_stem(name: str) -> str:
    return re.sub(r"[^A-Za-z0-9_.-]+", "_", Path(name).stem)


def _find_zip_member_for_receipt(row: dict[str, Any], zip_members: list[str]) -> str | None:
    candidates = [
        row.get("raw_original_filename"),
        row.get("raw_filename"),
        row.get("reference"),
        row.get("source_filename"),
        row.get("filename"),
    ]
    normalized_members = {Path(m).name.lower(): m for m in zip_members}
    full_lower = {m.lower(): m for m in zip_members}

    for value in candidates:
        if not value:
            continue
        v = str(value).strip()
        if v.lower() in full_lower:
            return full_lower[v.lower()]
        base = Path(v).name.lower()
        if base in normalized_members:
            return normalized_members[base]

    # Last-resort association using exact basename fragments from persisted fields.
    for value in candidates:
        if not value:
            continue
        stem = Path(str(value)).stem.lower()
        if not stem:
            continue
        matches = [m for m in zip_members if stem in Path(m).stem.lower() or Path(m).stem.lower() in stem]
        if len(matches) == 1:
            return matches[0]
    return None


def _fetch_existing_receipts(conn: sqlite3.Connection) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    if not _has_table(conn, "receipt_tables"):
        raise RuntimeError("Tabel receipt_tables ontbreekt")

    rt_cols = _columns(conn, "receipt_tables")
    rr_cols = _columns(conn, "raw_receipts") if _has_table(conn, "raw_receipts") else []

    rt_id = _first_existing(rt_cols, ["id"]) or "id"
    raw_receipt_id = _first_existing(rt_cols, ["raw_receipt_id"])
    store_name = _first_existing(rt_cols, ["store_name"])
    store_chain = _first_existing(rt_cols, ["store_chain"])
    reference = _first_existing(rt_cols, ["reference"])
    total_amount = _first_existing(rt_cols, ["total_amount"])
    created_at = _first_existing(rt_cols, ["created_at"])

    rr_id = _first_existing(rr_cols, ["id"])
    rr_original = _first_existing(rr_cols, ["original_filename", "filename", "source_filename", "file_name"])
    rr_storage = _first_existing(rr_cols, ["storage_path", "path", "file_path"])
    rr_status = _first_existing(rr_cols, ["raw_status"])

    select_parts = [
        f"rt.{_q(rt_id)} AS receipt_table_id",
    ]
    for col, alias in [
        (raw_receipt_id, "raw_receipt_id"),
        (store_name, "store_name"),
        (store_chain, "store_chain"),
        (reference, "reference"),
        (total_amount, "total_amount"),
        (created_at, "created_at"),
    ]:
        if col:
            select_parts.append(f"rt.{_q(col)} AS {alias}")
        else:
            select_parts.append(f"NULL AS {alias}")

    join_sql = ""
    if raw_receipt_id and rr_id:
        for col, alias in [
            (rr_original, "raw_original_filename"),
            (rr_storage, "raw_storage_path"),
            (rr_status, "raw_status"),
        ]:
            if col:
                select_parts.append(f"rr.{_q(col)} AS {alias}")
            else:
                select_parts.append(f"NULL AS {alias}")
        join_sql = f" LEFT JOIN raw_receipts rr ON rr.{_q(rr_id)} = rt.{_q(raw_receipt_id)} "
    else:
        select_parts.extend([
            "NULL AS raw_original_filename",
            "NULL AS raw_storage_path",
            "NULL AS raw_status",
        ])

    order_sql = f"ORDER BY rt.{_q(created_at)}" if created_at else f"ORDER BY rt.{_q(rt_id)}"
    sql = f"SELECT {', '.join(select_parts)} FROM receipt_tables rt {join_sql} {order_sql}"

    rows = [dict(row) for row in conn.execute(sql).fetchall()]
    schema = {
        "receipt_tables_columns": rt_cols,
        "raw_receipts_columns": rr_cols,
        "used_columns": {
            "receipt_table_id": rt_id,
            "raw_receipt_id": raw_receipt_id,
            "store_name": store_name,
            "store_chain": store_chain,
            "reference": reference,
            "total_amount": total_amount,
            "created_at": created_at,
            "raw_original_filename": rr_original,
            "raw_storage_path": rr_storage,
            "raw_status": rr_status,
        },
        "sql": sql,
    }
    return rows, schema


def _run_b5_b6(zip_path: Path, member: str, out_dir: Path, preprocess: bool, b5: Any, b6: Any) -> dict[str, Any]:
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

    return {"b5": b5_report, "b6": b6_report}


def _summarize_selected(row: dict[str, Any], member: str | None, diagnostics: dict[str, Any] | None) -> dict[str, Any]:
    base = {
        "receipt_table_id": row.get("receipt_table_id"),
        "raw_receipt_id": row.get("raw_receipt_id"),
        "store_name": row.get("store_name"),
        "store_chain": row.get("store_chain"),
        "reference": row.get("reference"),
        "raw_original_filename": row.get("raw_original_filename"),
        "raw_storage_path": row.get("raw_storage_path"),
        "zip_member": member,
        "selected_as_ah_from_existing_persisted_store_fields": True,
        "diagnostics_executed": diagnostics is not None,
    }
    if diagnostics is None:
        return {
            **base,
            "reconstructed_article_count": 0,
            "reconstructed_article_sum": 0,
            "reconstructed_articles": [],
            "suspicious_findings": [{"type": "zip_member_not_found" if member is None else "diagnostics_not_executed"}],
            "suspicious_finding_count": 1,
            "pass_batch_diagnostic": False,
        }

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
            "paddle_raw_text_count": diagnostics["b5"].get("paddle", {}).get("raw_text_count"),
            "paddle_bbox_count": diagnostics["b5"].get("paddle", {}).get("bbox_count"),
            "paddle_grouped_line_count": diagnostics["b5"].get("paddle", {}).get("grouped_line_count"),
        },
        "reconstructed_article_count": len(articles),
        "reconstructed_article_sum": round(sum(float(a.get("amount") or 0) for a in articles), 2),
        "reconstructed_articles": articles,
        "suspicious_findings": suspicious,
        "suspicious_finding_count": len(suspicious),
        "pass_batch_diagnostic": len(articles) > 0 and len(suspicious) == 0,
    }


def build_report(db_path: Path, zip_path: Path | None, out_dir: Path, preprocess: bool, expected_ah_count: int | None, run_diagnostics: bool, max_diagnostics: int | None) -> dict[str, Any]:
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row

    receipts, schema = _fetch_existing_receipts(conn)
    selected_rows = [r for r in receipts if _is_ah_from_existing_store_fields(r)]

    zip_members = _all_image_members(zip_path) if zip_path else []
    root = Path.cwd()
    b5 = b6 = None
    if run_diagnostics and zip_path:
        b5 = _load_module(root / "tools/R9-28B5_export_pre_parser_ocr_diagnostics.py", "r9_28b5_export_pre_parser_ocr_diagnostics")
        b6 = _load_module(root / "tools/R9-28B6_ah_paddle_box_reconstruction.py", "r9_28b6_ah_paddle_box_reconstruction")

    summaries = []
    diagnostics_done = 0
    for row in selected_rows:
        member = _find_zip_member_for_receipt(row, zip_members) if zip_members else None
        diagnostics = None
        if run_diagnostics and zip_path and member and (max_diagnostics is None or diagnostics_done < max_diagnostics):
            diagnostics = _run_b5_b6(zip_path, member, out_dir, preprocess, b5, b6)
            diagnostics_done += 1
        summaries.append(_summarize_selected(row, member, diagnostics))

    failure_types: dict[str, int] = {}
    for s in summaries:
        for f in s.get("suspicious_findings", []) or []:
            kind = f.get("type", "unknown")
            failure_types[kind] = failure_types.get(kind, 0) + 1

    selection_pass = True if expected_ah_count is None else len(selected_rows) == expected_ah_count
    if not selection_pass:
        failure_types["persisted_store_ah_selection_count_mismatch"] = 1

    return {
        "audit": "R9-28B6C5 persisted existing store-detection batch selection",
        "created_at": datetime.now().isoformat(timespec="seconds"),
        "scope": "batch diagnostics; AH selection via existing persisted inleesproces store fields; no OCR/parser rerun for selection; no mutation",
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
            "existing_persisted_store_detection_used": True,
            "parse_receipt_content_rerun_for_selection": False,
            "filename_based_chain_classification_allowed": False,
            "new_ocr_marker_chain_classifier_allowed": False,
            "filename_specific_parser_rules_allowed": False,
            "member_specific_rules_allowed": False,
            "hardcoded_receipt_ids_allowed": False,
            "selection_method": "receipt_tables/raw_receipts store fields produced by existing inleesproces",
        },
        "input": {
            "db_path": str(db_path),
            "zip_path": str(zip_path) if zip_path else None,
            "expected_ah_count": expected_ah_count,
            "run_diagnostics": run_diagnostics,
            "max_diagnostics": max_diagnostics,
            "preprocess_for_diagnostics": preprocess,
        },
        "schema": schema,
        "aggregate": {
            "receipt_table_count": len(receipts),
            "ah_member_count_detected_by_existing_persisted_store": len(selected_rows),
            "expected_ah_count": expected_ah_count,
            "selection_pass": selection_pass,
            "diagnostics_executed_count": diagnostics_done,
            "passed_count": sum(1 for s in summaries if s.get("pass_batch_diagnostic")),
            "failed_or_suspicious_count": sum(1 for s in summaries if not s.get("pass_batch_diagnostic")),
            "failure_types": failure_types,
        },
        "selected_ah_receipts": summaries,
        "next_step_hint": "If this selects exactly 4 AH receipts, use these persisted inleesproces results as the fixed AH batch scope. Then run diagnostics one-by-one if memory is limited.",
    }


def render_markdown(report: dict[str, Any]) -> str:
    lines = [
        "# R9-28B6C5 — AH-selectie via bestaande opgeslagen winkelherkenning",
        "",
        f"Gemaakt: `{report['created_at']}`",
        "",
        "## SSOT-compliance",
        "",
    ]
    for k, v in report["ssot_compliance"].items():
        lines.append(f"- `{k}`: `{v}`")
    lines += ["", "## Guardrails", ""]
    for k, v in report["guardrails"].items():
        lines.append(f"- `{k}`: `{v}`")
    lines += ["", "## Batchsamenvatting", ""]
    for k, v in report["aggregate"].items():
        lines.append(f"- `{k}`: `{v}`")
    lines += [
        "",
        "## Geselecteerde AH-receipts uit bestaande database",
        "",
        "| receipt_table_id | store_name | store_chain | reference | raw filename | zip member | diagnostics | artikelen | som | suspicious |",
        "|---|---|---|---|---|---|---:|---:|---:|---:|",
    ]
    for s in report["selected_ah_receipts"]:
        lines.append(
            f"| `{s.get('receipt_table_id')}` | `{s.get('store_name')}` | `{s.get('store_chain')}` | `{s.get('reference')}` | "
            f"`{s.get('raw_original_filename')}` | `{s.get('zip_member')}` | `{s.get('diagnostics_executed')}` | "
            f"`{s.get('reconstructed_article_count')}` | `{s.get('reconstructed_article_sum')}` | `{s.get('suspicious_finding_count')}` |"
        )
    lines += ["", "## Gereconstrueerde artikelen", ""]
    for s in report["selected_ah_receipts"]:
        if not s.get("diagnostics_executed"):
            continue
        lines.append(f"### `{s.get('zip_member') or s.get('receipt_table_id')}`")
        for a in s.get("reconstructed_articles") or []:
            lines.append(f"- `{a.get('article_name')}` — `{a.get('amount_text')}`")
        if s.get("suspicious_findings"):
            lines.append("")
            lines.append("Suspicious findings:")
            for f in s.get("suspicious_findings") or []:
                lines.append(f"- `{f.get('type')}`")
        lines.append("")
    return "\n".join(lines)


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--db", default="/app/data/rezzerv.db")
    p.add_argument("--zip", default=None)
    p.add_argument("--out", default="/tmp/R9-28B6C5_persisted_store_batch")
    p.add_argument("--expected-ah-count", type=int, default=4)
    p.add_argument("--run-diagnostics", action="store_true")
    p.add_argument("--max-diagnostics", type=int, default=None)
    p.add_argument("--preprocess", action="store_true")
    args = p.parse_args()

    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)
    report = build_report(
        db_path=Path(args.db),
        zip_path=Path(args.zip) if args.zip else None,
        out_dir=out_dir,
        preprocess=args.preprocess,
        expected_ah_count=args.expected_ah_count,
        run_diagnostics=args.run_diagnostics,
        max_diagnostics=args.max_diagnostics,
    )

    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    json_path = out_dir / f"R9-28B6C5_persisted_store_detection_batch_{stamp}.json"
    md_path = out_dir / f"R9-28B6C5_persisted_store_detection_batch_{stamp}.md"
    json_path.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    md_path.write_text(render_markdown(report), encoding="utf-8")

    print("R9-28B6C5 persisted existing store-detection batch geschreven:")
    print(f"- {json_path}")
    print(f"- {md_path}")
    print("SSOT: no parser/OCR/database/status/baseline/UI mutation")
    print("Guardrail: AH selection from persisted existing inleesproces store fields")
    print(f"receipt_table_count={report['aggregate']['receipt_table_count']}")
    print(f"ah_member_count_detected_by_existing_persisted_store={report['aggregate']['ah_member_count_detected_by_existing_persisted_store']}")
    print(f"expected_ah_count={report['aggregate']['expected_ah_count']}")
    print(f"selection_pass={report['aggregate']['selection_pass']}")
    print(f"diagnostics_executed_count={report['aggregate']['diagnostics_executed_count']}")
    print(f"failure_types={report['aggregate']['failure_types']}")
    if not report["aggregate"]["selection_pass"]:
        raise SystemExit(2)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
