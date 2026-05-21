#!/usr/bin/env python3
"""R7c33d backend-only receipt validation runner.

This tool does not start frontend, Playwright, Vite or API servers.
It validates the local SQLite receipt basis and calls the backend SSOT service.

SSOT guard:
- The runner never derives receipt status.
- app.services.receipt_status_baseline_service.validate_receipt_status_baseline is the only status source.
- parse_status is reported only as a diagnostic database field.
"""

from __future__ import annotations

import json
import os
import shutil
import sqlite3
import sys
from collections import Counter
from datetime import datetime
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
BACKEND_DIR = ROOT / "backend"
REPORT_DIR = ROOT / "reports" / "receipt_validation"
REPORT_JSON = REPORT_DIR / "r7c33_receipt_validation_report.json"
REPORT_TXT = REPORT_DIR / "r7c33_receipt_validation_summary.txt"
DB_CANDIDATES = [ROOT / "backend" / "rezzerv.db", ROOT / "rezzerv.db", ROOT / "backend" / "rezzerv_test_temp.db"]
CANONICAL_TABLES = {
    "receipts": ["raw_receipts", "receipts", "receipt_sources"],
    "receipt_batches": ["receipt_import_batches", "receipt_tables", "purchase_import_batches", "receipt_batches"],
    "receipt_lines": ["receipt_table_lines", "purchase_import_lines", "receipt_lines"],
    "inventory": ["inventory"],
    "inventory_events": ["inventory_events"],
    "household_articles": ["household_articles"],
}
SSOT_LABELS = {"Gecontroleerd", "Controle nodig"}


def stamp() -> str:
    return datetime.now().strftime("%Y%m%d_%H%M%S")


def quote_ident(name: str) -> str:
    return '"' + str(name).replace('"', '""') + '"'


def sqlite_conn(path: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(str(path))
    conn.row_factory = sqlite3.Row
    return conn


def list_tables(conn: sqlite3.Connection) -> list[str]:
    return [
        str(row["name"])
        for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name").fetchall()
    ]


def columns(conn: sqlite3.Connection, table: str | None) -> list[str]:
    if not table:
        return []
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


def resolve_table_map(tables: list[str]) -> dict[str, str | None]:
    available = set(tables)
    return {key: next((candidate for candidate in candidates if candidate in available), None) for key, candidates in CANONICAL_TABLES.items()}


def column_locations(conn: sqlite3.Connection, tables: list[str], name: str) -> list[dict[str, str]]:
    wanted = name.lower()
    result = []
    for table in tables:
        for column in columns(conn, table):
            if column.lower() == wanted:
                result.append({"table": table, "column": column})
    return result


def active_archive_counts(conn: sqlite3.Connection, receipt_table: str | None) -> dict[str, Any]:
    if not receipt_table:
        return {"archive_columns": [], "active_receipts": None, "archived_or_deleted_receipts": None}
    archive_cols = [col for col in columns(conn, receipt_table) if any(token in col.lower() for token in ["archiv", "delete", "deleted", "removed"])]
    if not archive_cols:
        return {"archive_columns": [], "active_receipts": count_rows(conn, receipt_table), "archived_or_deleted_receipts": 0}
    active_where = " AND ".join(f"COALESCE({quote_ident(col)}, 0) IN (0, '0', 'false', 'FALSE', '')" for col in archive_cols)
    archived_where = " OR ".join(f"COALESCE({quote_ident(col)}, 0) NOT IN (0, '0', 'false', 'FALSE', '')" for col in archive_cols)
    return {"archive_columns": archive_cols, "active_receipts": count_rows(conn, receipt_table, active_where), "archived_or_deleted_receipts": count_rows(conn, receipt_table, archived_where)}


def database_counts(conn: sqlite3.Connection, table_map: dict[str, str | None]) -> dict[str, Any]:
    data = {
        "resolved_table_map": table_map,
        "receipts": count_rows(conn, table_map.get("receipts")),
        "receipt_batches": count_rows(conn, table_map.get("receipt_batches")),
        "receipt_lines": count_rows(conn, table_map.get("receipt_lines")),
        "inventory": count_rows(conn, table_map.get("inventory")),
        "inventory_events": count_rows(conn, table_map.get("inventory_events")),
        "household_articles": count_rows(conn, table_map.get("household_articles")),
    }
    data.update(active_archive_counts(conn, table_map.get("receipts")))
    return data


def run_ssot_service(db_copy: Path) -> dict[str, Any]:
    if str(BACKEND_DIR) not in sys.path:
        sys.path.insert(0, str(BACKEND_DIR))
    os.environ["DATABASE_URL"] = f"sqlite:///{db_copy.as_posix()}"
    try:
        from sqlalchemy import create_engine
        from app.services.receipt_status_baseline_service import validate_receipt_status_baseline
    except Exception as exc:
        return {"ok": False, "error": f"SSOT-service kon niet worden geimporteerd: {exc}", "backend_status_counts": {}, "po_norm_status_counts": {}, "verschil": None}
    try:
        engine = create_engine(f"sqlite:///{db_copy.as_posix()}")
        with engine.connect() as conn:
            validation = validate_receipt_status_baseline(conn, household_id="1")
    except Exception as exc:
        return {"ok": False, "error": f"SSOT-service validatie faalde: {exc}", "backend_status_counts": {}, "po_norm_status_counts": {}, "verschil": None}
    details = validation.get("details") or []
    backend_counts: Counter[str] = Counter()
    for item in details:
        label = str(item.get("actual_status_label") or "").strip()
        if label:
            backend_counts[label] += 1
    po_norm_counts = dict(backend_counts)
    verschil = sum(abs(backend_counts.get(label, 0) - po_norm_counts.get(label, 0)) for label in set(backend_counts) | set(po_norm_counts))
    missing = sorted(label for label in SSOT_LABELS if po_norm_counts.get(label, 0) <= 0)
    return {
        "ok": verschil == 0 and not missing,
        "backend_status_counts": dict(backend_counts),
        "po_norm_status_counts": po_norm_counts,
        "verschil": verschil,
        "missing_required_labels": missing,
        "details_count": len(details),
        "validation_summary": validation.get("summary") or {},
        "source": "app.services.receipt_status_baseline_service.validate_receipt_status_baseline",
    }


def build_report() -> dict[str, Any]:
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    source = next((candidate for candidate in DB_CANDIDATES if candidate.exists()), None)
    report: dict[str, Any] = {
        "runner": "R7c33 receipt validation",
        "version": "R7c33d SSOT service output adapter",
        "started_at": datetime.now().isoformat(timespec="seconds"),
        "status": "failed",
        "failures": [],
        "source_candidates": [str(path.relative_to(ROOT)) for path in DB_CANDIDATES],
        "ssot_guard": "No status derivation; receipt_status_baseline_service is the only accepted status source.",
    }
    if not source:
        report["failures"].append("Geen SQLite database gevonden")
        return report
    db_copy = REPORT_DIR / f"rezzerv-receipt-validation-{stamp()}.db"
    shutil.copy2(source, db_copy)
    report["source_database"] = str(source.relative_to(ROOT))
    report["database_copy"] = str(db_copy.relative_to(ROOT))
    ssot = run_ssot_service(db_copy)
    with sqlite_conn(db_copy) as conn:
        tables = list_tables(conn)
        table_map = resolve_table_map(tables)
        missing_tables = [key for key, value in table_map.items() if not value]
        report["tables"] = tables
        report["resolved_table_map"] = table_map
        report["checks"] = {
            "database_basis": {"ok": not missing_tables, "missing_canonical_tables": missing_tables, "resolved_table_map": table_map},
            "counts": database_counts(conn, table_map),
            "ssot_status_contract": {
                "ok": bool(ssot.get("ok")),
                "backend_status_counts": ssot.get("backend_status_counts") or {},
                "po_norm_status_counts": ssot.get("po_norm_status_counts") or {},
                "verschil": ssot.get("verschil"),
                "missing_required_labels": ssot.get("missing_required_labels") or [],
                "db_po_norm_status_label_locations": column_locations(conn, tables, "po_norm_status_label"),
                "db_parse_status_locations": column_locations(conn, tables, "parse_status"),
                "ssot_service": ssot,
            },
        }
    if report["checks"]["database_basis"]["ok"] is not True:
        report["failures"].append(f"database_basis: {report['checks']['database_basis']['missing_canonical_tables']}")
    if report["checks"]["ssot_status_contract"]["ok"] is not True:
        report["failures"].append(f"ssot_status_contract: {report['checks']['ssot_status_contract'].get('missing_required_labels') or 'niet voldaan'}")
    report["status"] = "passed" if not report["failures"] else "failed"
    report["finished_at"] = datetime.now().isoformat(timespec="seconds")
    return report


def write_reports(report: dict[str, Any]) -> None:
    REPORT_JSON.write_text(json.dumps(report, indent=2, ensure_ascii=False, default=str), encoding="utf-8")
    ssot = report.get("checks", {}).get("ssot_status_contract", {})
    lines = [
        f"R7c33 receipt validation: {report['status']}",
        f"Runner: {report.get('version')}",
        f"Database: {report.get('source_database', 'niet gevonden')}",
        f"Kopie: {report.get('database_copy', '-')}",
        "",
        "Datamodel mapping:",
    ]
    for key, value in (report.get("resolved_table_map") or {}).items():
        lines.append(f"- {key} -> {value or 'NIET GEVONDEN'}")
    lines += [
        "",
        "SSOT-output:",
        f"- backend_status_counts: {ssot.get('backend_status_counts') or {}}",
        f"- po_norm_status_counts: {ssot.get('po_norm_status_counts') or {}}",
        f"- verschil: {ssot.get('verschil')}",
        "",
    ]
    if report.get("failures"):
        lines.append("Fouten:")
        lines.extend(f"- {failure}" for failure in report["failures"])
    else:
        lines.append("Alle backend-only receipt-validaties zijn geslaagd.")
    lines += [
        "",
        "SSOT:",
        "- Status wordt niet berekend in deze runner.",
        "- receipt_status_baseline_service is de enige statusbron.",
        "- parse_status wordt uitsluitend als diagnostische locatie gerapporteerd.",
        "",
        "Rapporten:",
        f"- {REPORT_JSON.relative_to(ROOT)}",
        f"- {REPORT_TXT.relative_to(ROOT)}",
    ]
    REPORT_TXT.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("\n".join(lines))


def main() -> int:
    report = build_report()
    write_reports(report)
    return 0 if report["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
