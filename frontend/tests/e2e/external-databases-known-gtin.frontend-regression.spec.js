import { test, expect } from '@playwright/test';
import {
  attachConsoleErrorCollector,
  expectNoConsoleErrors,
  expectRouteLoads,
} from './helpers/rezzervAssertions.js';

test.use({ storageState: 'playwright/.auth/superuser.json' })

test.describe('Externe databases 2: overzicht en OFF-kandidaten', () => {
  test.use({ storageState: { cookies: [], origins: [] } })
  test('tellers en kolom Art./Barcode filteren het complete overzicht; barcode zoekt exact in OFF', async ({ page }) => {
    const rows = [
      { id: 'receipt-table-line:ed2-empty', receipt_line_text: 'Melk zonder code', retailer_code: 'jumbo',
        receipt_article_number: '123', article_code: '', link_status: 'unlinked' },
      { id: 'receipt-table-line:ed2-pending', receipt_line_text: 'Melk zonder classificatie', retailer_code: 'jumbo',
        receipt_article_number: '456', article_code: '8718452504435', link_status: 'classification_pending' },
      { id: 'receipt-table-line:ed2-linked', receipt_line_text: 'Melk met code', retailer_code: 'jumbo',
        receipt_article_number: '789', article_code: '8720326035617', link_status: 'linked' },
    ]
    const requests = []
    await page.route('**/api/**', async (route) => {
      const path = new URL(route.request().url()).pathname
      if (path === '/api/session') return route.fulfill({ json: {
        user_id: 'test-superuser', active_household_id: '0', context_type: 'system',
        role: 'owner', is_platform_superuser: true,
        permissions: { 'platform.system_household.access': true },
      } })
      if (path === '/api/maintenance/status') return route.fulfill({ json: { state: 'normal' } })
      if (path === '/api/onboarding') return route.fulfill({ json: { onboarding_status: 'completed' } })
      if (path === '/api/features') return route.fulfill({ json: { features: {} } })
      if (path === '/api/action-buttons') return route.fulfill({ json: { items: [] } })
      if (path === '/api/external-databases/articles-overview') return route.fulfill({ json: {
        items: rows, total: 3, counts: { unlinked: 1, classification_pending: 1, linked: 1 },
      } })
      if (path === '/api/external-databases/products/search-preview') return route.fulfill({ json: {
        results: [], provider: 'none',
      } })
      if (path === '/api/external-products/off/search') {
        requests.push(route.request().postDataJSON())
        return route.fulfill({ json: { provider: 'off_exact_gtin', results: [{
          gtin: '8718452504435', product_name: 'Halfvolle melk', brand: 'Jumbo',
          score: 0.9, selection_proof: 'signed-exact', identity_compatible: true,
        }] } })
      }
      return route.fulfill({ json: {} })
    })
    await page.goto('/externe-databases-2')
    const table = page.getByTestId('external-databases-2-table')
    await expect(table.locator('tbody tr')).toHaveCount(3)
    const unlinkedCounter = page.getByRole('button', { name: 'Niet gekoppeld: 1' })
    const pendingCounter = page.getByRole('button', { name: 'Classificatie ontbreekt: 1' })
    const linkedCounter = page.getByRole('button', { name: 'Gekoppeld: 1', exact: true })
    await expect(unlinkedCounter).toHaveCSS('background-color', 'rgb(255, 217, 168)')
    await expect(pendingCounter).toHaveCSS('background-color', 'rgb(255, 255, 255)')
    await expect(linkedCounter).toHaveCSS('background-color', 'rgb(217, 245, 224)')

    await linkedCounter.click()
    await expect(table).toContainText('Melk met code')
    await expect(table).not.toContainText('Melk zonder code')
    await page.getByRole('button', { name: 'Wis filters' }).click()
    await page.getByRole('textbox', { name: 'Filter op Art./Barcode' }).fill('8720326035617')
    await expect(table).toContainText('Melk met code')
    await expect(table).not.toContainText('Melk zonder code')
    await page.getByRole('button', { name: 'Wis filters' }).click()
    await page.getByRole('textbox', { name: 'Filter op GS1-class.' }).fill('Gekoppeld')
    await expect(table.locator('tbody tr')).toHaveCount(1)
    await expect(table).toContainText('Melk met code')
    await expect(table).not.toContainText('Melk zonder code')
    await expect(table.locator('thead')).toContainText('GS1-class.')
    await page.getByRole('button', { name: 'Wis filters' }).click()

    await table.locator('tbody tr').filter({ hasText: 'Melk zonder code' }).dblclick()
    await page.getByRole('button', { name: 'Zelf zoeken in OFF' }).click()
    const selectedReceiptName = page.getByText('Melk zonder code', { exact: true })
    await expect(selectedReceiptName).toHaveCSS('font-weight', '700')
    const freeSearch = page.getByRole('textbox', { name: 'Omschrijving of barcode in OFF' })
    const searchButton = page.getByRole('button', { name: 'Zoeken', exact: true })
    await expect(page.getByRole('textbox')).toHaveCount(2)
    for (const width of [390, 1280]) {
      await page.setViewportSize({ width, height: 900 })
      // A responsive viewport switch may briefly unmount the current layout.
      // Wait for both controls and keep the original height/alignment contract.
      await expect(freeSearch).toBeVisible()
      await expect(searchButton).toBeVisible()
      await expect.poll(async () => {
        const fieldBox = await freeSearch.boundingBox()
        const buttonBox = await searchButton.boundingBox()
        return Boolean(fieldBox && buttonBox
          && Math.abs(fieldBox.height - buttonBox.height) <= 1
          && Math.abs((fieldBox.y + fieldBox.height) - (buttonBox.y + buttonBox.height)) <= 1)
      }).toBe(true)
    }
    await freeSearch.fill('8718452504435')
    await searchButton.click()
    await expect(page.getByTestId('external-off-free-search-results')).toContainText('Halfvolle melk')
    expect(requests).toEqual([{ receipt_item_id: rows[0].id, mode: 'manual', gtin: '8718452504435', limit: 20 }])
    await freeSearch.fill('1234567')
    await searchButton.click()
    await expect(page.getByRole('alert')).toContainText('Vul een geldige barcode van 8, 12, 13 of 14 cijfers in.')
    expect(requests).toHaveLength(1)
    await freeSearch.fill('Halfvolle melk 2')
    await searchButton.click()
    expect(requests[1]).toEqual({ receipt_item_id: rows[0].id, mode: 'manual', query: 'Halfvolle melk 2', limit: 20 })
  })
  for (const width of [390, 1280]) {
    test(`OFF-product zonder GPC blijft in Catalogus en ED2 zichtbaar op ${width}px`, async ({ page }) => {
      await page.setViewportSize({ width, height: 900 })
      const item = { id: 'receipt-table-line:achterham-test', receipt_line_text: 'Achterham BL',
        retailer_code: 'lidl', receipt_article_number: '6604471', quantity_label: '1 stuk' }
      let saved = false
      await page.route('**/api/**', async (route) => {
        const request = route.request()
        const path = new URL(request.url()).pathname
        if (path === '/api/session') return route.fulfill({ json: {
          user_id: 'test-superuser', active_household_id: '0', context_type: 'system',
          role: 'owner', is_platform_superuser: true,
          permissions: { 'platform.system_household.access': true },
        } })
        if (path === '/api/maintenance/status') return route.fulfill({ json: { state: 'normal' } })
        if (path === '/api/onboarding') return route.fulfill({ json: { onboarding_status: 'completed' } })
        if (path === '/api/features') return route.fulfill({ json: { features: {} } })
        if (path === '/api/action-buttons') return route.fulfill({ json: { items: [] } })
        if (path === '/api/external-databases/articles-overview') return route.fulfill({ json: {
          items: [saved ? { ...item, article_code: '8718452504435',
            link_status: 'classification_pending' } : { ...item, article_code: '', link_status: 'unlinked' }],
          total: 1, counts: saved ? { unlinked: 0, classification_pending: 1, linked: 0 }
            : { unlinked: 1, classification_pending: 0, linked: 0 },
        } })
        if (path === '/api/external-databases/products/search-preview') return route.fulfill({ json: {
          provider: 'openfoodfacts', results: [{ gtin: '8718452504435',
            product_name: 'Achterham', brand: 'Zwagerman', score: .9 }],
        } })
        if (path === '/api/external-products/off/search') return route.fulfill({ json: {
          provider: 'openfoodfacts', mutated: false, results: [{
            gtin: '8718452504435', product_name: 'Achterham', brand: 'Zwagerman',
            score: .98, selection_proof: 'signed-achterham',
          }],
        } })
        if (path === '/api/external-databases/off/link-selected') {
          expect(request.postDataJSON()).toEqual({
            receipt_item_id: item.id, gtin: '8718452504435', selection_proof: 'signed-achterham',
          })
          saved = true
          return route.fulfill({ json: {
            ok: true, linked: false, cataloged: true, classification_pending: true,
            global_product_id: 'pending-achterham',
          } })
        }
        if (path === '/api/catalog') return route.fulfill({ json: {
          items: [{ id: 'pending-achterham', name: 'Achterham', brand: 'Zwagerman',
            primary_gtin: '8718452504435', catalog_kind: 'exact', product_type: '',
            gpc_brick_code: '', gpc_brick_name: '', gpc_class_name: '', gpc_family_name: '',
          }], total: 1,
        } })
        return route.fulfill({ json: {} })
      })
      await page.goto('/externe-databases-2')
      const table = page.getByTestId('external-databases-2-table')
      const row = table.locator('tbody tr').filter({ hasText: 'Achterham BL' })
      if (width <= 720) await row.click()
      else await row.dblclick()
      await page.getByRole('button', { name: 'Zelf zoeken in OFF' }).click()
      await page.getByRole('textbox', { name: 'Omschrijving of barcode in OFF' }).fill('Achterham')
      await page.getByRole('button', { name: 'Zoeken', exact: true }).click()
      const candidate = page.getByTestId('external-off-free-search-results').locator('tbody tr').first()
      if (width <= 720) await candidate.click()
      else await candidate.dblclick()
      await page.getByRole('button', { name: 'OK', exact: true }).click()
      await expect(page).toHaveURL(/\/externe-databases-2$/)
      await expect(page.getByTestId('external-off-link-outcome')).toContainText('GS1-classificatie ontbreekt nog')
      await expect(table).toContainText('Achterham BL')
      await expect(table).toContainText('8718452504435')
      await expect(page.getByRole('button', { name: 'Classificatie ontbreekt: 1' })).toBeVisible()
      await page.goto('/catalogus')
      await expect(page.getByText('Achterham', { exact: true })).toBeVisible()
      await expect(page.getByText('Classificatie ontbreekt')).toBeVisible()
    })
  }
  for (const width of [390, 1280]) {
    test(`OFF-paneel gebruikt bestaande automatische zoekflow op ${width}px`, async ({ page }) => {
      await page.setViewportSize({ width, height: 900 })
      const searches = []
      const links = []
      let linkResultMode = 'success'
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
        if (path === '/api/external-databases/off/link-selected') {
          const body = request.postDataJSON()
          links.push(body)
          expect(body).toEqual({ receipt_item_id: rows[0].id, gtin: '8712345678900', selection_proof: 'signed-fixture-proof' })
          if (linkResultMode === 'fail') return route.fulfill({ status: 422, json: { detail: 'Officiële GS1-classificatie ontbreekt.' } })
          return route.fulfill({ json: { ok: true, linked: true, global_product_id: 'catalog-existing' } })
        }
        if (path === '/api/external-products/off/search') {
          const body = request.postDataJSON()
          expect(body).toEqual({ receipt_item_id: rows[0].id, mode: 'manual', query: 'halfvolle melk bio', limit: 20 })
          return route.fulfill({ json: { provider: 'openfoodfacts', mutated: false, results: Array.from({ length: 16 }, (_, index) => ({
            gtin: `87123456789${String(index).padStart(2, '0')}`, product_name: `Vrij gezocht product ${index + 1}`,
            brand: 'OFF-merk', quantity: '1 l', score: 1 - index / 20, selection_proof: 'signed-fixture-proof',
          })) } })
        }
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
            ...Array.from({ length: 13 }, (_, index) => ({ gtin: String(80000000 + index), product_name: `Aanvullende suggestie ${String(index).padStart(2, '0')}`, source: 'Jumbo', evidence_label: 'Winkelproduct; suggestie op naam', score: .7 })),
          ] } })
        }
        if (request.method() !== 'GET') unexpectedWrites.push(path)
        if (path === '/api/session') return route.fulfill({ json: {
          user_id: 'off-panel-test', email: 'off-panel@example.test', active_household_id: '0',
          context_type: 'system', role: 'owner', is_platform_superuser: true,
          permissions: { 'platform.system_household.access': true },
        } })
        if (path === '/api/maintenance/status') return route.fulfill({ json: { state: 'normal' } })
        if (path === '/api/external-databases/articles-overview') return route.fulfill({ json: { items: rows, total: rows.length } })
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
      await expect(candidates).toContainText('Lidl + OFF')
      await expect(panel.getByTestId('retailer-product-evidence')).toHaveCount(0)
      await expect(panel).not.toContainText('Lidl vermeldt één geldige barcode')
      expect(searches[0]).toEqual({ receipt_item_id: rows[0].id, mode: 'automatic', limit: 20 })
      await expect(candidates.locator('tbody tr')).toHaveCount(7)
      const paging = panel.getByRole('navigation', { name: 'Paginering' })
      await paging.getByRole('button', { name: '+', exact: true }).click()
      await expect(candidates.locator('tbody tr')).toHaveCount(7)
      await expect(candidates).toContainText('Aanvullende suggestie 05')
      await paging.getByRole('button', { name: '3', exact: true }).click()
      await expect(candidates.locator('tbody tr')).toHaveCount(1)
      await expect(candidates).toContainText('Aanvullende suggestie 12')
      await panel.getByRole('textbox', { name: 'Filter op Artikel', exact: true }).fill('Voorkeur')
      await expect(candidates.locator('tbody tr')).toHaveCount(1)
      await expect(candidates).toContainText('Voorkeur uit automatische zoekvarianten')
      await expect(paging).toHaveCount(0)
      await panel.getByRole('textbox', { name: 'Filter op Artikel', exact: true }).fill('')
      await expect(candidates.locator('tbody tr')).toHaveCount(7)
      expect(searches).toHaveLength(1)
      // Het OFF-paneel volgt op de gewone tabel en de bulkacties in dezelfde
      // overzichtscontainer, niet meer als direct volgend sibling-element.
      const overview = page.locator('.rz-external-receipt-overview')
      await expect(overview.getByTestId('external-databases-2-table')).toHaveCount(1)
      await expect(overview.getByTestId('external-databases-2-off-panel')).toHaveCount(1)
      expect(await overview.evaluate((element) => {
        const table = element.querySelector('[data-testid="external-databases-2-table"]')
        const panel = element.querySelector('[data-testid="external-databases-2-off-panel"]')
        return Boolean(table && panel && (table.compareDocumentPosition(panel) & Node.DOCUMENT_POSITION_FOLLOWING))
      })).toBe(true)
      await panel.getByRole('button', { name: 'Zelf zoeken in OFF' }).click()
      await expect(page).toHaveURL(/\/externe-databases-2\/off-zoeken\//)
      if (width <= 720) {
        await expect(page.getByTestId('mobile-global-header').getByRole('heading', { name: 'Zelf zoeken in OFF' })).toBeVisible()
      } else {
        await expect(page.getByTestId('app-header')).toContainText('Zelf zoeken in OFF')
      }
      await expect(page.getByRole('textbox')).toHaveCount(2)
      const freeSearch = page.getByRole('textbox', { name: 'Omschrijving of barcode in OFF' })
      await freeSearch.fill('halfvolle melk bio')
      await page.getByRole('button', { name: 'Zoeken', exact: true }).click()
      const freeResults = page.getByTestId('external-off-free-search-results')
      await expect(freeResults.locator('tbody tr')).toHaveCount(7)
      await expect(freeResults).toContainText('Vrij gezocht product 1')
      const freePaging = page.getByRole('navigation', { name: 'Paginering' })
      await freePaging.getByRole('button', { name: '3', exact: true }).click()
      await expect(freeResults.locator('tbody tr')).toHaveCount(2)
      await expect(freeResults).toContainText('Vrij gezocht product 16')
      await expect(page.locator('.rz-external-off-manual-header')).toHaveCount(0)
      const selectRow = async () => {
        if (width <= 720) await freeResults.locator('tbody tr').first().click()
        else await freeResults.locator('tbody tr').first().dblclick()
      }
      await selectRow()
      await expect(page.getByRole('alertdialog')).toHaveText(/Weet u zeker dat u dit artikel wilt koppelen\?\s*Annuleren\s*OK/)
      await expect(page.getByRole('alertdialog')).not.toContainText('Cataloguskoppeling bevestigen')
      await expect(page.getByRole('alertdialog')).not.toContainText('OFF kon')
      await page.getByRole('button', { name: 'Annuleren', exact: true }).click()
      await expect(page.getByRole('alertdialog')).toHaveCount(0)
      expect(links).toHaveLength(0)
      await freePaging.getByRole('button', { name: '1', exact: true }).click()
      await selectRow()
      await page.getByRole('button', { name: 'OK', exact: true }).click()
      await expect(page).toHaveURL(/\/externe-databases-2$/)
      await expect(page.getByTestId('external-off-link-outcome')).toHaveText('Artikel gekoppeld aan de Catalogus.')
      expect(links).toHaveLength(1)
      await expect(panel).toHaveCount(0)

      // A link that the server rejects must ALSO return to the overview;
      // it must not look successful or leave the user stuck in OFF search.
      linkResultMode = 'fail'
      await open(0)
      await expect(panel.getByRole('heading')).toContainText('Melk — Lidl')
      await panel.getByRole('button', { name: 'Zelf zoeken in OFF' }).click()
      await expect(page).toHaveURL(/\/externe-databases-2\/off-zoeken\//)
      await page.getByRole('textbox', { name: 'Omschrijving of barcode in OFF' }).fill('halfvolle melk bio')
      await page.getByRole('button', { name: 'Zoeken', exact: true }).click()
      await expect(freeResults.locator('tbody tr')).toHaveCount(7)
      await selectRow()
      await page.getByRole('button', { name: 'OK', exact: true }).click()
      await expect(page).toHaveURL(/\/externe-databases-2$/)
      await expect(page.getByTestId('external-off-link-outcome')).toContainText('Koppeling niet bevestigd: Officiële GS1-classificatie ontbreekt.')
      await expect(page.getByTestId('external-off-link-outcome')).toHaveAttribute('role', 'alert')
      await expect(panel.getByRole('heading')).toContainText('Melk — Lidl')
      expect(links).toHaveLength(2)
      await open(1)
      await expect(panel.getByRole('heading')).toContainText('Appels — Lidl')
      await expect(panel).toContainText('Geen passende productkandidaten gevonden.')
      await expect(panel).not.toContainText('Tweede suggestie')
      await expect(panel).not.toContainText('Lidl-product gevonden, maar geen barcode vermeld.')
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
        if (path === '/api/external-databases/articles-overview') return route.fulfill({ json: { items: rows, total: rows.length } })
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
      // Na zoeken blijft de nieuwe bulkselectie beschikbaar voor de ene
      // zichtbare rij; zonder selectie is exporteren terecht uitgeschakeld.
      await expect(table.getByRole('checkbox')).toHaveCount(1)
      await expect(table.getByRole('checkbox', { name: 'Selecteer Artikel 22' })).not.toBeChecked()
      // Inhuis policy: Exporteren is desktop-only at 720px and below.
      // The button remains in the DOM, but must be hidden on mobile.
      const exportButton = page.locator('button[data-mobile-export-action="true"]')
      await expect(exportButton).toHaveCount(1)
      if (width <= 720) await expect(exportButton).toBeHidden()
      else await expect(exportButton).toBeDisabled()
      await expect(page.getByRole('button', { name: 'Ontkoppelen', exact: true })).toBeDisabled()
      await expect(page.getByRole('button', { name: 'Afsluiten', exact: true })).toHaveCount(0)
      await expect(page.getByRole('button', { name: /Koppel|Zoek product|Zelf zoeken/ })).toHaveCount(0)
      expect(writes).toEqual([])
    })

    test(`Jumbo-kandidaten tonen compacte bron- en herkenningsteksten op ${width}px`, async ({ page }) => {
      await page.setViewportSize({ width, height: 900 })
      const notice = 'Producten gevonden bij Jumbo. De koppeling met het bonartikel is alleen op naam; controleer de suggesties.'
      await page.route('**/api/**', async (route) => {
        const path = new URL(route.request().url()).pathname
        if (path === '/api/session') return route.fulfill({ json: {
          user_id: 'jumbo-display-test', email: 'jumbo-display@example.test',
          active_household_id: '0', context_type: 'system', role: 'owner',
          is_platform_superuser: true, permissions: { 'platform.system_household.access': true },
        } })
        if (path === '/api/external-databases/articles-overview') return route.fulfill({ json: { items: [
          { id: 'receipt-table-line:jumbo-display', receipt_line_text: 'JUMBO FUET PLAKJES',
            retailer_code: 'jumbo', receipt_article_number: '123', quantity_label: '1' },
        ] } })
        if (path === '/api/external-databases/products/search-preview') return route.fulfill({ json: {
          provider: 'retailer_catalog', retailer_evidence: { source: 'Jumbo', status: 'name_suggestions', message: notice },
          results: [
            { gtin: '8710000000001', product_name: 'Jumbo Fuet plakjes', source: 'Jumbo', evidence_label: 'Winkelproduct; suggestie op naam', score: .9 },
            { gtin: '8710000000002', product_name: 'Fuet plakjes', source: 'Open Food Facts', evidence_label: 'Suggestie op artikelnaam', score: .8 },
            { gtin: '8710000000003', product_name: 'Jumbo Fuet 70 g', source: 'Jumbo + Open Food Facts', evidence_label: 'Artikelnummer en barcode bevestigd', score: 1 },
          ],
        } })
        if (path === '/api/onboarding') return route.fulfill({ json: { onboarding_status: 'completed' } })
        if (path === '/api/features') return route.fulfill({ json: { features: {} } })
        if (path === '/api/action-buttons') return route.fulfill({ json: { items: [] } })
        return route.fulfill({ json: {} })
      })
      await page.goto('/externe-databases-2')
      const row = page.getByTestId('external-databases-2-table').locator('tbody tr').first()
      if (width <= 720) await row.click()
      else await row.dblclick()
      const panel = page.getByTestId('external-databases-2-off-panel')
      const candidates = panel.getByTestId('external-databases-2-off-candidates')
      await expect(candidates.locator('tbody tr')).toHaveCount(3)
      await expect(candidates.locator('thead tr').first()).not.toContainText('Voorkeur')
      await expect(candidates.locator('tbody tr').first().locator('td').first()).toHaveText('1')
      await expect(candidates).toContainText('Alleen op artikelnaam')
      await expect(candidates).toContainText('Winkelproduct; alleen op naam')
      await expect(candidates).not.toContainText('Suggestie')
      await expect(candidates).toContainText('Jumbo + OFF')
      await expect(candidates).not.toContainText('Open Food Facts')
      await expect(panel.locator('.rz-external-databases-card--off > p')).toContainText('Open Food Facts (OFF)')
      await expect(panel.getByTestId('retailer-product-evidence')).toHaveCount(0)
      const spacing = await panel.locator('.rz-external-databases-card--off').evaluate((element) => ({
        gap: getComputedStyle(element).rowGap,
        introMarginTop: getComputedStyle(element.querySelector(':scope > p')).marginTop,
        introMarginBottom: getComputedStyle(element.querySelector(':scope > p')).marginBottom,
      }))
      expect(spacing).toEqual({ gap: '14px', introMarginTop: '0px', introMarginBottom: '0px' })
      await candidates.getByRole('textbox', { name: 'Filter op Bron' }).fill('OFF')
      await expect(candidates.locator('tbody tr')).toHaveCount(2)
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
  for (const width of [390, 1280]) {
    test('directe ED2-kandidaat bevestigen op ' + width + 'px', async ({ page }) => {
      await page.setViewportSize({ width, height: 900 })
      const item = { id: 'receipt-table-line:direct', receipt_line_text: 'Aardappel iets kruimig',
        retailer_code: 'lidl', receipt_article_number: '0083242', link_status: 'unlinked' }
      const gtin = '8718452504435'
      let saved = false
      let noProof = false
      let incompatible = false
      const writes = []
      const lookups = []
      await page.route('**/api/**', async (route) => {
        const request = route.request()
        const path = new URL(request.url()).pathname
        if (path === '/api/session') return route.fulfill({ json: {
          user_id: 'ed2-test', active_household_id: '0', context_type: 'system', role: 'owner',
          is_platform_superuser: true, permissions: { 'platform.system_household.access': true },
        } })
        if (path === '/api/maintenance/status') return route.fulfill({ json: { state: 'normal' } })
        if (path === '/api/onboarding') return route.fulfill({ json: { onboarding_status: 'completed' } })
        if (path === '/api/features') return route.fulfill({ json: { features: {} } })
        if (path === '/api/action-buttons') return route.fulfill({ json: { items: [] } })
        if (path === '/api/external-databases/articles-overview') return route.fulfill({ json: {
          items: [{ ...item, link_status: saved ? 'classification_pending' : 'unlinked',
            article_code: saved ? gtin : '' }],
          counts: { unlinked: saved ? 0 : 1, classification_pending: saved ? 1 : 0, linked: 0 },
        } })
        if (path === '/api/external-databases/products/search-preview') return route.fulfill({ json: {
          provider: 'openfoodfacts', mutated: false,
          results: [{ gtin, product_name: 'Aardappelen iets kruimig', brand: 'Testmerk',
            source: 'Open Food Facts', evidence_label: 'Suggestie op artikelnaam', score: 0.85 }],
        } })
        if (path === '/api/external-products/off/search') {
          lookups.push(request.postDataJSON())
          return route.fulfill({ json: { provider: 'off_exact_gtin',
            results: noProof ? [] : [{ gtin, product_name: 'Aardappelen iets kruimig',
              brand: 'Testmerk', selection_proof: 'receipt-bound-proof',
              identity_compatible: !incompatible }] } })
        }
        if (path === '/api/external-databases/off/link-selected') {
          writes.push(request.postDataJSON())
          saved = true
          return route.fulfill({ json: { cataloged: true, classification_pending: true } })
        }
        return route.fulfill({ json: {} })
      })
      await page.goto('/externe-databases-2')
      const table = page.getByTestId('external-databases-2-table')
      const article = table.locator('tbody tr').first()
      if (width <= 720) await article.click()
      else await article.dblclick()
      const candidate = page.getByTestId('external-databases-2-off-candidates').locator('tbody tr').first()
      await expect(candidate).toContainText(gtin)
      expect(writes).toHaveLength(0)
      const select = async () => width <= 720 ? candidate.click() : candidate.dblclick()
      // Preview candidates without signed OFF evidence must not be linked.
      noProof = true
      await select()
      await expect(page.getByRole('alert')).toContainText('kon niet in OFF worden bevestigd')
      expect(writes).toHaveLength(0)
      noProof = false
      incompatible = true
      await select()
      await expect(page.getByRole('alert')).toContainText('past niet veilig')
      expect(writes).toHaveLength(0)
      incompatible = false
      await select()
      await expect(page.getByRole('alertdialog')).toContainText('Testmerk')
      await expect(page.getByRole('alertdialog')).toContainText(gtin)
      expect(writes).toHaveLength(0)
      await page.getByRole('button', { name: 'Annuleren' }).click()
      await expect(page.getByRole('alertdialog')).toHaveCount(0)
      expect(writes).toHaveLength(0)
      await select()
      await page.getByRole('button', { name: 'OK', exact: true }).click()
      await expect(page.getByTestId('external-off-link-outcome')).toContainText('GS1-classificatie ontbreekt nog')
      await expect(table).toContainText(gtin)
      await expect(page.getByRole('button', { name: 'Classificatie ontbreekt: 1' })).toBeVisible()
      expect(lookups).toHaveLength(4)
      expect(lookups[0]).toEqual({ receipt_item_id: item.id, mode: 'manual', gtin, limit: 20 })
      expect(writes).toEqual([{ receipt_item_id: item.id, gtin, selection_proof: 'receipt-bound-proof' }])
    })
  }

});


test.describe('ED2 barcode identity mismatch uses central overlay', () => {
  test.use({ storageState: { cookies: [], origins: [] } })

  test('incompatible OFF barcode shows Melding instead of a text row under the barcode field', async ({ page }) => {
    const article = {
      id: 'receipt-table-line:ah-toetenv-test',
      receipt_line_text: 'AH TOETENV',
      retailer_code: 'ah',
      receipt_article_number: '48291',
      article_code: '',
      link_status: 'unlinked',
    }
    const barcode = '5099514002476'
    const attempts = []
    await page.route('**/api/**', async (route) => {
      const request = route.request()
      const url = new URL(request.url())
      if (url.pathname === '/api/session') return route.fulfill({ json: {
        user_id: 'test-superuser', active_household_id: '0',
        context_type: 'system', role: 'owner', is_platform_superuser: true,
        permissions: { 'platform.system_household.access': true },
      } })
      if (url.pathname === '/api/maintenance/status') return route.fulfill({ json: { state: 'normal' } })
      if (url.pathname === '/api/onboarding') return route.fulfill({ json: { onboarding_status: 'completed' } })
      if (url.pathname === '/api/features') return route.fulfill({ json: { features: {} } })
      if (url.pathname === '/api/action-buttons') return route.fulfill({ json: { items: [] } })
      if (url.pathname === '/api/external-databases/articles-overview') return route.fulfill({ json: {
        items: [article], total: 1,
        counts: { unlinked: 1, linked: 0, classification_pending: 0 },
      } })
      if (url.pathname === '/api/external-databases/products/search-preview') return route.fulfill({
        json: { results: [], provider: 'none' },
      })
      if (url.pathname === '/api/catalog/ed2/manual-barcodes') {
        attempts.push(request.postDataJSON())
        return route.fulfill({ status: 409, json: {
          detail: 'De OFF-productgegevens passen niet veilig bij dit bonartikel. Er is niets opgeslagen.',
        } })
      }
      return route.fulfill({ json: {} })
    })

    await page.goto('/externe-databases-2')
    await page.getByTestId('external-databases-2-table')
      .locator('tbody tr', { hasText: 'AH TOETENV' }).dblclick()
    await page.getByRole('button', { name: 'Zelf zoeken in OFF' }).click()
    const input = page.getByTestId('ed2-manual-barcode-input')
    await expect(input).toBeVisible()
    await input.fill(barcode)
    await page.getByTestId('ed2-manual-barcode-save').click()
    await page.getByRole('alertdialog').getByRole('button', { name: 'OK' }).click()

    const message = page.getByTestId('ed2-manual-barcode-error')
    await expect(message).toBeVisible()
    await expect(message).toContainText('De gegevens van deze barcode komen niet voldoende overeen')
    await expect(message).toContainText('Er is niets opgeslagen')
    await expect(page.getByTestId('ed2-manual-barcode-entry').locator('p[role="alert"]')).toHaveCount(0)
    await expect(input).toHaveValue(barcode)
    expect(attempts).toEqual([{ receipt_item_id: article.id, gtin: barcode }])
  })
})
