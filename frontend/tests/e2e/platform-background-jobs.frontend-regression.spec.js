import { expect, test } from '@playwright/test'

const BACKGROUND_PERMISSION = 'platform.background_jobs.manage'

const noneSession = {
  user: { id: 'platform-background-user', email: 'platform-background@example.test' },
  user_id: 'platform-background-user',
  email: 'platform-background@example.test',
  context_type: 'none',
  active_household_id: null,
  active_household_name: '',
  role: null,
  display_role: null,
  permissions: { [BACKGROUND_PERMISSION]: true },
  supported_permissions: [BACKGROUND_PERMISSION],
  is_platform_superuser: false,
  is_frontteam: false,
}

async function mockSession(page, session) {
  await page.route('**/api/session', async (route) => {
    await route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(session) })
  })
}

const allowedActions = [
  {
    key: 'parsing-fixtures',
    title: 'Parsing-fixture regressie uitvoeren',
    confirm: 'Fixture-regressie starten',
    endpoint: '**/api/testing/regression/parsing-fixtures/run',
    testType: 'parsing_fixture',
  },
  {
    key: 'parsing-raw',
    title: 'Raw parsing regressie uitvoeren',
    confirm: 'Raw regressie starten',
    endpoint: '**/api/testing/regression/parsing-raw/run',
    testType: 'parsing_raw',
  },
]

const excludedEndpoints = [
  '**/api/testing/regression/smoke/run',
  '**/api/testing/regression/all/run',
  '**/api/testing/regression/layer1/run',
  '**/api/testing/regression/layer2/run',
  '**/api/testing/regression/layer3/run',
  '**/api/testing/reports/complete',
  '**/api/testing/status',
  '**/api/testing/reports/latest',
]

test('background jobs page confirms and runs only self-contained parsing tasks', async ({ page }) => {
  await mockSession(page, noneSession)
  const requests = []
  const excludedRequests = []

  for (const action of allowedActions) {
    await page.route(action.endpoint, async (route) => {
      requests.push(`${route.request().method()} ${action.key}`)
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          test_type: action.testType,
          last_run_at: '2026-08-24T13:45:00+00:00',
          blocked_count: 0,
          results: [
            { name: 'controle 1', status: 'passed', error: null },
            { name: 'controle 2', status: 'passed', error: null },
          ],
        }),
      })
    })
  }

  for (const endpoint of excludedEndpoints) {
    await page.route(endpoint, async (route) => {
      excludedRequests.push(`${route.request().method()} ${route.request().url()}`)
      await route.fulfill({ status: 500, contentType: 'application/json', body: '{}' })
    })
  }

  await page.goto('/home')
  await expect(page.getByTestId('platform-home-tile-background-jobs')).toBeVisible()
  await expect(page.locator('[data-testid^="platform-home-tile-"]')).toHaveCount(1)

  await page.goto('/platform/achtergrondtaken')
  await expect(page.getByTestId('platform-background-jobs-page')).toBeVisible()
  await expect(page.getByText('De huidige smoke-, volledige regressie- en layer-startmarkers zijn hier bewust niet beschikbaar: zij markeren alleen een externe run als gestart en voeren zonder aparte runner geen complete taak uit.')).toBeVisible()
  await expect(page.getByText('Status en historie vallen onder Diagnostiek en worden op deze pagina niet gelezen zonder')).toBeVisible()
  expect(requests).toEqual([])
  expect(excludedRequests).toEqual([])

  for (const action of allowedActions) {
    const before = requests.length
    await page.getByRole('button', { name: action.title, exact: true }).click()
    await expect(page.getByTestId(`platform-background-jobs-confirm-${action.key}`)).toBeVisible()
    expect(requests).toHaveLength(before)
    expect(excludedRequests).toEqual([])

    await page.getByRole('button', { name: action.confirm, exact: true }).click()
    const result = page.getByTestId(`platform-background-jobs-result-${action.key}`)
    await expect(result).toContainText(`Taaktype: ${action.testType}`)
    await expect(result).toContainText('Controles: 2')
    await expect(result).toContainText('Geslaagd: 2')
    await expect(result).toContainText('Mislukt: 0')
    await expect(result).toContainText('Geblokkeerd: 0')
    expect(requests).toHaveLength(before + 1)
    expect(requests[requests.length - 1]).toBe(`POST ${action.key}`)
    expect(excludedRequests).toEqual([])
  }

  expect(requests).toEqual(['POST parsing-fixtures', 'POST parsing-raw'])
  expect(excludedRequests).toEqual([])
})

test('background jobs direct route stays closed without permission and performs no job calls', async ({ page }) => {
  const auditOnlySession = {
    ...noneSession,
    permissions: { 'platform.audit.view': true },
    supported_permissions: ['platform.audit.view'],
  }
  await mockSession(page, auditOnlySession)
  let jobCalls = 0

  for (const action of allowedActions) {
    await page.route(action.endpoint, async (route) => {
      jobCalls += 1
      await route.fulfill({ status: 200, contentType: 'application/json', body: '{}' })
    })
  }

  await page.goto('/platform/achtergrondtaken')
  await expect(page).toHaveURL(/\/home$/)
  await expect(page.getByTestId('none-session-home')).toBeVisible()
  expect(jobCalls).toBe(0)
})
