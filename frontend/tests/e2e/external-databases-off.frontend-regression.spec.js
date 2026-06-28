import { test, expect } from '@playwright/test';
import {
  attachConsoleErrorCollector,
  expectNoConsoleErrors,
  expectRouteLoads,
} from './helpers/rezzervAssertions.js';

function receiptItemsPayload(includeOffCandidate = false) {
  const candidates = [
    {
      candidate_id: 'candidate-off-preview-existing',
      id: 'candidate-off-preview-existing',
      candidate_name: 'Halfvolle melk bestaand',
      candidate_brand: 'Jumbo',
      external_source_name: 'Open Food Facts',
      candidate_source_name: 'Open Food Facts',
      external_source_product_code: '8710000000000',
      candidate_source_product_code: '8710000000000',
      source_product_code: '8710000000000',
      retailer_article_number: '8710000000000',
      variant: 'Standaard',
      score: 0.7,
      candidate_status: 'candidate',
      is_linked_to_catalog: false,
      is_linkable_to_catalog: true,
    },
  ];

  if (includeOffCandidate) {
    candidates.push({
      candidate_id: 'candidate-off-saved-best',
      id: 'candidate-off-saved-best',
      candidate_name: 'Halfvolle melk',
      candidate_brand: 'Jumbo',
      external_source_name: 'Open Food Facts',
      candidate_source_name: 'Open Food Facts',
      external_source_product_code: '8710000000002',
      candidate_source_product_code: '8710000000002',
      source_product_code: '8710000000002',
      retailer_article_number: '8710000000002',
      quantity_label: '1 l',
      variant: '1 l',
      score: 0.82,
      candidate_status: 'candidate',
      is_linked_to_catalog: false,
      is_linkable_to_catalog: true,
    });
  }

  return {
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
        candidates,
      },
    ],
  };
}

test.describe('Externe databases OFF candidate flow', () => {
  test('Raadpleeg OFF noteert kandidaten in onderste tabel voor expliciet koppelen', async ({ page }) => {
    const consoleErrors = attachConsoleErrorCollector(page);
    let includeOffCandidate = false;

    await page.route('**/api/external-databases/receipt-items?limit=500', async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify(receiptItemsPayload(includeOffCandidate)),
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
    await page.route('**/api/external-databases/off/save-candidates', async (route) => {
      offRequestBody = route.request().postDataJSON();
      includeOffCandidate = true;
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          ok: true,
          source_name: 'open_food_facts',
          context_key: 'ctx-off-preview-regression',
          retailer_code: 'jumbo',
          receipt_line_text: 'halfvolle melk',
          candidate_count: 1,
          saved_count: 1,
          updated_count: 0,
          skipped_count: 0,
          saved_candidate_ids: ['candidate-off-saved-best'],
          updated_candidate_ids: [],
          preview: {
            ok: true,
            source_name: 'open_food_facts',
            mode: 'read_only_search_preview',
            status: 'found',
            external_source_available: true,
            provider: 'search_a_licious',
            result_count: 1,
            creates_global_product: false,
            creates_household_article: false,
            creates_inventory_event: false,
          },
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

    const candidateTable = page.getByTestId('external-receipt-item-candidates-table');
    await expect(candidateTable).toBeVisible();
    await expect(candidateTable.getByText('Halfvolle melk bestaand')).toBeVisible();
    await expect(candidateTable.getByText('8710000000002')).toHaveCount(0);

    await page.getByRole('button', { name: 'Raadpleeg OFF' }).click();

    await expect(page.getByTestId('external-off-preview-meta')).toContainText('OFF-status: Gevonden');
    await expect(page.getByTestId('external-off-preview-meta')).toContainText('Provider: search_a_licious');
    await expect(page.getByTestId('external-off-preview-meta')).toContainText('Productmutatie: nee');

    await expect(candidateTable.getByText('Halfvolle melk')).toBeVisible();
    await expect(candidateTable.getByText('8710000000002')).toBeVisible();
    await expect(page.getByTestId('external-off-candidates-table')).toHaveCount(0);

    const offCandidateRow = candidateTable.locator('tbody tr', { hasText: '8710000000002' });
    await expect(offCandidateRow).toBeVisible();
    await offCandidateRow.locator('input[type="radio"]').check();
    await expect(page.getByRole('button', { name: 'Koppel artikel' })).toBeEnabled();

    expect(offRequestBody).toMatchObject({
      receipt_line_text: 'halfvolle melk',
      retailer_code: 'jumbo',
      candidate_name: 'Halfvolle melk bestaand',
      quantity_label: '1 l',
      receipt_line_id: 'receipt-line-off-preview-regression',
      purchase_import_line_id: 'purchase-line-off-preview-regression',
      limit: 5,
    });

    await expectNoConsoleErrors(consoleErrors);
  });
});
