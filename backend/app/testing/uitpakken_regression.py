"""
Technical Design Reference:
- TD Section: TD-08 Test, baseline en regressie
- Module Role: Uitpakken regression test
- Runtime Type: test
- Status Authority: no
- Refactor Status: keep_test

Volledige regressietest voor de Uitpakken-keten op tijdelijke, losstaande
SQLite-testdatabases. Iedere case draait geïsoleerd. De normale Rezzerv-
database wordt niet gelezen, niet gekopieerd en niet gewijzigd.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from backend.app.testing.uitpakken_test_db import (
    ARTICLE_MELK_ID,
    ARTICLE_PASTA_ID,
    ARTICLE_TOMATEN_ID,
    ARTICLE_TOILETPAPIER_ID,
    LINE_MELK_ID,
    LINE_ONBEKEND_ID,
    LINE_PASTA_ID,
    LINE_TOILETPAPIER_ID,
    LINE_TOMATEN_ID,
    SPACE_BERGING_ID,
    SPACE_KEUKEN_ID,
    SUBLOCATION_KEUKEN_KOELKAST_ID,
    SUBLOCATION_KEUKEN_VOORRAADKAST_ID,
    apply_article_default_to_line,
    assign_target_location,
    fetch_all,
    fetch_one,
    get_article_default_location,
    process_line_to_inventory,
    temporary_uitpakken_database,
)


PROJECT_ROOT = Path(__file__).resolve().parents[3]
REPORT_PATH = PROJECT_ROOT / "uitpakken_regression_report.json"
REQUIRED_CASE_COUNT = 12


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def count_rows(conn, table_name: str) -> int:
    if not table_name.replace("_", "").isalnum():
        raise ValueError(f"Unsafe table name: {table_name}")
    row = fetch_one(conn, f"select count(*) as count from {table_name}")
    return int(row["count"] if row else 0)


def passed(case_id: str, description: str, details: dict[str, Any] | None = None) -> dict[str, Any]:
    return {
        "case_id": case_id,
        "description": description,
        "status": "passed",
        "error": None,
        "details": details or {},
    }


def failed(case_id: str, description: str, error: str, details: dict[str, Any] | None = None) -> dict[str, Any]:
    return {
        "case_id": case_id,
        "description": description,
        "status": "failed",
        "error": error,
        "details": details or {},
    }


def run_isolated_case(case_id: str, description: str, func: Callable[[Any], dict[str, Any]]) -> dict[str, Any]:
    db_path_after = None
    try:
        with temporary_uitpakken_database(prefix=f"rezzerv_uitpakken_{case_id.lower()}_") as db:
            db_path_after = db.path
            result = func(db.conn)
            db.conn.commit()

        removed = bool(db_path_after is not None and not db_path_after.exists())
        if not removed:
            return failed(case_id, description, "tijdelijke database is na afloop nog aanwezig", {"db_path": str(db_path_after)})
        if result.get("status") != "passed":
            return failed(case_id, description, str(result.get("error") or result), result)
        return passed(case_id, description, result)
    except Exception as exc:
        return failed(case_id, description, f"{type(exc).__name__}: {exc}")


def case_01_space_without_sublocation(conn) -> dict[str, Any]:
    assigned = assign_target_location(conn, LINE_PASTA_ID, location_id=SPACE_BERGING_ID)
    processed = process_line_to_inventory(conn, LINE_PASTA_ID)
    inventory = fetch_one(
        conn,
        """
        select *
        from inventory
        where household_article_id = ?
          and location_id = ?
          and sublocation_id is null
        """,
        (ARTICLE_PASTA_ID, SPACE_BERGING_ID),
    )
    ok = (
        assigned.get("status") == "passed"
        and processed.get("status") == "processed"
        and inventory
        and float(inventory.get("quantity") or 0) == 1.0
    )
    return {
        "status": "passed" if ok else "failed",
        "error": None if ok else "ruimte zonder sublocatie is niet correct verwerkt",
        "assigned": assigned,
        "processed": processed,
        "inventory": dict(inventory or {}),
    }


def case_02_space_with_sublocation(conn) -> dict[str, Any]:
    assigned = assign_target_location(
        conn,
        LINE_PASTA_ID,
        location_id=SPACE_KEUKEN_ID,
        sublocation_id=SUBLOCATION_KEUKEN_VOORRAADKAST_ID,
    )
    processed = process_line_to_inventory(conn, LINE_PASTA_ID)
    inventory = fetch_one(
        conn,
        """
        select *
        from inventory
        where household_article_id = ?
          and location_id = ?
          and sublocation_id = ?
        """,
        (ARTICLE_PASTA_ID, SPACE_KEUKEN_ID, SUBLOCATION_KEUKEN_VOORRAADKAST_ID),
    )
    ok = (
        assigned.get("status") == "passed"
        and processed.get("status") == "processed"
        and inventory
        and float(inventory.get("quantity") or 0) == 1.0
    )
    return {
        "status": "passed" if ok else "failed",
        "error": None if ok else "ruimte met sublocatie is niet correct verwerkt",
        "assigned": assigned,
        "processed": processed,
        "inventory": dict(inventory or {}),
    }


def case_03_missing_required_sublocation(conn) -> dict[str, Any]:
    assigned = assign_target_location(conn, LINE_PASTA_ID, location_id=SPACE_KEUKEN_ID)
    line = fetch_one(conn, "select target_location_id, target_sublocation_id from purchase_import_lines where id = ?", (LINE_PASTA_ID,))
    ok = (
        assigned.get("status") == "blocked"
        and assigned.get("error") == "missing_required_sublocation_id"
        and line
        and line.get("target_location_id") is None
        and line.get("target_sublocation_id") is None
    )
    return {
        "status": "passed" if ok else "failed",
        "error": None if ok else "ruimte met sublocaties zonder sublocatie werd niet correct geblokkeerd",
        "assigned": assigned,
        "line": dict(line or {}),
    }


def case_04_incidental_location_does_not_update_default(conn) -> dict[str, Any]:
    before = get_article_default_location(conn, ARTICLE_TOMATEN_ID)
    assigned = assign_target_location(
        conn,
        LINE_TOMATEN_ID,
        location_id=SPACE_BERGING_ID,
        default_location_policy="line_only",
    )
    after = get_article_default_location(conn, ARTICLE_TOMATEN_ID)
    ok = before == (None, None) and after == (None, None) and assigned.get("status") == "passed"
    return {
        "status": "passed" if ok else "failed",
        "error": None if ok else "incidentele locatie heeft artikeldefault onterecht gewijzigd",
        "before_default": before,
        "after_default": after,
        "assigned": assigned,
    }


def case_05_default_location_without_sublocation(conn) -> dict[str, Any]:
    assigned = assign_target_location(
        conn,
        LINE_TOMATEN_ID,
        location_id=SPACE_BERGING_ID,
        default_location_policy="article_default",
    )
    default = get_article_default_location(conn, ARTICLE_TOMATEN_ID)
    ok = assigned.get("status") == "passed" and assigned.get("standard_location_updated") is True and default == (SPACE_BERGING_ID, None)
    return {
        "status": "passed" if ok else "failed",
        "error": None if ok else "standaardlocatie zonder sublocatie is niet correct opgeslagen",
        "default": default,
        "assigned": assigned,
    }


def case_06_default_location_with_sublocation(conn) -> dict[str, Any]:
    assigned = assign_target_location(
        conn,
        LINE_TOMATEN_ID,
        location_id=SPACE_KEUKEN_ID,
        sublocation_id=SUBLOCATION_KEUKEN_KOELKAST_ID,
        default_location_policy="article_default",
    )
    default = get_article_default_location(conn, ARTICLE_TOMATEN_ID)
    ok = (
        assigned.get("status") == "passed"
        and assigned.get("standard_location_updated") is True
        and default == (SPACE_KEUKEN_ID, SUBLOCATION_KEUKEN_KOELKAST_ID)
    )
    return {
        "status": "passed" if ok else "failed",
        "error": None if ok else "standaardlocatie met sublocatie is niet correct opgeslagen",
        "default": default,
        "assigned": assigned,
    }


def case_07_existing_default_applies_to_new_line(conn) -> dict[str, Any]:
    applied = apply_article_default_to_line(conn, LINE_MELK_ID)
    line = fetch_one(conn, "select target_location_id, target_sublocation_id from purchase_import_lines where id = ?", (LINE_MELK_ID,))
    ok = (
        applied.get("status") == "passed"
        and line
        and int(line.get("target_location_id") or 0) == SPACE_KEUKEN_ID
        and int(line.get("target_sublocation_id") or 0) == SUBLOCATION_KEUKEN_KOELKAST_ID
    )
    return {
        "status": "passed" if ok else "failed",
        "error": None if ok else "bestaande artikeldefault is niet toegepast op nieuwe regel",
        "applied": applied,
        "line": dict(line or {}),
    }


def case_08_line_without_article_is_blocked(conn) -> dict[str, Any]:
    assigned = assign_target_location(conn, LINE_ONBEKEND_ID, location_id=SPACE_BERGING_ID)
    processed = process_line_to_inventory(conn, LINE_ONBEKEND_ID)
    ok = assigned.get("status") == "passed" and processed.get("status") == "blocked" and processed.get("error") == "missing_household_article"
    return {
        "status": "passed" if ok else "failed",
        "error": None if ok else "regel zonder artikel werd niet correct geblokkeerd",
        "assigned": assigned,
        "processed": processed,
    }


def case_09_line_without_location_is_blocked(conn) -> dict[str, Any]:
    processed = process_line_to_inventory(conn, LINE_PASTA_ID)
    ok = processed.get("status") == "blocked" and processed.get("error") == "missing_target_location_id"
    return {
        "status": "passed" if ok else "failed",
        "error": None if ok else "regel zonder locatie werd niet correct geblokkeerd",
        "processed": processed,
    }


def case_10_multiple_complete_lines_process(conn) -> dict[str, Any]:
    assign_a = assign_target_location(conn, LINE_PASTA_ID, location_id=SPACE_BERGING_ID)
    assign_b = assign_target_location(
        conn,
        LINE_TOMATEN_ID,
        location_id=SPACE_KEUKEN_ID,
        sublocation_id=SUBLOCATION_KEUKEN_VOORRAADKAST_ID,
    )
    processed_a = process_line_to_inventory(conn, LINE_PASTA_ID)
    processed_b = process_line_to_inventory(conn, LINE_TOMATEN_ID)
    events = count_rows(conn, "inventory_events")
    inventory_rows = count_rows(conn, "inventory")
    ok = (
        assign_a.get("status") == "passed"
        and assign_b.get("status") == "passed"
        and processed_a.get("status") == "processed"
        and processed_b.get("status") == "processed"
        and events == 2
        and inventory_rows == 2
    )
    return {
        "status": "passed" if ok else "failed",
        "error": None if ok else "meerdere complete regels zijn niet correct verwerkt",
        "assign_a": assign_a,
        "assign_b": assign_b,
        "processed_a": processed_a,
        "processed_b": processed_b,
        "inventory_events": events,
        "inventory_rows": inventory_rows,
    }


def case_11_processed_line_is_not_processed_twice(conn) -> dict[str, Any]:
    assigned = assign_target_location(conn, LINE_PASTA_ID, location_id=SPACE_BERGING_ID)
    first = process_line_to_inventory(conn, LINE_PASTA_ID)
    second = process_line_to_inventory(conn, LINE_PASTA_ID)
    events = count_rows(conn, "inventory_events")
    inventory = fetch_one(
        conn,
        """
        select *
        from inventory
        where household_article_id = ?
          and location_id = ?
          and sublocation_id is null
        """,
        (ARTICLE_PASTA_ID, SPACE_BERGING_ID),
    )
    ok = (
        assigned.get("status") == "passed"
        and first.get("status") == "processed"
        and second.get("status") == "skipped"
        and second.get("error") == "already_processed"
        and events == 1
        and inventory
        and float(inventory.get("quantity") or 0) == 1.0
    )
    return {
        "status": "passed" if ok else "failed",
        "error": None if ok else "verwerkte regel werd dubbel verwerkt",
        "assigned": assigned,
        "first": first,
        "second": second,
        "inventory_events": events,
        "inventory": dict(inventory or {}),
    }


def case_12_bulk_sublocation_assignment(conn) -> dict[str, Any]:
    target_lines = [LINE_PASTA_ID, LINE_MELK_ID, LINE_TOMATEN_ID]
    assignments = [
        assign_target_location(
            conn,
            line_id,
            location_id=SPACE_KEUKEN_ID,
            sublocation_id=SUBLOCATION_KEUKEN_VOORRAADKAST_ID,
        )
        for line_id in target_lines
    ]
    rows = fetch_all(
        conn,
        """
        select id, target_location_id, target_sublocation_id
        from purchase_import_lines
        where id in (?, ?, ?)
        order by id
        """,
        tuple(target_lines),
    )
    ok = all(item.get("status") == "passed" for item in assignments) and all(
        int(row.get("target_location_id") or 0) == SPACE_KEUKEN_ID
        and int(row.get("target_sublocation_id") or 0) == SUBLOCATION_KEUKEN_VOORRAADKAST_ID
        for row in rows
    )
    return {
        "status": "passed" if ok else "failed",
        "error": None if ok else "bulklocatie met sublocatie is niet correct toegepast",
        "assignments": assignments,
        "rows": rows,
    }


CASES: list[tuple[str, str, Callable[[Any], dict[str, Any]]]] = [
    ("U-RG-01", "ruimte zonder sublocaties verwerken", case_01_space_without_sublocation),
    ("U-RG-02", "ruimte met sublocatie verwerken", case_02_space_with_sublocation),
    ("U-RG-03", "ruimte met sublocaties zonder sublocatie blokkeren", case_03_missing_required_sublocation),
    ("U-RG-04", "incidentele locatiekeuze slaat geen artikeldefault op", case_04_incidental_location_does_not_update_default),
    ("U-RG-05", "standaardlocatie zonder sublocatie opslaan", case_05_default_location_without_sublocation),
    ("U-RG-06", "standaardlocatie met sublocatie opslaan", case_06_default_location_with_sublocation),
    ("U-RG-07", "nieuwe regel gebruikt bestaande artikeldefault", case_07_existing_default_applies_to_new_line),
    ("U-RG-08", "regel zonder artikel blokkeren", case_08_line_without_article_is_blocked),
    ("U-RG-09", "regel zonder locatie blokkeren", case_09_line_without_location_is_blocked),
    ("U-RG-10", "meerdere complete regels verwerken", case_10_multiple_complete_lines_process),
    ("U-RG-11", "verwerkte regel niet dubbel verwerken", case_11_processed_line_is_not_processed_twice),
    ("U-RG-12", "bulklocatie met sublocatie toepassen", case_12_bulk_sublocation_assignment),
]


def build_report(results: list[dict[str, Any]]) -> dict[str, Any]:
    failed_count = sum(1 for item in results if item.get("status") != "passed")
    passed_count = sum(1 for item in results if item.get("status") == "passed")
    return {
        "test_type": "uitpakken_regression",
        "status": "passed" if failed_count == 0 and len(results) == REQUIRED_CASE_COUNT else "failed",
        "ran_at": utc_now(),
        "acceptance_basis": (
            "Vaste Uitpakken-regressieset in tijdelijke aparte SQLite-testdatabases. "
            "Iedere case bouwt eigen fixtures op en verwijdert de database na afloop. "
            "De normale Rezzerv-database wordt niet gelezen, niet gekopieerd en niet gewijzigd."
        ),
        "summary": {
            "required_case_count": REQUIRED_CASE_COUNT,
            "tested_case_count": len(results),
            "passed_count": passed_count,
            "failed_count": failed_count,
            "blocked_count": 0,
        },
        "results": results,
        "blocking_issues": [],
    }


def run_regression() -> dict[str, Any]:
    results = [run_isolated_case(case_id, description, func) for case_id, description, func in CASES]
    report = build_report(results)
    REPORT_PATH.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    return report


def main() -> None:
    report = run_regression()
    print(json.dumps(report, indent=2, ensure_ascii=False))
    if report.get("status") != "passed":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
