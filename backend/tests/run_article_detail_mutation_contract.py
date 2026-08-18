from __future__ import annotations

import runpy
from pathlib import Path


LEGACY_TEST = Path(__file__).with_name('test_article_detail_mutation_contract.py')
namespace = runpy.run_path(str(LEGACY_TEST))


def test_analysis_has_flat_direct_functional_subtabs() -> None:
    read = namespace['_read']
    wrapper = read(namespace['ANALYSIS_WRAPPER_PATH'])
    analysis = read(namespace['ANALYSIS_PATH'])
    policy = read(namespace['POLICY_PATH'])

    for label in ("'Trends'", "'Prijs'", "'Prognose'", "'Onderbouwing'"):
        assert label in wrapper
    assert 'data-active-subtab={activeKey}' in wrapper
    assert 'ariaLabel="Analyse subtabs"' in wrapper
    assert 'className="rz-article-subtab-frame"' in wrapper
    assert 'article-analysis-frame-${activeKey}' in wrapper
    assert 'keepAnalysisSectionsOpen' in wrapper
    assert '.rz-article-section-summary[aria-expanded="false"]' in wrapper
    assert 'summary.click()' in wrapper
    assert 'MutationObserver' not in wrapper
    assert 'dataset.analysisSubtab' not in wrapper

    for anchor in (
        'data-testid="analysis-row-automation"',
        'data-testid="analysis-row-price"',
        'data-testid="analysis-row-consumption"',
        'data-testid="analysis-row-forecast"',
        'data-testid="analysis-row-advice"',
        'data-testid="analysis-row-quality"',
    ):
        assert anchor in analysis

    for selector in (
        '[data-active-subtab="trends"]',
        '[data-active-subtab="price"]',
        '[data-active-subtab="forecast"]',
        '[data-active-subtab="evidence"]',
        '[data-testid="analysis-row-consumption"]',
        '[data-testid="analysis-row-price"]',
        '[data-testid="analysis-row-forecast"]',
        '[data-testid="analysis-row-advice"]',
        '[data-testid="analysis-row-automation"]',
        '[data-testid="analysis-row-quality"]',
    ):
        assert selector in policy
    assert '[data-analysis-subtab]' not in policy


def test_article_detail_backend_has_one_canonical_patch_and_settings_route() -> None:
    read = namespace['_read']
    gateway = read(namespace['GATEWAY_PATH'])
    product_router = read(namespace['PRODUCT_ROUTER_PATH'])
    main = read(namespace['MAIN_PATH'])

    # PATCH en PUT blijven exact één keer geregistreerd: op de canonieke app.main-route.
    assert "@router.patch('/api/household-articles/{household_article_id}')" not in gateway
    assert "@router.put('/api/household-articles/{household_article_id}/settings')" not in gateway
    assert '@app.patch("/api/household-articles/{household_article_id}")' in main
    assert '@app.put("/api/household-articles/{household_article_id}/settings")' in main

    # De admin/eigenaar-borging wordt bij startup op die canonieke FastAPI-calls gezet.
    assert "_install_admin_guard(" in gateway
    assert "dependant.call = guarded_endpoint" in gateway
    assert "'/api/household-articles/{household_article_id}'," in gateway
    assert "'/api/household-articles/{household_article_id}/settings'," in gateway
    assert "preserve_server_owned_settings=True" in gateway

    # Alleen de twee nieuwe artikel-scoped voorraadmutaties zijn echte gateway-routes.
    assert "@router.post('/api/household-articles/{household_article_id}/inventory-events')" in gateway
    assert "@router.post('/api/household-articles/{household_article_id}/inventory-transfers')" in gateway
    assert "_assert_inventory_belongs_to_article" in gateway

    gateway_include = "router.include_router(article_detail_admin_router)"
    assert gateway_include in product_router


def run_contract() -> None:
    obsolete_names = {
        'test_analysis_has_compact_direct_functional_subtabs',
        'test_article_detail_backend_gateway_is_admin_only_and_registered_first',
    }
    for name, candidate in namespace.items():
        if not name.startswith('test_') or not callable(candidate) or name in obsolete_names:
            continue
        candidate()

    test_analysis_has_flat_direct_functional_subtabs()
    test_article_detail_backend_has_one_canonical_patch_and_settings_route()
    print('ARTICLE_DETAIL_MEMBER_READONLY_CONTRACT_GREEN')
    print('ARTICLE_DETAIL_SUBTABS_CONTRACT_GREEN')
    print('ARTICLE_DETAIL_MUTATION_CONTRACT_GREEN')
    print('ARTICLE_DETAIL_ROUTE_OWNERSHIP_GREEN')


if __name__ == '__main__':
    run_contract()
