from __future__ import annotations

from contextlib import contextmanager
from types import SimpleNamespace

from app.services.household_alias_policy import (
    _install_inventory_alias_update,
    _inventory_alias_projection,
)


ARTICLE_ID = 'article-a'
INVENTORY_ID = 'inventory-a'


class Result:
    def __init__(self, row=None, rows=None):
        self.row = row
        self.rows = rows or []

    def mappings(self):
        return self

    def first(self):
        return self.row

    def all(self):
        return self.rows


class ProjectionConnection:
    def execute(self, statement, params=None):
        sql = str(statement)
        assert 'FROM household_articles ha' in sql
        return Result(rows=[{
            'id': ARTICLE_ID,
            'naam': '7 Granen Ontbijt',
            'custom_name': 'Keesje',
            'product_name': '7 Granen Ontbijt',
            'image_url': 'https://images.example.test/ontbijt.jpg',
        }])


class ProjectionEngine:
    @contextmanager
    def begin(self):
        yield ProjectionConnection()


class CentralCatalogProjectionConnection:
    def __init__(self, *, ambiguous=False):
        self.ambiguous = ambiguous

    def execute(self, statement, params=None):
        sql = str(statement)
        if 'FROM household_articles ha' in sql and 'LEFT JOIN global_products gp' in sql:
            return Result(rows=[{
                'id': ARTICLE_ID,
                'household_id': 'household-a',
                'naam': 'Bio dadeltjes',
                'custom_name': '',
                'global_product_id': None,
                'product_name': '',
                'image_url': '',
            }])
        if 'WITH source_identities AS' in sql:
            rows = [{
                'household_article_id': ARTICLE_ID,
                'retailer_code': 'Albert Heijn',
                'receipt_line_text': 'BIO DADELTJES',
                'external_article_code': '',
                'source_rank': 1,
            }]
            if self.ambiguous:
                rows.append({
                    'household_article_id': ARTICLE_ID,
                    'retailer_code': 'Jumbo',
                    'receipt_line_text': 'BIO DADELTJES',
                    'external_article_code': '',
                    'source_rank': 2,
                })
            return Result(rows=rows)
        if 'FROM external_article_product_links link' in sql:
            rows = [{
                'retailer_code': 'albert-heijn',
                'external_article_code': '',
                'receipt_text_normalized': 'bio dadeltjes',
                'global_product_id': 'global-product-a',
                'image_url': 'https://images.example.test/bio-dadeltjes.jpg',
                'confirmed_at': '2026-09-20T12:00:00Z',
                'id': 'link-a',
            }]
            if self.ambiguous:
                rows.append({
                    'retailer_code': 'jumbo',
                    'external_article_code': '',
                    'receipt_text_normalized': 'bio dadeltjes',
                    'global_product_id': 'global-product-b',
                    'image_url': 'https://images.example.test/other-dadeltjes.jpg',
                    'confirmed_at': '2026-09-19T12:00:00Z',
                    'id': 'link-b',
                })
            return Result(rows=rows)
        raise AssertionError(f'Onverwachte Catalogus-projectie-SQL: {sql}')


class CentralCatalogProjectionEngine:
    def __init__(self, *, ambiguous=False):
        self.ambiguous = ambiguous

    @contextmanager
    def begin(self):
        yield CentralCatalogProjectionConnection(ambiguous=self.ambiguous)


class AliasUpdatePayload:
    def __init__(self, naam, aantal=1, space_name='Keuken', sublocation_name='Kast'):
        self.naam = naam
        self.aantal = aantal
        self.space_name = space_name
        self.sublocation_name = sublocation_name

    def model_copy(self, update=None):
        data = {
            'naam': self.naam,
            'aantal': self.aantal,
            'space_name': self.space_name,
            'sublocation_name': self.sublocation_name,
        }
        data.update(update or {})
        return AliasUpdatePayload(**data)


class AliasUpdateConnection:
    def __init__(self, state):
        self.state = state

    def execute(self, statement, params=None):
        sql = str(statement)
        params = dict(params or {})
        if 'SELECT id, naam, household_article_id' in sql and 'FROM inventory' in sql:
            return Result(row={
                'id': INVENTORY_ID,
                'naam': self.state['inventory_name'],
                'household_article_id': ARTICLE_ID,
            })
        if 'UPDATE household_articles' in sql and 'SET custom_name = :custom_name' in sql:
            self.state['custom_name'] = params.get('custom_name')
            return Result()
        raise AssertionError(f'Onverwachte alias-update-SQL: {sql}')


class AliasUpdateEngine:
    def __init__(self, state):
        self.state = state

    @contextmanager
    def begin(self):
        yield AliasUpdateConnection(self.state)


def test_inventory_preview_projects_household_alias_instead_of_inventory_name():
    main_module = SimpleNamespace(engine=ProjectionEngine(), text=lambda value: value)
    payload = {
        'rows': [{
            'id': INVENTORY_ID,
            'household_article_id': ARTICLE_ID,
            'household_article_name': '7 Granen Ontbijt',
            'product_name': '7 Granen Ontbijt',
            'artikel': '7 Granen Ontbijt',
            'aantal': 1,
        }]
    }

    projected = _inventory_alias_projection(main_module, payload)

    assert projected['rows'][0]['artikel'] == '7 Granen Ontbijt'
    assert projected['rows'][0]['household_article_name'] == 'Keesje'
    assert projected['rows'][0]['product_name'] == '7 Granen Ontbijt'
    assert projected['rows'][0]['image_url'] == 'https://images.example.test/ontbijt.jpg'


def test_inventory_preview_uses_confirmed_central_catalog_image_without_household_product_mutation():
    main_module = SimpleNamespace(
        engine=CentralCatalogProjectionEngine(),
        text=lambda value: value,
    )
    payload = {
        'rows': [{
            'id': INVENTORY_ID,
            'household_article_id': ARTICLE_ID,
            'artikel': 'Bio dadeltjes',
            'aantal': 1,
        }]
    }

    projected = _inventory_alias_projection(main_module, payload)

    assert projected['rows'][0]['image_url'] == 'https://images.example.test/bio-dadeltjes.jpg'
    assert projected['rows'][0]['household_article_name'] == 'Bio dadeltjes'


def test_inventory_preview_does_not_guess_image_when_one_household_article_maps_to_multiple_products():
    main_module = SimpleNamespace(
        engine=CentralCatalogProjectionEngine(ambiguous=True),
        text=lambda value: value,
    )
    payload = {
        'rows': [{
            'id': INVENTORY_ID,
            'household_article_id': ARTICLE_ID,
            'artikel': 'Bio dadeltjes',
            'aantal': 1,
        }]
    }

    projected = _inventory_alias_projection(main_module, payload)

    assert projected['rows'][0]['image_url'] == ''


def test_inventory_inline_household_name_does_not_rename_inventory_identity():
    state = {'inventory_name': '7 Granen Ontbijt', 'custom_name': 'Keesje'}
    calls = []

    def original_call(inventory_id, payload, authorization=None):
        calls.append((inventory_id, payload.naam, authorization))
        return {'ok': True, 'row': {'id': inventory_id, 'artikel': payload.naam}}

    route = SimpleNamespace(
        path='/api/dev/inventory/{inventory_id}',
        methods={'PUT'},
        dependant=SimpleNamespace(call=original_call),
    )
    main_module = SimpleNamespace(
        app=SimpleNamespace(routes=[route]),
        engine=AliasUpdateEngine(state),
        text=lambda value: value,
        require_inventory_write_context=lambda authorization: {'active_household_id': 'household-a'},
    )

    _install_inventory_alias_update(main_module)
    result = route.dependant.call(
        inventory_id=INVENTORY_ID,
        payload=AliasUpdatePayload('Nieuwe huishoudnaam'),
        authorization='Bearer admin',
    )

    assert calls == [(INVENTORY_ID, '7 Granen Ontbijt', 'Bearer admin')]
    assert state['inventory_name'] == '7 Granen Ontbijt'
    assert state['custom_name'] == 'Nieuwe huishoudnaam'
    assert result['row']['artikel'] == '7 Granen Ontbijt'
    assert result['row']['household_article_name'] == 'Nieuwe huishoudnaam'


def run_contract() -> None:
    test_inventory_preview_projects_household_alias_instead_of_inventory_name()
    test_inventory_preview_uses_confirmed_central_catalog_image_without_household_product_mutation()
    test_inventory_preview_does_not_guess_image_when_one_household_article_maps_to_multiple_products()
    test_inventory_inline_household_name_does_not_rename_inventory_identity()
    print('HOUSEHOLD_ALIAS_INVENTORY_PROJECTION_GREEN')


if __name__ == '__main__':
    run_contract()
