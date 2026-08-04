from pathlib import Path


ROUTE_SOURCE = Path('app/api/day_article_routes.py').read_text(encoding='utf-8')


def test_batch_contract_returns_protected_direct_location():
    assert 'direct_location = ensure_direct_location(conn, household_id)' in ROUTE_SOURCE
    assert '"direct_location": direct_location' in ROUTE_SOURCE


def test_direct_location_is_kept_active_for_existing_location_lists():
    assert 'UPDATE spaces SET active = 1' in ROUTE_SOURCE
    assert 'UPDATE sublocations SET active = 1' in ROUTE_SOURCE
