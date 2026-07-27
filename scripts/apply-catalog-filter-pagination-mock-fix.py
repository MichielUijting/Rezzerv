from __future__ import annotations

from pathlib import Path

TARGET = Path('frontend/tests/e2e/external-databases.frontend-regression.spec.js')

OLD = """async function routeReceiptItems(page, items) {
  await page.route('**/api/external-databases/receipt-items?*', async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({ items }),
    });
  });
"""

NEW = """async function routeReceiptItems(page, items) {
  await page.route('**/api/external-databases/receipt-items?*', async (route) => {
    const url = new URL(route.request().url());
    const catalogLinked = url.searchParams.get('catalogLinked') || 'all';
    const filteredItems = items.filter((item) => {
      const linked = item.central_link_active === true || item.is_linked_to_catalog === true;
      if (catalogLinked === 'linked') return linked;
      if (catalogLinked === 'unlinked') return !linked;
      return true;
    });
    const pageNumber = Number(url.searchParams.get('page') || 1);
    const pageSize = Number(url.searchParams.get('page_size') || 10);
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        items: filteredItems,
        total: filteredItems.length,
        page: pageNumber,
        page_size: pageSize,
        page_count: Math.max(1, Math.ceil(filteredItems.length / pageSize)),
        read_only: true,
        projection_mode: 'regression_mock',
      }),
    });
  });
"""


def main() -> None:
    source = TARGET.read_text(encoding='utf-8-sig')
    count = source.count(OLD)
    if count != 1:
        raise RuntimeError(f'catalogusfiltermock: verwacht exact 1 treffer, gevonden {count}')
    TARGET.write_text(source.replace(OLD, NEW, 1), encoding='utf-8', newline='\n')
    print('CATALOG_FILTER_PAGINATION_MOCK_FIX_APPLIED')


if __name__ == '__main__':
    main()
