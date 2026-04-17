from __future__ import annotations

from dataclasses import dataclass
from typing import Any
from uuid import uuid4

from sqlalchemy import text

TEST_HOUSEHOLD_ID = '__product_enrichment_self_test__'
TEST_BARCODE = '8076800195057'  # Present in public_product_catalog.json
TEST_ARTICLE_NAME = 'Barilla Spaghetti No. 5'


@dataclass
class Scenario:
    scenario_id: str
    name: str
    force_refresh: bool
    expected_status: str
    expected_title_contains: str
    notes: str = ''


def _api():
    from app import main as api
    return api


def _cleanup(conn, household_id: str) -> None:
    conn.execute(text('DELETE FROM product_enrichment_attempts WHERE household_article_id IN (SELECT id FROM household_articles WHERE household_id = :household_id) OR global_product_id IN (SELECT global_product_id FROM household_articles WHERE household_id = :household_id)'), {'household_id': household_id})
    conn.execute(text('DELETE FROM product_enrichment_audit WHERE household_article_id IN (SELECT id FROM household_articles WHERE household_id = :household_id) OR global_product_id IN (SELECT global_product_id FROM household_articles WHERE household_id = :household_id)'), {'household_id': household_id})
    conn.execute(text('DELETE FROM product_enrichments WHERE household_article_id IN (SELECT id FROM household_articles WHERE household_id = :household_id) OR global_product_id IN (SELECT global_product_id FROM household_articles WHERE household_id = :household_id)'), {'household_id': household_id})
    conn.execute(text('DELETE FROM product_identities WHERE household_article_id IN (SELECT id FROM household_articles WHERE household_id = :household_id)'), {'household_id': household_id})
    conn.execute(text('DELETE FROM household_articles WHERE household_id = :household_id'), {'household_id': household_id})


def _ensure_article(conn, household_id: str, article_name: str = TEST_ARTICLE_NAME) -> str:
    article_id = str(uuid4())
    conn.execute(text("""
        INSERT INTO household_articles (
            id, household_id, naam, barcode, consumable, status, updated_at
        ) VALUES (
            :id, :household_id, :naam, :barcode, 1, 'active', CURRENT_TIMESTAMP
        )
    """), {
        'id': article_id,
        'household_id': household_id,
        'naam': article_name,
        'barcode': TEST_BARCODE,
    })
    return article_id


def _run_scenario(conn, household_id: str, scenario: Scenario) -> dict[str, Any]:
    api = _api()
    _cleanup(conn, household_id)
    article_id = _ensure_article(conn, household_id)
    try:
        api.upsert_product_identity(conn, article_id, 'gtin', TEST_BARCODE, 'self_test', confidence_score=1.0, is_primary=True)
    except Exception:
        pass
    enrichment = api.ensure_article_product_enrichment(conn, article_id, TEST_BARCODE, force_refresh=scenario.force_refresh)
    product_details = api.get_article_product_details(conn, household_id, article_id=article_id, auto_enrich=False)
    global_product_id = api.resolve_global_product_id_for_article(conn, article_id, TEST_BARCODE)
    latest_global = api.get_latest_global_product_enrichment(conn, global_product_id)
    attempts = api.get_recent_product_enrichment_attempts(conn, article_id, limit=5)
    product_row = conn.execute(text('SELECT id, primary_gtin, name, brand, category, source FROM global_products WHERE id = :id LIMIT 1'), {'id': global_product_id}).mappings().first() if global_product_id else None

    actual_status = 'failed'
    error = None
    if enrichment and enrichment.get('lookup_status') == scenario.expected_status and latest_global and latest_global.get('lookup_status') == scenario.expected_status:
        title = str((latest_global or {}).get('title') or '')
        if scenario.expected_title_contains.lower() in title.lower():
            actual_status = 'passed'
        else:
            error = f"Titel bevat '{scenario.expected_title_contains}' niet: {title}"
    else:
        error = f"Enrichmentstatus niet zoals verwacht: article={enrichment and enrichment.get('lookup_status')} global={latest_global and latest_global.get('lookup_status')}"

    if actual_status == 'passed' and not global_product_id:
        actual_status = 'failed'
        error = 'Geen global_product_id gekoppeld aan household_article'
    if actual_status == 'passed' and (not product_row or str(product_row.get('primary_gtin') or '') != TEST_BARCODE):
        actual_status = 'failed'
        error = 'global_products.primary_gtin is niet correct gevuld'
    shared_row_count = None
    second_article_id = None
    if actual_status == 'passed' and global_product_id:
        second_article_id = _ensure_article(conn, household_id, article_name=f"{TEST_ARTICLE_NAME} extra")
        try:
            api.upsert_product_identity(conn, second_article_id, 'gtin', TEST_BARCODE, 'self_test', confidence_score=1.0, is_primary=True)
        except Exception:
            pass
        second_enrichment = api.ensure_article_product_enrichment(conn, second_article_id, TEST_BARCODE, force_refresh=False)
        source_name = str((latest_global or {}).get('source_name') or (second_enrichment or {}).get('source_name') or '')
        shared_row_count = conn.execute(text("""
            SELECT COUNT(*) AS cnt
            FROM product_enrichments
            WHERE global_product_id = :global_product_id
              AND source_name = :source_name
        """), {'global_product_id': global_product_id, 'source_name': source_name}).mappings().first().get('cnt')
        if not second_enrichment or second_enrichment.get('lookup_status') != scenario.expected_status:
            actual_status = 'failed'
            error = 'Tweede artikel met dezelfde barcode gebruikt de centrale enrichment niet correct'
        elif int(shared_row_count or 0) != 1:
            actual_status = 'failed'
            error = f'Centrale enrichment is niet uniek per global_product_id + source_name (aantal={shared_row_count})'

    if actual_status == 'passed' and not attempts:
        actual_status = 'failed'
        error = 'Geen enrichment-auditpogingen vastgelegd'

    return {
        'scenario_id': scenario.scenario_id,
        'name': scenario.name,
        'status': actual_status,
        'notes': scenario.notes,
        'expected_status': scenario.expected_status,
        'article_enrichment_status': enrichment.get('lookup_status') if enrichment else None,
        'global_enrichment_status': latest_global.get('lookup_status') if latest_global else None,
        'global_product_id': global_product_id,
        'global_product': dict(product_row) if product_row else None,
        'article_product_details': {
            'identity': product_details.get('identity'),
            'enrichment_status': product_details.get('enrichment_status'),
            'enrichment': product_details.get('enrichment'),
        },
        'second_article_id': second_article_id,
        'shared_global_enrichment_row_count': int(shared_row_count or 0) if shared_row_count is not None else None,
        'attempt_count': len(attempts),
        'attempts': attempts,
        'error': error,
    }


def run_product_enrichment_backend_self_test(engine) -> dict[str, Any]:
    scenarios = [
        Scenario(
            scenario_id='product_enrichment_global_source_of_truth',
            name='Barcode lookup wordt centraal opgeslagen op global_products',
            force_refresh=True,
            expected_status='found',
            expected_title_contains='Barilla',
            notes='Controleert centrale enrichment-opslag, global_product-koppeling en audittrail.',
        )
    ]
    results: list[dict[str, Any]] = []
    with engine.begin() as conn:
        for scenario in scenarios:
            results.append(_run_scenario(conn, TEST_HOUSEHOLD_ID, scenario))
        _cleanup(conn, TEST_HOUSEHOLD_ID)
    failed_count = sum(1 for item in results if item.get('status') == 'failed')
    passed_count = sum(1 for item in results if item.get('status') == 'passed')
    blocked_count = sum(1 for item in results if item.get('status') == 'blocked')
    return {
        'test_type': 'product_enrichment_self_test',
        'status': 'passed' if failed_count == 0 else 'failed',
        'passed_count': passed_count,
        'blocked_count': blocked_count,
        'failed_count': failed_count,
        'results': results,
    }
