"""Regression coverage: household next-shopping date drives Bijna op, not stock writes."""
from __future__ import annotations

import pytest

from app import main as api


@pytest.mark.parametrize("value,expected", [(None, 0), ("", 0), (0, 0), (3, 3), ("14", 14), (365, 365)])
def test_shopping_horizon_accepts_only_safe_days(value, expected):
    assert api.normalize_almost_out_shopping_days(value) == expected


@pytest.mark.parametrize("value", [-1, 366, "later", "3.5", 1.5, True])
def test_shopping_horizon_rejects_invalid_days(value):
    with pytest.raises(ValueError):
        api.normalize_almost_out_shopping_days(value)


def _evaluate(monkeypatch, *, shopping_days, prediction_enabled=False, prediction_days=0,
              min_stock=1, predicted_until=3, stock=4, prediction_available=True):
    calls = []
    monkeypatch.setattr(api, "get_household_product_inventory_rows", lambda *_: [{"quantity": stock}])
    monkeypatch.setattr(api, "get_household_product_event_rows", lambda *_: [])
    def fake_prediction(_conn, _household, _article, _name, **kwargs):
        calls.append(kwargs["prediction_days"])
        if not prediction_available:
            return None
        return {
            "prediction_available": True,
            "prediction_triggered": predicted_until <= kwargs["prediction_days"],
            "predicted_days_until_depletion": predicted_until,
            "prediction_threshold_days": kwargs["prediction_days"],
        }
    monkeypatch.setattr(api, "compute_household_product_prediction", fake_prediction)
    row = {"id": "article-1", "naam": "Melk", "min_stock": min_stock, "ideal_stock": 6}
    settings = {"shopping_days": shopping_days, "prediction_enabled": prediction_enabled,
                "prediction_days": prediction_days, "policy_mode": "advisory"}
    result = api.evaluate_household_article_almost_out(
        object(), "household-1", row, household_settings=settings, article_settings_map={}
    )
    return result, calls


def test_next_shopping_day_triggers_forecast_even_without_extra_prediction(monkeypatch):
    near, calls = _evaluate(monkeypatch, shopping_days=3)
    assert near["include_in_almost_out"] is True
    assert near["trigger_type"] == "predicted"
    assert near["shopping_days"] == 3
    assert near["effective_prediction_days"] == 3
    assert near["current_quantity"] == 4
    assert near["amount_to_buy"] == 2
    assert calls == [3]

    far, calls = _evaluate(monkeypatch, shopping_days=2)
    assert far["include_in_almost_out"] is False
    assert calls == [2]


def test_largest_horizon_applies_without_losing_existing_prediction(monkeypatch):
    selected, calls = _evaluate(monkeypatch, shopping_days=2, prediction_enabled=True,
                                prediction_days=7, predicted_until=5)
    assert selected["effective_prediction_days"] == 7
    assert selected["include_in_almost_out"] is True
    assert calls == [7]


def test_no_shop_date_and_disabled_prediction_preserve_legacy_stock_rule(monkeypatch):
    unchanged, calls = _evaluate(monkeypatch, shopping_days=0, min_stock=1)
    assert unchanged["include_in_almost_out"] is False
    assert calls == []

    stock, calls = _evaluate(monkeypatch, shopping_days=0, min_stock=4)
    assert stock["include_in_almost_out"] is True
    assert stock["trigger_type"] == "stock"
    assert calls == []


def test_no_prediction_history_falls_back_to_minimum_stock(monkeypatch):
    result, calls = _evaluate(monkeypatch, shopping_days=5, min_stock=4,
                              prediction_available=False)
    assert result["include_in_almost_out"] is True
    assert result["trigger_type"] == "stock"
    assert calls == [5]


def test_inconsistent_stock_does_not_become_a_forecast(monkeypatch):
    result, calls = _evaluate(monkeypatch, shopping_days=5, stock=-1)
    assert result["include_in_almost_out"] is False
    assert result["data_state"] == api.ALMOST_OUT_DATA_STATE_INCONSISTENT
    assert calls == []
