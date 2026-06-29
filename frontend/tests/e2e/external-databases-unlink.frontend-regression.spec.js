import { test, expect } from '@playwright/test';
import {
  attachConsoleErrorCollector,
  expectNoConsoleErrors,
  expectRouteLoads,
} from './helpers/rezzervAssertions.js';

function receiptItemsPayload(isLinked = true) {
  return {
    items: [
      {
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
        external_source_product_code: 'LIDL-LINKED',
        candidate_source_product_code: 'LIDL-LINKED',
        source_product_code: 'LIDL-LINKED',
        variant: 'Standaard',
        score: 0.8,
        candidate_status: isLinked ? 'linked_to_catalog' : 'candidate',
        is_linked_to_catalog: isLinked,
        is_linkable_to_catalog: !isLinked,
      },
    ],
  };
}

test.describe('Externe databases ontkoppelen regressie', () => {
  test('Gekoppelde kandidaat kan vanuit detailscherm worden ontkoppeld', async ({ page }) => {
    const consoleErrors = attachConsoleErrorCollector(page);
    let linked = true;
    let unlinkRequestBody = null;

    await page.route('**/api/external-databases/receipt-items?limit=500', async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify(receiptItemsPayload(linked)),
      });
    });

    await page.route('**/api/external-databases/off/save-candidates', async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          ok: true,
          preview: {
            ok: true,
            status: 'no_results',
            provider: 'search_a_licious',
            creates_global_product: false,
            creates_household_article: false,
            creates_inventory_event: false,
          },
        }),
      });
    });

    await page.route('**/api/external-databases/catalog/unlink', async (route) => {
      unlinkRequestBody = route.request().postDataJSON();
      linked = false;
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
    await expect(receiptTable).toBeVisible();

    const receiptRow = receiptTable.locator('tbody tr', { hasText: 'Ontkoppel kandidaat regressietest' });
    await expect(receiptRow).toBeVisible();
    await expect(receiptRow.locator('td').nth(3).locator('input')).toBeChecked();
    await receiptRow.dblclick();

    const candidateTable = page.getByTestId('external-receipt-item-candidates-table');
    await expect(candidateTable).toBeVisible();

    const linkedCandidateRow = candidateTable.locator('tbody tr', { hasText: 'Gekoppelde ontkoppel kandidaat' });
    await expect(linkedCandidateRow).toBeVisible();
    await expect(linkedCandidateRow).toContainText('Gekoppeld');
    await linkedCandidateRow.locator('input[type="radio"]').check();

    await expect(page.getByRole('button', { name: 'Koppel artikel' })).toBeDisabled();
    await expect(page.getByRole('button', { name: 'Ontkoppel artikel' })).toBeEnabled();
    await page.getByRole('button', { name: 'Ontkoppel artikel' }).click();

    expect(unlinkRequestBody).toMatchObject({
      context_keys: ['ctx-unlink-regression'],
      candidate_ids: ['candidate-linked-unlink-regression'],
    });

    await expect(receiptTable.locator('tbody tr', { hasText: 'Ontkoppel kandidaat regressietest' }).locator('td').nth(3).locator('input')).not.toBeChecked();
    await expectNoConsoleErrors(consoleErrors);
  });
});
