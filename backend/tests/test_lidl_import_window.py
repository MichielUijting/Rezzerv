"""Focused Lidl household import-window tests without a substitute database."""
from datetime import date, timedelta
from unittest.mock import MagicMock
import pytest

from app.services.lidl_import_window_service import get_window, save_window, record_import_date


def _engine(row=None):
    engine = MagicMock()
    engine.connect.return_value.__enter__.return_value.execute.return_value.mappings.return_value.first.return_value = row
    return engine


def test_default_window_and_household_checkpoint():
    today = date.today()
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


def test_import_checkpoint_ignores_invalid_and_future_dates():
    engine = _engine()
    record_import_date(engine, "h", "not-a-date")
    record_import_date(engine, "h", "2099-01-01T12:00:00")
    engine.begin.assert_not_called()
    record_import_date(engine, "h", "2026-10-01T12:00:00")
    assert engine.begin.called
    assert engine.begin.return_value.__enter__.return_value.execute.call_args.args[1]["day"] == date(2026, 10, 1)
