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

    def test_store_is_never_required_for_a_synonym(self):
        for a_store, b_store in [('ah', 'ah'), ('ah', 'jumbo'), ('', ''), ('', 'jumbo')]:
            pair = service.suggest_pairs([
                product('a', 'Halfvolle melk', retailer_code=a_store),
                product('b', 'Halfvolle melk', retailer_code=b_store),
            ])[0]
            self.assertTrue(pair['linkable'])
            self.assertEqual(pair['match_basis'], 'product_similarity')

    def test_same_retailer_code_is_not_synonym(self):
        items = [product('a','Melk'), product('b','Melk',retailer_code='jumbo')]
        for item in items:
            item['article_codes'] = ['ah: 123']
        self.assertEqual(service.suggest_pairs(items), [])

    def test_brick_conflict_excluded(self):
        self.assertEqual(service.suggest_pairs([product('a','Halfvolle melk'), product('b','Halfvolle melk', brick='fruit', retailer_code='jumbo')]), [])

    def test_canonical_receipt_store_aliases(self):
        self.assertEqual(service._retailer_code('Albert Heijn'), 'ah')
        self.assertEqual(service._retailer_code('AH'), 'ah')
        self.assertEqual(service._retailer_code('Lidl Nederland GmbH'), 'lidl')
        self.assertEqual(service._retailer_code('Lidl'), 'lidl')

    def test_multiple_stores_are_metadata_not_pairing_restrictions(self):
        multi = product('a', 'Halfvolle melk', retailer_code='')
        multi['retailer_codes'] = ['ah', 'jumbo']
        different = product('b', 'Halfvolle melk', retailer_code='lidl')
        overlapping = product('c', 'Halfvolle melk', retailer_code='jumbo')
        matches = service.suggest_pairs([multi, different, overlapping])
        pairs = {(m['left']['id'], m['right']['id']) for m in matches}
        self.assertIn(('a', 'b'), pairs)
        self.assertIn(('a', 'c'), pairs)
        analysis = service.build_synonym_analysis([multi, different], {('a', 'b')}, [])
        self.assertEqual(analysis['summary']['confirmed_pairs'], 1)
        self.assertEqual(analysis['summary']['insufficient_articles'], 0)

    def test_no_unconfirmed_receipt_or_name_based_retailer_fallback(self):
        a = product('a', 'AH Halfvolle melk', retailer_code='')
        a['retailer_codes'] = []
        b = product('b', 'Jumbo Halfvolle melk', retailer_code='jumbo')
        self.assertTrue(service.suggest_pairs([a, b]))

    def test_name_based_candidates_are_confirmable_and_keep_store_unknown(self):
        a = product('a', 'Aardappelen', retailer_code='')
        b = product('b', 'Aardappelen kruimig', retailer_code='')
        c = product('c', 'Andere producten', retailer_code='jumbo', brick='fruit')
        self.assertTrue(service.suggest_pairs([a, b, c]))
        proposals = service.suggest_pairs([a, b, c], include_name_only=True)
        pair = next(p for p in proposals if {p['left']['id'], p['right']['id']} == {'a', 'b'})
        self.assertTrue(pair['linkable'])
        self.assertEqual(pair['match_basis'], 'product_similarity')
        analysis = service.build_synonym_analysis([a, b, c], set(), proposals)
        row = next(r for r in analysis['items'] if r['id'] == 'a')
        self.assertEqual(row['status'], 'review')
        self.assertEqual(row['store'], 'Winkel onbekend')
        self.assertGreater(len(row['pending']), 0)
        self.assertGreater(analysis['summary']['candidate_pairs'], 0)
        self.assertEqual(analysis['summary']['name_only_pairs'], 0)

    def test_same_store_name_match_is_confirmable_after_manual_review(self):
        a = product('a', 'Melk', retailer_code='ah')
        b = product('b', 'Melk', retailer_code='ah')
        pair = service.suggest_pairs([a, b], include_name_only=True)[0]
        self.assertTrue(pair['linkable'])
        self.assertEqual(service.suggest_pairs([a, b]), [pair])

    def test_two_similarly_named_products_are_not_the_same_identity(self):
        first = product('a', 'Volle melk', gtin='08719587325926', retailer_code='')
        other = product('b', 'Volle melk', gtin='08718452513666', retailer_code='')
        self.assertEqual(
            [(p['left']['id'], p['right']['id']) for p in service.suggest_pairs([first, other])],
            [('a', 'b')],
        )
        options = service.product_link_options([first, other], set(), 'a')
        self.assertEqual([p['id'] for p in options], ['b'])
        self.assertEqual(options[0]['status'], 'suggested')
        self.assertNotEqual(options[0]['id'], first['id'])

    def test_right_options_are_disjoint_linked_suggested_and_all_other(self):
        items = [
            product('a', 'Halfvolle melk', retailer_code=''),
            product('b', 'Halfvolle melk', retailer_code=''),
            product('c', 'Halfvolle melk', retailer_code=''),
            product('d', 'Onverwacht ander product', brick='milk', retailer_code=''),
        ]
        options = service.product_link_options(items, {('a', 'b')}, 'a')
        self.assertEqual([row['id'] for row in options], ['b', 'c', 'd'])
        self.assertEqual([row['status'] for row in options], ['linked', 'suggested', 'other'])
        self.assertEqual([row['linkable'] for row in options], [False, True, True])
        self.assertEqual([row['manual'] for row in options], [True, False, True])
        self.assertEqual(service.product_link_options(items, set(), 'missing'), None)

    def test_identical_gtin_and_conflicting_gpc_cannot_be_selected_manually(self):
        a = product('a', 'Halfvolle melk', gtin='08719587325926', brick='milk')
        b = product('b', 'Melk', gtin='08719587325926', brick='milk')
        c = product('c', 'Appels', brick='fruit')
        options = {row['id']: row for row in service.product_link_options([a, b, c], set(), 'a')}
        self.assertFalse(options['b']['linkable'])
        self.assertFalse(options['c']['linkable'])

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


class SynonymOverviewRouteTest(unittest.TestCase):
    def test_article_index_survives_missing_optional_legacy_classification(self):
        from unittest.mock import MagicMock

        connection = MagicMock()
        fake_engine = MagicMock()
        fake_engine.connect.return_value.__enter__.return_value = connection
        sample = product('a', 'Halfvolle melk', retailer_code='')
        sample['retailer_codes'] = []
        with patch.object(routes, '_actor'), \
                patch.object(routes, 'engine', fake_engine), \
                patch.object(routes, 'load_products', return_value=[sample]), \
                patch.object(routes, 'confirmed_pairs', return_value=set()), \
                patch('sqlalchemy.inspect') as introspection:
            introspection.return_value.has_table.return_value = False
            response = routes.synonym_analysis()
        self.assertEqual(response['summary']['eligible_articles'], 1)
        self.assertEqual(response['summary']['candidate_pairs'], 0)
        self.assertEqual(response['items'][0]['store'], 'Winkel onbekend')
        connection.execute.assert_not_called()


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
            conn.exec_driver_sql('CREATE TABLE external_product_candidates(context_key TEXT, retailer_code TEXT, global_product_id TEXT, is_user_confirmed BOOLEAN, status TEXT, candidate_status TEXT)')
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

    def test_multiple_confirmed_retailer_links_reach_synonym_projection(self):
        with self.engine.begin() as conn:
            conn.execute(text("INSERT INTO external_article_product_links VALUES ('a','lidl-nederland-gmbh','SKU4','confirmed')"))
            items = {item['id']: item for item in service.load_products(conn)}
            self.assertEqual(items['a']['retailer_codes'], ['ah', 'lidl'])
            self.assertEqual(items['a']['retailer_code'], '')
            self.assertIn('Albert Heijn', items['a']['store_name'])
            self.assertIn('Lidl', items['a']['store_name'])
            # 'b' is Jumbo: neither shop overlaps, so the pair remains reviewable.
            suggestions = service.suggest_pairs(list(items.values()))
            self.assertIn(('a', 'b'), [(p['left']['id'], p['right']['id']) for p in suggestions])

    def test_legacy_explicitly_confirmed_candidates_supply_retailer_from_kassa(self):
        with self.engine.begin() as conn:
            # 'c' is a pre-existing coded Catalogus product without any
            # external_article_product_links row or retailer source.
            conn.execute(text("UPDATE global_products SET primary_gtin='8712345678906' WHERE id='c'"))
            conn.execute(text("""
                INSERT INTO external_product_candidates
                (context_key, retailer_code, global_product_id, is_user_confirmed, status, candidate_status)
                VALUES
                ('receipt-line:confirmed', 'Lidl Nederland GmbH', 'c', TRUE, 'linked_to_catalog', 'linked_to_catalog'),
                ('receipt-line:proposed', 'Picnic', 'c', FALSE, 'possible_candidate', 'possible_candidate'),
                ('receipt-line:unlinked', 'Aldi', 'c', TRUE, 'unlinked_from_catalog', 'possible_candidate'),
                ('receipt-line:stale', 'Plus', 'c', TRUE, 'linked_to_catalog', 'unlinked_from_catalog')
            """))
            before = conn.execute(text("SELECT COUNT(*) FROM external_article_product_links")).scalar_one()
            products = {p['id']: p for p in service.load_products(conn)}
            self.assertEqual(products['c']['retailer_codes'], ['lidl'])
            self.assertEqual(products['c']['store_name'], 'Lidl')
            self.assertEqual(products['c']['retailer_code'], 'lidl')
            pairs = service.suggest_pairs(list(products.values()))
            self.assertIn(('a', 'c'), [
                (pair['left']['id'], pair['right']['id']) for pair in pairs
            ])
            analysis = service.build_synonym_analysis(list(products.values()), set(), pairs)
            row = next(item for item in analysis['items'] if item['id'] == 'c')
            self.assertEqual(row['store'], 'Lidl')
            self.assertEqual(row['status'], 'review')
            self.assertGreater(len(row['pending']), 0)
            self.assertEqual(conn.execute(text("SELECT COUNT(*) FROM external_article_product_links")).scalar_one(), before)

    def test_optional_legacy_candidate_table_can_be_absent(self):
        with self.engine.begin() as conn:
            conn.exec_driver_sql('DROP TABLE external_product_candidates')
            products = service.load_products(conn)
            self.assertEqual([p['id'] for p in products], ['a', 'b'])

    def test_conflicting_explicit_candidate_context_does_not_assign_store(self):
        with self.engine.begin() as conn:
            conn.execute(text("UPDATE global_products SET primary_gtin='8712345678906' WHERE id='c'"))
            conn.execute(text("""
                INSERT INTO external_product_candidates
                (context_key, retailer_code, global_product_id, is_user_confirmed, status, candidate_status)
                VALUES
                ('receipt-line:same', 'Lidl', 'c', TRUE, 'linked_to_catalog', 'linked_to_catalog'),
                ('receipt-line:same', 'Lidl', 'b', TRUE, 'linked_to_catalog', 'linked_to_catalog'),
                ('receipt-line:unconfirmed', 'Aldi', 'c', FALSE, 'linked_to_catalog', 'linked_to_catalog')
            """))
            products = {p['id']: p for p in service.load_products(conn)}
            self.assertEqual(products['c']['retailer_codes'], [])
            self.assertEqual(products['b']['retailer_codes'], ['jumbo'])
            # Conflicting source evidence does not invent a store, but the
            # independent products remain eligible for a manual synonym review.
            self.assertTrue(service.suggest_pairs([products['a'], products['c']]))

    def test_similar_products_can_be_confirmed_without_known_store(self):
        with self.engine.begin() as conn:
            conn.execute(text("""
                INSERT INTO global_products
                    (id,name,brand,variant,primary_gtin,size_value,size_unit,status,image_url,source)
                VALUES ('d','Halfvolle melk','','','8712345678906',1,'l','active','','catalog')
            """))
            products = service.load_products(conn)
            pair = next(p for p in service.suggest_pairs(products)
                        if {p['left']['id'], p['right']['id']} == {'a', 'd'})
            self.assertTrue(pair['linkable'])
            result = service.confirm_pairs(conn, [{
                'left_product_id': pair['left']['id'],
                'right_product_id': pair['right']['id'],
                'fingerprint': pair['fingerprint'],
            }], 'tester')
            self.assertEqual(result['linked'], 1)
            analysis = service.build_synonym_analysis(service.load_products(conn),
                service.confirmed_pairs(conn), [])
            row = next(item for item in analysis['items'] if item['id'] == 'd')
            self.assertEqual(row['store'], 'Winkel onbekend')
            self.assertEqual(row['synonym_count'], 1)

    def test_manual_other_catalog_article_can_be_confirmed_without_text_similarity(self):
        with self.engine.begin() as conn:
            conn.execute(text("""
                INSERT INTO global_products
                  (id,name,brand,variant,primary_gtin,size_value,size_unit,status,image_url,source)
                VALUES ('d','Xylofoon','','','8712345678906',1,'l','active','','catalog')
            """))
            products = service.load_products(conn)
            opts = {row['id']: row for row in service.product_link_options(products, set(), 'a')}
            self.assertEqual(opts['d']['status'], 'other')
            self.assertTrue(opts['d']['manual'])
            result = service.confirm_pairs(conn, [{
                'left_product_id': 'a', 'right_product_id': 'd',
                'fingerprint': opts['d']['fingerprint'], 'manual': True,
            }], 'actor')
            self.assertEqual(result['linked'], 1)
            self.assertEqual(service.confirmed_pairs(conn), {('a', 'd')})
            method = conn.execute(text("""
                SELECT method FROM article_synonym_links
                 WHERE left_product_id='a' AND right_product_id='d'
            """)).scalar_one()
            self.assertEqual(method, 'manual_catalog_review_v1')

    def test_self_link_is_blocked_before_any_database_mutation(self):
        with self.engine.begin() as conn:
            with self.assertRaises(HTTPException) as exc:
                service.confirm_pairs(conn, [{
                    'left_product_id': 'a', 'right_product_id': 'a',
                    'fingerprint': 'a' * 64, 'manual': True,
                }], 'actor')
            self.assertEqual(exc.exception.status_code, 409)
            self.assertEqual(service.confirmed_pairs(conn), set())

    def test_manual_selection_requires_current_server_fingerprint(self):
        with self.engine.begin() as conn:
            with self.assertRaises(HTTPException) as exc:
                service.confirm_pairs(conn, [{
                    'left_product_id': 'a', 'right_product_id': 'b',
                    'fingerprint': 'a' * 64, 'manual': True,
                }], 'actor')
            self.assertEqual(exc.exception.status_code, 409)
            self.assertEqual(service.confirmed_pairs(conn), set())

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

        # Confirmed Jumbo + Lidl evidence for e adds another distinct peer
        # shop to a, without inventing an exclusive shop for e.
        with self.engine.begin() as conn:
            conn.execute(text("INSERT INTO external_article_product_links (global_product_id,retailer_code,external_article_code,status) VALUES ('e','lidl-nederland-gmbh','E-2','confirmed')"))
        with patch.object(catalog_routes, 'engine', self.engine):
            self.assertEqual(catalog_routes._catalog_row('a')['linked_store_count'], 3)
            self.assertEqual(catalog_routes._catalog_row('e')['linked_store_count'], 1)

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

    def test_ed2_catalog_synonyms_almost_out_cross_store_chain(self):
        """Isolated PostgreSQL chain: ED2 -> Catalogus -> confirmed synonym -> Bijna op.

        ED2 uses the real central-link resolver against the test schema. Only
        receipt-source extraction is stubbed; there are no real receipts or
        household records. The synonym relation alone must never bypass missing
        GPC/product-type evidence in Bijna op.
        """
        import json
        from app.services import external_unlinked_articles_service as ed2
        from app.services import almost_out_group_service as almost_out

        household_id = "synonym-chain-isolated-household"
        with self.engine.begin() as conn:
            # Add the minimal *isolated* schema required by the production ED2
            # read projection and Bijna op grouping. Existing StoreTest schemas
            # are unique per test and are destroyed by tearDown.
            for column, declaration in (
                ("id", "TEXT"),
                ("receipt_text_normalized", "TEXT"),
                ("confirmed_at", "TIMESTAMPTZ"),
                ("confirmed_by", "TEXT"),
                ("source_candidate_id", "TEXT"),
                ("created_at", "TIMESTAMPTZ"),
                ("updated_at", "TIMESTAMPTZ"),
            ):
                conn.exec_driver_sql(
                    f"ALTER TABLE external_article_product_links ADD COLUMN {column} {declaration}"
                )
            conn.exec_driver_sql("""
                CREATE TABLE product_identities (
                    global_product_id TEXT, identity_type TEXT, identity_value TEXT
                )
            """)
            conn.exec_driver_sql("""
                CREATE TABLE product_group_memberships (
                    global_product_id TEXT, inventory_group_key TEXT,
                    active INTEGER, updated_at TIMESTAMPTZ, created_at TIMESTAMPTZ
                )
            """)
            conn.exec_driver_sql("""
                CREATE TABLE product_inventory_groups (
                    inventory_group_key TEXT, gpc_brick_code TEXT, source TEXT,
                    active INTEGER, display_name TEXT
                )
            """)
            conn.exec_driver_sql("""
                CREATE TABLE gpc_product_groups (
                    gpc_brick_code TEXT, language_code TEXT, active BOOLEAN,
                    gpc_brick_name TEXT, gpc_brick_name_en TEXT, source_version TEXT,
                    gpc_class_code TEXT, gpc_class_name TEXT,
                    gpc_family_code TEXT, gpc_family_name TEXT
                )
            """)
            conn.exec_driver_sql("""
                CREATE TABLE household_articles (
                    id TEXT, household_id TEXT, global_product_id TEXT, status TEXT
                )
            """)
            conn.exec_driver_sql("""
                CREATE TABLE global_product_consumption_profiles (
                    global_product_id TEXT, facts_json TEXT
                )
            """)
            conn.exec_driver_sql("""
                CREATE TABLE inventory (
                    id TEXT, household_id TEXT, household_article_id TEXT,
                    naam TEXT, aantal NUMERIC, space_id TEXT, sublocation_id TEXT,
                    status TEXT
                )
            """)
            conn.exec_driver_sql("CREATE TABLE spaces (id TEXT, household_id TEXT, naam TEXT)")
            conn.exec_driver_sql("CREATE TABLE sublocations (id TEXT, space_id TEXT, naam TEXT)")
            conn.exec_driver_sql("""
                CREATE TABLE inventory_events (
                    id TEXT, household_id TEXT, article_id TEXT,
                    event_type TEXT, created_at TIMESTAMPTZ,
                    purchase_date TEXT, quantity NUMERIC
                )
            """)
            conn.execute(text("""
                INSERT INTO gpc_product_groups
                  (gpc_brick_code, language_code, active, gpc_brick_name,
                   gpc_brick_name_en, source_version)
                VALUES ('10000025', 'nl', TRUE, 'Halfvolle melk',
                        'Semi-skimmed milk', 'test')
            """))
            conn.execute(text("""
                INSERT INTO product_inventory_groups
                  (inventory_group_key, gpc_brick_code, source, active, display_name)
                VALUES ('gpc:10000025', '10000025', 'gs1_gpc_official', 1, 'Halfvolle melk')
            """))
            for pid, name, gtin, receipt_code, retailer, volume in (
                ("a", "AH Halfvolle melk", "8719587325926", "823326", "ah", 1.0),
                ("b", "Jumbo Halfvolle melk", "8718452513666", "394270", "jumbo", 0.5),
            ):
                conn.execute(text("""
                    UPDATE global_products SET name=:name, size_value=:volume,
                        size_unit='l' WHERE id=:id
                """), {"name": name, "volume": volume, "id": pid})
                conn.execute(text("""
                    UPDATE external_article_product_links
                    SET id=:link_id, receipt_text_normalized=:receipt_name,
                        confirmed_at=CURRENT_TIMESTAMP,
                        confirmed_by='external_databases_off_link',
                        created_at=CURRENT_TIMESTAMP, updated_at=CURRENT_TIMESTAMP
                    WHERE global_product_id=:id AND retailer_code=:retailer
                      AND external_article_code=:receipt_code
                """), {
                    "link_id": "ed2-" + pid, "receipt_name": name.lower(),
                    "id": pid, "retailer": retailer, "receipt_code": receipt_code,
                })
                conn.execute(text("""
                    INSERT INTO product_identities
                      (global_product_id, identity_type, identity_value)
                    VALUES (:id, 'gtin', :gtin)
                """), {"id": pid, "gtin": gtin})
                conn.execute(text("""
                    INSERT INTO product_group_memberships
                      (global_product_id, inventory_group_key, active, created_at, updated_at)
                    VALUES (:id, 'gpc:10000025', 1, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
                """), {"id": pid})
                conn.execute(text("""
                    INSERT INTO global_product_gpc_bricks (global_product_id, brick_code)
                    VALUES (:id, '10000025')
                """), {"id": pid})
                conn.execute(text("""
                    INSERT INTO household_articles (id, household_id, global_product_id, status)
                    VALUES (:article, :household, :id, 'active')
                """), {"article": "ha-" + retailer, "household": household_id, "id": pid})
                conn.execute(text("""
                    INSERT INTO global_product_consumption_profiles (global_product_id, facts_json)
                    VALUES (:id, :facts)
                """), {"id": pid, "facts": json.dumps({"name": name})})
                conn.execute(text("""
                    INSERT INTO inventory
                      (id, household_id, household_article_id, naam, aantal, status)
                    VALUES (:id, :household, :article, :name, :amount, 'active')
                """), {
                    "id": "inv-" + pid, "household": household_id,
                    "article": "ha-" + retailer, "name": name,
                    "amount": 1 if pid == "a" else 2,
                })

        receipt_sources = [
            {
                "receipt_item_id": "receipt-table-line:chain-ah",
                "receipt_line_text": "AH Halfvolle melk",
                "retailer_code": "ah",
                "external_article_code": "823326",
                "quantity_label": "1 l",
            },
            {
                "receipt_item_id": "receipt-table-line:chain-jumbo",
                "receipt_line_text": "Jumbo Halfvolle melk",
                "retailer_code": "jumbo",
                "external_article_code": "394270",
                "quantity_label": "500 ml",
            },
        ]
        # Only the receipt source is synthetic: ED2's confirmed-link resolver,
        # completeness guard, Catalogus joins and almost-out grouping are real.
        with self.engine.connect() as conn, patch.object(
            ed2, "_source_articles", side_effect=lambda _conn: iter(receipt_sources)
        ):
            overview = ed2.list_all_external_articles(conn=conn)
        self.assertEqual(overview["counts"], {
            "unlinked": 0, "classification_pending": 0, "linked": 2,
        })
        rows = {row["retailer_code"]: row for row in overview["items"]}
        self.assertEqual(set(rows), {"ah", "jumbo"})
        self.assertEqual(rows["ah"]["receipt_article_number"], "823326")
        self.assertEqual(rows["jumbo"]["receipt_article_number"], "394270")
        self.assertEqual(rows["ah"]["catalog_product_id"], "a")
        self.assertEqual(rows["jumbo"]["catalog_product_id"], "b")
        self.assertEqual(rows["ah"]["article_code"], "8719587325926")
        self.assertEqual(rows["jumbo"]["article_code"], "8718452513666")
        self.assertNotEqual(rows["ah"]["article_code"], rows["jumbo"]["article_code"])

        with patch.object(catalog_routes, "engine", self.engine):
            before = {pid: catalog_routes._catalog_row(pid) for pid in ("a", "b")}
        self.assertEqual({pid: row["linked_store_count"] for pid, row in before.items()},
                         {"a": 0, "b": 0})
        self.assertEqual({row["gpc_brick_code"] for row in before.values()}, {"10000025"})

        def project_almost_out():
            with self.engine.connect() as conn:
                article_rows = [
                    {"id": "ha-ah"}, {"id": "ha-jumbo"},
                ]
                groups = almost_out.load_groups(conn, household_id, article_rows, {})
                projections = [almost_out.load_group_projection(conn, household_id, group)
                               for group in groups]
                stock_count = conn.execute(
                    text("SELECT COALESCE(SUM(aantal), 0) FROM inventory")
                ).scalar_one()
            return groups, projections, stock_count

        # GS1 and consistent packaging already permit one readable product group;
        # a synonym confirmation never silently creates inventory transactions.
        groups_before, projections_before, stock_before = project_almost_out()
        self.assertEqual(len(groups_before), 1)
        self.assertEqual({item["id"] for item in groups_before[0]["members"]},
                         {"ha-ah", "ha-jumbo"})
        self.assertEqual(sum(float(row["quantity"]) for row in
                             projections_before[0]["inventory_rows"]), 2.0)
        self.assertEqual(float(stock_before), 3.0)

        with self.engine.begin() as conn:
            products = service.load_products(conn)
            proposals = service.suggest_pairs(products)
            self.assertEqual(len(proposals), 1)
            candidate = proposals[0]
            self.assertEqual({candidate["left"]["id"], candidate["right"]["id"]},
                             {"a", "b"})
            selection = {
                "left_product_id": candidate["left"]["id"],
                "right_product_id": candidate["right"]["id"],
                "fingerprint": candidate["fingerprint"],
            }
            self.assertEqual(service.confirm_pairs(conn, [selection], "chain-test-admin"),
                             {"linked": 1, "already_linked": 0})
        with self.engine.begin() as conn:
            self.assertEqual(service.confirmed_pairs(conn), {("a", "b")})
            self.assertEqual(service.confirm_pairs(conn, [selection], "chain-test-admin"),
                             {"linked": 0, "already_linked": 1})
        with patch.object(catalog_routes, "engine", self.engine):
            after = {pid: catalog_routes._catalog_row(pid) for pid in ("a", "b")}
        self.assertEqual({pid: row["linked_store_count"] for pid, row in after.items()},
                         {"a": 1, "b": 1})
        self.assertEqual({pid: row["primary_gtin"] for pid, row in after.items()},
                         {"a": "8719587325926", "b": "8718452513666"})

        groups_after, projections_after, stock_after = project_almost_out()
        self.assertEqual(len(groups_after), 1)
        self.assertEqual({row["household_article_id"] for row in
                          projections_after[0]["inventory_rows"]}, {"ha-ah", "ha-jumbo"})
        self.assertEqual(sum(float(row["quantity"]) for row in
                             projections_after[0]["inventory_rows"]), 2.0)
        self.assertEqual(float(stock_after), float(stock_before))
        with self.engine.connect() as conn:
            self.assertEqual(conn.execute(
                text("SELECT COUNT(*) FROM inventory_events")
            ).scalar_one(), 0)

        # Critical negative chain: an explicitly confirmed synonym is NOT an
        # automatic Bijna op equivalence without current compatible GPC evidence.
        with self.engine.begin() as conn:
            conn.execute(text("""
                DELETE FROM global_product_gpc_bricks WHERE global_product_id='b'
            """))
            conn.execute(text("""
                DELETE FROM product_group_memberships WHERE global_product_id='b'
            """))
        with self.engine.connect() as conn, patch.object(
            ed2, "_source_articles", side_effect=lambda _conn: iter(receipt_sources)
        ):
            downgraded_ed2 = ed2.list_all_external_articles(conn=conn)
        statuses = {row["retailer_code"]: row["link_status"]
                    for row in downgraded_ed2["items"]}
        self.assertEqual(statuses, {"ah": "linked", "jumbo": "unlinked"})
        groups_missing_type, _, stock_missing_type = project_almost_out()
        self.assertEqual(len(groups_missing_type), 2)
        self.assertEqual(float(stock_missing_type), 3.0)
        with self.engine.connect() as conn:
            self.assertEqual(service.confirmed_pairs(conn), {("a", "b")})
            self.assertEqual(conn.execute(
                text("SELECT COUNT(*) FROM inventory_events")
            ).scalar_one(), 0)

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
                self.assertEqual(self.client.get('/api/external-databases/article-synonyms/analysis/a/options').status_code, status)
                self.assertEqual(self.client.post('/api/external-databases/article-synonyms/link', json={'selections':[dict(left_product_id='a',right_product_id='b',fingerprint='0'*64)]}).status_code,status)
        with patch.object(routes, 'require_platform_permission_from_session', return_value=SimpleNamespace(is_frontteam=False,is_platform_superuser=False)):
            self.assertEqual(self.client.get('/api/external-databases/article-synonyms').status_code,403)

    def test_both_roles_authorized_via_canonical_permission(self):
        for superuser, frontteam in [(True,False),(False,True),(True,True)]:
            actor = SimpleNamespace(is_platform_superuser=superuser,is_frontteam=frontteam,user_id='actor')
            with patch.object(routes, 'require_platform_permission_from_session', return_value=actor) as check:
                self.assertIs(routes._actor('platform.external_products.link_existing'), actor)
                check.assert_called_once_with('platform.external_products.link_existing')

    def test_manual_selection_contract_does_not_trust_client_identity(self):
        body = routes.BulkSelection(selections=[dict(
            left_product_id='a', right_product_id='b',
            fingerprint='0' * 64, manual=True,
        )])
        self.assertTrue(body.selections[0].manual)
        for forged in [
            dict(left_product_id='a', right_product_id='b', fingerprint='0' * 64,
                 manual=True, product_name='forged'),
        ]:
            self.assertEqual(self.client.post('/api/external-databases/article-synonyms/link',
                                              json={'selections': [forged]}).status_code, 422)

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
        self.assertEqual(result['summary']['confirmed_pairs'], 1)
        self.assertEqual(result['summary']['insufficient_articles'], 0)
        self.assertEqual(result['summary']['no_candidate_articles'], 0)
        rows = {row['id']: row for row in result['items']}
        self.assertEqual(rows['a']['synonym_count'], 1)
        self.assertEqual(rows['a']['store'], 'Winkel onbekend')


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
