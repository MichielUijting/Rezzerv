import { test, expect } from '@playwright/test'
import { attachConsoleErrorCollector, expectNoConsoleErrors } from './helpers/rezzervAssertions.js'

test.describe('Huishoudleden en autorisaties frontend-regressie', () => {
  test('beheerder wijzigt rol en individuele rechten via de nieuwe API-laag', async ({ page }) => {
    const consoleErrors = attachConsoleErrorCollector(page)
    let roleKey = 'household.member'
    const overrides = new Map()
    let rolePayload = null
    let permissionPayload = null

    await page.addInitScript(() => {
      localStorage.setItem('rezzerv_token', 'rezzerv-dev-token')
      localStorage.setItem('rezzerv_auth_context', JSON.stringify({
        active_household_id: '1',
        display_role: 'admin',
        permissions: {
          'members.manage': true,
          'permissions.manage': true,
        },
      }))
      sessionStorage.setItem('rezzerv_auth_checked_token', 'rezzerv-dev-token')
    })

    await page.route('**/api/households/1/authorization/members', async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          household_id: '1',
          total: 2,
          items: [
            { membership_id: 'member-admin', email: 'admin@rezzerv.local', role_key: 'household.admin', role_name: 'Beheerder', permission_overrides: [], is_current_user: true },
            { membership_id: 'member-lid', email: 'lid@rezzerv.local', role_key: roleKey, role_name: 'Lid', permission_overrides: [...overrides.entries()].map(([permission_key, effect]) => ({ permission_key, effect })) },
          ],
        }),
      })
    })

    await page.route('**/api/households/1/authorization/roles', async (route) => {
      await route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({ household_id: '1', items: [
        { role_key: 'household.viewer', name: 'Viewer' },
        { role_key: 'household.member', name: 'Lid' },
        { role_key: 'household.advanced_member', name: 'Gevorderd lid' },
        { role_key: 'household.admin', name: 'Beheerder' },
      ] }) })
    })

    await page.route('**/api/households/1/authorization/permissions', async (route) => {
      await route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({ household_id: '1', items: [
        { permission_key: 'inventory.update', description: 'Voorraad wijzigen' },
        { permission_key: 'members.view', description: 'Huishoudleden bekijken' },
      ] }) })
    })

    await page.route('**/api/households/1/authorization/members/member-lid/role', async (route) => {
      rolePayload = JSON.parse(route.request().postData() || '{}')
      roleKey = rolePayload.role_key
      await route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({ ok: true, role_key: roleKey }) })
    })

    await page.route('**/api/households/1/authorization/members/member-lid/permissions/inventory.update', async (route) => {
      if (route.request().method() === 'DELETE') {
        overrides.delete('inventory.update')
        await route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({ ok: true, deleted: true }) })
        return
      }
      permissionPayload = JSON.parse(route.request().postData() || '{}')
      overrides.set('inventory.update', permissionPayload.effect)
      await route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({ ok: true, effect: permissionPayload.effect }) })
    })

    await page.goto('/instellingen/huishouden/autorisaties')
    await expect(page.getByTestId('authorization-settings-page')).toBeVisible()
    await expect(page.getByText('lid@rezzerv.local', { exact: true })).toBeVisible()

    await page.getByLabel('Rol lid@rezzerv.local').selectOption('household.advanced_member')
    await expect.poll(() => rolePayload).toEqual({ role_key: 'household.advanced_member' })
    await expect(page.getByText('De rol van lid@rezzerv.local is opgeslagen.')).toBeVisible()

    await page.getByRole('button', { name: 'lid@rezzerv.local', exact: true }).click()
    await page.getByLabel('Recht inventory.update').selectOption('deny')
    await expect.poll(() => permissionPayload).toEqual({ effect: 'deny' })
    await expect(page.getByLabel('Recht inventory.update')).toHaveValue('deny')

    await page.getByLabel('Recht inventory.update').selectOption('')
    await expect(page.getByLabel('Recht inventory.update')).toHaveValue('')
    await expectNoConsoleErrors(consoleErrors)
  })
})
