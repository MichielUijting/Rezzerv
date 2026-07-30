import { test, expect } from '@playwright/test'
import { attachConsoleErrorCollector, expectNoConsoleErrors } from './helpers/rezzervAssertions.js'

async function seedAdminSession(page) {
  await page.addInitScript(() => {
    localStorage.setItem('rezzerv_token', 'rezzerv-dev-token')
    localStorage.setItem('rezzerv_auth_context', JSON.stringify({
      active_household_id: '1',
      display_role: 'admin',
      permissions: {
        'members.manage': true,
        'permissions.view': true,
      },
    }))
    sessionStorage.setItem('rezzerv_auth_checked_token', 'rezzerv-dev-token')
  })
}

function authorizationPayload(roleKey = 'household.member') {
  return {
    household_id: '1',
    members: [
      { membership_id: 'member-admin', email: 'admin@rezzerv.local', role_key: 'household.admin', role_name: 'Beheerder', permission_overrides: [], is_current_user: true },
      { membership_id: 'member-lid', email: 'lid@rezzerv.local', role_key: roleKey, role_name: 'Lid', permission_overrides: [] },
    ],
    roles: [
      { role_key: 'household.viewer', name: 'Viewer', permission_keys: ['inventory.view', 'members.view'] },
      { role_key: 'household.member', name: 'Lid', permission_keys: ['inventory.view', 'inventory.update', 'members.view'] },
      { role_key: 'household.advanced_member', name: 'Gevorderd lid', permission_keys: ['inventory.view', 'inventory.update', 'inventory.correct', 'members.view'] },
      { role_key: 'household.admin', name: 'Beheerder', permission_keys: ['inventory.view', 'inventory.update', 'inventory.correct', 'members.view', 'members.manage'] },
    ],
    permissions: [
      { permission_key: 'inventory.view', description: 'inventory.view' },
      { permission_key: 'inventory.update', description: 'inventory.update' },
      { permission_key: 'inventory.correct', description: 'inventory.correct' },
      { permission_key: 'members.view', description: 'members.view' },
      { permission_key: 'members.manage', description: 'members.manage' },
    ],
  }
}

async function mockAuthorizationApi(page, getRoleKey, setRoleKey) {
  await page.route('**/api/households/1/authorization/members', async (route) => {
    const payload = authorizationPayload(getRoleKey())
    await route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({ household_id: '1', total: 2, items: payload.members }) })
  })
  await page.route('**/api/households/1/authorization/roles', async (route) => {
    const payload = authorizationPayload(getRoleKey())
    await route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({ household_id: '1', items: payload.roles }) })
  })
  await page.route('**/api/households/1/authorization/permissions', async (route) => {
    const payload = authorizationPayload(getRoleKey())
    await route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({ household_id: '1', items: payload.permissions }) })
  })
  await page.route('**/api/households/1/authorization/members/member-lid/role', async (route) => {
    const payload = JSON.parse(route.request().postData() || '{}')
    setRoleKey(payload.role_key)
    await route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({ ok: true, role_key: payload.role_key }) })
  })
}

test.describe('Autorisaties frontend-regressie', () => {
  test('Autorisaties toont een Nederlandse rollenmatrix zonder leden of technische sleutels', async ({ page }) => {
    const consoleErrors = attachConsoleErrorCollector(page)
    let roleKey = 'household.member'
    await seedAdminSession(page)
    await mockAuthorizationApi(page, () => roleKey, (value) => { roleKey = value })

    await page.goto('/instellingen/huishouden/autorisaties')
    await expect(page.getByTestId('authorization-settings-page')).toBeVisible()
    await expect(page.getByRole('heading', { name: 'Autorisaties', exact: true })).toBeVisible()
    await expect(page.getByTestId('authorization-role-matrix')).toBeVisible()
    await expect(page.getByRole('columnheader', { name: 'Kijker' })).toBeVisible()
    await expect(page.getByRole('columnheader', { name: 'Lid' })).toBeVisible()
    await expect(page.getByRole('columnheader', { name: 'Geavanceerd lid' })).toBeVisible()
    await expect(page.getByRole('columnheader', { name: 'Beheerder' })).toBeVisible()
    await expect(page.getByRole('rowheader', { name: 'Voorraad bekijken' })).toBeVisible()
    await expect(page.getByLabel('Voorraad bekijken voor Kijker: toegestaan')).toBeChecked()
    await expect(page.getByLabel('Voorraad wijzigen voor Kijker: niet toegestaan')).not.toBeChecked()
    await expect(page.getByLabel('Voorraad wijzigen voor Lid: toegestaan')).toBeChecked()
    await expect(page.getByText('admin@rezzerv.local')).toHaveCount(0)
    await expect(page.getByText('inventory.view')).toHaveCount(0)
    await expect(page.locator('select')).toHaveCount(0)
    await expectNoConsoleErrors(consoleErrors)
  })

  test('Huishouden beheert leden en rollen en gebruikt overlaymeldingen', async ({ page }) => {
    const consoleErrors = attachConsoleErrorCollector(page)
    await seedAdminSession(page)

    let roleKey = 'household.member'
    let householdName = 'Molenstraat 19 Driel'
    const householdPayload = () => ({
      household_name: householdName,
      member_count: 2,
      is_household_admin: true,
      members: [
        { email: 'admin@rezzerv.local', is_current_user: true, can_remove: false },
        { email: 'lid@rezzerv.local', is_current_user: false, can_remove: true },
      ],
    })

    await mockAuthorizationApi(page, () => roleKey, (value) => { roleKey = value })
    await page.route('**/api/household/members', async (route) => {
      await route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(householdPayload()) })
    })
    await page.route('**/api/household/name', async (route) => {
      const payload = JSON.parse(route.request().postData() || '{}')
      householdName = payload.name
      await route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(householdPayload()) })
    })

    await page.goto('/instellingen/huishouden')
    await expect(page.getByTestId('household-settings-page')).toBeVisible()
    await expect(page.getByText('Rechten voor leden')).toHaveCount(0)
    await expect(page.getByLabel('Rol lid@rezzerv.local')).toHaveValue('household.member')

    await page.getByLabel('Rol lid@rezzerv.local').selectOption('household.advanced_member')
    const roleFeedback = page.getByTestId('app-feedback-success')
    await expect(roleFeedback).toContainText('De rol van lid@rezzerv.local is gewijzigd naar Geavanceerd lid.')
    await roleFeedback.getByRole('button', { name: 'OK' }).click()
    await expect(page.getByLabel('Rol lid@rezzerv.local')).toHaveValue('household.advanced_member')

    await page.getByTestId('household-name-input').fill('Molenstraat 19 Driel bijgewerkt')
    await page.getByTestId('household-name-save').click()
    const nameFeedback = page.getByTestId('app-feedback-success')
    await expect(nameFeedback).toContainText('Huishoudnaam opgeslagen.')
    await nameFeedback.getByRole('button', { name: 'OK' }).click()
    await expect(page.getByTestId('household-name-input')).toHaveValue('Molenstraat 19 Driel bijgewerkt')
    await expectNoConsoleErrors(consoleErrors)
  })
})
