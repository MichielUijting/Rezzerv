import { expect, test } from '@playwright/test'

const FEATURE_FLAGS_PERMISSION = 'platform.feature_flags.manage'
const FLAGS_ENDPOINT = '**/api/platform/feature-flags'
const FLAG_UPDATE_ENDPOINT = '**/api/platform/feature-flags/external_product_search'

const noneSession = {
  user: { id: 'platform-feature-flags-user', email: 'platform-feature-flags@example.test' },
  user_id: 'platform-feature-flags-user',
  email: 'platform-feature-flags@example.test',
  context_type: 'none',
  active_household_id: null,
  active_household_name: '',
  role: null,
  display_role: null,
  permissions: { [FEATURE_FLAGS_PERMISSION]: true },
  supported_permissions: [FEATURE_FLAGS_PERMISSION],
  is_platform_superuser: false,
  is_frontteam: false,
}

const defaultFlag = {
  key: 'external_product_search',
  label: 'Externe productzoekfunctie',
  description: 'Schakelt platformbreed de externe productzoekroutes die onder platform.external_products.search vallen.',
  enabled: true,
  default_enabled: true,
  source: 'default',
  updated_by: null,
  updated_at: null,
}

async function mockSession(page, session) {
  await page.route('**/api/session', async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify(session),
    })
  })
}

test('feature flags page is read-only until explicit second confirmation and sends no household authority', async ({ page }) => {
  await mockSession(page, noneSession)
  const reads = []
  const updates = []

  await page.route(FLAGS_ENDPOINT, async (route) => {
    const request = route.request()
    reads.push({ method: request.method(), url: request.url(), headers: request.headers(), postData: request.postData() })
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        items: [defaultFlag],
        count: 1,
        household_context_used: false,
        context_type: 'none',
      }),
    })
  })

  await page.route(FLAG_UPDATE_ENDPOINT, async (route) => {
    const request = route.request()
    updates.push({ method: request.method(), url: request.url(), headers: request.headers(), postData: request.postData() })
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        item: {
          ...defaultFlag,
          enabled: false,
          source: 'override',
          updated_by: 'platform-feature-flags-user',
          updated_at: '2026-08-24T16:00:00Z',
        },
        household_context_used: false,
        context_type: 'none',
      }),
    })
  })

  await page.goto('/home')
  await expect(page.getByTestId('platform-home-tile-feature-flags')).toBeVisible()
  await expect(page.locator('[data-testid^="platform-home-tile-"]')).toHaveCount(1)

  await page.goto('/platform/featureflags')
  await expect(page.getByTestId('platform-feature-flags-page')).toBeVisible()
  await expect(page.getByText('Er is geen actief huishouden en deze pagina valt nooit terug op huishouden 0.')).toBeVisible()
  const flag = page.getByTestId('platform-feature-flag-external_product_search')
  await expect(flag).toContainText('Externe productzoekfunctie')
  await expect(flag).toContainText('Status: Ingeschakeld')

  expect(reads).toHaveLength(1)
  expect(reads[0].method).toBe('GET')
  expect(reads[0].postData).toBeNull()
  expect(reads[0].url).not.toContain('household')
  expect(reads[0].headers.authorization).toBeUndefined()
  expect(reads[0].headers['x-admin-key']).toBeUndefined()
  expect(updates).toHaveLength(0)

  await flag.getByRole('button', { name: 'Uitschakelen', exact: true }).click()
  await expect(page.getByTestId('platform-feature-flag-confirmation')).toBeVisible()
  expect(updates).toHaveLength(0)

  await page.getByRole('button', { name: 'Annuleren', exact: true }).click()
  await expect(page.getByTestId('platform-feature-flag-confirmation')).toHaveCount(0)
  expect(updates).toHaveLength(0)

  await flag.getByRole('button', { name: 'Uitschakelen', exact: true }).click()
  await page.getByRole('button', { name: 'Definitief bevestigen', exact: true }).click()
  await expect.poll(() => updates.length).toBe(1)

  expect(updates[0].method).toBe('PUT')
  expect(JSON.parse(updates[0].postData)).toEqual({ enabled: false })
  expect(updates[0].url).not.toContain('household')
  expect(updates[0].headers.authorization).toBeUndefined()
  expect(updates[0].headers['x-admin-key']).toBeUndefined()
  await expect(flag).toContainText('Status: Uitgeschakeld')
  await expect(flag).toContainText('Bron: opgeslagen platforminstelling')
})

test('feature flags direct route stays closed without permission and performs no flag request', async ({ page }) => {
  const auditOnlySession = {
    ...noneSession,
    permissions: { 'platform.audit.view': true },
    supported_permissions: ['platform.audit.view'],
  }
  await mockSession(page, auditOnlySession)
  let flagReads = 0
  let flagUpdates = 0

  await page.route(FLAGS_ENDPOINT, async (route) => {
    flagReads += 1
    await route.fulfill({ status: 200, contentType: 'application/json', body: '{"items":[]}' })
  })
  await page.route(FLAG_UPDATE_ENDPOINT, async (route) => {
    flagUpdates += 1
    await route.fulfill({ status: 200, contentType: 'application/json', body: '{}' })
  })

  await page.goto('/platform/featureflags')
  await expect(page).toHaveURL(/\/home$/)
  await expect(page.getByTestId('none-session-home')).toBeVisible()
  expect(flagReads).toBe(0)
  expect(flagUpdates).toBe(0)
})
