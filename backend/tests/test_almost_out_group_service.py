from datetime import datetime, timezone

import pytest

from app.services.almost_out_group_service import content, grouping_key, prediction_from_events, confirmed_synonym_factors, load_groups, load_group_projection


@pytest.mark.parametrize('value,unit,expected', [(1, 'l', (1, 'l')), (500, 'ml', (.5, 'l')), (75, 'cl', (.75, 'l')), (250, 'g', (.25, 'kg')), (2, 'stuk', (2, 'stuk'))])
def test_content_units(value, unit, expected):
    assert content(value, unit) == expected


@pytest.mark.parametrize('value,unit', [(0, 'l'), (-1, 'l'), ('nan', 'l'), ('inf', 'kg'), (None, 'l'), (1, 'pak')])
def test_unknown_or_invalid_content_is_not_guessed(value, unit):
    assert content(value, unit) is None


def test_lidl_and_ah_are_automatically_equivalent_without_household_settings():
    first = {'id': 'ah', 'global_product_id': 'gp-ah', 'brick_code': '10000025', 'size_value': 1, 'size_unit': 'l', 'product_name': 'AH halfvolle melk'}
    second = {'id': 'lidl', 'global_product_id': 'gp-lidl', 'brick_code': '10000025', 'size_value': 500, 'size_unit': 'ml', 'product_name': 'Milbona halfvolle melk'}
    key, factor = grouping_key(first, {})
    other_key, other_factor = grouping_key(second, {})
    assert key == other_key
    assert factor == 1
    assert other_factor == .5
    assert grouping_key({**second, 'product_name': 'Volle melk'}, {})[0] != key
    assert grouping_key({**second, 'brick_code': '10000026'}, {})[0] != key
    assert grouping_key({**second, 'size_unit': 'kg'}, {})[0] != key


def test_unknown_metadata_and_obsolete_manual_settings_never_force_a_merge():
    first = {'id': 'a', 'global_product_id': 'gp-a', 'brick_code': '10000025', 'size_value': 1, 'size_unit': 'l', 'product_name': 'Melk'}
    second = {**first, 'id': 'b', 'global_product_id': 'gp-b'}
    obsolete = {'almost_out_variant': 'halfvolle melk', 'almost_out_content_value': 1, 'almost_out_content_unit': 'l'}
    assert grouping_key(first, obsolete)[0] != grouping_key(second, obsolete)[0]
    assert grouping_key({**first, 'facts_json': '{invalid'}, {})[0][0] == 'product'


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


class _Rows:
    def __init__(self, rows):
        self.rows = rows

    def mappings(self):
        return self

    def all(self):
        return self.rows


class _SynonymConnection:
    def __init__(self, metadata, links):
        self.metadata = metadata
        self.links = links
        self.calls = []

    def execute(self, statement, params):
        sql = str(statement)
        self.calls.append((sql, params))
        if 'FROM household_articles' in sql:
            return _Rows(self.metadata)
        if 'FROM article_synonym_links' in sql:
            return _Rows(self.links)
        raise AssertionError(f'Unexpected read: {sql}')


def _metadata(article_id, product_id, size, unit='l'):
    return {'id': article_id, 'global_product_id': product_id,
            'size_value': size, 'size_unit': unit,
            'product_name': 'Halfvolle melk', 'variant': '',
            'brick_code': None, 'facts_json': None}


def test_confirmed_pair_is_grouped_with_content_conversion_and_household_scope():
    metadata = [_metadata('house-a', 'gp-a', 1),
                _metadata('house-b', 'gp-b', 500, 'ml')]
    conn = _SynonymConnection(metadata, [
        {'left_product_id': 'gp-a', 'right_product_id': 'gp-b'}])
    groups = load_groups(conn, 'household-1',
                         [{'id': 'house-a'}, {'id': 'house-b'}], {})
    assert len(groups) == 1
    group = groups[0]
    assert group['key'][0] == 'confirmed_synonym'
    assert group['factors'] == {'house-a': 1, 'house-b': .5}
    assert all(params['household_id'] == 'household-1'
               for sql, params in conn.calls if 'FROM household_articles' in sql)
    assert not any('INSERT ' in sql or 'UPDATE ' in sql or 'DELETE ' in sql
                   for sql, _ in conn.calls)


def test_unconfirmed_pair_and_incompatible_units_remain_separate():
    metadata = [_metadata('a', 'gp-a', 1), _metadata('b', 'gp-b', 1)]
    assert len(load_groups(_SynonymConnection(metadata, []), 'hh',
                           [{'id': 'a'}, {'id': 'b'}], {})) == 2
    incompatible = [_metadata('a', 'gp-a', 1),
                    _metadata('b', 'gp-b', 250, 'g')]
    link = [{'left_product_id': 'gp-a', 'right_product_id': 'gp-b'}]
    assert len(load_groups(_SynonymConnection(incompatible, link), 'hh',
                           [{'id': 'a'}, {'id': 'b'}], {})) == 2


def test_confirmed_chain_does_not_become_a_stock_group():
    metadata = [_metadata('a', 'gp-a', 1), _metadata('b', 'gp-b', 1),
                _metadata('c', 'gp-c', 1)]
    links = [{'left_product_id': 'gp-a', 'right_product_id': 'gp-b'},
             {'left_product_id': 'gp-b', 'right_product_id': 'gp-c'}]
    groups = load_groups(_SynonymConnection(metadata, links), 'hh',
                         [{'id': 'a'}, {'id': 'b'}, {'id': 'c'}], {})
    assert len(groups) == 3
    assert not any(g['key'][0] == 'confirmed_synonym' for g in groups)


def test_out_of_household_link_prevents_partial_chain_merge():
    metadata = [_metadata('a', 'gp-a', 1), _metadata('b', 'gp-b', 1)]
    links = [{'left_product_id': 'gp-a', 'right_product_id': 'gp-b'},
             {'left_product_id': 'gp-b', 'right_product_id': 'gp-other'}]
    assert confirmed_synonym_factors(
        _SynonymConnection(metadata, links), metadata) == {}


def test_confirmed_pair_does_not_split_existing_automatic_product_type_group():
    metadata = [
        {**_metadata('a', 'gp-a', 1), 'brick_code': '10000025'},
        {**_metadata('b', 'gp-b', 500, 'ml'), 'brick_code': '10000025'},
        {**_metadata('c', 'gp-c', 1), 'brick_code': '10000026', 'product_name': 'Volle melk'},
    ]
    links = [{'left_product_id': 'gp-a', 'right_product_id': 'gp-c'}]
    groups = load_groups(_SynonymConnection(metadata, links), 'hh',
                         [{'id': 'a'}, {'id': 'b'}, {'id': 'c'}], {})
    automatic = [group for group in groups if group['key'][0] == 'automatic_product_type']
    assert len(groups) == 2
    assert any({item['id'] for item in group['members']} == {'a', 'b'} for group in automatic)
    assert not any(group['key'][0] == 'confirmed_synonym' for group in groups)


def test_confirmed_pair_projection_converts_inventory_without_mutating_members():
    class ReadOnlyConnection(_SynonymConnection):
        def execute(self, statement, params):
            sql = str(statement)
            if 'FROM inventory i' in sql:
                return _Rows([
                    {'id': 'inv-a', 'household_article_id': 'a', 'quantity': 1,
                     'space_id': None, 'sublocation_id': None, 'space_name': '', 'sublocation_name': ''},
                    {'id': 'inv-b', 'household_article_id': 'b', 'quantity': 2,
                     'space_id': None, 'sublocation_id': None, 'space_name': '', 'sublocation_name': ''},
                ])
            if 'FROM inventory_events' in sql:
                return _Rows([])
            return super().execute(statement, params)

    conn = ReadOnlyConnection(
        [_metadata('a', 'gp-a', 1), _metadata('b', 'gp-b', 500, 'ml')],
        [{'left_product_id': 'gp-a', 'right_product_id': 'gp-b'}],
    )
    groups = load_groups(conn, 'hh', [{'id': 'a'}, {'id': 'b'}], {})
    projection = load_group_projection(conn, 'hh', groups[0])
    assert projection['aggregation_scope'] == 'confirmed_synonym'
    assert projection['aggregation_unit'] == 'l'
    assert projection['representative_package_content'] == 1
    assert projection['member_article_ids'] == ['a', 'b']
    assert [item['quantity'] for item in projection['inventory_rows']] == [1, 1]
    assert [item['original_quantity'] for item in projection['inventory_rows']] == [1, 2]


def test_confirmed_three_member_fresh_courgette_group_requires_every_exact_package():
    metadata = [
        {**_metadata('a', 'gp-a', 1, 'stuk'), 'product_name': 'Courgette'},
        {**_metadata('b', 'gp-b', 1, 'stuk'), 'product_name': 'Courgette geel'},
        {**_metadata('c', 'gp-c', 1, 'stuk'), 'product_name': 'Courgette Bio'},
    ]
    links = [
        {'left_product_id': 'gp-a', 'right_product_id': 'gp-b'},
        {'left_product_id': 'gp-a', 'right_product_id': 'gp-c'},
    ]
    groups = load_groups(_SynonymConnection(metadata, links), 'hh',
                         [{'id': 'a'}, {'id': 'b'}, {'id': 'c'}], {})
    assert len(groups) == 1
    assert {m['id'] for m in groups[0]['members']} == {'a', 'b', 'c'}
    assert groups[0]['key'][0] == 'confirmed_synonym'
    assert groups[0]['factors'] == {'a': 1, 'b': 1, 'c': 1}


def test_chain_missing_courgette_package_or_one_household_member_does_not_group():
    metadata = [
        {**_metadata('a', 'gp-a', 1, 'stuk'), 'product_name': 'Courgette'},
        {**_metadata('b', 'gp-b', None, 'stuk'), 'product_name': 'Courgette geel'},
        {**_metadata('c', 'gp-c', 1, 'stuk'), 'product_name': 'Courgette Bio'},
    ]
    links = [
        {'left_product_id': 'gp-a', 'right_product_id': 'gp-b'},
        {'left_product_id': 'gp-a', 'right_product_id': 'gp-c'},
    ]
    articles = [{'id': 'a'}, {'id': 'b'}, {'id': 'c'}]
    assert len(load_groups(_SynonymConnection(metadata, links), 'hh', articles, {})) == 3
    complete_metadata = [{**row, 'size_value': 1} for row in metadata]
    assert len(load_groups(_SynonymConnection(complete_metadata[:2], links),
                           'hh', articles[:2], {})) == 2


def test_transitive_courgette_group_does_not_guess_incompatible_units():
    metadata = [
        {**_metadata('a', 'gp-a', 1, 'stuk'), 'product_name': 'Courgette'},
        {**_metadata('b', 'gp-b', 250, 'g'), 'product_name': 'Courgette geel'},
        {**_metadata('c', 'gp-c', 1, 'stuk'), 'product_name': 'Courgette Bio'},
    ]
    links = [
        {'left_product_id': 'gp-a', 'right_product_id': 'gp-b'},
        {'left_product_id': 'gp-b', 'right_product_id': 'gp-c'},
    ]
    assert len(load_groups(_SynonymConnection(metadata, links), 'hh',
                           [{'id': 'a'}, {'id': 'b'}, {'id': 'c'}], {})) == 3
