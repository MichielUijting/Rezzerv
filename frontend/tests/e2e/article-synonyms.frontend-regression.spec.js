import { test, expect } from '@playwright/test'

test.use({ storageState: { cookies: [], origins: [] } })
for (const width of [390, 1280]) {
  for (const role of ['superuser', 'frontteam']) {
    test(`${role}: bulk koppelen op ${width}px`, async ({ page }) => {
      await page.setViewportSize({ width, height: 900 })
      const writes = []
      const pairs = Array.from({ length: 12 }, (_, i) => ({
        id: `pair-${i}`, score: .95-i/100, fingerprint: 'a'.repeat(64),
        left: { id: `left-${i}`, name: `AH Melk ${i}`, store_name: 'Albert Heijn', primary_gtin: '08719587325926',
          image_url: i === 0 ? 'data:image/gif;base64,R0lGODlhAQABAAD/ACwAAAAAAQABAAACAUwAOw==' : '', size_value: '1', size_unit: 'l' },
        right: { id: `right-${i}`, name: `Jumbo Melk ${i}`, store_name: 'Jumbo', primary_gtin: '08718452513666',
          image_url: '', size_value: '2', size_unit: 'l' },
      }))
      const linked = new Set()
      let failed = false
      await page.route('**/api/**', async (route) => {
        const path = new URL(route.request().url()).pathname
        if (path === '/api/session') return route.fulfill({ json: {
          user_id: 'synonym-test', active_household_id: role === 'superuser' ? '0' : 'test-household',
          context_type: role === 'superuser' ? 'system' : 'regular', role: 'admin',
          is_platform_superuser: role === 'superuser', is_frontteam: role === 'frontteam',
          permissions: { 'platform.external_products.view': true, 'platform.external_products.link_existing': true },
        } })
        if (path.endsWith('/article-synonyms/link')) {
          writes.push(route.request().postDataJSON())
          if (!failed) { failed = true; return route.fulfill({ status: 409, json: { detail: 'Een suggestie is gewijzigd. Vernieuw de lijst.' } }) }
          for (const item of writes.at(-1).selections) linked.add(item.left_product_id)
          return route.fulfill({ json: { linked: writes.at(-1).selections.length } })
        }
        if (path.endsWith('/article-synonyms')) return route.fulfill({ json: { items: pairs.filter((p) => !linked.has(p.left.id)) } })
        if (path === '/api/onboarding') return route.fulfill({ json: { onboarding_status: 'completed' } })
        if (path === '/api/features') return route.fulfill({ json: { features: {} } })
        if (path === '/api/action-buttons') return route.fulfill({ json: { items: [] } })
        return route.fulfill({ json: {} })
      })
      await page.goto('/artikelsynoniemen')
      const table = page.getByTestId('article-synonyms-table')
      await expect(table.locator('tbody tr')).toHaveCount(10)
      await expect(page.getByRole('heading', { name: 'Artikel-synoniemen', level: 2, exact: true })).toBeVisible()
      await expect(table.locator('thead tr').first().locator('th')).toHaveCount(7)
      await expect(table.locator('thead tr').first().locator('th').first()).toHaveText('')
      await expect(table.locator('colgroup col').first()).toHaveAttribute('style', /48px/)
      await expect(table.locator('thead tr').first()).toContainText('Artikelnaam')
      await expect(table.locator('thead tr').first()).toContainText('Foto artikel')
      await expect(table.locator('tbody tr').first()).toContainText('Albert Heijn')
      await expect(table.locator('tbody tr').first()).toContainText('Jumbo')
      await expect(table.locator('tbody tr').first().locator('img')).toHaveCount(1)
      await expect(page.getByRole('button', { name: 'Vernieuwen' })).toHaveCount(0)
      await expect(page.getByRole('button', { name: 'Koppelen', exact: true })).toBeDisabled()
      await table.getByRole('checkbox').nth(0).check()
      await table.getByRole('checkbox').nth(1).check()
      await page.getByRole('navigation', { name: 'Paginering' }).getByRole('button', { name: '+', exact: true }).click()
      await expect(table.locator('tbody tr')).toHaveCount(2)
      await table.getByRole('checkbox').first().check()
      await page.getByRole('textbox', { name: 'Filter op artikelnaam eerste winkel', exact: true }).fill('AH Melk 0')
      await expect(table.locator('tbody tr')).toHaveCount(1)
      expect(writes).toEqual([])
      await page.getByRole('button', { name: 'Koppelen', exact: true }).click()
      await expect(page.getByRole('alert')).toContainText('Een suggestie is gewijzigd')
      await expect(page.getByText('3 geselecteerd', { exact: true })).toBeVisible()
      await page.getByRole('button', { name: 'Koppelen', exact: true }).click()
      await expect(page.getByText('0 geselecteerd', { exact: true })).toBeVisible()
      expect(writes[1].selections.map((item) => item.left_product_id)).toEqual(['left-0', 'left-1', 'left-10'])
      await page.getByRole('textbox', { name: 'Filter op artikelnaam eerste winkel', exact: true }).fill('')
      await expect(table.locator('tbody tr')).toHaveCount(9)
      await expect(table).not.toContainText('AH Melk 0')
      await page.reload()
      await expect(table.locator('tbody tr')).toHaveCount(9)
      await expect(page.getByRole('link', { name: 'Externe databases 2', exact: true })).toBeVisible()
      if (width <= 720) await expect(page.getByRole('button', { name: 'Terug', exact: true }).first()).toBeVisible()
    })
  }
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
