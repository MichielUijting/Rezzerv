import { expect, test } from '@playwright/test'

const platformPermissions = {
  'platform.audit.view': true,
  'platform.background_jobs.manage': true,
  'platform.diagnostics.view': true,
  'platform.feature_flags.manage': true,
  'platform.integrations.manage': true,
  'platform.logs.view': true,
  'platform.permissions.manage': true,
  'platform.recovery.manage': true,
  'platform.sessions.revoke': true,
  'platform.technical_configuration.manage': true,
  'platform.test_fixtures.manage': true,
  'platform.users.suspend': true,
}

const noneSession = {
  user: { id: 'platform-user', email: 'platform@example.test' },
  user_id: 'platform-user',
  email: 'platform@example.test',
  context_type: 'none',
  active_household_id: null,
  active_household_name: '',
  role: null,
  display_role: null,
  permissions: platformPermissions,
  supported_permissions: Object.keys(platformPermissions).sort(),
  is_platform_superuser: false,
  is_frontteam: false,
}

async function mockNoneSession(page, session = noneSession) {
  await page.route('**/api/session', async (route) => {
    await route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(session) })
  })
}

test('none session stays authenticated in a safe household-free state', async ({ page }) => {
  let loginCalled = false
  let logoutCalled = false

  await page.route('**/api/auth/login', async (route) => {
    loginCalled = true
    await route.fulfill({ status: 200, contentType: 'application/json', body: '{}' })
  })
  await mockNoneSession(page)
  await page.route('**/api/auth/logout', async (route) => {
    logoutCalled = true
    await route.fulfill({ status: 200, contentType: 'application/json', body: '{}' })
  })

  await page.goto('/login')
  await page.getByTestId('login-submit').click()

  await expect(page).toHaveURL(/\/home$/)
  expect(loginCalled).toBe(true)
  await expect(page.getByTestId('none-session-home')).toBeVisible()
  await expect(page.getByText('Platformbeheerder', { exact: true }).first()).toBeVisible()
  await expect(page.getByText('Er is geen huishoudcontext actief.')).toBeVisible()
  await expect(page.getByText('platform@example.test')).toBeVisible()
  await expect(page.getByText('Huishouden:', { exact: false })).toHaveCount(0)

  for (const tile of ['Voorraad', 'Winkelen', 'Instellingen', 'Admin', 'Superuser']) {
    await expect(page.getByText(tile, { exact: true })).toHaveCount(0)
  }

  await page.goto('/voorraad')
  await expect(page).toHaveURL(/\/home$/)
  await expect(page.getByTestId('none-session-home')).toBeVisible()

  await page.goto('/superuser')
  await expect(page).toHaveURL(/\/home$/)
  await expect(page.getByTestId('none-session-home')).toBeVisible()

  await page.getByTestId('none-session-logout').click()
  await expect(page).toHaveURL(/\/login$/)
  expect(logoutCalled).toBe(true)
})

test('none context cannot cross into a household route even with a household permission', async ({ page }) => {
  const spoofedSession = {
    ...noneSession,
    permissions: { ...platformPermissions, 'shopping_list.view': true },
    supported_permissions: [...Object.keys(platformPermissions), 'shopping_list.view'].sort(),
  }
  await mockNoneSession(page, spoofedSession)

  await page.goto('/winkelen')
  await expect(page).toHaveURL(/\/home$/)
  await expect(page.getByTestId('none-session-home')).toBeVisible()
})
