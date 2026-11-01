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

test('Een barcode zonder OFF-match wordt in ED2 bewaard, niet als Catalogus-GTIN gepresenteerd', async ({ page }) => {
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
      source: 'manual', off_found: false, classification_pending: false, photo_loaded: false } })
  }))
  await page.goto('/externe-databases-2')
  const table = page.getByTestId('external-databases-2-table')
  await expect(table).toContainText('Melk zonder code')
  await table.locator('tbody tr', { hasText: 'Melk zonder code' }).dblclick()
  await page.getByTestId('ed2-manual-barcode-input').fill('8718452504435')
  await page.getByTestId('ed2-manual-barcode-save').click()
  await page.getByRole('alertdialog').getByRole('button', { name: 'OK' }).click()
  await expect(page.getByText(/Barcode handmatig opgeslagen/)).toBeVisible()
  await expect(table).toContainText('8718452504435')
  await expect(page.getByRole('button', { name: 'Niet gekoppeld: 1' })).toBeVisible()
  expect(requests).toEqual([{ receipt_item_id: item.id, gtin: '8718452504435' }])
  const cells = table.locator('tbody tr').first().locator('td')
  await expect(cells.nth(4)).toHaveText('8718452504435')
  await expect(cells.nth(4).locator('span')).toHaveAttribute('title', /Handmatig ingevoerde barcode/)
  await expect(cells.nth(5)).toHaveText('Niet gekoppeld')
  await expect(table.locator('thead')).toContainText('Art./Barcode')
})

test('Een OFF storing bewaart barcode in Art./Barcode en behoudt het bestaande filter', async ({ page }) => {
  const item = {
    id: 'receipt-table-line:manual-off-outage', receipt_line_text: 'SIMON LEVELT',
    retailer_code: 'ah', receipt_article_number: '768682',
    article_code: '', link_status: 'unlinked',
  }
  const stored = []
  await page.route('**/api/**', (route) => bootstrap(route, [item], stored, (request) => {
    const code = request.request().postDataJSON().gtin
    stored.push({ receipt_item_id: item.id, retailer_code: 'albert-heijn',
      receipt_text_normalized: 'simon levelt',
      external_article_code: '768682', gtin: code })
    return request.fulfill({ json: {
      saved: true, source: 'manual', gtin: code, off_found: false, off_unavailable: true,
      classification_pending: false, photo_loaded: false,
    } })
  }))
  await page.goto('/externe-databases-2')
  const table = page.getByTestId('external-databases-2-table')
  await page.getByRole('textbox', { name: 'Filter op Artikel' }).fill('SIMON')
  await table.locator('tbody tr', { hasText: 'SIMON LEVELT' }).dblclick()
  await page.getByTestId('ed2-manual-barcode-input').fill('8711138357776')
  await page.getByTestId('ed2-manual-barcode-save').click()
  await page.getByRole('alertdialog').getByRole('button', { name: 'OK' }).click()
  await expect(page.getByTestId('external-off-link-outcome')).toContainText('Barcode opgeslagen. OFF is tijdelijk niet bereikbaar')
  await expect(page.getByRole('textbox', { name: 'Filter op Artikel' })).toHaveValue('SIMON')
  await expect(table.locator('thead')).toContainText('Art./Barcode')
  await expect(table.locator('tbody tr', { hasText: 'SIMON LEVELT' }).locator('td').nth(4)).toHaveText('8711138357776')
  await expect(page.getByRole('button', { name: 'Niet gekoppeld: 1' })).toBeVisible()
  await page.reload()
  await expect(page.getByRole('textbox', { name: 'Filter op Artikel' })).toHaveValue('SIMON')
  await expect(table.locator('tbody tr', { hasText: 'SIMON LEVELT' }).locator('td').nth(4)).toHaveText('8711138357776')
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
  await page.getByTestId('external-databases-2-table')
    .locator('tbody tr', { hasText: 'AH CERVELAAT' }).dblclick()
  await page.getByRole('button', { name: 'Zelf zoeken in OFF' }).click()
  await page.getByRole('textbox', { name: 'Omschrijving of barcode in OFF' }).fill('cervelaat albert heijn')
  await page.getByRole('button', { name: 'Zoeken', exact: true }).click()
  const candidates = page.getByTestId('external-off-free-search-results')
  await candidates.locator('tbody tr', { hasText: 'Jumbo' }).dblclick()
  const overlay = page.getByTestId('app-feedback-error-overlay')
  await expect(overlay).toBeVisible()
  await expect(page.getByTestId('app-feedback-error')).toContainText('Het geselecteerde product is van Jumbo.')
  await expect(page.getByTestId('app-feedback-error')).toContainText('Melding')
  expect(writes).toHaveLength(0)
  await page.getByTestId('app-feedback-error').getByRole('button', { name: 'OK' }).click()
  await candidates.locator('tbody tr', { hasText: target.gtin }).dblclick()
  await expect(page.getByRole('alertdialog')).toContainText('Weet u zeker')
  await page.getByRole('alertdialog').getByRole('button', { name: 'OK' }).click()
  await expect(page).toHaveURL(/\/externe-databases-2$/)
  await expect(page.getByTestId('external-off-link-outcome')).toContainText('GS1-classificatie ontbreekt nog')
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
