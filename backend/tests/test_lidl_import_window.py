"""Focused Lidl household import-window tests without a substitute database."""
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo
from unittest.mock import MagicMock
import pytest

from app.services.lidl_import_window_service import get_window, save_window, complete_import


def _engine(row=None):
    engine = MagicMock()
    engine.connect.return_value.__enter__.return_value.execute.return_value.mappings.return_value.first.return_value = row
    return engine


def test_default_window_and_household_checkpoint():
    today = datetime.now(ZoneInfo('Europe/Amsterdam')).date()
    automatic = get_window(_engine(), "household-1")
    assert automatic["from_date"] == (today - timedelta(days=30)).isoformat()
    assert automatic["to_date"] == today.isoformat()
    assert automatic["automatic_from"] is True

    latest = get_window(_engine({"last_imported_date": date(2026, 10, 1)}), "household-2")
    assert latest["from_date"] == "2026-10-01"
    assert latest["last_imported_date"] == "2026-10-01"


def test_manual_window_and_isolation():
    values = {"from_date": "2026-01-01", "to_date": "2026-02-01"}
    window = get_window(_engine(values), "household-1")
    assert window["from_date"] == "2026-01-01"
    assert window["to_date"] == "2026-02-01"
    assert window["automatic_from"] is False
    assert get_window(_engine(), "household-2")["automatic_from"] is True


def test_reverse_period_is_rejected_before_sql():
    engine = _engine()
    with pytest.raises(ValueError):
        save_window(engine, "household-1", date(2026, 10, 10), date(2026, 10, 1))
    engine.begin.assert_not_called()


def test_import_checkpoint_requires_completed_automatic_window():
    engine = _engine()
    today = datetime.now(ZoneInfo("Europe/Amsterdam")).date()
    start = today - timedelta(days=30)
    complete_import(engine, "h", today, start, today)
    assert engine.begin.called
    assert engine.begin.return_value.__enter__.return_value.execute.call_args.args[1]["day"] == today


def test_partial_run_does_not_advance_checkpoint():
    # Individual receipt imports deliberately do not call complete_import.
    engine = _engine()
    assert get_window(engine, "h")["last_imported_date"] is None
    engine.begin.assert_not_called()


def test_wrong_window_or_future_checkpoint_fails_closed():
    engine = _engine()
    today = datetime.now(ZoneInfo("Europe/Amsterdam")).date()
    with pytest.raises(ValueError):
        complete_import(engine, "h", today, today - timedelta(days=31), today)
    with pytest.raises(ValueError):
        complete_import(engine, "h", today + timedelta(days=1), today - timedelta(days=30), today)
    engine.begin.assert_not_called()


def test_historical_manual_backfill_does_not_advance_auto_cursor():
    engine = _engine({"from_date": date(2024, 3, 1), "to_date": date(2024, 3, 31)})
    complete_import(engine, "h", date(2024, 3, 11), date(2024, 3, 1), date(2024, 3, 31))
    engine.begin.assert_not_called()
