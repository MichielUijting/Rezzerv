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
    items: rows,
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
    stored.push({ retailer_code: 'jumbo', receipt_text_normalized: 'melk zonder code',
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
  await expect(cells.nth(4)).toHaveText('')
  await expect(cells.nth(5)).toHaveText('8718452504435')
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
