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

async function dismissFeedback(page) {
  const ok = page.getByRole('button', { name: 'OK' })
  await expect(ok).toBeVisible()
  await ok.click()
  await expect(ok).toHaveCount(0)
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

test('Wat Inhuis global locations keep the full standard management UX without sublocations', async ({ page }) => {
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

test('Waar Inhuis onboarding defers all location entry to Settings', async ({ page }) => {
  await page.context().clearCookies()
  const registration = await page.request.post('/api/auth/register', {
    data: {
      email: uniqueEmail('waar-inhuis-no-location-frame'),
      password: 'SterkWachtwoord123!',
    },
  })
  expect(registration.status()).toBe(201)

  await page.goto('/onboarding')
  await page.getByTestId('onboarding-choice-waar_inhuis').check()
  await page.getByTestId('onboarding-primary-continue').click()

  await expect(page.getByTestId('onboarding-waar-inhuis-follow-up')).toBeVisible()
  await expect(page.getByTestId('waar-inhuis-locations-settings-hint')).toContainText('Instellingen → Locaties')
  await expect(page.getByText('Welke hoofdlocaties wil je gebruiken?')).toHaveCount(0)
  await expect(page.getByText('Locaties nu al verfijnen?')).toHaveCount(0)
  await expect(page.getByTestId('waar-inhuis-custom-location-input')).toHaveCount(0)
  await expect(page.getByTestId('waar-inhuis-refine-locations')).toHaveCount(0)
  await expect(page.getByTestId('waar-inhuis-sublocation-add')).toHaveCount(0)

  await page.getByTestId('waar-inhuis-finish').click()
  await expect(page.getByText('Jouw volledige inrichting')).toBeVisible()
})

test('Waar Inhuis exact locations keep full main-location and sublocation management working', async ({ page }) => {
  await registerAndComplete(page, {
    prefix: 'dynamic-settings-waar-inhuis',
    useCase: 'waar_inhuis',
    householdName: 'Dynamische instellingen Waar Inhuis',
    profile: {
      unpacking_enabled: true,
      receipt_processing_enabled: true,
      almost_out_enabled: false,
    },
  })

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
