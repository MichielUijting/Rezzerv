from __future__ import annotations

from contextlib import contextmanager
from pathlib import Path
from types import SimpleNamespace

from app.services.household_alias_policy import (
    _install_inventory_alias_update,
    _inventory_alias_projection,
    install_household_alias_policy,
    resolve_household_catalog_images,
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
        if 'FROM product_identities pi' in sql:
            return Result(rows=[])
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


class SynonymPhotoConnection(CentralCatalogProjectionConnection):
    def __init__(self, *, own_image='', peer_image='https://images.example.test/confirmed-peer.jpg', ambiguous=False):
        super().__init__(ambiguous=ambiguous)
        self.own_image = own_image
        self.peer_image = peer_image
        self.synonym_queries = 0

    def execute(self, statement, params=None):
        sql = str(statement)
        if 'FROM article_synonym_links asl' in sql:
            self.synonym_queries += 1
            return Result(rows=([{
                'source_id': 'global-product-a',
                'peer_id': 'confirmed-synonym-b',
                'image_url': self.peer_image,
            }] if self.peer_image else []))
        result = super().execute(statement, params)
        if 'FROM external_article_product_links link' in sql:
            for row in result.rows:
                row['image_url'] = self.own_image
        return result


class SynonymPhotoEngine:
    def __init__(self, **options):
        self.conn = SynonymPhotoConnection(**options)

    @contextmanager
    def begin(self):
        yield self.conn


class CanonicalIdentityProjectionConnection:
    def execute(self, statement, params=None):
        sql = str(statement)
        if 'FROM household_articles ha' in sql and 'LEFT JOIN global_products gp' in sql:
            return Result(rows=[{
                'id': ARTICLE_ID,
                'household_id': 'household-a',
                'naam': 'Gouda belegen geraspt',
                'custom_name': '',
                'global_product_id': None,
                'barcode': '',
                'product_name': '',
                'image_url': '',
            }])
        if 'FROM product_identities pi' in sql:
            return Result(rows=[{
                'household_article_id': ARTICLE_ID,
                'global_product_id': 'global-product-identity',
                'image_url': 'https://images.example.test/gouda.jpg',
            }])
        raise AssertionError(f'Onverwachte identity-projectie-SQL: {sql}')


class CanonicalIdentityProjectionEngine:
    @contextmanager
    def begin(self):
        yield CanonicalIdentityProjectionConnection()


class CanonicalBarcodeProjectionConnection:
    def execute(self, statement, params=None):
        sql = str(statement)
        if 'FROM household_articles ha' in sql and 'LEFT JOIN global_products gp' in sql:
            return Result(rows=[{
                'id': ARTICLE_ID,
                'household_id': 'household-a',
                'naam': 'Rijstwafel',
                'custom_name': '',
                'global_product_id': None,
                'barcode': '8712345678901',
                'product_name': '',
                'image_url': '',
            }])
        if 'FROM product_identities pi' in sql:
            return Result(rows=[])
        if 'FROM global_products' in sql and 'primary_gtin IN' in sql:
            return Result(rows=[{
                'global_product_id': 'global-product-barcode',
                'primary_gtin': '8712345678901',
                'image_url': 'https://images.example.test/rijstwafel.jpg',
            }])
        raise AssertionError(f'Onverwachte barcode-projectie-SQL: {sql}')


class CanonicalBarcodeProjectionEngine:
    @contextmanager
    def begin(self):
        yield CanonicalBarcodeProjectionConnection()


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


def test_main_activates_household_alias_policy_after_api_routes_are_registered():
    main_source = (
        Path(__file__).resolve().parents[1] / 'app' / 'main.py'
    ).read_text(encoding='utf-8')

    import_statement = (
        'from app.services.household_alias_policy import install_household_alias_policy'
    )
    install_statement = 'install_household_alias_policy(sys.modules[__name__])'
    router_statement = 'app.include_router(api_router)'

    assert import_statement in main_source
    assert install_statement in main_source
    assert main_source.rfind(install_statement) > main_source.rfind(router_statement)


def test_runtime_installer_wraps_inventory_preview_with_catalog_image_projection():
    payload = {
        'rows': [{
            'id': INVENTORY_ID,
            'household_article_id': ARTICLE_ID,
            'artikel': '7 Granen Ontbijt',
            'aantal': 1,
        }]
    }
    route = SimpleNamespace(
        path='/api/dev/inventory-preview',
        methods={'GET'},
        dependant=SimpleNamespace(call=lambda authorization=None: payload),
    )
    main_module = SimpleNamespace(
        app=SimpleNamespace(routes=[route]),
        engine=ProjectionEngine(),
        text=lambda value: value,
        apply_household_article_defaults_from_enrichment=lambda *args, **kwargs: None,
        merge_household_article_details_with_product_defaults=lambda row, product_details: dict(row or {}),
    )

    install_household_alias_policy(main_module)
    projected = route.dependant.call(authorization='Bearer test')

    assert projected['rows'][0]['image_url'] == 'https://images.example.test/ontbijt.jpg'
    assert projected['rows'][0]['household_article_name'] == 'Keesje'


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


def test_inventory_preview_uses_canonical_product_identity_image():
    main_module = SimpleNamespace(
        engine=CanonicalIdentityProjectionEngine(),
        text=lambda value: value,
    )
    payload = {
        'rows': [{
            'id': INVENTORY_ID,
            'household_article_id': ARTICLE_ID,
            'artikel': 'Gouda belegen geraspt',
            'aantal': 1,
        }]
    }

    projected = _inventory_alias_projection(main_module, payload)

    assert projected['rows'][0]['image_url'] == 'https://images.example.test/gouda.jpg'


def test_inventory_preview_uses_household_barcode_for_catalog_image():
    main_module = SimpleNamespace(
        engine=CanonicalBarcodeProjectionEngine(),
        text=lambda value: value,
    )
    payload = {
        'rows': [{
            'id': INVENTORY_ID,
            'household_article_id': ARTICLE_ID,
            'artikel': 'Rijstwafel',
            'aantal': 1,
        }]
    }

    projected = _inventory_alias_projection(main_module, payload)

    assert projected['rows'][0]['image_url'] == 'https://images.example.test/rijstwafel.jpg'


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



def test_almost_out_can_reuse_exact_confirmed_catalog_image_from_receipt():
    with CentralCatalogProjectionEngine().begin() as conn:
        images = resolve_household_catalog_images(conn, lambda query: query, [{
            'id': ARTICLE_ID, 'household_id': 'household-a', 'naam': 'Bio dadeltjes',
            'barcode': '', 'global_product_id': None, 'image_url': '',
        }])
    assert images == {ARTICLE_ID: 'https://images.example.test/bio-dadeltjes.jpg'}


def test_almost_out_can_reuse_canonical_household_gtin():
    with CanonicalBarcodeProjectionEngine().begin() as conn:
        images = resolve_household_catalog_images(conn, lambda query: query, [{
            'id': ARTICLE_ID, 'household_id': 'household-a', 'barcode': '8712345678901',
            'global_product_id': None, 'image_url': '',
        }])
    assert images == {ARTICLE_ID: 'https://images.example.test/rijstwafel.jpg'}


def test_almost_out_never_guesses_ambiguous_receipt_product():
    with CentralCatalogProjectionEngine(ambiguous=True).begin() as conn:
        images = resolve_household_catalog_images(conn, lambda query: query, [{
            'id': ARTICLE_ID, 'household_id': 'household-a', 'naam': 'Bio dadeltjes',
            'barcode': '', 'global_product_id': None, 'image_url': '',
        }])
    assert images == {}


def _unlinked_receipt_article():
    return {
        'id': ARTICLE_ID, 'household_id': 'household-a',
        'naam': 'Bio dadeltjes', 'global_product_id': None,
        'barcode': '', 'image_url': '',
    }


def test_confirmed_synonym_photo_is_used_when_own_catalog_product_has_no_photo():
    engine = SynonymPhotoEngine()
    with engine.begin() as conn:
        images = resolve_household_catalog_images(conn, lambda value: value, [_unlinked_receipt_article()])
    assert images == {ARTICLE_ID: 'https://images.example.test/confirmed-peer.jpg'}
    assert engine.conn.synonym_queries == 1


def test_own_catalog_photo_has_priority_over_confirmed_synonym():
    engine = SynonymPhotoEngine(own_image='https://images.example.test/own.jpg')
    with engine.begin() as conn:
        images = resolve_household_catalog_images(conn, lambda value: value, [_unlinked_receipt_article()])
    assert images == {ARTICLE_ID: 'https://images.example.test/own.jpg'}
    assert engine.conn.synonym_queries == 0


def test_no_photo_when_neither_own_product_nor_confirmed_synonym_has_one():
    engine = SynonymPhotoEngine(peer_image='')
    with engine.begin() as conn:
        images = resolve_household_catalog_images(conn, lambda value: value, [_unlinked_receipt_article()])
    assert images == {}


def test_direct_catalog_identity_is_not_replaced_by_different_receipt_product():
    engine = SynonymPhotoEngine()
    article = {**_unlinked_receipt_article(), 'global_product_id': 'different-global-product'}
    with engine.begin() as conn:
        images = resolve_household_catalog_images(conn, lambda value: value, [article])
    # A historical receipt link to global-product-a cannot override this known
    # central identity. Nor can the peer of global-product-a be borrowed.
    assert images == {}


def test_ambiguous_catalog_identification_never_borrows_synonym_photo():
    engine = SynonymPhotoEngine(ambiguous=True)
    with engine.begin() as conn:
        images = resolve_household_catalog_images(conn, lambda value: value, [_unlinked_receipt_article()])
    assert images == {}
    assert engine.conn.synonym_queries == 0


def test_inventory_uses_confirmed_synonym_photo_not_broad_gpc_representative():
    engine = SynonymPhotoEngine()
    payload = {'rows': [{'id': INVENTORY_ID, 'household_article_id': ARTICLE_ID, 'artikel': 'Bio dadeltjes'}]}
    result = _inventory_alias_projection(SimpleNamespace(engine=engine, text=lambda x: x), payload)
    assert result['rows'][0]['image_url'] == 'https://images.example.test/confirmed-peer.jpg'


def test_almost_out_image_fallback_happens_after_visibility_filtering():
    source = (Path(__file__).resolve().parents[1] / 'app' / 'main.py').read_text(encoding='utf-8')
    body = source.split('def build_almost_out_items(', 1)[1].split('def get_household_article_details_for_inventory(', 1)[0]
    assert body.index("if evaluation.get('include_in_almost_out'):") < body.index(
        'images = resolve_household_catalog_images(conn, text, source_rows)'
    )
    assert "ha.global_product_id, ha.barcode" in body
    assert "item['image_url'] = images.get(" in body


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
    test_inventory_preview_uses_canonical_product_identity_image()
    test_inventory_preview_uses_household_barcode_for_catalog_image()
    test_inventory_preview_does_not_guess_image_when_one_household_article_maps_to_multiple_products()
    test_confirmed_synonym_photo_is_used_when_own_catalog_product_has_no_photo()
    test_own_catalog_photo_has_priority_over_confirmed_synonym()
    test_no_photo_when_neither_own_product_nor_confirmed_synonym_has_one()
    test_ambiguous_catalog_identification_never_borrows_synonym_photo()
    test_direct_catalog_identity_is_not_replaced_by_different_receipt_product()
    test_inventory_uses_confirmed_synonym_photo_not_broad_gpc_representative()
    test_inventory_inline_household_name_does_not_rename_inventory_identity()
    print('HOUSEHOLD_ALIAS_INVENTORY_PROJECTION_GREEN')


if __name__ == '__main__':
    run_contract()
