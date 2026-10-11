"""Lidl import window settings per household."""
from datetime import date, timedelta
from sqlalchemy import text


def get_window(engine, household_id):
    with engine.connect() as conn:
        row = conn.execute(text("SELECT from_date, to_date, last_imported_date FROM household_lidl_import_windows WHERE household_id=:id"), {"id": household_id}).mappings().first()
    data = dict(row or {})
    start = data.get("from_date")
    end = data.get("to_date")
    last = data.get("last_imported_date")
    today = date.today()
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
    if start and not end and start > date.today():
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


def record_import_date(engine, household_id, timestamp):
    if not isinstance(timestamp, str):
        return
    try:
        day = date.fromisoformat(timestamp[:10])
    except ValueError:
        return
    if day > date.today():
        return
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
        """), {"id": household_id, "day": day})
