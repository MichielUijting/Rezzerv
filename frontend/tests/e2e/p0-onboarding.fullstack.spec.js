import { test, expect } from '@playwright/test'

const email = process.env.PLAYWRIGHT_L4_ONBOARDING_EMAIL
const password = process.env.PLAYWRIGHT_L4_ONBOARDING_PASSWORD
const householdName = process.env.PLAYWRIGHT_L4_ONBOARDING_HOUSEHOLD

function required(name, value) {
  if (!String(value || '').trim()) throw new Error(`${name} ontbreekt voor L4-01`)
  return String(value).trim()
}

test('L4-01 register -> Wat Inhuis onboarding -> settings projection -> usable app', async ({ page }) => {
  const accountEmail = required('PLAYWRIGHT_L4_ONBOARDING_EMAIL', email)
  const accountPassword = required('PLAYWRIGHT_L4_ONBOARDING_PASSWORD', password)
  const expectedHouseholdName = required('PLAYWRIGHT_L4_ONBOARDING_HOUSEHOLD', householdName)

  await page.goto('/registreren')
  await expect(page.getByTestId('register-page')).toBeVisible()

  await page.getByTestId('register-email').fill(accountEmail)
  await page.getByTestId('register-password').fill(accountPassword)
  await page.getByTestId('register-password-repeat').fill(accountPassword)

  const registrationResponsePromise = page.waitForResponse((response) => (
    response.url().includes('/api/auth/register')
    && response.request().method() === 'POST'
  ))
  await page.getByTestId('register-submit').click()
  const registrationResponse = await registrationResponsePromise
  expect(registrationResponse.status()).toBe(201)

  await expect(page.getByTestId('onboarding-use-case-page')).toBeVisible()
  await page.getByTestId('onboarding-choice-wat_inhuis').check()

  const primaryUseCaseResponsePromise = page.waitForResponse((response) => (
    response.url().includes('/api/onboarding/primary-use-case')
    && response.request().method() === 'POST'
  ))
  await page.getByTestId('onboarding-primary-continue').click()
  const primaryUseCaseResponse = await primaryUseCaseResponsePromise
  expect(primaryUseCaseResponse.ok()).toBeTruthy()

  await expect(page.getByTestId('onboarding-wat-inhuis-follow-up')).toBeVisible()
  await page.getByTestId('wat-inhuis-tracking-quantity').check()
  await page.getByTestId('wat-inhuis-global-locations-no').check()
  await page.getByTestId('wat-inhuis-almost-out-yes').check()
  await page.getByTestId('wat-inhuis-shopping-yes').check()

  const watInhuisResponsePromise = page.waitForResponse((response) => (
    response.url().includes('/api/onboarding/wat-inhuis')
    && response.request().method() === 'POST'
  ))
  await page.getByTestId('wat-inhuis-finish').click()
  const watInhuisResponse = await watInhuisResponsePromise
  expect(watInhuisResponse.ok()).toBeTruthy()

  await expect(page.getByTestId('onboarding-shared-household-minimum')).toBeVisible()
  await page.getByTestId('shared-household-name').fill(expectedHouseholdName)
  await page.getByTestId('shared-household-usage-alone').check()

  const householdResponsePromise = page.waitForResponse((response) => (
    response.url().includes('/api/onboarding/shared-household-minimum')
    && response.request().method() === 'POST'
  ))
  await page.getByTestId('shared-household-finish').click()
  const householdResponse = await householdResponsePromise
  expect(householdResponse.ok()).toBeTruthy()

  await expect(page).toHaveURL(/\/home$/)
  await expect(page.getByTestId('dynamic-home-navigation')).toBeVisible()
  await expect(page.getByTestId('home-tile-voorraad')).toBeVisible()
  await expect(page.getByTestId('home-tile-bijna-op')).toBeVisible()
  await expect(page.getByTestId('home-tile-winkelen')).toBeVisible()
  await expect(page.getByTestId('home-tile-locaties')).toHaveCount(0)

  await page.goto('/instellingen')
  await expect(page.getByTestId('settings-page')).toHaveAttribute('data-settings-mode', 'dynamic')
  await expect(page.getByTestId('settings-active-profile')).toContainText('Wat Inhuis')
  await expect(page.getByTestId('settings-active-profile')).toContainText('Voorraad met aantallen')
  await expect(page.getByTestId('settings-active-profile')).toContainText('Bijna op')
  await expect(page.getByTestId('settings-active-profile')).toContainText('Winkelen')
  await expect(page.getByTestId('settings-tile-locations')).toHaveCount(0)

  const capabilitiesResponse = await page.request.get('/api/onboarding/capabilities')
  expect(capabilitiesResponse.ok()).toBeTruthy()
  const capabilities = await capabilitiesResponse.json()
  expect(capabilities.primary_use_case).toBe('wat_inhuis')
  expect(capabilities.active_use_cases).toEqual(['wat_inhuis'])
  expect(capabilities.onboarding_status).toBe('completed')
  expect(capabilities.household_name).toBe(expectedHouseholdName)
  expect(capabilities.product_configuration.inventory_tracking_level).toBe('quantity')
  expect(capabilities.product_configuration.location_tracking_level).toBe('none')
  expect(capabilities.product_configuration.almost_out_enabled).toBe(true)
  expect(capabilities.product_configuration.shopping_enabled).toBe(true)

  const sessionResponse = await page.request.get('/api/session')
  expect(sessionResponse.ok()).toBeTruthy()
  const session = await sessionResponse.json()
  expect(session.email).toBe(accountEmail.toLowerCase())
  expect(session.context_type).toBe('regular')
  expect(session.role).toBe('admin')

  console.log('P0_L4_01_ONBOARDING_BROWSER_GREEN')
})
