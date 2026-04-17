from __future__ import annotations

import importlib
import json
import os
import shutil
import sqlite3
import sys
import tempfile
import uuid
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[3]
BACKEND_ROOT = PROJECT_ROOT / 'backend'
SOURCE_DB = BACKEND_ROOT / 'rezzerv.db'
REPORT_PATH = PROJECT_ROOT / 'canonical_identity_match_self_test.json'


def make_temp_db() -> Path:
    tmp_dir = Path(tempfile.mkdtemp(prefix='rezzerv-canonical-identity-'))
    db_path = tmp_dir / 'rezzerv.db'
    shutil.copy2(SOURCE_DB, db_path)
    return db_path


def import_module_for_db(db_path: Path):
    os.environ['DATABASE_URL'] = f'sqlite:///{db_path.as_posix()}'
    if str(BACKEND_ROOT) not in sys.path:
        sys.path.insert(0, str(BACKEND_ROOT))
    for name in ['app.main', 'app.db']:
        if name in sys.modules:
            del sys.modules[name]
    return importlib.import_module('app.main')


def query_one(conn: sqlite3.Connection, sql: str, params: tuple = ()):  # noqa: ANN001
    row = conn.execute(sql, params).fetchone()
    if row is None:
        return None
    columns = [col[0] for col in conn.execute(sql, params).description]
    return dict(zip(columns, row))


def main():
    db_path = make_temp_db()
    api = import_module_for_db(db_path)

    household_one = f'self-test-household-1-{uuid.uuid4()}'
    household_two = f'self-test-household-2-{uuid.uuid4()}'
    provider_row = None
    connection_row = None

    with api.engine.begin() as conn:
        provider_row = conn.execute(api.text("SELECT id FROM store_providers ORDER BY id LIMIT 1")).mappings().first()
        connection_row = conn.execute(api.text("SELECT id FROM household_store_connections ORDER BY id LIMIT 1")).mappings().first()
        assert provider_row and connection_row, 'Seeddata ontbreekt voor store_provider of household_store_connection'

        conn.execute(api.text("INSERT INTO households (id, naam, created_at) VALUES (:id, :naam, CURRENT_TIMESTAMP)"), {'id': household_one, 'naam': 'Self Test Huis 1'})
        conn.execute(api.text("INSERT INTO households (id, naam, created_at) VALUES (:id, :naam, CURRENT_TIMESTAMP)"), {'id': household_two, 'naam': 'Self Test Huis 2'})

        global_product_id = str(uuid.uuid4())
        conn.execute(
            api.text(
                """
                INSERT INTO global_products (id, primary_gtin, name, brand, category, source, status, created_at, updated_at)
                VALUES (:id, NULL, :name, :brand, :category, 'self_test', 'active', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
                """
            ),
            {'id': global_product_id, 'name': 'Canonieke Mosterd', 'brand': 'Rezzerv', 'category': 'Sauzen'},
        )

        api.ensure_household_article(conn, household_one, 'Canonieke Mosterd', consumable=True)
        api.ensure_household_article(conn, household_two, 'Canonieke Mosterd', consumable=True)
        article_one = api.get_household_article_row_by_name(conn, household_one, 'Canonieke Mosterd')
        article_two = api.get_household_article_row_by_name(conn, household_two, 'Canonieke Mosterd')
        assert article_one and article_two, 'Household articles konden niet worden aangemaakt'

        api.set_household_article_global_product_id(conn, str(article_one['id']), global_product_id)
        api.set_household_article_global_product_id(conn, str(article_two['id']), global_product_id)
        identity = api.upsert_product_identity(
            conn,
            str(article_one['id']),
            'external_article_number',
            'SKU-42 / test',
            'self_test',
            confidence_score=1.0,
            is_primary=True,
        )

        batch_id = str(uuid.uuid4())
        line_id = str(uuid.uuid4())
        conn.execute(
            api.text(
                """
                INSERT INTO purchase_import_batches (
                    id, household_id, store_provider_id, connection_id, source_type, source_reference, import_status, raw_payload, created_at
                ) VALUES (
                    :id, :household_id, :store_provider_id, :connection_id, 'self_test', 'canonical-identity', 'pending', '{}', CURRENT_TIMESTAMP
                )
                """
            ),
            {
                'id': batch_id,
                'household_id': household_two,
                'store_provider_id': str(provider_row['id']),
                'connection_id': str(connection_row['id']),
            },
        )
        conn.execute(
            api.text(
                """
                INSERT INTO purchase_import_lines (
                    id, batch_id, external_line_ref, external_article_code, article_name_raw, brand_raw, quantity_raw, unit_raw,
                    line_price_raw, currency_code, match_status, review_decision, processing_status, created_at, updated_at
                ) VALUES (
                    :id, :batch_id, 'identity-line-1', :external_article_code, :article_name_raw, :brand_raw, 1, 'stuk',
                    2.49, 'EUR', 'unmatched', 'selected', 'pending', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP
                )
                """
            ),
            {
                'id': line_id,
                'batch_id': batch_id,
                'external_article_code': 'sku 42-test',
                'article_name_raw': 'Canonieke Mosterd',
                'brand_raw': 'Rezzerv',
            },
        )

        before_count = conn.execute(api.text("SELECT COUNT(*) AS total FROM global_products")).mappings().first()['total']
        resolved = api.resolve_receipt_line_product_links(
            conn,
            household_two,
            'Canonieke Mosterd',
            barcode='sku 42-test',
            brand='Rezzerv',
            create_global_product=True,
            create_household_article=False,
            external_article_code='sku 42-test',
        )
        synced = api.sync_purchase_import_line_product_links(conn, line_id, household_two)
        after_count = conn.execute(api.text("SELECT COUNT(*) AS total FROM global_products")).mappings().first()['total']
        stored_line = conn.execute(
            api.text(
                """
                SELECT id, external_article_code, matched_global_product_id, matched_household_article_id, match_status
                FROM purchase_import_lines
                WHERE id = :id
                LIMIT 1
                """
            ),
            {'id': line_id},
        ).mappings().first()

    assert resolved['matched_global_product_id'] == global_product_id, resolved
    assert str(resolved['match_method']).startswith('identity:'), resolved
    assert resolved['match_method'] != 'created_new', resolved
    assert after_count == before_count, {'before_count': before_count, 'after_count': after_count}
    assert synced['matched_global_product_id'] == global_product_id, synced
    assert stored_line['matched_global_product_id'] == global_product_id, stored_line
    assert stored_line['matched_household_article_id'], stored_line

    report = {
        'status': 'passed',
        'database_under_test': str(db_path),
        'checks': {
            'identity_match_reused_existing_global_product': {
                'external_article_code_input': 'sku 42-test',
                'normalized_identity_value': api.normalize_product_identity_value('external_article_number', 'SKU-42 / test'),
                'match_method': resolved['match_method'],
                'confidence_score': resolved['confidence_score'],
                'matched_global_product_id': resolved['matched_global_product_id'],
                'matched_household_article_id': synced['matched_household_article_id'],
                'stored_line': dict(stored_line),
            },
            'no_new_global_product_created': {
                'global_product_count_before': before_count,
                'global_product_count_after': after_count,
                'created_new_present': 'created_new' in str(resolved['match_method']),
            },
            'identity_source_record': {
                'identity_type': identity['identity_type'],
                'identity_value': identity['identity_value'],
                'global_product_id': identity['global_product_id'],
            },
        },
    }
    REPORT_PATH.write_text(json.dumps(report, indent=2, ensure_ascii=False))
    print(json.dumps(report, indent=2, ensure_ascii=False))


if __name__ == '__main__':
    main()
