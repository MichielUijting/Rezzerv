import { test, expect } from '@playwright/test'

const SUPERUSER_EMAIL = process.env.PLAYWRIGHT_SUPERUSER_EMAIL || 'supergebruiker@rezzerv.local'
const SUPERUSER_PASSWORD = process.env.PLAYWRIGHT_SUPERUSER_PASSWORD

async function loginAsSuperuser(page) {
  if (!SUPERUSER_PASSWORD) throw new Error('PLAYWRIGHT_SUPERUSER_PASSWORD ontbreekt.')
  await page.context().clearCookies()
  await page.goto('/login')
  await page.getByLabel('E-mail').fill(SUPERUSER_EMAIL)
  await page.getByLabel('Wachtwoord').fill(SUPERUSER_PASSWORD)
  await page.getByRole('button', { name: 'Inloggen' }).click()
  await page.waitForURL((url) => url.pathname !== '/login')
  await page.goto('/home')
  await expect(page).toHaveURL(/\/home$/)
}

test.describe('Meldingen frontend-regressie', () => {
  test('gewone gebruiker houdt Meldingen op de landingspagina en blijft buiten Superuser', async ({ page }) => {
    await page.goto('/home')

    const navigation = page.getByRole('navigation', { name: 'Acties' })
    await expect(navigation.getByText('Meldingen', { exact: true })).toBeVisible()
    await expect(navigation.getByText('Superuser', { exact: true })).toHaveCount(0)

    await navigation.getByText('Meldingen', { exact: true }).click()
    await expect(page).toHaveURL(/\/meldingen$/)
    await expect(page.getByText('Meldingen', { exact: true }).first()).toBeVisible()

    await page.goto('/superuser')
    await expect(page).toHaveURL(/\/home$/)
  })

  test('platform-superuser gebruikt Meldingen via Beheercentrum en niet via de landingspagina', async ({ page }) => {
    await loginAsSuperuser(page)

    const navigation = page.getByRole('navigation', { name: 'Acties' })
    await expect(navigation.getByText('Meldingen', { exact: true })).toHaveCount(0)
    await expect(navigation.getByText('Superuser', { exact: true })).toBeVisible()

    await navigation.getByText('Superuser', { exact: true }).click()
    await expect(page).toHaveURL(/\/superuser$/)
    await expect(page.getByTestId('superuser-platform-overview')).toBeVisible()

    const meldingenButton = page.getByRole('button', { name: /Meldingen \(\d+\)/ })
    await expect(meldingenButton).toBeVisible()
    await meldingenButton.click()

    await expect(page).toHaveURL(/\/superuser\/meldingen$/)
    await expect(page.getByTestId('platform-support-page')).toBeVisible()
    await expect(page.getByRole('combobox', { name: 'Filter op status' })).toHaveValue('Open')
    await expect(page.getByText('Alle meldingen', { exact: true })).toBeVisible()
    await expect(page.getByTestId('platform-support-broadcast-form')).toBeVisible()
  })
})
