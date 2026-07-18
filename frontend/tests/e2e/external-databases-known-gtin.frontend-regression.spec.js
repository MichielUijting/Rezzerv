import { test, expect } from '@playwright/test';
import {
  attachConsoleErrorCollector,
  expectNoConsoleErrors,
  expectRouteLoads,
} from './helpers/rezzervAssertions.js';

test.describe('Externe databases bekende GTIN regressie', () => {
  test('Bonartikel met bestaande GTIN behoudt artikelcode en start geen OFF-zoekactie', async ({ page }) => {
    const consoleErrors = attachConsoleErrorCollector(page);
    let offSearchCalled = false;

    await page.route('**/api/external-databases/receipt-items?limit=500', async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          items: [
            {
              receipt_item_id: 'purchase-import-line:purchase-line-known-gtin-regression',
              receipt_item_type: 'purchase_import_line',
              receipt_item_source_id: 'purchase-line-known-gtin-regression',
              context_key: 'ctx-known-gtin-regression',
              receipt_line_id: 'receipt-line-known-gtin-regression',
              purchase_import_line_id: 'purchase-line-known-gtin-regression',
              receipt_line_text: 'Bekende GTIN regressietest',
              retailer_code: 'lidl',
              retailer_article_number: '8710000001234',
              gtin: '8710000001234',
              quantity_label: '1 stuk',
              price: 1.23,
              is_receipt_item_placeholder: true,
              candidates: [
                {
                  candidate_id: 'candidate-should-be-ignored-for-known-gtin',
                  id: 'candidate-should-be-ignored-for-known-gtin',
                  candidate_name: 'Onterechte kandidaat',
                  candidate_brand: 'Testmerk',
                  external_source_name: 'Open Food Facts',
                  candidate_source_name: 'Open Food Facts',
                  external_source_product_code: '9999999999999',
                  candidate_source_product_code: '9999999999999',
                  source_product_code: '9999999999999',
                  variant: 'Standaard',
                  score: 0.99,
                  candidate_status: 'candidate',
                  is_linked_to_catalog: false,
                  is_linkable_to_catalog: true,
                },
              ],
            },
          ],
        }),
      });
    });

    await page.route('**/api/external-products/off/search', async (route) => {
      offSearchCalled = true;
      await route.fulfill({
        status: 500,
        contentType: 'application/json',
        body: JSON.stringify({ detail: 'OFF mocht niet worden aangeroepen voor bekende GTIN' }),
      });
    });

    await expectRouteLoads(page, '/externe-databases', [
      'Externe databases',
      'Bonartikelen',
      'Kandidaten',
      'Product',
    ]);

    const receiptTable = page.getByTestId('external-receipt-items-table');
    const receiptRow = receiptTable.locator('tbody tr', { hasText: 'Bekende GTIN regressietest' });
    await expect(receiptRow).toBeVisible();
    await expect(receiptRow.locator('td').nth(4)).toHaveText('-');
    await expect(receiptRow.locator('td').nth(5)).toHaveText('8710000001234');
    await expect(receiptRow.locator('td').nth(8)).toHaveText('-');
    await expect(receiptRow.locator('td').nth(9)).toHaveText('-');
    await expect(receiptRow.locator('td').nth(10)).toHaveText('0');

    await receiptRow.dblclick();

    const candidateTable = page.getByTestId('external-receipt-item-candidates-table');
    await expect(candidateTable).toBeVisible();
    await expect(candidateTable).toContainText('Geen universele kandidaten met score 0,500 of hoger voor dit bonartikel.');
    await expect(candidateTable.getByText('Onterechte kandidaat')).toHaveCount(0);
    await expect(page.getByText('GTIN/EAN is al bekend; OFF-kandidaten worden niet automatisch toegevoegd.')).toBeVisible();
    await expect(page.getByRole('button', { name: 'Koppel artikel', exact: true })).toBeDisabled();
    await expect(page.getByRole('button', { name: 'Ontkoppel artikel', exact: true })).toBeDisabled();
    expect(offSearchCalled).toBe(false);

    await expectNoConsoleErrors(consoleErrors);
  });
});
