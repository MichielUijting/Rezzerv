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


def list_safe_stale_receipt_candidates(engine, *, limit: int = 100) -> list[dict[str, Any]]:
    """Return only stale receipts for which destructive reparse is state-safe.

    ``reparse_receipt`` replaces receipt line rows. Therefore a candidate is
    eligible only when no user/business state refers to those rows.
    """
    safe_limit = max(1, min(int(limit or 100), 1000))
    with engine.begin() as conn:
        if not (_table_exists(conn, "receipt_tables") and _table_exists(conn, "raw_receipts")):
            return []

        rt_columns = _columns(conn, "receipt_tables")
        rtl_columns = _columns(conn, "receipt_table_lines")

        receipt_guards = [
            "lower(trim(COALESCE(rt.parse_status, ''))) = 'review_needed'",
            "rt.deleted_at IS NULL" if "deleted_at" in rt_columns else "1 = 1",
            "rr.deleted_at IS NULL" if "deleted_at" in _columns(conn, "raw_receipts") else "1 = 1",
        ]
        if "approved_at" in rt_columns:
            receipt_guards.append("rt.approved_at IS NULL")
        if "reviewed_at" in rt_columns:
            receipt_guards.append("rt.reviewed_at IS NULL")
        if "corrected_by_user_email" in rt_columns:
            receipt_guards.append("COALESCE(TRIM(rt.corrected_by_user_email), '') = ''")
        if "totals_overridden" in rt_columns:
            receipt_guards.append("COALESCE(rt.totals_overridden, 0) = 0")

        line_blockers: list[str] = []
        for column_name in (
            "corrected_raw_label",
            "corrected_quantity",
            "corrected_unit",
            "corrected_unit_price",
            "corrected_line_total",
            "matched_article_id",
            "matched_global_product_id",
        ):
            if column_name in rtl_columns:
                line_blockers.append(f"rtl.{column_name} IS NOT NULL")
        if "is_deleted" in rtl_columns:
            line_blockers.append("COALESCE(rtl.is_deleted, 0) <> 0")
        if "is_validated" in rtl_columns:
            line_blockers.append("COALESCE(rtl.is_validated, 0) <> 0")

        if line_blockers:
            receipt_guards.append(
                "NOT EXISTS (SELECT 1 FROM receipt_table_lines rtl "
                "WHERE rtl.receipt_table_id = rt.id AND ("
                + " OR ".join(line_blockers)
                + "))"
            )

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
    limit: int = 100,
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
                    "parse_status": result.get("parse_status"),
                    "line_count": result.get("line_count"),
                }
            )
        except Exception as exc:
            errors.append(
                {
                    "receipt_table_id": receipt_table_id,
                    "original_filename": candidate.get("original_filename"),
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
