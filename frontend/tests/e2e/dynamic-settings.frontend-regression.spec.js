import { test, expect } from '@playwright/test'

function uniqueEmail(prefix) {
  return `${prefix}-${Date.now()}-${Math.random().toString(16).slice(2)}@example.com`
}

async function registerAndComplete(page, { prefix, useCase, profile, householdName }) {
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
  await expect(page.getByTestId('settings-section-help')).toHaveCount(0)

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
  await expect(page.getByTestId('settings-tile-locations')).toHaveCount(0)
})

test('Wat Inhuis global settings expose main locations without sublocation controls', async ({ page }) => {
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
  await expect(page.getByTestId('settings-tile-locations')).toBeVisible()
  await expect(page.getByTestId('settings-tile-store-import')).toHaveCount(0)
  await expect(page.getByTestId('settings-tile-almost-out')).toHaveCount(0)
  await expect(page.getByTestId('settings-tile-household-automation')).toBeVisible()

  await page.getByTestId('settings-tile-locations').click()
  await expect(page).toHaveURL(/\/instellingen\/locaties$/)
  await expect(page.getByTestId('settings-global-locations-page')).toBeVisible()
  await expect(page.getByTestId('settings-locations-page')).toHaveCount(0)
  await expect(page.getByRole('button', { name: 'Toevoegen sublocatie' })).toHaveCount(0)

  await page.getByTestId('global-location-name-input').fill('Woning')
  await page.getByTestId('global-location-add').click()
  await expect(page.getByDisplayValue('Woning')).toBeVisible()
})