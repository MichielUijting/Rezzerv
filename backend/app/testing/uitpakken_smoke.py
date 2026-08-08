"""
Technical Design Reference:
- TD Section: TD-08 Test, baseline en regressie
- Module Role: Uitpakken smoke test
- Runtime Type: test
- Status Authority: no
- Refactor Status: keep_test

Smoke-test voor de Uitpakken-keten op een tijdelijke, losstaande SQLite-
testdatabase. De normale Rezzerv-database wordt niet gelezen, niet gekopieerd
en niet gewijzigd.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from backend.app.testing.uitpakken_test_db import (
    LINE_PASTA_ID,
    SPACE_KEUKEN_ID,
    SUBLOCATION_KEUKEN_VOORRAADKAST_ID,
    assign_target_location,
    fetch_one,
    process_line_to_inventory,
    seed_summary,
    temporary_uitpakken_database,
)


PROJECT_ROOT = Path(__file__).resolve().parents[3]
REPORT_PATH = PROJECT_ROOT / "uitpakken_smoke_report.json"


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def passed_result(case_id: str, description: str, details: dict[str, Any] | None = None) -> dict[str, Any]:
    return {
        "case_id": case_id,
        "description": description,
        "status": "passed",
        "error": None,
        "details": details or {},
    }


def failed_result(case_id: str, description: str, error: str, details: dict[str, Any] | None = None) -> dict[str, Any]:
    return {
        "case_id": case_id,
        "description": description,
        "status": "failed",
        "error": error,
        "details": details or {},
    }


def build_report(results: list[dict[str, Any]], db_removed: bool) -> dict[str, Any]:
    failed_count = sum(1 for item in results if item.get("status") != "passed")
    passed_count = sum(1 for item in results if item.get("status") == "passed")

    return {
        "test_type": "uitpakken_smoke",
        "status": "passed" if failed_count == 0 and db_removed else "failed",
        "ran_at": utc_now(),
        "acceptance_basis": (
            "Uitpakken smoke-test in tijdelijke aparte SQLite-testdatabase. "
            "De normale Rezzerv-database wordt niet gelezen, niet gekopieerd en niet gewijzigd."
        ),
        "summary": {
            "required_case_count": 8,
            "tested_case_count": len(results),
            "passed_count": passed_count,
            "failed_count": failed_count,
            "blocked_count": 0 if db_removed else 1,
        },
        "results": results,
        "blocking_issues": [] if db_removed else ["tijdelijke database is na afloop nog aanwezig"],
    }


def run_smoke() -> dict[str, Any]:
    results: list[dict[str, Any]] = []
    db_path_after: Path | None = None

    try:
        with temporary_uitpakken_database(prefix="rezzerv_uitpakken_smoke_") as db:
            db_path_after = db.path

            if db.path.exists():
                results.append(passed_result("U-SM-01", "tijdelijke database bestaat tijdens testrun", {"db_path": str(db.path)}))
            else:
                results.append(failed_result("U-SM-01", "tijdelijke database bestaat tijdens testrun", "databasebestand ontbreekt tijdens run"))

            summary_before = seed_summary(db.conn)
            expected_seed = {
                "households": 1,
                "spaces": 3,
                "sublocations": 3,
                "household_articles": 4,
                "household_article_settings": 4,
                "purchase_import_batches": 1,
                "purchase_import_lines": 5,
                "inventory_events": 0,
                "inventory": 0,
            }
            if summary_before == expected_seed:
                results.append(passed_result("U-SM-02", "basisfixtures zijn correct opgebouwd", {"seed_summary": summary_before}))
            else:
                results.append(failed_result("U-SM-02", "basisfixtures zijn correct opgebouwd", f"onverwachte seed_summary: {summary_before}", {"expected": expected_seed, "actual": summary_before}))

            line_before = fetch_one(db.conn, "select * from purchase_import_lines where id = ?", (LINE_PASTA_ID,))
            if line_before and line_before.get("matched_household_article_id") is not None:
                results.append(passed_result("U-SM-03", "smokeregel heeft gekoppeld huishoudelijk artikel", {"line_id": LINE_PASTA_ID, "article_id": line_before.get("matched_household_article_id")}))
            else:
                results.append(failed_result("U-SM-03", "smokeregel heeft gekoppeld huishoudelijk artikel", "matched_household_article_id ontbreekt"))

            assigned = assign_target_location(
                db.conn,
                LINE_PASTA_ID,
                location_id=SPACE_KEUKEN_ID,
                sublocation_id=SUBLOCATION_KEUKEN_VOORRAADKAST_ID,
            )
            if assigned.get("status") == "passed":
                results.append(passed_result("U-SM-04", "locatie met sublocatie kan worden toegewezen", assigned))
            else:
                results.append(failed_result("U-SM-04", "locatie met sublocatie kan worden toegewezen", str(assigned.get("error") or assigned), assigned))

            line_after_location = fetch_one(db.conn, "select target_location_id, target_sublocation_id from purchase_import_lines where id = ?", (LINE_PASTA_ID,))
            if (
                line_after_location
                and int(line_after_location.get("target_location_id") or 0) == SPACE_KEUKEN_ID
                and int(line_after_location.get("target_sublocation_id") or 0) == SUBLOCATION_KEUKEN_VOORRAADKAST_ID
            ):
                results.append(passed_result("U-SM-05", "doellocatie is op bonregel opgeslagen", dict(line_after_location)))
            else:
                results.append(failed_result("U-SM-05", "doellocatie is op bonregel opgeslagen", f"onverwachte doellocatie: {line_after_location}", dict(line_after_location or {})))

            processed = process_line_to_inventory(db.conn, LINE_PASTA_ID)
            if processed.get("status") == "processed":
                results.append(passed_result("U-SM-06", "complete regel wordt naar voorraad verwerkt", processed))
            else:
                results.append(failed_result("U-SM-06", "complete regel wordt naar voorraad verwerkt", str(processed.get("error") or processed), processed))

            event = fetch_one(db.conn, "select * from inventory_events where source_type = 'purchase_import_line' and source_id = ?", (LINE_PASTA_ID,))
            if event and float(event.get("quantity_delta") or 0) == 1.0:
                results.append(passed_result("U-SM-07", "voorraadevent is aangemaakt", dict(event)))
            else:
                results.append(failed_result("U-SM-07", "voorraadevent is aangemaakt", f"voorraadevent ontbreekt of is ongeldig: {event}", dict(event or {})))

            inventory = fetch_one(
                db.conn,
                """
                select *
                from inventory
                where household_article_id = ?
                  and location_id = ?
                  and sublocation_id = ?
                """,
                (
                    int(line_before["matched_household_article_id"]) if line_before else -1,
                    SPACE_KEUKEN_ID,
                    SUBLOCATION_KEUKEN_VOORRAADKAST_ID,
                ),
            )
            if inventory and float(inventory.get("quantity") or 0) == 1.0:
                results.append(passed_result("U-SM-08", "voorraadprojectie is bijgewerkt", dict(inventory)))
            else:
                results.append(failed_result("U-SM-08", "voorraadprojectie is bijgewerkt", f"inventory ontbreekt of is ongeldig: {inventory}", dict(inventory or {})))

            db.conn.commit()

    except Exception as exc:
        results.append(failed_result("U-SM-TECH", "technische uitvoering smoke-test", f"{type(exc).__name__}: {exc}"))

    db_removed = bool(db_path_after is not None and not db_path_after.exists())
    report = build_report(results, db_removed)
    REPORT_PATH.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    return report


def main() -> None:
    report = run_smoke()
    print(json.dumps(report, indent=2, ensure_ascii=False))
    if report.get("status") != "passed":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
