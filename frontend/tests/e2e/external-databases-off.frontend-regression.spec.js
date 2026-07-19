import { test, expect } from '@playwright/test';
import {
  attachConsoleErrorCollector,
  expectNoConsoleErrors,
} from './helpers/rezzervAssertions.js';

function receiptItemsPayload() {
  return {
    items: [
      {
        receipt_item_id: 'purchase-import-line:purchase-line-off-preview-regression',
        receipt_item_type: 'purchase_import_line',
        receipt_item_source_id: 'purchase-line-off-preview-regression',
        context_key: 'ctx-off-preview-regression',
        receipt_line_id: 'receipt-line-off-preview-regression',
        purchase_import_line_id: 'purchase-line-off-preview-regression',
        receipt_line_text: 'halfvolle melk',
        retailer_code: 'jumbo',
        retailer_article_number: '',
        gtin: '',
        quantity_label: '1 l',
        price: 1.29,
        candidate_id: 'receipt-item-placeholder-off',
        candidate_name: '',
        candidate_brand: '',
        external_source_name: '',
        external_source_product_code: '',
        variant: '',
        score: 0,
        candidate_status: 'candidate',
        is_receipt_item_placeholder: true,
        is_linked_to_catalog: false,
        is_linkable_to_catalog: false,
        candidates: [],
      },
    ],
  };
}

function automaticSearchResponse() {
  return {
    ok: true,
    status: 'found',
    provider: 'legacy_cgi',
    query: 'halfvolle melk',
    mode: 'automatic',
    mutated: false,
    creates_global_product: false,
    creates_household_article: false,
    creates_inventory_event: false,
    results: [
      {
        gtin: '8710000000002',
        product_name: 'Halfvolle melk',
        brand: 'Jumbo',
        score: 0.82,
        automatic_rank_score: 0.93,
        confidence: 'high',
        automatic_evidence: {
          phrase_hits: 1,
          weighted_hits: 2,
        },
      },
    ],
  };
}

function manualSearchResponse() {
  return {
    ok: true,
    status: 'found',
    provider: 'legacy_cgi',
    query: 'melk halfvol zelf zoeken',
    mode: 'manual',
    mutated: false,
    creates_global_product: false,
    creates_household_article: false,
    creates_inventory_event: false,
    results: [
      {
        gtin: '8710000000099',
        product_name: 'Melk halfvol handmatig',
        brand: 'Jumbo',
        score: 0.91,
        confidence: 'high',
      },
    ],
  };
}

test.describe('Externe databases OFF candidate flow', () => {
  test('Detail openen zoekt automatisch read-only en Zelf zoeken vervangt de resultaatset', async ({ page }) => {
    const consoleErrors = attachConsoleErrorCollector(page);
    const offRequestBodies = [];

    await page.route('**/api/external-databases/receipt-items?limit=500', async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify(receiptItemsPayload()),
      });
    });

    await page.route('**/api/external-products/off/search', async (route) => {
      const body = route.request().postDataJSON();
      offRequestBodies.push(body);
      const response = body?.mode === 'manual'
        ? manualSearchResponse()
        : automaticSearchResponse();

      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify(response),
      });
    });

    await page.goto('/externe-databases');
    await expect(page.locator('body')).toBeVisible();
    await expect(page.getByText(/Application error|Uncaught|TypeError|ReferenceError/i)).toHaveCount(0);
    await expect(page.getByRole('button', { name: 'Terug' })).toHaveCount(0);
    await expect(page.getByRole('button', { name: 'Vernieuwen' })).toHaveCount(0);

    const receiptTable = page.getByTestId('external-receipt-items-table');
    await expect(receiptTable).toBeVisible();

    const receiptRow = receiptTable.locator('tbody tr', { hasText: 'halfvolle melk' });
    await expect(receiptRow).toBeVisible();
    await receiptRow.dblclick();

    const candidateTable = page.getByTestId('external-receipt-item-candidates-table');
    await expect(candidateTable).toBeVisible();
    await expect(page.getByRole('button', { name: 'Zelf zoeken' })).toBeVisible();
    await expect(page.getByLabel('OFF zoektekst')).toHaveValue('halfvolle melk');

    await expect(page.getByTestId('external-off-preview-meta')).toContainText('OFF-status: Gevonden');
    await expect(page.getByTestId('external-off-preview-meta')).toContainText('Provider: legacy_cgi');
    await expect(page.getByTestId('external-off-preview-meta')).toContainText('Zoektype: automatisch');
    await expect(page.getByTestId('external-off-preview-meta')).toContainText('Productmutatie: nee');

    const automaticRow = candidateTable.locator('tbody tr', { hasText: '8710000000002' });
    await expect(automaticRow).toBeVisible();
    await expect(automaticRow.getByRole('cell', { name: 'Halfvolle melk', exact: true })).toBeVisible();
    await expect(automaticRow.getByRole('cell', { name: '0,930', exact: true })).toBeVisible();

    await page.getByLabel('OFF zoektekst').fill('melk halfvol zelf zoeken');
    await page.getByRole('button', { name: 'Zelf zoeken' }).click();

    await expect(page.getByTestId('external-off-preview-meta')).toContainText('Zoektype: handmatig');
    await expect(page.getByTestId('external-off-preview-meta')).toContainText('Zoektekst: melk halfvol zelf zoeken');
    await expect(candidateTable.locator('tbody tr', { hasText: '8710000000099' })).toBeVisible();
    await expect(candidateTable.locator('tbody tr', { hasText: '8710000000002' })).toHaveCount(0);

    expect(offRequestBodies).toHaveLength(2);
    expect(offRequestBodies[0]).toEqual({
      receipt_item_id: 'purchase-import-line:purchase-line-off-preview-regression',
      mode: 'automatic',
      limit: 10,
    });
    expect(offRequestBodies[1]).toEqual({
      receipt_item_id: 'purchase-import-line:purchase-line-off-preview-regression',
      query: 'melk halfvol zelf zoeken',
      mode: 'manual',
      limit: 10,
    });

    await expect(page.getByTestId('external-producttype-link-panel')).toBeVisible();
    await expect(page.getByRole('button', { name: 'Koppel artikel en Producttype', exact: true })).toBeDisabled();
    await expect(page.getByRole('button', { name: 'Ontkoppel artikel', exact: true })).toBeDisabled();
    await expectNoConsoleErrors(consoleErrors);
  });

  test('Langdurige OFF-zoekactie toont na één seconde de blokkerende R en verwijdert die direct na een fout', async ({ page }) => {
    const consoleErrors = attachConsoleErrorCollector(page);
    let releaseSearch;
    const searchGate = new Promise((resolve) => {
      releaseSearch = resolve;
    });

    await page.route('**/api/external-databases/receipt-items?limit=500', async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify(receiptItemsPayload()),
      });
    });

    await page.route('**/api/external-products/off/search', async (route) => {
      await searchGate;
      await route.fulfill({
        status: 503,
        contentType: 'application/json',
        body: JSON.stringify({ detail: 'OFF regressiestoring' }),
      });
    });

    await page.goto('/externe-databases');

    const receiptTable = page.getByTestId('external-receipt-items-table');
    const receiptRow = receiptTable.locator('tbody tr', { hasText: 'halfvolle melk' });
    await expect(receiptRow).toBeVisible();

    await receiptRow.dblclick();

    const overlay = page.getByRole('status', { name: 'Zoekactie wordt uitgevoerd' });
    await expect(overlay).toHaveCount(0);

    await page.waitForTimeout(1100);
    await expect(overlay).toBeVisible();
    await expect(overlay).toHaveAttribute('aria-busy', 'true');
    await expect(overlay.getByText('R', { exact: true })).toBeVisible();
    await expect(overlay.getByText('Zoekactie wordt uitgevoerd', { exact: true })).toBeVisible();

    releaseSearch();

    await expect(overlay).toHaveCount(0);
    await expect(page.getByText('OFF regressiestoring', { exact: true })).toBeVisible();
    await expect(page.getByRole('button', { name: 'Zelf zoeken' })).toBeEnabled();
    await expect(page.getByRole('button', { name: 'Koppel artikel en Producttype', exact: true })).toBeDisabled();
    await expect(page.getByRole('button', { name: 'Ontkoppel artikel', exact: true })).toBeDisabled();

    const unexpectedConsoleErrors = consoleErrors.filter(
      (message) => !message.includes('Failed to load resource: the server responded with a status of 503'),
    );
    expect(unexpectedConsoleErrors).toEqual([]);
  });

  test('Gekoppelde bonartikelregel toont score, artikel, Producttype en definitieve GTIN', async ({ page }) => {
    const consoleErrors = attachConsoleErrorCollector(page);

    await page.route('**/api/external-databases/receipt-items?limit=500', async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          items: [
            {
              receipt_item_id: 'purchase-import-line:linked-banana-regression',
              receipt_item_type: 'purchase_import_line',
              receipt_item_source_id: 'linked-banana-regression',
              context_key: 'ctx-linked-banana-regression',
              purchase_import_line_id: 'linked-banana-regression',
              receipt_line_text: 'AH BANANEN',
              retailer_code: 'ah',
              retailer_article_number: '',
              gtin: '',
              quantity_label: '1 stuk',
              price: 1.99,
              candidate_status: 'linked_to_catalog',
              status: 'linked_to_catalog',
              global_product_id: 'e9cc7c77-c201-4295-b125-c88a23c88ca2',
              canonical_catalog_product_id: 'e9cc7c77-c201-4295-b125-c88a23c88ca2',
              is_receipt_item_placeholder: true,
              is_linked_to_catalog: true,
              is_existing_link_for_receipt_item: true,
              is_linkable_to_catalog: false,
              linked_candidate_name: 'Bananen',
              linked_product_type_id: 'gpc:10005897',
              linked_product_type: 'Bananen (Cavendish)',
              linked_gtin: '8718265184886',
              linked_score: 0.691,
              candidates: [],
            },
          ],
        }),
      });
    });

    await page.route('**/api/inventory/groups', async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({ group_options: [{ inventory_group_key: 'gpc:10005897', display_name: 'Bananen (Cavendish)', default_base_unit: 'stuk' }] }),
      });
    });

    await page.goto('/externe-databases');

    const receiptTable = page.getByTestId('external-receipt-items-table');
    await expect(receiptTable).toBeVisible();

    const headers = receiptTable.locator('thead tr').first().locator('th');
    await expect(headers.nth(3)).toContainText('Catalogus');
    await expect(headers.nth(4)).toContainText('Score');
    await expect(headers.nth(5)).toContainText('(Kand.) artikel');
    await expect(headers.nth(6)).toContainText('Producttype');
    await expect(headers.nth(7)).toContainText('(Kand.) GTIN/EAN');

    const receiptRow = receiptTable.locator('tbody tr', { hasText: 'AH BANANEN' });
    await expect(receiptRow).toBeVisible();
    await expect(receiptRow.locator('td').nth(3).getByRole('checkbox')).toBeChecked();
    await expect(receiptRow.locator('td').nth(4)).toHaveText('0,691');
    await expect(receiptRow.locator('td').nth(5)).toHaveText('Bananen');
    await expect(receiptRow.locator('td').nth(6)).toHaveText('Bananen (Cavendish)');
    await expect(receiptRow.locator('td').nth(7)).toHaveText('8718265184886');

    await receiptRow.dblclick();

    const candidateTable = page.getByTestId('external-receipt-item-candidates-table');
    const linkedCandidateRow = candidateTable.locator('tbody tr', { hasText: 'Bananen' });
    await expect(linkedCandidateRow).toBeVisible();
    await expect(linkedCandidateRow.locator('td').nth(1)).toHaveText('Bananen');
    await expect(linkedCandidateRow.locator('td').nth(3)).toHaveText('Artikelcatalogus');
    await expect(linkedCandidateRow.locator('td').nth(4)).toHaveText('8718265184886');
    await expect(linkedCandidateRow.locator('td').nth(5)).toHaveText('0,691');
    await expect(linkedCandidateRow.locator('td').nth(6)).toHaveText('Gekoppeld');
    await expect(linkedCandidateRow.getByRole('radio')).toBeChecked();

    await expect(page.getByLabel('Producttype')).toHaveValue('gpc:10005897');

    await expectNoConsoleErrors(consoleErrors);
  });

  // OFF_ZOEKOVERLAY_REGRESSIETEST_INGEVOERD

});
