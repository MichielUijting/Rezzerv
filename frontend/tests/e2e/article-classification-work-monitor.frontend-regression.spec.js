import { test, expect } from '@playwright/test'

test.use({ storageState: { cookies: [], origins: [] } })

for (const width of [390, 1280]) {
  test(`Artikelbeheer laadt uitsluitend gekozen werkgebied en toont synoniemen direct op ${width}px`, async ({ page }) => {
    await page.setViewportSize({ width, height: 900 })
    const writes = []
    const requests = []
    await page.route('**/api/**', async (route) => {
      const url = new URL(route.request().url())
      const path = url.pathname
      requests.push(path)
      if (!['GET', 'HEAD'].includes(route.request().method())) writes.push(path)
      if (path === '/api/session') return route.fulfill({ json: {
        user_id: 'workqueue-user', active_household_id: '0', context_type: 'system',
        role: 'owner', is_platform_superuser: true, permissions: { 'gpc.update': true },
      } })
      if (path === '/api/maintenance/status') return route.fulfill({ json: { state: 'normal' } })
      if (path === '/api/external-databases/articles-overview') return route.fulfill({ json: {
        items: [], counts: { unlinked: 3, classification_pending: 2, linked: 7 },
      } })
      if (path === '/api/catalog') return route.fulfill({ json: { items: [
        { id: 'p1', name: 'Testmelk', brand: 'Voorbeeld', primary_gtin: '8712345678901' },
      ] } })
      if (path === '/api/catalog/p1/gpc-brick') return route.fulfill({ json: {
        assignment: { brick_code: '10000001', brick_description: 'Melk' }, suggestions: [],
      } })
      if (path === '/api/cbs-classifications/workqueue') return route.fulfill({ json: {
        total: 1, task_count_scope: 'page', items: [{
          id: 'p1', name: 'Testmelk', brand: 'Voorbeeld', gtin: '8712345678901',
          gpc_code: '10000001', gpc_status: 'classified',
          cbs_code: '', cbs_name: '', cbs_status: 'unclassified', cbs_version: 0,
        }], tasks: [{ key: 'p1:cbs', global_product_id: 'p1', system: 'cbs', status: 'open' }],
      } })
      if (path === '/api/cbs-classifications/products') return route.fulfill({ json: {
        total: 1, items: [{ id: 'p1', name: 'Testmelk', classified: false, version: 0 }],
      } })
      if (path === '/api/external-databases/article-synonyms/analysis') return route.fulfill({ json: {
        summary: { candidate_pairs: 0 }, items: [
          { id: 'p1', name: 'Testmelk', primary_gtin: '8712345678901', synonym_count: 0 },
        ],
      } })
      return route.fulfill({ json: {} })
    })
    await page.goto('/externe-databases-2')
    await expect(page.getByRole('heading', { name: 'Artikelbeheer' }).first()).toBeVisible()
    const nav = page.getByTestId('classification-work-monitor')
    for (const name of ['Identificeren', 'Classificeren', 'Synoniemen']) {
      await expect(nav.getByRole('button', { name })).toBeVisible()
    }
    await expect(nav.getByRole('button', { name: 'Synchroniseren' })).toHaveCount(0)
    await expect(page.getByTestId('external-databases-2-table')).toHaveCount(0)
    expect(requests).not.toContain('/api/external-databases/articles-overview')
    expect(requests).not.toContain('/api/cbs-classifications/products')
    expect(requests).not.toContain('/api/external-databases/article-synonyms/analysis')

    await nav.getByRole('button', { name: 'Classificeren' }).click()
    await expect(page.getByTestId('combined-classification-workspace')).toBeVisible()
    await expect(page.getByTestId('combined-classification-articles')).toContainText('Testmelk')
    await expect(page.getByTestId('combined-selected-article')).toHaveCount(0)
    await page.getByTestId('combined-classification-articles').getByRole('row', { name: /Testmelk/ }).click()
    await expect(page.getByTestId('combined-selected-article')).toContainText('Testmelk')
    await expect(page.getByTestId('classification-dual-panels')).toBeVisible()
    await expect(page.getByTestId('classification-gs1-panel')).toContainText('GS1 GPC')
    await expect(page.getByTestId('classification-cbs-panel')).toContainText('CBS ECOICOPv2')
    await expect(page.getByTestId('classification-gs1-panel')).toContainText('10000001')
    await expect(page.getByTestId('cbs-single-product')).toContainText('Niet geclassificeerd')
    await expect(page.getByTestId('classification-cbs-panel')).toContainText('CBS-categorie zoeken of doorbladeren')
    const selectedRow = page.getByTestId('combined-classification-articles').getByRole('row', { name: /Testmelk/ })
    await expect(selectedRow).toHaveAttribute('aria-selected', 'true')
    await expect(selectedRow.locator('td').first()).toHaveCSS('background-color', 'rgb(215, 242, 223)')
    await page.getByTestId('classification-gs1-panel').getByRole('button', { name: 'Andere Brick kiezen' }).click()
    await expect(page.getByRole('dialog', { name: 'GS1 GPC Brick kiezen' })).toBeVisible()
    await page.getByRole('dialog', { name: 'GS1 GPC Brick kiezen' }).getByRole('button', { name: 'Sluiten' }).click()
    await page.getByTestId('classification-cbs-panel').getByRole('button', { name: 'CBS-categorie zoeken of doorbladeren' }).click()
    await expect(page.getByRole('dialog', { name: 'CBS ECOICOPv2-categorie kiezen' })).toBeVisible()
    await page.getByRole('dialog', { name: 'CBS ECOICOPv2-categorie kiezen' }).getByRole('button', { name: 'Sluiten' }).click()
    await expect(page.getByTestId('classification-gs1-panel')).toContainText('Andere Brick kiezen')
    const panelPositions = await page.getByTestId('classification-dual-panels').evaluate((element) => {
      const parts = Array.from(element.children).map((child) => child.getBoundingClientRect())
      return parts.map(({ x, y }) => ({ x, y }))
    })
    if (width > 720) {
      expect(panelPositions[0].y).toBeCloseTo(panelPositions[1].y, 0)
      expect(panelPositions[0].x).toBeLessThan(panelPositions[1].x)
    } else {
      expect(panelPositions[0].y).toBeLessThan(panelPositions[1].y)
    }
    await expect(page.getByTestId('combined-classification-articles')).toContainText('10000001')
    await expect(page.getByTestId('external-databases-2-table')).toHaveCount(0)

    await nav.getByRole('button', { name: 'Synoniemen' }).click()
    await expect(page.getByTestId('article-synonyms-articles')).toBeVisible()
    await expect(page.getByTestId('article-synonyms-table')).toBeVisible()
    await expect(page.getByRole('button', { name: 'Artikel-synoniemen openen' })).toHaveCount(0)
    await expect(page.getByTestId('external-databases-2-table')).toHaveCount(0)

    await nav.getByRole('button', { name: 'Identificeren' }).click()
    await expect(page.getByTestId('external-databases-2-table')).toBeVisible()
    await expect(page.getByRole('button', { name: 'Niet gekoppeld: 3' })).toBeVisible()
    expect(requests).toContain('/api/external-databases/articles-overview')
    expect(writes).toEqual([])
  })
}
