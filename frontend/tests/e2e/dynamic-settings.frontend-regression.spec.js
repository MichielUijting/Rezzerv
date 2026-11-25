import { test, expect } from '@playwright/test'

function uniqueEmail(prefix) {
  return `${prefix}-${Date.now()}-${Math.random().toString(16).slice(2)}@example.com`
}

async function registerAndComplete(page, { prefix, useCase, profile, householdName }, retry) {
  // The canonical full-regression project starts each test with the shared system
  // fixture cookie. Drop it only from this fresh browser context so these tests
  // can create their own regular consumer account without revoking the shared
  // server session used by the rest of the regression suite.
  await page.context().clearCookies()

  // These accounts represent households whose onboarding began before the
  // mandatory quick registration. The CI-only fixture provisions one per retry.
  // All profile transitions below still run against the real authenticated API.
  const password = process.env.PLAYWRIGHT_LEGACY_ONBOARDING_PASSWORD
  expect(password, 'PR253 must provision isolated legacy onboarding fixtures').toBeTruthy()
  const login = await page.request.post('/api/auth/login', {
    data: { email: `${prefix}-retry${retry}@example.test`, password },
  })
  expect(login.status()).toBe(200)
  const session = await login.json()
  expect(session.context_type).toBe('regular')
  const before = await page.request.get('/api/onboarding')
  expect(before.status()).toBe(200)
  expect(await before.json()).toMatchObject({
    onboarding_status: 'not_started',
    initial_choice_required: true,
    can_manage: true,
  })

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
  expect(completed.status()).toBe(200)
  const state = await completed.json()
  expect(state).toMatchObject({
    onboarding_status: 'completed',
    primary_use_case: useCase,
    household_name: householdName,
    household_usage_mode: 'alone',
  })
  return state
}

async function dismissFeedback(page) {
  const ok = page.getByRole('button', { name: 'OK' })
  await expect(ok).toBeVisible()
  await ok.click()
  await expect(ok).toHaveCount(0)
}

test('system context keeps personal Settings while Frontteambeheer lives under Superuser', async ({ page }) => {
  const session = await page.request.get('/api/session')
  expect(session.ok()).toBeTruthy()
  expect((await session.json()).context_type).toBe('system')

  await page.goto('/instellingen')
  await expect(page).toHaveURL(/\/instellingen$/)
  await expect(page.getByTestId('settings-page')).toBeVisible()
  await expect(page.getByTestId('settings-tile-account')).toBeVisible()
  await expect(page.getByTestId('settings-tile-help-about')).toBeVisible()
  await expect(page.getByTestId('settings-tile-frontteam')).toHaveCount(0)
})

test('Inhuis halen shows grouped product-relevant settings while keeping general household settings', async ({ page }, testInfo) => {
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
  }, testInfo.retry)

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
  await expect(page.getByTestId('settings-tile-store-connections')).toBeVisible()
  await expect(page.getByTestId('settings-tile-household')).toBeVisible()
  await expect(page.getByTestId('settings-tile-household')).toHaveAttribute('data-settings-scope', 'household')
  await expect(page.getByTestId('settings-tile-authorizations')).toBeVisible()
  await expect(page.getByTestId('settings-tile-household-automation')).toBeVisible()
  await expect(page.getByTestId('settings-tile-almost-out')).toBeVisible()
  await expect(page.getByTestId('settings-tile-help-about')).toBeVisible()
  await expect(page.getByTestId('settings-tile-help-about')).toHaveAttribute('data-settings-scope', 'personal')
  await expect(page.getByTestId('settings-tile-locations')).toHaveCount(0)
})

test('Wat Inhuis global locations keep the full standard management UX without sublocations', async ({ page }, testInfo) => {
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
  }, testInfo.retry)

  await page.goto('/instellingen')
  await expect(page.getByTestId('settings-page')).toHaveAttribute('data-settings-mode', 'dynamic')
  await expect(page.getByTestId('settings-tile-locations')).toBeVisible()
  await page.getByTestId('settings-tile-locations').click()

  await expect(page).toHaveURL(/\/instellingen\/locaties$/)
  const locationsPage = page.getByTestId('settings-locations-page')
  await expect(locationsPage).toBeVisible()
  await expect(locationsPage).toHaveAttribute('data-sublocations-enabled', 'false')
  await expect(page.getByTestId('sublocations-section')).toHaveCount(0)

  const table = page.getByTestId('settings-locations-table')
  await expect(table).toBeVisible()
  await expect(page.getByLabel('Filter op locatie')).toBeVisible()
  await expect(page.getByLabel('Filter op actief')).toBeVisible()
  await expect(page.getByLabel('Selecteer alle locaties')).toBeVisible()
  await expect(table.locator('.rz-column-resize-handle')).toHaveCount(3)

  const direct = page.getByTestId('canonical-direct-location')
  await expect(direct).toHaveText('Direct')
  await expect(page.locator('input[aria-label="Locatienaam Direct"]')).toHaveCount(0)
  await expect(page.getByLabel('Actief Direct')).toBeDisabled()
  await expect(page.getByLabel('Selecteer Direct')).toBeDisabled()

  const locationHeader = table.locator('th').nth(1)
  const handle = locationHeader.locator('.rz-column-resize-handle')
  const beforeTableWidth = await table.evaluate((element) => element.getBoundingClientRect().width)
  const beforeWidth = Number.parseFloat(await table.locator('col').nth(1).evaluate((element) => element.style.width))
  const beforeAdjacentWidth = Number.parseFloat(await table.locator('col').nth(2).evaluate((element) => element.style.width))
  const box = await handle.boundingBox()
  expect(box).toBeTruthy()
  await page.mouse.move(box.x + box.width / 2, box.y + box.height / 2)
  await page.mouse.down()
  await page.mouse.move(box.x + box.width / 2 + 60, box.y + box.height / 2)
  await page.mouse.up()
  const afterTableWidth = await table.evaluate((element) => element.getBoundingClientRect().width)
  const afterWidth = Number.parseFloat(await table.locator('col').nth(1).evaluate((element) => element.style.width))
  const afterAdjacentWidth = Number.parseFloat(await table.locator('col').nth(2).evaluate((element) => element.style.width))
  expect(afterWidth).toBeGreaterThan(beforeWidth)
  expect(afterAdjacentWidth).toBeLessThan(beforeAdjacentWidth)
  expect(Math.abs(afterTableWidth - beforeTableWidth)).toBeLessThanOrEqual(1)
  expect(Math.abs((afterWidth - beforeWidth) + (afterAdjacentWidth - beforeAdjacentWidth))).toBeLessThanOrEqual(1)

  await expect(page.getByRole('button', { name: 'Exporteren' })).toBeVisible()
  await expect(page.getByRole('button', { name: 'Verwijderen' })).toBeVisible()
  await expect(page.getByRole('button', { name: 'Wijzigingen opslaan' })).toHaveCount(0)

  const newRow = page.getByTestId('new-main-location-row')
  const labelBox = await newRow.getByText('Nieuwe hoofdlocatie', { exact: true }).boundingBox()
  const inputBox = await newRow.locator('#new-main-location').boundingBox()
  expect(labelBox).toBeTruthy()
  expect(inputBox).toBeTruthy()
  expect(labelBox.x).toBeLessThan(inputBox.x)

  await newRow.locator('#new-main-location').fill('Woning')
  await newRow.getByRole('button', { name: 'Toevoegen' }).click()
  const successDialog = page.getByRole('dialog')
  await expect(successDialog).toContainText('Hoofdlocatie toegevoegd.')
  await dismissFeedback(page)
  await expect(page.getByLabel('Locatienaam Woning')).toBeVisible()

  await page.getByLabel('Locatienaam Woning').fill('Woning gewijzigd')
  await page.goBack()
  const pending = page.getByTestId('locations-pending-changes-overlay')
  await expect(pending).toBeVisible()
  await expect(pending.getByRole('button', { name: 'Wijzigingen opslaan' })).toBeVisible()
  await expect(pending.getByRole('button', { name: 'Wijzigingen annuleren' })).toBeVisible()
  await pending.getByRole('button', { name: 'Wijzigingen annuleren' }).click()
  await expect(page).toHaveURL(/\/instellingen$/)
})

test('Quick Start onboarding asks for no locations and preserves Wat Inhuis defaults in Settings', async ({ page }) => {
  await page.context().clearCookies()
  await page.goto('/registreren')
  await expect(page.getByTestId('register-page')).toBeVisible()
  await expect(page.getByTestId('register-quick-start-defaults')).toContainText('Wat Inhuis · Aantallen · Alleen.')
  await expect(page.getByTestId('register-password-repeat')).toHaveCount(0)
  await expect(page.getByTestId('onboarding-quick-start')).toHaveCount(0)
  await expect(page.getByTestId('onboarding-choice-waar_inhuis')).toHaveCount(0)
  await expect(page.getByTestId('onboarding-waar-inhuis-follow-up')).toHaveCount(0)
  await expect(page.getByText('Welke hoofdlocaties wil je gebruiken?')).toHaveCount(0)
  await expect(page.getByText('Locaties nu al verfijnen?')).toHaveCount(0)
  await expect(page.getByTestId('waar-inhuis-custom-location-input')).toHaveCount(0)
  await expect(page.getByTestId('waar-inhuis-refine-locations')).toHaveCount(0)
  await expect(page.getByTestId('waar-inhuis-sublocation-add')).toHaveCount(0)

  await page.getByTestId('register-email').fill(uniqueEmail('no-location-onboarding'))
  await page.getByTestId('register-password').fill('SterkWachtwoord123!')
  await page.getByTestId('register-household-name').fill('Wat Inhuis zonder locatiewizard')
  const registrationPromise = page.waitForResponse(response =>
    new URL(response.url()).pathname === '/api/auth/register' && response.request().method() === 'POST')
  await page.getByTestId('register-submit').click()
  const registration = await registrationPromise
  expect(registration.status()).toBe(201)
  expect((await registration.json()).onboarding).toMatchObject({
    onboarding_status: 'completed',
    primary_use_case: 'wat_inhuis',
    household_usage_mode: 'alone',
    household_name: 'Wat Inhuis zonder locatiewizard',
    product_configuration: { inventory_tracking_level: 'quantity', location_tracking_level: 'none' },
  })
  await expect(page).toHaveURL(/\/onboarding\/winkels$/)
  await expect(page.getByTestId('store-onboarding-selection')).toBeVisible()
  await expect(page.getByTestId('receipt-connections-overview')).toHaveCount(0)
  await expect(page.getByTestId('onboarding-choice-waar_inhuis')).toHaveCount(0)

  const onboardingResponse = await page.request.get('/api/onboarding')
  expect(onboardingResponse.ok()).toBeTruthy()
  const onboarding = await onboardingResponse.json()
  expect(onboarding).toMatchObject({
    onboarding_status: 'completed',
    primary_use_case: 'wat_inhuis',
    household_usage_mode: 'alone',
    household_name: 'Wat Inhuis zonder locatiewizard',
  })
  expect(onboarding.product_configuration.inventory_tracking_level).toBe('quantity')
  expect(onboarding.product_configuration.location_tracking_level).toBe('none')

  await page.getByTestId('onboarding-stores-later').click()
  await page.goto('/instellingen')
  await expect(page.getByTestId('settings-page')).toHaveAttribute('data-settings-mode', 'dynamic')
  await expect(page.getByTestId('settings-active-profile')).toContainText('Wat Inhuis')
  await expect(page.getByTestId('settings-tile-locations')).toHaveCount(0)
})

test('Waar Inhuis exact locations keep full main-location and sublocation management working', async ({ page }, testInfo) => {
  await registerAndComplete(page, {
    prefix: 'dynamic-settings-waar-inhuis',
    useCase: 'waar_inhuis',
    householdName: 'Dynamische instellingen Waar Inhuis',
    profile: {
      unpacking_enabled: true,
      receipt_processing_enabled: true,
      almost_out_enabled: false,
    },
  }, testInfo.retry)

  await page.goto('/instellingen')
  await expect(page.getByTestId('settings-tile-locations')).toBeVisible()
  await page.getByTestId('settings-tile-locations').click()
  await expect(page).toHaveURL(/\/instellingen\/locaties$/)

  const locationsPage = page.getByTestId('settings-locations-page')
  await expect(locationsPage).toHaveAttribute('data-sublocations-enabled', 'true')
  await expect(page.getByTestId('sublocations-section')).toBeVisible()
  await expect(page.getByLabel('Filter op locatie')).toBeVisible()
  await expect(page.getByLabel('Selecteer alle locaties')).toBeVisible()

  const newLocationRow = page.getByTestId('new-main-location-row')
  await newLocationRow.locator('#new-main-location').fill('Woning exact')
  await newLocationRow.getByRole('button', { name: 'Toevoegen' }).click()
  await dismissFeedback(page)
  await expect(page.getByLabel('Locatienaam Woning exact')).toBeVisible()

  const woningExactRow = page.getByRole('row').filter({ has: page.getByLabel('Locatienaam Woning exact') })
  await woningExactRow.dblclick()
  await expect(page.getByTestId('sublocations-heading')).toHaveText('Sublocaties van Woning exact')

  const newSublocationRow = page.getByTestId('new-sublocation-row')
  await newSublocationRow.getByLabel('Hoofdlocatie voor nieuwe sublocatie').selectOption({ label: 'Woning exact' })
  await newSublocationRow.getByLabel('Naam nieuwe sublocatie').fill('Kast 1')
  await newSublocationRow.getByRole('button', { name: 'Toevoegen' }).click()
  await dismissFeedback(page)

  await expect(page.getByTestId('sublocations-heading')).toHaveText('Sublocaties van Woning exact')
  await expect(page.getByLabel('Sublocatienaam Kast 1')).toBeVisible()
  await expect(page.getByTestId('settings-sublocations-table').locator('.rz-column-resize-handle')).toHaveCount(3)
})


test('Winkelkoppelingen renders Albert Heijn and Lidl Plus in desktop and mobile route content', async ({ page }, testInfo) => {
  await registerAndComplete(page, {
    prefix: 'dynamic-settings-store-connections',
    useCase: 'inhuis_halen',
    householdName: 'Dynamische instellingen Winkelkoppelingen',
    profile: {
      simple_inventory_enabled: true,
      receipt_processing_enabled: true,
      almost_out_notifications_enabled: false,
      recipes_enabled: false,
    },
  }, testInfo.retry)

  await page.goto('/instellingen')
  await expect(page.getByTestId('settings-tile-store-connections')).toBeVisible()
  await page.getByTestId('settings-tile-store-connections').click()

  await expect(page).toHaveURL(/\/instellingen\/winkelkoppelingen$/)
  await expect(page.getByTestId('store-connections-page')).toBeVisible()
  await expect(page.getByTestId('receipt-connections-overview')).toBeVisible()
  await expect(page.getByTestId('ah-digital-receipts')).toHaveCount(0)
  await page.getByTestId('receipt-connection-action-ah').click()
  await expect(page.getByTestId('ah-digital-receipts')).toContainText('Albert Heijn digitale bonnen')
  await page.getByTestId('receipt-connection-action-lidl').click()
  await expect(page.getByTestId('ah-digital-receipts')).toHaveCount(0)
  await expect(page.getByTestId('lidl-digital-receipts')).toContainText('Lidl digitale kassabonnen')
  await expect(page.getByTestId('lidl-web-open-history')).toBeVisible()
  await page.getByTestId('lidl-help-open').click()
  await expect(page.getByTestId('lidl-bookmarklet-dialog')).toBeVisible()
  await expect(page.getByTestId('lidl-web-bookmarklet')).toHaveAttribute('href', /^javascript:/)
  await page.getByTestId('lidl-help-ok').click()

  await page.goto('/instellingen/winkelimport')
  await expect(page.getByTestId('store-import-digital-receipts')).toBeVisible()
  await expect(page.getByTestId('store-import-open-ah')).toHaveText('Albert Heijn')
  await expect(page.getByTestId('store-import-open-lidl')).toHaveText('Lidl Plus')
})

for (const width of [390, 1280]) {
  test(`Bijna op settings validates policies, errors and silent successful saves at ${width}px`, async ({ page }) => {
    await page.setViewportSize({ width, height: 900 })
    let rejectSave = true
    let savedPolicy = null
    let savedShoppingDays = null
    await page.route('**/api/**', async route => {
      const path = new URL(route.request().url()).pathname
      if (path === '/api/household/almost-out-settings') {
        if (route.request().method() === 'PUT') {
          const payload = route.request().postDataJSON()
          if (rejectSave) {
            return route.fulfill({ status: 422, json: { detail: [{ loc: ['body', 'policy_mode'], msg: 'Invalid value' }] } })
          }
          savedPolicy = payload.policy_mode
          savedShoppingDays = payload.shopping_days
          return route.fulfill({ json: { ...payload, is_household_admin: true } })
        }
        return route.fulfill({ json: { prediction_enabled: false, prediction_days: 7, policy_mode: 'advisory', is_household_admin: true } })
      }
      const responses = {
        '/api/session': {
          authenticated: true, user_id: 'settings-admin', email: 'settings@example.test',
          user: { id: 'settings-admin', email: 'settings@example.test' },
          context_type: 'regular', active_household_id: 'settings-household',
          active_household_name: 'Test huishouden', role: 'admin', display_role: 'admin',
          household_role: 'household.admin', is_viewer: false, is_platform_superuser: false,
          is_frontteam: false,
          permissions: { 'household_settings.view': true, 'household_settings.manage': true },
          supported_permissions: ['household_settings.view', 'household_settings.manage'],
        },
        '/api/session/households': { items: [], can_switch_households: false },
        '/api/household': { id: 'settings-household', name: 'Test huishouden' },
        '/api/maintenance/status': { state: 'normal' },
      }
      return route.fulfill({ json: responses[path] ?? {} })
    })
    await page.goto('/instellingen/bijna-op-voorspelling')
    const policy = page.getByTestId('almost-out-policy-mode')
    await expect(policy.locator('option')).toHaveCount(2)
    await expect(policy.locator('option[value="override_fallback_to_stock"]')).toHaveCount(0)
    await page.getByTestId('almost-out-prediction-enabled').check()
    await page.getByTestId('almost-out-shopping-days').fill('3')
    await policy.selectOption('override')
    await page.getByTestId('almost-out-settings-save').click()
    await expect(page.getByTestId('app-feedback-error')).toContainText('De instellingen zijn niet opgeslagen.')
    await page.getByTestId('app-feedback-error').getByRole('button', { name: 'OK', exact: true }).click()
    await expect(page.getByTestId('settings-almost-out-page')).not.toContainText('[object Object]')
    rejectSave = false
    await page.getByTestId('almost-out-settings-save').click()
    await expect.poll(() => savedPolicy).toBe('override')
    expect(savedShoppingDays).toBe(3)
    await expect(page.getByTestId('almost-out-shopping-days')).toHaveValue('3')
    await expect(page.getByTestId('almost-out-settings-save')).toBeEnabled()
    await expect(page.getByRole('status')).toHaveCount(0)
  })
}


for (const width of [390, 1280]) {
  test(`Voorspeltermijn updates from Bijna op and Instellingen share one household value at ${width}px`, async ({ page }) => {
    await page.setViewportSize({ width, height: 900 })
    let settings = {
      prediction_enabled: true, prediction_days: 7, shopping_days: 3,
      policy_mode: 'override', is_household_admin: true,
    }
    const writes = []
    let almostOutReads = 0
    await page.route('**/api/**', route => {
      const request = route.request()
      const path = new URL(request.url()).pathname
      if (path === '/api/household/almost-out-settings') {
        if (request.method() === 'PUT') {
          const payload = request.postDataJSON()
          writes.push(payload)
          settings = { ...settings, ...payload }
        }
        return route.fulfill({ json: settings })
      }
      if (path === '/api/households/horizon-household/almost-out') {
        almostOutReads += 1
        return route.fulfill({ json: { items: [] } })
      }
      const responses = {
        '/api/session': {
          authenticated: true, context_type: 'regular',
          active_household_id: 'horizon-household', active_household_name: 'Test huishouden',
          user_id: 'horizon-admin', email: 'horizon@example.test',
          user: { id: 'horizon-admin', email: 'horizon@example.test' },
          role: 'admin', display_role: 'admin', household_role: 'household.admin',
          permissions: { 'household_settings.view': true, 'household_settings.manage': true },
          supported_permissions: ['household_settings.view', 'household_settings.manage'],
        },
        '/api/session/households': { items: [], can_switch_households: false },
        '/api/household': { id: 'horizon-household', name: 'Test huishouden' },
        '/api/onboarding/capabilities': { product_configuration: { location_tracking_level: 'none' } },
        '/api/maintenance/status': { state: 'normal' },
      }
      return route.fulfill({ json: responses[path] ?? {} })
    })

    await page.goto('/bijna-op')
    const horizon = page.getByTestId('almost-out-prediction-term')
    await expect(horizon).toContainText('Voorspeltermijn: 7 dagen')
    const readsBefore = almostOutReads
    await horizon.getByTestId('almost-out-prediction-edit').click()
    await horizon.getByTestId('almost-out-prediction-input').fill('9')
    await horizon.getByTestId('almost-out-prediction-save').click()
    await expect(horizon).toContainText('Voorspeltermijn: 9 dagen')
    await expect.poll(() => almostOutReads).toBeGreaterThan(readsBefore)
    expect(writes).toHaveLength(1)
    expect(writes[0]).toMatchObject({
      prediction_enabled: true, prediction_days: 9,
      shopping_days: 3, policy_mode: 'override',
    })
    await page.goto('/instellingen/bijna-op-voorspelling')
    const input = page.getByTestId('almost-out-prediction-days')
    await expect(input).toHaveValue('9')
    await expect(page.getByText('Voorspeltermijn (dagen)')).toBeVisible()
    await input.fill('11')
    await page.getByTestId('almost-out-settings-save').click()
    await expect.poll(() => settings.prediction_days).toBe(11)
    await page.goto('/bijna-op')
    await expect(page.getByTestId('almost-out-prediction-term')).toContainText('Voorspeltermijn: 11 dagen')
    settings = { ...settings, is_household_admin: false }
    await page.reload()
    await expect(page.getByTestId('almost-out-prediction-term')).toContainText('11 dagen')
    await expect(page.getByTestId('almost-out-prediction-edit')).toHaveCount(0)
  })
}
