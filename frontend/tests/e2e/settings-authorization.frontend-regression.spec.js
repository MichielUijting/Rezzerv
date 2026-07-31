import { test, expect } from '@playwright/test'
import { attachConsoleErrorCollector, expectNoConsoleErrors } from './helpers/rezzervAssertions.js'

test.describe('Autorisaties frontend-regressie', () => {
  test('toont alleen Kijker, Lid en Eigenaar', async ({ page }) => {
    const consoleErrors = attachConsoleErrorCollector(page)
    const roles = [
      { role_key: 'huishouden.kijker', name: 'Kijker', permission_keys: ['inventory.view'] },
      { role_key: 'huishouden.lid', name: 'Lid', permission_keys: ['inventory.view', 'inventory.update'] },
      { role_key: 'huishouden.eigenaar', name: 'Eigenaar', permission_keys: ['inventory.view', 'inventory.update', 'inventory.correct', 'permissions.view'] },
    ]
    const permissions = [
      { permission_key: 'inventory.view', description: 'Voorraad bekijken' },
      { permission_key: 'inventory.update', description: 'Voorraad wijzigen' },
      { permission_key: 'inventory.correct', description: 'Voorraad corrigeren' },
      { permission_key: 'permissions.view', description: 'Autorisaties bekijken' },
    ]
    await page.route('**/api/households/*/authorization/members', (route) => route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({ household_id: '1', total: 0, items: [] }) }))
    await page.route('**/api/households/*/authorization/roles', (route) => route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({ household_id: '1', items: roles }) }))
    await page.route('**/api/households/*/authorization/permissions', (route) => route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({ household_id: '1', items: permissions }) }))

    await page.goto('/instellingen/huishouden/autorisaties')
    const matrix = page.getByTestId('authorization-role-matrix')
    await expect(matrix).toBeVisible()
    await expect(page.getByRole('columnheader', { name: 'Kijker', exact: true })).toBeVisible()
    await expect(page.getByRole('columnheader', { name: 'Lid', exact: true })).toBeVisible()
    await expect(page.getByRole('columnheader', { name: 'Eigenaar', exact: true })).toBeVisible()
    await expect(page.getByRole('columnheader', { name: 'Beheerder', exact: true })).toHaveCount(0)
    await expect(page.getByRole('columnheader', { name: 'Geavanceerd lid', exact: true })).toHaveCount(0)
    await expect(page.getByLabel('Voorraad bekijken voor Kijker: toegestaan')).toBeChecked()
    await expect(page.getByLabel('Voorraad wijzigen voor Kijker: niet toegestaan')).not.toBeChecked()
    await expect(page.getByLabel('Voorraad wijzigen voor Lid: toegestaan')).toBeChecked()
    await expect(page.getByTestId('authorization-settings-page').locator('select')).toHaveCount(0)
    await expect(page.getByTestId('authorization-settings-page')).toContainText('minimaal één actieve rol')
    await expectNoConsoleErrors(consoleErrors)
  })
})
