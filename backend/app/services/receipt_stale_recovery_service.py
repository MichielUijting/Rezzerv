"""Safe one-time recovery for stale, untouched Kassa parser results.

This migration is deliberately conservative. It reparses only active receipts
that are still ``review_needed`` and have no evidence of user review, matching,
unpacking or inventory effects. The existing raw source remains authoritative;
no receipt names, hashes, stores or product text are hard-coded here.
"""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from sqlalchemy import text

from app.services.receipt_service import reparse_receipt


MIGRATION_ID = "v01.12.110-safe-stale-receipt-recovery"
_TRUE_VALUES = {"1", "true", "yes", "on"}
_REQUIRED_RECEIPT_COLUMNS = {
    "deleted_at",
    "approved_at",
    "reviewed_at",
    "corrected_by_user_email",
    "totals_overridden",
}
_REQUIRED_RAW_COLUMNS = {"deleted_at", "storage_path"}
_REQUIRED_LINE_COLUMNS = {
    "corrected_raw_label",
    "corrected_quantity",
    "corrected_unit",
    "corrected_unit_price",
    "corrected_line_total",
    "matched_article_id",
    "matched_global_product_id",
    "is_deleted",
    "is_validated",
}


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _enabled() -> bool:
    return str(
        os.getenv("REZZERV_STALE_RECEIPT_RECOVERY_ENABLED", "true") or "true"
    ).strip().lower() in _TRUE_VALUES


def _table_exists(conn, table_name: str) -> bool:
    return bool(
        conn.execute(
            text(
                "SELECT 1 FROM sqlite_master "
                "WHERE type = 'table' AND name = :table_name LIMIT 1"
            ),
            {"table_name": table_name},
        ).first()
    )


def _columns(conn, table_name: str) -> set[str]:
    if not _table_exists(conn, table_name):
        return set()
    return {
        str(row.get("name") or "")
        for row in conn.execute(text(f"PRAGMA table_info({table_name})")).mappings().all()
    }


def _marker_paths(receipt_storage_root: Path) -> tuple[Path, Path]:
    data_root = Path(receipt_storage_root).resolve().parent.parent
    marker_dir = data_root / ".rezzerv-migrations"
    return (
        marker_dir / f"{MIGRATION_ID}.done.json",
        marker_dir / f"{MIGRATION_ID}.last.json",
    )


def _write_report(path: Path, report: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = path.with_suffix(path.suffix + ".tmp")
    tmp_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp_path.replace(path)


def list_safe_stale_receipt_candidates(engine, *, limit: int = 1000) -> list[dict[str, Any]]:
    """Return only stale receipts for which destructive reparse is state-safe.

    ``reparse_receipt`` replaces receipt line rows. Therefore a candidate is
    eligible only when every safety column is available and no user/business
    state refers to those rows. Missing safety schema means no candidates.
    """
    safe_limit = max(1, min(int(limit or 1000), 1000))
    with engine.begin() as conn:
        required_tables = {"receipt_tables", "raw_receipts", "receipt_table_lines"}
        if not all(_table_exists(conn, table_name) for table_name in required_tables):
            return []

        rt_columns = _columns(conn, "receipt_tables")
        rr_columns = _columns(conn, "raw_receipts")
        rtl_columns = _columns(conn, "receipt_table_lines")
        if not _REQUIRED_RECEIPT_COLUMNS.issubset(rt_columns):
            return []
        if not _REQUIRED_RAW_COLUMNS.issubset(rr_columns):
            return []
        if not _REQUIRED_LINE_COLUMNS.issubset(rtl_columns):
            return []

        line_blockers = [
            "rtl.corrected_raw_label IS NOT NULL",
            "rtl.corrected_quantity IS NOT NULL",
            "rtl.corrected_unit IS NOT NULL",
            "rtl.corrected_unit_price IS NOT NULL",
            "rtl.corrected_line_total IS NOT NULL",
            "rtl.matched_article_id IS NOT NULL",
            "rtl.matched_global_product_id IS NOT NULL",
            "COALESCE(rtl.is_deleted, 0) <> 0",
            "COALESCE(rtl.is_validated, 0) <> 0",
        ]
        receipt_guards = [
            "lower(trim(COALESCE(rt.parse_status, ''))) = 'review_needed'",
            "rt.deleted_at IS NULL",
            "rr.deleted_at IS NULL",
            "rt.approved_at IS NULL",
            "rt.reviewed_at IS NULL",
            "COALESCE(TRIM(rt.corrected_by_user_email), '') = ''",
            "COALESCE(rt.totals_overridden, 0) = 0",
            "NOT EXISTS (SELECT 1 FROM receipt_table_lines rtl "
            "WHERE rtl.receipt_table_id = rt.id AND ("
            + " OR ".join(line_blockers)
            + "))",
        ]

        if _table_exists(conn, "purchase_import_batches"):
            receipt_guards.append(
                "NOT EXISTS (SELECT 1 FROM purchase_import_batches pib "
                "WHERE pib.source_type = 'receipt' "
                "AND pib.source_reference = ('receipt:' || rt.id))"
            )

        if _table_exists(conn, "inventory_events"):
            receipt_guards.append(
                "NOT EXISTS (SELECT 1 FROM inventory_events ie "
                "WHERE ie.source_reference = ('receipt:' || rt.id))"
            )

        rows = conn.execute(
            text(
                f"""
                SELECT rt.id AS receipt_table_id,
                       rt.household_id,
                       rt.parse_status,
                       rt.line_count AS previous_line_count,
                       rr.original_filename,
                       rr.storage_path,
                       rr.sha256_hash
                FROM receipt_tables rt
                JOIN raw_receipts rr ON rr.id = rt.raw_receipt_id
                WHERE {' AND '.join(receipt_guards)}
                ORDER BY datetime(COALESCE(rt.updated_at, rt.created_at)) ASC, rt.id ASC
                LIMIT :limit
                """
            ),
            {"limit": safe_limit},
        ).mappings().all()
    return [dict(row) for row in rows]


def run_safe_stale_receipt_recovery(
    engine,
    receipt_storage_root: Path,
    *,
    limit: int = 1000,
) -> dict[str, Any]:
    """Run the versioned recovery once and persist an audit report next to the DB."""
    done_path, last_path = _marker_paths(receipt_storage_root)
    if not _enabled():
        return {"migration_id": MIGRATION_ID, "status": "disabled"}
    if done_path.exists():
        try:
            return json.loads(done_path.read_text(encoding="utf-8"))
        except Exception:
            return {"migration_id": MIGRATION_ID, "status": "already_completed"}

    started_at = _utc_now()
    candidates = list_safe_stale_receipt_candidates(engine, limit=limit)
    results: list[dict[str, Any]] = []
    errors: list[dict[str, Any]] = []

    for candidate in candidates:
        receipt_table_id = str(candidate.get("receipt_table_id") or "").strip()
        storage_path = Path(str(candidate.get("storage_path") or ""))
        if not receipt_table_id:
            continue
        if not storage_path.exists():
            errors.append(
                {
                    "receipt_table_id": receipt_table_id,
                    "original_filename": candidate.get("original_filename"),
                    "previous_line_count": candidate.get("previous_line_count"),
                    "error": f"raw source missing: {storage_path}",
                }
            )
            continue
        try:
            result = reparse_receipt(engine, receipt_storage_root, receipt_table_id) or {}
            results.append(
                {
                    "receipt_table_id": receipt_table_id,
                    "original_filename": candidate.get("original_filename"),
                    "previous_line_count": candidate.get("previous_line_count"),
                    "parse_status": result.get("parse_status"),
                    "line_count": result.get("line_count"),
                }
            )
        except Exception as exc:
            errors.append(
                {
                    "receipt_table_id": receipt_table_id,
                    "original_filename": candidate.get("original_filename"),
                    "previous_line_count": candidate.get("previous_line_count"),
                    "error": str(exc),
                }
            )

    report = {
        "migration_id": MIGRATION_ID,
        "status": "completed" if not errors else "completed_with_errors",
        "started_at": started_at,
        "finished_at": _utc_now(),
        "candidate_count": len(candidates),
        "reparsed_count": len(results),
        "approved_count": sum(
            1 for item in results if str(item.get("parse_status") or "").lower() == "approved"
        ),
        "still_review_needed_count": sum(
            1
            for item in results
            if str(item.get("parse_status") or "").lower() == "review_needed"
        ),
        "error_count": len(errors),
        "results": results,
        "errors": errors,
    }
    _write_report(last_path, report)
    _write_report(done_path, report)
    return report
