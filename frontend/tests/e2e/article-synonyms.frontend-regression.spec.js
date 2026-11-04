import { test, expect } from '@playwright/test'

test.use({ storageState: { cookies: [], origins: [] } })

for (const width of [390, 1280]) {
  test(`Artikel-synoniemen: uitgelijnde tabellen, checkboxen en ontkoppelen op ${width}px`, async ({ page }) => {
    await page.setViewportSize({ width, height: 900 })
    const posts = []
    const articles = [
      { id: 'a', name: 'Aardappelen', primary_gtin: '08719587325926' },
      { id: 'b', name: 'Aardappelen', primary_gtin: '08718452513666' },
      { id: 'c', name: 'Kruimige aardappelen', primary_gtin: '08712345678906' },
      { id: 'd', name: 'Snijbonen', primary_gtin: '08712345678913' },
    ]
    const options = [
      { id: 'c', name: 'Kruimige aardappelen', primary_gtin: '08712345678906',
        status: 'linked', status_label: 'Al gekoppeld', linkable: false,
        fingerprint: 'c'.repeat(64), reason: 'Al gekoppeld', manual: true },
      { id: 'b', name: 'Aardappelen', primary_gtin: '08718452513666',
        status: 'suggested', status_label: 'Voorstel', linkable: true,
        fingerprint: 'b'.repeat(64), manual: false },
      { id: 'd', name: 'Snijbonen', primary_gtin: '08712345678913',
        status: 'other', status_label: 'Overig', linkable: true,
        fingerprint: 'd'.repeat(64), manual: true },
    ]
    await page.route('**/api/**', async (route) => {
      const path = new URL(route.request().url()).pathname
      if (path === '/api/session') return route.fulfill({ json: {
        user_id: 'synonym-test', active_household_id: '0', context_type: 'system',
        is_platform_superuser: true, role: 'admin',
        permissions: { 'platform.external_products.view': true,
          'platform.external_products.link_existing': true },
      } })
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
          unlinked: action === 'unlink' ? payload.selections.length : 0 } })
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
      await expect(table.locator('thead tr').first().locator('th')).toHaveCount(4)
      await expect(table.locator('thead')).toContainText('Foto')
      await expect(table.locator('thead')).toContainText('Artikelnaam')
      await expect(table.locator('thead')).toContainText('Barcode')
      await expect(table.locator('thead')).not.toContainText('Winkel')
    }
    const leftCheck = left.locator('tbody tr').first().getByRole('checkbox')
    await leftCheck.check()
    await expect(leftCheck).toBeChecked()
    await expect(right.locator('tbody tr')).toHaveCount(3)
    await expect(right.locator('tbody tr').first()).toHaveClass(/rz-synonym-relation-linked/)
    await expect(right.locator('tbody tr').nth(1)).toHaveClass(/rz-synonym-relation-suggested/)
    await expect(right.locator('tbody tr').nth(2)).toHaveClass(/rz-synonym-relation-other/)
    await expect(right).not.toContainText('08719587325926')
    await expect(right.getByRole('checkbox')).toHaveCount(3)
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
    await right.locator('tbody tr').nth(1).getByRole('checkbox').check()
    await expect(page.getByRole('button', { name: 'Koppelen', exact: true })).toBeEnabled()
    await expect(page.getByRole('button', { name: 'Ontkoppelen' })).toBeDisabled()
    await page.getByRole('button', { name: 'Koppelen', exact: true }).click()
    expect(posts[1].action).toBe('link')
    expect(posts[1].payload.selections).toEqual([{
      left_product_id: 'a', right_product_id: 'b', fingerprint: 'b'.repeat(64), manual: false,
    }])
  })
}

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
