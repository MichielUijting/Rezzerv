import { test, expect } from '@playwright/test';
import {
  attachConsoleErrorCollector,
  expectAnyVisible,
  expectNoConsoleErrors,
  expectRouteLoads,
} from './helpers/rezzervAssertions.js';

test.describe('Externe databases frontend-regressie', () => {
  test('Externe databases scherm laadt en behoudt bonartikelen-overzicht', async ({ page }) => {
    const consoleErrors = attachConsoleErrorCollector(page);

    await expectRouteLoads(page, '/externe-databases', [
      'Externe databases',
      'Open Food Facts',
      'Bonartikelen',
      'Kandidaten',
      'Product',
    ]);

    await expectAnyVisible(page, [
      'Externe databases',
      'Open Food Facts',
      'Bonartikelen',
      'Kandidaten',
      'Product',
    ], 'Externe databases kernlabels');

    await expect(page.getByText('Lidl-kandidaatpreview')).toHaveCount(0);
    await expect(page.getByRole('button', { name: 'Test kandidaat' })).toHaveCount(0);

    const receiptTable = page.getByTestId('external-receipt-items-table');
    await expect(receiptTable).toBeVisible();

    const rowWithCandidates = receiptTable.locator('tbody tr').filter({ hasText: /\b[1-9]\d*$/ }).first();
    await expect(rowWithCandidates).toBeVisible();
    await rowWithCandidates.dblclick();

    await expect(page.getByText('Koppelen kandidaten in artikel-catalogus')).toBeVisible();
    await expect(page.getByTestId('external-receipt-item-candidates-table')).toBeVisible();

    await expect(page.getByText(/Application error|Uncaught|TypeError|ReferenceError/i)).toHaveCount(0);
    await expectNoConsoleErrors(consoleErrors);
  });
  test('Kandidatenlijst ondertabel ontdubbelt dubbele externe kandidaten', async ({ page }) => {
    const consoleErrors = attachConsoleErrorCollector(page);

    await page.route('**/api/external-databases/receipt-items?limit=500', async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          items: [
            {
              context_key: 'ctx-dedupe-regression',
              receipt_line_id: 'receipt-line-dedupe-regression',
              purchase_import_line_id: 'purchase-line-dedupe-regression',
              receipt_line_text: 'Dubbele kandidaat regressietest',
              retailer_code: 'lidl',
              retailer_article_number: '12345',
              gtin: '8710000000001',
              quantity_label: '1 stuk',
              price: 1.23,
              candidate_id: 'candidate-low-score',
              candidate_name: 'Rezzerv Test Mosterd',
              candidate_brand: 'Testmerk',
              external_source_name: 'Open Food Facts',
              external_source_product_code: '8710000000001',
              variant: 'Standaard',
              score: 0.4,
              candidate_status: 'candidate',
              is_linked_to_catalog: false,
              is_linkable_to_catalog: true,
            },
            {
              context_key: 'ctx-dedupe-regression',
              receipt_line_id: 'receipt-line-dedupe-regression',
              purchase_import_line_id: 'purchase-line-dedupe-regression',
              receipt_line_text: 'Dubbele kandidaat regressietest',
              retailer_code: 'lidl',
              retailer_article_number: '12345',
              gtin: '8710000000001',
              quantity_label: '1 stuk',
              price: 1.23,
              candidate_id: 'candidate-high-score',
              candidate_name: 'Rezzerv Test Mosterd',
              candidate_brand: 'Testmerk',
              external_source_name: 'Open Food Facts',
              external_source_product_code: '8710000000001',
              variant: 'Standaard',
              score: 0.8,
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

    await expectRouteLoads(page, '/externe-databases', [
      'Externe databases',
      'Bonartikelen',
      'Kandidaten',
      'Product',
    ]);

    const receiptTable = page.getByTestId('external-receipt-items-table');
    await expect(receiptTable).toBeVisible();

    await receiptTable.locator('tbody tr', { hasText: 'Dubbele kandidaat regressietest' }).dblclick();

    const candidateTable = page.getByTestId('external-receipt-item-candidates-table');
    await expect(candidateTable).toBeVisible();

    const candidateRows = candidateTable.locator('tbody tr').filter({
      has: page.locator('input[type="radio"]'),
    });

    await expect(candidateRows).toHaveCount(1);
    await expect(candidateTable.getByText('0,800')).toBeVisible();
    await expect(candidateTable.getByText('0,400')).toHaveCount(0);

    await expectNoConsoleErrors(consoleErrors);
  });
});
