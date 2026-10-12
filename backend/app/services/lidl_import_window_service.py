"""Lidl import window settings per household."""
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo
from sqlalchemy import text


def _date(value):
    return date.fromisoformat(value) if isinstance(value, str) else value


def get_window(engine, household_id):
    with engine.connect() as conn:
        row = conn.execute(text("SELECT from_date, to_date, last_imported_date FROM household_lidl_import_windows WHERE household_id=:id"), {"id": household_id}).mappings().first()
    data = dict(row or {})
    start = _date(data.get("from_date"))
    end = _date(data.get("to_date"))
    last = _date(data.get("last_imported_date"))
    today = datetime.now(ZoneInfo('Europe/Amsterdam')).date()
    return {
        "from_date": (start or last or (today - timedelta(days=30))).isoformat(),
        "to_date": (end or today).isoformat(),
        "configured_from_date": start.isoformat() if start else None,
        "configured_to_date": end.isoformat() if end else None,
        "last_imported_date": last.isoformat() if last else None,
        "automatic_from": start is None,
        "automatic_to": end is None,
    }


def save_window(engine, household_id, start, end):
    if start and end and start > end:
        raise ValueError("Van-datum ligt na tot-datum.")
    if (start is None) != (end is None) and start is None:
        raise ValueError("Kies een van-datum bij een vaste tot-datum.")
    if start and not end and start > datetime.now(ZoneInfo('Europe/Amsterdam')).date():
        raise ValueError("Van-datum ligt in de toekomst.")
    with engine.begin() as conn:
        conn.execute(text("""
            INSERT INTO household_lidl_import_windows(household_id, from_date, to_date)
            VALUES (:id, :start, :end)
            ON CONFLICT(household_id) DO UPDATE
            SET from_date=EXCLUDED.from_date, to_date=EXCLUDED.to_date,
                updated_at=CURRENT_TIMESTAMP
        """), {"id": household_id, "start": start, "end": end})
    return get_window(engine, household_id)


def complete_import(engine, household_id, last_day, expected_start, expected_end):
    """Advance only after the browser confirmed a complete, acknowledged history scan.

    A manual date window/backfill must never skip receipts in automatic mode.
    The inclusive last date is re-scanned on the next run for idempotent recovery.
    """
    window = get_window(engine, household_id)
    if (window["from_date"], window["to_date"]) != (expected_start.isoformat(), expected_end.isoformat()):
        raise ValueError("Lidl-importperiode is tijdens het ophalen gewijzigd; start de import opnieuw.")
    if not window["automatic_from"] or not window["automatic_to"] or last_day is None:
        return window
    today = datetime.now(ZoneInfo("Europe/Amsterdam")).date()
    if not (expected_start <= last_day <= expected_end <= today):
        raise ValueError("Lidl-checkpoint valt buiten de gecontroleerde importperiode.")
    with engine.begin() as conn:
        conn.execute(text("""
            INSERT INTO household_lidl_import_windows(household_id, last_imported_date)
            VALUES (:id, :day)
            ON CONFLICT(household_id) DO UPDATE SET
            last_imported_date=CASE
                WHEN household_lidl_import_windows.last_imported_date IS NULL
                    OR household_lidl_import_windows.last_imported_date < EXCLUDED.last_imported_date
                THEN EXCLUDED.last_imported_date
                ELSE household_lidl_import_windows.last_imported_date END,
            updated_at=CURRENT_TIMESTAMP
        """), {"id": household_id, "day": last_day})
    return get_window(engine, household_id)
