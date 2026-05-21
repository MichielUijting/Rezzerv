#!/usr/bin/env python3
"""R7c35c raw runtime dump for receipt status baseline details.

Analyse-only. No OCR, parser, SSOT, frontend or database changes.

Purpose: dump the exact runtime structure returned by
validate_receipt_status_baseline().details so diagnosis routing can be fixed
based on evidence instead of assumptions.
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
REPORT_DIR = ROOT / "reports" / "receipt_analysis"
DB_CANDIDATES = [ROOT / "backend" / "rezzerv.db", ROOT / "rezzerv.db", ROOT / "backend" / "rezzerv_test_temp.db"]


def stamp() -> str:
    return datetime.now().strftime("%Y%m%d_%H%M%S")


def write_json(path: Path, payload: Any) -> None:
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False, default=str), encoding="utf-8")


def load_db_copy() -> Path:
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    source = next((candidate for candidate in DB_CANDIDATES if candidate.exists()), None)
    if not source:
        raise SystemExit("Geen SQLite database gevonden")
    target = REPORT_DIR / f"rezzerv-receipt-status-details-{stamp()}.db"
    shutil.copy2(source, target)
    return target


def run_dump(db_copy: Path) -> dict[str, Any]:
    if str(BACKEND_DIR) not in sys.path:
        sys.path.insert(0, str(BACKEND_DIR))
    os.environ["DATABASE_URL"] = f"sqlite:///{db_copy.as_posix()}"

    from sqlalchemy import create_engine
    from app.services.receipt_status_baseline_service import validate_receipt_status_baseline

    engine = create_engine(f"sqlite:///{db_copy.as_posix()}")
    with engine.connect() as conn:
        validation = validate_receipt_status_baseline(conn, household_id="1")

    details = validation.get("details") or []
    result_counter = Counter(str(item.get("result") or "<missing>") for item in details)
    difference_type_counter = Counter(str(item.get("difference_type") or "<missing>") for item in details)
    actual_status_counter = Counter(str(item.get("actual_status_label") or "<missing>") for item in details)
    expected_status_counter = Counter(str(item.get("expected_status_label") or "<missing>") for item in details)

    different_items = [item for item in details if item.get("result") == "different"]
    unmatched_different_items = [
        item for item in different_items
        if not item.get("difference_type")
    ]

    return {
        "runner": "R7c35c raw receipt status details dump",
        "started_at": datetime.now().isoformat(timespec="seconds"),
        "database_copy": str(db_copy.relative_to(ROOT)),
        "status": "completed",
        "summary": validation.get("summary") or {},
        "details_count": len(details),
        "result_counter": dict(result_counter),
        "difference_type_counter": dict(difference_type_counter),
        "actual_status_counter": dict(actual_status_counter),
        "expected_status_counter": dict(expected_status_counter),
        "different_count": len(different_items),
        "different_without_difference_type_count": len(unmatched_different_items),
        "detail_keys_counter": dict(Counter(tuple(sorted(item.keys())) for item in details)),
        "different_items_full": different_items,
        "different_without_difference_type_full": unmatched_different_items,
        "details_full": details,
    }


def write_summary(report: dict[str, Any], path: Path) -> None:
    lines = [
        "R7c35c raw receipt status details dump: completed",
        f"Databasekopie: {report.get('database_copy')}",
        "",
        "Counters:",
        f"- details_count: {report.get('details_count')}",
        f"- result_counter: {report.get('result_counter')}",
        f"- difference_type_counter: {report.get('difference_type_counter')}",
        f"- actual_status_counter: {report.get('actual_status_counter')}",
        f"- expected_status_counter: {report.get('expected_status_counter')}",
        f"- different_count: {report.get('different_count')}",
        f"- different_without_difference_type_count: {report.get('different_without_difference_type_count')}",
        "",
        "Different items:",
    ]
    for item in report.get("different_items_full") or []:
        lines.append(
            "- "
            + f"source_file={item.get('source_file')} | "
            + f"result={item.get('result')} | "
            + f"difference_type={item.get('difference_type')} | "
            + f"expected={item.get('expected_status_label')} | "
            + f"actual={item.get('actual_status_label')} | "
            + f"reason={item.get('difference_reason') or item.get('reason')} | "
            + f"decision={item.get('decision_reason')}"
        )
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("\n".join(lines))


def main() -> int:
    db_copy = load_db_copy()
    report = run_dump(db_copy)
    report_json = REPORT_DIR / "r7c35c_receipt_status_details_dump.json"
    report_txt = REPORT_DIR / "r7c35c_receipt_status_details_dump_summary.txt"
    write_json(report_json, report)
    write_summary(report, report_txt)
    print("")
    print("Rapporten:")
    print(f"- {report_json.relative_to(ROOT)}")
    print(f"- {report_txt.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
