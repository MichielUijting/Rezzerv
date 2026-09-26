import { expect, test } from '@playwright/test'

test.use({ storageState: { cookies: [], origins: [] } })

test('Superuser beheert Frontteam als aanvullende rol zonder huishoudrol te vervangen', async ({ page }) => {
  const permission = 'platform.frontteam_roles.manage'
  await page.route('**/api/session', async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        user: { id: 'superuser', email: 'superuser@example.test' },
        user_id: 'superuser',
        email: 'superuser@example.test',
        context_type: 'system',
        active_household_id: '0',
        active_household_name: 'Systeemhuishouden',
        role: 'owner',
        display_role: 'Superuser',
        permissions: { [permission]: true },
        supported_permissions: [permission],
        is_platform_superuser: true,
        is_frontteam: false,
      }),
    })
  })
  await page.route('**/api/onboarding', async (route) => {
    await route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({}) })
  })

  let active = false
  const target = () => ({
    user_id: 'admin-user',
    email: 'admin@example.test',
    account_status: 'active',
    platform_role_keys: active ? ['platform.frontteam'] : [],
    effective_platform_permissions: [],
    is_current: false,
    is_ip_owner: false,
    role_actions: {
      'platform.frontteam': {
        active,
        can_grant: !active,
        can_revoke: active,
        grant_blocked_reason: active ? 'Rol is al actief' : null,
        revoke_blocked_reason: active ? null : 'Rol is niet actief',
      },
      'platform.superuser': { active: false, can_grant: false, can_revoke: false },
      'platform.platform_admin': { active: false, can_grant: false, can_revoke: false },
    },
  })

  await page.route('**/api/platform/frontteam-management', async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({ users: [target()], can_manage_frontteam_roles: true, context_type: 'system' }),
    })
  })
  await page.route('**/api/platform/authorizations/users/admin-user/frontteam/**', async (route) => {
    active = route.request().url().endsWith('/grant')
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({ item: target(), context_type: 'system' }),
    })
  })

  await page.goto('/instellingen/frontteam')
  await expect(page.getByTestId('settings-frontteam-page')).toBeVisible()
  const user = page.getByTestId('frontteam-user-admin-user')
  await expect(user).toContainText('Frontteam: Nee')
  await user.getByRole('button', { name: 'Frontteamlid maken' }).click()
  await expect(page.getByTestId('frontteam-confirmation')).toContainText('Het eigen reguliere huishouden en de huishoudrol worden niet gewijzigd.')
  await page.getByRole('button', { name: 'Bevestigen' }).click()
  await expect(page.getByRole('status')).toContainText('eigen huishouden en de huishoudrol zijn behouden')
  await expect(user).toContainText('Frontteam: Ja')
  await user.getByRole('button', { name: 'Frontteamlidmaatschap intrekken' }).click()
  await page.getByRole('button', { name: 'Bevestigen' }).click()
  await expect(user).toContainText('Frontteam: Nee')
})
