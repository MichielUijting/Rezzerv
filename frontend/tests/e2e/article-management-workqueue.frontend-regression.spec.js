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
        'gpc.update': !frontteam, 'platform.gpc.update': !frontteam },
    } })
    if (path === '/api/maintenance/status') return route.fulfill({ json: { state: 'normal' } })
    if (path === '/api/external-databases/articles-overview') return route.fulfill({ json: {
      items: sources, total: sources.length, counts: { unlinked: 3, classification_pending: 0, linked: 1 },
    } })
    if (path === '/api/external-databases/article-synonyms/analysis') {
      return route.fulfill({ json: { summary: { candidate_pairs: 1 },
        items: [
          { id: 'catalog-milk', name: 'Halfvolle melk', pending: [
            { id: 'catalog-other', name: 'Volle melk' },
          ] },
          { id: 'catalog-other', name: 'Volle melk', pending: [
            { id: 'catalog-milk', name: 'Halfvolle melk' },
          ] },
        ],
      } })
    }
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
    const matchingFilter = page.getByRole('button', { name: 'Handmatig matchen: 1' })
    await expect(matchingFilter).toBeVisible()
    // Prevent dark-on-dark labels: the global secondary button default has a
    // dark background, while Artikelbeheer's counters request dark text.
    await expect(matchingFilter).toHaveCSS('background-color', 'rgb(255, 255, 255)')
    await expect(matchingFilter).toHaveCSS('color', 'rgb(0, 95, 106)')
    await expect(page.getByRole('button', { name: 'Catalogus herstellen: 1' })).toBeVisible()
    await expect(page.getByRole('button', { name: 'Identificeren: 1' })).toBeVisible()
    await expect(page.getByRole('button', { name: 'Classificeren: 2' })).toBeVisible()
    await expect(page.getByRole('button', { name: 'Synoniemen: 2' })).toBeVisible()
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
  await expect(page.getByRole('button', { name: 'Synoniemen: 2' })).toBeVisible()
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

for (const width of [390, 1280]) {
  test('Overzicht staat naast Werkvoorraad en beide navigeren zelfstandig op ' + width + 'px', async ({ page }) => {
    await page.setViewportSize({ width, height: 900 })
    const requests = await mountMockBackend(page)
    await page.goto('/externe-databases-2')
    const nav = page.getByTestId('classification-work-monitor')
    const editing = nav.locator('.rz-article-management-areas')
    const secondary = nav.locator('.rz-article-management-workqueue-action')
    await expect(editing.getByRole('button')).toHaveCount(4)
    await expect(editing.getByRole('button', { name: 'Overzicht' })).toHaveCount(0)
    await expect(secondary.getByRole('button')).toHaveCount(2)
    const work = secondary.getByRole('button', { name: 'Werkvoorraad' })
    const overview = secondary.getByRole('button', { name: 'Overzicht' })
    const workBox = await work.boundingBox()
    const overviewBox = await overview.boundingBox()
    const editorsBox = await editing.boundingBox()
    expect(workBox).not.toBeNull()
    expect(overviewBox).not.toBeNull()
    expect(editorsBox).not.toBeNull()
    expect(overviewBox.x).toBeGreaterThan(workBox.x)
    expect(Math.abs(overviewBox.y - workBox.y)).toBeLessThan(3)
    expect(workBox.y).toBeGreaterThan(editorsBox.y)
    await overview.click()
    await expect(page.getByTestId('article-relationship-overview')).toBeVisible()
    await expect(overview).toHaveAttribute('aria-pressed', 'true')
    await work.click()
    await expect(page.getByTestId('article-workqueue-table')).toBeVisible()
    await expect(work).toHaveAttribute('aria-pressed', 'true')
    expect(requests.filter((req) => req.method === 'POST')).toEqual([])
  })
}

test('Catalogusexport is een afzonderlijke alleen-lezen download in Artikelbeheer', async ({ page }) => {
  const requests = await mountMockBackend(page)
  await page.route('**/api/cbs-classifications/catalog-export', route => route.fulfill({
    status: 200, headers: { 'content-type': 'application/zip' },
    body: 'PK-mock-binary-export',
  }))
  await page.goto('/externe-databases-2')
  await expect(page.getByRole('button', { name: 'Catalogus exporteren' })).toHaveCount(0)
  await page.getByRole('button', { name: 'Classificeren' }).click()
  const button = page.getByRole('button', { name: 'Catalogus exporteren' })
  await expect(button).toBeVisible()
  const download = page.waitForEvent('download')
  await button.click()
  const downloaded = await download
  expect(downloaded.suggestedFilename()).toBe('Inhuis_Catalogus_Classificatie.zip')
  await expect(page.getByRole('button', { name: 'Catalogus exporteren' })).toBeEnabled()
  expect(requests.filter(req => req.method === 'POST')).toEqual([])
})

test('Frontteam mag Catalogus exporteren zonder Superuser-matchrecht', async ({ page }) => {
  await mountMockBackend(page, { frontteam: true })
  await page.goto('/externe-databases-2')
  await expect(page.getByRole('button', { name: 'Catalogus exporteren' })).toHaveCount(0)
  await page.getByRole('button', { name: 'Classificeren' }).click()
  await expect(page.getByRole('button', { name: 'Catalogus exporteren' })).toBeVisible()
  await expect(page.getByRole('button', { name: 'Matchen' })).toHaveCount(0)
})

test('Classificeren: import controleert eerst en bevestigt alleen expliciet gekozen GS1 en CBS', async ({ page }) => {
  await mountMockBackend(page)
  const sent = []
  await page.route('**/api/cbs-classifications/classification-import/preview', route => route.fulfill({ json: {
    total: 1, blocked: 0, review_existing: 1, no_changes_yet: true,
    rows: [{
      product_id: 'product-milk', name: 'Halfvolle melk', brand: '',
      snapshot_sha256: 'a'.repeat(64), current_gpc: '10000002', current_cbs: '',
      gpc_status: 'Bestaand - controle nodig', cbs_status: 'Voorstel hoog',
      gpc_reason: '', cbs_reason: 'Productnaam', review_existing: true,
      problem: '', invalid_gpc: [], invalid_cbs: [],
      gpc_options: [{ code: '10000001', label: 'Drinkmelk', kind: 'bestaand controleren' }],
      cbs_options: [{ code: '011420', label: 'Melk', reference_version: '2026', kind: 'voorstel' }],
    }],
  } }))
  await page.route('**/api/cbs-classifications/classification-import/confirm', async route => {
    sent.push(route.request().postDataJSON())
    await route.fulfill({ json: { updated_gpc: 1, updated_cbs: 1, unchanged: 0, processed: 2 } })
  })
  await page.goto('/externe-databases-2')
  await page.getByRole('button', { name: 'Classificeren' }).click()
  await expect(page.getByTestId('classification-import-panel')).toBeVisible()
  await page.getByTestId('classification-file').setInputFiles({
    name: 'Inhuis_Classificatievoorstellen.csv', mimeType: 'text/csv',
    buffer: Buffer.from('testfile-contents'),
  })
  await expect(page.getByTestId('classification-import-table')).toHaveCount(0)
  await page.getByTestId('classification-import-preview').click()
  await expect(page.getByTestId('classification-import-table')).toContainText('Halfvolle melk')
  await expect(page.getByTestId('classification-import-table')).toContainText('Productnaam')
  await page.getByLabel('GPC voorstel Halfvolle melk').selectOption('10000001')
  await page.getByLabel('CBS voorstel Halfvolle melk').selectOption('011420')
  await expect(page.getByTestId('classification-import-confirm')).toContainText('2')
  await page.getByTestId('classification-import-confirm').click()
  await expect(page.getByText('Bestaande code vervangen')).toBeVisible()
  await expect(page.getByText('Bestaande code vervangen').locator('input')).not.toBeChecked()
  await page.getByRole('button', { name: 'Goedkeuren en verwerken' }).click()
  await expect(page.getByRole('alert')).toContainText('Bevestig per artikel')
  expect(sent).toHaveLength(0)
  // The warning dialog correctly intercepts clicks until explicitly closed.
  await page.getByRole('button', { name: 'Annuleren' }).click()
  await page.getByText('Bestaande code vervangen').locator('input').check()
  await page.getByTestId('classification-import-confirm').click()
  await page.getByRole('button', { name: 'Goedkeuren en verwerken' }).click()
  await expect.poll(() => sent.length).toBe(1)
  expect(sent[0].decisions.map(item => item.system).sort()).toEqual(['cbs', 'gpc'])
  expect(sent[0].decisions.find(item => item.system === 'gpc').allow_replace).toBe(true)
})
