import { test, expect } from '@playwright/test';
import {
  attachConsoleErrorCollector,
  expectNoConsoleErrors,
  expectRouteLoads,
} from './helpers/rezzervAssertions.js';

test.describe('Externe databases ontkoppelen regressie', () => {
  test('Bestaande cataloguskoppeling wordt niet vermengd met tijdelijke OFF-zoekresultaten', async ({ page }) => {
    const consoleErrors = attachConsoleErrorCollector(page);
    const offRequestBodies = [];
    let unlinkCalled = false;

    await page.route('**/api/external-databases/receipt-items?limit=500', async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          items: [
            {
              receipt_item_id: 'purchase-import-line:purchase-line-unlink-regression',
              receipt_item_type: 'purchase_import_line',
              receipt_item_source_id: 'purchase-line-unlink-regression',
              context_key: 'ctx-unlink-regression',
              receipt_line_id: 'receipt-line-unlink-regression',
              purchase_import_line_id: 'purchase-line-unlink-regression',
              receipt_line_text: 'Ontkoppel kandidaat regressietest',
              retailer_code: 'lidl',
              retailer_article_number: 'LIDL-LINKED',
              gtin: '',
              quantity_label: '1 stuk',
              price: 1.23,
              candidate_id: 'candidate-linked-unlink-regression',
              id: 'candidate-linked-unlink-regression',
              candidate_name: 'Gekoppelde ontkoppel kandidaat',
              candidate_brand: 'Testmerk',
              external_source_name: 'Open Food Facts',
              candidate_source_name: 'Open Food Facts',
              external_source_product_code: '8710000007777',
              candidate_source_product_code: '8710000007777',
              source_product_code: '8710000007777',
              variant: 'Standaard',
              score: 0.8,
              candidate_status: 'linked_to_catalog',
              is_linked_to_catalog: true,
              is_linkable_to_catalog: false,
              central_link_active: true,
              global_product_id: 'gp-unlink-regression',
              linked_candidate_name: 'Gekoppelde ontkoppel kandidaat',
              linked_product_type_id: 'gpc:unlink-regression',
              linked_product_type: 'Ontkoppel Producttype',
              linked_gtin: '8710000007777',
              linked_score: 0.8,
            },
          ],
        }),
      });
    });

    await page.route('**/api/external-products/off/search', async (route) => {
      offRequestBodies.push(route.request().postDataJSON());
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          ok: true,
          status: 'no_results',
          provider: 'legacy_cgi',
          query: 'ontkoppel kandidaat regressietest',
          mode: 'automatic',
          mutated: false,
          results: [],
          creates_global_product: false,
          creates_household_article: false,
          creates_inventory_event: false,
        }),
      });
    });

    await page.route('**/api/external-databases/catalog/unlink', async (route) => {
      unlinkCalled = true;
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({ status: 'ok', unlinked_count: 1 }),
      });
    });

    await expectRouteLoads(page, '/externe-databases', [
      'Externe databases',
      'Bonartikelen',
      'Kandidaten',
      'Product',
    ]);

    const receiptTable = page.getByTestId('external-receipt-items-table');
    const receiptRow = receiptTable.locator('tbody tr', { hasText: 'Ontkoppel kandidaat regressietest' });
    await expect(receiptRow).toBeVisible();
    await expect(receiptRow.locator('td').nth(3).locator('input')).toBeChecked();

    await receiptRow.dblclick();

    const candidateTable = page.getByTestId('external-receipt-item-candidates-table');
    await expect(candidateTable).toBeVisible();
    await expect(candidateTable.getByText('Gekoppelde ontkoppel kandidaat')).toBeVisible();
    await expect(candidateTable.getByText('Artikelcatalogus')).toBeVisible();
    await expect(candidateTable.getByText('8710000007777')).toBeVisible();
    await expect(page.getByRole('button', { name: 'Ontkoppel artikel', exact: true })).toBeDisabled();

    expect(offRequestBodies).toEqual([]);
    expect(unlinkCalled).toBe(false);

    await expectNoConsoleErrors(consoleErrors);
  });
});
