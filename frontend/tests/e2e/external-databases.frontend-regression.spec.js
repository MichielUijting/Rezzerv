import { test, expect } from '@playwright/test';
import {
  attachConsoleErrorCollector,
  expectAnyVisible,
  expectNoConsoleErrors,
  expectRouteLoads,
} from './helpers/rezzervAssertions.js';

async function routeReceiptItems(page, items) {
  await page.route('**/api/external-databases/receipt-items?limit=500', async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({ items }),
    });
  });
  await page.route('**/api/external-databases/receipt-items/ensure-candidates', async (route) => {
    await route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({ status: 'ok' }) });
  });
}

async function openExternalDatabases(page) {
  await expectRouteLoads(page, '/externe-databases', ['Externe databases', 'Bonartikelen', 'Kandidaten', 'Product']);
  const receiptTable = page.getByTestId('external-receipt-items-table');
  await expect(receiptTable).toBeVisible();
  return receiptTable;
}

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

    await expectAnyVisible(page, ['Externe databases', 'Open Food Facts', 'Bonartikelen', 'Kandidaten', 'Product'], 'Externe databases kernlabels');
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
    await routeReceiptItems(page, [
      {
        context_key: 'ctx-dedupe-regression',
        receipt_line_id: 'receipt-line-dedupe-regression',
        purchase_import_line_id: 'purchase-line-dedupe-regression',
        receipt_line_text: 'Dubbele kandidaat regressietest',
        retailer_code: 'lidl',
        retailer_article_number: '12345',
        gtin: '',
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
        gtin: '',
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
    ]);

    const receiptTable = await openExternalDatabases(page);
    const receiptRow = receiptTable.locator('tbody tr', { hasText: 'Dubbele kandidaat regressietest' });
    await expect(receiptRow).toBeVisible();
    await expect(receiptRow.locator('td').nth(4)).toHaveText('8710000000001');
    await expect(receiptRow.locator('td').nth(5)).toHaveText('-');
    await expect(receiptRow.locator('td').nth(9)).toContainText('Rezzerv Test Mosterd');
    await expect(receiptRow.locator('td').nth(10)).toContainText('0,800');

    await receiptRow.dblclick();
    const candidateTable = page.getByTestId('external-receipt-item-candidates-table');
    await expect(candidateTable).toBeVisible();
    await expect(candidateTable.locator('tbody tr').filter({ has: page.locator('input[type="radio"]') })).toHaveCount(1);
    await expect(candidateTable.getByText('0,800')).toBeVisible();
    await expect(candidateTable.getByText('0,400')).toHaveCount(0);
    await expectNoConsoleErrors(consoleErrors);
  });

  test('Bovenste tabel toont geen winkelspecifieke artikelcode als GTIN EAN', async ({ page }) => {
    const consoleErrors = attachConsoleErrorCollector(page);
    await routeReceiptItems(page, [{
      context_key: 'ctx-invalid-gtin-regression', receipt_line_id: 'receipt-line-invalid-gtin-regression', purchase_import_line_id: 'purchase-line-invalid-gtin-regression', receipt_line_text: 'Winkelspecifieke code regressietest', retailer_code: 'lidl', retailer_article_number: '12345', gtin: 'ART-8710000000001', quantity_label: '1 stuk', price: 1.23, candidate_id: 'candidate-invalid-gtin', candidate_name: 'Rezzerv Test Product', candidate_brand: 'Testmerk', external_source_name: 'Open Food Facts', external_source_product_code: 'LIDL-00999', variant: 'Standaard', score: 0.9, candidate_status: 'candidate', is_linked_to_catalog: false, is_linkable_to_catalog: true,
    }]);

    const receiptTable = await openExternalDatabases(page);
    const receiptRow = receiptTable.locator('tbody tr', { hasText: 'Winkelspecifieke code regressietest' });
    await expect(receiptRow).toBeVisible();
    await expect(receiptRow.locator('td').nth(4)).toHaveText('LIDL-00999');
    await expect(receiptRow.locator('td').nth(5)).toHaveText('-');
    await expect(receiptRow.locator('td').nth(9)).toContainText('Rezzerv Test Product');
    await expect(receiptRow.locator('td').nth(10)).toContainText('0,900');
    await expectNoConsoleErrors(consoleErrors);
  });

  test('Bovenste tabel gebruikt geen winkelketen-categorie pseudo-kandidaat als beste kandidaat', async ({ page }) => {
    const consoleErrors = attachConsoleErrorCollector(page);
    await routeReceiptItems(page, [
      { context_key: 'ctx-pseudo-code-regression', receipt_line_id: 'receipt-line-pseudo-code-regression', purchase_import_line_id: 'purchase-line-pseudo-code-regression', receipt_line_text: 'Pseudo artikelcode regressietest', retailer_code: 'lidl', retailer_article_number: 'lidl:groente.zoete-aardappel', source_product_code: 'lidl:groente.zoete-aardappel', candidate_source_product_code: 'lidl:groente.zoete-aardappel', gtin: '', quantity_label: '1 stuk', price: 1.23, candidate_id: 'candidate-retailer-pseudo', candidate_name: 'Lidl Zoete aardappel', candidate_brand: 'Lidl Groente', external_source_name: 'lidl_catalog_enrich', external_source_product_code: 'lidl:groente.zoete-aardappel', variant: 'Groente', score: 0.95, candidate_status: 'probable_candidate', is_linked_to_catalog: false, is_linkable_to_catalog: true },
      { context_key: 'ctx-pseudo-code-regression', receipt_line_id: 'receipt-line-pseudo-code-regression', purchase_import_line_id: 'purchase-line-pseudo-code-regression', receipt_line_text: 'Pseudo artikelcode regressietest', retailer_code: 'lidl', retailer_article_number: 'lidl:groente.zoete-aardappel', gtin: '', quantity_label: '1 stuk', price: 1.23, candidate_id: 'candidate-off-real', candidate_name: 'Zoete aardappel', candidate_brand: '-', external_source_name: 'Open Food Facts', external_source_product_code: '000426660609', variant: 'OFF', score: 0.642, candidate_status: 'candidate', is_linked_to_catalog: false, is_linkable_to_catalog: true },
    ]);

    const receiptTable = await openExternalDatabases(page);
    const receiptRow = receiptTable.locator('tbody tr', { hasText: 'Pseudo artikelcode regressietest' });
    await expect(receiptRow).toBeVisible();
    await expect(receiptRow.locator('td').nth(4)).toHaveText('000426660609');
    await expect(receiptRow.locator('td').nth(9)).toContainText('Zoete aardappel');
    await expect(receiptRow).not.toContainText('lidl:groente.zoete-aardappel');
    await expect(receiptRow).not.toContainText('Lidl Zoete aardappel');

    await receiptRow.dblclick();
    const candidateTable = page.getByTestId('external-receipt-item-candidates-table');
    await expect(candidateTable).toBeVisible();
    await expect(candidateTable).toContainText('Open Food Facts');
    await expect(candidateTable).toContainText('000426660609');
    await expect(candidateTable).not.toContainText('lidl_catalog_enrich');
    await expect(candidateTable).not.toContainText('lidl:groente.zoete-aardappel');
    await expectNoConsoleErrors(consoleErrors);
  });

  test('Bovenste tabel gebruikt gekoppelde kandidaat boven hoogste score', async ({ page }) => {
    const consoleErrors = attachConsoleErrorCollector(page);
    await routeReceiptItems(page, [
      { context_key: 'ctx-linked-wins-regression', receipt_line_id: 'receipt-line-linked-wins-regression', purchase_import_line_id: 'purchase-line-linked-wins-regression', receipt_line_text: 'Gekoppelde kandidaat regressietest', retailer_code: 'lidl', retailer_article_number: '12345', gtin: '', quantity_label: '1 stuk', price: 1.23, candidate_id: 'candidate-highest-score-not-linked', candidate_name: 'Niet gekoppelde hoogste score', candidate_brand: 'Testmerk', external_source_name: 'Open Food Facts', external_source_product_code: 'LIDL-HIGH', variant: 'Standaard', score: 0.99, candidate_status: 'candidate', is_linked_to_catalog: false, is_linkable_to_catalog: true },
      { context_key: 'ctx-linked-wins-regression', receipt_line_id: 'receipt-line-linked-wins-regression', purchase_import_line_id: 'purchase-line-linked-wins-regression', receipt_line_text: 'Gekoppelde kandidaat regressietest', retailer_code: 'lidl', retailer_article_number: '12345', gtin: '', quantity_label: '1 stuk', price: 1.23, candidate_id: 'candidate-linked-lower-score', candidate_name: 'Gekoppelde lagere score', candidate_brand: 'Testmerk', external_source_name: 'Open Food Facts', external_source_product_code: 'LIDL-LINKED', variant: 'Standaard', score: 0.50, candidate_status: 'linked_to_catalog', is_linked_to_catalog: true, is_linkable_to_catalog: false },
    ]);

    const receiptTable = await openExternalDatabases(page);
    const receiptRow = receiptTable.locator('tbody tr', { hasText: 'Gekoppelde kandidaat regressietest' });
    await expect(receiptRow).toBeVisible();
    await expect(receiptRow.locator('td').nth(4)).toHaveText('LIDL-LINKED');
    await expect(receiptRow.locator('td').nth(5)).toHaveText('-');
    await receiptRow.dblclick();
    const linkedCandidateRow = page.getByTestId('external-receipt-item-candidates-table').locator('tbody tr', { hasText: 'Gekoppelde lagere score' });
    await expect(linkedCandidateRow).toBeVisible();
    await expect(linkedCandidateRow).toContainText('Gekoppeld');
    await expectNoConsoleErrors(consoleErrors);
  });

  test('Fallbackkandidaat is zichtbaar maar niet koppelbaar', async ({ page }) => {
    const consoleErrors = attachConsoleErrorCollector(page);
    await routeReceiptItems(page, [{
      context_key: 'ctx-fallback-regression', receipt_line_id: 'receipt-line-fallback-regression', purchase_import_line_id: 'purchase-line-fallback-regression', receipt_line_text: 'Fallback kandidaat regressietest', retailer_code: 'lidl', retailer_article_number: '12345', gtin: '', quantity_label: '1 stuk', price: 1.23, candidate_id: 'candidate-fallback-regression', candidate_name: 'Fallback kandidaat', candidate_brand: '-', external_source_name: 'receipt_product_intent_fallback', external_source_product_code: 'fallback:creme-frache', variant: 'Geen externe match', score: 0.1, candidate_status: 'candidate', is_linked_to_catalog: false, is_linkable_to_catalog: true,
    }]);

    const receiptTable = await openExternalDatabases(page);
    const receiptRow = receiptTable.locator('tbody tr', { hasText: 'Fallback kandidaat regressietest' });
    await expect(receiptRow).toBeVisible();
    await expect(receiptRow.locator('td').nth(9)).toHaveText('-');
    await expect(receiptRow.locator('td').nth(10)).toHaveText('-');
    await expect(receiptRow.locator('td').nth(11)).toHaveText('0');
    await receiptRow.dblclick();
    const fallbackRow = page.getByTestId('external-receipt-item-candidates-table').locator('tbody tr', { hasText: 'Fallback kandidaat' });
    await expect(fallbackRow).toBeVisible();
    await expect(fallbackRow).toContainText('Geen externe match');
    await expect(fallbackRow.locator('input[type="radio"]')).toBeDisabled();
    await expect(page.getByRole('button', { name: 'Koppel artikel', exact: true })).toBeDisabled();
    await expectNoConsoleErrors(consoleErrors);
  });

  test('Catalogusfilter reset detailselectie als geselecteerde rij verdwijnt', async ({ page }) => {
    const consoleErrors = attachConsoleErrorCollector(page);
    await routeReceiptItems(page, [
      { context_key: 'ctx-filter-linked', receipt_line_id: 'line-filter-linked', purchase_import_line_id: 'purchase-filter-linked', receipt_line_text: 'Gekoppeld filter product', retailer_code: 'lidl', retailer_article_number: 'LIDL-LINKED', gtin: '', quantity_label: '1 stuk', price: 1.23, candidate_id: 'candidate-filter-linked', candidate_name: 'Gekoppeld filter kandidaat', candidate_brand: '-', external_source_name: 'Open Food Facts', external_source_product_code: '8710000000001', variant: 'Standaard', score: 0.9, candidate_status: 'linked_to_catalog', is_linked_to_catalog: true, is_linkable_to_catalog: false, global_product_id: 'gp-filter-linked' },
      { context_key: 'ctx-filter-unlinked', receipt_line_id: 'line-filter-unlinked', purchase_import_line_id: 'purchase-filter-unlinked', receipt_line_text: 'Niet gekoppeld filter product', retailer_code: 'lidl', retailer_article_number: 'LIDL-UNLINKED', gtin: '', quantity_label: '1 stuk', price: 1.45, candidate_id: 'candidate-filter-unlinked', candidate_name: 'Niet gekoppeld filter kandidaat', candidate_brand: '-', external_source_name: 'Open Food Facts', external_source_product_code: '8710000000002', variant: 'Standaard', score: 0.8, candidate_status: 'candidate', is_linked_to_catalog: false, is_linkable_to_catalog: true },
    ]);

    const receiptTable = await openExternalDatabases(page);
    const unlinkedRow = receiptTable.locator('tbody tr', { hasText: 'Niet gekoppeld filter product' });
    await expect(unlinkedRow).toBeVisible();
    await unlinkedRow.dblclick();
    await expect(page.getByTestId('external-receipt-item-candidates-table')).toContainText('Niet gekoppeld filter kandidaat');
    await receiptTable.locator('select').first().selectOption('linked');
    await expect(receiptTable.locator('tbody tr', { hasText: 'Gekoppeld filter product' })).toBeVisible();
    await expect(receiptTable.locator('tbody tr', { hasText: 'Niet gekoppeld filter product' })).toHaveCount(0);
    await expect(page.getByText('Niet gekoppeld filter kandidaat')).toHaveCount(0);
    await expectNoConsoleErrors(consoleErrors);
  });
});
