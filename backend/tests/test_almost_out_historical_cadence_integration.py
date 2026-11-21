"""PR6 Bijna op runtime integration: PR3 cadence needs physical volume.

Legacy event-rate, threshold, unsafe grouping and household ownership remain
covered by the existing API/F3 test suite. No alternate datastore is started.
"""
from datetime import date
from unittest.mock import patch

import pytest

from app import main as api


def projection(*, events=None, stock=1, members=("ah", "lidl")):
    return {
        "inventory_rows": [{"quantity": stock}],
        "event_rows": events if events is not None else [
            {"article_id": "ah", "event_type": "baseline", "quantity": 0},
            {"article_id": "lidl", "event_type": "purchase",
             "purchase_date": date.today().isoformat(), "quantity": stock},
        ],
        "member_article_ids": list(members),
        "member_data_inconsistent": False,
        "aggregation_scope": "confirmed_synonym",
        "aggregation_variant": None,
        "aggregation_unit": None,
        "representative_package_content": None,
    }


def cadence(members=("ah", "lidl")):
    return {
        "members": tuple(members),
        "interval_days": 10,
        "purchase_day_count": 2,
        "first_date": date.today(),
        "last_date": date.today(),
    }


def evaluate(*, group=None, known=None, prediction_days=20, min_stock=0):
    return api.evaluate_household_article_almost_out(
        object(), "home-1",
        {"id": "ah", "naam": "Bewezen product", "min_stock": min_stock,
         "ideal_stock": 2},
        household_settings={
            "shopping_days": 0, "prediction_enabled": True,
            "prediction_days": prediction_days, "policy_mode": "advisory",
        },
        article_settings_map={},
        group_projection=group if group is not None else projection(),
        purchase_cadence=known if known is not None else cadence(),
    )


def test_one_repeat_and_one_actual_day_quantity_trigger_cadence_forecast():
    row = evaluate()
    assert row["include_in_almost_out"] is True
    assert row["trigger_type"] == "predicted"
    assert row["prediction_basis"] == "confirmed_historical_cadence_and_latest_purchase_quantity"
    assert row["historical_repurchase_interval_days"] == 10
    assert row["historical_repurchase_purchase_days"] == 2
    assert row["member_article_ids"] == ["ah", "lidl"]
    assert row["amount_to_buy"] >= 1


def test_cadence_alone_never_triggers_without_real_new_purchase_volume():
    group = projection(events=[{"article_id": "ah", "event_type": "baseline", "quantity": 1}])
    safe = evaluate(group=group, prediction_days=20)
    assert safe["include_in_almost_out"] is False
    assert safe["prediction_available"] is False
    assert safe["historical_repurchase_interval_days"] == 10


def test_incomplete_synonym_group_cannot_claim_a_shared_cadence():
    unsafe = evaluate(
        group=projection(members=("ah", "unverified")),
        known=cadence(members=("ah", "lidl")),
    )
    assert unsafe["include_in_almost_out"] is False
    assert "historical_repurchase_interval_days" not in unsafe


def test_stock_inconsistency_blocks_historical_forecast():
    group = projection()
    group["member_data_inconsistent"] = True
    row = evaluate(group=group)
    assert row["include_in_almost_out"] is False
    assert row["data_state"] == api.ALMOST_OUT_DATA_STATE_INCONSISTENT


def test_existing_volume_based_forecast_keeps_precedence():
    with patch(
        "app.services.almost_out_group_service.prediction_from_events",
        return_value={
            "prediction_available": True, "prediction_triggered": False,
            "predicted_quantity_at_horizon": 0.75, "prediction_basis": "stock_adjusted_purchase_rate",
        },
    ):
        row = evaluate()
    assert row["prediction_basis"] == "stock_adjusted_purchase_rate"
    assert row["include_in_almost_out"] is False


def test_prediction_disabled_does_not_force_history_into_almost_out():
    group = projection()
    with patch("app.services.almost_out_group_service.prediction_from_events", return_value=None):
        row = api.evaluate_household_article_almost_out(
            object(), "home-1",
            {"id": "ah", "naam": "Bewezen product", "min_stock": 0, "ideal_stock": 2},
            household_settings={
                "shopping_days": 0, "prediction_enabled": False,
                "prediction_days": 7, "policy_mode": "advisory",
            },
            article_settings_map={}, group_projection=group, purchase_cadence=cadence(),
        )
    assert row["include_in_almost_out"] is False
    assert row["prediction_available"] is False


def test_first_use_history_only_shows_estimated_need_when_stock_baseline_is_untouched():
    from datetime import timedelta
    group = projection(
        stock=1,
        events=[
            {"article_id": "ah", "event_type": "baseline", "quantity": 0,
             "source": "historical_auto_stock"},
            {"article_id": "lidl", "event_type": "baseline", "quantity": 1,
             "source": "historical_auto_stock"},
        ],
    )
    approved = {
        **cadence(),
        "last_date": date.today() - timedelta(days=12),
        "first_date": date.today() - timedelta(days=22),
    }
    row = api.evaluate_household_article_almost_out(
        object(), "home-1",
        {"id": "ah", "naam": "Bewezen product", "min_stock": 0, "ideal_stock": 2},
        household_settings={
            "shopping_days": 0, "prediction_enabled": True,
            "prediction_days": 7, "policy_mode": "advisory",
        },
        article_settings_map={}, group_projection=group,
        purchase_cadence=approved, historical_baseline_allowed=True,
    )
    assert row["prediction_available"] is True
    assert row["prediction_basis"] == "confirmed_historical_replacement_and_untouched_opening_stock"
    assert row["prediction_triggered"] is True
    assert row["include_in_almost_out"] is True
    assert row["trigger_type"] == "predicted"

    # An explicit disabled replacement policy cannot use opening-stock volume.
    disabled = api.evaluate_household_article_almost_out(
        object(), "home-1",
        {"id": "ah", "naam": "Bewezen product", "min_stock": 0, "ideal_stock": 2},
        household_settings={
            "shopping_days": 0, "prediction_enabled": True,
            "prediction_days": 7, "policy_mode": "advisory",
        },
        article_settings_map={}, group_projection=group,
        purchase_cadence=approved, historical_baseline_allowed=False,
    )
    assert disabled["include_in_almost_out"] is False
