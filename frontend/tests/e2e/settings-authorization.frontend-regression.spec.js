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
        'permissions.manage': true,
      },
    }))
    sessionStorage.setItem('rezzerv_auth_checked_token', 'rezzerv-dev-token')
  })
}

test.describe('Huishoudleden en autorisaties frontend-regressie', () => {
  test('beheerder wijzigt rol en individuele rechten via de nieuwe API-laag', async ({ page }) => {
    const consoleErrors = attachConsoleErrorCollector(page)
    let roleKey = 'household.member'
    const overrides = new Map()
    let rolePayload = null
    let permissionPayload = null

    await seedAdminSession(page)

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
    await expect(page.getByRole('heading', { name: 'Huishoudleden en autorisaties', exact: true })).toBeVisible()
    await expect(page.getByText('Terug naar instellingen')).toHaveCount(0)
    await expect(page.getByText('lid@rezzerv.local', { exact: true })).toBeVisible()

    await page.getByLabel('Rol lid@rezzerv.local').selectOption('household.advanced_member')
    await expect.poll(() => rolePayload).toEqual({ role_key: 'household.advanced_member' })
    const roleFeedback = page.getByTestId('app-feedback-success')
    await expect(roleFeedback).toContainText('De rol van lid@rezzerv.local is opgeslagen.')
    await roleFeedback.getByRole('button', { name: 'OK' }).click()

    await page.getByRole('button', { name: 'lid@rezzerv.local', exact: true }).click()
    await page.getByLabel('Recht inventory.update').selectOption('deny')
    await expect.poll(() => permissionPayload).toEqual({ effect: 'deny' })
    const denyFeedback = page.getByTestId('app-feedback-success')
    await expect(denyFeedback).toContainText('De uitzondering voor inventory · update is opgeslagen.')
    await denyFeedback.getByRole('button', { name: 'OK' }).click()
    await expect(page.getByLabel('Recht inventory.update')).toHaveValue('deny')

    await page.getByLabel('Recht inventory.update').selectOption('')
    const deleteFeedback = page.getByTestId('app-feedback-success')
    await expect(deleteFeedback).toContainText('De uitzondering voor inventory · update is verwijderd.')
    await deleteFeedback.getByRole('button', { name: 'OK' }).click()
    await expect(page.getByLabel('Recht inventory.update')).toHaveValue('')
    await expectNoConsoleErrors(consoleErrors)
  })

  test('Huishouden bevat geen rollen of rechten en gebruikt standaard overlaymeldingen', async ({ page }) => {
    const consoleErrors = attachConsoleErrorCollector(page)
    await seedAdminSession(page)

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
    await expect(page.getByText('Terug naar instellingen')).toHaveCount(0)
    await expect(page.getByText('Rechten voor leden')).toHaveCount(0)
    await expect(page.locator('[data-testid^="household-role-select-"]')).toHaveCount(0)
    await expect(page.getByTestId('household-member-role-select')).toHaveCount(0)
    await expect(page.getByText('Rollen en individuele rechten beheer je uitsluitend via Huishoudleden en autorisaties.')).toBeVisible()

    await page.getByTestId('household-name-input').fill('Molenstraat 19 Driel bijgewerkt')
    await page.getByTestId('household-name-save').click()
    const feedback = page.getByTestId('app-feedback-success')
    await expect(feedback).toContainText('Huishoudnaam opgeslagen.')
    await feedback.getByRole('button', { name: 'OK' }).click()
    await expect(page.getByTestId('household-name-input')).toHaveValue('Molenstraat 19 Driel bijgewerkt')
    await expectNoConsoleErrors(consoleErrors)
  })
})
