import { expect, test } from '@playwright/test'


test.describe('password recovery', () => {
  test('login exposes enumeration-safe forgot-password flow', async ({ page }) => {
    let requestBody = null
    await page.route('**/api/auth/password-reset/request', async (route) => {
      requestBody = route.request().postDataJSON()
      await route.fulfill({
        status: 202,
        contentType: 'application/json',
        body: JSON.stringify({
          message: 'Als dit e-mailadres bij ons bekend is, ontvang je een e-mail waarmee je je wachtwoord opnieuw kunt instellen.',
        }),
      })
    })

    await page.goto('/login')
    await page.getByTestId('forgot-password-link').click()
    await expect(page).toHaveURL(/\/wachtwoord-vergeten$/)
    await page.getByTestId('forgot-password-email').fill('iemand@example.com')
    await page.getByTestId('forgot-password-submit').click()

    expect(requestBody).toEqual({ email: 'iemand@example.com' })
    await expect(page.getByTestId('forgot-password-message')).toContainText(
      'Als dit e-mailadres bij ons bekend is',
    )
  })

  test('reset secret is stripped from URL and only submitted on confirm', async ({ page }) => {
    const rawToken = 'test-only-secret-reset-token'
    let confirmBody = null
    await page.route('**/api/auth/password-reset/confirm', async (route) => {
      confirmBody = route.request().postDataJSON()
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          message: 'Je wachtwoord is gewijzigd. Alle bestaande sessies zijn beëindigd. Log opnieuw in met je nieuwe wachtwoord.',
        }),
      })
    })

    await page.goto(`/wachtwoord-herstellen#token=${encodeURIComponent(rawToken)}`)
    await expect(page).toHaveURL(/\/wachtwoord-herstellen$/)
    expect(page.url()).not.toContain(rawToken)

    const browserStorage = await page.evaluate(() => ({
      local: { ...localStorage },
      session: { ...sessionStorage },
    }))
    expect(JSON.stringify(browserStorage)).not.toContain(rawToken)

    await page.getByTestId('reset-password-new').fill('NieuwSterkWachtwoord456!')
    await page.getByTestId('reset-password-repeat').fill('NieuwSterkWachtwoord456!')
    await page.getByTestId('reset-password-submit').click()

    expect(confirmBody).toEqual({
      token: rawToken,
      new_password: 'NieuwSterkWachtwoord456!',
    })
    await expect(page.getByTestId('reset-password-success')).toContainText(
      'Alle bestaande sessies zijn beëindigd',
    )
    await expect(page.getByTestId('reset-password-login-link')).toBeVisible()
  })
})
