import { test, expect } from '@playwright/test';
import {
  attachConsoleErrorCollector,
  expectNoConsoleErrors,
} from './helpers/rezzervAssertions.js';

function receiptItemsPayload(includeOffCandidate = false, manualCandidate = false) {
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
      candidate_id: manualCandidate ? 'candidate-off-manual-best' : 'candidate-off-saved-best',
      id: manualCandidate ? 'candidate-off-manual-best' : 'candidate-off-saved-best',
      candidate_name: manualCandidate ? 'Melk halfvol handmatig' : 'Halfvolle melk',
      candidate_brand: 'Jumbo',
      external_source_name: 'Open Food Facts',
      candidate_source_name: 'Open Food Facts',
      external_source_product_code: manualCandidate ? '8710000000099' : '8710000000002',
      candidate_source_product_code: manualCandidate ? '8710000000099' : '8710000000002',
      source_product_code: manualCandidate ? '8710000000099' : '8710000000002',
      retailer_article_number: manualCandidate ? '8710000000099' : '8710000000002',
      quantity_label: '1 l',
      variant: '1 l',
      score: manualCandidate ? 0.91 : 0.82,
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
  test('Detail openen raadpleegt OFF automatisch en Zelf zoeken zoekt opnieuw met aangepaste tekst', async ({ page }) => {
    const consoleErrors = attachConsoleErrorCollector(page);
    let includeOffCandidate = false;
    let manualCandidate = false;
    const offRequestBodies = [];

    await page.route('**/api/external-databases/receipt-items?limit=500', async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify(receiptItemsPayload(includeOffCandidate, manualCandidate)),
      });
    });

    await page.route('**/api/external-databases/receipt-items/ensure-candidates', async (route) => {
      await route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({ status: 'ok' }) });
    });

    await page.route('**/api/external-databases/off/save-candidates', async (route) => {
      const body = route.request().postDataJSON();
      offRequestBodies.push(body);
      includeOffCandidate = true;
      manualCandidate = body?.candidate_name === 'melk halfvol zelf zoeken';
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
          saved_candidate_ids: [manualCandidate ? 'candidate-off-manual-best' : 'candidate-off-saved-best'],
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

    await page.goto('/externe-databases');
    await expect(page.locator('body')).toBeVisible();
    await expect(page.getByText(/Application error|Uncaught|TypeError|ReferenceError/i)).toHaveCount(0);

    const receiptTable = page.getByTestId('external-receipt-items-table');
    await expect(receiptTable).toBeVisible();

    const receiptRow = receiptTable.locator('tbody tr', { hasText: 'halfvolle melk' });
    await expect(receiptRow).toBeVisible();
    await receiptRow.dblclick();

    const candidateTable = page.getByTestId('external-receipt-item-candidates-table');
    await expect(candidateTable).toBeVisible();
    await expect(page.getByRole('button', { name: 'Raadpleeg OFF' })).toHaveCount(0);
    await expect(page.getByRole('button', { name: 'Zelf zoeken' })).toBeVisible();
    await expect(page.getByLabel('OFF zoektekst')).toHaveValue('Halfvolle melk bestaand');

    await expect(page.getByTestId('external-off-preview-meta')).toContainText('OFF-status: Gevonden');
    await expect(page.getByTestId('external-off-preview-meta')).toContainText('Provider: search_a_licious');
    await expect(page.getByTestId('external-off-preview-meta')).toContainText('Productmutatie: nee');

    const offCandidateRow = candidateTable.locator('tbody tr', { hasText: '8710000000002' });
    await expect(offCandidateRow).toBeVisible();
    await expect(offCandidateRow.getByRole('cell', { name: 'Halfvolle melk', exact: true })).toBeVisible();
    await expect(offCandidateRow.getByRole('cell', { name: '8710000000002', exact: true })).toBeVisible();
    await expect(page.getByTestId('external-off-candidates-table')).toHaveCount(0);

    await page.getByLabel('OFF zoektekst').fill('melk halfvol zelf zoeken');
    await page.getByRole('button', { name: 'Zelf zoeken' }).click();
    await expect(page.getByTestId('external-off-preview-meta')).toContainText('Zoektype: handmatig');
    await expect(page.getByTestId('external-off-preview-meta')).toContainText('Zoektekst: melk halfvol zelf zoeken');
    await expect(candidateTable.locator('tbody tr', { hasText: '8710000000099' })).toBeVisible();

    const manualCandidateRow = candidateTable.locator('tbody tr', { hasText: '8710000000099' });
    await manualCandidateRow.locator('input[type="radio"]').check();
    await expect(page.getByRole('button', { name: 'Koppel artikel', exact: true })).toBeEnabled();

    expect(offRequestBodies[0]).toMatchObject({
      receipt_line_text: 'halfvolle melk',
      retailer_code: 'jumbo',
      candidate_name: 'Halfvolle melk bestaand',
      quantity_label: '1 l',
      receipt_line_id: 'receipt-line-off-preview-regression',
      purchase_import_line_id: 'purchase-line-off-preview-regression',
      limit: 5,
    });
    expect(offRequestBodies[1]).toMatchObject({
      receipt_line_text: 'halfvolle melk',
      retailer_code: 'jumbo',
      candidate_name: 'melk halfvol zelf zoeken',
      quantity_label: '1 l',
      receipt_line_id: 'receipt-line-off-preview-regression',
      purchase_import_line_id: 'purchase-line-off-preview-regression',
      limit: 5,
      source: 'manual_off_search',
    });

    await expectNoConsoleErrors(consoleErrors);
  });
});
