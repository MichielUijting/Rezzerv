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


# R9-28B6C6
# Scope AH testset via current receipt_import_batches.results_json.
#
# Scope:
# - Uses the current completed receipt_import_batch for source_filename.
# - Uses receipt_table_id from receipt_import_batches.results_json.
# - Uses existing persisted receipt_tables.store_name / store_chain for store selection.
# - Does NOT select store chain from filename.
# - Does NOT introduce OCR marker chain detection.
# - Does NOT rerun parse_receipt_content for selection.
# - Does NOT mutate parser/OCR/database/status/baseline/UI.
#
# Purpose:
# Build the exact current testset scope first:
#   latest completed receipt_import_batches row for supermarkten.zip
#   -> 14 import result entries
#   -> join to receipt_tables
#   -> select exactly 4 AH receipts using existing store fields.


IMAGE_SUFFIXES = {".jpg", ".jpeg", ".png", ".bmp", ".tif", ".tiff", ".webp"}
SUPPORTED_DIAG_SUFFIXES = IMAGE_SUFFIXES  # R9-28B5 currently handles image members, not PDFs.


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


def _normalize(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "").strip()).lower()


def _is_ah_from_existing_store_fields(row: dict[str, Any]) -> bool:
    # This evaluates only store fields already produced by the Rezzerv inleesproces.
    # filename/archive_path is intentionally not used for chain detection.
    store_text = " | ".join(
        _normalize(row.get(k))
        for k in ["store_name", "store_chain"]
        if row.get(k) is not None
    )
    return bool(
        re.search(r"\balbert\s+hei[jin]{1,2}\b", store_text)
        or "ah to go" in store_text
        or re.search(r"(^|\W)ah($|\W)", store_text)
    )


def _all_zip_members(zip_path: Path) -> list[str]:
    if not zip_path or not zip_path.exists():
        return []
    with zipfile.ZipFile(zip_path, "r") as z:
        return sorted([n for n in z.namelist() if not n.endswith("/")])


def _find_zip_member(filename: str | None, archive_path: str | None, members: list[str]) -> str | None:
    if not members:
        return None
    candidates = [archive_path, filename]
    by_full = {m.lower(): m for m in members}
    by_base = {Path(m).name.lower(): m for m in members}
    for c in candidates:
        if not c:
            continue
        c = str(c).strip()
        if c.lower() in by_full:
            return by_full[c.lower()]
        base = Path(c).name.lower()
        if base in by_base:
            return by_base[base]
    return None


def _fetch_latest_batch(conn: sqlite3.Connection, source_filename: str, batch_id: str | None) -> dict[str, Any]:
    if batch_id:
        row = conn.execute(
            "SELECT * FROM receipt_import_batches WHERE id = ?",
            (batch_id,),
        ).fetchone()
    else:
        row = conn.execute(
            """
            SELECT *
            FROM receipt_import_batches
            WHERE source_filename = ?
              AND status = 'completed'
            ORDER BY finished_at DESC, created_at DESC
            LIMIT 1
            """,
            (source_filename,),
        ).fetchone()
    if row is None:
        raise RuntimeError(f"Geen completed receipt_import_batch gevonden voor source_filename={source_filename!r}")
    return dict(row)


def _load_batch_entries(batch: dict[str, Any]) -> list[dict[str, Any]]:
    raw = batch.get("results_json")
    if not raw:
        return []
    data = json.loads(raw)
    if not isinstance(data, list):
        raise RuntimeError("receipt_import_batches.results_json is geen JSON-list")
    return [dict(item) for item in data]


def _fetch_receipt_tables(conn: sqlite3.Connection, receipt_table_ids: list[str]) -> dict[str, dict[str, Any]]:
    if not receipt_table_ids:
        return {}
    placeholders = ",".join("?" for _ in receipt_table_ids)
    rows = conn.execute(
        f"""
        SELECT
          rt.id AS receipt_table_id,
          rt.raw_receipt_id,
          rt.store_name,
          rt.store_chain,
          rt.reference,
          rt.total_amount,
          rt.parse_status,
          rt.created_at,
          rt.deleted_at,
          rr.original_filename AS raw_original_filename,
          rr.mime_type AS raw_mime_type,
          rr.storage_path AS raw_storage_path,
          rr.deleted_at AS raw_deleted_at,
          rr.raw_status AS raw_status
        FROM receipt_tables rt
        LEFT JOIN raw_receipts rr ON rr.id = rt.raw_receipt_id
        WHERE rt.id IN ({placeholders})
        """,
        receipt_table_ids,
    ).fetchall()
    return {row["receipt_table_id"]: dict(row) for row in rows}


def _safe_stem(name: str) -> str:
    return re.sub(r"[^A-Za-z0-9_.-]+", "_", Path(name).stem)


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


def _summarize_diagnostics(diag: dict[str, Any] | None) -> dict[str, Any]:
    if not diag:
        return {
            "diagnostics_executed": False,
            "reconstructed_article_count": 0,
            "reconstructed_article_sum": 0,
            "reconstructed_articles": [],
            "suspicious_findings": [],
            "suspicious_finding_count": 0,
            "pass_batch_diagnostic": None,
        }

    b5_report = diag["b5"]
    b6_report = diag["b6"]
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
        "diagnostics_executed": True,
        "ocr_summary": {
            "paddle_raw_text_count": b5_report.get("paddle", {}).get("raw_text_count"),
            "paddle_bbox_count": b5_report.get("paddle", {}).get("bbox_count"),
            "paddle_grouped_line_count": b5_report.get("paddle", {}).get("grouped_line_count"),
        },
        "reconstructed_article_count": len(articles),
        "reconstructed_article_sum": round(sum(float(a.get("amount") or 0) for a in articles), 2),
        "reconstructed_articles": articles,
        "suspicious_findings": suspicious,
        "suspicious_finding_count": len(suspicious),
        "pass_batch_diagnostic": len(articles) > 0 and len(suspicious) == 0,
    }


def build_report(
    db_path: Path,
    source_filename: str,
    batch_id: str | None,
    expected_file_count: int | None,
    expected_ah_count: int | None,
    zip_path: Path | None,
    out_dir: Path,
    run_diagnostics: bool,
    preprocess: bool,
    max_diagnostics: int | None,
) -> dict[str, Any]:
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row

    batch = _fetch_latest_batch(conn, source_filename, batch_id)
    entries = _load_batch_entries(batch)

    ids = [str(e.get("receipt_table_id")) for e in entries if e.get("receipt_table_id")]
    tables_by_id = _fetch_receipt_tables(conn, ids)

    zip_members = _all_zip_members(zip_path) if zip_path else []

    root = Path.cwd()
    b5 = b6 = None
    if run_diagnostics:
        if not zip_path:
            raise RuntimeError("--run-diagnostics vereist --zip")
        b5 = _load_module(root / "tools/R9-28B5_export_pre_parser_ocr_diagnostics.py", "r9_28b5_export_pre_parser_ocr_diagnostics")
        b6 = _load_module(root / "tools/R9-28B6_ah_paddle_box_reconstruction.py", "r9_28b6_ah_paddle_box_reconstruction")

    scoped = []
    ah_selected = []
    diag_done = 0

    for e in entries:
        rt = tables_by_id.get(str(e.get("receipt_table_id")), {})
        merged = {
            "batch_filename": e.get("filename"),
            "batch_archive_path": e.get("archive_path"),
            "batch_import_status": e.get("import_status"),
            "batch_parse_status": e.get("parse_status"),
            "batch_duplicate": e.get("duplicate"),
            **rt,
        }
        is_ah = _is_ah_from_existing_store_fields(merged)
        member = _find_zip_member(e.get("filename"), e.get("archive_path"), zip_members)

        diag = None
        diag_skip_reason = None
        if is_ah:
            if not member:
                diag_skip_reason = "zip_member_not_found"
            elif Path(member).suffix.lower() not in SUPPORTED_DIAG_SUFFIXES:
                diag_skip_reason = "diagnostics_not_supported_for_pdf_or_non_image"
            elif run_diagnostics and (max_diagnostics is None or diag_done < max_diagnostics):
                diag = _run_b5_b6(zip_path, member, out_dir, preprocess, b5, b6)
                diag_done += 1
            elif run_diagnostics:
                diag_skip_reason = "max_diagnostics_limit_reached"
            else:
                diag_skip_reason = "diagnostics_not_requested"

        diag_summary = _summarize_diagnostics(diag)
        item = {
            **merged,
            "zip_member": member,
            "selected_as_ah_from_existing_store_fields": is_ah,
            "diag_skip_reason": diag_skip_reason,
            **diag_summary,
        }
        scoped.append(item)
        if is_ah:
            ah_selected.append(item)

    failure_types: dict[str, int] = {}
    if expected_file_count is not None and len(entries) != expected_file_count:
        failure_types["batch_file_count_mismatch"] = 1
    if expected_ah_count is not None and len(ah_selected) != expected_ah_count:
        failure_types["batch_ah_count_mismatch"] = 1

    for s in ah_selected:
        if s.get("diag_skip_reason") and run_diagnostics:
            key = str(s.get("diag_skip_reason"))
            failure_types[key] = failure_types.get(key, 0) + 1
        for f in s.get("suspicious_findings") or []:
            key = f.get("type", "unknown")
            failure_types[key] = failure_types.get(key, 0) + 1

    return {
        "audit": "R9-28B6C6 AH testscope via receipt_import_batches.results_json",
        "created_at": datetime.now().isoformat(timespec="seconds"),
        "scope": "current import-batch scoped diagnostics; AH selection via existing receipt_tables store fields; no mutation",
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
            "batch_scope_source": "receipt_import_batches.results_json",
            "existing_store_detection_used": "receipt_tables.store_name / receipt_tables.store_chain",
            "filename_based_chain_classification_allowed": False,
            "filename_used_only_for_batch_member_mapping": True,
            "new_ocr_marker_chain_classifier_allowed": False,
            "parse_receipt_content_rerun_for_selection": False,
            "hardcoded_receipt_ids_allowed": False,
            "database_mutated": False,
        },
        "input": {
            "db_path": str(db_path),
            "source_filename": source_filename,
            "batch_id": batch_id,
            "zip_path": str(zip_path) if zip_path else None,
            "expected_file_count": expected_file_count,
            "expected_ah_count": expected_ah_count,
            "run_diagnostics": run_diagnostics,
            "max_diagnostics": max_diagnostics,
            "preprocess_for_diagnostics": preprocess,
        },
        "batch": {
            "id": batch.get("id"),
            "source_filename": batch.get("source_filename"),
            "total_files": batch.get("total_files"),
            "processed_files": batch.get("processed_files"),
            "imported_files": batch.get("imported_files"),
            "duplicate_files": batch.get("duplicate_files"),
            "failed_files": batch.get("failed_files"),
            "status": batch.get("status"),
            "created_at": batch.get("created_at"),
            "finished_at": batch.get("finished_at"),
        },
        "aggregate": {
            "scoped_batch_entry_count": len(entries),
            "expected_file_count": expected_file_count,
            "file_count_pass": expected_file_count is None or len(entries) == expected_file_count,
            "ah_count_from_existing_store_fields": len(ah_selected),
            "expected_ah_count": expected_ah_count,
            "ah_count_pass": expected_ah_count is None or len(ah_selected) == expected_ah_count,
            "diagnostics_executed_count": diag_done,
            "passed_count": sum(1 for s in ah_selected if s.get("pass_batch_diagnostic") is True),
            "failed_or_suspicious_count": sum(1 for s in ah_selected if s.get("pass_batch_diagnostic") is False),
            "failure_types": failure_types,
        },
        "scoped_batch_entries": scoped,
        "selected_ah_receipts": ah_selected,
        "next_step_hint": "This is the correct fixed AH test scope. Run image diagnostics one-by-one for image AH receipts; PDF diagnostics require a separate PDF-capable export path.",
    }


def render_markdown(report: dict[str, Any]) -> str:
    lines = [
        "# R9-28B6C6 — AH-testscope via actuele receipt_import_batch",
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
    lines += ["", "## Batch", ""]
    for k, v in report["batch"].items():
        lines.append(f"- `{k}`: `{v}`")
    lines += ["", "## Samenvatting", ""]
    for k, v in report["aggregate"].items():
        lines.append(f"- `{k}`: `{v}`")
    lines += [
        "",
        "## Alle entries in actuele batch",
        "",
        "| filename | import_status | receipt_table_id | store_name | store_chain | AH | total | zip member |",
        "|---|---|---|---|---|---:|---:|---|",
    ]
    for s in report["scoped_batch_entries"]:
        lines.append(
            f"| `{s.get('batch_filename')}` | `{s.get('batch_import_status')}` | `{s.get('receipt_table_id')}` | "
            f"`{s.get('store_name')}` | `{s.get('store_chain')}` | `{s.get('selected_as_ah_from_existing_store_fields')}` | "
            f"`{s.get('total_amount')}` | `{s.get('zip_member')}` |"
        )
    lines += [
        "",
        "## Geselecteerde AH-receipts",
        "",
        "| filename | receipt_table_id | store_name | total | diagnostics | skip reason | artikelen | som | suspicious |",
        "|---|---|---|---:|---:|---|---:|---:|---:|",
    ]
    for s in report["selected_ah_receipts"]:
        lines.append(
            f"| `{s.get('batch_filename')}` | `{s.get('receipt_table_id')}` | `{s.get('store_name')}` | `{s.get('total_amount')}` | "
            f"`{s.get('diagnostics_executed')}` | `{s.get('diag_skip_reason')}` | "
            f"`{s.get('reconstructed_article_count')}` | `{s.get('reconstructed_article_sum')}` | `{s.get('suspicious_finding_count')}` |"
        )
    lines += ["", "## Gereconstrueerde artikelen", ""]
    for s in report["selected_ah_receipts"]:
        if not s.get("diagnostics_executed"):
            continue
        lines.append(f"### `{s.get('batch_filename')}`")
        for a in s.get("reconstructed_articles") or []:
            lines.append(f"- `{a.get('article_name')}` — `{a.get('amount_text')}`")
        if s.get("suspicious_findings"):
            lines.append("")
            lines.append("Suspicious findings:")
            for f in s.get("suspicious_findings") or []:
                lines.append(f"- `{f.get('type')}`")
        lines.append("")
    lines += ["## Vervolg", "", report["next_step_hint"], ""]
    return "\n".join(lines)


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--db", default="/app/data/rezzerv.db")
    p.add_argument("--source-filename", default="supermarkten.zip")
    p.add_argument("--batch-id", default=None)
    p.add_argument("--zip", default=None)
    p.add_argument("--out", default="/tmp/R9-28B6C6_batch_scope")
    p.add_argument("--expected-file-count", type=int, default=14)
    p.add_argument("--expected-ah-count", type=int, default=4)
    p.add_argument("--run-diagnostics", action="store_true")
    p.add_argument("--max-diagnostics", type=int, default=None)
    p.add_argument("--preprocess", action="store_true")
    args = p.parse_args()

    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)

    report = build_report(
        db_path=Path(args.db),
        source_filename=args.source_filename,
        batch_id=args.batch_id,
        expected_file_count=args.expected_file_count,
        expected_ah_count=args.expected_ah_count,
        zip_path=Path(args.zip) if args.zip else None,
        out_dir=out_dir,
        run_diagnostics=args.run_diagnostics,
        preprocess=args.preprocess,
        max_diagnostics=args.max_diagnostics,
    )

    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    json_path = out_dir / f"R9-28B6C6_batch_scope_{stamp}.json"
    md_path = out_dir / f"R9-28B6C6_batch_scope_{stamp}.md"
    json_path.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    md_path.write_text(render_markdown(report), encoding="utf-8")

    print("R9-28B6C6 batchscope geschreven:")
    print(f"- {json_path}")
    print(f"- {md_path}")
    print("SSOT: no parser/OCR/database/status/baseline/UI mutation")
    print("Guardrail: batch scope from receipt_import_batches.results_json; AH selection from existing receipt_tables store fields")
    print(f"batch_id={report['batch']['id']}")
    print(f"scoped_batch_entry_count={report['aggregate']['scoped_batch_entry_count']}")
    print(f"file_count_pass={report['aggregate']['file_count_pass']}")
    print(f"ah_count_from_existing_store_fields={report['aggregate']['ah_count_from_existing_store_fields']}")
    print(f"ah_count_pass={report['aggregate']['ah_count_pass']}")
    print(f"diagnostics_executed_count={report['aggregate']['diagnostics_executed_count']}")
    print(f"failure_types={report['aggregate']['failure_types']}")
    if not report["aggregate"]["file_count_pass"] or not report["aggregate"]["ah_count_pass"]:
        raise SystemExit(2)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
