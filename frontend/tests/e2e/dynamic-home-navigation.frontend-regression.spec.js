import { test, expect } from '@playwright/test'

function uniqueEmail(prefix = 'dynamic-navigation') {
  return `${prefix}-${Date.now()}-${Math.random().toString(16).slice(2)}@example.com`
}

test('completed Inhuis halen onboarding drives Home prominence while Meer keeps other routes available', async ({ page }) => {
  const email = uniqueEmail()
  const password = 'SterkWachtwoord123!'

  const registration = await page.request.post('/api/auth/register', {
    data: { email, password },
  })
  expect(registration.status()).toBe(201)

  const primaryUseCase = await page.request.post('/api/onboarding/primary-use-case', {
    data: { primary_use_case: 'inhuis_halen' },
  })
  expect(primaryUseCase.ok()).toBeTruthy()

  const profile = await page.request.post('/api/onboarding/inhuis-halen', {
    data: {
      simple_inventory_enabled: true,
      almost_out_notifications_enabled: true,
      receipt_processing_enabled: true,
      recipes_enabled: false,
    },
  })
  expect(profile.ok()).toBeTruthy()

  const completed = await page.request.post('/api/onboarding/shared-household-minimum', {
    data: {
      household_name: 'Dynamische navigatie test',
      household_usage_mode: 'alone',
    },
  })
  expect(completed.ok()).toBeTruthy()
  expect((await completed.json()).product_configuration.shopping_enabled).toBe(true)

  await page.goto('/home')
  await expect(page.getByTestId('dynamic-home-navigation')).toBeVisible()
  await expect(page.getByTestId('legacy-home-navigation')).toHaveCount(0)

  await expect(page.getByTestId('home-tile-bijna-op')).toBeVisible()
  await expect(page.getByTestId('home-tile-winkelen')).toBeVisible()
  await expect(page.getByTestId('home-tile-kassa')).toBeVisible()
  await expect(page.getByTestId('home-tile-voorraad')).toHaveCount(0)

  await page.getByTestId('home-more-toggle').click()
  await expect(page.getByTestId('home-more-navigation')).toBeVisible()
  await expect(page.getByTestId('home-tile-voorraad')).toBeVisible()
  await expect(page.getByTestId('home-tile-prognoses')).toHaveCount(0)
})

test('Waar Inhuis keeps location management inside Settings and never adds a Locations Home tile', async ({ page }) => {
  const email = uniqueEmail('dynamic-navigation-waar-inhuis')
  const password = 'SterkWachtwoord123!'

  const registration = await page.request.post('/api/auth/register', {
    data: { email, password },
  })
  expect(registration.status()).toBe(201)

  const primaryUseCase = await page.request.post('/api/onboarding/primary-use-case', {
    data: { primary_use_case: 'waar_inhuis' },
  })
  expect(primaryUseCase.ok()).toBeTruthy()

  const profile = await page.request.post('/api/onboarding/waar-inhuis', {
    data: {
      unpacking_enabled: true,
      receipt_processing_enabled: true,
      almost_out_enabled: false,
    },
  })
  expect(profile.ok()).toBeTruthy()

  const completed = await page.request.post('/api/onboarding/shared-household-minimum', {
    data: {
      household_name: 'Dynamische navigatie Waar Inhuis',
      household_usage_mode: 'alone',
    },
  })
  expect(completed.ok()).toBeTruthy()
  expect((await completed.json()).product_configuration.location_tracking_level).toBe('exact')

  await page.goto('/home')
  await expect(page.getByTestId('dynamic-home-navigation')).toBeVisible()
  await expect(page.getByTestId('home-tile-locaties')).toHaveCount(0)

  await page.getByTestId('home-more-toggle').click()
  await expect(page.getByTestId('home-more-navigation')).toBeVisible()
  await expect(page.getByTestId('home-tile-locaties')).toHaveCount(0)

  await page.goto('/instellingen')
  await expect(page.getByTestId('settings-tile-locations')).toBeVisible()
})
