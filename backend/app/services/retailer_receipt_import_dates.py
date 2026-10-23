"""Read-only, household-scoped dates for digital retailer receipt imports.

Only the existing receipt sources and Lidl's acknowledged history checkpoint are
read. No provider credentials, receipt bodies or user-facing fallback dates live
in this service.
"""
from __future__ import annotations

from datetime import date, datetime
from sqlalchemy import text
from sqlalchemy.engine import Engine


def _iso_date(value) -> str | None:
    if isinstance(value, datetime):
        return value.date().isoformat()
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, str):
        try:
            return date.fromisoformat(value[:10]).isoformat()
        except ValueError:
            return None
    return None


def latest_retailer_import_dates(engine: Engine, *, household_id: str) -> dict[str, str | None]:
    """Report only dates supported by persisted, scoped data.

    Jumbo: latest saved non-deleted digital receipt (import date).
    Lidl: latest saved receipt OR the acknowledged scan checkpoint.
    The frontend decides how to present a never-imported retailer.
    """
    household = str(household_id)
    result: dict[str, str | None] = {"jumbo": None, "lidl": None}
    with engine.connect() as conn:
        for provider in result:
            recorded = conn.execute(
                text("""
                    SELECT MAX(created_at)
                    FROM raw_receipts
                    WHERE household_id = :household_id
                      AND source_id = :source_id
                      AND deleted_at IS NULL
                """),
                {
                    "household_id": household,
                    "source_id": f"{household}-retailer-{provider}",
                },
            ).scalar_one_or_none()
            result[provider] = _iso_date(recorded)

        lidl_checkpoint = conn.execute(
            text("""
                SELECT last_imported_date
                FROM household_lidl_import_windows
                WHERE household_id = :household_id
            """),
            {"household_id": household},
        ).scalar_one_or_none()
        lidl_day = _iso_date(lidl_checkpoint)
        if lidl_day and (result["lidl"] is None or lidl_day > result["lidl"]):
            result["lidl"] = lidl_day
    return result
