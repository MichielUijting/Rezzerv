import { expect, test } from '@playwright/test'

const AUTHORIZATIONS_PERMISSION = 'platform.permissions.manage'
const AUTHORIZATIONS_ENDPOINT = '**/api/platform/authorizations'
const GRANT_ENDPOINT = '**/api/platform/authorizations/users/target-user/platform-admin/grant'
const REVOKE_ENDPOINT = '**/api/platform/authorizations/users/target-user/platform-admin/revoke'

const noneSession = {
  user: { id: 'platform-auth-actor', email: 'platform-auth@example.test' },
  user_id: 'platform-auth-actor',
  email: 'platform-auth@example.test',
  context_type: 'none',
  active_household_id: null,
  active_household_name: '',
  role: null,
  display_role: null,
  permissions: { [AUTHORIZATIONS_PERMISSION]: true },
  supported_permissions: [AUTHORIZATIONS_PERMISSION],
  is_platform_superuser: false,
  is_frontteam: false,
}

const roles = [
  {
    role_key: 'platform.frontteam',
    name: 'Frontteamlid',
    permissions: ['platform.frontteam_messages.read'],
    managed_by_this_page: false,
  },
  {
    role_key: 'platform.ip_owner',
    name: 'IP-eigenaar',
    permissions: [AUTHORIZATIONS_PERMISSION, 'platform.special_roles.manage'],
    managed_by_this_page: false,
  },
  {
    role_key: 'platform.platform_admin',
    name: 'Platformbeheerder',
    permissions: [AUTHORIZATIONS_PERMISSION, 'platform.users.suspend'],
    managed_by_this_page: true,
  },
  {
    role_key: 'platform.superuser',
    name: 'Platform-superuser',
    permissions: [AUTHORIZATIONS_PERMISSION],
    managed_by_this_page: false,
  },
]

const users = [
  {
    user_id: 'platform-auth-actor',
    email: 'platform-auth@example.test',
    account_status: 'active',
    platform_role_keys: ['platform.platform_admin'],
    effective_platform_permissions: [AUTHORIZATIONS_PERMISSION],
    has_platform_admin: true,
    is_current: true,
    can_grant_platform_admin: false,
    can_revoke_platform_admin: false,
  },
  {
    user_id: 'target-user',
    email: 'target-user@example.test',
    account_status: 'active',
    platform_role_keys: ['platform.frontteam'],
    effective_platform_permissions: ['platform.frontteam_messages.read'],
    has_platform_admin: false,
    is_current: false,
    can_grant_platform_admin: true,
    can_revoke_platform_admin: false,
  },
  {
    user_id: 'suspended-user',
    email: 'suspended-user@example.test',
    account_status: 'suspended',
    platform_role_keys: [],
    effective_platform_permissions: [],
    has_platform_admin: false,
    is_current: false,
    can_grant_platform_admin: false,
    can_revoke_platform_admin: false,
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

test('platform authorizations grants platform admin only after explicit confirmation', async ({ page }) => {
  await mockSession(page, noneSession)
  const reads = []
  const grants = []
  const revokes = []

  await page.route(AUTHORIZATIONS_ENDPOINT, async (route) => {
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
        users,
        roles,
        managed_role_key: 'platform.platform_admin',
        household_context_used: false,
        context_type: 'none',
      }),
    })
  })

  await page.route(GRANT_ENDPOINT, async (route) => {
    const request = route.request()
    grants.push({
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
          ...users[1],
          platform_role_keys: ['platform.frontteam', 'platform.platform_admin'],
          effective_platform_permissions: ['platform.frontteam_messages.read', AUTHORIZATIONS_PERMISSION],
          has_platform_admin: true,
          can_grant_platform_admin: false,
          can_revoke_platform_admin: true,
        },
        household_context_used: false,
        context_type: 'none',
      }),
    })
  })

  await page.route(REVOKE_ENDPOINT, async (route) => {
    revokes.push(route.request().method())
    await route.fulfill({ status: 200, contentType: 'application/json', body: '{}' })
  })

  await page.goto('/home')
  await expect(page.getByTestId('platform-home-tile-permissions')).toBeVisible()
  await expect(page.locator('[data-testid^="platform-home-tile-"]')).toHaveCount(1)

  await page.goto('/platform/autorisaties')
  await expect(page.getByTestId('platform-authorizations-page')).toBeVisible()
  await expect(page.getByText(/geen householdcontext en geen H0-fallback/i)).toBeVisible()
  await expect(page.getByText(/IP-owner, de bestaande Superuser-v1.1-rol, support en frontteam blijven read-only/i)).toBeVisible()
  await expect(page.getByText(/wachtwoorden, hashes en sessietokens worden niet geprojecteerd/i)).toBeVisible()

  const current = page.getByTestId('platform-authorization-user-platform-auth-actor')
  const target = page.getByTestId('platform-authorization-user-target-user')
  const suspended = page.getByTestId('platform-authorization-user-suspended-user')

  await expect(current).toContainText('Huidig beheeraccount')
  await expect(current.getByRole('button', { name: 'Platformbeheerder intrekken', exact: true })).toHaveCount(0)
  await expect(target).toContainText('Frontteamlid')
  await expect(suspended).toContainText('Een geschorst account kan geen Platformbeheerder worden')
  await expect(suspended.getByRole('button', { name: 'Platformbeheerder maken', exact: true })).toHaveCount(0)

  await expect(page.getByTestId('platform-role-platform.ip_owner')).toContainText('Read-only op deze pagina')
  await expect(page.getByTestId('platform-role-platform.superuser')).toContainText('Read-only op deze pagina')
  await expect(page.getByTestId('platform-role-platform.platform_admin')).toContainText('Beheerbaar op deze pagina')

  expect(reads).toHaveLength(1)
  expect(reads[0].method).toBe('GET')
  expect(reads[0].postData).toBeNull()
  expect(reads[0].url).not.toContain('household')
  expect(reads[0].headers.authorization).toBeUndefined()
  expect(reads[0].headers['x-admin-key']).toBeUndefined()
  expect(grants).toHaveLength(0)
  expect(revokes).toHaveLength(0)

  await target.getByRole('button', { name: 'Platformbeheerder maken', exact: true }).click()
  await expect(page.getByTestId('platform-authorization-confirmation')).toBeVisible()
  expect(grants).toHaveLength(0)
  expect(revokes).toHaveLength(0)

  await page.getByRole('button', { name: 'Annuleren', exact: true }).click()
  await expect(page.getByTestId('platform-authorization-confirmation')).toHaveCount(0)
  expect(grants).toHaveLength(0)

  await target.getByRole('button', { name: 'Platformbeheerder maken', exact: true }).click()
  await page.getByRole('button', { name: 'Definitief toekennen', exact: true }).click()
  await expect.poll(() => grants.length).toBe(1)

  expect(grants[0].method).toBe('POST')
  expect(grants[0].postData).toBeNull()
  expect(grants[0].url).toContain('/api/platform/authorizations/users/target-user/platform-admin/grant')
  expect(grants[0].url).not.toContain('household')
  expect(grants[0].headers.authorization).toBeUndefined()
  expect(grants[0].headers['x-admin-key']).toBeUndefined()
  expect(revokes).toHaveLength(0)

  await expect(target).toContainText('Platformbeheerder')
  await expect(target.getByRole('button', { name: 'Platformbeheerder intrekken', exact: true })).toBeVisible()
  await expect(page.getByRole('status')).toContainText('is Platformbeheerder geworden')
})

test('platform authorizations direct route stays closed without permission and performs no management request', async ({ page }) => {
  const usersOnlySession = {
    ...noneSession,
    permissions: { 'platform.users.suspend': true },
    supported_permissions: ['platform.users.suspend'],
  }
  await mockSession(page, usersOnlySession)
  let reads = 0
  let mutations = 0

  await page.route(AUTHORIZATIONS_ENDPOINT, async (route) => {
    reads += 1
    await route.fulfill({ status: 200, contentType: 'application/json', body: '{"users":[],"roles":[]}' })
  })
  await page.route('**/api/platform/authorizations/users/**', async (route) => {
    mutations += 1
    await route.fulfill({ status: 200, contentType: 'application/json', body: '{}' })
  })

  await page.goto('/platform/autorisaties')
  await expect(page).toHaveURL(/\/home$/)
  await expect(page.getByTestId('none-session-home')).toBeVisible()
  expect(reads).toBe(0)
  expect(mutations).toBe(0)
})
