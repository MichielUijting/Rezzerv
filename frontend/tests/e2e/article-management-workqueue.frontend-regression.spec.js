import { test, expect } from '@playwright/test'

test.use({ storageState: { cookies: [], origins: [] } })

const sources = [
  { id: 'receipt-milk', retailer_code: 'ah', receipt_line_text: 'AH HV MELK',
    receipt_article_number: '38856', identity_status: 'not_identified',
    automatic_match_review_reason: 'Twee verschillend bevestigde Catalogusproducten' },
  { id: 'receipt-repair', retailer_code: 'lidl', receipt_line_text: 'WASMIDDEL',
    receipt_article_number: '120', identity_status: 'saved_only', identity_repairable: true,
    manual_barcode: '8712345678901' },
  { id: 'receipt-unknown', retailer_code: 'jumbo', receipt_line_text: 'TOMPOUCEN',
    receipt_article_number: '527121', identity_status: 'not_identified' },
  { id: 'receipt-linked', retailer_code: 'ah', receipt_line_text: 'ELSTAR',
    receipt_article_number: '58', identity_status: 'catalog_linked',
    catalog_product_id: 'catalog-milk' },
]

function mountMockBackend(page, { frontteam = false, invalidClassPage = false } = {}) {
  const requests = []
  return page.route('**/api/**', async (route) => {
    const path = new URL(route.request().url()).pathname
    const method = route.request().method()
    requests.push({ path, method })
    if (path === '/api/session') return route.fulfill({ json: {
      user_id: 'queue-test-user', active_household_id: frontteam ? 'family-1' : '0',
      context_type: frontteam ? 'regular' : 'system', role: 'admin',
      is_platform_superuser: !frontteam, is_frontteam: frontteam,
      permissions: { 'platform.external_products.view': true, 'platform.external_products.link_existing': true,
        'gpc.update': !frontteam },
    } })
    if (path === '/api/maintenance/status') return route.fulfill({ json: { state: 'normal' } })
    if (path === '/api/external-databases/articles-overview') return route.fulfill({ json: {
      items: sources, total: sources.length, counts: { unlinked: 3, classification_pending: 0, linked: 1 },
    } })
    if (path === '/api/cbs-classifications/workqueue') return route.fulfill({ json: {
      product_count_scope: 'global', task_count_scope: 'page',
      total: invalidClassPage ? 2 : 1, items: [{
        id: 'catalog-milk', name: 'Halfvolle melk', gtin: '8712345678901',
        gpc_status: 'unclassified', cbs_status: 'unclassified',
      }], tasks: [
        { key: 'catalog-milk:gpc', global_product_id: 'catalog-milk', system: 'gpc', status: 'open' },
        { key: 'catalog-milk:cbs', global_product_id: 'catalog-milk', system: 'cbs', status: 'open' },
      ],
    } })
    return route.fulfill({ json: {} })
  }).then(() => requests)
}

for (const width of [390, 1280]) {
  test('Werkvoorraad is read-only, toont echte taaksoorten en opent Identificeren op ' + width + 'px', async ({ page }) => {
    await page.setViewportSize({ width, height: 900 })
    const requests = await mountMockBackend(page)
    await page.goto('/externe-databases-2')
    expect(requests.some((req) => req.path === '/api/cbs-classifications/workqueue')).toBe(false)
    await page.getByRole('button', { name: 'Werkvoorraad' }).click()
    await expect(page.getByTestId('article-workqueue-table')).toBeVisible()
    await expect(page.getByRole('button', { name: 'Handmatig matchen: 1' })).toBeVisible()
    await expect(page.getByRole('button', { name: 'Catalogus herstellen: 1' })).toBeVisible()
    await expect(page.getByRole('button', { name: 'Identificeren: 1' })).toBeVisible()
    await expect(page.getByRole('button', { name: 'Classificeren: 2' })).toBeVisible()
    await expect(page.getByTestId('article-workqueue-table')).toContainText('AH HV MELK')
    await expect(page.getByTestId('article-workqueue-table')).toContainText('TOMPOUCEN')
    await expect(page.getByTestId('article-workqueue-table')).toContainText('Halfvolle melk')
    await expect(page.getByTestId('article-workqueue-table')).not.toContainText('ELSTAR')
    expect(requests.filter((req) => req.method === 'POST')).toEqual([])

    // Up to this point, reading and filtering Werkvoorraad must be GET-only.
    expect(requests.filter((req) => req.method === 'POST')).toEqual([])
    await page.getByRole('button', { name: 'Identificeren: 1' }).click()
    await expect(page.getByTestId('article-workqueue-table')).toContainText('TOMPOUCEN')
    await expect(page.getByTestId('article-workqueue-table')).not.toContainText('WASMIDDEL')
    await page.getByTestId('article-workqueue-table').getByRole('row', { name: /TOMPOUCEN/ }).click()
    await page.getByRole('button', { name: 'Naar Identificeren' }).click()
    await expect(page.getByTestId('external-databases-2-table')).toBeVisible()
    await expect(page.getByRole('heading', { name: 'Artikelbeheer' }).first()).toBeVisible()
    // Identificeren has an existing POST /products/search-preview which only
    // previews candidate products. It is neither a match confirmation nor a write.
    expect(requests.filter((req) => req.method === 'POST'
      && req.path !== '/api/external-databases/products/search-preview')).toEqual([])
  })
}

test('Frontteam ziet geen Superuser-matchtaak of Matchen-knop', async ({ page }) => {
  const requests = await mountMockBackend(page, { frontteam: true })
  await page.goto('/externe-databases-2')
  await page.getByRole('button', { name: 'Werkvoorraad' }).click()
  await expect(page.getByTestId('article-workqueue-table')).toBeVisible()
  await expect(page.getByRole('button', { name: /Handmatig matchen/ })).toHaveCount(0)
  await expect(page.getByTestId('article-workqueue-table')).not.toContainText('AH HV MELK')
  await expect(page.getByRole('button', { name: 'Naar Synoniemen' })).toBeVisible()
  expect(requests.filter((req) => req.method === 'POST')).toEqual([])
})

test('Fout of onvolledige classificatieprojectie levert geen fictieve nul taken op', async ({ page }) => {
  const requests = await mountMockBackend(page, { invalidClassPage: true })
  await page.goto('/externe-databases-2')
  await page.getByRole('button', { name: 'Werkvoorraad' }).click()
  await expect(page.getByRole('alert')).toContainText('Controle niet voltooid')
  await expect(page.getByTestId('article-workqueue-count-summary')).toHaveCount(0)
  await expect(page.getByTestId('article-workqueue-table')).toHaveCount(0)
  expect(requests.filter((req) => req.method === 'POST')).toEqual([])
})
