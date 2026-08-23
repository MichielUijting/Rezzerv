import { test, expect } from '@playwright/test'

function uniqueEmail() {
  return `circular-expansion-${Date.now()}-${Math.random().toString(16).slice(2)}@example.com`
}

test('Inhuis halen can add Wat Inhuis without rerunning or downgrading existing configuration', async ({ page }) => {
  const email = uniqueEmail()
  const password = 'SterkWachtwoord123!'

  const registration = await page.request.post('/api/auth/register', {
    data: { email, password },
  })
  expect(registration.status()).toBe(201)

  expect((await page.request.post('/api/onboarding/primary-use-case', {
    data: { primary_use_case: 'inhuis_halen' },
  })).ok()).toBeTruthy()

  expect((await page.request.post('/api/onboarding/inhuis-halen', {
    data: {
      simple_inventory_enabled: true,
      almost_out_notifications_enabled: true,
      receipt_processing_enabled: true,
      recipes_enabled: false,
    },
  })).ok()).toBeTruthy()

  expect((await page.request.post('/api/onboarding/shared-household-minimum', {
    data: {
      household_name: 'Circulaire uitbreiding test',
      household_usage_mode: 'alone',
    },
  })).ok()).toBeTruthy()

  const before = await page.request.get('/api/onboarding/capabilities')
  expect(before.ok()).toBeTruthy()
  const beforePayload = await before.json()
  expect(beforePayload.primary_use_case).toBe('inhuis_halen')
  expect(beforePayload.active_use_cases).toEqual(['inhuis_halen'])
  expect(beforePayload.product_configuration.inventory_tracking_level).toBe('quantity')
  expect(beforePayload.product_configuration.shopping_enabled).toBe(true)
  expect(beforePayload.product_configuration.receipt_processing_enabled).toBe(true)

  await page.goto('/instellingen/mogelijkheden')
  await expect(page.getByTestId('settings-capabilities-page')).toBeVisible()
  await expect(page.getByTestId('capability-active-inhuis_halen')).toBeVisible()
  await page.getByTestId('capability-add-wat_inhuis').click()

  await expect(page.getByTestId('capability-expansion-form-wat_inhuis')).toBeVisible()
  await expect(page.getByTestId('capability-wat-global-locations')).toBeVisible()
  await expect(page.getByTestId('capability-wat-inventory-level')).toHaveCount(0)
  await expect(page.getByTestId('capability-wat-almost-out')).toHaveCount(0)
  await expect(page.getByTestId('capability-wat-shopping')).toHaveCount(0)

  await page.getByTestId('capability-wat-global-locations').check()
  await page.getByTestId('capability-expansion-submit').click()
  await expect(page.getByTestId('capability-active-wat_inhuis')).toBeVisible()

  const after = await page.request.get('/api/onboarding/capabilities')
  expect(after.ok()).toBeTruthy()
  const afterPayload = await after.json()
  expect(afterPayload.primary_use_case).toBe('inhuis_halen')
  expect(afterPayload.active_use_cases).toEqual(['inhuis_halen', 'wat_inhuis'])
  expect(afterPayload.product_configuration.inventory_tracking_level).toBe('quantity')
  expect(afterPayload.product_configuration.location_tracking_level).toBe('global')
  expect(afterPayload.product_configuration.shopping_enabled).toBe(true)
  expect(afterPayload.product_configuration.almost_out_enabled).toBe(true)
  expect(afterPayload.product_configuration.almost_out_notifications_enabled).toBe(true)
  expect(afterPayload.product_configuration.receipt_processing_enabled).toBe(true)

  await page.goto('/instellingen')
  await expect(page.getByTestId('settings-tile-capabilities')).toBeVisible()
  await expect(page.getByTestId('settings-tile-locations')).toBeVisible()
})
