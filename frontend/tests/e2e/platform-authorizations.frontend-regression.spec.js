import { expect, test } from '@playwright/test'

test.use({ storageState: { cookies: [], origins: [] } })

const INVENTORY_PERMISSION = 'platform.permissions.manage'
const SPECIAL_ROLES_PERMISSION = 'platform.special_roles.manage'
const AUTHORIZATIONS_ENDPOINT = '**/api/platform/authorizations'

const roles = [
  { role_key: 'platform.frontteam', name: 'Frontteamlid', permissions: [], managed_by_this_page: true, protected: false },
  { role_key: 'platform.ip_owner', name: 'IP-eigenaar', permissions: [SPECIAL_ROLES_PERMISSION], managed_by_this_page: false, protected: true },
  { role_key: 'platform.platform_admin', name: 'Platformbeheerder', permissions: [INVENTORY_PERMISSION], managed_by_this_page: true, protected: false },
  { role_key: 'platform.superuser', name: 'Superuser', permissions: [], managed_by_this_page: true, protected: false },
]

function action(active, canGrant, canRevoke, reason = null) {
  return {
    active,
    can_grant: canGrant,
    can_revoke: canRevoke,
    grant_blocked_reason: canGrant ? null : reason,
    revoke_blocked_reason: canRevoke ? null : reason,
  }
}

function user(overrides = {}) {
  return {
    user_id: 'target-user',
    email: 'target-user@example.test',
    account_status: 'active',
    platform_role_keys: [],
    effective_platform_permissions: [],
    is_current: false,
    is_ip_owner: false,
    role_actions: {
      'platform.superuser': action(false, true, false, 'Rol is niet actief'),
      'platform.frontteam': action(false, true, false, 'Rol is niet actief'),
      'platform.platform_admin': action(false, true, false, 'Rol is niet actief'),
    },
    ...overrides,
  }
}

async function mockSession(page, session) {
  await page.route('**/api/session', async (route) => {
    await route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(session) })
  })
}

const platformAdminSession = {
  user: { id: 'platform-admin', email: 'platform-admin@example.test' },
  user_id: 'platform-admin',
  email: 'platform-admin@example.test',
  context_type: 'none',
  active_household_id: null,
  active_household_name: '',
  role: null,
  display_role: null,
  permissions: { [INVENTORY_PERMISSION]: true },
  supported_permissions: [INVENTORY_PERMISSION],
  is_platform_superuser: false,
  is_frontteam: false,
}

const ipOwnerSession = {
  user: { id: 'owner', email: 'owner@example.test' },
  user_id: 'owner',
  email: 'owner@example.test',
  context_type: 'none',
  active_household_id: null,
  active_household_name: '',
  role: null,
  display_role: null,
  permissions: { [SPECIAL_ROLES_PERMISSION]: true },
  supported_permissions: [SPECIAL_ROLES_PERMISSION],
  is_platform_superuser: false,
  is_frontteam: false,
}

test('platformbeheerder can inspect authorizations but cannot mutate special roles', async ({ page }) => {
  await mockSession(page, platformAdminSession)
  let mutations = 0
  await page.route(AUTHORIZATIONS_ENDPOINT, async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        users: [user({
          role_actions: {
            'platform.superuser': action(false, false, false, 'Alleen de IP-eigenaar beheert speciale rollen'),
            'platform.frontteam': action(false, false, false, 'Alleen de IP-eigenaar beheert speciale rollen'),
            'platform.platform_admin': action(false, false, false, 'Alleen de IP-eigenaar beheert speciale rollen'),
          },
        })],
        roles,
        inventory_permission: INVENTORY_PERMISSION,
        special_roles_permission: SPECIAL_ROLES_PERMISSION,
        can_manage_special_roles: false,
        household_context_used: false,
        context_type: 'none',
      }),
    })
  })
  await page.route('**/api/platform/authorizations/users/**', async (route) => {
    mutations += 1
    await route.fulfill({ status: 500, body: 'unexpected mutation' })
  })

  await page.goto('/platform/autorisaties')
  await expect(page.getByTestId('platform-authorizations-page')).toBeVisible()
  await expect(page.getByTestId('platform-authorizations-read-only')).toContainText('Alleen-lezen')
  await expect(page.getByRole('button', { name: /toekennen|intrekken/i })).toHaveCount(0)
  expect(mutations).toBe(0)
})

test('IP-owner sees only active Superusers and can grant by email or revoke', async ({ page }) => {
  await mockSession(page, ipOwnerSession)
  const mutations = []
  let isSuperuser = false

  await page.route('**/api/ip-owner/superusers', async (route) => {
    const request = route.request()
    if (request.method() === 'POST') {
      mutations.push({ url: request.url(), method: request.method(), headers: request.headers(), postData: request.postData() })
      isSuperuser = true
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({ item: { user_id: 'target-user' }, context_type: 'none' }),
      })
      return
    }
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        users: isSuperuser
          ? [{
              user_id: 'target-user',
              email: 'target-user@example.test',
              account_status: 'active',
              is_superuser: true,
              can_revoke: true,
            }]
          : [],
        can_manage_superusers: true,
        context_type: 'none',
        household_context_used: false,
      }),
    })
  })

  await page.route('**/api/platform/authorizations/users/target-user/superuser/revoke', async (route) => {
    const request = route.request()
    mutations.push({ url: request.url(), method: request.method(), headers: request.headers(), postData: request.postData() })
    isSuperuser = false
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({ item: { user_id: 'target-user' }, context_type: 'none' }),
    })
  })

  await page.goto('/ip-eigenaar/superusers')
  await expect(page.getByTestId('ip-owner-superusers-page')).toBeVisible()
  await expect(page.getByText('De IP-eigenaar kan uitsluitend de Superuserrol beheren.')).toBeVisible()
  await expect(page.getByText('Platformbeheerder', { exact: true })).toHaveCount(0)
  await expect(page.getByText('Frontteamlid', { exact: true })).toHaveCount(0)
  await expect(page.getByText('Er zijn geen actieve Superusers.')).toBeVisible()

  await page.getByLabel('E-mailadres').fill('target-user@example.test')
  await page.getByRole('button', { name: 'Superuser maken', exact: true }).click()
  await expect(page.getByTestId('ip-owner-superuser-confirmation')).toContainText('Superuser maken?')
  expect(mutations).toHaveLength(0)
  await page.getByRole('button', { name: 'Definitief Superuser maken', exact: true }).click()
  await expect.poll(() => mutations.length).toBe(1)
  expect(mutations[0].method).toBe('POST')
  expect(mutations[0].url).toContain('/api/ip-owner/superusers')
  expect(JSON.parse(mutations[0].postData)).toEqual({ email: 'target-user@example.test' })
  expect(mutations[0].headers.authorization).toBeUndefined()

  const target = page.getByTestId('ip-owner-superuser-target-user')
  await expect(target).toContainText('Superuser actief')
  await target.getByRole('button', { name: 'Deactiveren', exact: true }).click()
  await expect(page.getByTestId('ip-owner-superuser-confirmation')).toContainText('Superuser deactiveren?')
  await page.getByRole('button', { name: 'Definitief deactiveren', exact: true }).click()
  await expect.poll(() => mutations.length).toBe(2)
  expect(mutations[1].url).toContain('/superuser/revoke')
  await expect(page.getByText('Er zijn geen actieve Superusers.')).toBeVisible()
})

test('platform authorizations direct route stays closed without inventory permission', async ({ page }) => {
  await mockSession(page, {
    ...platformAdminSession,
    permissions: { 'platform.users.suspend': true },
    supported_permissions: ['platform.users.suspend'],
  })
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
  expect(reads).toBe(0)
  expect(mutations).toBe(0)
})
