import { test, expect } from '@playwright/test'

function uniqueEmail(prefix) {
  return `${prefix}-${Date.now()}-${Math.random().toString(16).slice(2)}@example.com`
}

async function registerAndComplete(page, { prefix, useCase, profile, householdName }) {
  // The canonical full-regression project starts each test with the shared system
  // fixture cookie. Drop it only from this fresh browser context so these tests
  // can create their own regular consumer account without revoking the shared
  // server session used by the rest of the regression suite.
  await page.context().clearCookies()

  const registration = await page.request.post('/api/auth/register', {
    data: {
      email: uniqueEmail(prefix),
      password: 'SterkWachtwoord123!',
    },
  })
  expect(registration.status()).toBe(201)

  const selected = await page.request.post('/api/onboarding/primary-use-case', {
    data: { primary_use_case: useCase },
  })
  expect(selected.ok()).toBeTruthy()

  const configured = await page.request.post(`/api/onboarding/${useCase.replaceAll('_', '-')}`, {
    data: profile,
  })
  expect(configured.ok()).toBeTruthy()

  const completed = await page.request.post('/api/onboarding/shared-household-minimum', {
    data: {
      household_name: householdName,
      household_usage_mode: 'alone',
    },
  })
  expect(completed.ok()).toBeTruthy()
  return completed.json()
}

test('system context cannot enter consumer Settings', async ({ page }) => {
  const session = await page.request.get('/api/session')
  expect(session.ok()).toBeTruthy()
  expect((await session.json()).context_type).toBe('system')

  await page.goto('/instellingen')
  await expect(page).toHaveURL(/\/home$/)
  await expect(page.getByTestId('settings-page')).toHaveCount(0)
})

test('Inhuis halen shows grouped product-relevant settings while keeping general household settings', async ({ page }) => {
  await registerAndComplete(page, {
    prefix: 'dynamic-settings-inhuis-halen',
    useCase: 'inhuis_halen',
    householdName: 'Dynamische instellingen Inhuis halen',
    profile: {
      simple_inventory_enabled: true,
      almost_out_notifications_enabled: true,
      receipt_processing_enabled: true,
      recipes_enabled: false,
    },
  })

  await page.goto('/instellingen')
  await expect(page.getByTestId('settings-page')).toHaveAttribute('data-settings-mode', 'dynamic')

  await expect(page.getByTestId('settings-section-account')).toBeVisible()
  await expect(page.getByTestId('settings-section-household')).toBeVisible()
  await expect(page.getByTestId('settings-section-usage')).toBeVisible()
  await expect(page.getByTestId('settings-section-help')).toBeVisible()

  await expect(page.getByTestId('settings-tile-account')).toBeVisible()
  await expect(page.getByTestId('settings-tile-account')).toHaveAttribute('data-settings-scope', 'personal')
  await expect(page.getByTestId('settings-tile-article-details')).toBeVisible()
  await expect(page.getByTestId('settings-tile-article-details')).toHaveAttribute('data-settings-scope', 'personal')
  await expect(page.getByTestId('settings-tile-article-groups')).toBeVisible()
  await expect(page.getByTestId('settings-tile-privacy-data-sharing')).toBeVisible()
  await expect(page.getByTestId('settings-tile-store-import')).toBeVisible()
  await expect(page.getByTestId('settings-tile-household')).toBeVisible()
  await expect(page.getByTestId('settings-tile-household')).toHaveAttribute('data-settings-scope', 'household')
  await expect(page.getByTestId('settings-tile-authorizations')).toBeVisible()
  await expect(page.getByTestId('settings-tile-household-automation')).toBeVisible()
  await expect(page.getByTestId('settings-tile-almost-out')).toBeVisible()
  await expect(page.getByTestId('settings-tile-help-about')).toBeVisible()
  await expect(page.getByTestId('settings-tile-help-about')).toHaveAttribute('data-settings-scope', 'personal')
  await expect(page.getByTestId('settings-tile-locations')).toHaveCount(0)
})

test('Wat Inhuis global settings use the standard locations table without sublocation controls', async ({ page }) => {
  await registerAndComplete(page, {
    prefix: 'dynamic-settings-wat-inhuis',
    useCase: 'wat_inhuis',
    householdName: 'Dynamische instellingen Wat Inhuis',
    profile: {
      inventory_tracking_level: 'quantity',
      global_locations_enabled: true,
      almost_out_enabled: false,
      shopping_enabled: false,
    },
  })

  await page.goto('/instellingen')
  await expect(page.getByTestId('settings-page')).toHaveAttribute('data-settings-mode', 'dynamic')
  await expect(page.getByTestId('settings-active-profile')).toContainText('Kassabonnen')
  await expect(page.getByTestId('settings-tile-account')).toBeVisible()
  await expect(page.getByTestId('settings-tile-help-about')).toBeVisible()
  await expect(page.getByTestId('settings-tile-locations')).toBeVisible()
  // Wat Inhuis keeps Kassa/receipt processing canonical active even with shopping off,
  // so the shopping-or-receipts Winkelimport setting remains relevant.
  await expect(page.getByTestId('settings-tile-store-import')).toBeVisible()
  await expect(page.getByTestId('settings-tile-almost-out')).toHaveCount(0)
  await expect(page.getByTestId('settings-tile-household-automation')).toBeVisible()

  await page.getByTestId('settings-tile-locations').click()
  await expect(page).toHaveURL(/\/instellingen\/locaties$/)
  await expect(page.getByTestId('settings-global-locations-page')).toBeVisible()
  await expect(page.getByTestId('settings-locations-page')).toHaveCount(0)
  await expect(page.getByRole('button', { name: 'Toevoegen sublocatie' })).toHaveCount(0)

  const table = page.getByTestId('settings-global-locations-table')
  await expect(table).toBeVisible()
  expect(await table.evaluate((element) => element.style.tableLayout)).toBe('fixed')
  expect(await table.locator('col').nth(0).evaluate((element) => element.style.width)).toBe('420px')
  expect(await table.locator('col').nth(1).evaluate((element) => element.style.width)).toBe('140px')

  await page.getByTestId('global-location-name-input').fill('Woning')
  await page.getByTestId('global-location-add').click()
  await expect(page.getByLabel('Locatienaam Woning')).toBeVisible()
})

test('Waar Inhuis exact locations keep the full location and sublocation management flow working', async ({ page }) => {
  await registerAndComplete(page, {
    prefix: 'dynamic-settings-waar-inhuis',
    useCase: 'waar_inhuis',
    householdName: 'Dynamische instellingen Waar Inhuis',
    profile: {
      main_locations: ['Keuken'],
      sublocations: [],
      unpacking_enabled: true,
      receipt_processing_enabled: true,
      almost_out_enabled: false,
    },
  })

  await page.goto('/instellingen')
  await expect(page.getByTestId('settings-page')).toHaveAttribute('data-settings-mode', 'dynamic')
  await expect(page.getByTestId('settings-tile-locations')).toBeVisible()

  await page.getByTestId('settings-tile-locations').click()
  await expect(page).toHaveURL(/\/instellingen\/locaties$/)
  await expect(page.getByTestId('settings-locations-page')).toBeVisible()
  await expect(page.getByTestId('settings-global-locations-page')).toHaveCount(0)

  await page.getByRole('button', { name: 'Toevoegen locatie' }).click()
  const locationDialog = page.getByRole('dialog', { name: 'Nieuwe locatie' })
  await locationDialog.getByLabel('Locatie naam').fill('Woning exact')
  await locationDialog.getByRole('button', { name: 'Opslaan' }).click()

  const locationConfirmation = page.getByRole('dialog', { name: 'Bevestiging' })
  await expect(locationConfirmation).toBeVisible()
  await locationConfirmation.getByRole('button', { name: 'OK' }).click()
  await expect(page.getByLabel('Locatienaam Woning exact')).toBeVisible()

  const addSublocation = page.getByRole('button', { name: 'Toevoegen sublocatie' })
  await expect(addSublocation).toBeEnabled()
  await addSublocation.click()

  const sublocationDialog = page.getByRole('dialog', { name: 'Nieuwe sublocatie' })
  await sublocationDialog.getByLabel('Locatie').selectOption({ label: 'Woning exact' })
  await sublocationDialog.getByLabel('Sublocatie naam').fill('Kast 1')
  await sublocationDialog.getByRole('button', { name: 'Opslaan' }).click()

  const sublocationConfirmation = page.getByRole('dialog', { name: 'Bevestiging' })
  await expect(sublocationConfirmation).toBeVisible()
  await sublocationConfirmation.getByRole('button', { name: 'OK' }).click()
  await expect(page.getByLabel('Sublocatienaam Kast 1')).toBeVisible()
})