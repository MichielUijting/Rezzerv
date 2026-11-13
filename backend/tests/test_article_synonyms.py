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
from app.services.synonym_equivalence_review import review_pair
from app.services import synonym_classification_inheritance_service as inheritance
from app.services import synonym_classification_review_service as classification_review

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
    def test_quality_review_cross_brand_and_retailer_prefixes(self):
        left = product('a', 'AH Halfvolle melk', brick='milk')
        right = product('b', 'Jumbo Halfvolle melk', retailer_code='jumbo', brick='milk')
        result = review_pair(left, right)
        self.assertEqual(result['review_level'], 'strong')
        self.assertNotIn('link', result)
        options = service.product_link_options([left, right], set(), 'a')
        self.assertEqual(options[0]['review_level'], 'strong')
        self.assertTrue(options[0]['linkable'])

    def test_quality_review_flags_suspect_existing_links_without_unlinking(self):
        left = product('a', 'Zaanse halfvolle mayo')
        right = product('b', 'AH Houdbare halfvolle melk', retailer_code='jumbo')
        options = service.product_link_options([left, right], {('a', 'b')}, 'a')
        self.assertEqual(options[0]['status'], 'linked')
        self.assertEqual(options[0]['review_level'], 'check')
        self.assertIn('productsoorten', options[0]['review_reason'])
        self.assertFalse(options[0]['linkable'])

    def test_quality_review_blocks_false_confidence_on_variants(self):
        for left, right in (('Halfvolle melk', 'Volle melk'),
                            ('Magere kwark', 'Magere yoghurt'),
                            ('Noten', 'Kruidnoten'),
                            ('Roomboter ongezouten', 'Roomboter gezouten')):
            with self.subTest(left=left, right=right):
                self.assertEqual(
                    review_pair(product('a', left), product('b', right))['review_level'],
                    'check'
                )

    def test_quality_review_package_difference_needs_review(self):
        left = product('a', 'Burrata')
        right = product('b', 'Burrata')
        left['size_value'], left['size_unit'] = '125', 'g'
        right['size_value'], right['size_unit'] = '150', 'g'
        self.assertEqual(review_pair(left, right)['review_level'], 'check')

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

    def test_conflict_details_distinguish_gtin_codes_and_gpc(self):
        left = product('a', 'Aardappelschijfjes', gtin='08719587325926', brick='milk')
        same_gtin = product('b', 'Aardappelschijfjes', gtin='08719587325926', brick='milk')
        same_code = product('c', 'Aardappelen', gtin='08718452513666', brick='milk')
        same_code['article_codes'] = ['STORE-99']
        left['article_codes'] = ['STORE-99']
        different_gpc = product('d', 'Aardappelschijfjes met spek',
                                gtin='08712345678906', brick='fruit')
        records = {r['id']: r for r in service.product_link_options(
            [left, same_gtin, same_code, different_gpc], set(), 'a')}
        self.assertEqual(records['b']['conflict_type'], 'same_gtin')
        self.assertIn('08719587325926', records['b']['conflict_detail'])
        self.assertEqual(records['b']['resolution_route'], '/catalogus/b')
        self.assertEqual(records['c']['conflict_type'], 'shared_article_code')
        self.assertIn('STORE-99', records['c']['conflict_detail'])
        self.assertEqual(records['d']['conflict_type'], 'gpc_mismatch')
        self.assertEqual(records['d']['status_label'], 'Classificatie kiezen')
        self.assertIn('milk', records['d']['conflict_detail'])
        self.assertIn('fruit', records['d']['conflict_detail'])
        self.assertEqual(records['d']['resolution_route'], '/catalogus/gpc-classificeren')
        for item in records.values():
            self.assertFalse(item['linkable'])

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


    def test_article_index_exposes_real_catalog_creation_date(self):
        from unittest.mock import MagicMock

        connection = MagicMock()
        connection.execute.return_value.mappings.return_value = [
            {'id': 'a', 'created_at': '2026-02-03 10:00:00'},
        ]
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
            introspection.return_value.get_columns.return_value = [{'name': 'created_at'}]
            response = routes.synonym_analysis()
        self.assertEqual(response['items'][0]['added_on'], '2026-02-03')
        self.assertEqual(connection.execute.call_count, 1)



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
            conn.exec_driver_sql("""
                CREATE TABLE global_product_gpc_bricks (
                    global_product_id TEXT PRIMARY KEY, brick_code TEXT,
                    assignment_source TEXT NOT NULL DEFAULT 'manual_catalog_detail',
                    confidence FLOAT NOT NULL DEFAULT 1.0,
                    migrated_from TEXT, updated_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
                )
            """)
            conn.exec_driver_sql("""
                CREATE TABLE cbs_ecoicop_categories (
                    cbs_code TEXT, reference_version TEXT, parent_code TEXT,
                    name_nl TEXT NOT NULL,
                    PRIMARY KEY (cbs_code, reference_version)
                )
            """)
            conn.exec_driver_sql("""
                INSERT INTO cbs_ecoicop_categories VALUES
                    ('011420','CBS-ECOICOPv2-2026',NULL,'Melkproducten'),
                    ('011410','CBS-ECOICOPv2-2026',NULL,'Andere zuivel')
            """)
            conn.exec_driver_sql("""
                CREATE TABLE global_product_cbs_classifications (
                    global_product_id TEXT PRIMARY KEY,
                    cbs_code TEXT NOT NULL, reference_version TEXT NOT NULL,
                    version INTEGER NOT NULL, is_active BOOLEAN NOT NULL DEFAULT TRUE,
                    confirmed_by TEXT NOT NULL,
                    confirmation_source TEXT NOT NULL,
                    confirmed_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
                )
            """)
            conn.exec_driver_sql("""
                CREATE TABLE global_product_cbs_history (
                    id TEXT PRIMARY KEY, global_product_id TEXT NOT NULL,
                    cbs_code TEXT, reference_version TEXT, version INTEGER,
                    action TEXT NOT NULL, confirmed_by TEXT NOT NULL,
                    confirmation_source TEXT NOT NULL,
                    confirmed_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
                )
            """)
            conn.exec_driver_sql('CREATE TABLE external_article_product_links(global_product_id TEXT, retailer_code TEXT, external_article_code TEXT, status TEXT)')
            conn.exec_driver_sql('CREATE TABLE external_product_candidates(context_key TEXT, retailer_code TEXT, global_product_id TEXT, is_user_confirmed BOOLEAN, status TEXT, candidate_status TEXT)')
            # Install the real PostgreSQL maintenance gate before the new catalog table.
            maintenance = migration_module('20261021_01_server_maintenance')
            module = migration_module('20261026_01_article_synonyms')
            sync_audit = migration_module('20261104_01_article_classification_sync_audit')
            with Operations.context(MigrationContext.configure(conn)):
                maintenance.upgrade()
                module.upgrade()
                sync_audit.upgrade()
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

    def _set_cbs(self, conn, product_id, code='011420'):
        conn.execute(text("""
            INSERT INTO global_product_cbs_classifications
                (global_product_id,cbs_code,reference_version,version,is_active,
                 confirmed_by,confirmation_source)
            VALUES (:id,:code,'CBS-ECOICOPv2-2026',1,TRUE,'manual','explicit_manual_confirmation')
        """), {'id': product_id, 'code': code})

    def _check_inheritance_irrespective_of_retailer(self, retailer):
        with self.engine.begin() as conn:
            if retailer is None:
                conn.execute(text("""
                    UPDATE external_article_product_links
                       SET status='inactive' WHERE global_product_id='b'
                """))
            else:
                conn.execute(text("""
                    UPDATE external_article_product_links
                       SET retailer_code=:retailer WHERE global_product_id='b'
                """), {'retailer': retailer})
            conn.execute(text("""
                INSERT INTO global_product_gpc_bricks(global_product_id,brick_code)
                VALUES ('a','10000025')
            """))
            self._set_cbs(conn, 'a')
            # The component is fed an already confirmed central synonym pair;
            # shop provenance must never enter classification inheritance.
            report = inheritance.propagate_confirmed_classifications(
                conn, {('a', 'b')}, {'a', 'b'}, 'actor',
            )
            self.assertEqual(report['gpc_inherited'], 1)
            self.assertEqual(report['cbs_inherited'], 1)
            self.assertEqual(report['conflicts'], [])
            self.assertEqual(conn.execute(text("""
                SELECT brick_code FROM global_product_gpc_bricks
                 WHERE global_product_id='b'
            """)).scalar_one(), '10000025')
            self.assertEqual(conn.execute(text("""
                SELECT cbs_code FROM global_product_cbs_classifications
                 WHERE global_product_id='b'
            """)).scalar_one(), '011420')
            self.assertEqual(conn.execute(text("""
                SELECT COUNT(*) FROM global_product_cbs_history
                 WHERE global_product_id='b'
            """)).scalar_one(), 1)

    def test_inheritance_with_unknown_retailer(self):
        self._check_inheritance_irrespective_of_retailer(None)

    def test_inheritance_with_same_retailer(self):
        self._check_inheritance_irrespective_of_retailer('ah')

    def test_inheritance_with_different_retailers(self):
        self._check_inheritance_irrespective_of_retailer('jumbo')

    def test_confirmed_synonyms_inherit_both_and_retry_is_idempotent(self):
        with self.engine.begin() as conn:
            conn.execute(text("""
                INSERT INTO global_product_gpc_bricks(global_product_id,brick_code)
                VALUES ('a','10000025')
            """))
            self._set_cbs(conn, 'a')
            selection = self.selection(conn)
            result = service.confirm_pairs(conn, [selection], 'actor')
            self.assertEqual(result['linked'], 1)
            self.assertEqual(result['classification_inheritance']['gpc_inherited'], 1)
            self.assertEqual(result['classification_inheritance']['cbs_inherited'], 1)
        with self.engine.begin() as conn:
            self.assertEqual(conn.execute(text(
                "SELECT brick_code FROM global_product_gpc_bricks WHERE global_product_id='b'"
            )).scalar_one(), '10000025')
            row = conn.execute(text("""
                SELECT cbs_code, confirmation_source FROM global_product_cbs_classifications
                WHERE global_product_id='b'
            """)).one()
            self.assertEqual(tuple(row), ('011420', 'synonym:a'))
            self.assertEqual(conn.execute(text("""
                SELECT COUNT(*) FROM global_product_cbs_history
                WHERE global_product_id='b'
            """)).scalar_one(), 1)
            audit = conn.execute(text("""
                SELECT source_product_id, target_product_id, classification_system,
                       classification_code, reference_version, decision_version, status
                FROM article_classification_sync_events ORDER BY classification_system
            """)).all()
            self.assertEqual(len(audit), 2)
            self.assertEqual({(row[0],row[1],row[2],row[3],row[6]) for row in audit},
                             {('a','b','GPC','10000025','processed'),
                              ('a','b','CBS','011420','processed')})
            self.assertEqual(next(row[5] for row in audit if row[2]=='CBS'), 1)
            again = service.confirm_pairs(conn, [selection], 'actor')
            self.assertEqual(again['already_linked'], 1)
            self.assertNotIn('classification_inheritance', again)
            self.assertEqual(conn.execute(text(
                "SELECT COUNT(*) FROM article_classification_sync_events"
            )).scalar_one(), 2)
            self.assertEqual(conn.execute(text("""
                SELECT COUNT(*) FROM global_product_cbs_history
                WHERE global_product_id='b'
            """)).scalar_one(), 1)

    def test_sync_exception_audit_and_explicit_retry_after_reference_validation(self):
        from app.services.article_classification_sync_monitor import (
            list_sync_exceptions, retry_sync_exception,
        )
        with self.engine.begin() as conn:
            self._set_cbs(conn, 'a', '099999')
            selected = self.selection(conn)
            result = service.confirm_pairs(conn, [selected], 'actor')
            self.assertEqual(result['classification_inheritance']['cbs_inherited'], 0)
            exceptions = list_sync_exceptions(conn)
            self.assertEqual(exceptions['total'], 1)
            entry = exceptions['items'][0]
            self.assertEqual(entry['status'], 'review_required')
            self.assertEqual(entry['source_product_id'], 'a')
            self.assertEqual(entry['target_product_id'], 'b')
            self.assertEqual(entry['classification_system'], 'CBS')
            self.assertEqual(entry['classification_code'], '099999')
            self.assertEqual(entry['decision_version'], 1)
            with self.assertRaises(HTTPException) as stale:
                with conn.begin_nested():
                    retry_sync_exception(conn, event_id=entry['id'],
                                         expected_decision_version=0,
                                         expected_target_version=0, expected_target_code='', actor_id='actor')
            self.assertEqual(stale.exception.status_code, 409)
            # A rejected transaction rolls back even its pending audit marker.
            with self.assertRaises(HTTPException) as unavailable:
                with conn.begin_nested():
                    retry_sync_exception(conn, event_id=entry['id'],
                                         expected_decision_version=1,
                                         expected_target_version=0, expected_target_code='', actor_id='actor')
            self.assertEqual(unavailable.exception.status_code, 409)
            self.assertEqual(conn.execute(text("""
                SELECT COUNT(*) FROM global_product_cbs_classifications
                WHERE global_product_id='b'
            """)).scalar_one(), 0)
            # A verified official leaf may later be added through a separate
            # official authority operation. Only an explicit retry then writes.
            conn.execute(text("""
                INSERT INTO cbs_ecoicop_categories VALUES
                    ('099999','CBS-ECOICOPv2-2026',NULL,'Speciale categorie')
            """))
            retry = retry_sync_exception(conn, event_id=entry['id'],
                                         expected_decision_version=1,
                                         expected_target_version=0, expected_target_code='', actor_id='actor')
            self.assertEqual(retry['cbs_inherited'], 1)
            again = retry_sync_exception(conn, event_id=entry['id'],
                                         expected_decision_version=1,
                                         expected_target_version=0, expected_target_code='', actor_id='actor')
            self.assertEqual(again['cbs_inherited'], 0)
            self.assertEqual(list_sync_exceptions(conn)['total'], 0)
            self.assertEqual(conn.execute(text("""
                SELECT COUNT(*) FROM article_classification_sync_events
                WHERE status='processed'
            """)).scalar_one(), 2)
            self.assertEqual(conn.execute(text("""
                SELECT COUNT(*) FROM global_product_cbs_history
                WHERE global_product_id='b'
            """)).scalar_one(), 1)

    def test_failed_retry_logs_only_after_rollback_without_mutating_catalog(self):
        from app.services.article_classification_sync_monitor import (
            record_sync_event, list_sync_exceptions,
        )
        with self.engine.begin() as conn:
            record_sync_event(
                conn, source_id='a', target_id='b', system='CBS',
                code='011420', reference='CBS-ECOICOPv2-2026',
                decision_version=1, status='review_required',
                reason='Officiële bron tijdelijk niet beschikbaar', actor_id='actor',
            )
            event_id = conn.execute(text(
                "SELECT id FROM article_classification_sync_events"
            )).scalar_one()
        app = FastAPI()
        app.include_router(routes.router)
        client = TestClient(app)
        actor = SimpleNamespace(is_platform_superuser=True, is_frontteam=False, user_id='actor')
        with patch.object(routes, 'engine', self.engine), \
                patch.object(routes, 'require_platform_permission_from_session',
                             return_value=actor), \
                patch.object(routes, 'retry_sync_exception',
                             side_effect=RuntimeError('injected failed transaction')):
            response = client.post(
                '/api/external-databases/article-synonyms/sync-exceptions/retry',
                json={'event_id': event_id, 'expected_decision_version': 1,
                      'expected_target_version': 0, 'expected_target_code': ''},
            )
        self.assertEqual(response.status_code, 503)
        with self.engine.connect() as conn:
            monitor = list_sync_exceptions(conn)
            self.assertEqual(monitor['total'], 1)
            self.assertEqual(monitor['items'][0]['status'], 'failed')
            self.assertEqual(conn.execute(text(
                "SELECT COUNT(*) FROM global_product_cbs_classifications"
            )).scalar_one(), 0)

    def test_gpc_retry_requires_separate_official_write_permission(self):
        from app.services.article_classification_sync_monitor import record_sync_event
        with self.engine.begin() as conn:
            record_sync_event(
                conn, source_id='a', target_id='b', system='GPC',
                code='10000025', decision_version=0, status='review_required',
                reason='Uitzondering voor expliciete test', actor_id='actor',
            )
            event_id = conn.execute(text(
                "SELECT id FROM article_classification_sync_events"
            )).scalar_one()
        app = FastAPI()
        app.include_router(routes.router)
        client = TestClient(app)
        actor = SimpleNamespace(is_platform_superuser=True, is_frontteam=False, user_id='actor')
        def authorize(permission):
            if permission == 'platform.gpc.update':
                raise HTTPException(403, 'GPC-schrijfrecht ontbreekt.')
            return actor
        with patch.object(routes, 'engine', self.engine), \
                patch.object(routes, 'require_platform_permission_from_session',
                             side_effect=authorize):
            response = client.post(
                '/api/external-databases/article-synonyms/sync-exceptions/retry',
                json={'event_id': event_id, 'expected_decision_version': 0,
                      'expected_target_version': 0, 'expected_target_code': ''},
            )
        self.assertEqual(response.status_code, 403)
        with self.engine.connect() as conn:
            self.assertEqual(conn.execute(text(
                "SELECT COUNT(*) FROM article_classification_sync_events"
            )).scalar_one(), 1)

    def test_existing_confirmed_gpc_conflict_is_logged_once_without_overwrite(self):
        from app.services.article_classification_sync_monitor import list_sync_exceptions
        with self.engine.begin() as conn:
            conn.execute(text("""
                INSERT INTO global_product_gpc_bricks(global_product_id, brick_code)
                VALUES ('a','10000025'),('b','10000026')
            """))
            for _ in range(2):
                report = inheritance.propagate_confirmed_classifications(
                    conn, {('a','b')}, {'a','b'}, 'actor'
                )
                self.assertEqual([x['system'] for x in report['conflicts']], ['GPC'])
            self.assertEqual(list_sync_exceptions(conn)['total'], 1)
            self.assertEqual(conn.execute(text("""
                SELECT brick_code FROM global_product_gpc_bricks WHERE global_product_id='b'
            """)).scalar_one(), '10000026')

    def test_audit_rolls_back_with_rejected_synonym_transaction(self):
        from app.services import article_classification_sync_monitor as monitor
        with self.assertRaisesRegex(RuntimeError, 'audit interrupted'):
            with self.engine.begin() as conn:
                conn.execute(text("""
                    INSERT INTO global_product_gpc_bricks(global_product_id, brick_code)
                    VALUES ('a','10000025')
                """))
                selected = self.selection(conn)
                with patch.object(inheritance, 'record_sync_event',
                                  side_effect=RuntimeError('audit interrupted')):
                    service.confirm_pairs(conn, [selected], 'actor')
        with self.engine.connect() as conn:
            self.assertEqual(conn.execute(text(
                "SELECT COUNT(*) FROM article_synonym_links"
            )).scalar_one(), 0)
            self.assertEqual(conn.execute(text(
                "SELECT COUNT(*) FROM article_classification_sync_events"
            )).scalar_one(), 0)
            self.assertEqual(conn.execute(text(
                "SELECT COUNT(*) FROM global_product_gpc_bricks"
            )).scalar_one(), 0)

    def test_mandatory_three_articles_a_b_c_classification_chain(self):
        """Every-PR regression: A classified, B empty, C conflicts in both systems.

        All writes happen in an isolated PostgreSQL schema created by setUp.
        Never mutate a user household, real catalog, receipt or inventory.
        """
        with self.engine.begin() as conn:
            conn.exec_driver_sql("""
                CREATE TABLE gpc_product_groups (
                    gpc_brick_code TEXT PRIMARY KEY,
                    language_code TEXT NOT NULL, active BOOLEAN NOT NULL,
                    gpc_brick_name TEXT NOT NULL
                )
            """)
            conn.exec_driver_sql("""
                INSERT INTO gpc_product_groups VALUES
                    ('10000025','nl',TRUE,'Halfvolle melk'),
                    ('10000026','nl',TRUE,'Andere melk')
            """)
            # C has a distinct *valid* product barcode, not a name-based identity.
            conn.execute(text("""
                UPDATE global_products SET primary_gtin='8719587325933' WHERE id='c'
            """))
            conn.execute(text("""
                INSERT INTO global_product_gpc_bricks(global_product_id,brick_code)
                VALUES ('a','10000025'),('c','10000026')
            """))
            self._set_cbs(conn, 'a', '011420')
            self._set_cbs(conn, 'c', '011410')
            products = {item['id']: item for item in service.load_products(conn)}
            self.assertEqual(set(products), {'a','b','c'})
            self.assertEqual(service.confirmed_pairs(conn), set())

            # A -> B: both official classifications inherited atomically.
            ab = dict(left_product_id='a', right_product_id='b',
                      fingerprint=service._fingerprint(products['a'],products['b']))
            first = service.confirm_pairs(conn, [ab], 'every-pr-test')
            self.assertEqual(first['linked'], 1)
            self.assertEqual(first['classification_inheritance']['gpc_inherited'], 1)
            self.assertEqual(first['classification_inheritance']['cbs_inherited'], 1)
            self.assertEqual(dict(conn.execute(text("""
                SELECT global_product_id, brick_code FROM global_product_gpc_bricks
            """)).all()), {'a':'10000025','b':'10000025','c':'10000026'})
            self.assertEqual(dict(conn.execute(text("""
                SELECT global_product_id, cbs_code FROM global_product_cbs_classifications
            """)).all()), {'a':'011420','b':'011420','c':'011410'})

            # A / C: both values must be shown; no silent overwrite.
            products = {item['id']: item for item in service.load_products(conn)}
            ac = dict(left_product_id='a', right_product_id='c',
                      fingerprint=service._fingerprint(products['a'],products['c']),
                      manual=True)
            review = classification_review.review_pairs(conn, [ac], products)[0]
            self.assertEqual({clash['system'] for clash in review['clashes']}, {'GPC','CBS'})
            codes = {clash['system']:(clash['left']['code'],clash['right']['code'])
                     for clash in review['clashes']}
            self.assertEqual(codes['GPC'], ('10000025','10000026'))
            self.assertEqual(codes['CBS'], ('011420','011410'))
            with self.assertRaises(HTTPException) as missing_choice:
                with conn.begin_nested():
                    service.confirm_pairs(conn, [ac], 'every-pr-test')
            self.assertEqual(missing_choice.exception.status_code, 409)
            self.assertEqual(service.confirmed_pairs(conn), {('a','b')})

            # Explicit, separately captured GPC and CBS choice from A preserves
            # the already-confirmed A/B component; C is the only changed target.
            decision = dict(left_product_id='a', right_product_id='c',
                            snapshot=review['snapshot'],
                            gpc_source_id='a', cbs_source_id='a')
            resolved = service.confirm_pairs(conn,[ac],'every-pr-test',decisions=[decision])
            self.assertEqual(resolved['linked'],1)
            self.assertEqual(resolved['classification_inheritance']['gpc_resolved'],1)
            self.assertEqual(resolved['classification_inheritance']['cbs_resolved'],1)
            self.assertEqual(dict(conn.execute(text("""
                SELECT global_product_id, brick_code FROM global_product_gpc_bricks
            """)).all()), {'a':'10000025','b':'10000025','c':'10000025'})
            self.assertEqual(dict(conn.execute(text("""
                SELECT global_product_id, cbs_code FROM global_product_cbs_classifications
            """)).all()), {'a':'011420','b':'011420','c':'011420'})
            self.assertEqual(service.confirmed_pairs(conn), {('a','b'),('a','c')})

            # Retry never creates extra events, classifications or links.
            audit_before = conn.execute(text(
                "SELECT COUNT(*) FROM article_classification_sync_events"
            )).scalar_one()
            retry = service.confirm_pairs(conn,[ac],'every-pr-test',decisions=[])
            self.assertEqual(retry['already_linked'],1)
            self.assertEqual(conn.execute(text(
                "SELECT COUNT(*) FROM article_classification_sync_events"
            )).scalar_one(), audit_before)
            self.assertEqual(conn.execute(text(
                "SELECT COUNT(*) FROM global_product_cbs_history"
            )).scalar_one(), 2)

    def test_inheritance_is_bidirectional_and_systems_independent(self):
        with self.engine.begin() as conn:
            self._set_cbs(conn, 'b')
            conn.execute(text("""
                INSERT INTO global_product_gpc_bricks(global_product_id,brick_code)
                VALUES ('b','10000025')
            """))
            selection = self.selection(conn)
            result = service.confirm_pairs(conn, [selection], 'actor')
            self.assertEqual(result['classification_inheritance']['gpc_inherited'], 1)
            self.assertEqual(result['classification_inheritance']['cbs_inherited'], 1)
            self.assertEqual(conn.execute(text("""
                SELECT confirmation_source FROM global_product_cbs_classifications
                WHERE global_product_id='a'
            """)).scalar_one(), 'synonym:b')

    def test_conflicting_cbs_values_require_user_choice_before_linking(self):
        with self.engine.begin() as conn:
            selection = self.selection(conn)
            self._set_cbs(conn, 'a', '011420')
            self._set_cbs(conn, 'b', '011410')
            with self.assertRaises(HTTPException) as rejection:
                service.confirm_pairs(conn, [selection], 'actor')
            self.assertEqual(rejection.exception.status_code, 409)
            self.assertEqual(service.confirmed_pairs(conn), set())
            self.assertEqual(conn.execute(text("""
                SELECT COUNT(*) FROM global_product_cbs_history
            """)).scalar_one(), 0)
            self.assertEqual(set(conn.execute(text("""
                SELECT cbs_code FROM global_product_cbs_classifications
            """)).scalars()), {'011410', '011420'})

    def test_reviewer_can_choose_each_independent_classification(self):
        with self.engine.begin() as conn:
            # Only this test needs a small official GPC label authority; other
            # chain tests create the production-shaped GPC table themselves.
            conn.exec_driver_sql("""
                CREATE TABLE gpc_product_groups (
                    gpc_brick_code TEXT PRIMARY KEY,
                    language_code TEXT NOT NULL,
                    active BOOLEAN NOT NULL,
                    gpc_brick_name TEXT NOT NULL
                )
            """)
            conn.exec_driver_sql("""
                INSERT INTO gpc_product_groups VALUES
                    ('10000025','nl',TRUE,'Melk'),
                    ('10000026','nl',TRUE,'Andere melk')
            """)
            conn.execute(text("""
                INSERT INTO global_product_gpc_bricks(global_product_id,brick_code)
                VALUES ('a','10000025'),('b','10000026')
            """))
            self._set_cbs(conn, 'a', '011420')
            self._set_cbs(conn, 'b', '011410')
            products = {p['id']: p for p in service.load_products(conn)}
            choice = dict(left_product_id='a', right_product_id='b',
                          fingerprint=service._fingerprint(products['a'], products['b']),
                          manual=True)
            review = classification_review.review_pairs(conn, [choice], products)[0]
            self.assertEqual([c['system'] for c in review['clashes']], ['GPC', 'CBS'])
            self.assertEqual(review['clashes'][0]['left']['code'], '10000025')
            self.assertEqual(review['clashes'][0]['right']['code'], '10000026')
            self.assertEqual(review['clashes'][1]['left']['label'], 'Melkproducten')
            decision = dict(left_product_id='a', right_product_id='b',
                            snapshot=review['snapshot'], gpc_source_id='a',
                            cbs_source_id='b')
            result = service.confirm_pairs(conn, [choice], 'actor', decisions=[decision])
            self.assertEqual(result['linked'], 1)
            self.assertEqual(result['classification_inheritance']['gpc_resolved'], 1)
            self.assertEqual(result['classification_inheritance']['cbs_resolved'], 1)
            self.assertEqual(dict(conn.execute(text("""
                SELECT global_product_id, brick_code FROM global_product_gpc_bricks
            """)).all()), {'a': '10000025', 'b': '10000025'})
            self.assertEqual(dict(conn.execute(text("""
                SELECT global_product_id, cbs_code FROM global_product_cbs_classifications
            """)).all()), {'a': '011410', 'b': '011410'})
            self.assertEqual(conn.execute(text("""
                SELECT confirmation_source FROM global_product_cbs_history
                WHERE global_product_id='a'
            """)).scalar_one(), 'synonym_review:b')
            self.assertEqual(conn.execute(text("""
                SELECT assignment_source FROM global_product_gpc_bricks
                WHERE global_product_id='b'
            """)).scalar_one(), 'synonym_review')

    def test_stale_classification_choice_is_rejected_without_writes(self):
        with self.engine.begin() as conn:
            self._set_cbs(conn, 'a', '011420')
            self._set_cbs(conn, 'b', '011410')
            choice = self.selection(conn)
            products = {p['id']: p for p in service.load_products(conn)}
            review = classification_review.review_pairs(conn, [choice], products)[0]
            decision = dict(left_product_id='a', right_product_id='b',
                            snapshot=review['snapshot'], cbs_source_id='a')
            conn.execute(text("""
                UPDATE global_product_cbs_classifications
                SET version=version+1 WHERE global_product_id='a'
            """))
            with self.assertRaises(HTTPException) as rejected:
                service.confirm_pairs(conn, [choice], 'actor', decisions=[decision])
            self.assertEqual(rejected.exception.status_code, 409)
            self.assertEqual(service.confirmed_pairs(conn), set())

    def test_shared_gtin_cannot_be_bypassed_by_a_classification_choice(self):
        with self.engine.begin() as conn:
            conn.execute(text("""
                UPDATE global_products SET primary_gtin='8719587325926' WHERE id='b'
            """))
            products = {p['id']: p for p in service.load_products(conn)}
            forged = dict(left_product_id='a', right_product_id='b',
                          fingerprint=service._fingerprint(products['a'], products['b']),
                          manual=True)
            with self.assertRaises(HTTPException) as rejected:
                service.confirm_pairs(conn, [forged], 'actor')
            self.assertEqual(rejected.exception.status_code, 409)
            self.assertEqual(service.confirmed_pairs(conn), set())

    def test_overlapping_precedence_choices_are_rejected_atomically(self):
        conflicting_reviews = [
            dict(left_id='a', right_id='b', snapshot='a' * 64,
                 clashes=[dict(system='GPC')]),
            dict(left_id='a', right_id='c', snapshot='b' * 64,
                 clashes=[dict(system='GPC')]),
        ]
        selections = [
            dict(left_product_id='a', right_product_id='b',
                 snapshot='a' * 64, gpc_source_id='a'),
            dict(left_product_id='a', right_product_id='c',
                 snapshot='b' * 64, gpc_source_id='a'),
        ]
        with self.engine.begin() as conn:
            with self.assertRaises(HTTPException) as rejected:
                classification_review.apply_choices(conn, conflicting_reviews, selections, 'actor')
            self.assertEqual(rejected.exception.status_code, 409)
            self.assertEqual(service.confirmed_pairs(conn), set())

    def test_existing_gpc_conflict_blocks_only_gpc_not_cbs(self):
        with self.engine.begin() as conn:
            conn.execute(text("""
                INSERT INTO global_product_gpc_bricks(global_product_id,brick_code)
                VALUES ('a','10000025'),('b','10000026')
            """))
            self._set_cbs(conn, 'a')
            # A pre-existing confirmed relationship may acquire a later GPC
            # conflict. Do not override either Brick or suppress safe CBS fill.
            report = inheritance.propagate_confirmed_classifications(
                conn, {('a', 'b')}, {'a', 'b'}, 'actor',
            )
            self.assertEqual(report['gpc_inherited'], 0)
            self.assertEqual(report['cbs_inherited'], 1)
            self.assertEqual([item['system'] for item in report['conflicts']], ['GPC'])
            self.assertEqual(dict(conn.execute(text("""
                SELECT global_product_id, brick_code FROM global_product_gpc_bricks
            """)).all()), {'a': '10000025', 'b': '10000026'})
            self.assertEqual(conn.execute(text("""
                SELECT cbs_code FROM global_product_cbs_classifications
                 WHERE global_product_id='b'
            """)).scalar_one(), '011420')

    def test_missing_gpc_does_not_prevent_independent_cbs_inheritance(self):
        with self.engine.begin() as conn:
            self._set_cbs(conn, 'a')
            pair = self.selection(conn)
            result = service.confirm_pairs(conn, [pair], 'actor')
            self.assertEqual(result['classification_inheritance']['gpc_inherited'], 0)
            self.assertEqual(result['classification_inheritance']['cbs_inherited'], 1)
            self.assertEqual(conn.execute(text(
                "SELECT COUNT(*) FROM global_product_gpc_bricks"
            )).scalar_one(), 0)

    def test_three_article_synonym_group_inherits_consistently(self):
        with self.engine.begin() as conn:
            conn.execute(text("""
                INSERT INTO external_article_product_links VALUES
                    ('c','lidl','LIDL123','confirmed')
            """))
            conn.execute(text("""
                INSERT INTO global_product_gpc_bricks(global_product_id,brick_code)
                VALUES ('a','10000025')
            """))
            self._set_cbs(conn, 'a')
            first = self.selection(conn)
            service.confirm_pairs(conn, [first], 'actor')
            candidates = service.suggest_pairs(service.load_products(conn),
                                               service.confirmed_pairs(conn))
            next_pair = next(p for p in candidates
                             if 'c' in (p['left']['id'], p['right']['id']))
            selection = dict(left_product_id=next_pair['left']['id'],
                             right_product_id=next_pair['right']['id'],
                             fingerprint=next_pair['fingerprint'])
            service.confirm_pairs(conn, [selection], 'actor')
            self.assertEqual(conn.execute(text(
                "SELECT COUNT(*) FROM global_product_gpc_bricks WHERE brick_code='10000025'"
            )).scalar_one(), 3)
            self.assertEqual(conn.execute(text("""
                SELECT COUNT(*) FROM global_product_cbs_classifications
                WHERE cbs_code='011420' AND is_active=TRUE
            """)).scalar_one(), 3)

    def test_failure_rolls_back_link_and_both_classifications(self):
        with self.assertRaisesRegex(RuntimeError, 'simulated'):
            with self.engine.begin() as conn:
                conn.execute(text("""
                    INSERT INTO global_product_gpc_bricks(global_product_id,brick_code)
                    VALUES ('a','10000025')
                """))
                self._set_cbs(conn, 'a')
                first = self.selection(conn)
                with patch.object(inheritance, 'propagate_confirmed_classifications',
                                  side_effect=RuntimeError('simulated')):
                    service.confirm_pairs(conn, [first], 'actor')
        with self.engine.connect() as conn:
            self.assertEqual(service.confirmed_pairs(conn), set())
            self.assertEqual(conn.execute(text(
                "SELECT COUNT(*) FROM global_product_cbs_classifications"
            )).scalar_one(), 0)

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

    def test_transitive_conflict_rejects_second_link_without_erasing_first(self):
        # A and C contradict each other in milk fat; intermediary B is unknown.
        # Direct edges A-B and B-C look individually safe.
        with self.engine.begin() as conn:
            conn.execute(text("UPDATE global_products SET name='Melk' WHERE id='b'"))
            conn.execute(text("""
                UPDATE global_products SET name='Volle melk',
                       primary_gtin='8719587325933' WHERE id='c'
            """))
            products = {p['id']: p for p in service.load_products(conn)}
            self.assertEqual(set(products), {'a', 'b', 'c'})
            first = dict(left_product_id='a', right_product_id='b',
                         fingerprint=service._fingerprint(products['a'], products['b']),
                         manual=True)
            self.assertEqual(service.confirm_pairs(conn, [first], 'actor')['linked'], 1)
            products = {p['id']: p for p in service.load_products(conn)}
            second = dict(left_product_id='b', right_product_id='c',
                          fingerprint=service._fingerprint(products['b'], products['c']),
                          manual=True)
            with self.assertRaises(HTTPException) as refused:
                with conn.begin_nested():
                    service.confirm_pairs(conn, [second], 'actor')
            self.assertEqual(refused.exception.status_code, 409)
            self.assertIn('Halfvolle melk', str(refused.exception.detail))
            self.assertIn('Volle melk', str(refused.exception.detail))
            self.assertEqual(service.confirmed_pairs(conn), {('a', 'b')})
            self.assertEqual(conn.execute(text("""
                SELECT COUNT(*) FROM article_synonym_links
            """)).scalar_one(), 1)

    def test_transitive_bulk_conflict_is_atomic_in_postgresql(self):
        with self.engine.begin() as conn:
            conn.execute(text("UPDATE global_products SET name='Melk' WHERE id='b'"))
            conn.execute(text("""
                UPDATE global_products SET name='Volle melk',
                       primary_gtin='8719587325933' WHERE id='c'
            """))
            products = {p['id']: p for p in service.load_products(conn)}
            bulk = [
                dict(left_product_id=left, right_product_id=right,
                     fingerprint=service._fingerprint(products[left], products[right]),
                     manual=True)
                for left, right in [('a', 'b'), ('b', 'c')]
            ]
            with self.assertRaises(HTTPException) as refused:
                with conn.begin_nested():
                    service.confirm_pairs(conn, bulk, 'actor')
            self.assertEqual(refused.exception.status_code, 409)
            self.assertEqual(service.confirmed_pairs(conn), set())

    def test_unlink_removes_only_selected_direct_synonym_and_keeps_products(self):
        with self.engine.begin() as conn:
            selection = self.selection(conn)
            service.confirm_pairs(conn, [selection], 'actor')
            pairs = service.confirmed_pairs(conn)
            self.assertEqual(len(pairs), 1)
            before_products = conn.execute(text("SELECT COUNT(*) FROM global_products")).scalar_one()
            options = service.product_link_options(service.load_products(conn), pairs, 'a')
            linked = next(row for row in options if row['status'] == 'linked')
            self.assertTrue(linked['fingerprint'])
            deleted = service.unlink_pairs(conn, [{
                'left_product_id': 'a', 'right_product_id': linked['id'],
                'fingerprint': linked['fingerprint'],
            }])
            self.assertEqual(deleted, {'unlinked': 1})
            self.assertEqual(service.confirmed_pairs(conn), set())
            self.assertEqual(conn.execute(text("SELECT COUNT(*) FROM global_products")).scalar_one(), before_products)

    def test_unlink_rejects_missing_or_stale_pair_without_partial_write(self):
        with self.engine.begin() as conn:
            first = self.selection(conn)
            service.confirm_pairs(conn, [first], 'actor')
            existing = service.confirmed_pairs(conn)
            for payload in [
                [{'left_product_id': 'a', 'right_product_id': 'b',
                  'fingerprint': '0' * 64}],
                [{'left_product_id': 'a', 'right_product_id': 'a',
                  'fingerprint': '0' * 64}],
                [{'left_product_id': 'a', 'right_product_id': 'c',
                  'fingerprint': '0' * 64}],
            ]:
                with self.assertRaises(HTTPException):
                    service.unlink_pairs(conn, payload)
                self.assertEqual(service.confirmed_pairs(conn), existing)

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
            # AH has an explicitly confirmed CBS code; Jumbo must inherit
            # only after the independent central synonym confirmation.
            self._set_cbs(conn, "a", "011420")
            conn.execute(text("""
                INSERT INTO product_inventory_groups
                  (inventory_group_key, gpc_brick_code, source, active, display_name)
                VALUES ('gpc:10000025', '10000025', 'gs1_gpc_official', 1, 'Halfvolle melk')
            """))
            for pid, name, gtin, receipt_code, retailer, volume in (
                ("a", "AH Halfvolle melk", "8719587325926", "823326", "ah", 1.0),
                ("b", "Jumbo Halfvolle melk", "8718452513666", "394270", "jumbo", 1.0),
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

        # Same global product in another household must never expose or
        # mutate that household's inventory when synonyms/classifications
        # change. Its household article ID deliberately differs.
        other_household_id = "synonym-chain-other-household"
        with self.engine.begin() as conn:
            conn.execute(text("""
                INSERT INTO household_articles (id, household_id, global_product_id, status)
                VALUES ('ha-other', :household, 'a', 'active')
            """), {"household": other_household_id})
            conn.execute(text("""
                INSERT INTO inventory
                    (id, household_id, household_article_id, naam, aantal, status)
                VALUES ('inv-other', :household, 'ha-other',
                        'AH Halfvolle melk', 7, 'active')
            """), {"household": other_household_id})

        # Use the actual canonical source query for receipt_table_lines.
        # These are synthetic receipts inside this test's disposable schema,
        # not existing user receipts, OCR, or live retailer imports.
        with self.engine.begin() as conn:
            conn.exec_driver_sql("""
                CREATE TABLE purchase_import_batches (
                    id TEXT PRIMARY KEY, raw_payload TEXT, source_type TEXT
                )
            """)
            conn.exec_driver_sql("""
                CREATE TABLE purchase_import_lines (
                    id TEXT PRIMARY KEY, batch_id TEXT,
                    external_article_code TEXT, article_name_raw TEXT,
                    brand_raw TEXT, quantity_raw NUMERIC, unit_raw TEXT,
                    external_line_ref TEXT, created_at TIMESTAMPTZ
                )
            """)
            conn.exec_driver_sql("""
                CREATE TABLE raw_receipts (
                    id TEXT PRIMARY KEY, household_id TEXT, deleted_at TIMESTAMPTZ
                )
            """)
            conn.exec_driver_sql("""
                CREATE TABLE receipt_tables (
                    id TEXT PRIMARY KEY, raw_receipt_id TEXT, household_id TEXT,
                    store_chain TEXT, store_name TEXT, deleted_at TIMESTAMPTZ,
                    workflow_state TEXT, created_at TIMESTAMPTZ
                )
            """)
            conn.exec_driver_sql("""
                CREATE TABLE receipt_table_lines (
                    id TEXT PRIMARY KEY, receipt_table_id TEXT,
                    corrected_raw_label TEXT, normalized_label TEXT, raw_label TEXT,
                    external_article_code TEXT, barcode TEXT, quantity NUMERIC, unit TEXT,
                    is_deleted BOOLEAN, line_role TEXT,
                    inventory_eligible INTEGER, line_index INTEGER
                )
            """)
            for retailer, receipt_name, article_code, line_id in (
                ("ah", "AH Halfvolle melk", "823326", "chain-ah"),
                ("jumbo", "Jumbo Halfvolle melk", "394270", "chain-jumbo"),
            ):
                conn.execute(text("""
                    INSERT INTO raw_receipts (id, household_id)
                    VALUES (:raw_id, :household)
                """), {"raw_id": "raw-" + line_id, "household": household_id})
                conn.execute(text("""
                    INSERT INTO receipt_tables
                        (id, raw_receipt_id, household_id, store_chain,
                         store_name, workflow_state, created_at)
                    VALUES (:receipt, :raw_id, :household, :retailer,
                            :retailer, 'active', CURRENT_TIMESTAMP)
                """), {"receipt": "receipt-" + line_id, "raw_id": "raw-" + line_id,
                       "household": household_id, "retailer": retailer})
                conn.execute(text("""
                    INSERT INTO receipt_table_lines
                        (id, receipt_table_id, raw_label, external_article_code,
                         quantity, unit, is_deleted, line_role,
                         inventory_eligible, line_index)
                    VALUES (:line, :receipt, :name, :article_code,
                            1, 'l', FALSE, 'product', 1, 0)
                """), {"line": line_id, "receipt": "receipt-" + line_id,
                       "name": receipt_name, "article_code": article_code})

        # The receipt rows are synthetic, but ED2 now executes its *actual*
        # production receipt-table SELECT and central identity resolver.
        with self.engine.connect() as conn:
            overview = ed2.list_all_external_articles(conn=conn)
        self.assertEqual(overview["counts"], {
            "unlinked": 0, "classification_pending": 0, "linked": 2,
        })
        rows = {row["retailer_code"]: row for row in overview["items"]}
        self.assertEqual(set(rows), {"ah", "jumbo"})
        self.assertEqual({row["id"] for row in rows.values()}, {
            "receipt-table-line:chain-ah", "receipt-table-line:chain-jumbo",
        })
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
        with self.engine.connect() as conn:
            cbs_before = dict(conn.execute(text("""
                SELECT global_product_id, cbs_code
                FROM global_product_cbs_classifications
            """)).all())
        self.assertEqual(cbs_before, {"a": "011420"})

        def project_almost_out():
            with self.engine.connect() as conn:
                # Submit a forged foreign article ID alongside legitimate rows.
                # The production service must filter by the actual household.
                article_rows = [
                    {"id": "ha-ah"}, {"id": "ha-jumbo"}, {"id": "ha-other"},
                ]
                groups = almost_out.load_groups(conn, household_id, article_rows, {})
                projections = [almost_out.load_group_projection(conn, household_id, group)
                               for group in groups]
                stock_count = conn.execute(text("""
                    SELECT COALESCE(SUM(aantal), 0) FROM inventory
                    WHERE household_id=:household
                """), {"household": household_id}).scalar_one()
            return groups, projections, stock_count

        def project_other_household():
            with self.engine.connect() as conn:
                # Try to force the foreign household into this projection too.
                groups = almost_out.load_groups(conn, other_household_id, [
                    {"id": "ha-other"}, {"id": "ha-ah"}, {"id": "ha-jumbo"},
                ], {})
                projections = [almost_out.load_group_projection(
                    conn, other_household_id, group
                ) for group in groups]
            return groups, projections

        # GS1 and consistent packaging already permit one readable product group;
        # a synonym confirmation never silently creates inventory transactions.
        groups_before, projections_before, stock_before = project_almost_out()
        self.assertEqual(len(groups_before), 1)
        self.assertEqual({item["id"] for item in groups_before[0]["members"]},
                         {"ha-ah", "ha-jumbo"})
        self.assertEqual(sum(float(row["quantity"]) for row in
                             projections_before[0]["inventory_rows"]), 3.0)
        self.assertEqual(float(stock_before), 3.0)
        other_groups_before, other_projections_before = project_other_household()
        self.assertEqual(len(other_groups_before), 1)
        self.assertEqual([row["id"] for row in other_groups_before[0]["members"]],
                         ["ha-other"])
        self.assertEqual([row["household_article_id"] for row in
                          other_projections_before[0]["inventory_rows"]], ["ha-other"])
        self.assertEqual(float(other_projections_before[0]["inventory_rows"][0]["quantity"]), 7.0)

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
            linked = service.confirm_pairs(conn, [selection], "chain-test-admin")
            self.assertEqual(linked["linked"], 1)
            self.assertEqual(linked["already_linked"], 0)
            self.assertEqual(linked["classification_inheritance"]["cbs_inherited"], 1)
            self.assertEqual(linked["classification_inheritance"]["gpc_inherited"], 0)
            self.assertEqual(linked["classification_inheritance"]["conflicts"], [])
            self.assertEqual(dict(conn.execute(text("""
                SELECT global_product_id, cbs_code
                FROM global_product_cbs_classifications
            """)).all()), {"a": "011420", "b": "011420"})
            # The classification audit is tied to the correct distinct product
            # identities; not to receipt text, GTIN equality or household stock.
            events = [dict(row) for row in conn.execute(text("""
                SELECT source_product_id, target_product_id, classification_system,
                       classification_code, status
                FROM article_classification_sync_events
            """)).mappings()]
            self.assertEqual(events, [{
                "source_product_id": "a", "target_product_id": "b",
                "classification_system": "CBS",
                "classification_code": "011420", "status": "processed",
            }])
        with self.engine.begin() as conn:
            self.assertEqual(service.confirmed_pairs(conn), {("a", "b")})
            self.assertEqual(service.confirm_pairs(conn, [selection], "chain-test-admin"),
                             {"linked": 0, "already_linked": 1})
            self.assertEqual(conn.execute(text(
                "SELECT COUNT(*) FROM global_product_cbs_history"
            )).scalar_one(), 1)
            self.assertEqual(conn.execute(text(
                "SELECT COUNT(*) FROM article_classification_sync_events"
            )).scalar_one(), 1)
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
                             projections_after[0]["inventory_rows"]), 3.0)
        self.assertEqual(float(stock_after), float(stock_before))
        self.assertEqual(float(stock_after), 3.0)
        other_groups_after, other_projections_after = project_other_household()
        self.assertEqual(len(other_groups_after), 1)
        self.assertEqual([row["id"] for row in other_groups_after[0]["members"]],
                         ["ha-other"])
        self.assertEqual([row["household_article_id"] for row in
                          other_projections_after[0]["inventory_rows"]], ["ha-other"])
        self.assertEqual(float(other_projections_after[0]["inventory_rows"][0]["quantity"]), 7.0)
        with self.engine.connect() as conn:
            self.assertEqual(conn.execute(text(
                "SELECT COUNT(*) FROM external_article_product_links"
            )).scalar_one(), 2)
            self.assertEqual(conn.execute(text(
                "SELECT COUNT(*) FROM household_articles"
            )).scalar_one(), 3)
            self.assertEqual(conn.execute(text(
                "SELECT COUNT(*) FROM inventory"
            )).scalar_one(), 3)
        with self.engine.connect() as conn:
            self.assertEqual(conn.execute(
                text("SELECT COUNT(*) FROM inventory_events")
            ).scalar_one(), 0)

        # A confirmed synonym remains an explicit authority when GPC
        # classification is removed. Catalogus identity is independent of
        # classification (PR #671) and stock must remain unchanged.
        with self.engine.begin() as conn:
            conn.execute(text("""
                DELETE FROM global_product_gpc_bricks WHERE global_product_id='b'
            """))
            conn.execute(text("""
                DELETE FROM product_group_memberships WHERE global_product_id='b'
            """))
        with self.engine.connect() as conn:
            downgraded_ed2 = ed2.list_all_external_articles(conn=conn)
        statuses = {row["retailer_code"]: row["link_status"]
                    for row in downgraded_ed2["items"]}
        self.assertEqual(statuses, {"ah": "linked", "jumbo": "linked"})
        groups_missing_type, projections_missing_type, stock_missing_type = project_almost_out()
        self.assertEqual(len(groups_missing_type), 1)
        self.assertEqual(
            {row["id"] for row in groups_missing_type[0]["members"]},
            {"ha-ah", "ha-jumbo"},
        )
        self.assertEqual(
            {row["household_article_id"] for row in projections_missing_type[0]["inventory_rows"]},
            {"ha-ah", "ha-jumbo"},
        )
        self.assertEqual(
            sum(float(row["quantity"]) for row in projections_missing_type[0]["inventory_rows"]),
            3.0,
        )
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
                self.assertEqual(self.client.post('/api/external-databases/article-synonyms/link/review', json={'selections':[dict(left_product_id='a',right_product_id='b',fingerprint='0'*64)]}).status_code,status)
                self.assertEqual(self.client.post('/api/external-databases/article-synonyms/unlink', json={'selections':[dict(left_product_id='a',right_product_id='b',fingerprint='0'*64)]}).status_code,status)
        with patch.object(routes, 'require_platform_permission_from_session', return_value=SimpleNamespace(is_frontteam=False,is_platform_superuser=False)):
            self.assertEqual(self.client.get('/api/external-databases/article-synonyms').status_code,403)

    def test_internal_sync_monitor_denies_anonymous_household_and_forged_retry(self):
        path = '/api/external-databases/article-synonyms/sync-exceptions'
        payload = {'event_id': str(uuid4()), 'expected_decision_version': 1,
                   'expected_target_version': 0, 'expected_target_code': ''}
        for status in (401, 403):
            with patch.object(routes, 'require_platform_permission_from_session',
                              side_effect=HTTPException(status)):
                self.assertEqual(self.client.get(path).status_code, status)
                self.assertEqual(self.client.post(path + '/retry', json=payload).status_code, status)
        with patch.object(routes, 'require_platform_permission_from_session',
                          return_value=SimpleNamespace(is_frontteam=False, is_platform_superuser=False)):
            self.assertEqual(self.client.get(path).status_code, 403)
            self.assertEqual(self.client.post(path + '/retry', json=payload).status_code, 403)
        self.assertEqual(self.client.post(path + '/retry', json={
            **payload, 'actor_id': 'forged', 'household_id': '0',
        }).status_code, 422)
        self.assertEqual(self.client.post(path + '/retry', json={
            'event_id': payload['event_id'], 'expected_decision_version': -1,
        }).status_code, 422)
        # An anonymous request must receive 401, not a made-up 403.
        self.assertEqual(self.client.get(path + '?limit=101').status_code, 401)
        actor = SimpleNamespace(is_frontteam=True, is_platform_superuser=False,
                                user_id='actor')
        with patch.object(routes, 'require_platform_permission_from_session',
                          return_value=actor):
            self.assertEqual(self.client.get(path + '?limit=101').status_code, 422)

    def test_gpc_choice_requires_existing_gpc_write_permission(self):
        actor = SimpleNamespace(is_platform_superuser=True, is_frontteam=False, user_id='actor')
        def authorize(permission):
            if permission == 'platform.gpc.update':
                raise HTTPException(403, 'GS1 GPC-bewerking is niet toegestaan.')
            return actor
        payload = {
            'selections': [dict(left_product_id='a', right_product_id='b',
                                fingerprint='a' * 64, manual=True)],
            'decisions': [dict(left_product_id='a', right_product_id='b',
                               snapshot='b' * 64, gpc_source_id='a')],
        }
        with patch.object(routes, 'require_platform_permission_from_session', side_effect=authorize):
            response = self.client.post('/api/external-databases/article-synonyms/link', json=payload)
        self.assertEqual(response.status_code, 403)

    def test_superuser_gpc_choice_uses_platform_authority_not_household_authority(self):
        """The system-household Superuser can choose the prevailing central GPC."""
        actor = SimpleNamespace(is_platform_superuser=True, is_frontteam=False,
                                user_id='superuser')
        checked = []

        def authorize(permission):
            checked.append(permission)
            if permission == 'gpc.update':
                raise AssertionError('Household permission must not guard central GPC writes')
            if permission not in {'platform.external_products.link_existing',
                                  'platform.gpc.update'}:
                raise HTTPException(403)
            return actor

        payload = {
            'selections': [dict(left_product_id='a', right_product_id='b',
                                fingerprint='a' * 64, manual=True)],
            'decisions': [dict(left_product_id='a', right_product_id='b',
                               snapshot='b' * 64, gpc_source_id='a')],
        }
        with patch.object(routes, 'require_platform_permission_from_session',
                          side_effect=authorize), \
             patch.object(routes, 'engine') as engine, \
             patch.object(routes, 'confirm_pairs',
                          return_value={'linked': 1, 'classification_inheritance': {
                              'gpc_resolved': 1}}) as confirm:
            result = self.client.post('/api/external-databases/article-synonyms/link',
                                      json=payload)
        self.assertEqual(result.status_code, 200)
        self.assertEqual(result.json()['classification_inheritance']['gpc_resolved'], 1)
        self.assertEqual(checked, ['platform.external_products.link_existing',
                                   'platform.gpc.update'])
        engine.begin.assert_called_once()
        confirm.assert_called_once()

    def test_frontteam_may_link_but_not_override_gpc_without_platform_grant(self):
        actor = SimpleNamespace(is_platform_superuser=False, is_frontteam=True,
                                user_id='frontteam')
        checked = []

        def authorize(permission):
            checked.append(permission)
            if permission == 'platform.gpc.update':
                raise HTTPException(403, 'Centrale GS1 GPC-wijziging niet toegestaan.')
            return actor

        payload = {
            'selections': [dict(left_product_id='a', right_product_id='b',
                                fingerprint='a' * 64, manual=True)],
            'decisions': [dict(left_product_id='a', right_product_id='b',
                               snapshot='b' * 64, gpc_source_id='a')],
        }
        with patch.object(routes, 'require_platform_permission_from_session',
                          side_effect=authorize), \
             patch.object(routes, 'engine') as engine:
            response = self.client.post('/api/external-databases/article-synonyms/link',
                                        json=payload)
        self.assertEqual(response.status_code, 403)
        self.assertEqual(checked, ['platform.external_products.link_existing',
                                   'platform.gpc.update'])
        engine.begin.assert_not_called()

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
