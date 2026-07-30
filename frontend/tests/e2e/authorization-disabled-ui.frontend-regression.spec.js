import { test, expect } from '@playwright/test'
import { attachConsoleErrorCollector, expectNoConsoleErrors } from './helpers/rezzervAssertions.js'

const MESSAGE = 'Alleen de beheerder is geautoriseerd voor deze functie.'

async function seedSession(page, permissions = {}) {
  await page.addInitScript(({ grantedPermissions }) => {
    localStorage.setItem('rezzerv_token', 'rezzerv-dev-token')
    localStorage.setItem('rezzerv_auth_context', JSON.stringify({
      active_household_id: '1',
      active_household_name: 'Testhuishouden',
      display_role: 'member',
      permissions: grantedPermissions,
    }))
    sessionStorage.setItem('rezzerv_auth_checked_token', 'rezzerv-dev-token')
  }, { grantedPermissions: permissions })
}

test.describe('Autorisatiegestuurde disabled-state', () => {
  test('niet-geautoriseerde tegel blijft zichtbaar, blokkeert navigatie en toont uitleg', async ({ page }) => {
    const consoleErrors = attachConsoleErrorCollector(page)
    await seedSession(page, { 'permissions.view': true })

    await page.goto('/instellingen')
    await expect(page.getByTestId('settings-page')).toBeVisible()

    const wrapper = page.locator('[data-authorization-message]').filter({ hasText: 'Artikelgroepen' })
    const tile = wrapper.getByText('Artikelgroepen', { exact: true })

    await expect(tile).toBeVisible()
    await expect(wrapper).toHaveAttribute('aria-label', MESSAGE)

    await wrapper.hover()
    await expect(wrapper.getByRole('tooltip')).toBeVisible()
    await expect(wrapper.getByRole('tooltip')).toHaveText(MESSAGE)

    await wrapper.focus()
    await expect(wrapper.getByRole('tooltip')).toBeVisible()

    await wrapper.locator('a').click({ force: true })
    await expect(page).toHaveURL(/\/instellingen$/)
    await expectNoConsoleErrors(consoleErrors)
  })

  test('toegekende autorisatie laat normale navigatie toe', async ({ page }) => {
    const consoleErrors = attachConsoleErrorCollector(page)
    await seedSession(page, {
      'article_groups.manage': true,
      'permissions.view': true,
    })

    await page.goto('/instellingen')
    const tile = page.getByText('Artikelgroepen', { exact: true })
    await expect(tile).toBeVisible()
    await expect(tile.locator('xpath=ancestor::a')).not.toHaveAttribute('aria-disabled', 'true')

    await tile.click()
    await expect(page).toHaveURL(/\/instellingen\/artikelgroepen$/)
    await expectNoConsoleErrors(consoleErrors)
  })
})
