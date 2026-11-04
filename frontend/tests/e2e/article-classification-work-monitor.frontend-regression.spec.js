import { test, expect } from '@playwright/test'

test.use({ storageState: { cookies: [], origins: [] } })

test('superuser ziet afzonderlijke OFF-, GS1-, CBS- en synoniemwachtrijen zonder schrijfactie', async ({ page }) => {
  const writes = []
  let refreshes = 0
  await page.route('**/api/**', async (route) => {
    const url = new URL(route.request().url())
    const path = url.pathname
    if (route.request().method() !== 'GET') writes.push({ path, method: route.request().method() })
    if (path === '/api/session') return route.fulfill({ json: {
      user_id: 'workqueue-user', active_household_id: '0', context_type: 'system',
      role: 'owner', is_platform_superuser: true, permissions: {},
    } })
    if (path === '/api/maintenance/status') return route.fulfill({ json: { state: 'normal' } })
    if (path === '/api/onboarding') return route.fulfill({ json: { onboarding_status: 'completed' } })
    if (path === '/api/features') return route.fulfill({ json: { features: {} } })
    if (path === '/api/action-buttons') return route.fulfill({ json: { items: [] } })
    if (path === '/api/external-databases/articles-overview') return route.fulfill({ json: {
      items: [], counts: { unlinked: 3, classification_pending: 2, linked: 7 },
    } })
    if (path === '/api/cbs-classifications/products') {
      refreshes += 1
      const offset = Number(url.searchParams.get('offset') || 0)
      const items = offset === 0 ? [
        { id: 'a', classified: false }, { id: 'b', classified: true },
      ] : []
      return route.fulfill({ json: { total: 2, items } })
    }
    if (path === '/api/external-databases/article-synonyms/analysis') {
      return route.fulfill({ json: { summary: { candidate_pairs: 4 }, items: [] } })
    }
    return route.fulfill({ json: {} })
  })
  await page.goto('/externe-databases-2')
  await expect(page.getByRole('heading', { name: 'Artikel classificeren' }).first()).toBeVisible()
  const monitor = page.getByTestId('classification-work-monitor')
  await expect(monitor).toContainText('Nog niet gekoppeld (OFF)')
  await expect(monitor).toContainText('GS1-classificatie ontbreekt')
  await expect(monitor).toContainText('CBS-classificaties ontbreken')
  await expect(monitor).toContainText('Voorgestelde synoniemparen')
  await expect(monitor).toContainText('3')
  await expect(monitor).toContainText('2')
  await expect(monitor).toContainText('1')
  await expect(monitor).toContainText('4')
  await expect(page.getByTestId('classification-sync-evidence')).toContainText('nog niet beschikbaar')
  expect(writes).toHaveLength(0)
  await monitor.getByRole('button', { name: 'Werkvoorraad vernieuwen' }).click()
  await expect.poll(() => refreshes).toBe(2)
  expect(writes).toHaveLength(0)
})

test('ontbrekende CBS- en synoniembron is onbekend, geen nul', async ({ page }) => {
  await page.route('**/api/**', async (route) => {
    const path = new URL(route.request().url()).pathname
    if (path === '/api/session') return route.fulfill({ json: {
      user_id: 'workqueue-user', active_household_id: '0', context_type: 'system',
      role: 'owner', is_platform_superuser: true, permissions: {},
    } })
    if (path === '/api/maintenance/status') return route.fulfill({ json: { state: 'normal' } })
    if (path === '/api/external-databases/articles-overview') return route.fulfill({ json: {
      items: [], counts: { unlinked: 0, classification_pending: 0, linked: 0 },
    } })
    if (path === '/api/cbs-classifications/products' || path === '/api/external-databases/article-synonyms/analysis') {
      return route.fulfill({ status: 503, json: { detail: 'Tijdelijk niet beschikbaar' } })
    }
    return route.fulfill({ json: {} })
  })
  await page.goto('/externe-databases-2')
  const monitor = page.getByTestId('classification-work-monitor')
  await expect(monitor.getByRole('alert')).toContainText('kon niet worden gemeten')
  await expect(monitor.getByText('—')).toHaveCount(2)
  await expect(page.getByTestId('classification-sync-evidence')).toContainText('nog niet beschikbaar')
})
