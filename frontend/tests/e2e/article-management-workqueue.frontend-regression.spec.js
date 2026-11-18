import { test, expect } from '@playwright/test'
import { readFile } from 'node:fs/promises'

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
    if (path === '/api/cbs-classifications/workqueue-summary') return route.fulfill({ json: {
      product_total: 1, task_total: 2, product_count_scope: 'global', task_count_scope: 'global',
    } })
    if (path === '/api/cbs-classifications/workqueue-page') return route.fulfill({ json: {
      total: 1, limit: 8, offset: 0, product_count_scope: 'filtered', task_count_scope: 'page',
      items: [{ id: 'catalog-milk', name: 'Halfvolle melk', gtin: '8712345678901',
        brand: '', gpc_code: '', cbs_code: '',
        gpc_status: 'unclassified', cbs_status: 'unclassified' }],
      tasks: [
        { key: 'catalog-milk:gpc', global_product_id: 'catalog-milk', system: 'gpc' },
        { key: 'catalog-milk:cbs', global_product_id: 'catalog-milk', system: 'cbs' },
      ],
    } })
    if (path === '/api/cbs-classifications/workqueue-ids') return route.fulfill({
      json: { ids: ['catalog-milk'], total: 1, offset: 0, limit: 1000 },
    })
    if (path === '/api/cbs-classifications/workqueue-selected-export') return route.fulfill({
      status: 200, contentType: 'text/csv; charset=utf-8',
      body: '\uFEFF"product_id";"Artikel"\r\n"catalog-milk";"Halfvolle melk"\r\n',
    })
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


test('Classificeren: echte serverpagina, globale filters en selectie/export over pagina’s', async ({ page }) => {
  const requests = await mountMockBackend(page)
  const calls = []
  const exported = []
  const items = Array.from({ length: 10 }, (_, index) => ({
    id: 'catalog-' + (index + 1),
    name: 'Product ' + String(index + 1).padStart(2, '0'),
    brand: index === 4 ? '=CMD' : '',
    gtin: index === 0 ? '0000000000001' : String(8710000000000 + index),
    gpc_code: index === 0 ? '10000001' : '',
    gpc_status: index === 0 ? 'classified' : 'unclassified',
    cbs_code: index === 9 ? '011420' : '',
    cbs_status: index === 9 ? 'classified' : 'unclassified',
    cbs_name: index === 9 ? 'Melk' : '',
    cbs_reference_version: index === 9 ? '2026' : '',
  }))
  await page.route('**/api/cbs-classifications/workqueue-summary', route => route.fulfill({ json: {
    product_total: 10, task_total: 18,
    task_count_scope: 'global', product_count_scope: 'global',
  } }))
  await page.route('**/api/cbs-classifications/workqueue-page?**', async route => {
    const query = new URL(route.request().url()).searchParams
    const offset = Number(query.get('offset') || 0)
    const filter = query.get('cbs_status') || ''
    const filtered = filter.toLowerCase().includes('niet g')
      ? items.filter(item => !item.cbs_code) : items
    calls.push({ offset, limit: query.get('limit'), filter,
      sort: query.get('sort'), direction: query.get('direction') })
    return route.fulfill({ json: {
      total: filtered.length, offset, limit: 8,
      task_count_scope: 'page', product_count_scope: 'filtered',
      items: filtered.slice(offset, offset + 8),
      tasks: filtered.slice(offset, offset + 8).flatMap(item => [
        ...(!item.gpc_code ? [{ key: item.id + ':gpc', global_product_id: item.id, system: 'gpc' }] : []),
        ...(!item.cbs_code ? [{ key: item.id + ':cbs', global_product_id: item.id, system: 'cbs' }] : []),
      ]),
    } })
  })
  await page.route('**/api/cbs-classifications/workqueue-ids?**', async route => {
    const query = new URL(route.request().url()).searchParams
    const filtered = (query.get('cbs_status') || '').toLowerCase().includes('niet g')
      ? items.filter(item => !item.cbs_code) : items
    return route.fulfill({ json: {
      ids: filtered.map(item => item.id), total: filtered.length, offset: 0, limit: 1000,
    } })
  })
  await page.route('**/api/cbs-classifications/workqueue-selected-export', async route => {
    const ids = route.request().postDataJSON().product_ids
    exported.push(ids)
    const content = '\uFEFF"product_id";"Artikel";"Merk";"Barcode";"GS1 GPC code";"CBS ECOICOPv2 code"\r\n'
      + ids.map(id => {
        const item = items.find(product => product.id === id)
        return '"' + id + '";"' + item.name + '";"'
          + (item.brand ? "'=CMD" : '') + '";"' + item.gtin + '";"";""\r\n'
      }).join('')
    return route.fulfill({
      status: 200, contentType: 'text/csv; charset=utf-8',
      body: content, headers: {
        'content-disposition': 'attachment; filename="Inhuis_Artikelclassificeren_Geselecteerde_artikelen.csv"',
      },
    })
  })

  await page.goto('/externe-databases-2')
  await page.getByRole('button', { name: 'Classificeren' }).click()
  const table = page.getByTestId('combined-classification-articles')
  const selectionCount = page.getByTestId('classification-workqueue-selected-count')
  const all = page.getByTestId('classification-workqueue-select-all-table')
  const pageAll = page.getByTestId('classification-workqueue-select-all-page')
  const exportButton = page.getByTestId('classification-workqueue-export')
  const paging = page.getByRole('navigation', { name: 'Paginering' })

  await expect(table).toContainText('Product 01')
  await expect(page.getByTestId('classification-first-page-ready')).toContainText('10 artikelen')
  await expect(selectionCount).toContainText('0 rijen geselecteerd')
  await expect(exportButton).toBeDisabled()
  await expect(table.getByRole('checkbox', { name: /^Selecteer Product/ })).toHaveCount(8)
  expect(calls[0]).toMatchObject({ offset: 0, limit: '8', sort: 'name', direction: 'asc' })
  // React StrictMode may repeat the same GET, but must never download a
  // second (or hundred-item) batch without a user paging/filtering action.
  expect(calls.length).toBeGreaterThanOrEqual(1)
  expect(calls.every(call => call.offset === 0 && call.limit === '8')).toBe(true)
  const header = table.locator('thead tr').first().locator('th').first()
  await expect(header.getByRole('checkbox', { name: 'Alle rijen op deze pagina' })).toBeVisible()

  await pageAll.check()
  await expect(selectionCount).toContainText('8 rijen geselecteerd')
  await expect(all).not.toBeChecked()
  await paging.getByRole('button', { name: '+' }).click()
  await expect(table.getByRole('checkbox', { name: /^Selecteer Product/ })).toHaveCount(2)
  await pageAll.check()
  await expect(selectionCount).toContainText('10 rijen geselecteerd')
  await expect(all).toBeChecked()
  await all.uncheck()
  await expect(selectionCount).toContainText('0 rijen geselecteerd')

  // Selection outside a new filter stays selected and exportable.
  await table.getByRole('checkbox', { name: 'Selecteer Product 10' }).check()
  await expect(page.getByTestId('combined-selected-article')).toHaveCount(0)
  const cbsFilter = table.getByRole('textbox', { name: 'Filter op CBS ECOICOPv2' })
  await cbsFilter.fill('niet g')
  await expect(table.getByRole('checkbox', { name: /^Selecteer Product/ })).toHaveCount(8)
  await all.check()
  await expect(selectionCount).toContainText('10 rijen geselecteerd')
  await expect(all).toBeChecked()

  const downloadPromise = page.waitForEvent('download')
  await exportButton.click()
  const download = await downloadPromise
  expect(download.suggestedFilename()).toBe('Inhuis_Artikelclassificeren_Geselecteerde_artikelen.csv')
  const contents = await readFile(await download.path(), 'utf8')
  expect(contents.charCodeAt(0)).toBe(0xfeff)
  expect(contents).toContain('"catalog-1";"Product 01"')
  expect(contents).toContain('"catalog-5";"Product 05";"\'=CMD"')
  expect(contents).toContain('"catalog-10";"Product 10"')
  expect(contents.split('\r\n').filter(Boolean)).toHaveLength(11)
  expect(exported).toHaveLength(1)
  expect(exported[0]).toHaveLength(10)
  expect(requests.filter(req => req.method === 'POST'
    && req.path !== '/api/cbs-classifications/workqueue-selected-export')).toEqual([])

  await page.getByTestId('app-feedback-success-overlay').click({ position: { x: 2, y: 2 } })
  await page.getByTestId('classification-workqueue-clear').click()
  await expect(selectionCount).toContainText('0 rijen geselecteerd')
  await expect(exportButton).toBeDisabled()
})

test('Classificeren: alleen nieuwe en afwijkende classificaties, rijselectie en bulk onder de tabel', async ({ page }) => {
  await mountMockBackend(page)
  const sent = []
  await page.route('**/api/cbs-classifications/classification-import/preview', route => route.fulfill({ json: {
    total: 617, unchanged: 616, changed_count: 1, gpc_new: 0, gpc_replace: 1,
    cbs_new: 1, cbs_replace: 0, blocked: 0, review_existing: 1, no_changes_yet: true,
    rows: [{
      product_id: 'product-milk', name: 'Halfvolle melk', brand: '',
      snapshot_sha256: 'a'.repeat(64), current_gpc: '10000002', current_cbs: '',
      gpc_status: 'Bestaand - controle nodig', cbs_status: 'Voorstel hoog',
      gpc_reason: 'GS1 mogelijk onjuist', cbs_reason: 'Productnaam', review_existing: true,
      problem: '', invalid_gpc: [], invalid_cbs: [],
      gpc_change: { code: '10000001', label: 'Drinkmelk', kind: 'bestaand controleren' },
      cbs_change: { code: '011420', label: 'Melk', reference_version: '2026', kind: 'voorstel' },
    }],
  } }))
  await page.route('**/api/cbs-classifications/classification-import/confirm', async route => {
    sent.push(route.request().postDataJSON())
    await route.fulfill({ json: { updated_gpc: 1, updated_cbs: 1, unchanged: 0, processed: 2 } })
  })
  await page.goto('/externe-databases-2')
  await page.getByRole('button', { name: 'Classificeren' }).click()
  await page.getByTestId('classification-file').setInputFiles({
    name: 'Inhuis_Classificatievoorstellen.csv', mimeType: 'text/csv',
    buffer: Buffer.from('testfile-contents'),
  })
  await expect(page.getByTestId('classification-import-table')).toHaveCount(0)
  await page.getByTestId('classification-import-preview').click()
  const table = page.getByTestId('classification-import-table')
  await expect(table).toContainText('Halfvolle melk')
  await expect(table).toContainText('10000001')
  await expect(table).toContainText('011420')
  await expect(table).toContainText('Productnaam')
  await expect(page.getByTestId('classification-import-summary')).toContainText('616 gelijke overgeslagen')
  await expect(table.getByRole('checkbox')).toHaveCount(2)
  await expect(table.getByRole('combobox')).toHaveCount(0)
  await expect(page.getByText('Bestaande code vervangen')).toHaveCount(0)
  const selection = table.getByRole('checkbox', { name: 'Selecteer Halfvolle melk' })
  const all = page.getByTestId('classification-import-panel').getByRole('checkbox', { name: 'Alle rijen in de tabel' })
  const pageAll = table.getByRole('checkbox', { name: 'Alle rijen op deze pagina' })
  const header = table.locator('thead tr').first().locator('th').first()
  await expect(header.getByRole('checkbox', { name: 'Alle rijen op deze pagina' })).toBeVisible()
  await expect(header).not.toContainText('Alle rijen in de tabel')
  await expect(header).not.toContainText('Selecteer')
  await expect(page.locator('.rz-classification-import-select-actions')).toHaveCSS('justify-content', 'flex-end')
  await expect(all).toBeVisible()
  await expect(page.getByTestId('classification-import-confirm')).toBeDisabled()
  await pageAll.check()
  await expect(selection).toBeChecked()
  await expect(all).toBeChecked()
  await pageAll.uncheck()
  await expect(selection).not.toBeChecked()
  await all.check()
  await expect(selection).toBeChecked()
  await all.uncheck()
  await expect(selection).not.toBeChecked()
  await selection.check()
  await expect(page.getByTestId('classification-import-confirm')).toContainText('(1)')
  const bulk = page.getByTestId('classification-import-confirm')
  await bulk.click()
  await expect(page.getByTestId('app-feedback-warning-overlay')).toContainText('1 GS1 vervangen')
  await expect(page.getByTestId('app-feedback-warning-overlay')).toContainText('1 CBS nieuw')
  expect(sent).toHaveLength(0)
  await page.getByRole('button', { name: 'Annuleren' }).click()
  await expect(selection).toBeChecked()
  await bulk.click()
  await page.getByRole('button', { name: 'Goedkeuren en verwerken' }).click()
  await expect.poll(() => sent.length).toBe(1)
  expect(sent[0].decisions.map(item => item.system).sort()).toEqual(['cbs', 'gpc'])
  expect(sent[0].decisions.find(item => item.system === 'gpc').allow_replace).toBe(true)
  expect(sent[0].decisions.find(item => item.system === 'cbs').allow_replace).toBe(false)
  await expect(table).toContainText('Geen nieuwe of afwijkende classificaties gevonden.')
})

test('Classificeren: identieke voorstellen verdwijnen zelfs als Excel controle nodig zegt', async ({ page }) => {
  await mountMockBackend(page)
  await page.route('**/api/cbs-classifications/classification-import/preview', route => route.fulfill({ json: {
    total: 617, unchanged: 617, changed_count: 0, gpc_new: 0, gpc_replace: 0,
    cbs_new: 0, cbs_replace: 0, blocked: 0, review_existing: 0, no_changes_yet: true,
    rows: [],
  } }))
  await page.goto('/externe-databases-2')
  await page.getByRole('button', { name: 'Classificeren' }).click()
  await page.getByTestId('classification-file').setInputFiles({
    name: 'classificaties.csv', mimeType: 'text/csv',
    buffer: Buffer.from('unused'),
  })
  await page.getByTestId('classification-import-preview').click()
  await expect(page.getByTestId('classification-import-summary')).toContainText('617 gelijke overgeslagen')
  await expect(page.getByTestId('classification-import-table')).toContainText('Geen nieuwe of afwijkende classificaties gevonden.')
  await expect(page.getByTestId('classification-import-confirm')).toBeDisabled()
  await expect(page.getByTestId('classification-import-panel').getByRole('checkbox', { name: 'Alle rijen in de tabel' })).toBeDisabled()
})

test('Classificeren: selecteer alle gefilterde tabelrijen over paginagrenzen', async ({ page }) => {
  await mountMockBackend(page)
  const rows = Array.from({ length: 9 }, (_, index) => ({
    product_id: `article-${index + 1}`,
    name: `Product ${String(index + 1).padStart(2, '0')}`,
    brand: '', snapshot_sha256: 'b'.repeat(64),
    current_gpc: '', current_cbs: '',
    gpc_status: '', cbs_status: 'Voorstel hoog', gpc_reason: '', cbs_reason: 'Productnaam',
    review_existing: false, problem: '', invalid_gpc: [], invalid_cbs: [],
    gpc_options: [], cbs_options: [],
    gpc_change: null, cbs_change: {
      code: '011420', label: 'Melk', reference_version: '2026', kind: 'voorstel',
    },
  }))
  await page.route('**/api/cbs-classifications/classification-import/preview', route => route.fulfill({ json: {
    total: 9, unchanged: 0, changed_count: 9, blocked: 0,
    gpc_new: 0, gpc_replace: 0, cbs_new: 9, cbs_replace: 0,
    rows,
  } }))
  await page.goto('/externe-databases-2')
  await page.getByRole('button', { name: 'Classificeren' }).click()
  await page.getByTestId('classification-file').setInputFiles({
    name: 'voorstellen.csv', mimeType: 'text/csv', buffer: Buffer.from('mock'),
  })
  await page.getByTestId('classification-import-preview').click()
  const table = page.getByTestId('classification-import-table')
  const all = page.getByTestId('classification-import-panel').getByRole('checkbox', { name: 'Alle rijen in de tabel' })
  const pageAll = table.getByRole('checkbox', { name: 'Alle rijen op deze pagina' })
  const paging = page.getByRole('navigation', { name: 'Paginering' })
  await expect(table.getByRole('checkbox', { name: /^Selecteer Product/ })).toHaveCount(8)

  // The header checkbox selects only the eight rows on the visible page.
  await pageAll.check()
  await expect(page.getByTestId('classification-import-panel').getByText('8 rijen geselecteerd')).toBeVisible()
  await expect(all).not.toBeChecked()
  await paging.getByRole('button', { name: '+' }).click()
  await expect(table.getByRole('checkbox', { name: /^Selecteer Product/ })).toHaveCount(1)
  await expect(pageAll).not.toBeChecked()
  await pageAll.check()
  await expect(page.getByTestId('classification-import-panel').getByText('9 rijen geselecteerd')).toBeVisible()
  await expect(all).toBeChecked()
  await pageAll.uncheck()
  await expect(page.getByTestId('classification-import-panel').getByText('8 rijen geselecteerd')).toBeVisible()

  // Changing page preserves the other page's selection and header state.
  await paging.getByRole('button', { name: '-' }).click()
  await expect(pageAll).toBeChecked()
  await expect(all).not.toBeChecked()
  await pageAll.uncheck()
  await expect(page.getByTestId('classification-import-panel').getByText('0 rijen geselecteerd')).toBeVisible()
  await expect(pageAll).not.toBeChecked()

  // The separate control above the table selects across page boundaries.
  await all.check()
  await expect(page.getByTestId('classification-import-panel').getByText('9 rijen geselecteerd')).toBeVisible()
  await all.uncheck()
  await expect(page.getByTestId('classification-import-panel').getByText('0 rijen geselecteerd')).toBeVisible()

  // Both controls obey the current DataTable filters, without forgetting other selections.
  await table.getByRole('textbox', { name: 'Filter op Artikel' }).fill('Product 09')
  await expect(table).toContainText('Product 09')
  await expect(table.getByRole('checkbox', { name: /^Selecteer Product/ })).toHaveCount(1)
  await all.check()
  await expect(pageAll).toBeChecked()
  await expect(page.getByTestId('classification-import-panel').getByText('1 rijen geselecteerd')).toBeVisible()
  await table.getByRole('textbox', { name: 'Filter op Artikel' }).fill('')
  await expect(all).not.toBeChecked()
  await expect(page.getByTestId('classification-import-panel').getByText('1 rijen geselecteerd')).toBeVisible()
})

test('Classificeren: persistente keuze verwerkt eerste 100 artikelrijen, inclusief 200 GS1/CBS-codes', async ({ page }) => {
  await mountMockBackend(page)
  const rows = Array.from({ length: 101 }, (_, index) => ({
    product_id: `article-${index + 1}`,
    name: `Product ${String(index + 1).padStart(3, '0')}`, brand: '',
    snapshot_sha256: 'c'.repeat(64), current_gpc: '', current_cbs: '',
    gpc_status: 'Voorstel hoog', cbs_status: 'Voorstel hoog', gpc_reason: '', cbs_reason: '',
    review_existing: false, problem: '', invalid_gpc: [], invalid_cbs: [],
    gpc_options: [], cbs_options: [],
    gpc_change: { code: '10000001', label: 'GPC', reference_version: '' },
    cbs_change: { code: '011420', label: 'Melk', reference_version: '2026' },
  }))
  await page.route('**/api/cbs-classifications/classification-import/preview', route => route.fulfill({ json: {
    total: 101, unchanged: 0, changed_count: 101, blocked: 0,
    gpc_new: 101, gpc_replace: 0, cbs_new: 101, cbs_replace: 0, rows,
  } }))
  const attempted = []
  await page.route('**/api/cbs-classifications/classification-import/confirm', async route => {
    const decisions = route.request().postDataJSON().decisions
    attempted.push(decisions)
    await route.fulfill({ json: {
      updated_gpc: decisions.filter(item => item.system === 'gpc').length,
      updated_cbs: decisions.filter(item => item.system === 'cbs').length,
      unchanged: 0, processed: decisions.length,
    } })
  })
  await page.goto('/externe-databases-2')
  await page.getByRole('button', { name: 'Classificeren' }).click()
  await page.getByTestId('classification-file').setInputFiles({
    name: 'voorstellen.csv', mimeType: 'text/csv', buffer: Buffer.from('mock'),
  })
  await page.getByTestId('classification-import-preview').click()
  const all = page.getByTestId('classification-import-panel').getByRole('checkbox', { name: 'Alle rijen in de tabel' })
  const bulk = page.getByTestId('classification-import-confirm')
  await all.check()
  await expect(page.getByTestId('classification-import-panel').getByText('101 rijen geselecteerd')).toBeVisible()
  const prompt = page.getByTestId('app-feedback-warning-overlay')
  await expect(prompt).toContainText('100 artikelen (200 classificaties)')
  await expect(prompt).toContainText('1 andere geselecteerde rijen')
  await expect(page.getByRole('button', { name: 'Eerste 100 rijen verwerken' })).toBeVisible()
  expect(attempted).toHaveLength(0)

  // No auto-dismiss: even after the normal 4-second transient timeout, the
  // decision must still be visible until cancel/approval/outside-click.
  await page.waitForTimeout(4300)
  await expect(prompt).toBeVisible()
  await page.getByRole('button', { name: 'Annuleren' }).click()
  await expect(prompt).toHaveCount(0)
  expect(attempted).toHaveLength(0)
  await expect(bulk).toBeEnabled()

  await bulk.click()
  await expect(prompt).toBeVisible()
  await prompt.click({ position: { x: 2, y: 2 } })
  await expect(prompt).toHaveCount(0)
  expect(attempted).toHaveLength(0)

  await bulk.click()
  await page.getByRole('button', { name: 'Eerste 100 rijen verwerken' }).click()
  await expect.poll(() => attempted.length).toBe(1)
  expect(attempted[0]).toHaveLength(200)
  expect(new Set(attempted[0].map(item => item.product_id)).size).toBe(100)
  expect(attempted[0].filter(item => item.system === 'gpc')).toHaveLength(100)
  expect(attempted[0].filter(item => item.system === 'cbs')).toHaveLength(100)
  expect(attempted[0].some(item => item.product_id === 'article-101')).toBe(false)
  await expect(page.getByTestId('classification-import-panel').getByText('1 rijen geselecteerd')).toBeVisible()
  await expect(bulk).toContainText('(1)')

  // The remaining selected article can be processed in a new explicit batch.
  await page.getByTestId('app-feedback-success-overlay').click({ position: { x: 2, y: 2 } })
  await bulk.click()
  await expect(page.getByRole('button', { name: 'Goedkeuren en verwerken' })).toBeVisible()
  await page.getByRole('button', { name: 'Goedkeuren en verwerken' }).click()
  await expect.poll(() => attempted.length).toBe(2)
  expect(attempted[1]).toHaveLength(2)
  expect(attempted[1].map(item => item.product_id)).toEqual(['article-101', 'article-101'])
  await expect(page.getByTestId('classification-import-table')).toContainText('Geen nieuwe of afwijkende classificaties gevonden.')
})
