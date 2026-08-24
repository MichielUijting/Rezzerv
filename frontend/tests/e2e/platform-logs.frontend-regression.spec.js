import { expect, test } from '@playwright/test'

const LOGS_PERMISSION = 'platform.logs.view'
const LOGS_ENDPOINT = '**/api/platform/logs?*'

const noneSession = {
  user: { id: 'platform-logs-actor', email: 'platform-logs@example.test' },
  user_id: 'platform-logs-actor',
  email: 'platform-logs@example.test',
  context_type: 'none',
  active_household_id: null,
  active_household_name: '',
  role: null,
  display_role: null,
  permissions: { [LOGS_PERMISSION]: true },
  supported_permissions: [LOGS_PERMISSION],
  is_platform_superuser: false,
  is_frontteam: false,
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

test('platform logs is a read-only cookie-session projection with level filtering', async ({ page }) => {
  await mockSession(page, noneSession)
  const reads = []
  let auditReads = 0
  let platformMutations = 0

  await page.route(LOGS_ENDPOINT, async (route) => {
    const request = route.request()
    reads.push({
      method: request.method(),
      url: request.url(),
      headers: request.headers(),
      postData: request.postData(),
    })
    const level = new URL(request.url()).searchParams.get('level')
    const items = level === 'ERROR'
      ? [
          {
            id: 2,
            created_at: '2026-08-24T20:00:01Z',
            level: 'ERROR',
            logger: 'rezzerv.api',
            message: 'Onverwerkte API-fout op /api/example',
            exception_type: 'RuntimeError',
          },
        ]
      : [
          {
            id: 2,
            created_at: '2026-08-24T20:00:01Z',
            level: 'ERROR',
            logger: 'rezzerv.api',
            message: 'Onverwerkte API-fout op /api/example',
            exception_type: 'RuntimeError',
          },
          {
            id: 1,
            created_at: '2026-08-24T20:00:00Z',
            level: 'INFO',
            logger: 'rezzerv.api',
            message: 'Datastore: sqlite',
            exception_type: null,
          },
        ]
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        items,
        count: items.length,
        limit: 100,
        level: level || null,
        levels: ['DEBUG', 'INFO', 'WARNING', 'ERROR', 'CRITICAL'],
        retention: 'runtime_memory',
        max_entries: 500,
        source: 'rezzerv.*',
        audit_separate: true,
        household_context_used: false,
        context_type: 'none',
      }),
    })
  })

  await page.route('**/api/platform/audit?*', async (route) => {
    auditReads += 1
    await route.fulfill({ status: 200, contentType: 'application/json', body: '{"items":[]}' })
  })
  await page.route('**/api/platform/**', async (route) => {
    if (route.request().method() !== 'GET') platformMutations += 1
    await route.continue()
  })

  await page.goto('/home')
  await expect(page.getByTestId('platform-home-tile-logs')).toBeVisible()
  await expect(page.locator('[data-testid^="platform-home-tile-"]')).toHaveCount(1)

  await page.goto('/platform/logs')
  await expect(page.getByTestId('platform-logs-page')).toBeVisible()
  await expect(page.getByText(/staat los van Audit/i)).toBeVisible()
  await expect(page.getByTestId('platform-logs-retention')).toContainText('alleen huidige backendruntime')
  await expect(page.getByTestId('platform-logs-retention')).toContainText('maximaal 500 records')
  await expect(page.getByText(/Tracebacks, requestbodies en headers worden niet opgeslagen/i)).toBeVisible()
  await expect(page.getByTestId('platform-log-item-2')).toContainText('ERROR — rezzerv.api')
  await expect(page.getByTestId('platform-log-item-2')).toContainText('RuntimeError')
  await expect(page.getByTestId('platform-log-item-1')).toContainText('Datastore: sqlite')

  expect(reads).toHaveLength(1)
  expect(reads[0].method).toBe('GET')
  expect(reads[0].postData).toBeNull()
  expect(reads[0].url).toContain('/api/platform/logs?')
  expect(reads[0].url).not.toContain('household')
  expect(reads[0].headers.authorization).toBeUndefined()
  expect(reads[0].headers['x-admin-key']).toBeUndefined()
  expect(auditReads).toBe(0)
  expect(platformMutations).toBe(0)

  await page.getByTestId('platform-logs-level').selectOption('ERROR')
  await expect.poll(() => reads.length).toBe(2)
  await expect(page.getByTestId('platform-log-item-2')).toBeVisible()
  await expect(page.getByTestId('platform-log-item-1')).toHaveCount(0)
  expect(new URL(reads[1].url).searchParams.get('level')).toBe('ERROR')
  expect(reads[1].method).toBe('GET')
  expect(reads[1].postData).toBeNull()
  expect(reads[1].headers.authorization).toBeUndefined()
  expect(reads[1].headers['x-admin-key']).toBeUndefined()
  expect(auditReads).toBe(0)
  expect(platformMutations).toBe(0)

  await page.getByRole('button', { name: 'Vernieuwen', exact: true }).click()
  await expect.poll(() => reads.length).toBe(3)
  expect(reads[2].method).toBe('GET')
  expect(platformMutations).toBe(0)
})

test('platform logs direct route stays closed without platform.logs.view and performs no log request', async ({ page }) => {
  const auditOnlySession = {
    ...noneSession,
    permissions: { 'platform.audit.view': true },
    supported_permissions: ['platform.audit.view'],
  }
  await mockSession(page, auditOnlySession)
  let logReads = 0

  await page.route(LOGS_ENDPOINT, async (route) => {
    logReads += 1
    await route.fulfill({ status: 200, contentType: 'application/json', body: '{"items":[]}' })
  })

  await page.goto('/platform/logs')
  await expect(page).toHaveURL(/\/home$/)
  await expect(page.getByTestId('none-session-home')).toBeVisible()
  expect(logReads).toBe(0)
})
