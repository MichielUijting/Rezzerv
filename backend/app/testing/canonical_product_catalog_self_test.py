from __future__ import annotations

import importlib
import json
import os
import shutil
import sqlite3
import sys
import tempfile
from pathlib import Path
from uuid import uuid4

PROJECT_ROOT = Path(__file__).resolve().parents[3]
BACKEND_ROOT = PROJECT_ROOT / 'backend'
SOURCE_DB = BACKEND_ROOT / 'rezzerv.db'
REPORT_PATH = PROJECT_ROOT / 'canonical_product_catalog_self_test.json'

TEST_BARCODE = '8710400131472'
TEST_PRODUCT_NAME = 'Canonieke Mosterd Test'
TEST_BRAND = 'Rezzerv Testhuis'
HOUSEHOLD_A = '__canon_household_a__'
HOUSEHOLD_B = '__canon_household_b__'


def make_temp_db() -> Path:
    tmp_dir = Path(tempfile.mkdtemp(prefix='rezzerv-canonical-catalog-'))
    db_path = tmp_dir / 'rezzerv.db'
    shutil.copy2(SOURCE_DB, db_path)
    return db_path


def import_api_for_db(db_path: Path):
    os.environ['DATABASE_URL'] = f'sqlite:///{db_path.as_posix()}'
    if str(BACKEND_ROOT) not in sys.path:
        sys.path.insert(0, str(BACKEND_ROOT))
    for name in ['app.main', 'app.db']:
        if name in sys.modules:
            del sys.modules[name]
    return importlib.import_module('app.main')


def cleanup(conn: sqlite3.Connection) -> None:
    article_rows = conn.execute(
        'SELECT id, global_product_id FROM household_articles WHERE household_id IN (?, ?)',
        (HOUSEHOLD_A, HOUSEHOLD_B),
    ).fetchall()
    article_ids = [row[0] for row in article_rows]
    global_product_ids = [row[1] for row in article_rows if row[1]]
    batch_ids = [row[0] for row in conn.execute('SELECT id FROM purchase_import_batches WHERE household_id IN (?, ?)', (HOUSEHOLD_A, HOUSEHOLD_B)).fetchall()]
    if batch_ids:
        marks = ','.join('?' for _ in batch_ids)
        conn.execute(f'DELETE FROM purchase_import_lines WHERE batch_id IN ({marks})', batch_ids)
        conn.execute(f'DELETE FROM purchase_import_batches WHERE id IN ({marks})', batch_ids)
    if article_ids:
        marks = ','.join('?' for _ in article_ids)
        conn.execute(f'DELETE FROM product_identities WHERE household_article_id IN ({marks})', article_ids)
        conn.execute(f'DELETE FROM product_enrichments WHERE household_article_id IN ({marks})', article_ids)
        conn.execute(f'DELETE FROM product_enrichment_audit WHERE household_article_id IN ({marks})', article_ids)
        conn.execute(f'DELETE FROM product_enrichment_attempts WHERE household_article_id IN ({marks})', article_ids)
        conn.execute(f'DELETE FROM household_articles WHERE id IN ({marks})', article_ids)
    if global_product_ids:
        marks = ','.join('?' for _ in global_product_ids)
        conn.execute(f'DELETE FROM product_enrichments WHERE global_product_id IN ({marks})', global_product_ids)
        conn.execute(f'DELETE FROM product_enrichment_audit WHERE global_product_id IN ({marks})', global_product_ids)
        conn.execute(f'DELETE FROM product_enrichment_attempts WHERE global_product_id IN ({marks})', global_product_ids)
        conn.execute(f'DELETE FROM global_products WHERE id IN ({marks})', global_product_ids)
    conn.commit()


def ensure_households(conn: sqlite3.Connection) -> None:
    for household_id, name in [(HOUSEHOLD_A, 'Canon Household A'), (HOUSEHOLD_B, 'Canon Household B')]:
        conn.execute(
            'INSERT OR IGNORE INTO households (id, naam, created_at) VALUES (?, ?, CURRENT_TIMESTAMP)',
            (household_id, name),
        )
    conn.commit()


def insert_household_article(conn: sqlite3.Connection, household_id: str, name: str) -> str:
    article_id = str(uuid4())
    conn.execute(
        '''
        INSERT INTO household_articles (
            id, household_id, naam, barcode, brand_or_maker, status, consumable, updated_at
        ) VALUES (?, ?, ?, ?, ?, 'active', 1, CURRENT_TIMESTAMP)
        ''',
        (article_id, household_id, name, TEST_BARCODE, TEST_BRAND),
    )
    conn.commit()
    return article_id


def main() -> None:
    db_path = make_temp_db()
    api = import_api_for_db(db_path)

    conn = sqlite3.connect(db_path)
    cleanup(conn)
    ensure_households(conn)
    conn.close()

    with api.engine.begin() as tx:
        article_a = insert_household_article(sqlite3.connect(db_path), HOUSEHOLD_A, TEST_PRODUCT_NAME)
        article_b = insert_household_article(sqlite3.connect(db_path), HOUSEHOLD_B, TEST_PRODUCT_NAME)

    with api.engine.begin() as tx:
        api.upsert_product_identity(tx, article_a, 'gtin', TEST_BARCODE, 'self_test', confidence_score=1.0, is_primary=True)
        api.upsert_product_identity(tx, article_b, 'gtin', TEST_BARCODE, 'self_test', confidence_score=1.0, is_primary=True)
        global_product_a = api.ensure_household_article_global_product_link(tx, article_a, TEST_BARCODE)
        global_product_b = api.ensure_household_article_global_product_link(tx, article_b, TEST_BARCODE)

        batch_id = str(uuid4())
        line_id = str(uuid4())
        tx.execute(api.text(
            '''
            INSERT INTO purchase_import_batches (id, household_id, store_provider_id, connection_id, source_type, import_status, created_at)
            VALUES (:id, :household_id, :store_provider_id, :connection_id, 'manual_test', 'new', CURRENT_TIMESTAMP)
            '''
        ), {'id': batch_id, 'household_id': HOUSEHOLD_B, 'store_provider_id': 'manual-test', 'connection_id': f'conn-{batch_id}'})
        tx.execute(api.text(
            '''
            INSERT INTO purchase_import_lines (
                id, batch_id, external_line_ref, external_article_code, article_name_raw, brand_raw,
                quantity_raw, unit_raw, match_status, review_decision, processing_status, created_at, updated_at
            ) VALUES (
                :id, :batch_id, :external_line_ref, :external_article_code, :article_name_raw, :brand_raw,
                '1', 'stuk', 'unmatched', 'selected', 'pending', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP
            )
            '''
        ), {
            'id': line_id,
            'batch_id': batch_id,
            'external_line_ref': 'canon-line-1',
            'article_name_raw': TEST_PRODUCT_NAME,
            'brand_raw': TEST_BRAND,
            'external_article_code': TEST_BARCODE,
        })
        sync_result = api.sync_purchase_import_line_product_links(tx, line_id, HOUSEHOLD_B)

        enrichment_a = api.ensure_article_product_enrichment(tx, article_a, TEST_BARCODE, force_refresh=True)
        enrichment_b = api.ensure_article_product_enrichment(tx, article_b, TEST_BARCODE, force_refresh=False)
        latest_global = api.get_latest_global_product_enrichment(tx, global_product_a)

        duplicate_global_rows = tx.execute(api.text(
            'SELECT COUNT(*) AS cnt FROM global_products WHERE primary_gtin = :barcode'
        ), {'barcode': TEST_BARCODE}).mappings().first()['cnt']
        duplicate_enrichment_rows = tx.execute(api.text(
            '''
            SELECT COUNT(*) AS cnt
            FROM product_enrichments
            WHERE global_product_id = :global_product_id
              AND source_name = :source_name
            '''
        ), {
            'global_product_id': global_product_a,
            'source_name': str((latest_global or {}).get('source_name') or (enrichment_a or {}).get('source_name') or ''),
        }).mappings().first()['cnt']
        linked_line = tx.execute(api.text(
            '''
            SELECT id, matched_global_product_id, matched_household_article_id, match_status
            FROM purchase_import_lines
            WHERE id = :id
            LIMIT 1
            '''
        ), {'id': line_id}).mappings().first()

    report = {
        'status': 'passed' if (global_product_a and global_product_a == global_product_b and int(duplicate_global_rows or 0) == 1 and int(duplicate_enrichment_rows or 0) == 1 and linked_line and linked_line.get('matched_global_product_id') == global_product_a) else 'failed',
        'database_under_test': str(db_path),
        'checks': {
            'same_barcode_maps_to_same_global_product_across_households': {
                'household_a_article_id': article_a,
                'household_b_article_id': article_b,
                'global_product_id_household_a': global_product_a,
                'global_product_id_household_b': global_product_b,
                'shared_global_product': bool(global_product_a and global_product_a == global_product_b),
            },
            'receipt_import_uses_matched_global_product_id': {
                'line_id': line_id,
                'sync_result': sync_result,
                'stored_line': dict(linked_line) if linked_line else None,
            },
            'no_duplicate_global_products_or_enrichments': {
                'barcode': TEST_BARCODE,
                'global_product_row_count_for_barcode': int(duplicate_global_rows or 0),
                'global_enrichment_row_count_for_source': int(duplicate_enrichment_rows or 0),
                'latest_global_enrichment': latest_global,
                'article_a_enrichment_status': (enrichment_a or {}).get('lookup_status'),
                'article_b_enrichment_status': (enrichment_b or {}).get('lookup_status'),
            },
        },
    }
    REPORT_PATH.write_text(json.dumps(report, indent=2, ensure_ascii=False))
    print(json.dumps(report, indent=2, ensure_ascii=False))


if __name__ == '__main__':
    main()
