import { test, expect } from '@playwright/test'
import {
  attachConsoleErrorCollector,
  expectNoConsoleErrors,
} from './helpers/rezzervAssertions.js'

async function seedSession(page, { contextType = 'regular', isViewer = false } = {}) {
  await page.route('**/api/session', async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        authenticated: true,
        user: { id: 'help-user', email: 'help@example.com' },
        user_id: 'help-user',
        email: 'help@example.com',
        active_household_id: contextType === 'regular' ? 'household-1' : '0',
        active_household_name: contextType === 'regular' ? 'Help huishouden' : 'Systeemhuishouden',
        context_type: contextType,
        role: isViewer ? 'viewer' : 'member',
        display_role: isViewer ? 'viewer' : 'member',
        permissions: {},
        supported_permissions: [],
        is_viewer: isViewer,
        is_platform_superuser: contextType === 'system',
        is_frontteam: false,
      }),
    })
  })
  await page.route('**/api/onboarding', async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({}),
    })
  })
}

test.describe('Hulp & Over frontend-regressie', () => {
  test('regular viewer kan pagina lezen met canonical versie- en bestemmingslinks', async ({ page }) => {
    const consoleErrors = attachConsoleErrorCollector(page)
    await page.addInitScript(() => {
      window.__REZZERV_VERSION__ = { version: '1.12.109-test' }
    })
    await seedSession(page, { contextType: 'regular', isViewer: true })

    await page.goto('/instellingen/hulp-over')

    await expect(page).toHaveURL(/\/instellingen\/hulp-over$/)
    await expect(page.getByTestId('settings-help-about-page')).toBeVisible()
    await expect(page.getByTestId('help-about-version')).toHaveText('Versie 1.12.109-test')
    await expect(page.getByTestId('help-about-support-link')).toHaveAttribute('href', '/meldingen')
    await expect(page.getByTestId('help-about-privacy-link')).toHaveAttribute('href', '/instellingen/privacy-datadeling')
    await expectNoConsoleErrors(consoleErrors)
  })

  test('Settings toont de Hulp & informatie-sectie met persoonlijke Hulp & Over-tegel', async ({ page }) => {
    await seedSession(page)

    await page.goto('/instellingen')

    await expect(page.getByTestId('settings-section-help')).toBeVisible()
    await expect(page.getByTestId('settings-tile-help-about')).toBeVisible()
    await expect(page.getByTestId('settings-tile-help-about')).toHaveAttribute('data-settings-scope', 'personal')
    await page.getByTestId('settings-tile-help-about').click()
    await expect(page).toHaveURL(/\/instellingen\/hulp-over$/)
    await expect(page.getByTestId('settings-help-about-page')).toBeVisible()
  })

  test('system context kan Hulp & Over niet rechtstreeks openen', async ({ page }) => {
    await seedSession(page, { contextType: 'system' })

    await page.goto('/instellingen/hulp-over')

    await expect(page).toHaveURL(/\/home$/)
    await expect(page.getByTestId('settings-help-about-page')).toHaveCount(0)
  })
})
