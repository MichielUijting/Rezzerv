"""Small contract selftest; PostgreSQL transaction and browser tests remain required."""
from pathlib import Path
from app.services.gtin_validation_service import is_valid_gtin


def main():
    assert is_valid_gtin('8712345678906')
    assert not is_valid_gtin('8712345678905')
    assert not is_valid_gtin('12345678')
    root = Path(__file__).parents[1]
    route = (root / 'app/api/catalog_shopify_review_routes.py').read_text(encoding='utf8')
    migration = (root / 'alembic/versions/20261028_01_catalog_shopify_review.py').read_text(encoding='utf8')
    assert "down_revision = '20261027_02'" in migration
    assert 'inhuis_maintenance_write_barrier' in migration
    assert 'with engine.begin() as conn:' in route and 'FOR UPDATE' in route
    assert 'barcode_confirmed' in route and 'expected_version' in route
    catalog = (root / 'app/api/catalog_routes.py').read_text(encoding='utf8')
    assert 'catalog_classification.shopify_path' in catalog
    assert 'article_classification' in catalog
    assert 'CASE WHEN catalog_classification.is_active THEN' in catalog
    # Confirmed category is projected in the normal Catalogus API, and the
    # displayed missing-category label is also the SQL filter/sort value.
    assert "COALESCE({article_classification}, 'Niet geclassificeerd')" in catalog
    assert '"article_classification": visible_article_classification' in catalog
    assert 'select_parts.append(f"{visible_article_classification} AS article_classification")' in catalog

    assert "@router.post('/bulk-remove')" in route
    assert "def remove_batch(payload: RemovalBatch):" in route
    assert "platform.external_products.link_existing" in route
    assert "with engine.begin() as conn:" in route
    assert "is_active = FALSE, version = :version" in route
    assert "action)" in route and "'removed')" in route
    assert "affected.rowcount != 1" in route
    migration02 = (root / 'alembic/versions/20261028_02_catalog_classification_removal.py').read_text(encoding='utf8')
    assert "down_revision = '20261028_01'" in migration02
    assert "'is_active'" in migration02 and "'action'" in migration02
    assert "WHERE is_active = FALSE" in migration02

    for forbidden in ('global_product_gpc_bricks', 'household_articles', 'product_group_memberships', 'inventory_events'):
        assert forbidden not in route
    print('CATALOG_SHOPIFY_REVIEW_CONTRACT_GREEN')


if __name__ == '__main__':
    main()
