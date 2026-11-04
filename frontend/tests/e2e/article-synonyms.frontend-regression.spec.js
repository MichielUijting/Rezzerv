import { test, expect } from '@playwright/test'

test.use({ storageState: { cookies: [], origins: [] } })

for (const width of [390, 1280]) {
  test(`Artikel-synoniemen: uitgelijnde tabellen, checkboxen en ontkoppelen op ${width}px`, async ({ page }) => {
    await page.setViewportSize({ width, height: 900 })
    const posts = []
    const articles = [
      { id: 'a', name: 'Aardappelen', primary_gtin: '08719587325926', synonym_count: 1 },
      { id: 'b', name: 'Aardappelen', primary_gtin: '08718452513666', synonym_count: 0 },
      { id: 'c', name: 'Kruimige aardappelen', primary_gtin: '08712345678906', synonym_count: 1 },
      { id: 'd', name: 'Snijbonen', primary_gtin: '08712345678913', synonym_count: 0 },
    ]
    const options = [
      { id: 'c', name: 'Kruimige aardappelen', primary_gtin: '08712345678906',
        status: 'linked', status_label: 'Al gekoppeld', linkable: false,
        fingerprint: 'c'.repeat(64), reason: 'Al gekoppeld', manual: true },
      { id: 'b', name: 'Aardappelen', primary_gtin: '08718452513666',
        status: 'suggested', status_label: 'Voorstel', linkable: true,
        fingerprint: 'b'.repeat(64), manual: false },
      { id: 'd', name: 'Snijbonen', primary_gtin: '08712345678913',
        status: 'other', status_label: 'Niet koppelbaar', linkable: false,
        reason: 'De GS1 GPC-classificaties verschillen: 10000001 tegenover 10000002.',
        conflict_type: 'gpc_mismatch', conflict_detail: 'De GS1 GPC-classificaties verschillen: 10000001 tegenover 10000002.',
        resolution_route: '/catalogus/gpc-classificeren', fingerprint: 'd'.repeat(64), manual: true },
    ]
    // Both DataTables must actually paginate; <=10 mocked rows hide
    // the shared pagination controls by design.
    for (let i = 0; i < 9; i += 1) {
      const id = `extra-${i}`
      articles.push({ id, name: `Z extra artikel ${i}`, primary_gtin: `87123456789${String(i).padStart(2, '0')}`, synonym_count: 0 })
      options.push({ id, name: `Z extra artikel ${i}`, primary_gtin: `87123456789${String(i).padStart(2, '0')}`,
        status: 'other', status_label: 'Overig', linkable: true, manual: true,
        fingerprint: 'e'.repeat(64) })
    }
    await page.route('**/api/**', async (route) => {
      const path = new URL(route.request().url()).pathname
      if (path === '/api/session') return route.fulfill({ json: {
        user_id: 'synonym-test', active_household_id: '0', context_type: 'system',
        is_platform_superuser: true, role: 'admin',
        permissions: { 'platform.external_products.view': true,
          'platform.external_products.link_existing': true },
      } })
      if (path.endsWith('/article-synonyms/link/review')) {
        const body = route.request().postDataJSON()
        const clashes = body.selections.some((item) =>
          item.left_product_id === 'd' || item.right_product_id === 'd')
        return route.fulfill({ json: { items: clashes ? [{
          left_id: 'a', right_id: 'd', snapshot: 'a'.repeat(64),
          clashes: [{ system: 'GPC',
            left: { id: 'a', name: 'Aardappelen', code: '10000001', label: 'Aardappelen' },
            right: { id: 'd', name: 'Snijbonen', code: '10000002', label: 'Bonen' },
          }],
        }] : [] } })
      }
      if (path.endsWith('/article-synonyms/link') || path.endsWith('/article-synonyms/unlink')) {
        const action = path.endsWith('/unlink') ? 'unlink' : 'link'
        const payload = route.request().postDataJSON()
        posts.push({ action, payload })
        for (const choice of payload.selections) {
          const target = options.find((item) => item.id === choice.right_product_id)
          if (target) {
            target.status = action === 'unlink' ? 'other' : 'linked'
            target.status_label = action === 'unlink' ? 'Overig' : 'Al gekoppeld'
            target.linkable = action === 'unlink'
          }
        }
        return route.fulfill({ json: { linked: action === 'link' ? payload.selections.length : 0,
          unlinked: action === 'unlink' ? payload.selections.length : 0,
          ...(action === 'link' ? {
            classification_inheritance: { gpc_inherited: 1, cbs_inherited: 1, conflicts: [] },
          } : {}),
        } })
      }
      if (path.endsWith('/article-synonyms/analysis/a/options')) return route.fulfill({ json: { items: options } })
      if (path.endsWith('/article-synonyms/analysis')) return route.fulfill({ json: { items: articles } })
      if (path === '/api/onboarding') return route.fulfill({ json: { onboarding_status: 'completed' } })
      if (path === '/api/features') return route.fulfill({ json: { features: {} } })
      if (path === '/api/action-buttons') return route.fulfill({ json: { items: [] } })
      return route.fulfill({ json: {} })
    })
    await page.goto('/artikelsynoniemen')
    const left = page.getByTestId('article-synonyms-articles')
    const right = page.getByTestId('article-synonyms-table')
    await expect(left).toBeVisible()
    await expect(right).toBeVisible()
    for (const table of [left, right]) {
      await expect(table.locator('thead tr').first().locator('th')).toHaveCount(table === left ? 5 : 4)
      await expect(table.locator('thead')).toContainText('Foto')
      await expect(table.locator('thead')).toContainText('Artikelnaam')
      await expect(table.locator('thead')).toContainText('Barcode')
      await expect(table.locator('thead')).not.toContainText('Winkel')
    }
    // Beide checkbox- en fotokolommen hebben dezelfde breedte; de vrijgekomen
    // ruimte gaat naar de linker artikelnaam zonder Syn. weg te drukken.
    const leftCols = await left.locator('colgroup col').evaluateAll((cols) =>
      cols.map((col) => Math.round(parseFloat(col.style.width))))
    const rightCols = await right.locator('colgroup col').evaluateAll((cols) =>
      cols.map((col) => Math.round(parseFloat(col.style.width))))
    expect(leftCols).toEqual([42, 70, 236, 112, 52])
    expect(leftCols[0]).toBe(rightCols[0])
    expect(leftCols[1]).toBe(rightCols[1])
    expect(leftCols.reduce((total, value) => total + value, 0))
      .toBe(rightCols.reduce((total, value) => total + value, 0))
    await expect(left.locator('thead')).toContainText('Syn.')
    await expect(left.locator('thead')).not.toContainText('Synoniemen')
    await expect(page.getByText('Externe databases 2', { exact: true })).toHaveCount(0)
    const synHeader = left.getByRole('columnheader', { name: /Syn\./ })
    await expect(synHeader).toBeVisible()
    if (width > 900) {
      const leftWidth = await left.evaluate((table) => table.parentElement.clientWidth)
      const scrollWidth = await left.evaluate((table) => table.scrollWidth)
      expect(scrollWidth).toBeLessThanOrEqual(leftWidth + 4)
    }
    await expect(right.locator('thead')).not.toContainText('Synoniemen')
    await expect(left.locator('tbody tr').first().locator('td').last()).toHaveText('1')
    await expect(left.locator('tbody tr').nth(1).locator('td').last()).toHaveText('0')
    const leftCheck = left.locator('tbody tr').first().getByRole('checkbox')
    await leftCheck.check()
    await expect(leftCheck).toBeChecked()
    await expect(right.locator('tbody tr')).toHaveCount(10)
    const panes = page.locator('.rz-synonym-side')
    const leftPagination = panes.nth(0).locator('.rz-data-table-controls')
    const rightPagination = panes.nth(1).locator('.rz-data-table-controls')
    await expect(leftPagination).toBeVisible()
    await expect(rightPagination).toBeVisible()
    const leftBottom = await leftPagination.boundingBox()
    const rightBottom = await rightPagination.boundingBox()
    if (width > 900) expect(Math.abs(leftBottom.y - rightBottom.y)).toBeLessThan(2)
    else expect(rightBottom.y).toBeGreaterThan(leftBottom.y)
    const actionBar = panes.nth(1).locator('.rz-synonym-analysis-actions')
    const actionBox = await actionBar.boundingBox()
    expect(actionBox.y).toBeGreaterThan(rightBottom.y + rightBottom.height - 1)
    await expect(rightPagination.getByRole('button', { name: 'Koppelen' })).toHaveCount(0)
    await expect(rightPagination.getByRole('button', { name: 'Ontkoppelen' })).toHaveCount(0)
    await expect(right.locator('tbody tr').first()).toHaveClass(/rz-synonym-relation-linked/)
    await expect(right.locator('tbody tr').nth(1)).toHaveClass(/rz-synonym-relation-suggested/)
    await expect(right.locator('tbody tr').nth(2)).toHaveClass(/rz-synonym-relation-other/)
    await expect(right).not.toContainText('08719587325926')
    await expect(right.getByRole('checkbox')).toHaveCount(10)
    const conflictCheckbox = right.locator('tbody tr').filter({ hasText: '08712345678913' }).getByRole('checkbox')
    await expect(conflictCheckbox).toBeEnabled()
    await conflictCheckbox.check()
    await expect(page.getByRole('button', { name: 'Koppelen', exact: true })).toBeEnabled()
    await page.getByRole('button', { name: 'Koppelen', exact: true }).click()
    const choiceDialog = page.getByTestId('article-synonyms-classification-choice')
    await expect(choiceDialog).toBeVisible()
    await expect(choiceDialog.getByTestId('article-synonyms-classification-choice-comparison')).toContainText('Aardappelen')
    await expect(choiceDialog.getByTestId('article-synonyms-classification-choice-comparison')).toContainText('Snijbonen')
    await expect(choiceDialog.getByTestId('article-synonyms-classification-choice-comparison')).toContainText('10000001')
    await expect(choiceDialog.getByTestId('article-synonyms-classification-choice-comparison')).toContainText('10000002')
    await expect(choiceDialog.getByTestId('article-synonyms-classification-choice-field-choice_0_GPC')).toBeVisible()
    expect(posts).toHaveLength(0)
    await choiceDialog.getByRole('button', { name: 'Annuleren' }).click()
    await expect(choiceDialog).toHaveCount(0)
    await conflictCheckbox.uncheck()
    await expect(page.getByText(/geselecteerd$/)).toHaveCount(0)
    const leftTop = await left.locator('thead').boundingBox()
    const rightTop = await right.locator('thead').boundingBox()
    if (width > 900) expect(Math.abs(leftTop.y - rightTop.y)).toBeLessThan(2)
    else expect(rightTop.y).toBeGreaterThan(leftTop.y)
    const colors = await right.locator('tbody tr').evaluateAll((rows) =>
      rows.map((row) => getComputedStyle(row.cells[0]).backgroundColor))
    expect(colors[0]).not.toBe(colors[1])
    expect(colors[1]).not.toBe(colors[2])
    const linkedCheck = right.locator('tbody tr').first().getByRole('checkbox')
    await linkedCheck.check()
    await expect(page.getByRole('button', { name: 'Ontkoppelen' })).toBeEnabled()
    await expect(page.getByRole('button', { name: 'Koppelen', exact: true })).toBeDisabled()
    expect(posts).toHaveLength(0)
    await page.getByRole('button', { name: 'Ontkoppelen' }).click()
    await expect(linkedCheck).not.toBeChecked()
    expect(posts[0].action).toBe('unlink')
    expect(posts[0].payload.selections).toEqual([{
      left_product_id: 'a', right_product_id: 'c', fingerprint: 'c'.repeat(64),
    }])
    await right.locator('tbody tr').filter({ hasText: '08718452513666' }).getByRole('checkbox').check()
    await expect(page.getByRole('button', { name: 'Koppelen', exact: true })).toBeEnabled()
    await expect(page.getByRole('button', { name: 'Ontkoppelen' })).toBeDisabled()
    await page.getByRole('button', { name: 'Koppelen', exact: true }).click()
    expect(posts[1].action).toBe('link')
    expect(posts[1].payload.selections).toEqual([{
      left_product_id: 'a', right_product_id: 'b', fingerprint: 'b'.repeat(64), manual: false,
    }])
    await expect(page.getByTestId('app-feedback-success'))
      .toContainText('1 GS1 GPC en 1 CBS automatisch overgenomen.')
  })
}


test('Bevestigd synoniem met classificatieconflict toont herstel-overlay zonder bestaande waarden te overschrijven', async ({ page }) => {
  await page.setViewportSize({ width: 1280, height: 900 })
  const posts = []
  await page.route('**/api/**', async (route) => {
    const path = new URL(route.request().url()).pathname
    if (path === '/api/session') return route.fulfill({ json: {
      user_id: 'synonym-test', active_household_id: '0', context_type: 'system',
      is_platform_superuser: true, role: 'admin',
      permissions: {
        'platform.external_products.view': true,
        'platform.external_products.link_existing': true,
      },
    } })
    if (path === '/api/external-databases/article-synonyms/analysis') return route.fulfill({
      json: { items: [
        { id: 'a', name: 'Melk A', primary_gtin: '8719587325926', synonym_count: 0 },
        { id: 'b', name: 'Melk B', primary_gtin: '8718452513666', synonym_count: 0 },
      ] },
    })
    if (path === '/api/external-databases/article-synonyms/analysis/a/options') return route.fulfill({
      json: { items: [
        { id: 'b', name: 'Melk B', primary_gtin: '8718452513666', status: 'other',
          status_label: 'Overig', linkable: true, manual: true,
          fingerprint: 'b'.repeat(64) },
      ] },
    })
    if (path.endsWith('/article-synonyms/link')) {
      posts.push(route.request().postDataJSON())
      return route.fulfill({ json: {
        linked: 1, already_linked: 0,
        classification_inheritance: {
          gpc_inherited: 0, cbs_inherited: 1,
          conflicts: [{ system: 'GPC', product_ids: ['a', 'b'] }],
        },
      } })
    }
    if (path === '/api/onboarding') return route.fulfill({ json: { onboarding_status: 'completed' } })
    if (path === '/api/features') return route.fulfill({ json: { features: {} } })
    if (path === '/api/action-buttons') return route.fulfill({ json: { items: [] } })
    return route.fulfill({ json: {} })
  })
  await page.goto('/artikelsynoniemen')
  const left = page.getByTestId('article-synonyms-articles')
  await left.locator('tbody tr').filter({ hasText: 'Melk A' }).getByRole('checkbox').check()
  const right = page.getByTestId('article-synonyms-table')
  await right.locator('tbody tr').filter({ hasText: 'Melk B' }).getByRole('checkbox').check()
  await page.getByRole('button', { name: 'Koppelen', exact: true }).click()
  const dialog = page.getByTestId('article-synonyms-inheritance-conflict')
  await expect(dialog).toBeVisible()
  await expect(dialog).toContainText('1 synoniemkoppeling(en) bevestigd')
  await expect(dialog).toContainText('0 GS1 GPC en 1 CBS overgenomen')
  await expect(dialog).toContainText('bestaande waarden behouden')
  await expect(dialog.getByRole('button', { name: 'Naar GS1 GPC' })).toBeVisible()
  expect(posts).toHaveLength(1)
  await dialog.getByRole('button', { name: 'Sluiten' }).click()
  await expect(dialog).toHaveCount(0)
})

test('Twee verschillende classificaties tonen artikelcodes naast elkaar en vereisen twee afzonderlijke keuzes', async ({ page }) => {
  await page.setViewportSize({ width: 1280, height: 900 })
  const posts = []
  const a = { id: 'a', name: 'Halfvolle melk A', primary_gtin: '8719587325926', synonym_count: 0 }
  const b = { id: 'b', name: 'Halfvolle melk B', primary_gtin: '8718452513666', synonym_count: 0 }
  await page.route('**/api/**', async (route) => {
    const path = new URL(route.request().url()).pathname
    if (path === '/api/session') return route.fulfill({ json: {
      user_id: 'synonym-test', active_household_id: '0', context_type: 'system',
      is_platform_superuser: true, role: 'admin',
      permissions: { 'platform.external_products.view': true,
        'platform.external_products.link_existing': true, 'gpc.update': true },
    } })
    if (path.endsWith('/article-synonyms/analysis')) return route.fulfill({ json: { items: [a, b] } })
    if (path.endsWith('/article-synonyms/analysis/a/options')) return route.fulfill({ json: { items: [
      { ...b, status: 'other', status_label: 'Niet koppelbaar', linkable: false,
        conflict_type: 'gpc_mismatch', fingerprint: 'b'.repeat(64), manual: true },
    ] } })
    if (path.endsWith('/article-synonyms/link/review')) return route.fulfill({ json: { items: [{
      left_id: 'a', right_id: 'b', snapshot: 'c'.repeat(64),
      clashes: [
        { system: 'GPC',
          left: { id: 'a', name: a.name, code: '10000025', label: 'Melk' },
          right: { id: 'b', name: b.name, code: '10000026', label: 'Andere melk' } },
        { system: 'CBS',
          left: { id: 'a', name: a.name, code: '011420', label: 'Melkproducten', reference: 'CBS-2026' },
          right: { id: 'b', name: b.name, code: '011410', label: 'Overige zuivel', reference: 'CBS-2026' } },
      ],
    }] } })
    if (path.endsWith('/article-synonyms/link')) {
      posts.push(route.request().postDataJSON())
      return route.fulfill({ json: {
        linked: 1, classification_inheritance: {
          gpc_inherited: 0, cbs_inherited: 0, gpc_resolved: 1, cbs_resolved: 1, conflicts: [],
        },
      } })
    }
    if (path === '/api/onboarding') return route.fulfill({ json: { onboarding_status: 'completed' } })
    if (path === '/api/features') return route.fulfill({ json: { features: {} } })
    if (path === '/api/action-buttons') return route.fulfill({ json: { items: [] } })
    return route.fulfill({ json: {} })
  })
  await page.goto('/artikelsynoniemen')
  await page.getByTestId('article-synonyms-articles').locator('tbody tr').first().getByRole('checkbox').check()
  await page.getByTestId('article-synonyms-table').locator('tbody tr').first().getByRole('checkbox').check()
  await page.getByRole('button', { name: 'Koppelen', exact: true }).click()
  const dialog = page.getByTestId('article-synonyms-classification-choice')
  await expect(dialog).toBeVisible()
  const comparison = dialog.getByTestId('article-synonyms-classification-choice-comparison')
  for (const label of ['Halfvolle melk A', 'Halfvolle melk B', '10000025', '10000026',
    '011420', '011410', 'Melkproducten', 'Overige zuivel']) {
    await expect(comparison).toContainText(label)
  }
  await dialog.getByTestId('article-synonyms-classification-choice-field-choice_0_GPC').selectOption('a')
  expect(posts).toHaveLength(0)
  await dialog.getByRole('button', { name: 'Keuze bevestigen en koppelen' }).click()
  await expect(dialog.getByTestId('article-synonyms-classification-choice-action-error'))
    .toContainText('Vul cbs')
  expect(posts).toHaveLength(0)
  await dialog.getByTestId('article-synonyms-classification-choice-field-choice_0_CBS').selectOption('b')
  await dialog.getByRole('button', { name: 'Keuze bevestigen en koppelen' }).click()
  await expect(dialog).toHaveCount(0)
  expect(posts).toHaveLength(1)
  expect(posts[0].decisions).toEqual([{
    left_product_id: 'a', right_product_id: 'b',
    snapshot: 'c'.repeat(64), gpc_source_id: 'a', cbs_source_id: 'b',
  }])
  await expect(page.getByTestId('app-feedback-success')).toContainText('1 GS1 GPC- en 1 CBS-keuzes verwerkt')
})

test('reguliere gebruiker krijgt geen suggesties', async ({ page }) => {
  let reads = 0
  await page.route('**/api/**', async (route) => {
    const path = new URL(route.request().url()).pathname
    if (path.includes('/article-synonyms')) reads++
    if (path === '/api/session') return route.fulfill({ json: { user_id: 'regular', active_household_id: 'h', context_type: 'regular', role: 'admin', permissions: {} } })
    if (path === '/api/onboarding') return route.fulfill({ json: { onboarding_status: 'completed' } })
    return route.fulfill({ json: {} })
  })
  await page.goto('/artikelsynoniemen')
  await expect(page).toHaveURL(/\/home$/)
  await expect(page.getByTestId('article-synonyms-table')).toHaveCount(0)
  expect(reads).toBe(0)
})

for (const width of [390, 1280]) {
  test(`Catalogus toont het aantal gekoppelde winkels op ${width}px`, async ({ page }) => {
    await page.setViewportSize({ width, height: 900 })
    const articles = [
      { id: 'ah', name: 'Halfvolle melk AH', catalog_kind: 'exact', linked_store_count: 1 },
      { id: 'jumbo', name: 'Halfvolle melk Jumbo', catalog_kind: 'exact', linked_store_count: 1 },
      { id: 'other', name: 'Brood', catalog_kind: 'exact', linked_store_count: 0 },
    ]
    await page.route('**/api/**', async (route) => {
      const path = new URL(route.request().url()).pathname
      if (path === '/api/session') return route.fulfill({ json: {
        user_id: 'synonym-test', active_household_id: '0', context_type: 'system', role: 'admin',
        is_platform_superuser: true, permissions: {},
      } })
      if (path === '/api/catalog') return route.fulfill({ json: {
        items: articles, total: articles.length, limit: 10, offset: 0,
      } })
      if (path === '/api/onboarding') return route.fulfill({ json: { onboarding_status: 'completed' } })
      if (path === '/api/features') return route.fulfill({ json: { features: {} } })
      if (path === '/api/action-buttons') return route.fulfill({ json: { items: [] } })
      return route.fulfill({ json: {} })
    })
    await page.goto('/catalogus')
    if (width > 720) {
      await expect(page.getByTestId('catalog-linked-stores-ah')).toHaveText('1')
      await expect(page.getByTestId('catalog-linked-stores-jumbo')).toHaveText('1')
      await expect(page.getByTestId('catalog-linked-stores-other')).toHaveText('0')
      await expect(page.getByRole('columnheader', { name: /Gekoppelde winkels/ })).toBeVisible()
      await expect(page.getByRole('textbox', { name: 'Filter gekoppelde winkels' })).toBeVisible()
    } else {
      await expect(page.getByTestId('mobile-catalog-open-ah')).toContainText('Gekoppelde winkels: 1')
      await expect(page.getByTestId('mobile-catalog-open-other')).toContainText('Gekoppelde winkels: 0')
    }
  })
}


for (const width of [390, 1280]) {
  test('Synoniemenanalyse: vier tellerfilters en beide opslagroutes op ' + width + 'px', async ({ page }) => {
    await page.setViewportSize({ width, height: 900 })
    const links = new Set()
    const posts = []
    const definitions = [
      ['ah', 'Halfvolle melk AH', 'Albert Heijn'],
      ['jumbo', 'Halfvolle melk Jumbo', 'Jumbo'],
      ['lidl', 'Halfvolle melk Lidl', 'Lidl'],
      ['plus', 'Halfvolle melk PLUS', 'PLUS'],
      ['aldi', 'Halfvolle melk Aldi', 'Aldi'],
      ['picnic', 'Halfvolle melk Picnic', 'Picnic'],
      ['dirk', 'Halfvolle melk Dirk', 'Dirk'],
      ['extra', 'Halfvolle melk extra', 'Hoogvliet'],
    ]
    const products = definitions.map(([id, name, store]) => ({
      id, name, store, store_name: store, group_key: 'shopify:Melk', group_label: 'Melk',
      brand: '', variant: '', retailer_code: id,
      image_url: '', size_value: '1', size_unit: 'l',
    }))
    const candidates = products.slice(1).map((other) => ({
      id: 'pair-ah-' + other.id, fingerprint: 'a'.repeat(64),
      left: products[0], right: other, warning: 'Controleer variant, bereiding en inhoud.',
    }))
    const linkKey = (a, b) => [a, b].sort().join('|')
    links.add(linkKey('ah', 'jumbo'))
    function analysis() {
      const items = products.map((p) => {
        const peers = products.filter((q) => links.has(linkKey(p.id, q.id)) && q.id !== p.id)
        return { ...p, synonym_count: peers.length,
          synonym_names: peers.map((q) => q.name), linked_stores: peers.map((q) => q.store),
          pending: [], status: peers.length ? 'linked' : 'no_candidate' }
      })
      return { summary: {
        synonym_buckets: {
          '0': items.filter((p) => p.synonym_count === 0).length,
          '1': items.filter((p) => p.synonym_count === 1).length,
          '2': items.filter((p) => p.synonym_count === 2).length,
          '3+': items.filter((p) => p.synonym_count >= 3).length,
        },
        eligible_articles: items.length,
      }, items }
    }
    await page.route('**/api/**', async (route) => {
      const path = new URL(route.request().url()).pathname
      if (path === '/api/session') return route.fulfill({ json: {
        user_id: 'synonym-test', active_household_id: '0', context_type: 'system', role: 'admin',
        is_platform_superuser: true, permissions: { 'platform.external_products.view': true, 'platform.external_products.link_existing': true },
      } })
      if (path.endsWith('/article-synonyms/link')) {
        const body = route.request().postDataJSON()
        posts.push(body)
        for (const item of body.selections) links.add(linkKey(item.left_product_id, item.right_product_id))
        return route.fulfill({ json: { linked: body.selections.length, already_linked: 0 } })
      }
      if (path.endsWith('/article-synonyms/analysis')) return route.fulfill({ json: analysis() })
      if (path.endsWith('/article-synonyms/analysis/ah/candidates')) {
        return route.fulfill({ json: { items: candidates.filter((p) => !links.has(linkKey(p.left.id, p.right.id))).slice(0, 5), limit: 5 } })
      }
      if (path === '/api/onboarding') return route.fulfill({ json: { onboarding_status: 'completed' } })
      if (path === '/api/features') return route.fulfill({ json: { features: {} } })
      if (path === '/api/action-buttons') return route.fulfill({ json: { items: [] } })
      return route.fulfill({ json: {} })
    })
    await page.goto('/catalogus/synoniemenanalyse')
    const main = page.getByTestId('synonym-analysis-items')
    await expect(main).toContainText('Halfvolle melk AH')
    await expect(page.getByRole('combobox', { name: 'Filter artikelsoort' })).toHaveCount(0)
    await expect(page.getByRole('combobox', { name: 'Filter winkel' })).toHaveCount(0)
    await expect(page.getByPlaceholder('Artikel, merk of winkel')).toHaveCount(0)
    // The shared table wrapper is capped for many screens; this page must not
    // put the horizontal scrollbar across its last visible article row.
    const mainDimensions = await main.evaluate((table) => {
      const wrapper = table.parentElement
      const lastRow = table.querySelector('tbody tr:last-child')
      return {
        scrollHeight: wrapper.scrollHeight,
        clientHeight: wrapper.clientHeight,
        wrapperBottom: wrapper.getBoundingClientRect().bottom,
        lastRowBottom: lastRow.getBoundingClientRect().bottom,
      }
    })
    expect(mainDimensions.scrollHeight).toBeLessThanOrEqual(mainDimensions.clientHeight + 1)
    expect(mainDimensions.wrapperBottom).toBeGreaterThanOrEqual(mainDimensions.lastRowBottom)
    await expect(page.getByTestId('synonym-count-0')).toContainText('6')
    await expect(page.getByTestId('synonym-count-1')).toContainText('2')
    await page.getByTestId('synonym-count-0').click()
    await expect(page.getByTestId('synonym-count-0')).toHaveAttribute('aria-pressed', 'true')
    await expect(main).not.toContainText('Halfvolle melk AH')
    await page.getByTestId('synonym-count-0').click()
    await expect(main).toContainText('Halfvolle melk AH')
    const articleRow = main.getByTestId('synonym-analysis-open-ah')
    await expect(articleRow.locator('button')).toHaveCount(0)
    await expect(articleRow.locator('td').first().locator('span').last()).toHaveText('Halfvolle melk AH')
    await expect(page.getByText('Bekijk hoeveel bevestigde synoniemen')).toHaveCount(0)
    await expect(page.getByText('Een synoniem is één rechtstreeks bevestigd')).toHaveCount(0)
    await expect(page.getByTestId('synonym-analysis-candidates')).toHaveCount(0)
    await articleRow.click()
    await expect(page.getByTestId('synonym-analysis-candidates')).toHaveCount(0)
    await articleRow.dblclick()
    await expect(page.getByRole('button', { name: 'Sluiten', exact: true })).toHaveCount(0)
    const table = page.getByTestId('synonym-analysis-candidate-table')
    await expect(table.locator('tbody tr')).toHaveCount(5)
    const candidateDimensions = await table.evaluate((tableElement) => {
      const wrapper = tableElement.parentElement
      const lastRow = tableElement.querySelector('tbody tr:last-child')
      return {
        scrollHeight: wrapper.scrollHeight,
        clientHeight: wrapper.clientHeight,
        wrapperBottom: wrapper.getBoundingClientRect().bottom,
        lastRowBottom: lastRow.getBoundingClientRect().bottom,
      }
    })
    expect(candidateDimensions.scrollHeight).toBeLessThanOrEqual(candidateDimensions.clientHeight + 1)
    expect(candidateDimensions.wrapperBottom).toBeGreaterThanOrEqual(candidateDimensions.lastRowBottom)
    await expect(page.getByTestId('synonym-analysis-confirm')).toBeDisabled()
    await table.getByRole('radio', { name: 'Selecteer Halfvolle melk Lidl als synoniem' }).check()
    await expect(page.getByTestId('synonym-analysis-confirm')).toBeEnabled()
    await page.getByTestId('synonym-analysis-confirm').click()
    await expect(page.getByTestId('synonym-count-0')).toContainText('5')
    await expect(page.getByTestId('synonym-count-2')).toContainText('1')
    await expect(main).toContainText('Halfvolle melk Lidl')
    await expect(table).not.toContainText('Halfvolle melk Lidl')
    const next = table.getByTestId('synonym-candidate-plus')
    await expect(next).toBeVisible()
    await next.dblclick()
    await expect(page.getByTestId('synonym-count-0')).toContainText('4')
    await expect(page.getByTestId('synonym-count-3plus')).toContainText('1')
    expect(posts).toHaveLength(2)
    expect(posts.map((p) => p.selections[0].right_product_id)).toEqual(['lidl', 'plus'])
  })
}

test('Synoniemenanalyse is beschermd tegen reguliere gebruikers', async ({ page }) => {
  let reads = 0
  await page.route('**/api/**', async (route) => {
    const path = new URL(route.request().url()).pathname
    if (path.endsWith('/article-synonyms/analysis')) reads++
    if (path === '/api/session') return route.fulfill({ json: {
      user_id: 'regular', active_household_id: 'h', context_type: 'regular',
      role: 'admin', permissions: {},
    } })
    if (path === '/api/onboarding') return route.fulfill({ json: { onboarding_status: 'completed' } })
    return route.fulfill({ json: {} })
  })
  await page.goto('/catalogus/synoniemenanalyse')
  await expect(page).toHaveURL(/\/home$/)
  expect(reads).toBe(0)
})
