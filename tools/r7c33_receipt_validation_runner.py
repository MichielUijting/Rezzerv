#!/usr/bin/env python3
"""
R7c33c backend-only receipt validation runner.

Purpose:
- Validate the receipt/Kassa/Uitpakken database basis without frontend, Playwright, Vite, ports or run-regression.mjs.
- Adapt canonical receipt concepts to the actual Rezzerv SQLite datamodel.
- Enforce SSOT boundaries: status is never inferred here; po_norm_status_label is only detected and counted when present.

This runner is intentionally read-only against a copied SQLite database.
"""

from __future__ import annotations

import json
import shutil
import sqlite3
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

# Canonical concepts used by the validation report, mapped to real Rezzerv table candidates.
# This is a datamodel adapter only. It must not introduce status logic.
CANONICAL_TABLES = {
    "receipts": ["raw_receipts", "receipts", "receipt_sources"],
    "receipt_batches": ["receipt_import_batches", "receipt_tables", "purchase_import_batches", "receipt_batches"],
    "receipt_lines": ["receipt_table_lines", "purchase_import_lines", "receipt_lines"],
    "inventory": ["inventory"],
    "inventory_events": ["inventory_events"],
    "household_articles": ["household_articles"],
}
REQUIRED_CANONICAL_TABLES = list(CANONICAL_TABLES.keys())
SSOT_LABELS = {"Gecontroleerd", "Controle nodig"}
SSOT_COLUMN = "po_norm_status_label"
DIAGNOSTIC_STATUS_COLUMN = "parse_status"


def now_stamp() -> str:
    return datetime.now().strftime("%Y%m%d_%H%M%S")


def json_default(value: Any) -> str:
    return str(value)


def quote_ident(name: str) -> str:
    return '"' + str(name).replace('"', '""') + '"'


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


def count_rows(conn: sqlite3.Connection, table: str | None, where: str | None = None) -> int | None:
    if not table:
        return None
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


def query_first(conn: sqlite3.Connection, sql: str, params: tuple[Any, ...] = ()) -> sqlite3.Row | None:
    try:
        return conn.execute(sql, params).fetchone()
    except sqlite3.Error:
        return None


def find_receipt_like_tables(tables: list[str]) -> list[str]:
    return [name for name in tables if "receipt" in name.lower() or "kassa" in name.lower() or "purchase_import" in name.lower()]


def resolve_table_map(tables: list[str]) -> dict[str, str | None]:
    table_set = set(tables)
    resolved: dict[str, str | None] = {}
    for canonical, candidates in CANONICAL_TABLES.items():
        resolved[canonical] = next((candidate for candidate in candidates if candidate in table_set), None)
    return resolved


def check_database_basis(conn: sqlite3.Connection, tables: list[str], table_map: dict[str, str | None]) -> dict[str, Any]:
    missing = [canonical for canonical in REQUIRED_CANONICAL_TABLES if not table_map.get(canonical)]
    return {
        "ok": not missing,
        "required_canonical_tables": REQUIRED_CANONICAL_TABLES,
        "canonical_table_candidates": CANONICAL_TABLES,
        "resolved_table_map": table_map,
        "missing_canonical_tables": missing,
        "receipt_like_tables": find_receipt_like_tables(tables),
    }


def count_active_archived_receipts(conn: sqlite3.Connection, receipt_table: str | None) -> dict[str, Any]:
    if not receipt_table:
        return {"active_receipts": None, "archived_or_deleted_receipts": None, "archive_columns": []}
    columns = table_columns(conn, receipt_table)
    archive_cols = [col for col in columns if any(token in col.lower() for token in ["archiv", "delete", "deleted", "removed"])]
    result: dict[str, Any] = {"archive_columns": archive_cols}
    if not archive_cols:
        result["active_receipts"] = count_rows(conn, receipt_table)
        result["archived_or_deleted_receipts"] = 0
        return result
    active_where = " AND ".join(
        f"COALESCE({quote_ident(col)}, 0) IN (0, '0', 'false', 'FALSE', '')" for col in archive_cols
    )
    archived_where = " OR ".join(
        f"COALESCE({quote_ident(col)}, 0) NOT IN (0, '0', 'false', 'FALSE', '')" for col in archive_cols
    )
    result["active_receipts"] = count_rows(conn, receipt_table, active_where)
    result["archived_or_deleted_receipts"] = count_rows(conn, receipt_table, archived_where)
    return result


def check_counts(conn: sqlite3.Connection, table_map: dict[str, str | None]) -> dict[str, Any]:
    receipt_table = table_map.get("receipts")
    batch_table = table_map.get("receipt_batches")
    line_table = table_map.get("receipt_lines")
    counts: dict[str, Any] = {
        "resolved_table_map": table_map,
        "receipts": count_rows(conn, receipt_table),
        "receipt_batches": count_rows(conn, batch_table),
        "receipt_lines": count_rows(conn, line_table),
        "inventory": count_rows(conn, table_map.get("inventory")),
        "inventory_events": count_rows(conn, table_map.get("inventory_events")),
        "household_articles": count_rows(conn, table_map.get("household_articles")),
    }
    counts.update(count_active_archived_receipts(conn, receipt_table))
    return counts


def find_column_locations(conn: sqlite3.Connection, tables: list[str], column_name: str) -> list[dict[str, str]]:
    locations = []
    wanted = column_name.lower()
    for table in tables:
        for column in table_columns(conn, table):
            if column.lower() == wanted:
                locations.append({"table": table, "column": column})
    return locations


def check_ssot_status_contract(conn: sqlite3.Connection, tables: list[str]) -> dict[str, Any]:
    # SSOT rule: this runner does not derive status. It only detects and counts po_norm_status_label when present.
    po_norm_locations = find_column_locations(conn, tables, SSOT_COLUMN)
    parse_status_locations = [
        location for location in find_column_locations(conn, tables, DIAGNOSTIC_STATUS_COLUMN)
    ]
    evidence = []
    found_labels: Counter[str] = Counter()
    for location in po_norm_locations:
        table = location["table"]
        column = location["column"]
        values = safe_distinct_counts(conn, table, column)
        for item in values:
            if item.get("value") in SSOT_LABELS:
                found_labels[str(item.get("value"))] += int(item.get("count") or 0)
        evidence.append({"table": table, "column": column, "values": values})
    missing_labels = sorted(label for label in SSOT_LABELS if found_labels[label] <= 0)
    return {
        "ok": bool(po_norm_locations) and not missing_labels,
        "po_norm_status_label_locations": po_norm_locations,
        "parse_status_locations": parse_status_locations,
        "found_labels": dict(found_labels),
        "missing_required_labels": missing_labels,
        "evidence": evidence,
        "ssot_rule": "Status wordt hier niet berekend. Alleen po_norm_status_label wordt geteld; parse_status is diagnostisch.",
    }


def find_batch_fk(line_columns: list[str]) -> str | None:
    preferred = ["batch_id", "receipt_import_batch_id", "receipt_batch_id", "receipt_table_id", "raw_receipt_id", "receipt_id"]
    for column in preferred:
        if column in line_columns:
            return column
    for column in line_columns:
        low = column.lower()
        if "batch" in low or "receipt" in low and low.endswith("_id"):
            return column
    return None


def structural_complete_expr(columns: list[str]) -> str | None:
    # No status derivation. Completeness here means structural line content exists for fixture readiness.
    name_cols = [col for col in columns if any(token in col.lower() for token in ["article", "product", "name", "description", "omschrijving"])]
    amount_cols = [col for col in columns if any(token in col.lower() for token in ["price", "amount", "total", "subtotal", "bedrag", "prijs"])]
    parts = []
    if name_cols:
        parts.append("(" + " OR ".join(f"COALESCE(trim(CAST({quote_ident(col)} AS TEXT)), '') <> ''" for col in name_cols) + ")")
    if amount_cols:
        parts.append("(" + " OR ".join(f"COALESCE(trim(CAST({quote_ident(col)} AS TEXT)), '') <> ''" for col in amount_cols) + ")")
    if not parts:
        return None
    return " AND ".join(parts)


def structural_incomplete_expr(columns: list[str]) -> str | None:
    # No status derivation. Incompleteness here means a line lacks structural product/name content or amount content.
    name_cols = [col for col in columns if any(token in col.lower() for token in ["article", "product", "name", "description", "omschrijving"])]
    amount_cols = [col for col in columns if any(token in col.lower() for token in ["price", "amount", "total", "subtotal", "bedrag", "prijs"])]
    missing_parts = []
    if name_cols:
        missing_parts.append("(" + " AND ".join(f"COALESCE(trim(CAST({quote_ident(col)} AS TEXT)), '') = ''" for col in name_cols) + ")")
    if amount_cols:
        missing_parts.append("(" + " AND ".join(f"COALESCE(trim(CAST({quote_ident(col)} AS TEXT)), '') = ''" for col in amount_cols) + ")")
    if not missing_parts:
        return None
    return " OR ".join(missing_parts)


def check_fixture_readiness(conn: sqlite3.Connection, table_map: dict[str, str | None], ssot: dict[str, Any]) -> dict[str, Any]:
    line_table = table_map.get("receipt_lines")
    batch_table = table_map.get("receipt_batches")
    if not line_table:
        return {"ok": False, "detail": "Geen gemapte receipt line tabel gevonden", "checks": {"resolved_table_map": table_map}}
    line_cols = table_columns(conn, line_table)
    batch_fk = find_batch_fk(line_cols)
    complete_expr = structural_complete_expr(line_cols)
    incomplete_expr = structural_incomplete_expr(line_cols)
    checks: dict[str, Any] = {
        "line_table": line_table,
        "batch_table": batch_table,
        "batch_fk": batch_fk,
        "line_columns": line_cols,
        "complete_expr_type": "structural_content_only_no_status",
        "incomplete_expr_type": "structural_missing_content_only_no_status",
        "complete_expr_available": bool(complete_expr),
        "incomplete_expr_available": bool(incomplete_expr),
    }
    if complete_expr:
        row = query_first(conn, f"SELECT COUNT(*) AS n FROM {quote_ident(line_table)} WHERE {complete_expr}")
        checks["complete_line_count"] = int(row["n"] if row else 0)
    else:
        checks["complete_line_count"] = None
    if incomplete_expr:
        row = query_first(conn, f"SELECT COUNT(*) AS n FROM {quote_ident(line_table)} WHERE {incomplete_expr}")
        checks["incomplete_line_count"] = int(row["n"] if row else 0)
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
    export_cols = [col for col in line_cols if any(token in col.lower() for token in ["price", "amount", "total", "name", "article", "product", "description", "omschrijving"])]
    checks["exportable_signal_columns"] = export_cols
    if export_cols:
        expr = " OR ".join(f"COALESCE(trim(CAST({quote_ident(col)} AS TEXT)), '') <> ''" for col in export_cols)
        row = query_first(conn, f"SELECT COUNT(*) AS n FROM {quote_ident(line_table)} WHERE {expr}")
        checks["exportable_line_count"] = int(row["n"] if row else 0)
    else:
        checks["exportable_line_count"] = None
    checks["has_gecontroleerd_fixture"] = ssot["found_labels"].get("Gecontroleerd", 0) > 0
    checks["has_controle_nodig_fixture"] = ssot["found_labels"].get("Controle nodig", 0) > 0
    failures = []
    if checks.get("complete_line_count") in (None, 0):
        failures.append("geen structureel complete receiptregel gevonden")
    if checks.get("incomplete_line_count") in (None, 0):
        failures.append("geen structureel incomplete receiptregel gevonden")
    if not checks.get("batch_with_complete_and_incomplete_line"):
        failures.append("geen batch met minimaal 1 structureel complete en 1 structureel incomplete regel gevonden")
    if checks.get("exportable_line_count") in (None, 0):
        failures.append("geen exporteerbare receiptregel gevonden")
    if not checks.get("has_gecontroleerd_fixture"):
        failures.append("geen po_norm_status_label='Gecontroleerd' fixture gevonden")
    if not checks.get("has_controle_nodig_fixture"):
        failures.append("geen po_norm_status_label='Controle nodig' fixture gevonden")
    return {"ok": not failures, "detail": "ok" if not failures else "; ".join(failures), "checks": checks}


def build_report() -> dict[str, Any]:
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    source = next((candidate for candidate in DB_CANDIDATES if candidate.exists()), None)
    report: dict[str, Any] = {
        "runner": "R7c33 receipt validation",
        "version": "R7c33c datamodel adapter",
        "started_at": datetime.now().isoformat(timespec="seconds"),
        "source_candidates": [str(path.relative_to(ROOT)) for path in DB_CANDIDATES],
        "status": "failed",
        "checks": {},
        "failures": [],
        "ssot_guard": "No status derivation; po_norm_status_label is the only accepted status label source.",
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
        table_map = resolve_table_map(tables)
        ssot = check_ssot_status_contract(conn, tables)
        report["tables"] = tables
        report["resolved_table_map"] = table_map
        report["checks"]["database_basis"] = check_database_basis(conn, tables, table_map)
        report["checks"]["counts"] = check_counts(conn, table_map)
        report["checks"]["ssot_status_contract"] = ssot
        report["checks"]["fixture_readiness"] = check_fixture_readiness(conn, table_map, ssot)
    for name, check in report["checks"].items():
        if isinstance(check, dict) and not check.get("ok", True):
            detail = check.get("detail") or check.get("missing_canonical_tables") or "niet voldaan"
            report["failures"].append(f"{name}: {detail}")
    report["status"] = "passed" if not report["failures"] else "failed"
    report["finished_at"] = datetime.now().isoformat(timespec="seconds")
    return report


def write_reports(report: dict[str, Any]) -> None:
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    REPORT_JSON.write_text(json.dumps(report, indent=2, ensure_ascii=False, default=json_default), encoding="utf-8")
    lines = []
    lines.append(f"R7c33 receipt validation: {report['status']}")
    lines.append(f"Runner: {report.get('version', 'onbekend')}")
    lines.append(f"Database: {report.get('source_database', 'niet gevonden')}")
    if report.get("database_copy"):
        lines.append(f"Kopie: {report['database_copy']}")
    if report.get("resolved_table_map"):
        lines.append("")
        lines.append("Datamodel mapping:")
        for canonical, actual in report["resolved_table_map"].items():
            lines.append(f"- {canonical} -> {actual or 'NIET GEVONDEN'}")
    lines.append("")
    if report.get("failures"):
        lines.append("Fouten:")
        for failure in report["failures"]:
            lines.append(f"- {failure}")
    else:
        lines.append("Alle backend-only receipt-validaties zijn geslaagd.")
    lines.append("")
    lines.append("SSOT:")
    lines.append("- Status wordt niet berekend in deze runner.")
    lines.append("- Alleen po_norm_status_label wordt als statuslabelbron geaccepteerd.")
    lines.append("- parse_status wordt uitsluitend als diagnostische locatie gerapporteerd.")
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
