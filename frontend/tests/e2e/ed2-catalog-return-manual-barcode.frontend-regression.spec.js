import { test, expect } from '@playwright/test'
import { buildArticleRelationshipGraph } from '../../src/features/externalDatabases/articleRelationshipModel.js'

test.use({ storageState: { cookies: [], origins: [] } })

// Mock the asynchronous, authenticated background-job contract. These tests
// must not depend on the retired synchronous /bonnamen-matchen/auto endpoint.
function matchingJob({ state = 'completed', matched = 0, pass = 1,
                       checked = 0, total = 0, checkNumber = 0 } = {}) {
  return {
    ok: true, id: 'playwright-match-job', state,
    phase: state === 'completed' ? 'afgerond' : 'controleren',
    pass_number: pass, check_number: checkNumber,
    checks_completed: checked === total ? checkNumber : Math.max(0, checkNumber - 1),
    estimated_checks: 5 * pass, overall_percent: state === 'completed' ? 100 : 0,
    checked, total, matched, error: '',
  }
}

function bootstrap(route, rows, manualRows, onSave) {
  const url = new URL(route.request().url())
  const path = url.pathname
  if (path === '/api/session') return route.fulfill({ json: {
    user_id: 'test-ed2-keeper', active_household_id: '0', context_type: 'system',
    role: 'owner', is_platform_superuser: true,
    permissions: { 'platform.system_household.access': true },
  } })
  if (path === '/api/maintenance/status') return route.fulfill({ json: { state: 'normal' } })
  if (path === '/api/onboarding') return route.fulfill({ json: { onboarding_status: 'completed' } })
  if (path === '/api/features') return route.fulfill({ json: { features: {} } })
  if (path === '/api/action-buttons') return route.fulfill({ json: { items: [] } })
  if (path === '/api/external-databases/articles-overview') return route.fulfill({ json: {
    items: rows.map((row) => ({
      ...row,
      manual_barcode: manualRows.find((saved) =>
        saved.receipt_item_id === row.id)?.gtin || '',
    })),
    total: rows.length,
    counts: { unlinked: rows.length, classification_pending: 0, linked: 0 },
  } })
  if (path === '/api/catalog/ed2/bonnamen-matchen/progress')
    return route.fulfill({ json: { ok: false, state: 'not_started' } })
  if (path === '/api/catalog/ed2/bonnamen-matchen/progress/start')
    return route.fulfill({ json: matchingJob() })
  if (path === '/api/catalog/ed2/manual-barcodes') {
    if (route.request().method() === 'GET') return route.fulfill({ json: { items: manualRows } })
    return onSave(route)
  }
  if (path === '/api/external-databases/products/search-preview') return route.fulfill({ json: {
    provider: 'none', results: [],
  } })
  if (path === '/api/catalog') {
    const search = url.searchParams.get('name')?.toLowerCase() || ''
    const offset = Number(url.searchParams.get('offset') || 0)
    const matches = Array.from({ length: 12 }, (_, i) => ({
      id: 'catalog-' + (i + 1), name: 'Melk ' + String(i + 1).padStart(2, '0'),
      catalog_kind: 'exact', brand: 'Test', primary_gtin: '',
    })).filter((row) => row.name.toLowerCase().includes(search))
    return route.fulfill({ json: { items: matches.slice(offset, offset + 10), total: matches.length } })
  }
  if (path.startsWith('/api/catalog/catalog-')) return route.fulfill({ json: {
    product: { id: path.split('/').at(-1), name: 'Melk detail', primary_gtin: '', status: 'active' },
    identities: [], household_articles: [], receipt_lines: [],
  } })
  return route.fulfill({ json: {} })
}

test('ED2 toont alleen drie statustellers bij actieve tabel- en statusfilters', async ({ page }) => {
  const article = {
    id: 'receipt-table-line:counter-filter', receipt_line_text: 'Scharrelei M/L',
    retailer_code: 'jumbo', retailer: 'Jumbo', receipt_article_number: '533',
    article_code: '', link_status: 'unlinked',
  }
  await page.route('**/api/**', (route) => bootstrap(route, [article], [], () =>
    route.fulfill({ json: {} })))
  await page.goto('/externe-databases-2')
  await page.getByTestId('classification-work-monitor').getByRole('button', { name: 'Identificeren' }).click()
  const counters = page.locator('.rz-external-ed2-counters')
  await expect(counters.locator('button')).toHaveCount(3)
  await expect(counters).toContainText('Niet gekoppeld: 1')
  await expect(counters).toContainText('Classificatie ontbreekt: 0')
  await expect(counters).toContainText('Gekoppeld: 0')
  await page.getByRole('textbox', { name: 'Filter op Artikel' }).fill('Scharrelei')
  await expect(counters.locator('button')).toHaveCount(3)
  const unlinked = counters.getByRole('button', { name: 'Niet gekoppeld: 1' })
  await unlinked.click()
  await expect(unlinked).toHaveAttribute('aria-pressed', 'true')
  await expect(counters.locator('button')).toHaveCount(3)
  await unlinked.click()
  await expect(unlinked).toHaveAttribute('aria-pressed', 'false')
  await expect(counters.locator('button')).toHaveCount(3)
  await expect(page.getByRole('textbox', { name: 'Filter op Artikel' })).toHaveValue('Scharrelei')
  await expect(page.getByTestId('external-databases-2-table')).toContainText('Scharrelei M/L')
})

test('ED2 houdt een camerafout zichtbaar en biedt fotoherkenning alleen als reserveoptie', async ({ page }) => {
  const item = {
    id: 'receipt-table-line:camera-error', receipt_line_text: 'Scharrelei M/L',
    retailer_code: 'jumbo', receipt_article_number: '777',
    article_code: '', link_status: 'unlinked',
  }
  let saveRequests = 0
  await page.addInitScript(() => {
    let attempts = 0
    Object.defineProperty(navigator, 'mediaDevices', {
      configurable: true,
      value: {
        getUserMedia: () => {
          attempts += 1
          return Promise.reject(new DOMException('Could not start video source', 'NotReadableError'))
        },
        enumerateDevices: () => Promise.resolve([]),
      },
    })
    window.__ed2GetUserMediaAttempts = () => attempts
  })
  await page.route('**/api/**', (route) => bootstrap(route, [item], [], (request) => {
    saveRequests += 1
    return request.fulfill({ json: {} })
  }))
  // Enter the mobile flow before opening an article: changing viewport after
  // selecting it can remount the page and intentionally clear selectedItem.
  await page.setViewportSize({ width: 390, height: 844 })
  await page.goto('/externe-databases-2')
  await page.getByTestId('classification-work-monitor').getByRole('button', { name: 'Identificeren' }).click()
  await page.getByTestId('external-databases-2-table')
    .locator('tbody tr', { hasText: 'Scharrelei M/L' }).click()
  const panel = page.getByTestId('external-databases-2-off-panel')
  await expect(panel.getByTestId('ed2-article-barcode-scan')).toBeVisible()
  await expect(panel.getByRole('button', { name: 'Barcode uit foto' })).toHaveCount(0)
  await panel.getByTestId('ed2-article-barcode-scan').click()
  const scanner = page.getByTestId('barcode-scanner-backdrop')
  await expect(scanner).toBeVisible()
  // The shared scanner uses the canonical app-wide feedback overlay and
  // keeps recovery and photo fallbacks available after a camera failure.
  const warning = page.getByTestId('app-feedback-error-overlay')
  await expect(warning).toBeVisible()
  await expect(scanner.getByTestId('barcode-camera-recovery-help')).toContainText(/camera/i)
  await warning.getByRole('button', { name: 'OK' }).click()
  await expect(scanner.locator('.rz-inline-feedback')).toHaveCount(0)
  await expect(scanner.getByRole('button', { name: 'Camera opnieuw proberen' })).toBeVisible()
  await expect(scanner.getByRole('button', { name: 'Barcode uit foto' })).toBeVisible()
  await expect(scanner).toContainText('Geen werkende camera? Kies Barcode uit foto')
  const initialAttempts = await page.evaluate(() => window.__ed2GetUserMediaAttempts())
  expect(initialAttempts).toBeGreaterThan(0)
  // No automatic permission/compatibility rewrite without explicit action.
  await scanner.getByRole('button', { name: 'Camera opnieuw proberen' }).click()
  await expect(page.getByTestId('app-feedback-error-overlay')).toBeVisible()
  await expect(scanner.getByTestId('barcode-camera-recovery-help')).toContainText(/camera/i)
  await expect.poll(() => page.evaluate(() => window.__ed2GetUserMediaAttempts())).toBeGreaterThan(initialAttempts)
  await page.getByTestId('app-feedback-error-overlay').getByRole('button', { name: 'OK' }).click()
  await scanner.getByRole('button', { name: 'Camera sluiten' }).click()
  await expect(scanner).toHaveCount(0)
  await expect(panel.getByRole('button', { name: 'Barcode uit foto' })).toHaveCount(0)
  expect(saveRequests).toBe(0)
})

test('Een bevestigde barcode koppelt zonder OFF-match aan Catalogus, onafhankelijk van classificatie', async ({ page }) => {
  const item = {
    id: 'receipt-table-line:manual-code-test', receipt_line_text: 'Melk zonder code',
    retailer_code: 'jumbo', receipt_article_number: '123',
    article_code: '', link_status: 'unlinked', quantity_label: '1 l',
  }
  const stored = []
  const requests = []
  await page.route('**/api/**', (route) => bootstrap(route, [item], stored, (request) => {
    const body = request.request().postDataJSON()
    requests.push(body)
    stored.push({ receipt_item_id: item.id, retailer_code: 'jumbo',
      receipt_text_normalized: 'melk zonder code',
      external_article_code: '123', gtin: body.gtin })
    return request.fulfill({ json: { saved: true, gtin: body.gtin,
      source: 'manual', catalog_linked: true, catalog_product_created: true,
      off_found: false, classification_pending: false, photo_loaded: false } })
  }))
  await page.goto('/externe-databases-2')
  await page.getByTestId('classification-work-monitor').getByRole('button', { name: 'Identificeren' }).click()
  const table = page.getByTestId('external-databases-2-table')
  await expect(table).toContainText('Melk zonder code')
  await table.locator('tbody tr', { hasText: 'Melk zonder code' }).dblclick()
  const scanActions = page.getByTestId('external-databases-2-off-panel').locator('.rz-external-databases-actions')
  await expect(scanActions.getByRole('button', { name: 'Zelf zoeken in OFF' })).toBeVisible()
  // Desktop keeps manual entry; the article scanner is mobile-only.
  await expect(scanActions.getByTestId('ed2-article-barcode-scan')).toHaveCount(0)
  await page.getByTestId('ed2-manual-barcode-input').fill('8718452504435')
  await page.getByTestId('ed2-manual-barcode-save').click()
  await page.getByRole('alertdialog').getByRole('button', { name: 'OK' }).click()
  await expect(page.getByTestId('app-feedback-success')).toContainText('Barcode opgeslagen en gekoppeld aan een nieuw Catalogusproduct.')
  await expect(table).toContainText('8718452504435')
  await expect(page.getByRole('button', { name: 'Niet gekoppeld: 1' })).toBeVisible()
  expect(requests).toEqual([{ receipt_item_id: item.id, gtin: '8718452504435' }])
  const cells = table.locator('tbody tr').first().locator('td')
  await expect(cells.nth(4)).toHaveText('8718452504435')
  await expect(cells.nth(4).locator('span')).toHaveAttribute('title', /Handmatig ingevoerde barcode/)
  await expect(cells.nth(5)).toHaveText('Nog identificeren')
  await expect(cells.nth(6)).toHaveText('Niet gekoppeld')
  await expect(table.locator('thead')).toContainText('Art./Barcode')
})

test('Catalogusidentificatie blijft bij OFF-storing mogelijk en behoudt het bestaande filter', async ({ page }) => {
  const item = {
    id: 'receipt-table-line:manual-off-outage', receipt_line_text: 'SIMON LEVELT',
    retailer_code: 'ah', receipt_article_number: '768682',
    article_code: '', link_status: 'unlinked',
  }
  const stored = []
  let offSearchCalls = 0
  await page.route('**/api/**', (route) => {
    if (new URL(route.request().url()).pathname === '/api/external-products/off/search') {
      offSearchCalls += 1
      return route.fulfill({ status: 503, json: { detail: 'OFF tijdelijk onbereikbaar' } })
    }
    return bootstrap(route, [item], stored, (request) => {
      const code = request.request().postDataJSON().gtin
      stored.push({ receipt_item_id: item.id, retailer_code: 'albert-heijn',
        receipt_text_normalized: 'simon levelt',
        external_article_code: '768682', gtin: code })
      return request.fulfill({ json: {
        saved: true, source: 'manual', gtin: code, catalog_linked: true,
        catalog_product_created: false, off_found: false, off_unavailable: true,
        classification_pending: false, photo_loaded: false,
      } })
    })
  })
  await page.goto('/externe-databases-2')
  await page.getByTestId('classification-work-monitor').getByRole('button', { name: 'Identificeren' }).click()
  const table = page.getByTestId('external-databases-2-table')
  await page.getByRole('textbox', { name: 'Filter op Artikel' }).fill('SIMON')
  await table.locator('tbody tr', { hasText: 'SIMON LEVELT' }).dblclick()
  await page.getByTestId('ed2-manual-barcode-input').fill('8711138357776')
  await page.getByTestId('ed2-manual-barcode-save').click()
  await page.getByRole('alertdialog').getByRole('button', { name: 'OK' }).click()
  await expect(page.getByTestId('app-feedback-success')).toContainText('Barcode opgeslagen en gekoppeld aan het bestaande Catalogusproduct.')
  await expect(page.getByRole('textbox', { name: 'Filter op Artikel' })).toHaveValue('SIMON')
  await expect(table.locator('thead')).toContainText('Art./Barcode')
  await expect(table.locator('tbody tr', { hasText: 'SIMON LEVELT' }).locator('td').nth(4)).toHaveText('8711138357776')
  await expect(page.getByRole('button', { name: 'Niet gekoppeld: 1' })).toBeVisible()
  await page.reload()
  await expect(page.getByRole('textbox', { name: 'Filter op Artikel' })).toHaveValue('SIMON')
  await expect(table.locator('tbody tr', { hasText: 'SIMON LEVELT' }).locator('td').nth(4)).toHaveText('8711138357776')
  expect(offSearchCalls).toBe(0) // Barcode-opslag blijft OFF-onafhankelijk.
})

test('ED2 keert van handmatig OFF zoeken terug naar dezelfde gefilterde pagina', async ({ page }) => {
  const rows = Array.from({ length: 12 }, (_, i) => ({
    id: 'receipt-table-line:ed2-page-' + (i + 1),
    receipt_line_text: 'Melk ' + String(i + 1).padStart(2, '0'),
    retailer_code: 'jumbo', receipt_article_number: String(100 + i),
    article_code: '', link_status: 'unlinked',
  }))
  await page.route('**/api/**', (route) => bootstrap(route, rows, [], () => route.fulfill({ json: {} })))
  await page.goto('/externe-databases-2')
  await page.getByTestId('classification-work-monitor').getByRole('button', { name: 'Identificeren' }).click()
  const table = page.getByTestId('external-databases-2-table')
  await page.getByRole('textbox', { name: 'Filter op Artikel' }).fill('Melk')
  await page.getByRole('navigation', { name: 'Paginering' }).getByRole('button', { name: '+' }).click()
  await expect(page.getByLabel('Pagina 2 van 2')).toBeVisible()
  await expect(table).toContainText('Melk 12')
  await table.locator('tbody tr', { hasText: 'Melk 12' }).dblclick()
  await page.getByRole('button', { name: 'Zelf zoeken in OFF' }).click()
  await expect(page.getByRole('textbox', { name: 'Omschrijving of barcode in OFF' })).toBeVisible()
  await page.goBack()
  await expect(page.getByRole('textbox', { name: 'Filter op Artikel' })).toHaveValue('Melk')
  await expect(page.getByLabel('Pagina 2 van 2')).toBeVisible()
  await expect(table).toContainText('Melk 12')
})

test('Catalogus opent detail en herstelt de desktopfilter en tabelpagina bij browser Terug', async ({ page }) => {
  await page.setViewportSize({ width: 1400, height: 850 })
  await page.route('**/api/**', (route) => bootstrap(route, [], [], () => route.fulfill({ json: {} })))
  await page.goto('/catalogus')
  const table = page.getByTestId('catalog-table')
  await page.getByPlaceholder('Zoek', { exact: true }).fill('Melk')
  await expect(table).toContainText('Melk 01')
  await page.getByRole('navigation', { name: 'Paginering' }).getByRole('button', { name: '+' }).click()
  await expect(page.getByLabel('Pagina 2 van 2')).toBeVisible()
  await table.getByTestId('catalog-row-catalog-12').dblclick()
  await expect(page.getByTestId('catalog-detail-page')).toBeVisible()
  await page.goBack()
  await expect(page.getByPlaceholder('Zoek', { exact: true })).toHaveValue('Melk')
  await expect(page.getByLabel('Pagina 2 van 2')).toBeVisible()
  await expect(table.getByTestId('catalog-row-catalog-12')).toBeVisible()
})



test('AH CERVELAAT: kandidaat 4 laat bevestigen toe en echte merkconflicten krijgen Melding-overlay', async ({ page }) => {
  const item = {
    id: 'receipt-table-line:ah-cervelaat', receipt_line_text: 'AH CERVELAAT',
    retailer_code: 'ah', receipt_article_number: '718410',
    article_code: '', link_status: 'unlinked',
  }
  const target = {
    gtin: '2323685801969', product_name: 'Cervelaat', brand: 'AlbertHeijn',
    score: 0.85, identity_compatible: true, selection_proof: 'signed-ah-cervelaat',
  }
  const writes = []
  let saved = false
  await page.route('**/api/**', (route) => {
    const path = new URL(route.request().url()).pathname
    if (path === '/api/external-products/off/search') return route.fulfill({ json: {
      provider: 'openfoodfacts', mutated: false, results: [
        { gtin: '2385429202951', product_name: 'Scharrel kip cervelaat',
          brand: 'Albert Heijn', score: 0.88, identity_compatible: true, selection_proof: 'first' },
        { gtin: '8718907651172', product_name: 'Gerookte cervelaat',
          brand: 'Albert Heijn', score: 0.88, identity_compatible: true, selection_proof: 'second' },
        { gtin: '4056489977186', product_name: 'Cervelaat', brand: 'Jumbo',
          score: 0.86, identity_compatible: false,
          identity_conflict_reason: 'private_label_brand_conflict',
          selection_proof: 'signed-ah-cervelaat-jumbo',
          identity_conflict_message: 'AH CERVELAAT is een Albert Heijn huismerk. Het geselecteerde product is van Jumbo.' },
        target,
      ],
    } })
    if (path === '/api/external-databases/off/link-selected') {
      writes.push(route.request().postDataJSON())
      saved = true
      return route.fulfill({ json: { cataloged: true, classification_pending: true } })
    }
    return bootstrap(route, [{
      ...item, article_code: saved ? target.gtin : '',
      link_status: saved ? 'classification_pending' : 'unlinked',
    }], [], () => route.fulfill({ status: 405, json: {} }))
  })
  await page.goto('/externe-databases-2')
  await page.getByTestId('classification-work-monitor').getByRole('button', { name: 'Identificeren' }).click()
  await page.getByTestId('external-databases-2-table')
    .locator('tbody tr', { hasText: 'AH CERVELAAT' }).dblclick()
  await page.getByRole('button', { name: 'Zelf zoeken in OFF' }).click()
  await page.getByRole('textbox', { name: 'Omschrijving of barcode in OFF' }).fill('cervelaat albert heijn')
  await page.getByRole('button', { name: 'Zoeken', exact: true }).click()
  const candidates = page.getByTestId('external-off-free-search-results')
  await candidates.locator('tbody tr', { hasText: 'Jumbo' }).dblclick()
  const warning = page.getByTestId('ed2-private-label-override-warning-overlay')
  await expect(warning).toBeVisible()
  await expect(page.getByTestId('ed2-private-label-override-warning')).toContainText('Het geselecteerde product is van Jumbo.')
  await expect(page.getByTestId('ed2-private-label-override-warning')).toContainText('Waarschuwing bij koppelen')
  expect(writes).toHaveLength(0)
  await page.getByTestId('ed2-private-label-override-warning').getByRole('button', { name: 'Annuleren' }).click()
  await expect(warning).toHaveCount(0)
  expect(writes).toHaveLength(0)
  await candidates.locator('tbody tr', { hasText: target.gtin }).dblclick()
  await expect(page.getByRole('alertdialog')).toContainText('Weet u zeker')
  await page.getByRole('alertdialog').getByRole('button', { name: 'OK' }).click()
  await expect(page).toHaveURL(/\/externe-databases-2$/)
  await expect(page.getByTestId('app-feedback-success')).toContainText('GS1-classificatie ontbreekt nog')
  expect(writes).toEqual([{
    receipt_item_id: item.id, gtin: target.gtin, selection_proof: target.selection_proof,
  }])
})

test('Jumbo Pindakaas: een door de server geweigerde kandidaat toont Melding en vult geen barcode in', async ({ page }) => {
  const item = {
    id: 'receipt-table-line:jumbo-pindakaas', receipt_line_text: 'Pindakaas',
    retailer_code: 'jumbo', receipt_article_number: 'JUMBO-SEED-3',
    article_code: '', link_status: 'unlinked',
  }
  const gtin = '8711200428953'
  let linkRequests = 0
  await page.route('**/api/**', (route) => {
    const path = new URL(route.request().url()).pathname
    if (path === '/api/external-databases/products/search-preview') return route.fulfill({ json: {
      provider: 'openfoodfacts', results: [
        { gtin, product_name: 'Calvé Pindakaas Regular 350 g', brand: 'Calvé',
          source: 'Jumbo', score: 0.88 },
      ],
    } })
    if (path === '/api/external-products/off/search') return route.fulfill({ json: {
      results: [{ gtin, product_name: 'Calvé Pindakaas Regular 350 g',
        brand: 'Calvé', selection_proof: 'signed-jumbo-pindakaas',
        identity_compatible: true }],
    } })
    if (path === '/api/external-databases/off/link-selected') {
      linkRequests += 1
      return route.fulfill({ status: 422, json: {
        detail: 'De centrale Cataloguskoppeling kon niet worden bevestigd.',
      } })
    }
    return bootstrap(route, [item], [], () => route.fulfill({ json: {} }))
  })
  await page.goto('/externe-databases-2')
  await page.getByTestId('classification-work-monitor').getByRole('button', { name: 'Identificeren' }).click()
  const table = page.getByTestId('external-databases-2-table')
  await table.locator('tbody tr', { hasText: 'Pindakaas' }).dblclick()
  await page.getByTestId('external-databases-2-off-candidates')
    .locator('tbody tr', { hasText: gtin }).dblclick()
  await expect(page.getByRole('alertdialog')).toContainText('Calvé Pindakaas')
  await page.getByRole('alertdialog').getByRole('button', { name: 'OK' }).click()
  const warning = page.getByTestId('app-feedback-error-overlay')
  await expect(warning).toBeVisible()
  await expect(page.getByTestId('app-feedback-error')).toContainText('Melding')
  await expect(page.getByTestId('app-feedback-error')).toContainText(
    'Koppeling niet bevestigd: De centrale Cataloguskoppeling kon niet worden bevestigd.',
  )
  await expect(table.locator('tbody tr', { hasText: 'Pindakaas' }).locator('td').nth(4)).toBeEmpty()
  await expect(page.getByRole('button', { name: 'Niet gekoppeld: 1' })).toBeVisible()
  expect(linkRequests).toBe(1)
})


test('Identificeren: historische bewaarde barcode toont aparte status en vraagt veilig herstel', async ({ page }) => {
  const original = {
    id: 'receipt-table-line:history', receipt_line_text: 'Courgette groen',
    retailer_code: 'lidl', receipt_article_number: '0082346',
    article_code: '', link_status: 'unlinked', manual_barcode: '2008234600001',
    identity_status: 'saved_only',
    identity_status_label: 'Barcode bewaard - Catalogus herstellen',
    identity_repairable: true,
  }
  const rows = [original]
  const manualRows = [{ receipt_item_id: original.id, gtin: original.manual_barcode }]
  let confirms = 0
  await page.route('**/api/**', route => {
    const path = new URL(route.request().url()).pathname
    if (path === '/api/catalog/ed2/manual-barcodes/materialize-existing') {
      confirms += 1
      expect(route.request().postDataJSON().selections).toEqual([
        { receipt_item_id: original.id, gtin: original.manual_barcode },
      ])
      rows[0] = { ...rows[0], identity_status: 'catalog_linked',
        identity_status_label: 'Catalogus gekoppeld',
        identity_repairable: false }
      return route.fulfill({ json: { ok: true, processed: 1, catalog_links_created: 1,
        already_confirmed: 0, catalog_products_created: 1 } })
    }
    return bootstrap(route, rows, manualRows, () => route.fulfill({ json: {} }))
  })
  await page.goto('/externe-databases-2')
  await page.getByTestId('classification-work-monitor').getByRole('button', { name: 'Identificeren' }).click()
  const table = page.getByTestId('external-databases-2-table')
  await expect(table).toContainText('Barcode bewaard - Catalogus herstellen')
  await expect(table).toContainText('Niet gekoppeld')
  expect(confirms).toBe(0)
  await page.getByRole('button', { name: 'Bewaarde barcodes koppelen' }).click()
  // The central AppFeedbackProvider uses role=dialog for action prompts,
  // unlike the older local alertdialog used by the barcode save flow.
  const confirmation = page.getByTestId('ed2-materialize-existing-confirm')
  await expect(confirmation).toHaveAttribute('role', 'dialog')
  await expect(confirmation).toContainText('1 eerder opgeslagen barcode')
  expect(confirms).toBe(0)
  await confirmation.getByRole('button', { name: 'Koppelen' }).click()
  await expect.poll(() => confirms).toBe(1)
  await expect(table).toContainText('Catalogus gekoppeld')
})



test('Courgette-identificatie zonder barcode vraagt bevestiging, geel wordt afzonderlijk synoniem', async ({ page }) => {
  const rows = [
    { id: 'receipt-table-line:green', receipt_line_text: 'Courgette groen',
      retailer_code: 'lidl', receipt_article_number: '0082346',
      article_code: '', manual_barcode: '', identity_status: 'not_identified',
      automatic_match_review_reason: 'Meerdere bewezen courgette-uitvoeringen. Kies het juiste product.',
      identity_status_label: 'Nog identificeren', link_status: 'unlinked' },
    { id: 'receipt-table-line:yellow', receipt_line_text: 'Courgette geel',
      retailer_code: 'lidl', receipt_article_number: '0082293',
      article_code: '', manual_barcode: '', identity_status: 'not_identified',
      automatic_match_review_reason: 'Meerdere bewezen courgettevarianten. Kies het juiste product.',
      identity_status_label: 'Nog identificeren', link_status: 'unlinked' },
    { id: 'receipt-table-line:baby', receipt_line_text: 'Olvarit 8+ Maanden Courgette',
      retailer_code: 'ah', receipt_article_number: '',
      article_code: '', manual_barcode: '', identity_status: 'not_identified',
      identity_status_label: 'Nog identificeren', link_status: 'unlinked' },
  ]
  const saved = []
  const posts = []
  await page.route('**/api/**', (route) => {
    const url = new URL(route.request().url())
    if (url.pathname === '/api/catalog/ed2/courgette-family/options') {
      const isYellow = url.searchParams.get('receipt_item_id') === 'receipt-table-line:yellow'
      return route.fulfill({ json: { family: 'verse_courgette_v1', options: [{
        product_id: 'ah-courgette', product_name: 'AH Courgette',
        mode: isYellow ? 'synonym_variant' : 'same_product',
        mode_label: isYellow ? 'Afzonderlijke variant als synoniem' : 'Zelfde verse courgette',
        fingerprint: (isYellow ? 'a' : 'b').repeat(64),
      }] } })
    }
    if (url.pathname === '/api/catalog/ed2/courgette-family/confirm') {
      const payload = route.request().postDataJSON()
      posts.push(payload)
      const row = rows.find((item) => item.id === payload.receipt_item_id)
      if (row) {
        row.identity_status = 'catalog_linked'
        row.identity_status_label = 'Catalogus gekoppeld'
      }
      return route.fulfill({ json: { ok: true, barcode_written: false,
        synonym_created: payload.match_mode === 'synonym_variant',
      } })
    }
    return bootstrap(route, rows, [], (request) => request.fulfill({ json: {} }))
  })
  await page.goto('/externe-databases-2')
  await page.getByTestId('classification-work-monitor').getByRole('button', { name: 'Matchen' }).click()
  const table = page.getByTestId('ed2-match-left-table')
  await table.locator('tbody tr', { hasText: 'Courgette groen' }).click()
  const family = page.getByRole('region', { name: 'Courgettefamilie koppelen zonder barcode' })
  await expect(family).toBeVisible()
  expect(posts).toHaveLength(0)
  await family.getByLabel('Bestaand Catalogusproduct').selectOption('b'.repeat(64))
  await family.getByRole('button', { name: 'Bonartikel koppelen' }).click()
  await expect(page.getByTestId('ed2-curated-family-confirm')).toContainText('Courgette groen')
  expect(posts).toHaveLength(0)
  await page.getByTestId('ed2-curated-family-confirm').getByRole('button', { name: 'Bevestigen' }).click()
  await expect.poll(() => posts.length).toBe(1)
  expect(posts[0].match_mode).toBe('same_product')

  await table.locator('tbody tr', { hasText: 'Courgette geel' }).click()
  const yellow = page.getByRole('region', { name: 'Courgettefamilie koppelen zonder barcode' })
  await yellow.getByLabel('Bestaand Catalogusproduct').selectOption('a'.repeat(64))
  await yellow.getByRole('button', { name: 'Variant als synoniem bevestigen' }).click()
  await page.getByTestId('ed2-curated-family-confirm').getByRole('button', { name: 'Bevestigen' }).click()
  await expect.poll(() => posts.length).toBe(2)
  expect(posts[1].match_mode).toBe('synonym_variant')
  await expect(table).not.toContainText('Olvarit')
  await expect(page.getByRole('region', { name: 'Courgettefamilie koppelen zonder barcode' })).toHaveCount(0)
})


test('ED2: zes courgettes in één gecontroleerde batch, zonder fictieve barcode', async ({ page }) => {
  const articles = [
    ['ah-linked','COURGETTE','ah','21003','catalog_linked'],
    ['ah','COURGETTE','ah','','not_identified'],
    ['jumbo','COURGETTE','jumbo','','not_identified'],
    ['green-code','Courgette groen','lidl','0082346','not_identified'],
    ['green','Courgette groen','lidl','','not_identified'],
    ['yellow','Courgette geel','lidl','0082293','not_identified'],
    ['bio','Courgette Bio','lidl','0084544','not_identified'],
  ].map(([id,name,shop,code,status]) => ({
    id: 'receipt-table-line:' + id, receipt_line_text: name,
    retailer_code: shop, receipt_article_number: code,
    article_code: status === 'catalog_linked' ? '8722800072026' : '',
    identity_status: status, identity_status_label: status === 'catalog_linked'
      ? 'Catalogus gekoppeld' : 'Nog identificeren', link_status: status === 'catalog_linked'
      ? 'linked' : 'unlinked',
  }))
  const selectedRows = articles.filter((item) => item.identity_status === 'not_identified')
  const receiptItems = selectedRows.map((item) => ({
    receipt_item_id: item.id, receipt_line_text: item.receipt_line_text,
    receipt_article_number: item.receipt_article_number,
    retailer: item.retailer_code,
    mode: /geel|bio/i.test(item.receipt_line_text) ? 'synonym_variant' : 'same_product',
    mode_label: /geel|bio/i.test(item.receipt_line_text)
      ? 'Afzonderlijk Catalogusproduct als synoniem' : 'Zelfde verse courgette',
  }))
  const posts = []
  const autoRequests = []
  let previews = 0
  await page.route('**/api/**', async (route) => {
    const url = new URL(route.request().url())
    if (url.pathname === '/api/catalog/ed2/curated-matching-batch/preview') {
      previews += 1
      return route.fulfill({ json: {
        family: 'verse_courgette_v1',
        targets: [{ product_id: 'gp-ah', product_name: 'AH Courgette',
          barcode: '8722800072026' }],
        items: url.searchParams.get('target_product_id') ? receiptItems : [],
        blocked: [], fingerprint: url.searchParams.get('target_product_id')
          ? 'e'.repeat(64) : null,
      } })
    }
    if (url.pathname === '/api/catalog/ed2/bonnamen-matchen/progress/start') {
      autoRequests.push(route.request().method())
      // The same two proven anchors still require an explicit review.
      return route.fulfill({ json: matchingJob() })
    }
    if (url.pathname === '/api/catalog/ed2/curated-matching-batch/confirm') {
      const payload = route.request().postDataJSON()
      posts.push(payload)
      for (const item of articles) {
        if (payload.receipt_item_ids.includes(item.id)) {
          item.identity_status = 'catalog_linked'
          item.identity_status_label = 'Catalogus gekoppeld'
        }
      }
      return route.fulfill({ json: {
        ok: true, linked: payload.receipt_item_ids.length,
        synonyms_created: 2, barcode_written: false,
      } })
    }
    return bootstrap(route, articles, [], (request) => request.fulfill({ json: {} }))
  })
  await page.goto('/externe-databases-2')
  await page.getByTestId('classification-work-monitor')
    .getByRole('button', { name: 'Matchen' }).click()
  await expect.poll(() => autoRequests.length).toBe(1)
  await page.getByText('Bonnaamregels en familie-uitzonderingen', { exact: true }).click()
  const batch = page.getByRole('region', { name: 'Gecontroleerde matching van productfamilies' })
  await batch.getByRole('button', { name: 'Familie-uitzonderingen beoordelen' }).click()
  expect(autoRequests).toEqual(['POST'])
  await batch.getByLabel('Bestaand, geïdentificeerd Catalogusproduct').selectOption('gp-ah')
  await expect(batch).toContainText('6 voorgesteld')
  await expect(batch.getByRole('checkbox')).toHaveCount(6)
  await expect(batch.getByRole('checkbox', { checked: true })).toHaveCount(6)
  expect(posts).toHaveLength(0)
  await batch.getByRole('button', { name: '6 matches in één keer bevestigen' }).click()
  const dialog = page.getByTestId('ed2-curated-batch-confirm')
  await expect(dialog).toContainText('6 geselecteerde bonartikelen')
  expect(posts).toHaveLength(0)
  await dialog.getByRole('button', { name: 'Alles bevestigen' }).click()
  await expect.poll(() => posts.length).toBe(1)
  expect(posts[0].target_product_id).toBe('gp-ah')
  expect(posts[0].fingerprint).toBe('e'.repeat(64))
  expect(posts[0].receipt_item_ids).toHaveLength(6)
  expect(posts[0].receipt_item_ids).not.toContain('receipt-table-line:ah-linked')
  await expect(page.getByTestId('ed2-match-left-table')).not.toContainText('Courgette groen')
  expect(previews).toBeGreaterThanOrEqual(2)
})


test('Matchen voert bewezen bonnamen automatisch bij toegang uit tot geen matches resteren', async ({ page }) => {
  const rows = [
    { id: 'receipt-table-line:milk-code', receipt_line_text: 'HALFVOLLE MELK',
      retailer_code: 'ah', receipt_article_number: '101', article_code: '8718907056274',
      catalog_product_id: 'milk-a', identity_status: 'catalog_linked',
      identity_status_label: 'Catalogus gekoppeld', link_status: 'linked' },
    { id: 'receipt-table-line:milk-no-code', receipt_line_text: 'HALFVOLLE MELK',
      retailer_code: 'plus', receipt_article_number: '', identity_status: 'not_identified',
      identity_status_label: 'Nog identificeren', link_status: 'unlinked' },
  ]
  const writes = []
  let finished = false
  await page.route('**/api/**', async (route) => {
    const path = new URL(route.request().url()).pathname
    if (route.request().method() !== 'GET') writes.push(path)
    if (path === '/api/catalog/ed2/bonnamen-matchen/progress')
      return route.fulfill({ json: finished ? matchingJob({ matched: 1, pass: 2 })
        : { ok: false, state: 'not_started' } })
    if (path === '/api/catalog/ed2/bonnamen-matchen/progress/start') {
      // A complete background job incorporates both write and zero-write passes.
      rows[1].identity_status = 'catalog_linked'
      rows[1].identity_status_label = 'Catalogus gekoppeld'
      rows[1].catalog_product_id = 'milk-a'
      finished = true
      return route.fulfill({ json: matchingJob({ matched: 1, pass: 2 }) })
    }
    return bootstrap(route, rows, [], (request) => request.fulfill({ json: {} }))
  })
  await page.goto('/externe-databases-2')
  await page.getByTestId('classification-work-monitor')
    .getByRole('button', { name: 'Matchen' }).click()
  const table = page.getByTestId('ed2-match-left-table')
  await expect(table).not.toContainText('HALFVOLLE MELK')
  await expect(page.getByTestId('ed2-auto-match-summary'))
    .toContainText('Bij het openen automatisch gematcht: 1')
  expect(writes).toEqual(['/api/catalog/ed2/bonnamen-matchen/progress/start'])
})


test('Bonnamen matchen is één knop; HV Melk alias geldt voor alle winkels', async ({ page }) => {
  const posts = []
  const items = [
    { id: 'receipt-table-line:milk', receipt_line_text: 'Halfvolle melk',
      retailer_code: 'ah', receipt_article_number: '21003', link_status: 'linked',
      identity_status: 'catalog_linked', identity_status_label: 'Catalogus gekoppeld' },
    { id: 'receipt-table-line:hv1', receipt_line_text: 'HV Melk',
      retailer_code: 'jumbo', receipt_article_number: '400', link_status: 'unlinked',
      identity_status: 'not_identified', identity_status_label: 'Nog identificeren' },
    { id: 'receipt-table-line:hv2', receipt_line_text: 'HV Melk',
      retailer_code: 'lidl', receipt_article_number: '900', link_status: 'unlinked',
      identity_status: 'not_identified', identity_status_label: 'Nog identificeren' },
  ]
  await page.route('**/api/**', async (route) => {
    const path = new URL(route.request().url()).pathname
    if (path === '/api/catalog/ed2/bonnaam-synoniem/confirm') {
      posts.push(route.request().postDataJSON())
      items.slice(1).forEach((x) => {
        x.identity_status = 'catalog_linked'
        x.identity_status_label = 'Catalogus gekoppeld'
      })
      return route.fulfill({ json: {
        ok: true, alias: { ok: true, alias_name: 'hv melk',
          target_name: 'halfvolle melk' },
        match_result: { ok: true, linked: 2, synonyms_created: 0,
          barcode_written: false },
      } })
    }
    return bootstrap(route, items, [], (request) => request.fulfill({ json: {} }))
  })
  await page.goto('/externe-databases-2')
  await page.getByTestId('classification-work-monitor')
    .getByRole('button', { name: 'Matchen' }).click()
  await page.getByText('Bonnaamregels en familie-uitzonderingen', { exact: true }).click()
  const section = page.getByTestId('ed2-bonnaam-alias-form')
  await expect(page.getByRole('button', { name: 'Courgettes automatisch herkennen' })).toHaveCount(0)
  await expect(page.getByRole('button', { name: 'Bewezen bonnamen herkennen' })).toHaveCount(0)
  await expect(page.getByRole('button', { name: 'Bonnamen matchen' })).toHaveCount(0)
  await expect(page.getByRole('button', { name: 'Familie-uitzonderingen beoordelen' })).toBeVisible()
  await section.getByLabel('Naam op de bon').fill('HV Melk')
  await section.getByLabel('Is hetzelfde als bonnaam').fill('Halfvolle melk')
  await section.getByRole('button', { name: 'Bonnaamsynoniem vastleggen' }).click()
  await expect(page.getByTestId('ed2-bonnaam-alias-confirm')).toBeVisible()
  expect(posts).toHaveLength(0)
  await page.getByTestId('ed2-bonnaam-alias-confirm')
    .getByRole('button', { name: 'Synoniem bevestigen' }).click()
  await expect.poll(() => posts.length).toBe(1)
  expect(posts[0]).toEqual({ alias_name: 'HV Melk', target_name: 'Halfvolle melk' })
  await expect(page.getByTestId('ed2-match-left-table'))
    .not.toContainText('HV Melk')
})


test('Matchen: serverfout blokkeert de handmatige lijst en kan opnieuw controleren', async ({ page }) => {
  const writes = []
  let failFirst = true
  let previews = 0
  await page.route('**/api/**', async (route) => {
    const path = new URL(route.request().url()).pathname
    if (route.request().method() !== 'GET') writes.push(path)
    if (path === '/api/catalog/ed2/bonnamen-matchen/progress/start') {
      if (failFirst) {
        failFirst = false
        return route.fulfill({ status: 500, contentType: 'text/plain', body: 'Internal Server Error' })
      }
      return route.fulfill({ json: matchingJob() })
    }
    if (path === '/api/catalog/ed2/curated-matching-batch/preview') {
      previews += 1
      return route.fulfill({ json: { targets: [] } })
    }
    return bootstrap(route, [{
      id: 'receipt-table-line:failure-repro', receipt_line_text: 'HALFVOLLE MELK',
      retailer_code: 'ah', receipt_article_number: '21003', link_status: 'unlinked',
    }], [], (request) => request.fulfill({ json: {} }))
  })
  await page.goto('/externe-databases-2')
  await page.getByTestId('classification-work-monitor')
    .getByRole('button', { name: 'Matchen' }).click()
  await expect(page.getByTestId('app-feedback-error'))
    .toContainText('De achtergrondcontrole kon niet worden gestart (HTTP 500)')
  await expect(page.getByTestId('ed2-match-left-table')).toHaveCount(0)
  expect(previews).toBe(0)
  expect(writes).toEqual(['/api/catalog/ed2/bonnamen-matchen/progress/start'])
  await page.getByTestId('app-feedback-error').getByRole('button', { name: 'OK' }).click()
  await page.getByRole('button', { name: 'Automatische controle opnieuw uitvoeren' }).click()
  await expect(page.getByTestId('ed2-match-left-table')).toBeVisible()
  expect(writes).toEqual([
    '/api/catalog/ed2/bonnamen-matchen/progress/start',
    '/api/catalog/ed2/bonnamen-matchen/progress/start',
  ])
})


test('AH HV MELK: geblokkeerde varianten hebben per bonartikel een blijvende uitleg', async ({ page }) => {
  const rows = [
    { id: 'ah-milk-569053', retailer_code: 'ah', receipt_line_text: 'AH HV MELK',
      receipt_article_number: '569053', article_code: '8718907056274',
      identity_status: 'catalog_linked', identity_status_label: 'Catalogus gekoppeld',
      link_status: 'linked' },
    { id: 'ah-milk-92154', retailer_code: 'ah', receipt_line_text: 'AH HV MELK',
      receipt_article_number: '92154', article_code: '8710400058519',
      identity_status: 'catalog_linked', identity_status_label: 'Catalogus gekoppeld',
      link_status: 'linked' },
    { id: 'ah-milk-no-code', retailer_code: 'ah', receipt_line_text: 'AH HV MELK',
      receipt_article_number: '', identity_status: 'not_identified',
      identity_status_label: 'Nog identificeren', link_status: 'unlinked',
      automatic_match_review_reason: 'Niet automatisch gematcht: deze bonnaam hoort bij 2 verschillende bevestigde Catalogusproducten of uitvoeringen: houdbare melk (barcode 8718907056274); halfvolle melk 1,5 liter (barcode 8710400058519). Kies het juiste product; Inhuis kiest geen willekeurige barcode.' },
    { id: 'ah-milk-11943', retailer_code: 'ah', receipt_line_text: 'AH HV MELK',
      receipt_article_number: '11943', identity_status: 'not_identified',
      identity_status_label: 'Nog identificeren', link_status: 'unlinked',
      automatic_match_review_reason: 'Niet automatisch gematcht: verschillende bevestigde Catalogusproducten of uitvoeringen. Kies het juiste product; Inhuis kiest geen willekeurige barcode.' },
  ]
  const writes = []
  await page.route('**/api/**', (route) => {
    if (route.request().method() !== 'GET') writes.push(route.request().url())
    return bootstrap(route, rows, [], (request) => request.fulfill({ json: {} }))
  })
  await page.goto('/externe-databases-2')
  await page.getByTestId('classification-work-monitor')
    .getByRole('button', { name: 'Identificeren', exact: true }).click()
  const table = page.getByTestId('external-databases-2-table')
  await page.getByRole('textbox', { name: 'Filter op Artikel', exact: true }).fill('HV MELK')
  await expect(table.locator('.rz-ed2-match-review-reason')).toHaveCount(2)
  await expect(table).toContainText('geen willekeurige barcode')
  await expect(table).toContainText('8710400058519')
  await expect(table).toContainText('8718907056274')
  await expect(table.locator('.rz-ed2-match-review-reason').first())
    .toHaveAttribute('title', /verschillende bevestigde Catalogusproducten/)
  expect(writes).toEqual([])
})


test('Superuser matcht een ongeïdentificeerd melkartikel via twee identieke tabellen', async ({ page }) => {
  const rows = [
    { id: 'receipt-table-line:unknown', receipt_line_text: 'AH HV MELK',
      retailer_code: 'ah', receipt_article_number: '11943',
      automatic_match_review_reason: 'Verschillende bewezen melkuitvoeringen. Kies er één.',
      identity_status: 'not_identified', identity_status_label: 'Nog identificeren',
      link_status: 'unlinked' },
    { id: 'receipt-table-line:proven', receipt_line_text: 'AH HV MELK',
      retailer_code: 'ah', receipt_article_number: '569053',
      article_code: '8718907056274', catalog_product_id: 'catalog-milk',
      identity_status: 'catalog_linked', identity_status_label: 'Catalogus gekoppeld',
      link_status: 'linked' },
  ]
  const posts = []
  await page.route('**/api/**', async (route) => {
    const url = new URL(route.request().url())
    if (url.pathname === '/api/catalog/ed2/manual-receipt-match/confirm') {
      posts.push(route.request().postDataJSON())
      rows[0].identity_status = 'catalog_linked'
      rows[0].identity_status_label = 'Catalogus gekoppeld'
      rows[0].catalog_product_id = 'catalog-milk'
      return route.fulfill({ json: { ok: true, linked: 1, barcode_written: false,
        catalog_product_id: 'catalog-milk' } })
    }
    return bootstrap(route, rows, [], (request) => request.fulfill({ json: {} }))
  })
  await page.goto('/externe-databases-2')
  const nav = page.getByTestId('classification-work-monitor')
  await expect(nav.getByRole('button', { name: 'Matchen' })).toBeVisible()
  await nav.getByRole('button', { name: 'Identificeren' }).click()
  await expect(page.getByTestId('ed2-bonnaam-alias-form')).toHaveCount(0)
  await expect(page.getByRole('button', { name: 'Bonnamen matchen' })).toHaveCount(0)
  await nav.getByRole('button', { name: 'Matchen' }).click()
  const left = page.getByTestId('ed2-match-left-table')
  const right = page.getByTestId('ed2-match-right-table')
  await expect(left.locator('thead')).toContainText('Bonartikelnummer')
  await expect(right.locator('thead')).toContainText('Bonartikelnummer')
  await expect(left).toContainText('11943')
  await expect(right).toContainText('569053')
  expect(posts).toHaveLength(0)
  await left.getByRole('checkbox', { name: /Selecteer links AH HV MELK/ }).check()
  await right.getByRole('checkbox', { name: /Selecteer rechts AH HV MELK/ }).check()
  await page.getByRole('button', { name: 'Bonartikel matchen' }).click()
  const overlay = page.getByTestId('ed2-manual-match-confirm')
  await expect(overlay).toBeVisible()
  expect(posts).toHaveLength(0)
  await overlay.getByRole('button', { name: 'Match bevestigen' }).click()
  await expect.poll(() => posts.length).toBe(1)
  expect(posts[0]).toEqual({ source_receipt_item_id: 'receipt-table-line:unknown',
    target_receipt_item_id: 'receipt-table-line:proven' })
  await expect(left).not.toContainText('11943')
})


test('Matchen toont voortgang en daarna uitsluitend echte handmatige uitzonderingen', async ({ page }) => {
  const rows = [
    { id: 'auto', receipt_line_text: 'AH ELSTAR', retailer_code: 'ah',
      receipt_article_number: '101', identity_status: 'not_identified' },
    { id: 'no-proof', receipt_line_text: 'ONBEKEND ARTIKEL', retailer_code: 'jumbo',
      receipt_article_number: '202', identity_status: 'not_identified' },
    { id: 'manual', receipt_line_text: 'AH HV MELK', retailer_code: 'ah',
      receipt_article_number: '11943', identity_status: 'not_identified',
      automatic_match_review_reason: 'Twee bevestigde Catalogusuitvoeringen; handmatig kiezen.' },
    { id: 'milk-a', receipt_line_text: 'AH HV MELK', retailer_code: 'ah',
      receipt_article_number: '569053', article_code: '8718907056274',
      catalog_product_id: 'milk-a', identity_status: 'catalog_linked' },
    { id: 'milk-b', receipt_line_text: 'AH HV MELK', retailer_code: 'ah',
      receipt_article_number: '92154', article_code: '8710400058519',
      catalog_product_id: 'milk-b', identity_status: 'catalog_linked' },
  ]
  let resume
  const held = new Promise((resolve) => { resume = resolve })
  let started = 0
  let completed = false
  await page.route('**/api/**', async (route) => {
    const path = new URL(route.request().url()).pathname
    if (path === '/api/catalog/ed2/bonnamen-matchen/progress/start') {
      started += 1
      return route.fulfill({ json: matchingJob({ state: 'running', checked: 2, total: 5,
        checkNumber: 1 }) })
    }
    if (path === '/api/catalog/ed2/bonnamen-matchen/progress') {
      if (!started) return route.fulfill({ json: { ok: false, state: 'not_started' } })
      if (!completed) return route.fulfill({ json: matchingJob({
        state: 'running', checked: 2, total: 5, checkNumber: 1,
      }) })
      return route.fulfill({ json: matchingJob({ matched: 1, pass: 2, checked: 5,
        total: 5, checkNumber: 2 }) })
    }
    return bootstrap(route, rows, [], (request) => request.fulfill({ json: {} }))
  })
  void held.then(() => {
    rows[0].identity_status = 'catalog_linked'
    rows[0].catalog_product_id = 'elstar-a'
    completed = true
  })
  await page.goto('/externe-databases-2')
  await page.getByTestId('classification-work-monitor')
    .getByRole('button', { name: 'Identificeren' }).click()
  await expect(page.getByTestId('external-databases-2-table')).toContainText('ONBEKEND ARTIKEL')
  expect(started).toBe(0)
  await page.getByTestId('classification-work-monitor')
    .getByRole('button', { name: 'Matchen' }).click()
  await expect(page.getByTestId('ed2-auto-match-progress')).toBeVisible()
  await expect(page.getByTestId('ed2-auto-match-progress').getByRole('progressbar')).toBeVisible()
  await expect(page.getByTestId('ed2-match-left-table')).toHaveCount(0)
  resume()
  await expect(page.getByTestId('ed2-auto-match-progress')).toHaveCount(0)
  const left = page.getByTestId('ed2-match-left-table')
  await expect(left).toContainText('AH HV MELK')
  await expect(left).not.toContainText('AH ELSTAR')
  await expect(left).not.toContainText('ONBEKEND ARTIKEL')
  await expect(page.getByText('1 handmatig te matchen')).toBeVisible()
  await expect(page.getByTestId('ed2-auto-match-summary'))
    .toContainText('Bij het openen automatisch gematcht: 1')
  expect(started).toBe(1)
})


const relationshipProducts = [
  { id: 'root', name: 'AH Courgette', primary_gtin: '8722800072026',
    article_codes: ['ah:21003'], image_url: '' },
  { id: 'yellow', name: 'Courgette geel', primary_gtin: '', image_url: '' },
  { id: 'bio', name: 'Courgette Bio', primary_gtin: '', image_url: '' },
  { id: 'other', name: 'Groentesoep', primary_gtin: '8712340000013', image_url: '' },
]
const receiptMatch = (id, name, retailer, number, productId) => ({
  id, receipt_line_text: name, retailer_code: retailer,
  receipt_article_number: number,
  identity_status: 'catalog_linked', identity_status_label: 'Catalogus gekoppeld',
  identity_catalog_product_id: productId, catalog_product_id: '',
})
const relationshipReceipts = [
  receiptMatch('ah-code', 'COURGETTE', 'ah', '21003', 'root'),
  receiptMatch('ah-no-code', 'COURGETTE', 'ah', '', 'root'),
  receiptMatch('jumbo-no-code', 'COURGETTE', 'jumbo', '', 'root'),
  receiptMatch('lidl-green', 'Courgette groen', 'lidl', '0082346', 'root'),
  receiptMatch('lidl-green-no-code', 'Courgette groen', 'lidl', '', 'root'),
  receiptMatch('lidl-yellow', 'Courgette geel', 'lidl', '0082293', 'yellow'),
  receiptMatch('lidl-bio', 'Courgette Bio', 'lidl', '0084544', 'bio'),
  { id: 'unconfirmed', receipt_line_text: 'COURGETTE', retailer_code: 'aldi',
    receipt_article_number: '', identity_status: 'not_identified' },
  { id: 'unrelated', receipt_line_text: 'Olvarit Courgette', retailer_code: 'ah',
    receipt_article_number: '', identity_status: 'not_identified' },
  { id: 'conflict', receipt_line_text: 'Courgette groen', retailer_code: 'plus',
    receipt_article_number: '99', identity_status: 'catalog_linked',
    identity_catalog_product_id: 'root', catalog_product_id: 'other' },
]

test('Overzicht: echte Catalogusmatches, directe synoniemen en onbewezen namen blijven gescheiden', async ({ page }) => {
  const writes = []
  await page.route('**/api/**', async (route) => {
    const path = new URL(route.request().url()).pathname
    if (route.request().method() !== 'GET') writes.push(path)
    if (path === '/api/external-databases/article-synonyms/analysis') {
      return route.fulfill({ json: { items: relationshipProducts } })
    }
    if (path === '/api/external-databases/article-synonyms/analysis/root/options') {
      return route.fulfill({ json: { items: [
        { id: 'yellow', status: 'linked' }, { id: 'bio', status: 'linked' },
        { id: 'other', status: 'suggested' },
      ] } })
    }
    if (path === '/api/external-databases/article-synonyms/analysis/yellow/options') {
      return route.fulfill({ json: { items: [
        { id: 'root', status: 'linked' }, { id: 'bio', status: 'other' },
      ] } })
    }
    return bootstrap(route, relationshipReceipts, [], (request) =>
      request.fulfill({ json: {} }))
  })
  await page.goto('/externe-databases-2')
  const monitor = page.getByTestId('classification-work-monitor')
  await expect(monitor.getByRole('button', { name: 'Matchen', exact: true })).toBeVisible()
  await monitor.getByRole('button', { name: 'Overzicht', exact: true }).click()
  const overview = page.getByTestId('article-relationship-overview')
  await expect(overview).toBeVisible()
  await expect(overview.getByText('Kies een Catalogusartikel', { exact: true })).toBeVisible()
  const search = overview.getByRole('searchbox', { name: 'Catalogusartikel zoeken' })
  await search.fill('Courgette')
  await expect(overview.locator('.rz-rel-search-options button')).toHaveCount(3)
  await overview.locator('.rz-rel-search-options button', { hasText: 'AH Courgette' }).click()
  await expect(overview.locator('.rz-rel-match-branch')).toHaveCount(5)
  await expect(overview.locator('.rz-rel-synonym-branch')).toHaveCount(2)
  await expect(overview.locator('.rz-rel-variant-match')).toHaveCount(2)
  await expect(overview.locator('.rz-rel-stat--matches')).toContainText('5')
  await expect(overview.locator('.rz-rel-stat--synonyms')).toContainText('2')
  await expect(overview.locator('.rz-rel-stat--pending')).toContainText('1')
  await expect(overview).not.toContainText('Groentesoep')
  await expect(overview).not.toContainText('Olvarit Courgette')
  await expect(overview.locator('.rz-rel-pending')).toContainText('COURGETTE')
  await expect(overview.locator('.rz-rel-pending')).toContainText('geen bewijs', { ignoreCase: true })
  expect(writes).toEqual([])

  await overview.getByRole('button', { name: 'Matches', exact: true }).click()
  await expect(overview.locator('.rz-rel-synonym-branch')).toHaveCount(0)
  await overview.getByRole('button', { name: 'Synoniemen', exact: true }).click()
  await expect(overview.locator('.rz-rel-match-branch')).toHaveCount(0)
  await expect(overview.locator('.rz-rel-synonym-branch')).toHaveCount(2)
  await search.fill('geel')
  await overview.locator('.rz-rel-search-options button', { hasText: 'Courgette geel' }).click()
  await expect(overview.locator('.rz-rel-match-branch')).toHaveCount(1)
  await expect(overview.locator('.rz-rel-synonym-branch')).toHaveCount(1)
  await expect(overview.locator('.rz-rel-stat--matches')).toContainText('1')

  // Choosing an unrelated independently identified product may never
  // reuse the prior courgette graph or fabricate synonym edges.
  await search.fill('Groentesoep')
  await overview.locator('.rz-rel-search-options button', { hasText: 'Groentesoep' }).click()
  await expect(overview.locator('.rz-rel-hub')).toContainText('Groentesoep')
  await expect(overview.locator('.rz-rel-match-branch')).toHaveCount(0)
  await expect(overview.locator('.rz-rel-synonym-branch')).toHaveCount(0)
  await expect(overview.locator('.rz-rel-stat--matches')).toContainText('0')
  await expect(overview.locator('.rz-rel-stat--synonyms')).toContainText('0')
  expect(writes).toEqual([])
})

test('Overzicht: mobiel blijft een leesbaar kaartennetwerk, geen tabel', async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 })
  await page.route('**/api/**', async (route) => {
    const path = new URL(route.request().url()).pathname
    if (path === '/api/external-databases/article-synonyms/analysis') {
      return route.fulfill({ json: { items: relationshipProducts } })
    }
    if (path === '/api/external-databases/article-synonyms/analysis/root/options') {
      return route.fulfill({ json: { items: [{ id: 'yellow', status: 'linked' }] } })
    }
    return bootstrap(route, relationshipReceipts, [], (request) =>
      request.fulfill({ json: {} }))
  })
  await page.goto('/externe-databases-2')
  await page.getByTestId('classification-work-monitor')
    .getByRole('button', { name: 'Overzicht', exact: true }).click()
  const overview = page.getByTestId('article-relationship-overview')
  await overview.getByRole('searchbox', { name: 'Catalogusartikel zoeken' }).fill('AH Courgette')
  await overview.locator('.rz-rel-search-options button', { hasText: 'AH Courgette' }).click()
  await expect(overview.locator('.rz-rel-synonym-branch')).toHaveCount(1)
  await expect(overview.locator('.rz-rel-hub')).toContainText('AH Courgette')
  await expect(overview.locator('table')).toHaveCount(0)
  const columns = await overview.locator('.rz-rel-layout').evaluate((el) =>
    getComputedStyle(el).gridTemplateColumns)
  expect(columns.split(' ').length).toBe(1)
})

test('Overzicht-projectie: onzekere, conflicterende en voorgestelde identiteiten zijn geen matches', () => {
  const graph = buildArticleRelationshipGraph(relationshipProducts, relationshipReceipts,
    [{ id: 'yellow', status: 'linked' }, { id: 'other', status: 'suggested' }], 'root')
  expect(graph.rootReceipts).toHaveLength(5)
  expect(graph.synonyms.map((item) => item.product.id)).toEqual(['yellow'])
  expect(graph.synonyms[0].receipts).toHaveLength(1)
  expect(graph.pending.map((item) => item.id)).toEqual(['unconfirmed'])
  expect(graph.rootReceipts.map((item) => item.id)).not.toContain('conflict')
  expect(buildArticleRelationshipGraph(relationshipProducts, relationshipReceipts,
    [], 'missing-product')).toBeNull()
})
