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

    await page.route('**/api/external-products/gpc/classify', async (route) => {
      await route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({ ok: true, status: 'not_classified', reason: 'insufficient_confidence' }) });
    });

    await page.route('**/api/catalog/gpc/bricks?query=*&limit=5', async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          items: [{
            brick_code: '10000284',
            brick_description: 'Cereals Products – Ready to Eat (Shelf Stable)',
            brick_description_en: 'Cereals Products – Ready to Eat (Shelf Stable)',
          }],
          total: 1,
        }),
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
      limit: 5,
    });
    expect(offRequestBodies[1]).toEqual({
      receipt_item_id: 'purchase-import-line:purchase-line-off-preview-regression',
      query: 'melk halfvol zelf zoeken',
      mode: 'manual',
      limit: 5,
    });

    await expect(page.getByTestId('external-producttype-link-panel')).toBeVisible();
    await candidateTable.locator('tbody tr', { hasText: '8710000000099' }).getByRole('radio').check();
    await expect(page.getByLabel('Producttype', { exact: true })).toBeDisabled();
    await expect(page.getByLabel('Producttype', { exact: true })).toHaveValue('');
    await expect(page.getByLabel('Producttype', { exact: true }).locator('option:checked')).toHaveText('GPC-classificatie ontbreekt');
    await expect(page.getByTestId('external-producttype-classification-status')).toContainText('Zoek handmatig op Brickcode of producttype.');
    await expect(page.getByTestId('external-manual-gpc-search')).toBeVisible();
    await page.getByLabel('Zoek op Brickcode of producttype').fill('10000284');
    await page.getByRole('button', { name: 'Zoek GPC' }).click();
    const gpcResults = page.getByTestId('external-gpc-search-results');
    await expect(gpcResults).toContainText('10000284');
    await expect(gpcResults).toContainText('Cereals Products – Ready to Eat (Shelf Stable)');
    await gpcResults.getByRole('option').click();
    await expect(page.getByLabel('Producttype', { exact: true })).toHaveValue('gpc:10000284');
    await expect(page.getByTestId('external-producttype-classification-status')).toContainText('Handmatig geselecteerd uit de officiële GS1 GPC-catalogus.');
    await expect(page.getByRole('button', { name: 'Koppel artikel en Producttype', exact: true })).toBeEnabled();
    await expect(page.getByRole('button', { name: 'Ontkoppel artikel', exact: true })).toBeDisabled();
    await expectNoConsoleErrors(consoleErrors);
  });

  test('Generiek boerenmetworst toont automatisch GPC-kandidaten zonder handmatig zoeken', async ({ page }) => {
    const consoleErrors = attachConsoleErrorCollector(page);
    const classifyBodies = [];
    await page.route('**/api/external-databases/receipt-items?limit=500', async (route) => {
      await route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({ items: [{ receipt_item_id: 'purchase-import-line:boerenmetworst-generic', receipt_item_type: 'purchase_import_line', receipt_item_source_id: 'boerenmetworst-generic', context_key: 'ctx-boerenmetworst-generic', purchase_import_line_id: 'boerenmetworst-generic', receipt_line_text: "'t Slagershuys boerenmetworst", retailer_code: 'Picnic', retailer_article_number: '', gtin: '', quantity_label: '1', price: 3.49, candidate_status: 'no_candidate', is_receipt_item_placeholder: true, is_linked_to_catalog: false, is_linkable_to_catalog: false, candidates: [] }] }) });
    });
    await page.route('**/api/external-products/off/search', async (route) => {
      await route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({ ok: true, status: 'found', provider: 'search_a_licious', query: 'slagershuys boerenmetworst', mode: 'automatic', mutated: false, results: [{ gtin: '5413848467457', product_name: 'Boerenmetworst', brand: '', category: 'Vleeswaren, worst', categories: 'Vleeswaren, worst', score: 0.883, automatic_rank_score: 0.883, confidence: 'high' }] }) });
    });
    await page.route('**/api/external-products/gpc/classify', async (route) => {
      classifyBodies.push(route.request().postDataJSON());
      await route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({ ok: true, status: 'not_classified', reason: 'insufficient_confidence', suggestions: [{ brick_code: '10001001', brick_description: 'Worst en worstproducten', class_description: 'Vleeswaren', family_description: 'Vleesproducten', segment_description: 'Voedingsmiddelen', confidence: 0.86, confidence_label: 'hoog', match_strength_percent: 86, suggestion_reason: 'Overeenkomst met productgegevens: boerenmetworst, vleeswaren' }, { brick_code: '10001002', brick_description: 'Gedroogde vleesproducten', class_description: 'Vleeswaren', family_description: 'Vleesproducten', segment_description: 'Voedingsmiddelen', confidence: 0.68, confidence_label: 'redelijk', match_strength_percent: 68, suggestion_reason: 'Overeenkomst met productgegevens: vleeswaren' }] }) });
    });
    await page.goto('/externe-databases');
    const receiptRow = page.getByTestId('external-receipt-items-table').locator('tbody tr', { hasText: "'t Slagershuys boerenmetworst" });
    await expect(receiptRow).toBeVisible();
    await receiptRow.dblclick();
    await expect(page.getByLabel('Generieke artikelnaam')).toHaveValue("'t Slagershuys boerenmetworst");
    const autoCandidates = page.getByTestId('external-auto-gpc-candidates');
    await expect(autoCandidates).toBeVisible();
    await expect(autoCandidates).toContainText('Waarschijnlijke GS1 GPC Bricks');
    await expect(autoCandidates).toContainText('10001001');
    await expect(autoCandidates).toContainText('86%');
    await expect(autoCandidates).toContainText('boerenmetworst');
    await expect(page.getByTestId('external-manual-gpc-search')).toBeVisible();
    await expect(page.getByLabel('Zoek op Brickcode of producttype')).toHaveValue('');
    await page.getByTestId('external-auto-gpc-candidate-list').getByRole('option').first().click();
    await expect(page.getByLabel('Producttype', { exact: true })).toHaveValue('gpc:10001001');
    await expect(page.getByTestId('external-producttype-classification-status')).toContainText('GPC-kandidaat bevestigd');
    await expect(page.getByRole('button', { name: 'Koppel als generiek artikel', exact: true })).toBeEnabled();
    await expect.poll(() => classifyBodies.length).toBeGreaterThan(0);
    expect(classifyBodies.some((body) => String(body?.product_name || '').includes('boerenmetworst'))).toBe(true);
    expect(classifyBodies.some((body) => String(body?.search_text || '').includes('boerenmetworst'))).toBe(true);
    await expectNoConsoleErrors(consoleErrors);
  });

  test('Bananen gebruiken de expliciete officiële GPC Brick uit OFF zonder classificatie-omweg', async ({ page }) => {
    let classifyCalled = false;
    let exactCatalogLookupCalled = false;

    await page.route('**/api/external-databases/receipt-items?limit=500', async (route) => {
      await route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(receiptItemsPayload()) });
    });
    await page.route('**/api/external-products/off/search', async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          ...automaticSearchResponse(),
          results: [{
            gtin: '8718265184886',
            product_name: 'Bananen',
            brand: 'De Groot',
            score: 0.99,
            gpc_brick_code: '10005897',
          }],
        }),
      });
    });
    await page.route('**/api/catalog?primary_gtin=8718265184886&limit=20', async (route) => {
      exactCatalogLookupCalled = true;
      await route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({ items: [] }) });
    });
    await page.route('**/api/external-products/gpc/classify', async (route) => {
      classifyCalled = true;
      await route.fulfill({ status: 500, contentType: 'application/json', body: JSON.stringify({ detail: 'Classificatie-omweg mag niet nodig zijn' }) });
    });
    await page.route('**/api/inventory/groups', async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          group_options: [{
            inventory_group_key: 'gpc:10005897',
            display_name: 'Bananen',
            default_base_unit: 'stuk',
            gpc_brick_code: '10005897',
            source: 'gs1_gpc_2026_05_en',
          }],
        }),
      });
    });

    await page.goto('/externe-databases');
    const receiptRow = page.getByTestId('external-receipt-items-table').locator('tbody tr', { hasText: 'halfvolle melk' });
    await receiptRow.dblclick();
    const candidateRow = page.getByTestId('external-receipt-item-candidates-table').locator('tbody tr', { hasText: '8718265184886' });
    await candidateRow.getByRole('radio').check();

    await expect(page.getByLabel('Producttype', { exact: true })).toHaveValue('gpc:10005897');
    await expect(page.getByLabel('Producttype', { exact: true }).locator('option:checked')).toContainText('Bananen — GPC 10005897');
    await expect(page.getByTestId('external-producttype-classification-status')).toContainText('Producttype bepaald via expliciete GPC Brickcode van de externe bron.');
    await expect(page.getByRole('button', { name: 'Koppel artikel en Producttype', exact: true })).toBeEnabled();
    expect(exactCatalogLookupCalled).toBe(true);
    expect(classifyCalled).toBe(false);
  });

  test('Langdurige OFF-zoekactie toont na Ã©Ã©n seconde de blokkerende R en verwijdert die direct na een fout', async ({ page }) => {
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

    await page.route('**/api/external-products/gpc/classify', async (route) => {
      await route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({ ok: true, status: 'not_classified', reason: 'insufficient_confidence' }) });
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
              central_link_active: true,
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
        body: JSON.stringify({ group_options: [{ inventory_group_key: 'gpc:10005897', display_name: 'Bananen (Cavendish)', default_base_unit: 'stuk', gpc_brick_code: '10005897', source: 'gs1_gpc_nl' }] }),
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

    await expect(page.getByLabel('Producttype', { exact: true })).toHaveValue('gpc:10005897');

    await expectNoConsoleErrors(consoleErrors);
  });

  test('AH BOUILLON kan breed zoeken en zonder GTIN generiek op GPC Brick worden gekoppeld', async ({ page }) => {
    const consoleErrors = attachConsoleErrorCollector(page);
    let genericLinked = false;
    let genericLinkBody = null;
    let releaseLateAutomaticGpc;
    const lateAutomaticGpcGate = new Promise((resolve) => { releaseLateAutomaticGpc = resolve; });

    const receiptPayload = () => ({
      items: [{
        receipt_item_id: 'purchase-import-line:ah-bouillon-generic',
        receipt_item_type: 'purchase_import_line',
        receipt_item_source_id: 'ah-bouillon-generic',
        context_key: 'ctx-ah-bouillon-generic',
        purchase_import_line_id: 'ah-bouillon-generic',
        receipt_line_text: 'AH BOUILLON',
        retailer_code: 'Albert Heijn',
        retailer_article_number: '',
        gtin: '',
        quantity_label: '1',
        price: 1.49,
        candidate_status: genericLinked ? 'linked_to_catalog' : 'no_candidate',
        status: genericLinked ? 'linked_to_catalog' : 'no_candidate',
        global_product_id: genericLinked ? 'generic-bouillon-product' : null,
        canonical_catalog_product_id: genericLinked ? 'generic-bouillon-product' : null,
        is_receipt_item_placeholder: true,
        is_linked_to_catalog: genericLinked,
        central_link_active: genericLinked,
        is_existing_link_for_receipt_item: genericLinked,
        is_generic_catalog_link: genericLinked,
        central_link_mode: genericLinked ? 'generic' : '',
        is_linkable_to_catalog: false,
        linked_candidate_name: genericLinked ? 'Bouillon' : '',
        linked_product_type_id: genericLinked ? 'gpc:10000262' : '',
        linked_product_type: genericLinked ? 'Soups - Prepared (Shelf Stable)' : '',
        linked_gtin: '',
        linked_score: null,
        candidates: [],
      }],
    });

    await page.route('**/api/external-databases/receipt-items?limit=500', async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify(receiptPayload()),
      });
    });

    await page.route('**/api/inventory/groups', async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({ group_options: [] }),
      });
    });

    await page.route('**/api/external-products/off/search', async (route) => {
      const body = route.request().postDataJSON();
      const manual = body?.mode === 'manual';
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          ok: true,
          status: manual ? 'found' : 'no_results',
          provider: 'search_a_licious',
          query: manual ? body.query : 'ah bouillon',
          mode: manual ? 'manual' : 'automatic',
          mutated: false,
          results: manual ? [
            {
              gtin: '0500003088840',
              product_name: 'Bouillon',
              brand: 'Marigold',
              score: 0.86,
              identity_compatible: false,
              identity_conflict_reason: 'private_label_brand_conflict',
              identity_conflict_message: 'Merk wijkt af van AH',
            },
            {
              gtin: '8718906470101',
              product_name: 'Bouillon bospaddenstoel',
              brand: 'Albert Heijn',
              score: 0.82,
              identity_compatible: true,
            },
          ] : [],
        }),
      });
    });

    await page.route('**/api/external-products/gpc/classify', async (route) => {
      await lateAutomaticGpcGate;
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          ok: true,
          status: 'not_classified',
          reason: 'insufficient_confidence',
          suggestions: [{
            brick_code: '10000262',
            brick_description: 'Soups - Prepared (Shelf Stable)',
            confidence: 0.71,
            confidence_label: 'redelijk',
            match_strength_percent: 71,
            suggestion_reason: 'Overeenkomst met productgegevens: Bouillon',
          }],
        }),
      });
    });

    await page.route('**/api/catalog?primary_gtin=*&limit=20', async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({ items: [], total: 0 }),
      });
    });

    await page.route('**/api/catalog/gpc/bricks?query=*&limit=5', async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          items: [{
            brick_code: '10000262',
            brick_description: 'Soups - Prepared (Shelf Stable)',
            brick_description_en: 'Soups - Prepared (Shelf Stable)',
          }],
          total: 1,
        }),
      });
    });

    await page.route('**/api/external-products/generic/link', async (route) => {
      genericLinkBody = route.request().postDataJSON();
      genericLinked = true;
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          ok: true,
          linked: true,
          generic: true,
          global_product: {
            id: 'generic-bouillon-product',
            gtin: '',
            name: 'Bouillon',
            brand: '',
            generic: true,
          },
          product_type: {
            id: 'gpc:10000262',
            gpc_brick_code: '10000262',
          },
        }),
      });
    });

    await page.goto('/externe-databases');
    const receiptTable = page.getByTestId('external-receipt-items-table');
    const receiptRow = receiptTable.locator('tbody tr', { hasText: 'AH BOUILLON' });
    await expect(receiptRow).toBeVisible();
    await receiptRow.dblclick();

    await expect(page.getByLabel('Generieke artikelnaam')).toHaveValue('Bouillon');
    await expect(page.getByRole('button', { name: 'Koppel artikel en Producttype', exact: true })).toBeDisabled();

    await page.getByLabel('OFF zoektekst').fill('BOUILLON');
    await page.getByRole('button', { name: 'Zelf zoeken' }).click();

    const candidateTable = page.getByTestId('external-receipt-item-candidates-table');
    const marigold = candidateTable.locator('tbody tr', { hasText: 'Marigold' });
    await expect(marigold).toBeVisible();
    await expect(marigold).toContainText('Merk wijkt af');
    await expect(marigold.getByRole('radio')).toBeDisabled();
    await expect(candidateTable.locator('tbody tr', { hasText: 'Albert Heijn' })).toBeVisible();

    await page.getByLabel('Zoek op Brickcode of producttype').fill('10000262');
    await page.getByRole('button', { name: 'Zoek GPC' }).click();
    const gpcResults = page.getByTestId('external-gpc-search-results');
    await expect(gpcResults).toContainText('10000262');
    await expect(gpcResults).toContainText('Soups - Prepared (Shelf Stable)');

    releaseLateAutomaticGpc();
    await expect(gpcResults).toContainText('10000262');
    await gpcResults.getByRole('option').click();

    await expect(page.getByRole('button', { name: 'Koppel als generiek artikel', exact: true })).toBeEnabled();
    await page.getByRole('button', { name: 'Koppel als generiek artikel', exact: true }).click();

    expect(genericLinkBody).toEqual({
      receipt_item_id: 'purchase-import-line:ah-bouillon-generic',
      generic_product_name: 'Bouillon',
      product_type_assignment: {
        product_type_id: 'gpc:10000262',
        gpc_source: 'manual',
        mapping_source: 'manual_gs1_gpc',
        confidence_score: 1,
      },
    });

    const linkedRow = receiptTable.locator('tbody tr', { hasText: 'AH BOUILLON' });
    await expect(linkedRow.locator('td').nth(3).getByRole('checkbox')).toBeChecked();
    await expect(linkedRow.locator('td').nth(5)).toHaveText('Bouillon');
    await expect(linkedRow.locator('td').nth(6)).toHaveText('Soups - Prepared (Shelf Stable)');
    await expect(linkedRow.locator('td').nth(7)).toHaveText('-');

    await expectNoConsoleErrors(consoleErrors);
  });

  // OFF_ZOEKOVERLAY_REGRESSIETEST_INGEVOERD

});
