import { test, expect } from '@playwright/test'

test.use({ storageState: { cookies: [], origins: [] } })

for (const width of [390, 1280]) {
  test(`Artikelbeheer heeft vier werkgebieden zonder dubbele werkvoorraadtellers op ${width}px`, async ({ page }) => {
    await page.setViewportSize({ width, height: 900 })
    const writes = []
    const requests = []
    await page.route('**/api/**', async (route) => {
      const path = new URL(route.request().url()).pathname
      requests.push(path)
      if (!['GET', 'HEAD'].includes(route.request().method())) writes.push(path)
      if (path === '/api/session') return route.fulfill({ json: {
        user_id: 'workqueue-user', active_household_id: '0', context_type: 'system',
        role: 'owner', is_platform_superuser: true, permissions: {},
      } })
      if (path === '/api/maintenance/status') return route.fulfill({ json: { state: 'normal' } })
      if (path === '/api/external-databases/articles-overview') return route.fulfill({ json: {
        items: [], counts: { unlinked: 3, classification_pending: 2, linked: 7 },
      } })
      return route.fulfill({ json: {} })
    })

    await page.goto('/externe-databases-2')
    await expect(page.getByRole('heading', { name: 'Artikelbeheer' }).first()).toBeVisible()
    const areas = page.getByTestId('classification-work-monitor')
    for (const name of ['Identificeren', 'Classificeren', 'Synoniemen', 'Synchroniseren']) {
      await expect(areas.getByRole('button', { name, exact: true })).toBeVisible()
    }
    await expect(page.getByRole('button', { name: 'Niet gekoppeld: 3' })).toBeVisible()
    await expect(page.getByRole('button', { name: 'Classificatie ontbreekt: 2' })).toBeVisible()

    await areas.getByRole('button', { name: 'Classificeren', exact: true }).click()
    await expect(page.getByTestId('classification-work-area')).toContainText('GS1 GPC')
    await expect(page.getByTestId('classification-work-area')).toContainText('CBS ECOICOPv2')
    await expect(page.getByTestId('external-databases-2-table')).toHaveCount(0)

    await areas.getByRole('button', { name: 'Synoniemen', exact: true }).click()
    await expect(page.getByTestId('synonym-work-area')).toContainText('Artikel-synoniemen openen')
    await areas.getByRole('button', { name: 'Synchroniseren', exact: true }).click()
    await expect(page.getByTestId('classification-sync-evidence')).toContainText('geen gevalideerde synchronisatiewerkvoorraad')
    await expect(page.getByTestId('external-databases-2-table')).toHaveCount(0)

    await areas.getByRole('button', { name: 'Identificeren', exact: true }).click()
    await expect(page.getByTestId('external-databases-2-table')).toBeVisible()
    expect(writes).toEqual([])
    expect(requests).not.toContain('/api/cbs-classifications/products')
    expect(requests).not.toContain('/api/external-databases/article-synonyms/analysis')
  })
}
