import { expect, test } from '@playwright/test'

const TEST_FIXTURE_PERMISSION = 'platform.test_fixtures.manage'

const noneSession = {
  user: { id: 'platform-fixtures-user', email: 'platform-fixtures@example.test' },
  user_id: 'platform-fixtures-user',
  email: 'platform-fixtures@example.test',
  context_type: 'none',
  active_household_id: null,
  active_household_name: '',
  role: null,
  display_role: null,
  permissions: { [TEST_FIXTURE_PERMISSION]: true },
  supported_permissions: [TEST_FIXTURE_PERMISSION],
  is_platform_superuser: false,
  is_frontteam: false,
}

async function mockSession(page, session) {
  await page.route('**/api/session', async (route) => {
    await route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(session) })
  })
}

const fixtureActions = [
  {
    key: 'browser-reset',
    title: 'Browserregressiefixture opnieuw opbouwen',
    confirm: 'Browserfixture opnieuw opbouwen',
    endpoint: '**/api/testing/fixtures/browser-regression/reset',
  },
  {
    key: 'inventory-ensure',
    title: 'Regressievoorraad garanderen',
    confirm: 'Regressievoorraad garanderen',
    endpoint: '**/api/testing/fixtures/inventory/ensure',
  },
  {
    key: 'receipt-layer1',
    title: 'Receipt layer-1 fixture genereren',
    confirm: 'Layer-1 fixture genereren',
    endpoint: '**/api/testing/fixtures/receipt-layer1/generate',
  },
  {
    key: 'seed-kassa',
    title: 'Kassa-regressiebonnen seeden',
    confirm: 'Kassa-fixtures seeden',
    endpoint: '**/api/testing/fixtures/receipts/seed-kassa',
  },
  {
    key: 'receipt-export',
    title: 'Receipt-exportfixture genereren',
    confirm: 'Exportfixture genereren',
    endpoint: '**/api/testing/fixtures/receipt-export/generate',
  },
  {
    key: 'cleanup',
    title: 'Regressiefixturedata opruimen',
    confirm: 'Fixturedata definitief opruimen',
    endpoint: '**/api/testing/fixtures/cleanup',
  },
]

test('test fixtures page requires confirmation and invokes only fixed canonical fixture mutations', async ({ page }) => {
  await mockSession(page, noneSession)
  const requests = []
  let diagnosticHouseholdRequests = 0
  let exportDownloadRequests = 0

  for (const action of fixtureActions) {
    await page.route(action.endpoint, async (route) => {
      requests.push(`${route.request().method()} ${action.key}`)
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          status: 'ok',
          dataset: action.key,
          household_id: action.key === 'browser-reset' ? 'demo-household' : 'regression-household',
          ...(action.key === 'receipt-export' ? { latestBatchId: 'batch-export-1' } : {}),
        }),
      })
    })
  }

  await page.route('**/api/testing/diagnostics/store-location-options', async (route) => {
    diagnosticHouseholdRequests += 1
    await route.fulfill({ status: 500, contentType: 'application/json', body: '{}' })
  })
  await page.route('**/api/testing/fixtures/receipt-export/download*', async (route) => {
    exportDownloadRequests += 1
    await route.fulfill({ status: 500, contentType: 'application/json', body: '{}' })
  })

  await page.goto('/home')
  await expect(page.getByTestId('platform-home-tile-test-fixtures')).toBeVisible()
  await expect(page.locator('[data-testid^="platform-home-tile-"]')).toHaveCount(1)

  await page.goto('/platform/testfixtures')
  await expect(page.getByTestId('platform-test-fixtures-page')).toBeVisible()
  await expect(page.getByText('Household-gerichte diagnostiek is hier bewust niet beschikbaar.')).toBeVisible()
  await expect(page.getByText('De receipt-exportdownload is hier eveneens niet beschikbaar, omdat die route zonder identifiers zelf testdata kan genereren.')).toBeVisible()
  await expect(page.getByText('Let op: dit is een destructieve testdata-actie. Bestaande regressiefixturedata wordt verwijderd.')).toBeVisible()
  expect(requests).toEqual([])
  expect(diagnosticHouseholdRequests).toBe(0)
  expect(exportDownloadRequests).toBe(0)

  for (const action of fixtureActions) {
    const before = requests.length
    await page.getByRole('button', { name: action.title, exact: true }).click()
    await expect(page.getByTestId(`platform-test-fixtures-confirm-${action.key}`)).toBeVisible()
    expect(requests).toHaveLength(before)

    await page.getByRole('button', { name: action.confirm, exact: true }).click()
    await expect(page.getByTestId(`platform-test-fixtures-result-${action.key}`)).toContainText('Resultaat: ok')
    expect(requests).toHaveLength(before + 1)
    expect(requests[requests.length - 1]).toBe(`POST ${action.key}`)
  }

  expect(requests).toEqual([
    'POST browser-reset',
    'POST inventory-ensure',
    'POST receipt-layer1',
    'POST seed-kassa',
    'POST receipt-export',
    'POST cleanup',
  ])
  expect(diagnosticHouseholdRequests).toBe(0)
  expect(exportDownloadRequests).toBe(0)
})

test('test fixtures direct route fails closed without platform.test_fixtures.manage and performs no fixture call', async ({ page }) => {
  const auditOnlySession = {
    ...noneSession,
    permissions: { 'platform.audit.view': true },
    supported_permissions: ['platform.audit.view'],
  }
  await mockSession(page, auditOnlySession)
  let fixtureCalls = 0

  await page.route('**/api/testing/fixtures/**', async (route) => {
    fixtureCalls += 1
    await route.fulfill({ status: 200, contentType: 'application/json', body: '{}' })
  })

  await page.goto('/platform/testfixtures')
  await expect(page).toHaveURL(/\/home$/)
  await expect(page.getByTestId('none-session-home')).toBeVisible()
  expect(fixtureCalls).toBe(0)
})
