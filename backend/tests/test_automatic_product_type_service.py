import json

import pytest

from app.services.automatic_product_type_service import (
    classify_product_type, package_content, persist_product_type, policy, source_facts,
)


@pytest.mark.parametrize('first,second,brick', [
    ('AH halfvolle melk 1 l', 'Milbona semi-skimmed milk 500 ml', '10000025'),
    ('AH Goudse jong belegen kaas 48+', 'Gouda jong belegen 48+ Lidl', '10000028'),
    ('Gouda jonge kaas 48+', 'Goudse jong kaas 48+', '10000028'),
    ('Gouda oude kaas 48+', 'Goudse oud kaas 48+', '10000028'),
    ('AH Elstar appels 1 kg', 'Lidl Elstar apples 500 g', '10005900'),
    ('AH vastkokende aardappelen 2 kg', 'Lidl vastkokend aardappelen 1 kg', '10006104'),
    ('AH volkoren brood', 'Lidl wholemeal bread', '10000164'),
    ('Biologische eieren', 'Organic eggs', '10006210'),
    ('Penne glutenvrij', 'Gluten free penne', '10000242'),
    ('Ongebrande ongezouten amandelen', 'Raw unsalted almonds', '10000007'),
])
def test_same_type_across_retailers_languages_brands_and_package_sizes(first, second, brick):
    a = classify_product_type({'name': first}, brick)
    b = classify_product_type({'name': second}, brick)
    assert a['status'] == b['status'] == 'ready', (a, b)
    assert a['key'] == b['key']


@pytest.mark.parametrize('first,second,brick', [
    ('Halfvolle melk', 'Volle melk', '10000025'),
    ('Halfvolle melk', 'Magere melk', '10000025'),
    ('Halfvolle melk', 'Lactosevrije halfvolle melk', '10000025'),
    ('Halfvolle koemelk', 'Halfvolle geitenmelk', '10000025'),
    ('Gouda jonge kaas 48+', 'Gouda jong belegen kaas 48+', '10000028'),
    ('Gouda jong belegen kaas 48+', 'Gouda oude kaas 48+', '10000028'),
    ('Gouda jong belegen 48+', 'Gouda jong belegen 30+', '10000028'),
    ('Gouda jong belegen 48+', 'Gouda jong belegen 48+ geraspt', '10000028'),
    ('Elstar appels', 'Gala appels', '10005900'),
    ('Kruimige aardappelen', 'Vastkokende aardappelen', '10006104'),
    ('Volkoren brood', 'Wit brood', '10000164'),
    ('Penne', 'Spaghetti', '10000242'),
])
def test_distinguishing_features_prevent_silent_aggregation(first, second, brick):
    a, b = [classify_product_type({'name': name}, brick) for name in (first, second)]
    assert a['status'] == b['status'] == 'ready', (a, b)
    assert a['key'] != b['key']


@pytest.mark.parametrize('name,brick', [
    ('Melk', '10000025'), ('Melk 1.5 l', '10000025'),
    ('Kaas', '10000028'), ('Jong belegen kaas 48+', '10000028'),
    ('Appels', '10005900'), ('Aardappelen', '10006104'),
    ('Onbekend product', ''), ('Amandelen', '10001742'),
    ('Halfvolle melk', '10000028'), ('Haver halfvolle melk', '10000025'),
    ('Volle en halfvolle melk', '10000025'), ('Gouda jong belegen en oude kaas 48+', '10000028'),
])
def test_missing_unsupported_or_conflicting_data_remains_pending_without_a_group(name, brick):
    result = classify_product_type({'name': name}, brick)
    assert result['status'] == 'pending', result
    assert result['key'] is None


def test_structured_gs1_attributes_supply_missing_information_and_conflicts_are_not_ignored():
    result = classify_product_type({'name': 'Melk', 'attributes': {'fatInMilkContent': 1.5}}, '10000025')
    assert result['status'] == 'ready'
    assert result['attributes']['milk_fat'] == 'halfvol'
    assert 'fatInMilkContent' in result['evidence']['milk_fat']
    conflict = classify_product_type({'name': 'Volle melk', 'fatInMilkContent': 1.5}, '10000025')
    assert conflict['status'] == 'pending'
    assert conflict['reason'] == 'conflicting_attributes'


def test_unambiguous_commodity_can_get_its_official_brick_without_user_selection():
    result = classify_product_type({'name': 'Elstar appels'})
    assert result['status'] == 'ready'
    assert result['gpc_brick_code'] == '10005900'
    assert classify_product_type({'name': 'Halfvolle melk'})['status'] == 'pending'


@pytest.mark.parametrize('product,expected', [
    ({'quantity': '2 x 250 g'}, (.5, 'kg')),
    ({'quantity': '500 ml'}, (.5, 'l')),
    ({'name': 'AH halfvolle melk 1,5 l'}, (1.5, 'l')),
    ({'size_value': 6, 'size_unit': 'stuk'}, (6, 'stuk')),
    ({'quantity': '0 l'}, None), ({'quantity': '-1 l'}, None),
    ({'size_value': float('inf'), 'size_unit': 'l'}, None),
    ({'name': 'voeding 500 mg 90 stuks'}, None),
    ({'quantity': 'een verpakking'}, None),
])
def test_package_conversion_is_explicit_and_does_not_infer_unknown_quantities(product, expected):
    assert package_content(product) == expected


def test_persistence_contains_only_central_product_facts_and_no_household_mutations():
    class Connection:
        def execute(self, query, params):
            assert str(query).lstrip().startswith('INSERT INTO global_product_consumption_profiles')
            assert 'household' not in str(query)
            self.params = params
    conn = Connection()
    result = persist_product_type(conn, 'central-product', {'name': 'Halfvolle melk', 'session_token': 'private', 'household_id': 'private', 'receipt_text': 'private'}, '10000025')
    assert result['status'] == 'ready'
    assert 'private' not in conn.params['facts']
    assert json.loads(conn.params['profile'])['key'] == result['key']
    assert source_facts({'gtin': '123', 'name': 'x'}) == {'name': 'x'}


def test_taxonomy_is_data_driven_and_not_limited_to_the_four_examples():
    rules = policy()['rules']
    assert len(rules) >= 16
    assert len({rule['key'] for rule in rules}) == len(rules)
    assert all(rule['attributes'] for rule in rules)


def test_corrupt_almond_labels_cannot_provide_evidence_for_engraving_tool_codes():
    from app.services.automatic_product_type_service import official_reference, verified_official_labels
    row = verified_official_labels({'brick_code': '10001742', 'brick_description': 'Amandelen ongebrand Amandelen', 'source_version': official_reference()['publication_version']})
    assert 'amandel' not in row['brick_description'].casefold()
    assert row['segment_code'] == '70000000'
    assert classify_product_type({'name': 'Ongebrande ongezouten amandelen'}, row['brick_code'])['status'] == 'pending'


def test_recognized_type_does_not_claim_aggregation_without_known_package_content():
    unknown = classify_product_type({'name': 'Halfvolle melk'}, '10000025')
    known = classify_product_type({'name': 'Halfvolle melk', 'quantity': '500 ml'}, '10000025')
    assert unknown['status'] == known['status'] == 'ready'
    assert unknown['aggregation_ready'] is False
    assert known['aggregation_ready'] is True
    assert known['package_content'] == {'value': .5, 'unit': 'l'}


def test_policy_codes_and_attribute_defaults_are_valid_and_food_does_not_match_appliances():
    from app.services.automatic_product_type_service import official_bricks
    for rule in policy()['rules']:
        for key in rule['attributes']:
            definition = policy()['attributes'][key]
            assert definition.get('default') is None or definition['default'] in definition['values']
        assert all(code in official_bricks() for code in rule['brick_codes'])
    assert classify_product_type({'name': 'Koffiebonen'}, '10006218')['status'] == 'pending'


@pytest.mark.parametrize('name', ['Aardappelpartjes', 'Aardappelschijfjes', 'Aardappelblokjes', 'Krieltjes', 'Frozen potato wedges'])
def test_potato_preparations_reject_crisps_without_guessing_storage(name):
    from app.services.automatic_product_type_service import gpc_brick_conflict
    assert gpc_brick_conflict({'product_name': name}, '10000177')
    for code in ['10006104', '10000270', '10000271', '10000272']:
        assert gpc_brick_conflict({'product_name': name}, code) is None
    assert classify_product_type({'name': name})['status'] == 'pending'


@pytest.mark.parametrize('name,code', [('Paprika chips','10000177'), ('Potato wedges crisps','10000177'), ('Bananen','10005897'), ('Halfvolle melk','10000025')])
def test_brick_validation_preserves_non_conflicting_sources(name, code):
    from app.services.automatic_product_type_service import gpc_brick_conflict
    assert gpc_brick_conflict({'product_name': name}, code) is None


def test_official_code_is_not_automatically_correct_for_product(monkeypatch):
    from contextlib import nullcontext
    from unittest.mock import Mock
    from app.services import gpc_local_catalog_service as service
    monkeypatch.setattr(service, 'ensure_local_gpc_schema', lambda: None)
    monkeypatch.setattr(service, 'engine', Mock(begin=lambda: nullcontext(None)))
    monkeypatch.setattr(service, 'search_official_gpc_bricks', lambda *args, **kwargs: [{'brick_code': '10000177', 'brick_description': 'Chips/Snacks'}])
    result = service.classify_gpc_product(product_name='Aardappelpartjes', explicit_gpc_brick_code='10000177')
    assert result['status'] == 'not_classified'
    assert result['reason'] == 'conflicting_product_category'
    assert not result.get('product_type_id')
    assert result['suggestions'] == []
    valid = service.classify_gpc_product(product_name='Paprika chips', explicit_gpc_brick_code='10000177')
    assert valid['status'] == 'classified'


def test_candidate_ranking_cannot_reintroduce_rejected_potato_snack_code(monkeypatch):
    from contextlib import nullcontext
    from unittest.mock import Mock
    from app.services import gpc_local_catalog_service as service
    monkeypatch.setattr(service, 'ensure_local_gpc_schema', lambda: None)
    monkeypatch.setattr(service, 'engine', Mock(begin=lambda: nullcontext(None)))
    monkeypatch.setattr(service, 'list_official_gpc_bricks', lambda *args: [])
    monkeypatch.setattr(service, 'rank_external_gpc_candidates', lambda **kwargs: ([{'gpc_brick_code':'10000177','confidence':1}], {}))
    result = service.classify_gpc_product(product_name='Aardappelpartjes')
    assert result['status'] == 'not_classified'
    assert result['suggestions'] == []


@pytest.mark.parametrize('generic', [False, True])
def test_link_routes_reject_conflicting_brick_inside_atomic_transaction(monkeypatch, generic):
    from unittest.mock import MagicMock
    from app.services import off_product_link_service as service
    engine = MagicMock()
    monkeypatch.setattr(service, 'engine', engine)
    monkeypatch.setattr(service, 'ensure_product_inventory_group_schema', lambda: None)
    monkeypatch.setattr(service, 'resolve_external_article_identity', lambda *args: {})
    monkeypatch.setattr(service, 'assert_external_product_identity_compatible', lambda **kwargs: None)
    monkeypatch.setattr(service, '_upsert_global_product', lambda *args: ('test-id','8710624234294',1,'stuk'))
    monkeypatch.setattr(service, '_resolve_product_type', lambda *args: 'gpc:10000177')
    persisted = MagicMock()
    monkeypatch.setattr(service, 'persist_product_type', persisted)
    with pytest.raises(ValueError, match='broncategorie'):
        if generic:
            service.link_generic_product_with_product_type(receipt_item_id='test', generic_product_name='Aardappelpartjes', product_type_assignment={})
        else:
            service.link_off_product_with_product_type(receipt_item_id='test', off_product={'product_name':'Aardappelpartjes'}, product_type_assignment={})
    persisted.assert_not_called()
    assert engine.begin.return_value.__exit__.call_args.args[0] is ValueError
