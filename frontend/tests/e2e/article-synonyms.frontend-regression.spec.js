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
  test('Synoniemenanalyse: winkelmatrix en artikelbeoordeling op ' + width + 'px', async ({ page }) => {
    await page.setViewportSize({ width, height: 900 })
    let writes = 0
    const products = [
      { id: 'ah', name: 'Halfvolle melk AH', store: 'Albert Heijn',
        group_key: 'shopify:Melk', group_label: 'Melk', brand: 'AH', variant: '',
        image_url: '', linked_stores: ['Jumbo'],
        pending: [{ id: 'lid', name: 'Halfvolle melk Lidl', store_name: 'Lidl', score: .91 }], status: 'review' },
      { id: 'jumbo', name: 'Halfvolle melk Jumbo', store: 'Jumbo',
        group_key: 'shopify:Melk', group_label: 'Melk', brand: 'Jumbo', variant: '',
        image_url: '', linked_stores: ['Albert Heijn'], pending: [], status: 'linked' },
    ]
    await page.route('**/api/**', async (route) => {
      const path = new URL(route.request().url()).pathname
      if (path.endsWith('/article-synonyms/link') && route.request().method() !== 'GET') writes++
      if (path === '/api/session') return route.fulfill({ json: {
        user_id: 'synonym-test', active_household_id: '0', context_type: 'system', role: 'admin',
        is_platform_superuser: true, permissions: { 'platform.external_products.view': true },
      } })
      if (path.endsWith('/article-synonyms/analysis')) return route.fulfill({ json: {
        summary: { confirmed_pairs: 1, candidate_pairs: 1, no_candidate_articles: 0, insufficient_articles: 0, eligible_articles: 2, classified_articles: 2 },
        groups: [
          { id: 'shopify:Melk|Albert Heijn', group_key: 'shopify:Melk', group_label: 'Melk', store: 'Albert Heijn', articles: 1, linked: 1, review: 1 },
          { id: 'shopify:Melk|Jumbo', group_key: 'shopify:Melk', group_label: 'Melk', store: 'Jumbo', articles: 1, linked: 1, review: 0 },
        ],
        items: products,
      } })
      if (path.endsWith('/article-synonyms')) return route.fulfill({ json: { items: [{
        id: 'proposal-ah-lidl', score: .91, fingerprint: 'a'.repeat(64),
        left: { id: 'ah', name: 'Halfvolle melk AH', store_name: 'Albert Heijn', image_url: '' },
        right: { id: 'lid', name: 'Halfvolle melk Lidl', store_name: 'Lidl', image_url: '' },
      }] } })
      if (path === '/api/onboarding') return route.fulfill({ json: { onboarding_status: 'completed' } })
      if (path === '/api/features') return route.fulfill({ json: { features: {} } })
      if (path === '/api/action-buttons') return route.fulfill({ json: { items: [] } })
      return route.fulfill({ json: {} })
    })
    await page.goto('/catalogus/synoniemenanalyse')
    await expect(page.getByTestId('synonym-analysis-groups')).toContainText('Albert Heijn')
    await expect(page.getByTestId('synonym-analysis-page')).toContainText('Open kandidaatparen')
    await expect(page.getByTestId('synonym-analysis-page')).toContainText('tekstovereenkomst')
    await page.getByTestId('synonym-analysis-groups').getByRole('button', { name: 'Artikelen' }).first().click()
    await expect(page.getByTestId('synonym-analysis-items')).toContainText('Halfvolle melk AH')
    await page.getByTestId('synonym-analysis-items').getByRole('button', { name: 'Beoordelen' }).click()
    await expect(page).toHaveURL(/\/artikelsynoniemen\?artikel=ah$/)
    await expect(page.getByTestId('article-synonyms-table').locator('tbody tr')).toHaveCount(1)
    expect(writes).toBe(0)
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
