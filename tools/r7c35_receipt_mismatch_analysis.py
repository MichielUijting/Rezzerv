#!/usr/bin/env python3
"""R7c35 backend-only receipt mismatch analysis.

Analyse-only. Does not change OCR, parser, SSOT status logic, frontend or database.

Outputs receipt-level and article-line-level diagnostics for the receipts that are
still marked as Controle nodig by the SSOT receipt baseline service.
"""

from __future__ import annotations

import json
import os
import shutil
import sqlite3
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
BACKEND_DIR = ROOT / "backend"
REPORT_DIR = ROOT / "reports" / "receipt_analysis"
DB_CANDIDATES = [ROOT / "backend" / "rezzerv.db", ROOT / "rezzerv.db", ROOT / "backend" / "rezzerv_test_temp.db"]


def stamp() -> str:
    return datetime.now().strftime("%Y%m%d_%H%M%S")


def write_json(path: Path, payload: Any) -> None:
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False, default=str), encoding="utf-8")


def sqlite_conn(path: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(str(path))
    conn.row_factory = sqlite3.Row
    return conn


def load_receipt_file_map(db_path: Path) -> dict[str, dict[str, Any]]:
    result: dict[str, dict[str, Any]] = {}
    with sqlite_conn(db_path) as conn:
        rows = conn.execute(
            """
            SELECT
                rt.id AS receipt_table_id,
                rr.id AS raw_receipt_id,
                rr.original_filename,
                rr.storage_path,
                rr.mime_type,
                rr.sha256_hash,
                rt.store_name,
                rt.purchase_at,
                rt.total_amount,
                rt.parse_status
            FROM receipt_tables rt
            JOIN raw_receipts rr ON rr.id = rt.raw_receipt_id
            WHERE rt.deleted_at IS NULL
            ORDER BY rt.created_at DESC
            """
        ).fetchall()
    for row in rows:
        data = dict(row)
        storage_path = Path(str(data.get("storage_path") or "")) if data.get("storage_path") else None
        file_payload: dict[str, Any] = {
            "receipt_table_id": data.get("receipt_table_id"),
            "raw_receipt_id": data.get("raw_receipt_id"),
            "original_filename": data.get("original_filename"),
            "storage_path": str(storage_path) if storage_path else None,
            "mime_type": data.get("mime_type"),
            "sha256_hash": data.get("sha256_hash"),
            "store_name": data.get("store_name"),
            "purchase_at": data.get("purchase_at"),
            "total_amount": data.get("total_amount"),
            "technical_parse_status": data.get("parse_status"),
            "file_exists": bool(storage_path and storage_path.exists()),
            "file_size_bytes": storage_path.stat().st_size if storage_path and storage_path.exists() else None,
            "file_suffix": storage_path.suffix.lower() if storage_path else None,
        }
        # Lightweight visual inspection metadata. No OCR or parser rerun.
        if storage_path and storage_path.exists() and storage_path.suffix.lower() in {".png", ".jpg", ".jpeg", ".webp"}:
            try:
                from PIL import Image
                with Image.open(storage_path) as image:
                    file_payload["image_width"] = image.width
                    file_payload["image_height"] = image.height
                    file_payload["image_mode"] = image.mode
            except Exception as exc:
                file_payload["image_inspection_error"] = str(exc)
        if storage_path and storage_path.exists() and storage_path.suffix.lower() == ".pdf":
            try:
                from pypdf import PdfReader
                reader = PdfReader(str(storage_path))
                file_payload["pdf_pages"] = len(reader.pages)
            except Exception as exc:
                file_payload["pdf_inspection_error"] = str(exc)
        result[str(data.get("receipt_table_id") or "")] = file_payload
    return result


def root_cause_category(item: dict[str, Any], line_diag: dict[str, Any] | None) -> str:
    reason = str(item.get("difference_reason") or item.get("diagnosis") or "").lower()
    if "geen geldige artikellijnen" in reason:
        return "geen_geldige_artikellijnen"
    if "ander aantal artikellijnen" in reason:
        return "artikelcount_mismatch"
    if "regelsom" in reason:
        return "regelsom_mismatch"
    if "totaalprijs" in reason or "totaal" in reason:
        return "totaalbedrag_mismatch"
    if line_diag:
        if line_diag.get("missing_lines"):
            return "ontbrekende_artikelregels"
        if line_diag.get("amount_mismatches"):
            return "artikelbedrag_mismatch"
        if line_diag.get("extra_lines"):
            return "extra_artikelregels"
    return "nader_te_analyseren"


def summarize_line_diag(line_diag: dict[str, Any] | None) -> dict[str, Any]:
    if not line_diag:
        return {
            "baseline_line_count": None,
            "actual_line_count": None,
            "matched_lines_count": None,
            "missing_line_count": None,
            "extra_line_count": None,
            "amount_mismatch_count": None,
        }
    return {
        "baseline_line_count": line_diag.get("baseline_line_count"),
        "actual_line_count": line_diag.get("actual_line_count"),
        "matched_lines_count": line_diag.get("matched_lines_count"),
        "missing_line_count": len(line_diag.get("missing_lines") or []),
        "extra_line_count": len(line_diag.get("extra_lines") or []),
        "amount_mismatch_count": len(line_diag.get("amount_mismatches") or []),
    }


def build_analysis(db_copy: Path) -> dict[str, Any]:
    if str(BACKEND_DIR) not in sys.path:
        sys.path.insert(0, str(BACKEND_DIR))
    os.environ["DATABASE_URL"] = f"sqlite:///{db_copy.as_posix()}"
    from sqlalchemy import create_engine
    from app.services.receipt_status_baseline_service import diagnose_receipt_status_baseline, validate_receipt_status_baseline

    engine = create_engine(f"sqlite:///{db_copy.as_posix()}")
    with engine.connect() as conn:
        validation = validate_receipt_status_baseline(conn, household_id="1")
        diagnosis = diagnose_receipt_status_baseline(conn, household_id="1")

    receipt_file_map = load_receipt_file_map(db_copy)
    extraction_items = diagnosis.get("extraction_mismatches") or []
    mapping_items = diagnosis.get("mapping_mismatches") or []
    status_items = diagnosis.get("status_logic_mismatches") or []

    receipt_analyses: list[dict[str, Any]] = []
    for item in extraction_items + mapping_items + status_items:
        receipt_table_id = str(item.get("receipt_table_id") or "")
        line_diag = item.get("line_diagnostics") or None
        receipt_analyses.append({
            "source_file": item.get("source_file"),
            "receipt_table_id": receipt_table_id,
            "matched_original_filename": item.get("matched_original_filename"),
            "store_name": item.get("store_name"),
            "ssot_status": "Controle nodig" if item in extraction_items or item in mapping_items else item.get("actual_parse_status"),
            "expected_parse_status": item.get("expected_parse_status"),
            "actual_parse_status": item.get("actual_parse_status"),
            "expected_total_amount": item.get("expected_total_amount"),
            "actual_total_amount": item.get("actual_total_amount"),
            "expected_line_count": item.get("expected_line_count"),
            "actual_line_count": item.get("actual_line_count"),
            "valid_line_count": item.get("valid_line_count"),
            "difference_reason": item.get("difference_reason"),
            "diagnosis": item.get("diagnosis"),
            "decision_reason": item.get("decision_reason"),
            "match_score": item.get("match_score"),
            "match_signals": item.get("match_signals"),
            "cause_category": root_cause_category(item, line_diag),
            "receipt_file": receipt_file_map.get(receipt_table_id, {}),
            "line_summary": summarize_line_diag(line_diag),
            "line_diagnostics": line_diag,
        })

    criteria_counts = ((validation.get("summary") or {}).get("failed_criteria_counts") or {})
    return {
        "runner": "R7c35 receipt mismatch analysis",
        "started_at": datetime.now().isoformat(timespec="seconds"),
        "database_copy": str(db_copy.relative_to(ROOT)),
        "status": "completed",
        "scope": "analyse-only; no OCR/parser/SSOT/frontend changes",
        "validation_summary": validation.get("summary") or {},
        "failed_criteria_counts": criteria_counts,
        "diagnosis_counts": {
            "extraction_mismatch_count": len(extraction_items),
            "mapping_mismatch_count": len(mapping_items),
            "status_logic_mismatch_count": len(status_items),
        },
        "receipt_analyses": receipt_analyses,
    }


def write_summary(report: dict[str, Any], path: Path) -> None:
    summary = report.get("validation_summary") or {}
    lines = [
        "R7c35 receipt mismatch analysis: completed",
        f"Databasekopie: {report.get('database_copy')}",
        "",
        "Samenvatting:",
        f"- baseline_total: {summary.get('baseline_total')}",
        f"- active_receipts_total: {summary.get('active_receipts_total')}",
        f"- correct: {summary.get('correct')}",
        f"- different: {summary.get('different')}",
        f"- po_norm_status_counts: {summary.get('po_norm_status_counts')}",
        f"- failed_criteria_counts: {report.get('failed_criteria_counts')}",
        "",
        "Per-bon analyse:",
    ]
    for item in report.get("receipt_analyses") or []:
        ls = item.get("line_summary") or {}
        rf = item.get("receipt_file") or {}
        lines.extend([
            f"- {item.get('source_file')} | oorzaak={item.get('cause_category')} | reden={item.get('diagnosis') or item.get('difference_reason')}",
            f"  status={item.get('ssot_status')} | verwacht_regels={item.get('expected_line_count')} | actueel_regels={item.get('actual_line_count')} | gematcht={ls.get('matched_lines_count')} | ontbrekend={ls.get('missing_line_count')} | extra={ls.get('extra_line_count')} | bedragverschil={ls.get('amount_mismatch_count')}",
            f"  bestand={rf.get('storage_path')} | bestaat={rf.get('file_exists')} | mime={rf.get('mime_type')} | grootte={rf.get('file_size_bytes')}",
        ])
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("\n".join(lines))


def main() -> int:
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    source = next((candidate for candidate in DB_CANDIDATES if candidate.exists()), None)
    if not source:
        raise SystemExit("Geen SQLite database gevonden")
    db_copy = REPORT_DIR / f"rezzerv-receipt-analysis-{stamp()}.db"
    shutil.copy2(source, db_copy)
    report = build_analysis(db_copy)
    report_json = REPORT_DIR / "r7c35_receipt_mismatch_analysis_report.json"
    report_txt = REPORT_DIR / "r7c35_receipt_mismatch_analysis_summary.txt"
    write_json(report_json, report)
    write_summary(report, report_txt)
    print("")
    print("Rapporten:")
    print(f"- {report_json.relative_to(ROOT)}")
    print(f"- {report_txt.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
