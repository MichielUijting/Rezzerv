import { test, expect } from '@playwright/test';
import {
  attachConsoleErrorCollector,
  expectNoConsoleErrors,
  expectRouteLoads,
} from './helpers/rezzervAssertions.js';

test.use({ storageState: 'playwright/.auth/superuser.json' })

test.describe('Externe databases 2: overzicht en OFF-kandidaten', () => {
  test.use({ storageState: { cookies: [], origins: [] } })
  for (const width of [390, 1280]) {
    test(`OFF-paneel gebruikt bestaande automatische zoekflow op ${width}px`, async ({ page }) => {
      await page.setViewportSize({ width, height: 900 })
      const searches = []
      const unexpectedWrites = []
      let errorAttempts = 0
      let slowMilk = false
      let releaseSlow = null
      let slowCompleted = false
      const rows = ['Melk', 'Appels', 'Kaas'].map((name, index) => ({
        id: `receipt-table-line:off-panel-${index}`, receipt_line_text: name,
        retailer_code: 'lidl', receipt_article_number: String(index), quantity_label: '1 stuk',
      }))
      await page.route('**/api/**', async (route) => {
        const request = route.request()
        const path = new URL(request.url()).pathname
        if (path === '/api/external-databases/products/search-preview') {
          const body = request.postDataJSON()
          searches.push(body)
          if (slowMilk && body.receipt_item_id === rows[0].id) {
            await new Promise((resolve) => { releaseSlow = resolve })
            try {
              await route.fulfill({ json: { provider: 'openfoodfacts', results: [
                { gtin: '8720326035617', product_name: 'Verouderde respons voor Melk', score: .99 },
              ] } })
            } catch { /* The previous item's request is expected to be aborted. */ }
            slowCompleted = true
            return
          }
          if (body.receipt_item_id === rows[1].id) return route.fulfill({ json: { provider: 'openfoodfacts', results: [], retailer_evidence: { status: 'no_barcode', message: 'Lidl-product gevonden, maar geen barcode vermeld.' } } })
          if (body.receipt_item_id === rows[2].id && errorAttempts++ === 0) return route.fulfill({ status: 503, json: { detail: 'OFF is tijdelijk niet bereikbaar.' } })
          return route.fulfill({ json: { provider: 'openfoodfacts', retailer_evidence: {
            status: 'barcode_found', product_name: 'Halfvolle melk', brand: 'Testmerk',
            article_number: '1234567', gtins: ['8720326035617'], source_url: 'https://www.lidl.nl/p/test/p1234567',
            message: 'Lidl vermeldt één geldige barcode bij dit product.',
          }, results: [
            { gtin: '8720326035617', product_name: 'Voorkeur uit automatische zoekvarianten', source: 'Lidl + Open Food Facts', evidence_label: 'Lidl-barcode gevonden in OFF', brand: 'Testmerk', quantity: '1 l', score: .60, automatic_rank_score: .95 },
            { gtin: '8718452504435', product_name: 'Tweede suggestie', brand: 'Testmerk', quantity: '500 ml', score: .99, automatic_rank_score: .80 },
          ] } })
        }
        if (request.method() !== 'GET') unexpectedWrites.push(path)
        if (path === '/api/session') return route.fulfill({ json: {
          user_id: 'off-panel-test', email: 'off-panel@example.test', active_household_id: '0',
          context_type: 'system', role: 'owner', is_platform_superuser: true,
          permissions: { 'platform.system_household.access': true },
        } })
        if (path === '/api/external-databases/unlinked-articles') return route.fulfill({ json: { items: rows, total: rows.length } })
        if (path === '/api/onboarding') return route.fulfill({ json: { onboarding_status: 'completed' } })
        if (path === '/api/features') return route.fulfill({ json: { features: {} } })
        if (path === '/api/action-buttons') return route.fulfill({ json: { items: [] } })
        return route.fulfill({ json: {} })
      })
      await page.goto('/externe-databases-2')
      const table = page.getByTestId('external-databases-2-table')
      await expect(table.locator('tbody tr')).toHaveCount(3)
      expect(searches).toEqual([])
      const open = async (index) => {
        const row = table.locator('tbody tr').filter({ hasText: rows[index].receipt_line_text })
        if (width <= 720) await row.click()
        else await row.dblclick()
      }
      if (width > 720) {
        await table.locator('tbody tr').first().click()
        await expect(page.getByTestId('external-databases-2-off-panel')).toHaveCount(0)
        expect(searches).toEqual([])
      }
      await open(0)
      const panel = page.getByTestId('external-databases-2-off-panel')
      await expect(panel.getByRole('heading')).toContainText('Melk — Lidl')
      const candidates = panel.getByTestId('external-databases-2-off-candidates')
      await expect(candidates.locator('tbody tr').first()).toContainText('Voorkeur uit automatische zoekvarianten')
      await expect(candidates.locator('tbody tr').first()).toContainText('95%')
      await expect(candidates).toContainText('Lidl + Open Food Facts')
      await expect(panel.getByTestId('retailer-product-evidence')).toContainText('1234567')
      await expect(panel.getByTestId('retailer-product-evidence')).toContainText('8720326035617')
      await expect(panel.getByRole('link', { name: 'Bekijk product bij Lidl' })).toHaveAttribute('href', 'https://www.lidl.nl/p/test/p1234567')
      expect(searches[0]).toEqual({ receipt_item_id: rows[0].id, mode: 'automatic', limit: 20 })
      expect(await panel.evaluate((element) => Boolean(element.previousElementSibling?.querySelector('[data-testid="external-databases-2-table"]')))).toBe(true)
      await open(1)
      await expect(panel.getByRole('heading')).toContainText('Appels — Lidl')
      await expect(panel).toContainText('Geen passende productkandidaten gevonden.')
      await expect(panel).not.toContainText('Tweede suggestie')
      await expect(panel).toContainText('Lidl-product gevonden, maar geen barcode vermeld.')
      await expect(panel).not.toContainText('1234567')
      await open(2)
      await expect(panel.getByRole('alert')).toContainText('OFF is tijdelijk niet bereikbaar.')
      await panel.getByRole('button', { name: 'Opnieuw zoeken' }).click()
      await expect(panel.getByTestId('external-databases-2-off-candidates')).toContainText('Tweede suggestie')
      await expect(table.locator('tbody tr')).toHaveCount(3)
      await expect(page.getByRole('button', { name: /Koppel|Opslaan|Afsluiten/ })).toHaveCount(0)
      slowMilk = true
      await open(0)
      await expect(panel.getByRole('status')).toContainText('Kandidaten zoeken')
      await expect.poll(() => Boolean(releaseSlow)).toBe(true)
      await open(1)
      await expect(panel).toContainText('Geen passende productkandidaten gevonden.')
      releaseSlow()
      await expect.poll(() => slowCompleted).toBe(true)
      await expect(panel.getByRole('heading')).toContainText('Appels — Lidl')
      await expect(panel).not.toContainText('Verouderde respons')
      expect(unexpectedWrites).toEqual([])
    })

    test(`standaardtabel zoekt over alle pagina's op ${width}px`, async ({ page }) => {
      await page.setViewportSize({ width, height: 900 })
      const writes = []
      const rows = Array.from({ length: 23 }, (_, index) => ({
        id: `article-${index}`, receipt_line_text: `Artikel ${String(index).padStart(2, '0')}`,
        retailer_code: 'lidl', receipt_article_number: String(index), quantity_label: '1 l',
      }))
      await page.route('**/api/**', async (route) => {
        const request = route.request()
        const path = new URL(request.url()).pathname
        if (request.method() !== 'GET') writes.push(path)
        if (path === '/api/session') return route.fulfill({ json: {
          user_id: 'external-overview-test', email: 'overview@example.test',
          active_household_id: '0', context_type: 'system', role: 'owner',
          is_platform_superuser: true, permissions: { 'platform.system_household.access': true },
        } })
        if (path === '/api/external-databases/unlinked-articles') return route.fulfill({ json: { items: rows, total: rows.length } })
        if (path === '/api/onboarding') return route.fulfill({ json: { onboarding_status: 'completed' } })
        if (path === '/api/features') return route.fulfill({ json: { features: {} } })
        if (path === '/api/action-buttons') return route.fulfill({ json: { items: [] } })
        return route.fulfill({ json: {} })
      })
      await page.goto('/externe-databases-2')
      const table = page.getByTestId('external-databases-2-table')
      await expect(table.locator('tbody tr')).toHaveCount(10)
      await expect(page.getByRole('navigation', { name: 'Paginering' })).toBeVisible()
      await page.getByRole('navigation', { name: 'Paginering' }).getByRole('button', { name: '+', exact: true }).click()
      await expect(table).toContainText('Artikel 10')
      await page.getByRole('textbox', { name: 'Filter op Artikel', exact: true }).fill('Artikel 22')
      await expect(table.locator('tbody tr')).toHaveCount(1)
      await expect(table).toContainText('Artikel 22')
      await expect(page.getByRole('navigation', { name: 'Paginering' })).toHaveCount(0)
      await expect(table.getByRole('checkbox')).toHaveCount(0)
      await expect(page.getByRole('button', { name: 'Afsluiten', exact: true })).toHaveCount(0)
      await expect(page.getByRole('button', { name: /Koppel|Zoek product|Zelf zoeken|Exporteren/ })).toHaveCount(0)
      expect(writes).toEqual([])
    })
  }
})

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
    await expect(receiptRow.locator('td').nth(5)).toHaveText('-');
    await expect(receiptRow.locator('td').nth(6)).toHaveText('-');
    await expect(receiptRow.locator('td').nth(7)).toHaveText('8710000001234');
    await expect(receiptRow.locator('td').nth(8)).toHaveText('1 stuk');
    await expect(receiptRow.locator('td').nth(9)).toHaveText('1,23');
    await expect(receiptRow.locator('td').nth(10)).toHaveText('0');

    await receiptRow.dblclick();

    const candidateTable = page.getByTestId('external-receipt-item-candidates-table');
    await expect(candidateTable).toBeVisible();
    await expect(candidateTable).toContainText('Geen universele kandidaten met score 0,500 of hoger voor dit bonartikel.');
    await expect(candidateTable.getByText('Onterechte kandidaat')).toHaveCount(0);
    await expect(page.getByText('GTIN/EAN is al bekend; OFF-kandidaten worden niet automatisch toegevoegd.')).toBeVisible();
    await expect(page.getByRole('button', { name: 'Koppel artikel en Producttype', exact: true })).toBeDisabled();
    await expect(page.getByRole('button', { name: 'Ontkoppel artikel', exact: true })).toBeDisabled();
    expect(offSearchCalled).toBe(false);

    await expectNoConsoleErrors(consoleErrors);
  });
});
