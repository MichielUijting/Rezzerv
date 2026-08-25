import { test, expect } from '@playwright/test'
import {
  attachConsoleErrorCollector,
  expectNoConsoleErrors,
} from './helpers/rezzervAssertions.js'

async function seedRegularAccountSession(page) {
  await page.route('**/api/session', async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        authenticated: true,
        user: { id: 'account-user', email: 'account@example.com' },
        user_id: 'account-user',
        email: 'account@example.com',
        active_household_id: 'household-1',
        active_household_name: 'Account huishouden',
        context_type: 'regular',
        role: 'member',
        display_role: 'member',
        permissions: {},
        supported_permissions: [],
        is_viewer: false,
        is_platform_superuser: false,
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

test.describe('Mijn account frontend-regressie', () => {
  test('regular gebruiker ziet eigen e-mail en kan wachtwoord wijzigen', async ({ page }) => {
    const consoleErrors = attachConsoleErrorCollector(page)
    await seedRegularAccountSession(page)
    let changePayload = null

    await page.route('**/api/account/password', async (route) => {
      changePayload = await route.request().postDataJSON()
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          password_updated: true,
          other_active_sessions_revoked: 2,
          message: 'Wachtwoord gewijzigd. Andere actieve sessies zijn ingetrokken.',
          context_type: 'regular',
        }),
      })
    })

    await page.goto('/instellingen/mijn-account')
    await expect(page).toHaveURL(/\/instellingen\/mijn-account$/)
    await expect(page.getByTestId('settings-my-account-page')).toBeVisible()
    await expect(page.getByTestId('my-account-email')).toHaveValue('account@example.com')
    await expect(page.getByTestId('my-account-email')).toHaveAttribute('readonly', '')

    await page.getByTestId('my-account-current-password').fill('HuidigWachtwoord123!')
    await page.getByTestId('my-account-new-password').fill('NieuwWachtwoord456!')
    await page.getByTestId('my-account-new-password-repeat').fill('NieuwWachtwoord456!')
    await page.getByTestId('my-account-password-submit').click()

    await expect.poll(() => changePayload).toEqual({
      current_password: 'HuidigWachtwoord123!',
      new_password: 'NieuwWachtwoord456!',
    })
    await expect(page.getByTestId('my-account-success')).toContainText('Wachtwoord gewijzigd')
    await expect(page.getByTestId('my-account-current-password')).toHaveValue('')
    await expect(page.getByTestId('my-account-new-password')).toHaveValue('')
    await expect(page.getByTestId('my-account-new-password-repeat')).toHaveValue('')
    await expectNoConsoleErrors(consoleErrors)
  })

  test('client validatie voorkomt mismatch en backendfout blijft zichtbaar', async ({ page }) => {
    const consoleErrors = attachConsoleErrorCollector(page)
    await seedRegularAccountSession(page)
    let apiCalls = 0

    await page.route('**/api/account/password', async (route) => {
      apiCalls += 1
      await route.fulfill({
        status: 400,
        contentType: 'application/json',
        body: JSON.stringify({ detail: 'Huidig wachtwoord is onjuist' }),
      })
    })

    await page.goto('/instellingen/mijn-account')
    await page.getByTestId('my-account-current-password').fill('VerkeerdWachtwoord123!')
    await page.getByTestId('my-account-new-password').fill('NieuwWachtwoord456!')
    await page.getByTestId('my-account-new-password-repeat').fill('AnderWachtwoord789!')
    await page.getByTestId('my-account-password-submit').click()

    await expect(page.getByTestId('my-account-error')).toHaveText('De nieuwe wachtwoorden zijn niet gelijk.')
    expect(apiCalls).toBe(0)

    await page.getByTestId('my-account-new-password-repeat').fill('NieuwWachtwoord456!')
    await page.getByTestId('my-account-password-submit').click()
    await expect.poll(() => apiCalls).toBe(1)
    await expect(page.getByTestId('my-account-error')).toHaveText('Huidig wachtwoord is onjuist')

    const unexpectedConsoleErrors = consoleErrors.filter((entry) => !(
      entry.includes('400 (Bad Request)')
      && entry.includes('/api/account/password')
    ))
    await expectNoConsoleErrors(unexpectedConsoleErrors)
  })
})
