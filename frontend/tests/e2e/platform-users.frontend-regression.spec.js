import { expect, test } from '@playwright/test'

const USERS_PERMISSION = 'platform.users.suspend'
const USERS_ENDPOINT = '**/api/platform/users'
const USER_SUSPEND_ENDPOINT = '**/api/platform/users/target-user/suspend'

const noneSession = {
  user: { id: 'platform-users-actor', email: 'platform-users@example.test' },
  user_id: 'platform-users-actor',
  email: 'platform-users@example.test',
  context_type: 'none',
  active_household_id: null,
  active_household_name: '',
  role: null,
  display_role: null,
  permissions: { [USERS_PERMISSION]: true },
  supported_permissions: [USERS_PERMISSION],
  is_platform_superuser: false,
  is_frontteam: false,
}

const users = [
  {
    user_id: 'platform-users-actor',
    email: 'platform-users@example.test',
    account_status: 'active',
    suspended_at: null,
    active_session_count: 1,
    is_current: true,
  },
  {
    user_id: 'target-user',
    email: 'target-user@example.test',
    account_status: 'active',
    suspended_at: null,
    active_session_count: 2,
    is_current: false,
  },
  {
    user_id: 'already-suspended',
    email: 'already-suspended@example.test',
    account_status: 'suspended',
    suspended_at: '2026-08-24T18:00:00+00:00',
    active_session_count: 0,
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

test('users page suspends only after explicit confirmation and never exposes credential authority', async ({ page }) => {
  await mockSession(page, noneSession)
  const reads = []
  const suspends = []

  await page.route(USERS_ENDPOINT, async (route) => {
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
        items: users,
        count: users.length,
        household_context_used: false,
        context_type: 'none',
      }),
    })
  })

  await page.route(USER_SUSPEND_ENDPOINT, async (route) => {
    const request = route.request()
    suspends.push({
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
          user_id: 'target-user',
          email: 'target-user@example.test',
          account_status: 'suspended',
          suspended_at: '2026-08-24T20:00:00+00:00',
          active_sessions_revoked: 2,
        },
        household_context_used: false,
        context_type: 'none',
      }),
    })
  })

  await page.goto('/home')
  await expect(page.getByTestId('platform-home-tile-users')).toBeVisible()
  await expect(page.locator('[data-testid^="platform-home-tile-"]')).toHaveCount(1)

  await page.goto('/platform/gebruikers')
  await expect(page.getByTestId('platform-users-page')).toBeVisible()
  await expect(page.getByText(/nooit een fallback naar huishouden 0/i)).toBeVisible()
  await expect(page.getByText(/wachtwoorden, password-hashes, sessietokens en token-hashes worden niet getoond/i)).toBeVisible()

  const current = page.getByTestId('platform-user-platform-users-actor')
  const target = page.getByTestId('platform-user-target-user')
  const suspended = page.getByTestId('platform-user-already-suspended')

  await expect(current).toContainText('Huidig beheeraccount')
  await expect(current.getByRole('button', { name: 'Gebruiker schorsen', exact: true })).toHaveCount(0)
  await expect(target).toContainText('Actieve sessies: 2')
  await expect(suspended).toContainText('Status: Geschorst')
  await expect(suspended.getByRole('button', { name: 'Gebruiker schorsen', exact: true })).toHaveCount(0)

  expect(reads).toHaveLength(1)
  expect(reads[0].method).toBe('GET')
  expect(reads[0].postData).toBeNull()
  expect(reads[0].url).not.toContain('household')
  expect(reads[0].headers.authorization).toBeUndefined()
  expect(reads[0].headers['x-admin-key']).toBeUndefined()
  expect(suspends).toHaveLength(0)

  await target.getByRole('button', { name: 'Gebruiker schorsen', exact: true }).click()
  await expect(page.getByTestId('platform-user-suspend-confirmation')).toBeVisible()
  expect(suspends).toHaveLength(0)

  await page.getByRole('button', { name: 'Annuleren', exact: true }).click()
  await expect(page.getByTestId('platform-user-suspend-confirmation')).toHaveCount(0)
  expect(suspends).toHaveLength(0)

  await target.getByRole('button', { name: 'Gebruiker schorsen', exact: true }).click()
  await page.getByRole('button', { name: 'Definitief schorsen', exact: true }).click()
  await expect.poll(() => suspends.length).toBe(1)

  expect(suspends[0].method).toBe('POST')
  expect(suspends[0].postData).toBeNull()
  expect(suspends[0].url).toContain('/api/platform/users/target-user/suspend')
  expect(suspends[0].url).not.toContain('household')
  expect(suspends[0].headers.authorization).toBeUndefined()
  expect(suspends[0].headers['x-admin-key']).toBeUndefined()

  await expect(target).toContainText('Status: Geschorst')
  await expect(target).toContainText('Actieve sessies: 0')
  await expect(target.getByRole('button', { name: 'Gebruiker schorsen', exact: true })).toHaveCount(0)
  await expect(page.getByRole('status')).toContainText('2 actieve sessie(s) zijn ingetrokken')
})

test('users direct route stays closed without permission and performs no user-management request', async ({ page }) => {
  const auditOnlySession = {
    ...noneSession,
    permissions: { 'platform.audit.view': true },
    supported_permissions: ['platform.audit.view'],
  }
  await mockSession(page, auditOnlySession)
  let reads = 0
  let suspends = 0

  await page.route(USERS_ENDPOINT, async (route) => {
    reads += 1
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: '{"items":[]}',
    })
  })
  await page.route('**/api/platform/users/*/suspend', async (route) => {
    suspends += 1
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: '{}',
    })
  })

  await page.goto('/platform/gebruikers')
  await expect(page).toHaveURL(/\/home$/)
  await expect(page.getByTestId('none-session-home')).toBeVisible()
  expect(reads).toBe(0)
  expect(suspends).toBe(0)
})
