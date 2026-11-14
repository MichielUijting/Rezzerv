import { test, expect } from '@playwright/test'

test.use({ storageState: { cookies: [], origins: [] } })

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
    counts: { unlinked: rows.length, classification_pending: 0, linked: 0 },
  } })
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
  await page.goto('/externe-databases-2')
  await page.getByTestId('classification-work-monitor').getByRole('button', { name: 'Identificeren' }).click()
  await page.getByTestId('external-databases-2-table')
    .locator('tbody tr', { hasText: 'Scharrelei M/L' }).dblclick()
  const panel = page.getByTestId('external-databases-2-off-panel')
  await expect(panel.getByRole('button', { name: 'Barcode uit foto' })).toHaveCount(0)
  await panel.getByTestId('ed2-barcode-scan').click()
  const scanner = page.getByTestId('barcode-scanner-backdrop')
  await expect(scanner).toBeVisible()
  const cameraWarning = page.getByTestId('ed2-barcode-scanner-message-overlay')
  await expect(cameraWarning).toBeVisible()
  await expect(page.getByTestId('ed2-barcode-scanner-message')).toContainText('Camera voor barcode scannen kon niet worden gestart')
  await cameraWarning.getByRole('button', { name: 'OK' }).click()
  await expect(scanner.locator('.rz-inline-feedback')).toHaveCount(0)
  await expect(scanner.getByRole('button', { name: 'Camera opnieuw proberen' })).toBeVisible()
  await expect(scanner.getByRole('button', { name: 'Barcode uit foto' })).toBeVisible()
  await expect(scanner).toContainText('bestaande foto')
  // The dialog must not disappear after the asynchronous camera error.
  await expect.poll(() => page.evaluate(() => window.__ed2GetUserMediaAttempts())).toBeGreaterThan(1)
  await expect(scanner).toBeVisible()
  await scanner.getByRole('button', { name: 'Camera opnieuw proberen' }).click()
  await expect(page.getByTestId('ed2-barcode-scanner-message-overlay')).toBeVisible()
  await expect(page.getByTestId('ed2-barcode-scanner-message')).toContainText('Camera voor barcode scannen kon niet worden gestart')
  await page.getByTestId('ed2-barcode-scanner-message-overlay').getByRole('button', { name: 'OK' }).click()
  await expect(scanner).toBeVisible()
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
  await expect(scanActions.getByTestId('ed2-barcode-scan')).toBeVisible()
  await expect(scanActions.getByTestId('ed2-barcode-scan')).toBeEnabled()
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
      identity_status_label: 'Nog identificeren', link_status: 'unlinked' },
    { id: 'receipt-table-line:yellow', receipt_line_text: 'Courgette geel',
      retailer_code: 'lidl', receipt_article_number: '0082293',
      article_code: '', manual_barcode: '', identity_status: 'not_identified',
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
  await table.locator('tbody tr', { hasText: 'Olvarit' }).click()
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
    if (url.pathname === '/api/catalog/ed2/bonnamen-matchen/auto') {
      autoRequests.push(route.request().method())
      // Two independently proven ordinary catalog anchors require an explicit
      // exception review. Never write the six unresolved receipt identities.
      return route.fulfill({ json: {
        ok: true, status: 'anchor_review_required', linked: 0,
        synonyms_created: 0, barcode_written: false, requires_review: true,
      } })
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
  await page.getByText('Automatisch matchen en bonnaamregels', { exact: true }).click()
  const batch = page.getByRole('region', { name: 'Gecontroleerde matching van productfamilies' })
  await batch.getByRole('button', { name: 'Bonnamen matchen' }).click()
  await expect(batch).toContainText('Niet alle productfamilies hebben één bewezen anker.')
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


test('Matchen: bewezen bonnamen van alle winkels alleen na expliciete klik koppelen', async ({ page }) => {
  const rows = [
    { id: 'receipt-table-line:milk-code', receipt_line_text: 'HALFVOLLE MELK',
      retailer_code: 'ah', receipt_article_number: '101', identity_status: 'catalog_linked',
      identity_status_label: 'Catalogus gekoppeld', link_status: 'linked' },
    { id: 'receipt-table-line:milk-no-code', receipt_line_text: 'HALFVOLLE MELK',
      retailer_code: 'plus', receipt_article_number: '', identity_status: 'not_identified',
      identity_status_label: 'Nog identificeren', link_status: 'unlinked' },
  ]
  const writes = []
  await page.route('**/api/**', async (route) => {
    const path = new URL(route.request().url()).pathname
    if (route.request().method() !== 'GET') writes.push(path)
    if (path === '/api/catalog/ed2/bonnamen-matchen/auto') {
      rows[1].identity_status = 'catalog_linked'
      rows[1].identity_status_label = 'Catalogus gekoppeld'
      return route.fulfill({ json: {
        ok: true, status: 'applied', linked: 1,
        linked_from_exact_names: 1, linked_from_families: 0,
        blocked: 0, synonyms_created: 0, barcode_written: false,
        limit_reached: false,
      } })
    }
    return bootstrap(route, rows, [], (request) => request.fulfill({ json: {} }))
  })
  await page.goto('/externe-databases-2')
  await page.getByTestId('classification-work-monitor')
    .getByRole('button', { name: 'Matchen' }).click()
  await page.getByText('Automatisch matchen en bonnaamregels', { exact: true }).click()
  const table = page.getByTestId('ed2-match-left-table')
  await page.getByRole('textbox', { name: 'Filter op Artikel', exact: true }).fill('melk')
  await expect(table).toContainText('HALFVOLLE MELK')
  expect(writes).toEqual([])
  await page.getByRole('button', { name: 'Bonnamen matchen', exact: true }).click()
  await expect(page.getByRole('region', { name: 'Gecontroleerde matching van productfamilies' }))
    .toContainText('1 bonartikel(en) gematched')
  await expect(table).not.toContainText('HALFVOLLE MELK')
  expect(writes).toEqual(['/api/catalog/ed2/bonnamen-matchen/auto'])
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
  await page.getByText('Automatisch matchen en bonnaamregels', { exact: true }).click()
  const section = page.getByTestId('ed2-bonnaam-alias-form')
  await expect(page.getByRole('button', { name: 'Courgettes automatisch herkennen' })).toHaveCount(0)
  await expect(page.getByRole('button', { name: 'Bewezen bonnamen herkennen' })).toHaveCount(0)
  await expect(page.getByRole('button', { name: 'Bonnamen matchen' })).toHaveCount(1)
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


test('Bonnamen matchen: serverfout opent geen onterecht matchingvoorstel', async ({ page }) => {
  const writes = []
  let previewRequests = 0
  await page.route('**/api/**', async (route) => {
    const path = new URL(route.request().url()).pathname
    if (route.request().method() !== 'GET') writes.push(path)
    if (path === '/api/catalog/ed2/bonnamen-matchen/auto') {
      return route.fulfill({
        status: 500, contentType: 'text/plain',
        body: 'Internal Server Error',
      })
    }
    if (path === '/api/catalog/ed2/curated-matching-batch/preview') {
      previewRequests += 1
      return route.fulfill({ json: { targets: [] } })
    }
    return bootstrap(route, [{
      id: 'receipt-table-line:failure-repro',
      receipt_line_text: 'HALFVOLLE MELK',
      retailer_code: 'ah', receipt_article_number: '21003',
      link_status: 'unlinked',
    }], [], (request) => request.fulfill({ json: {} }))
  })
  await page.goto('/externe-databases-2')
  await page.getByTestId('classification-work-monitor')
    .getByRole('button', { name: 'Matchen' }).click()
  await page.getByText('Automatisch matchen en bonnaamregels', { exact: true }).click()
  await page.getByRole('button', { name: 'Bonnamen matchen', exact: true }).click()
  await expect(page.getByText(/Matching kan niet worden beoordeeld \(HTTP 500\)/)).toBeVisible()
  await expect(page.getByRole('button', { name: 'Matchingvoorstellen sluiten' })).toHaveCount(0)
  expect(previewRequests).toBe(0)
  expect(writes).toEqual(['/api/catalog/ed2/bonnamen-matchen/auto'])
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
