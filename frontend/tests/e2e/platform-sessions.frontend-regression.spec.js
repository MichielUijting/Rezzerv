import { expect, test } from '@playwright/test'

const SESSIONS_PERMISSION = 'platform.sessions.revoke'
const SESSIONS_ENDPOINT = '**/api/platform/sessions'
const SESSION_REVOKE_ENDPOINT = '**/api/platform/sessions/session-target-active/revoke'

const noneSession = {
  user: { id: 'platform-sessions-user', email: 'platform-sessions@example.test' },
  user_id: 'platform-sessions-user',
  email: 'platform-sessions@example.test',
  context_type: 'none',
  active_household_id: null,
  active_household_name: '',
  role: null,
  display_role: null,
  permissions: { [SESSIONS_PERMISSION]: true },
  supported_permissions: [SESSIONS_PERMISSION],
  is_platform_superuser: false,
  is_frontteam: false,
}

const activeSessions = [
  {
    session_id: 'session-current',
    user_id: 'platform-sessions-user',
    email: 'platform-sessions@example.test',
    issued_at: '2026-08-24T18:00:00+00:00',
    expires_at: '2026-08-25T06:00:00+00:00',
    is_current: true,
  },
  {
    session_id: 'session-target-active',
    user_id: 'target-user',
    email: 'target-user@example.test',
    issued_at: '2026-08-24T18:10:00+00:00',
    expires_at: '2026-08-25T06:10:00+00:00',
    is_current: false,
  },
]

async function mockSession(page, session) {
  await page.route('**/api/session', async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify(session),
    })
  })
}

test('sessions page lists safe active sessions and revokes only after explicit confirmation', async ({ page }) => {
  await mockSession(page, noneSession)
  const reads = []
  const revokes = []

  await page.route(SESSIONS_ENDPOINT, async (route) => {
    const request = route.request()
    reads.push({
      method: request.method(),
      url: request.url(),
      headers: request.headers(),
      postData: request.postData(),
    })
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        items: activeSessions,
        count: activeSessions.length,
        household_context_used: false,
        context_type: 'none',
      }),
    })
  })

  await page.route(SESSION_REVOKE_ENDPOINT, async (route) => {
    const request = route.request()
    revokes.push({
      method: request.method(),
      url: request.url(),
      headers: request.headers(),
      postData: request.postData(),
    })
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        item: {
          session_id: 'session-target-active',
          user_id: 'target-user',
          email: 'target-user@example.test',
          issued_at: '2026-08-24T18:10:00+00:00',
          expires_at: '2026-08-25T06:10:00+00:00',
          revoked_at: '2026-08-24T19:00:00+00:00',
        },
        household_context_used: false,
        context_type: 'none',
      }),
    })
  })

  await page.goto('/home')
  await expect(page.getByTestId('platform-home-tile-sessions')).toBeVisible()
  await expect(page.locator('[data-testid^="platform-home-tile-"]')).toHaveCount(1)

  await page.goto('/platform/sessies')
  await expect(page.getByTestId('platform-sessions-page')).toBeVisible()
  await expect(page.getByText(/nooit een fallback naar huishouden 0/i)).toBeVisible()

  const current = page.getByTestId('platform-session-session-current')
  const target = page.getByTestId('platform-session-session-target-active')
  await expect(current).toContainText('Huidige sessie')
  await expect(current.getByRole('button', { name: 'Sessie intrekken', exact: true })).toHaveCount(0)
  await expect(target).toContainText('target-user@example.test')

  expect(reads).toHaveLength(1)
  expect(reads[0].method).toBe('GET')
  expect(reads[0].postData).toBeNull()
  expect(reads[0].url).not.toContain('household')
  expect(reads[0].headers.authorization).toBeUndefined()
  expect(reads[0].headers['x-admin-key']).toBeUndefined()
  expect(revokes).toHaveLength(0)

  await target.getByRole('button', { name: 'Sessie intrekken', exact: true }).click()
  await expect(page.getByTestId('platform-session-confirmation')).toBeVisible()
  expect(revokes).toHaveLength(0)

  await page.getByRole('button', { name: 'Annuleren', exact: true }).click()
  await expect(page.getByTestId('platform-session-confirmation')).toHaveCount(0)
  expect(revokes).toHaveLength(0)

  await target.getByRole('button', { name: 'Sessie intrekken', exact: true }).click()
  await page.getByRole('button', { name: 'Definitief intrekken', exact: true }).click()
  await expect.poll(() => revokes.length).toBe(1)

  expect(revokes[0].method).toBe('POST')
  expect(revokes[0].postData).toBeNull()
  expect(revokes[0].url).toContain('/api/platform/sessions/session-target-active/revoke')
  expect(revokes[0].url).not.toContain('household')
  expect(revokes[0].headers.authorization).toBeUndefined()
  expect(revokes[0].headers['x-admin-key']).toBeUndefined()

  await expect(page.getByTestId('platform-session-session-target-active')).toHaveCount(0)
  await expect(page.getByRole('status')).toContainText('target-user@example.test')
  await expect(page.getByTestId('platform-session-session-current')).toBeVisible()
})

test('sessions direct route stays closed without permission and performs no session-management request', async ({ page }) => {
  const auditOnlySession = {
    ...noneSession,
    permissions: { 'platform.audit.view': true },
    supported_permissions: ['platform.audit.view'],
  }
  await mockSession(page, auditOnlySession)
  let reads = 0
  let revokes = 0

  await page.route(SESSIONS_ENDPOINT, async (route) => {
    reads += 1
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: '{"items":[]}',
    })
  })
  await page.route('**/api/platform/sessions/*/revoke', async (route) => {
    revokes += 1
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: '{}',
    })
  })

  await page.goto('/platform/sessies')
  await expect(page).toHaveURL(/\/home$/)
  await expect(page.getByTestId('none-session-home')).toBeVisible()
  expect(reads).toBe(0)
  expect(revokes).toBe(0)
})
