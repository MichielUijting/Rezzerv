import { expect, test } from '@playwright/test'

test.use({ storageState: { cookies: [], origins: [] } })

test('Superuser beheert Frontteam via e-mailadres en ledenlijst', async ({ page }) => {
  const permission = 'platform.frontteam_roles.manage'
  await page.route('**/api/session', async (route) => route.fulfill({
    status: 200, contentType: 'application/json', body: JSON.stringify({
      user: { id: 'superuser', email: 'superuser@example.test' }, user_id: 'superuser',
      email: 'superuser@example.test', context_type: 'system', active_household_id: '0',
      active_household_name: 'Systeemhuishouden', display_role: 'Superuser',
      permissions: { [permission]: true }, supported_permissions: [permission], is_platform_superuser: true,
    }),
  }))
  await page.route('**/api/onboarding', async (route) => route.fulfill({ status: 200, contentType: 'application/json', body: '{}' }))

  let membership = null
  const member = () => ({
    user_id: 'admin-user', email: 'admin@example.test', account_status: 'active',
    platform_role_keys: membership === 'active' ? ['platform.frontteam'] : [],
    frontteam_status: membership, role_actions: { 'platform.frontteam': { can_grant: membership !== 'active', can_revoke: membership === 'active' } },
  })
  await page.route('**/api/platform/frontteam-management', async (route) => route.fulfill({
    status: 200, contentType: 'application/json',
    body: JSON.stringify({ frontteam_memberships: membership ? [member()] : [], can_manage_frontteam_roles: true }),
  }))
  await page.route('**/api/platform/frontteam-management/members', async (route) => {
    membership = 'active'
    await route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({ item: member() }) })
  })
  await page.route('**/api/platform/authorizations/users/admin-user/frontteam/**', async (route) => {
    membership = route.request().url().endsWith('/grant') ? 'active' : 'inactive'
    await route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({ item: member() }) })
  })
  await page.route('**/api/platform/frontteam-management/members/admin-user', async (route) => {
    membership = null
    await route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({ ok: true }) })
  })

  await page.goto('/instellingen/frontteam')
  await expect(page.getByText('Er zijn nog geen Frontteamleden.')).toBeVisible()
  await page.getByLabel('E-mailadres').fill('admin@example.test')
  await page.getByRole('button', { name: 'Toevoegen aan Frontteam' }).click()

  const row = page.getByTestId('frontteam-member-admin-user')
  await expect(row).toContainText('admin@example.test')
  await expect(row).toContainText('Actief')
  await expect(page.getByTestId('frontteam-members-table')).toBeVisible()
  await expect(page.getByPlaceholder('Filter e-mailadres')).toBeVisible()
  await expect(page.getByRole('navigation', { name: 'Paginering' })).toBeVisible()

  await page.getByLabel('Selecteer admin@example.test').check()
  await page.getByRole('button', { name: 'Deactiveren' }).click()
  await expect(row).toContainText('Inactief')
  await page.getByRole('button', { name: 'Activeren' }).click()
  await expect(row).toContainText('Actief')
  await expect(page.getByRole('button', { name: 'Exporteren' })).toBeEnabled()

  page.on('dialog', (dialog) => dialog.accept())
  await page.getByRole('button', { name: 'Verwijderen' }).click()
  await expect(page.getByText('Er zijn nog geen Frontteamleden.')).toBeVisible()
  await expect(page.getByRole('status')).toContainText('Inhuis-account en eigen huishouden zijn behouden')
})
