import { expect, test } from '@playwright/test'

const INVENTORY_PERMISSION = 'platform.permissions.manage'
const SPECIAL_ROLES_PERMISSION = 'platform.special_roles.manage'
const AUTHORIZATIONS_ENDPOINT = '**/api/platform/authorizations'

const roles = [
  { role_key: 'platform.frontteam', name: 'Frontteamlid', permissions: [], managed_by_this_page: true, protected: false },
  { role_key: 'platform.ip_owner', name: 'IP-eigenaar', permissions: [SPECIAL_ROLES_PERMISSION], managed_by_this_page: false, protected: true },
  { role_key: 'platform.platform_admin', name: 'Platformbeheerder', permissions: [INVENTORY_PERMISSION], managed_by_this_page: true, protected: false },
  { role_key: 'platform.superuser', name: 'Platform-superuser', permissions: [], managed_by_this_page: true, protected: false },
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
  context_type: 'system',
  active_household_id: '0',
  active_household_name: 'Systeem',
  role: 'owner',
  display_role: 'Eigenaar',
  permissions: { [INVENTORY_PERMISSION]: true, [SPECIAL_ROLES_PERMISSION]: true },
  supported_permissions: [INVENTORY_PERMISSION, SPECIAL_ROLES_PERMISSION],
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
  await expect(page.getByTestId('platform-authorizations-read-only')).toContainText('alleen de IP-eigenaar')
  await expect(page.getByRole('button', { name: /toekennen|intrekken/i })).toHaveCount(0)
  expect(mutations).toBe(0)
})

test('IP-owner manages the three ordinary special roles only after explicit confirmation', async ({ page }) => {
  await mockSession(page, ipOwnerSession)
  const mutations = []
  let currentTarget = user()
  const protectedOwner = user({
    user_id: 'owner',
    email: 'owner@example.test',
    platform_role_keys: ['platform.ip_owner'],
    effective_platform_permissions: [INVENTORY_PERMISSION, SPECIAL_ROLES_PERMISSION],
    is_current: true,
    is_ip_owner: true,
    role_actions: {
      'platform.superuser': action(false, false, false, 'IP-eigenaar is beschermd tegen regulier rolbeheer'),
      'platform.frontteam': action(false, false, false, 'IP-eigenaar is beschermd tegen regulier rolbeheer'),
      'platform.platform_admin': action(false, false, false, 'IP-eigenaar is beschermd tegen regulier rolbeheer'),
    },
  })

  await page.route(AUTHORIZATIONS_ENDPOINT, async (route) => {
    const request = route.request()
    expect(request.method()).toBe('GET')
    expect(request.headers().authorization).toBeUndefined()
    expect(request.headers()['x-admin-key']).toBeUndefined()
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        users: [protectedOwner, currentTarget],
        roles,
        inventory_permission: INVENTORY_PERMISSION,
        special_roles_permission: SPECIAL_ROLES_PERMISSION,
        can_manage_special_roles: true,
        household_context_used: false,
        context_type: 'system',
      }),
    })
  })

  await page.route('**/api/platform/authorizations/users/target-user/**', async (route) => {
    const request = route.request()
    mutations.push({ url: request.url(), method: request.method(), headers: request.headers(), postData: request.postData() })
    currentTarget = user({
      platform_role_keys: ['platform.superuser'],
      role_actions: {
        'platform.superuser': action(true, false, true, 'Rol is al actief'),
        'platform.frontteam': action(false, false, false, 'Frontteamlid kan niet met een systeem- of Platformbeheerderrol worden gecombineerd'),
        'platform.platform_admin': action(false, true, false, 'Rol is niet actief'),
      },
    })
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({ item: currentTarget, household_context_used: false, context_type: 'system' }),
    })
  })

  await page.goto('/platform/autorisaties')
  const target = page.getByTestId('platform-authorization-user-target-user')
  const owner = page.getByTestId('platform-authorization-user-owner')
  await expect(owner).toContainText('Beschermde IP-eigenaar')
  await expect(owner.getByRole('button')).toHaveCount(0)
  await expect(target.getByRole('button', { name: 'Superuser toekennen', exact: true })).toBeVisible()
  await expect(target.getByRole('button', { name: 'Frontteamlid toekennen', exact: true })).toBeVisible()
  await expect(target.getByRole('button', { name: 'Platformbeheerder toekennen', exact: true })).toBeVisible()

  await target.getByRole('button', { name: 'Superuser toekennen', exact: true }).click()
  await expect(page.getByTestId('platform-authorization-confirmation')).toContainText('Superuser definitief toekennen?')
  expect(mutations).toHaveLength(0)
  await page.getByRole('button', { name: 'Annuleren', exact: true }).click()
  expect(mutations).toHaveLength(0)

  await target.getByRole('button', { name: 'Superuser toekennen', exact: true }).click()
  await page.getByRole('button', { name: 'Definitief toekennen', exact: true }).click()
  await expect.poll(() => mutations.length).toBe(1)
  expect(mutations[0].method).toBe('POST')
  expect(mutations[0].postData).toBeNull()
  expect(mutations[0].url).toContain('/api/platform/authorizations/users/target-user/superuser/grant')
  expect(mutations[0].url).not.toContain('household')
  expect(mutations[0].headers.authorization).toBeUndefined()
  expect(mutations[0].headers['x-admin-key']).toBeUndefined()
  await expect(target.getByRole('button', { name: 'Superuser intrekken', exact: true })).toBeVisible()
  await expect(target.getByRole('button', { name: 'Platformbeheerder toekennen', exact: true })).toBeVisible()
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
