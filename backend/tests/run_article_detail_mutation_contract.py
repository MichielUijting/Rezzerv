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


def run_contract() -> None:
    obsolete_name = 'test_analysis_has_compact_direct_functional_subtabs'
    for name, candidate in namespace.items():
        if not name.startswith('test_') or not callable(candidate) or name == obsolete_name:
            continue
        candidate()

    test_analysis_has_flat_direct_functional_subtabs()
    print('ARTICLE_DETAIL_MEMBER_READONLY_CONTRACT_GREEN')
    print('ARTICLE_DETAIL_SUBTABS_CONTRACT_GREEN')
    print('ARTICLE_DETAIL_MUTATION_CONTRACT_GREEN')


if __name__ == '__main__':
    run_contract()
