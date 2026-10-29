"""Synthetic matching, authorization, atomic persistence and migration contracts."""
import importlib.util
import os
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import patch
from uuid import uuid4

from alembic.migration import MigrationContext
from alembic.operations import Operations
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url

from app.api import article_synonym_routes as routes
from app.api import catalog_routes
from app.services import article_synonym_service as service

ROOT = Path(__file__).resolve().parents[1]


def product(pid, name, gtin='', brick='milk', retailer_code='ah', **extra):
    return dict(id=pid, name=name, brand='', variant='', primary_gtin=gtin,
                size_value='1', size_unit='l', brick_code=brick, article_codes=[],
                retailer_code=retailer_code, store_name=service._store_name(retailer_code), image_url='', **extra)


def migration_module(name):
    spec = importlib.util.spec_from_file_location('article_synonym_migration', ROOT/f'alembic/versions/{name}.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class MatchingTest(unittest.TestCase):
    def test_cross_retailer_different_gtins(self):
        items = [product('a', 'AH Halfvolle melk', '08719587325926'), product('b', 'Jumbo Halfvolle melk', '08718452513666', retailer_code='jumbo'), product('c', 'Appels', brick='fruit')]
        result = service.suggest_pairs(items)
        self.assertEqual([(p['left']['id'], p['right']['id']) for p in result], [('a','b')])
        self.assertGreater(result[0]['score'], .9)
        self.assertEqual(service.suggest_pairs(items, [('a','b')]), [])

    def test_same_gtin_is_not_synonym(self):
        self.assertEqual(service.suggest_pairs([product('a','Melk','08719587325926'), product('b','Melk','08719587325926',retailer_code='jumbo')]), [])

    def test_same_or_unknown_store_cannot_be_confirmed_as_cross_store_synonym(self):
        self.assertEqual(service.suggest_pairs([product('a', 'Melk'), product('b', 'Melk')]), [])
        self.assertEqual(service.suggest_pairs([product('a', 'Melk'), product('b', 'Melk', retailer_code='')]), [])

    def test_same_retailer_code_is_not_synonym(self):
        items = [product('a','Melk'), product('b','Melk',retailer_code='jumbo')]
        for item in items:
            item['article_codes'] = ['ah: 123']
        self.assertEqual(service.suggest_pairs(items), [])

    def test_brick_conflict_excluded(self):
        self.assertEqual(service.suggest_pairs([product('a','Halfvolle melk'), product('b','Halfvolle melk', brick='fruit', retailer_code='jumbo')]), [])

    def test_distinct_packaging_preserved(self):
        a, b = product('a','Halfvolle melk'), product('b','Halfvolle melk', retailer_code='jumbo')
        b['size_value'] = '2'
        result = service.suggest_pairs([a,b])[0]
        self.assertEqual(result['left']['size_value'], '1')
        self.assertEqual(result['right']['size_value'], '2')
        self.assertIn('variant', result['warning'])

    def test_deterministic_unique_unordered_pairs(self):
        items = [product(str(i), 'Halfvolle melk', retailer_code='ah' if i%2 else 'jumbo') for i in range(12)]
        result = service.suggest_pairs(items)
        self.assertTrue(result)
        self.assertEqual(result, service.suggest_pairs(list(reversed(items))))
        self.assertEqual(len({p['id'] for p in result}), len(result))
        self.assertTrue(all(p['left']['id'] < p['right']['id'] for p in result))


class StoreTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        url = os.getenv('INHUIS_ARTICLE_SYNONYMS_TEST_DATABASE_URL', '')
        if not url:
            raise unittest.SkipTest('Expliciete, geïsoleerde PostgreSQL-testdatabase vereist')
        parsed = make_url(url)
        if parsed.get_backend_name() != 'postgresql' or not (parsed.database or '').endswith('_article_synonyms_test'):
            raise RuntimeError('Weiger verbinding met niet-geïsoleerde artikel-synoniemen database')
        cls.base_engine = create_engine(url)

    @classmethod
    def tearDownClass(cls):
        if hasattr(cls, 'base_engine'):
            cls.base_engine.dispose()

    def setUp(self):
        self.schema = 'article_synonyms_test_' + uuid4().hex
        with self.base_engine.begin() as conn:
            conn.exec_driver_sql(f'CREATE SCHEMA "{self.schema}"')
        self.engine = create_engine(self.base_engine.url, connect_args={'options': f'-csearch_path={self.schema}'})
        with self.engine.begin() as conn:
            conn.exec_driver_sql('CREATE TABLE global_products(id TEXT PRIMARY KEY, name TEXT, brand TEXT, variant TEXT, primary_gtin TEXT, size_value NUMERIC, size_unit TEXT, status TEXT, image_url TEXT, source TEXT)')
            conn.exec_driver_sql('CREATE TABLE global_product_gpc_bricks(global_product_id TEXT PRIMARY KEY, brick_code TEXT)')
            conn.exec_driver_sql('CREATE TABLE external_article_product_links(global_product_id TEXT, retailer_code TEXT, external_article_code TEXT, status TEXT)')
            # Install the real PostgreSQL maintenance gate before the new catalog table.
            maintenance = migration_module('20261021_01_server_maintenance')
            module = migration_module('20261026_01_article_synonyms')
            with Operations.context(MigrationContext.configure(conn)):
                maintenance.upgrade()
                module.upgrade()
            for pid, gtin in [('a','8719587325926'), ('b','8718452513666'), ('c','')]:
                conn.execute(text("INSERT INTO global_products (id,name,brand,variant,primary_gtin,size_value,size_unit,status,image_url,source) VALUES (:id,'Halfvolle melk','','',:gtin,1,'l','active','', 'catalog')"), dict(id=pid, gtin=gtin))
            conn.execute(text("INSERT INTO external_article_product_links VALUES ('a','ah','823326','confirmed'),('b','jumbo','394270','confirmed')"))

    def tearDown(self):
        self.engine.dispose()
        with self.base_engine.begin() as conn:
            conn.exec_driver_sql(f'DROP SCHEMA "{self.schema}" CASCADE')

    def selection(self, conn):
        p = service.suggest_pairs(service.load_products(conn))[0]
        return dict(left_product_id=p['left']['id'], right_product_id=p['right']['id'], fingerprint=p['fingerprint'])

    def test_read_only_excludes_codeless_invalid_and_deleted(self):
        with self.engine.begin() as conn:
            conn.execute(text("INSERT INTO global_products (id,name,brand,variant,primary_gtin,size_value,size_unit,status) VALUES ('d','Halfvolle melk','','','not8719587325926',1,'l','active')"))
            conn.execute(text("INSERT INTO global_products (id,name,brand,variant,primary_gtin,size_value,size_unit,status) VALUES ('e','Halfvolle melk','','','8719587325926',1,'l','deleted')"))
            self.assertEqual([p['id'] for p in service.load_products(conn)], ['a','b'])
            service.suggest_pairs(service.load_products(conn))
            self.assertEqual(service.confirmed_pairs(conn), set())

    def test_retailer_article_code_qualifies_without_gtin(self):
        with self.engine.begin() as conn:
            conn.execute(text("INSERT INTO external_article_product_links VALUES ('c','jumbo','123','confirmed')"))
            self.assertEqual([p['id'] for p in service.load_products(conn)], ['a','b','c'])
            conn.execute(text("UPDATE external_article_product_links SET status='inactive'"))
            self.assertEqual([p['id'] for p in service.load_products(conn)], ['a','b'])

    def test_catalog_image_and_confirmed_shop_are_projected(self):
        with self.engine.begin() as conn:
            conn.execute(text("UPDATE global_products SET image_url='https://example.org/test.jpg' WHERE id='a'"))
            items = service.load_products(conn)
            self.assertEqual([p['store_name'] for p in items], ['Albert Heijn', 'Jumbo'])
            self.assertEqual(items[0]['image_url'], 'https://example.org/test.jpg')
            self.assertEqual(items[1]['image_url'], '')
            self.assertEqual(len(service.suggest_pairs(items)), 1)

    def test_photo_change_does_not_invalidate_selection(self):
        with self.engine.begin() as conn:
            selection = self.selection(conn)
            conn.execute(text("UPDATE global_products SET image_url='data:image/png;base64,Zm9v' WHERE id='a'"))
            self.assertEqual(service.confirm_pairs(conn, [selection], 'actor'), {'linked': 1, 'already_linked': 0})

    def test_bulk_idempotent_and_persisted_with_actor(self):
        with self.engine.begin() as conn:
            selection = self.selection(conn)
            self.assertEqual(service.confirm_pairs(conn, [selection,selection], 'actor'), {'linked':1,'already_linked':0})
        with self.engine.begin() as conn:
            self.assertEqual(service.confirm_pairs(conn, [selection], 'other'), {'linked':0,'already_linked':1})
            self.assertEqual(conn.execute(text('SELECT confirmed_by FROM article_synonym_links')).scalar_one(), 'actor')
            self.assertEqual(service.suggest_pairs(service.load_products(conn), service.confirmed_pairs(conn)), [])
            self.assertEqual(conn.execute(text('SELECT COUNT(*) FROM global_products')).scalar_one(), 3)

    def test_catalog_counts_distinct_direct_other_shops_not_synonym_products(self):
        with self.engine.begin() as conn:
            conn.execute(text("""
                INSERT INTO global_products
                    (id,name,brand,variant,primary_gtin,size_value,size_unit,status,image_url,source)
                VALUES
                    ('d','Melk','','','',1,'l','active','','plus'),
                    ('e','Melk','','','',1,'l','active','','catalog'),
                    ('f','Melk','','','',1,'l','active','','catalog'),
                    ('g','Melk','','','',1,'l','deleted','','lidl')
            """))
            conn.execute(text("""
                INSERT INTO external_article_product_links VALUES
                    ('e','jumbo','SKU2','confirmed'),
                    ('f','ah','SKU3','confirmed'),
                    ('f','jumbo','SKU4','confirmed')
            """))
            for left, right in [('a','b'), ('a','d'), ('a','e'), ('a','f'), ('a','g'), ('b','d')]:
                conn.execute(text("""
                    INSERT INTO article_synonym_links
                        (left_product_id,right_product_id,confirmed_by,source_fingerprint,method,score)
                    VALUES (:left,:right,'tester','stable','fixture',0.9)
                """), {'left': left, 'right': right})
            # This isolated fixture uses a minimal retailer-link table; Catalogus
            # also needs the presentation alias column from the full schema.
            conn.exec_driver_sql('ALTER TABLE external_article_product_links ADD COLUMN receipt_text_normalized TEXT')

        # One AH article linked to two different Jumbo products and one PLUS
        # product has two linked stores. Ambiguous and deleted peers do not add
        # a store. A--B and B--D never imply a further A--D relation.
        with patch.object(catalog_routes, 'engine', self.engine):
            counts = {
                product_id: catalog_routes._catalog_row(product_id)['linked_store_count']
                for product_id in ('a', 'b', 'c', 'd', 'e', 'f')
            }
            self.assertEqual(counts, {'a': 2, 'b': 2, 'c': 0, 'd': 2, 'e': 1, 'f': 0})
            filtered = catalog_routes.list_catalog(
                linked_store_count='2', sort_by='linked_store_count',
                sort_direction='desc', limit=10, offset=0,
            )
            self.assertEqual(filtered['total'], 3)
            self.assertEqual({item['id'] for item in filtered['items']}, {'a', 'b', 'd'})

        with self.engine.begin() as conn:
            conn.execute(text("UPDATE external_article_product_links SET status='inactive' WHERE global_product_id='e'"))
        with patch.object(catalog_routes, 'engine', self.engine):
            self.assertEqual(catalog_routes._catalog_row('a')['linked_store_count'], 2)
            self.assertEqual(catalog_routes._catalog_row('e')['linked_store_count'], 0)

    def test_whole_bulk_rejected_on_stale_selection(self):
        with self.assertRaises(HTTPException) as error:
            with self.engine.begin() as conn:
                selection = self.selection(conn)
                invalid = {**selection, 'fingerprint':'0'*64}
                service.confirm_pairs(conn, [selection,invalid], 'actor')
        self.assertEqual(error.exception.status_code, 409)
        with self.engine.connect() as conn:
            self.assertEqual(service.confirmed_pairs(conn), set())

    def test_renamed_or_code_removed_selection_rejected(self):
        for update in ["UPDATE global_products SET name='Volle melk' WHERE id='b'", "UPDATE global_products SET primary_gtin='' WHERE id='b'"]:
            with self.engine.begin() as conn:
                selection = self.selection(conn)
                conn.execute(text(update))
                with self.assertRaises(HTTPException):
                    service.confirm_pairs(conn,[selection],'actor')
                conn.execute(text("UPDATE global_products SET name='Halfvolle melk', primary_gtin='8718452513666' WHERE id='b'"))

    def test_downgrade_only_removes_synonym_table(self):
        with self.engine.begin() as conn:
            with Operations.context(MigrationContext.configure(conn)):
                migration_module('20261026_01_article_synonyms').downgrade()
            self.assertEqual(conn.execute(text('SELECT COUNT(*) FROM global_products')).scalar_one(), 3)


class ApiTest(unittest.TestCase):
    def setUp(self):
        app = FastAPI()
        app.include_router(routes.router)
        self.client = TestClient(app)

    def test_anonymous_and_regular_and_technical_forbidden(self):
        for status in [401,403]:
            with patch.object(routes, 'require_platform_permission_from_session', side_effect=HTTPException(status)):
                self.assertEqual(self.client.get('/api/external-databases/article-synonyms').status_code, status)
                self.assertEqual(self.client.get('/api/external-databases/article-synonyms/analysis').status_code, status)
                self.assertEqual(self.client.get('/api/external-databases/article-synonyms/analysis/a/candidates').status_code, status)
                self.assertEqual(self.client.post('/api/external-databases/article-synonyms/link', json={'selections':[dict(left_product_id='a',right_product_id='b',fingerprint='0'*64)]}).status_code,status)
        with patch.object(routes, 'require_platform_permission_from_session', return_value=SimpleNamespace(is_frontteam=False,is_platform_superuser=False)):
            self.assertEqual(self.client.get('/api/external-databases/article-synonyms').status_code,403)

    def test_both_roles_authorized_via_canonical_permission(self):
        for superuser, frontteam in [(True,False),(False,True),(True,True)]:
            actor = SimpleNamespace(is_platform_superuser=superuser,is_frontteam=frontteam,user_id='actor')
            with patch.object(routes, 'require_platform_permission_from_session', return_value=actor) as check:
                self.assertIs(routes._actor('platform.external_products.link_existing'), actor)
                check.assert_called_once_with('platform.external_products.link_existing')

    def test_request_limits_and_forged_authority_rejected(self):
        for body in [{'selections':[]},{'selections':[{}]}, {'selections':[], 'role':'Superuser'}]:
            self.assertEqual(self.client.post('/api/external-databases/article-synonyms/link',json=body).status_code,422)
        with self.assertRaises(ValueError):
            routes.BulkSelection(selections=[dict(left_product_id='a',right_product_id='b',fingerprint='0'*64)]*201)



class SynonymAnalysisContractTest(unittest.TestCase):
    def test_summary_reuses_direct_links_without_transitive_inference(self):
        products = [product('a', 'Halfvolle melk', retailer_code='ah'),
                    product('b', 'Halfvolle melk', retailer_code='jumbo'),
                    product('c', 'Halfvolle melk', retailer_code='lidl')]
        suggestion = [{'left': products[0], 'right': products[2], 'score': .8}]
        result = service.build_synonym_analysis(products, {('a', 'b')}, suggestion,
                                                {'a': 'Melk', 'b': 'Melk', 'c': 'Melk'})
        self.assertEqual(result['summary']['confirmed_pairs'], 1)
        self.assertEqual(result['summary']['candidate_pairs'], 1)
        rows = {row['id']: row for row in result['items']}
        self.assertEqual(rows['a']['linked_stores'], ['Jumbo'])
        self.assertEqual(rows['a']['status'], 'review')
        self.assertEqual(rows['c']['linked_stores'], [])
        self.assertEqual(sum(group['articles'] for group in result['groups']), 3)

    def test_missing_retailer_not_assumed_to_be_a_supermarket(self):
        products = [product('a', 'Melk', retailer_code=''),
                    product('b', 'Melk', retailer_code='jumbo')]
        result = service.build_synonym_analysis(products, {('a', 'b')}, [])
        self.assertEqual(result['summary']['confirmed_pairs'], 0)
        self.assertEqual(result['summary']['insufficient_articles'], 1)
        self.assertEqual(result['summary']['no_candidate_articles'], 1)


    def test_buckets_0_1_2_3_plus_are_direct_product_counts(self):
        products = [
            product('a', 'Halfvolle melk', retailer_code='ah'),
            product('b', 'Halfvolle melk', retailer_code='jumbo'),
            product('c', 'Halfvolle melk', retailer_code='lidl'),
            product('d', 'Halfvolle melk', retailer_code='plus'),
            product('e', 'Halfvolle melk', retailer_code='aldi'),
            product('f', 'Halfvolle melk', retailer_code='picnic'),
        ]
        analysis = service.build_synonym_analysis(
            products, {('a', 'b'), ('a', 'c'), ('a', 'd'), ('c', 'd')}, [])
        self.assertEqual(analysis['summary']['synonym_buckets'], {'0': 2, '1': 1, '2': 2, '3+': 1})
        rows = {p['id']: p for p in analysis['items']}
        self.assertEqual(rows['a']['synonym_count'], 3)
        self.assertEqual(rows['b']['synonym_count'], 1)
        self.assertEqual(rows['c']['synonym_count'], 2)
        self.assertEqual(rows['e']['synonym_count'], 0)
        self.assertEqual(rows['a']['synonym_names'], ['Halfvolle melk'] * 3)
        # One new direct pair updates BOTH participants, without transitivity.
        updated = service.build_synonym_analysis(
            products, {('a', 'b'), ('a', 'c'), ('a', 'd'), ('c', 'd'), ('b', 'e')}, [])
        self.assertEqual(updated['summary']['synonym_buckets'], {'0': 1, '1': 1, '2': 3, '3+': 1})
        self.assertEqual({p['id']: p['synonym_count'] for p in updated['items']}['e'], 1)

    def test_candidate_list_maximum_five_and_only_existing_valid_pairs(self):
        products = [product('a', 'Halfvolle melk', retailer_code='ah')]
        products.extend(product(str(i), 'Halfvolle melk', retailer_code='jumbo') for i in range(10))
        pairs = service.candidate_pairs_for_product(products, set(), 'a')
        self.assertIsNotNone(pairs)
        self.assertLessEqual(len(pairs), 5)
        self.assertTrue(all('a' in (p['left']['id'], p['right']['id']) for p in pairs))
        self.assertEqual(pairs, service.candidate_pairs_for_product(products, set(), 'a'))
        self.assertEqual(service.candidate_pairs_for_product(products, set(), 'unknown'), None)
        self.assertTrue(all((pair['left']['id'], pair['right']['id']) != ('0', 'a')
                            for pair in service.candidate_pairs_for_product(products, {('0', 'a')}, 'a')))
        self.assertLessEqual(len(service.candidate_pairs_for_product(products, {('0', 'a')}, 'a')), 5)

if __name__ == '__main__':
    unittest.main()
