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

  // The new, separate choice screen keeps an independently persisted decision
  // for each available retailer; it does not reuse the settings overview.
  await expect(page).toHaveURL(/\/onboarding\/winkels$/)
  await expect(page.getByTestId('store-onboarding-selection')).toBeVisible()
  await expect(page.getByTestId('receipt-connections-overview-table')).toHaveCount(0)
  await expect(page.getByTestId('onboarding-store-arrow')).toHaveCount(0)
  for (const retailer of ['ah', 'jumbo', 'lidl']) {
    await expect(page.getByTestId('onboarding-select-' + retailer)).toBeVisible()
    await expect(page.getByTestId('onboarding-store-row-' + retailer)).toHaveAttribute('data-result', 'neutral')
  }
  for (const [code, mark] of [['ah', 'ah'], ['jumbo', 'J'], ['lidl', 'L']]) {
    await expect(page.getByTestId('onboarding-store-mark-' + code)).toHaveText(mark)
  }
  for (const width of [390, 320, 1280]) {
    await page.setViewportSize({ width, height: 844 })
    const selection = page.getByTestId('store-onboarding-selection')
    for (const header of await selection.locator('thead th').all()) {
      await expect(header).toHaveCSS('color', 'rgb(255, 255, 255)')
    }
    const table = await selection.locator('table').boundingBox()
    expect(table.x + table.width).toBeLessThanOrEqual(width + 1)
    const later = await page.getByTestId('onboarding-stores-later').boundingBox()
    expect(later.x + later.width).toBeLessThanOrEqual(width + 1)
  }
  // Checkbox clicks never persist or refresh; several shops can be picked
  // immediately, then adjusted locally before one explicit confirmation.
  const selectionWrites = []
  page.on('request', request => {
    if (request.url().includes('/api/onboarding/stores/selection') && request.method() === 'PUT') {
      selectionWrites.push(JSON.parse(request.postData()))
    }
  })
  await page.evaluate(() => { window.__inhuisSelectionPageMarker = 'same-document' })
  for (const code of ['ah', 'jumbo', 'lidl']) {
    await page.getByTestId('onboarding-store-row-' + code).locator('label').click()
    await expect(page.getByTestId('onboarding-select-' + code)).toBeChecked()
    expect(await page.evaluate(() => window.__inhuisSelectionPageMarker)).toBe('same-document')
  }
  expect(selectionWrites).toEqual([])
  expect(await page.evaluate(() => window.__inhuisSelectionPageMarker)).toBe('same-document')
  let selectionResponse = await page.request.get('/api/onboarding/stores')
  expect(selectionResponse.status()).toBe(200)
  expect(await selectionResponse.json()).toMatchObject({
    available: true, selected: [], results: {},
  })
  for (const code of ['ah', 'jumbo']) {
    await page.getByTestId('onboarding-store-row-' + code).locator('label').click()
    await expect(page.getByTestId('onboarding-select-' + code)).not.toBeChecked()
  }
  await expect(page.getByTestId('onboarding-select-lidl')).toBeChecked()
  expect(selectionWrites).toEqual([])

  // Use the real server: no request interception in this full-stack authority.
  const savedSelection = page.waitForResponse(response =>
    new URL(response.url()).pathname === '/api/onboarding/stores/selection' &&
    response.request().method() === 'PUT')
  await page.getByTestId('onboarding-stores-start').click()
  const savedResponse = await savedSelection
  expect(savedResponse.ok()).toBeTruthy()
  expect(selectionWrites).toEqual([{ selected: ['lidl'] }])
  await expect(page.getByTestId('lidl-digital-receipts')).toBeVisible()
  expect(await page.evaluate(() => window.__inhuisSelectionPageMarker)).toBe('same-document')
  selectionResponse = await page.request.get('/api/onboarding/stores')
  expect(selectionResponse.status()).toBe(200)
  expect(await selectionResponse.json()).toMatchObject({
    available: true, selected: ['lidl'], results: {},
  })
  await page.reload()
  await expect(page.getByTestId('onboarding-select-ah')).not.toBeChecked()
  await expect(page.getByTestId('onboarding-select-lidl')).toBeChecked()
  await expect(page.getByTestId('onboarding-select-jumbo')).not.toBeChecked()

  // Historical receipt counts remain an independent, scoped read-only source;
  // queued browser transfers are never represented as automatically connected.
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
  // Later never blocks Home, even when stores remain selected.
  await page.getByTestId('onboarding-stores-later').click()
  await expect(page).toHaveURL(/\/home$/)
  await expect(page.getByTestId('first-use-dashboard-guide')).toHaveCount(0)
  // Even an obsolete link must never render the deleted dashboard guide.
  await page.goto('/home?wegwijs=1')
  await expect(page.getByTestId('first-use-dashboard-guide')).toHaveCount(0)
  await page.goto('/home')
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

  // Touch-sized Android Chrome onboarding uses the retailer's actual import
  // bookmarklet, not the desktop drag-to-favorites control or a fake login.
  await page.addInitScript(() => {
    Object.defineProperty(navigator, 'userAgent', {
      configurable: true,
      get: () => 'Mozilla/5.0 (Linux; Android 14; Pixel 8) AppleWebKit/537.36 Chrome/130.0.0.0 Mobile Safari/537.36',
    })
    Object.defineProperty(navigator, 'clipboard', {
      configurable: true,
      value: { writeText: async value => { window.__inhuisCopiedBookmarklet = value } },
    })
  })
  await page.setViewportSize({ width: 390, height: 844 })
  await page.goto('/onboarding/winkels')
  // Explicit Later clears unfinished choices; verify persisted opt-out before reselecting.
  await expect(page.getByTestId('onboarding-select-lidl')).not.toBeChecked()
  const deferredResponse = await page.request.get('/api/onboarding/stores')
  expect(deferredResponse.ok()).toBeTruthy()
  expect(await deferredResponse.json()).toMatchObject({ available: true, selected: [], results: {} })
  await page.getByTestId('onboarding-store-row-lidl').locator('label').click()
  await expect(page.getByTestId('onboarding-select-lidl')).toBeChecked()
  await page.getByTestId('onboarding-store-row-lidl').locator('label').click()
  await expect(page.getByTestId('onboarding-select-lidl')).not.toBeChecked()
  await page.getByTestId('onboarding-store-row-lidl').locator('label').click()
  await expect(page.getByTestId('onboarding-select-lidl')).toBeChecked()
  await page.getByTestId('onboarding-stores-start').click()
  await expect(page.getByTestId('lidl-mobile-setup')).toHaveAttribute('data-browser', 'chrome')
  await expect(page.getByTestId('lidl-mobile-open-store')).toBeVisible()
  await expect(page.getByTestId('lidl-mobile-copy')).toHaveCount(0)
  await expect(page.getByTestId('lidl-mobile-setup')).toContainText('Adres gekopieerd')
  expect(await page.evaluate(() => window.__inhuisCopiedBookmarklet?.startsWith('javascript:'))).toBe(true)
  await expect(page.getByTestId('lidl-mobile-setup')).not.toContainText('Stap 3 van 3')
  await expect(page.getByTestId('lidl-web-bookmarklet')).toHaveCount(0)
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth + 2)).toBe(true)
  await page.getByTestId('lidl-mobile-skip').click()
  await expect(page).toHaveURL(/\/home$/)
  await expect(page.getByTestId('first-use-dashboard-guide')).toHaveCount(0)
  console.log('P0_L4_01_ONBOARDING_BROWSER_GREEN')
})
