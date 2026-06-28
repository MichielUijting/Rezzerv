import { test, expect } from '@playwright/test';
import {
  attachConsoleErrorCollector,
  expectNoConsoleErrors,
  expectRouteLoads,
} from './helpers/rezzervAssertions.js';

test.describe('Externe databases OFF read-only preview', () => {
  test('Raadpleeg OFF toont kandidaten zonder koppelbare mutatie', async ({ page }) => {
    const consoleErrors = attachConsoleErrorCollector(page);

    await page.route('**/api/external-databases/receipt-items?limit=500', async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          items: [
            {
              context_key: 'ctx-off-preview-regression',
              receipt_line_id: 'receipt-line-off-preview-regression',
              purchase_import_line_id: 'purchase-line-off-preview-regression',
              receipt_line_text: 'halfvolle melk',
              retailer_code: 'jumbo',
              retailer_article_number: '',
              gtin: '',
              quantity_label: '1 l',
              price: 1.29,
              candidate_id: 'candidate-off-preview-existing',
              candidate_name: 'Halfvolle melk',
              candidate_brand: 'Jumbo',
              external_source_name: 'Open Food Facts',
              external_source_product_code: '8710000000000',
              variant: 'Standaard',
              score: 0.7,
              candidate_status: 'candidate',
              is_linked_to_catalog: false,
              is_linkable_to_catalog: true,
            },
          ],
        }),
      });
    });

    await page.route('**/api/external-databases/receipt-items/ensure-candidates', async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({ status: 'ok' }),
      });
    });

    let offRequestBody = null;
    await page.route('**/api/external-databases/off/search-preview', async (route) => {
      offRequestBody = route.request().postDataJSON();
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          ok: true,
          source_name: 'open_food_facts',
          mode: 'read_only_search_preview',
          status: 'found',
          external_source_available: true,
          provider: 'search_a_licious',
          providers_used: ['search_a_licious'],
          receipt_line_text: 'halfvolle melk',
          retailer_code: 'jumbo',
          queried_terms: ['halfvolle melk 1 l'],
          query_limit: 1,
          timeout_seconds: 8,
          results: [
            {
              source_name: 'open_food_facts',
              source_product_code: '8710000000002',
              candidate_source_product_code: '8710000000002',
              code: '8710000000002',
              gtin: '8710000000002',
              ean: '8710000000002',
              barcode: '8710000000002',
              product_name: 'Halfvolle melk',
              candidate_name: 'Halfvolle melk',
              brands: 'Jumbo',
              candidate_brand: 'Jumbo',
              quantity: '1 l',
              quantity_label: '1 l',
              score: 0.82,
              candidate_status: 'off_candidate',
              requires_user_selection: true,
              creates_global_product: false,
              creates_household_article: false,
              creates_inventory_event: false,
            },
          ],
          result_count: 1,
          diagnostics: [{ search_term: 'halfvolle melk 1 l', provider: 'search_a_licious', http_status: 200, raw_count: 1 }],
          errors: [],
          requires_user_selection: true,
          creates_global_product: false,
          creates_household_article: false,
          creates_inventory_event: false,
        }),
      });
    });

    await expectRouteLoads(page, '/externe-databases', [
      'Externe databases',
      'Bonartikelen',
      'Kandidaten',
      'Product',
    ]);

    const receiptTable = page.getByTestId('external-receipt-items-table');
    await expect(receiptTable).toBeVisible();

    const receiptRow = receiptTable.locator('tbody tr', { hasText: 'halfvolle melk' });
    await expect(receiptRow).toBeVisible();
    await receiptRow.dblclick();

    await expect(page.getByText('Koppelen kandidaten in artikel-catalogus')).toBeVisible();
    await page.getByRole('button', { name: 'Raadpleeg OFF' }).click();

    await expect(page.getByTestId('external-off-preview-meta')).toContainText('OFF-status: Gevonden');
    await expect(page.getByTestId('external-off-preview-meta')).toContainText('Provider: search_a_licious');
    await expect(page.getByTestId('external-off-preview-meta')).toContainText('Productmutatie: nee');

    const offTable = page.getByTestId('external-off-candidates-table');
    await expect(offTable).toBeVisible();
    await expect(offTable.getByText('Halfvolle melk')).toBeVisible();
    await expect(offTable.getByText('8710000000002')).toBeVisible();
    await expect(offTable.getByText('Alleen raadplegen')).toBeVisible();

    await expect(page.getByRole('button', { name: 'Koppel artikel' })).toBeDisabled();
    expect(offRequestBody).toMatchObject({
      receipt_line_text: 'halfvolle melk',
      retailer_code: 'jumbo',
      candidate_name: 'Halfvolle melk',
      quantity_label: '1 l',
      limit: 5,
    });

    await expectNoConsoleErrors(consoleErrors);
  });
});
