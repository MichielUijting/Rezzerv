from datetime import datetime, timezone

import pytest

from app.services.almost_out_group_service import content, grouping_key, prediction_from_events


@pytest.mark.parametrize('value,unit,expected', [(1, 'l', (1, 'l')), (500, 'ml', (.5, 'l')), (75, 'cl', (.75, 'l')), (250, 'g', (.25, 'kg')), (2, 'stuk', (2, 'stuk'))])
def test_content_units(value, unit, expected):
    assert content(value, unit) == expected


@pytest.mark.parametrize('value,unit', [(0, 'l'), (-1, 'l'), ('nan', 'l'), ('inf', 'kg'), (None, 'l'), (1, 'pak')])
def test_unknown_or_invalid_content_is_not_guessed(value, unit):
    assert content(value, unit) is None


def test_lidl_and_ah_same_brick_and_variant_are_equivalent_despite_packaging():
    first = {'id': 'ah', 'global_product_id': 'gp-ah', 'brick_code': '10000025', 'size_value': 1, 'size_unit': 'l', 'naam': 'AH halfvolle melk'}
    second = {'id': 'lidl', 'global_product_id': 'gp-lidl', 'brick_code': '10000025', 'size_value': 500, 'size_unit': 'ml', 'naam': 'Milbona'}
    key, first_factor = grouping_key(first, {'almost_out_variant': 'Halfvolle koemelk'})
    other_key, other_factor = grouping_key(second, {'almost_out_variant': '  halfvolle   koemelk '})
    assert key == other_key
    assert first_factor == 1
    assert other_factor == .5
    assert grouping_key(second, {'almost_out_variant': 'volle koemelk'})[0] != key
    assert grouping_key({**second, 'brick_code': '10000026'}, {'almost_out_variant': 'halfvolle koemelk'})[0] != key


def test_unknown_variant_or_size_never_merges_two_products():
    first = {'id': 'a', 'global_product_id': 'gp-a', 'brick_code': '10000025', 'size_value': 1, 'size_unit': 'l'}
    second = {**first, 'id': 'b', 'global_product_id': 'gp-b'}
    assert grouping_key(first, {})[0] != grouping_key(second, {})[0]
    assert grouping_key({**first, 'size_value': None}, {'almost_out_variant': 'halfvol'})[0][0] == 'product'


def test_explicit_household_content_override_and_incompatible_dimensions():
    row = {'id': 'a', 'brick_code': '10000025', 'size_value': 1, 'size_unit': 'l'}
    key, factor = grouping_key(row, {'almost_out_variant': 'halfvol', 'almost_out_content_value': 500, 'almost_out_content_unit': 'ml'})
    assert factor == .5
    assert key != grouping_key({**row, 'size_unit': 'kg'}, {'almost_out_variant': 'halfvol'})[0]


def test_quantity_weighted_rhythm_handles_different_packages_and_same_day_purchases():
    now = datetime(2026, 10, 23, tzinfo=timezone.utc)
    events = [
        {'event_type': 'purchase', 'quantity': .5, 'purchase_date': '2026-10-09'},
        {'event_type': 'purchase', 'quantity': .5, 'purchase_date': '2026-10-09'},
        {'event_type': 'auto_repurchase', 'quantity': 2, 'purchase_date': '2026-10-16'},
        {'event_type': 'consume', 'quantity': -1, 'purchase_date': '2026-10-17'},
        {'event_type': 'purchase', 'quantity': 200, 'purchase_date': '2026-10-24'},
    ]
    result = prediction_from_events(events, 7, now)
    assert result['purchase_event_count'] == 2
    assert result['average_purchase_interval_days'] == 7
    # First litre lasted 7 days; the last two litres last 14 days, 7 remain.
    assert result['predicted_days_until_depletion'] == 7
    assert result['prediction_triggered'] is True
    assert prediction_from_events(events, 6, now)['prediction_triggered'] is False


def test_same_day_only_and_unusable_dates_have_no_prediction():
    events = [{'event_type': 'purchase', 'quantity': 1, 'purchase_date': '2026-10-09'}] * 2
    assert prediction_from_events(events, 7) is None
    assert prediction_from_events([{'event_type': 'purchase', 'quantity': 1, 'purchase_date': 'invalid'}], 7) is None


@pytest.mark.parametrize('quantity', [0, -1, float('inf'), float('nan')])
def test_production_settings_model_rejects_invalid_package_content(quantity):
    # Load the actual model without starting the application or its database.
    import ast
    from pathlib import Path
    from pydantic import BaseModel, Field, ValidationError, field_validator
    path = Path(__file__).parents[1] / 'app' / 'main.py'
    tree = ast.parse(path.read_text())
    model = next(node for node in tree.body if isinstance(node, ast.ClassDef) and node.name == 'HouseholdArticleSettingsUpdateRequest')
    namespace = {'BaseModel': BaseModel, 'Field': Field, 'field_validator': field_validator}
    exec(compile(ast.Module(body=[model], type_ignores=[]), str(path), 'exec'), namespace)
    with pytest.raises(ValidationError):
        namespace[model.name](almost_out_content_value=quantity, almost_out_content_unit='l')
