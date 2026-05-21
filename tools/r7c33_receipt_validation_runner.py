#!/usr/bin/env python3
"""
R7c33b backend-only receipt validation runner.

Purpose:
- Validate the receipt/Kassa/Uitpakken database basis without frontend, Playwright, Vite, ports or run-regression.mjs.
- Produce deterministic diagnostics for receipt fixtures and SSOT status-contract readiness.

This runner is intentionally read-only against a copied SQLite database.
"""

from __future__ import annotations

import json
import shutil
import sqlite3
import sys
from collections import Counter
from datetime import datetime
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
REPORT_DIR = ROOT / "reports" / "receipt_validation"
REPORT_JSON = REPORT_DIR / "r7c33_receipt_validation_report.json"
REPORT_TXT = REPORT_DIR / "r7c33_receipt_validation_summary.txt"
DB_CANDIDATES = [
    ROOT / "backend" / "rezzerv.db",
    ROOT / "rezzerv.db",
    ROOT / "backend" / "rezzerv_test_temp.db",
]
REQUIRED_TABLES = [
    "receipts",
    "receipt_lines",
    "receipt_batches",
    "inventory",
    "inventory_events",
    "household_articles",
]
SSOT_LABELS = {"Gecontroleerd", "Controle nodig"}


def now_stamp() -> str:
    return datetime.now().strftime("%Y%m%d_%H%M%S")


def json_default(value: Any) -> str:
    return str(value)


def connect(db_path: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    return conn


def list_tables(conn: sqlite3.Connection) -> list[str]:
    rows = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name"
    ).fetchall()
    return [str(row["name"]) for row in rows]


def table_columns(conn: sqlite3.Connection, table: str) -> list[str]:
    try:
        return [str(row["name"]) for row in conn.execute(f"PRAGMA table_info({quote_ident(table)})").fetchall()]
    except sqlite3.Error:
        return []


def quote_ident(name: str) -> str:
    return '"' + str(name).replace('"', '""') + '"'


def count_rows(conn: sqlite3.Connection, table: str, where: str | None = None) -> int | None:
    try:
        sql = f"SELECT COUNT(*) AS n FROM {quote_ident(table)}"
        if where:
            sql += f" WHERE {where}"
        row = conn.execute(sql).fetchone()
        return int(row["n"] if row else 0)
    except sqlite3.Error:
        return None


def safe_distinct_counts(conn: sqlite3.Connection, table: str, column: str, limit: int = 25) -> list[dict[str, Any]]:
    try:
        rows = conn.execute(
            f"""
            SELECT {quote_ident(column)} AS value, COUNT(*) AS count
            FROM {quote_ident(table)}
            GROUP BY {quote_ident(column)}
            ORDER BY count DESC, value ASC
            LIMIT ?
            """,
            (limit,),
        ).fetchall()
        return [{"value": row["value"], "count": int(row["count"])} for row in rows]
    except sqlite3.Error:
        return []


def pick_existing_table(tables: set[str], candidates: list[str]) -> str | None:
    for candidate in candidates:
        if candidate in tables:
            return candidate
    return None


def find_receipt_like_tables(tables: list[str]) -> list[str]:
    return [name for name in tables if "receipt" in name.lower() or "kassa" in name.lower()]


def find_columns(columns: list[str], keywords: list[str]) -> list[str]:
    lowered = [(col, col.lower()) for col in columns]
    hits = []
    for col, low in lowered:
        if any(keyword.lower() in low for keyword in keywords):
            hits.append(col)
    return hits


def query_first(conn: sqlite3.Connection, sql: str, params: tuple[Any, ...] = ()) -> sqlite3.Row | None:
    try:
        return conn.execute(sql, params).fetchone()
    except sqlite3.Error:
        return None


def query_all(conn: sqlite3.Connection, sql: str, params: tuple[Any, ...] = ()) -> list[sqlite3.Row]:
    try:
        return conn.execute(sql, params).fetchall()
    except sqlite3.Error:
        return []


def bool_result(ok: bool, detail: str, data: Any = None) -> dict[str, Any]:
    return {"ok": bool(ok), "detail": detail, "data": data}


def infer_line_completeness_expr(columns: list[str]) -> str | None:
    candidates = []
    for col in columns:
        low = col.lower()
        if low in {"is_complete", "complete", "is_completed", "completed"}:
            candidates.append(f"COALESCE({quote_ident(col)}, 0) IN (1, '1', 'true', 'TRUE', 'yes', 'YES')")
        if "status" in low:
            candidates.append(
                f"lower(COALESCE({quote_ident(col)}, '')) IN ('complete', 'completed', 'ready', 'gecontroleerd', 'ok')"
            )
        if "article" in low or "product" in low:
            # Product/article presence is a practical proxy for a complete receipt line in fixture checks.
            candidates.append(f"COALESCE(trim(CAST({quote_ident(col)} AS TEXT)), '') <> ''")
    if not candidates:
        return None
    return " OR ".join(f"({candidate})" for candidate in candidates)


def infer_line_incomplete_expr(columns: list[str]) -> str | None:
    candidates = []
    for col in columns:
        low = col.lower()
        if low in {"is_complete", "complete", "is_completed", "completed"}:
            candidates.append(f"COALESCE({quote_ident(col)}, 0) IN (0, '0', 'false', 'FALSE', 'no', 'NO')")
        if "status" in low:
            candidates.append(
                f"lower(COALESCE({quote_ident(col)}, '')) IN ('incomplete', 'partial', 'needs_review', 'controle nodig', 'review_needed')"
            )
        if "article" in low or "product" in low:
            candidates.append(f"COALESCE(trim(CAST({quote_ident(col)} AS TEXT)), '') = ''")
    if not candidates:
        return None
    return " OR ".join(f"({candidate})" for candidate in candidates)


def find_batch_fk(line_columns: list[str], batch_table: str | None) -> str | None:
    preferred = [
        "batch_id",
        "receipt_batch_id",
        "receipt_id",
        "receipt_upload_id",
        "receipt_batch",
    ]
    for col in preferred:
        if col in line_columns:
            return col
    for col in line_columns:
        low = col.lower()
        if "batch" in low or low in {"receipt_id", "receiptid"}:
            return col
    return None


def check_database_basis(conn: sqlite3.Connection, tables: list[str]) -> dict[str, Any]:
    table_set = set(tables)
    missing = [table for table in REQUIRED_TABLES if table not in table_set]
    return {
        "ok": not missing,
        "required_tables": REQUIRED_TABLES,
        "missing_tables": missing,
        "receipt_like_tables": find_receipt_like_tables(tables),
    }


def check_counts(conn: sqlite3.Connection, tables: list[str]) -> dict[str, Any]:
    table_set = set(tables)
    receipt_table = pick_existing_table(table_set, ["receipts", "receipt_uploads", "receipt_batches"])
    batch_table = pick_existing_table(table_set, ["receipt_batches", "receipts", "receipt_uploads"])
    line_table = pick_existing_table(table_set, ["receipt_lines", "receipt_items", "receipt_batch_lines"])
    counts: dict[str, Any] = {
        "receipt_table": receipt_table,
        "batch_table": batch_table,
        "line_table": line_table,
        "receipt_batches": count_rows(conn, batch_table) if batch_table else None,
        "receipt_lines": count_rows(conn, line_table) if line_table else None,
        "receipts": count_rows(conn, receipt_table) if receipt_table else None,
    }
    if receipt_table:
        receipt_cols = table_columns(conn, receipt_table)
        status_cols = find_columns(receipt_cols, ["status"])
        archive_cols = find_columns(receipt_cols, ["archiv", "delete", "deleted", "removed"])
        counts["receipt_status_columns"] = status_cols
        counts["receipt_archive_columns"] = archive_cols
        if status_cols:
            counts["receipt_status_counts"] = {col: safe_distinct_counts(conn, receipt_table, col) for col in status_cols}
        if archive_cols:
            active_where = " AND ".join(
                f"COALESCE({quote_ident(col)}, 0) IN (0, '0', 'false', 'FALSE', '')" for col in archive_cols
            )
            archived_where = " OR ".join(
                f"COALESCE({quote_ident(col)}, 0) NOT IN (0, '0', 'false', 'FALSE', '')" for col in archive_cols
            )
            counts["active_receipts"] = count_rows(conn, receipt_table, active_where)
            counts["archived_or_deleted_receipts"] = count_rows(conn, receipt_table, archived_where)
    return counts


def check_ssot_status_contract(conn: sqlite3.Connection, tables: list[str]) -> dict[str, Any]:
    table_set = set(tables)
    receipt_candidates = [name for name in ["receipts", "receipt_batches", "receipt_uploads"] if name in table_set]
    evidence = []
    found_labels = Counter()
    parse_status_locations = []
    po_norm_locations = []

    for table in receipt_candidates:
        cols = table_columns(conn, table)
        for col in cols:
            low = col.lower()
            if col == "po_norm_status_label" or low.endswith("po_norm_status_label"):
                po_norm_locations.append({"table": table, "column": col})
                values = safe_distinct_counts(conn, table, col)
                for item in values:
                    if item.get("value") in SSOT_LABELS:
                        found_labels[str(item.get("value"))] += int(item.get("count") or 0)
                evidence.append({"table": table, "column": col, "values": values})
            if "parse_status" in low:
                parse_status_locations.append({"table": table, "column": col})

    missing_labels = sorted(label for label in SSOT_LABELS if found_labels[label] <= 0)
    return {
        "ok": bool(po_norm_locations) and not missing_labels,
        "po_norm_status_label_locations": po_norm_locations,
        "parse_status_locations": parse_status_locations,
        "found_labels": dict(found_labels),
        "missing_required_labels": missing_labels,
        "evidence": evidence,
        "note": "parse_status mag alleen technische diagnostiek zijn en niet als UI-statusbron gelden.",
    }


def check_fixture_readiness(conn: sqlite3.Connection, tables: list[str]) -> dict[str, Any]:
    table_set = set(tables)
    batch_table = pick_existing_table(table_set, ["receipt_batches", "receipts", "receipt_uploads"])
    line_table = pick_existing_table(table_set, ["receipt_lines", "receipt_items", "receipt_batch_lines"])
    if not line_table:
        return {"ok": False, "detail": "Geen receipt line tabel gevonden", "checks": {}}

    line_cols = table_columns(conn, line_table)
    batch_fk = find_batch_fk(line_cols, batch_table)
    complete_expr = infer_line_completeness_expr(line_cols)
    incomplete_expr = infer_line_incomplete_expr(line_cols)
    checks: dict[str, Any] = {
        "line_table": line_table,
        "batch_table": batch_table,
        "batch_fk": batch_fk,
        "line_columns": line_cols,
        "complete_expr_available": bool(complete_expr),
        "incomplete_expr_available": bool(incomplete_expr),
    }

    if complete_expr:
        complete_count = query_first(conn, f"SELECT COUNT(*) AS n FROM {quote_ident(line_table)} WHERE {complete_expr}")
        checks["complete_line_count"] = int(complete_count["n"] if complete_count else 0)
    else:
        checks["complete_line_count"] = None

    if incomplete_expr:
        incomplete_count = query_first(conn, f"SELECT COUNT(*) AS n FROM {quote_ident(line_table)} WHERE {incomplete_expr}")
        checks["incomplete_line_count"] = int(incomplete_count["n"] if incomplete_count else 0)
    else:
        checks["incomplete_line_count"] = None

    if batch_fk and complete_expr and incomplete_expr:
        row = query_first(
            conn,
            f"""
            SELECT {quote_ident(batch_fk)} AS batch_id,
                   SUM(CASE WHEN {complete_expr} THEN 1 ELSE 0 END) AS complete_n,
                   SUM(CASE WHEN {incomplete_expr} THEN 1 ELSE 0 END) AS incomplete_n,
                   COUNT(*) AS total_n
            FROM {quote_ident(line_table)}
            WHERE COALESCE(trim(CAST({quote_ident(batch_fk)} AS TEXT)), '') <> ''
            GROUP BY {quote_ident(batch_fk)}
            HAVING complete_n >= 1 AND incomplete_n >= 1
            ORDER BY total_n DESC
            LIMIT 1
            """,
        )
        checks["batch_with_complete_and_incomplete_line"] = dict(row) if row else None
    else:
        checks["batch_with_complete_and_incomplete_line"] = None

    exportable_cols = [col for col in line_cols if any(k in col.lower() for k in ["price", "amount", "total", "name", "article", "product"])]
    checks["exportable_signal_columns"] = exportable_cols
    if exportable_cols:
        expr = " OR ".join(f"COALESCE(trim(CAST({quote_ident(col)} AS TEXT)), '') <> ''" for col in exportable_cols)
        row = query_first(conn, f"SELECT COUNT(*) AS n FROM {quote_ident(line_table)} WHERE {expr}")
        checks["exportable_line_count"] = int(row["n"] if row else 0)
    else:
        checks["exportable_line_count"] = None

    ssot = check_ssot_status_contract(conn, tables)
    checks["has_gecontroleerd_fixture"] = ssot["found_labels"].get("Gecontroleerd", 0) > 0
    checks["has_controle_nodig_fixture"] = ssot["found_labels"].get("Controle nodig", 0) > 0

    failures = []
    if checks.get("complete_line_count") in (None, 0):
        failures.append("geen complete receiptregel gevonden")
    if checks.get("incomplete_line_count") in (None, 0):
        failures.append("geen incomplete/controle-nodig receiptregel gevonden")
    if not checks.get("batch_with_complete_and_incomplete_line"):
        failures.append("geen batch met minimaal 1 complete en 1 incomplete regel gevonden")
    if checks.get("exportable_line_count") in (None, 0):
        failures.append("geen exporteerbare receiptregel gevonden")
    if not checks.get("has_gecontroleerd_fixture"):
        failures.append("geen receipt met status Gecontroleerd gevonden")
    if not checks.get("has_controle_nodig_fixture"):
        failures.append("geen receipt met status Controle nodig gevonden")

    return {"ok": not failures, "detail": "ok" if not failures else "; ".join(failures), "checks": checks}


def build_report() -> dict[str, Any]:
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    source = next((candidate for candidate in DB_CANDIDATES if candidate.exists()), None)
    report: dict[str, Any] = {
        "runner": "R7c33 receipt validation",
        "started_at": datetime.now().isoformat(timespec="seconds"),
        "source_candidates": [str(path.relative_to(ROOT)) for path in DB_CANDIDATES],
        "status": "failed",
        "checks": {},
        "failures": [],
    }
    if not source:
        report["failures"].append("Geen SQLite database gevonden in backend/rezzerv.db, rezzerv.db of backend/rezzerv_test_temp.db")
        return report

    db_copy = REPORT_DIR / f"rezzerv-receipt-validation-{now_stamp()}.db"
    shutil.copy2(source, db_copy)
    report["source_database"] = str(source.relative_to(ROOT))
    report["database_copy"] = str(db_copy.relative_to(ROOT))

    with connect(db_copy) as conn:
        tables = list_tables(conn)
        report["tables"] = tables
        report["checks"]["database_basis"] = check_database_basis(conn, tables)
        report["checks"]["counts"] = check_counts(conn, tables)
        report["checks"]["ssot_status_contract"] = check_ssot_status_contract(conn, tables)
        report["checks"]["fixture_readiness"] = check_fixture_readiness(conn, tables)

    for name, check in report["checks"].items():
        if isinstance(check, dict) and not check.get("ok", True):
            detail = check.get("detail") or check.get("missing_tables") or "niet voldaan"
            report["failures"].append(f"{name}: {detail}")

    report["status"] = "passed" if not report["failures"] else "failed"
    report["finished_at"] = datetime.now().isoformat(timespec="seconds")
    return report


def write_reports(report: dict[str, Any]) -> None:
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    REPORT_JSON.write_text(json.dumps(report, indent=2, ensure_ascii=False, default=json_default), encoding="utf-8")
    lines = []
    lines.append(f"R7c33 receipt validation: {report['status']}")
    lines.append(f"Database: {report.get('source_database', 'niet gevonden')}")
    if report.get("database_copy"):
        lines.append(f"Kopie: {report['database_copy']}")
    lines.append("")
    if report.get("failures"):
        lines.append("Fouten:")
        for failure in report["failures"]:
            lines.append(f"- {failure}")
    else:
        lines.append("Alle backend-only receipt-validaties zijn geslaagd.")
    lines.append("")
    lines.append("Rapporten:")
    lines.append(f"- {REPORT_JSON.relative_to(ROOT)}")
    lines.append(f"- {REPORT_TXT.relative_to(ROOT)}")
    REPORT_TXT.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("\n".join(lines))


def main() -> int:
    report = build_report()
    write_reports(report)
    return 0 if report["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
