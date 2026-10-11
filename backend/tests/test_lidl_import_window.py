"""Focused tests for household Lidl import window, no Docker needed."""
from datetime import date, timedelta
from sqlalchemy import create_engine, text
from app.services.lidl_import_window_service import get_window, save_window, record_import_date


def _engine():
    engine = create_engine("sqlite+pysqlite:///:memory:")
    with engine.begin() as conn:
        conn.execute(text("""
            CREATE TABLE household_lidl_import_windows (
                household_id TEXT PRIMARY KEY,
                from_date DATE,
                to_date DATE,
                last_imported_date DATE,
                updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        """))
    return engine


def test_defaults_and_incremental_checkpoint():
    engine = _engine()
    start = get_window(engine, "a")
    assert start["automatic_from"] is True
    assert start["automatic_to"] is True
    assert start["to_date"] == date.today().isoformat()
    assert start["from_date"] == (date.today() - timedelta(days=30)).isoformat()
    record_import_date(engine, "a", "2026-10-01T12:30:00")
    record_import_date(engine, "a", "2026-09-15T13:30:00")
    changed = get_window(engine, "a")
    assert changed["from_date"] == "2026-10-01"
    assert changed["last_imported_date"] == "2026-10-01"


def test_manual_window_reset_preserves_checkpoint():
    engine = _engine()
    record_import_date(engine, "h1", "2026-09-11T10:00:00")
    custom = save_window(engine, "h1", date(2026, 1, 1), date(2026, 2, 1))
    assert custom["from_date"] == "2026-01-01"
    assert custom["to_date"] == "2026-02-01"
    assert get_window(engine, "h2")["configured_from_date"] is None
    automatic = save_window(engine, "h1", None, None)
    assert automatic["from_date"] == "2026-09-11"
    assert automatic["automatic_from"] is True


def test_bad_order_is_rejected():
    engine = _engine()
    try:
        save_window(engine, "h", date(2026, 10, 11), date(2026, 10, 1))
    except ValueError:
        pass
    else:
        raise AssertionError("Reverse window must fail")
