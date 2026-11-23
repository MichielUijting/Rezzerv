import { test, expect } from '@playwright/test'

const email = process.env.PLAYWRIGHT_L4_ONBOARDING_EMAIL
const password = process.env.PLAYWRIGHT_L4_ONBOARDING_PASSWORD
const householdName = process.env.PLAYWRIGHT_L4_ONBOARDING_HOUSEHOLD

function required(name, value) {
  if (!String(value || '').trim()) throw new Error(`${name} ontbreekt voor L4-01`)
  return String(value).trim()
}

test('L4-01 one-screen registration -> Wat Inhuis defaults -> stores -> usable app', async ({ page }) => {
  const accountEmail = required('PLAYWRIGHT_L4_ONBOARDING_EMAIL', email)
  const accountPassword = required('PLAYWRIGHT_L4_ONBOARDING_PASSWORD', password)
  const expectedHouseholdName = required('PLAYWRIGHT_L4_ONBOARDING_HOUSEHOLD', householdName)

  await page.goto('/registreren')
  await expect(page.getByTestId('register-page')).toBeVisible()
  await expect(page.getByTestId('register-quick-start-defaults')).toContainText('Wat Inhuis · Aantallen · Alleen')
  await expect(page.getByTestId('register-password-repeat')).toHaveCount(0)
  await expect(page.getByTestId('register-household-name')).toHaveValue('Mijn huishouden')

  // The user enters only account credentials and optionally changes the household name.
  // Inhuis does not navigate through separate onboarding forms or reload the document.
  await page.evaluate(() => { window.__l4RegistrationDocumentMarker = 'single-page-registration' })
  const followUpPosts = []
  page.on('request', (request) => {
    if (request.method() === 'POST' && /\/api\/onboarding\//.test(request.url())) {
      followUpPosts.push(request.url())
    }
  })
  await page.getByTestId('register-email').fill(accountEmail)
  await page.getByTestId('register-password').fill(accountPassword)
  await page.getByTestId('register-household-name').fill(expectedHouseholdName)

  const registrationResponsePromise = page.waitForResponse((response) => (
    response.url().includes('/api/auth/register')
    && response.request().method() === 'POST'
  ))
  await page.getByTestId('register-submit').click()
  const registrationResponse = await registrationResponsePromise
  expect(registrationResponse.status()).toBe(201)
  const registration = await registrationResponse.json()
  expect(registration.onboarding?.onboarding_status).toBe('completed')
  expect(registration.onboarding?.primary_use_case).toBe('wat_inhuis')
  expect(registration.onboarding?.household_usage_mode).toBe('alone')
  expect(registration.onboarding?.household_name).toBe(expectedHouseholdName)
  expect(registration.onboarding?.product_configuration?.inventory_tracking_level).toBe('quantity')
  expect(registration.onboarding?.product_configuration?.receipt_processing_enabled).toBe(true)
  await expect(page).toHaveURL(/\/onboarding\/winkels$/)
  expect(await page.evaluate(() => window.__l4RegistrationDocumentMarker)).toBe('single-page-registration')
  expect(followUpPosts).toEqual([])

  const onboardingResponse = await page.request.get('/api/onboarding')
  expect(onboardingResponse.ok()).toBeTruthy()
  const initial = await onboardingResponse.json()
  expect(initial.onboarding_status).toBe('completed')
  expect(initial.household_usage_mode).toBe('alone')

  // Receipt-enabled households can connect stores before opening Home.
  await expect(page).toHaveURL(/\/onboarding\/winkels$/)
  await expect(page.getByTestId('onboarding-stores-step')).toBeVisible()
  for (const retailer of ['ah', 'jumbo', 'lidl']) {
    await expect(page.getByTestId('receipt-connection-action-' + retailer)).toBeVisible()
  }
  await expect(page.getByTestId('receipt-connection-action-aldi')).toHaveCount(0)

  // PR5: new household history is read-only and scoped to the active session.
  // Validate the real PostgreSQL summary before allowing the user to leave.
  await expect(page.getByTestId('historical-import-progress')).toBeVisible()
  const historyResponse = await page.request.get('/api/receipts/retailers/history-progress')
  expect(historyResponse.ok()).toBeTruthy()
  const history = await historyResponse.json()
  expect(history.history_cutover_enabled).toBe(true)
  expect(history.complete_retailer_history_known).toBe(false)
  expect(history.providers.map(row => row.code)).toEqual(['ah', 'lidl', 'jumbo'])
  for (const row of history.providers) {
    expect(row.kassa_receipts).toBe(0)
    expect(row.historical_receipts).toBe(0)
    expect(row.queue_pending).toBe(0)
    expect(row.queue_processing).toBe(0)
  }
  await page.getByTestId('historical-import-refresh').click()
  await expect(page.getByTestId('historical-import-stores')).toBeVisible()
  await page.getByTestId('onboarding-stores-later').click()

  // Skipping store setup preserves the completed household and existing Home flow.
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
