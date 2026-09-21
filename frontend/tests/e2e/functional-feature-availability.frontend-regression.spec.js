import { expect, test } from '@playwright/test'

const functionalPermission = 'platform.functional_features.manage'
const technicalPermission = 'platform.feature_flags.manage'
const key = 'feature.gerechten'

async function mockApi(page, actor, state) {
  const permissions = actor === 'superuser' ? { [functionalPermission]: true, 'platform.system_household.access': true }
    : actor === 'technical' ? { [technicalPermission]: true } : {}
  const system = actor === 'superuser'
  await page.route('**/api/**', async (route) => {
    const path = new URL(route.request().url()).pathname
    const json = (payload, status = 200) => route.fulfill({ status, json: payload })
    if (path === '/api/session') return json({
      user: { id: actor, email: `${actor}@example.test` }, user_id: actor,
      email: `${actor}@example.test`, permissions, supported_permissions: Object.keys(permissions),
      context_type: system ? 'system' : actor === 'technical' ? 'none' : 'regular',
      active_household_id: system ? '0' : actor === 'technical' ? null : 'test-household',
      role: system ? 'owner' : actor === 'technical' ? null : 'member',
      is_platform_superuser: system, is_frontteam: false,
    })
    if (path === '/api/onboarding') return json({ onboarding_status: 'completed', primary_use_case: null })
    if (path === '/api/features') {
      state.reads++
      return state.failed ? json({}, 503) : json({ features: { [key]: state.enabled } })
    }
    if (path.startsWith('/api/platform/functional-features')) {
      state.managementReads++
      if (actor !== 'superuser') return json({}, 403)
      const item = () => ({ key, label: 'Gerechten', enabled: state.enabled, default_enabled: false })
      if (route.request().method() === 'PUT') {
        state.updates.push(route.request().postDataJSON())
        state.enabled = route.request().postDataJSON().enabled
        return json({ item: item() })
      }
      return json({ items: [item()] })
    }
    return json({}, 404) // Never forward a test request to a real backend.
  })
}

for (const actor of ['member', 'superuser']) {
  test(`${actor}: default OFF, ON, refresh OFF and failure; other actions unchanged`, async ({ page }) => {
    const state = { enabled: false, reads: 0, managementReads: 0, updates: [] }
    await mockApi(page, actor, state)
    await page.goto('/home')
    await expect(page.getByTestId('legacy-home-navigation')).toBeVisible()
    await expect.poll(() => state.reads).toBeGreaterThan(0)
    await expect(page.getByTestId('home-tile-recepten')).toHaveCount(0)
    const otherTiles = await page.locator('[data-testid^="home-tile-"]').evaluateAll((nodes) => nodes.map((n) => n.dataset.testid))
    state.enabled = true
    await page.evaluate(() => window.dispatchEvent(new Event('focus')))
    await expect(page.getByTestId('home-tile-recepten')).toContainText('Gerechten')
    state.enabled = false
    await page.evaluate(() => window.dispatchEvent(new Event('focus')))
    await expect(page.getByTestId('legacy-home-navigation')).toBeVisible()
    await expect(page.getByTestId('home-tile-recepten')).toHaveCount(0)
    expect(await page.locator('[data-testid^="home-tile-"]').evaluateAll((nodes) => nodes.map((n) => n.dataset.testid))).toEqual(otherTiles)
    state.enabled = true
    await page.evaluate(() => window.dispatchEvent(new Event('focus')))
    await expect(page.getByTestId('home-tile-recepten')).toBeVisible()
    state.failed = true
    await page.evaluate(() => window.dispatchEvent(new Event('focus')))
    await expect(page.getByTestId('legacy-home-navigation')).toBeVisible()
    await expect(page.getByTestId('home-tile-recepten')).toHaveCount(0)
  })
}

test('Superuser opens functional management and enables Gerechten after confirmation', async ({ page }) => {
  const state = { enabled: false, reads: 0, managementReads: 0, updates: [] }
  await mockApi(page, 'superuser', state)
  await page.goto('/home')
  await page.getByRole('button', { name: 'Functionaliteiten', exact: true }).click()
  await expect(page).toHaveURL(/\/platform\/functionaliteiten$/)
  const feature = page.getByTestId(`platform-feature-flag-${key}`)
  await expect(feature).toContainText(key)
  await expect(feature).toContainText('Uitgeschakeld')
  await feature.getByRole('button', { name: 'Inschakelen', exact: true }).click()
  expect(state.updates).toEqual([])
  await page.getByRole('button', { name: 'Definitief bevestigen' }).click()
  await expect(feature).toContainText('Ingeschakeld')
  expect(state.updates).toEqual([{ enabled: true }])
  await page.goto('/home')
  await expect(page.getByTestId('home-tile-recepten')).toBeVisible()
})

for (const actor of ['member', 'technical']) {
  test(`${actor} cannot open functional management directly`, async ({ page }) => {
    const state = { enabled: false, reads: 0, managementReads: 0, updates: [] }
    await mockApi(page, actor, state)
    await page.goto('/platform/functionaliteiten')
    await expect(page).toHaveURL(/\/home$/)
    await expect(page.getByRole('button', { name: 'Functionaliteiten', exact: true })).toHaveCount(0)
    expect(state.managementReads).toBe(0)
  })
}
