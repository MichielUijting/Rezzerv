from __future__ import annotations

from pathlib import Path

FRONTEND = Path('frontend/tests/e2e/external-databases.frontend-regression.spec.js')
BACKEND = Path('backend/tests/test_off_product_type_link_contract_selftest.py')


def replace_once(source: str, old: str, new: str, label: str) -> str:
    count = source.count(old)
    if count != 1:
        raise RuntimeError(f'{label}: verwacht exact 1 treffer, gevonden {count}')
    return source.replace(old, new, 1)


def update_frontend() -> None:
    source = FRONTEND.read_text(encoding='utf-8-sig')
    old = """  await page.route('**/api/external-databases/receipt-items?*', async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({ items }),
    });
  });
"""
    new = """  await page.route('**/api/external-databases/receipt-items?*', async (route) => {
    const url = new URL(route.request().url());
    const catalogLinked = url.searchParams.get('catalogLinked') || 'all';
    const filteredItems = items.filter((item) => {
      const linked = item.central_link_active === true || item.is_linked_to_catalog === true;
      if (catalogLinked === 'linked') return linked;
      if (catalogLinked === 'unlinked') return !linked;
      return true;
    });
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        items: filteredItems,
        total: filteredItems.length,
        page: Number(url.searchParams.get('page') || 1),
        page_size: Number(url.searchParams.get('page_size') || 10),
        page_count: 1,
        read_only: true,
        projection_mode: 'regression_mock',
      }),
    });
  });
"""
    source = replace_once(source, old, new, 'serverfilter-mock')
    FRONTEND.write_text(source, encoding='utf-8', newline='\n')


def update_backend() -> None:
    source = BACKEND.read_text(encoding='utf-8-sig')
    source = replace_once(
        source,
        '    gtin = f"98{numeric_suffix}"\n',
        '    gtin = f"98{numeric_suffix}"\n    identity_candidate_id = f"off-link-identity-{suffix}"\n',
        'identity kandidaat-id',
    )
    before_anchor = """    with engine.begin() as conn:
        before = {
"""
    before_insert = """    with engine.begin() as conn:
        conn.execute(text(\"\"\"
            INSERT INTO external_product_candidates (
                id, purchase_import_line_id, context_key,
                retailer_code, receipt_line_text, candidate_name,
                candidate_source_name, candidate_source_product_code,
                score, candidate_status, is_user_confirmed,
                created_by, created_at, updated_at
            ) VALUES (
                :id, :line_id, :context_key,
                'contractwinkel', 'Contract Halfvolle melk', 'Contractidentiteit',
                'contract_selftest', :gtin,
                1.0, 'candidate', 0,
                'contract_selftest', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP
            )
        \"\"\"), {
            'id': identity_candidate_id,
            'line_id': line_id,
            'context_key': f'purchase-import-line:{line_id}',
            'gtin': gtin,
        })
        before = {
"""
    source = replace_once(source, before_anchor, before_insert, 'stabiele winkelidentiteit')
    cleanup_anchor = """        with engine.begin() as conn:
            conn.execute(text("DELETE FROM purchase_import_lines WHERE id = :id"), {"id": line_id})
"""
    cleanup_insert = """        with engine.begin() as conn:
            conn.execute(text("DELETE FROM external_product_candidates WHERE id = :id"), {"id": identity_candidate_id})
            conn.execute(text("DELETE FROM purchase_import_lines WHERE id = :id"), {"id": line_id})
"""
    source = replace_once(source, cleanup_anchor, cleanup_insert, 'identity cleanup')
    BACKEND.write_text(source, encoding='utf-8', newline='\n')


def main() -> None:
    update_frontend()
    update_backend()
    print('PAGINATION_REGRESSION_FIXTURES_APPLIED')


if __name__ == '__main__':
    main()
