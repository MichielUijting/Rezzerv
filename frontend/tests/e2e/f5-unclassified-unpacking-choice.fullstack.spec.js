import { writeFileSync } from 'node:fs'
import { test, expect } from '@playwright/test'

const email = process.env.PLAYWRIGHT_F5_09_EMAIL
const password = process.env.PLAYWRIGHT_F5_09_PASSWORD
const householdName = process.env.PLAYWRIGHT_F5_09_HOUSEHOLD

function required(name, value) {
  if (!String(value || '').trim()) throw new Error(`${name} ontbreekt voor F5-09`)
  return String(value).trim()
}

async function registerLocationsOnHousehold(page, accountEmail, accountPassword, expectedHouseholdName) {
  // New registration always starts Wat Inhuis, quantities and Alleen.
  await page.goto('/registreren')
  await expect(page.getByTestId('register-page')).toBeVisible()
  await expect(page.getByTestId('register-password-repeat')).toHaveCount(0)
  await page.getByTestId('register-email').fill(accountEmail)
  await page.getByTestId('register-password').fill(accountPassword)
  await page.getByTestId('register-household-name').fill(expectedHouseholdName)
  const registrationResponsePromise = page.waitForResponse((response) => (
    new URL(response.url()).pathname === '/api/auth/register'
    && response.request().method() === 'POST'
  ))
  await page.getByTestId('register-submit').click()
  const response = await registrationResponsePromise
  expect(response.status()).toBe(201)
  const registration = await response.json()
  expect(registration.onboarding?.onboarding_status).toBe('completed')
  expect(registration.onboarding?.primary_use_case).toBe('wat_inhuis')
  expect(registration.onboarding?.household_usage_mode).toBe('alone')
  expect(registration.onboarding?.household_name).toBe(expectedHouseholdName)
  expect(registration.onboarding?.product_configuration?.inventory_tracking_level).toBe('quantity')
  await expect(page).toHaveURL(/\/onboarding\/winkels$/)
  await expect(page.getByTestId('onboarding-stores-step')).toBeVisible()
  await page.getByTestId('onboarding-stores-later').click()
  await expect(page).toHaveURL(/\/home$/)

  // This dedicated Uitpakken authority deliberately adds Waar Inhuis afterwards
  // through the normal user-visible Settings flow; onboarding never asks this.
  await page.goto('/instellingen/mogelijkheden')
  await expect(page.getByTestId('settings-capabilities-page')).toBeVisible()
  await page.getByTestId('capability-add-waar_inhuis').click()
  const expansionForm = page.getByTestId('capability-expansion-form-waar_inhuis')
  await expect(expansionForm).toBeVisible()
  await page.getByTestId('capability-waar-unpacking').check()
  const expansionResponsePromise = page.waitForResponse((response) => (
    new URL(response.url()).pathname === '/api/onboarding/expand/waar-inhuis'
    && response.request().method() === 'POST'
  ))
  await page.getByTestId('capability-expansion-submit').click()
  const expansionResponse = await expansionResponsePromise
  expect(expansionResponse.ok()).toBeTruthy()
  const capabilities = await expansionResponse.json()
  expect(capabilities.primary_use_case).toBe('wat_inhuis')
  expect(capabilities.active_use_cases).toContain('waar_inhuis')
  expect(capabilities.product_configuration?.location_tracking_level).toBe('exact')
  expect(capabilities.product_configuration?.unpacking_enabled).toBe(true)
  expect(capabilities.product_configuration?.receipt_processing_enabled).toBe(true)
  await page.goto('/home')
}

async function createSpaceThroughUi(page, locationName) {
  await page.goto('/instellingen/locaties')
  await expect(page.getByTestId('settings-locations-page')).toBeVisible({ timeout: 30_000 })
  await expect(page.getByTestId('settings-locations-page')).toHaveAttribute('data-sublocations-enabled', 'true')
  await page.locator('#new-main-location').fill(locationName)
  const createPromise = page.waitForResponse((response) => (
    new URL(response.url()).pathname === '/api/spaces' && response.request().method() === 'POST'
  ))
  await page.getByTestId('new-main-location-row').getByRole('button', { name: 'Toevoegen', exact: true }).click()
  expect((await createPromise).ok()).toBeTruthy()
  await expect(page.locator('#new-main-location')).toHaveValue('')
}

async function readSession(page) {
  const response = await page.request.get('/api/session')
  expect(response.ok()).toBeTruthy()
  return response.json()
}

async function loadCanonicalReceiptFixture(request, baseURL) {
  const response = await request.get(`${baseURL}/api/testing/fixtures/receipt/file?kind=manual`)
  expect(response.ok(), 'Canonieke kassabonfixture moet beschikbaar zijn.').toBeTruthy()
  return { name: `f5-09-${Date.now()}.jpg`, mimeType: 'image/jpeg', buffer: await response.body() }
}

function receiptIdFromImport(payload) {
  return String(payload?.receipt_table_id || payload?.receiptTableId || payload?.existing_receipt?.receipt_table_id || '').trim()
}

async function uploadReceiptThroughKassa(page, file) {
  // The canonical JPG fixture depicts an old purchase. The history cutover
  // must hide it from the actionable Kassa list in a newly enabled household.
  // Import from Kassa itself to keep the real receipt detail available for
  // a deliberate, browser-only correction into this test's CURRENT purchase.
  await page.goto('/kassa')
  await expect(page.getByTestId('kassa-table')).toBeVisible({ timeout: 30_000 })
  const responsePromise = page.waitForResponse((response) => (
    new URL(response.url()).pathname === '/api/receipts/import' && response.request().method() === 'POST'
  ), { timeout: 180_000 })
  await page.getByTestId('kassa-manual-file-input').setInputFiles(file)
  const response = await responsePromise
  const payload = await response.json()
  expect([200, 201]).toContain(response.status())
  expect(payload?.duplicate).not.toBe(true)
  const receiptId = receiptIdFromImport(payload)
  expect(receiptId).not.toBe('')

  // This is a deliberately historical source photo. Verify that the backend
  // retains it as history without offering it as current Kassa work.
  const householdResponse = await page.request.get('/api/household')
  expect(householdResponse.ok()).toBeTruthy()
  const household = await householdResponse.json()
  const householdId = String(household?.active_household_id || household?.id || '')
  expect(householdId).not.toBe('')
  const params = new URLSearchParams({ householdId, page: '1', page_size: '10' })
  const activeBefore = await page.request.get(`/api/kassa/receipts-page?${params.toString()}`)
  expect(activeBefore.ok()).toBeTruthy()
  expect((await activeBefore.json()).items.some((row) => String(row.receipt_table_id) === receiptId)).toBe(false)

  const historical = await page.request.get(
    `/api/kassa/historical-receipts-page?householdId=${encodeURIComponent(householdId)}&page=1&page_size=100`
  )
  expect(historical.ok()).toBeTruthy()
  expect((await historical.json()).items.some((row) => String(row.receipt_table_id) === receiptId)).toBe(true)

  // Exercise real, authorized Kassa header editing, not a mocked API or
  // a test-only inventory bypass. A current date is necessary because these
  // browser tests cover active Uitpakken and physical article identity.
  await expect(page.getByTestId('receipt-detail-page')).toBeVisible({ timeout: 90_000 })
  await page.getByRole('tab', { name: 'Bonkop', exact: true }).click()
  const purchaseDate = page.getByLabel('Aankoopdatum', { exact: true })
  await expect(purchaseDate).toBeVisible()
  const currentDate = new Date().toISOString().slice(0, 10)
  const saved = page.waitForResponse((response) => (
    new URL(response.url()).pathname === `/api/receipts/${receiptId}`
    && response.request().method() === 'PATCH'
  ))
  await purchaseDate.fill(currentDate)
  await purchaseDate.blur()
  expect((await saved).ok()).toBeTruthy()

  // Reload to prove the row is now served by the actual Kassa projection,
  // rather than its transient optimistic upload fallback.
  await page.goto('/kassa')
  await expect(page.getByTestId(`kassa-row-${receiptId}`)).toBeVisible({ timeout: 60_000 })
  return receiptId
}

async function approveReceiptThroughKassa(page, receiptId) {
  await page.goto('/kassa')
  const row = page.getByTestId(`kassa-row-${receiptId}`)
  await expect(row).toBeVisible({ timeout: 60_000 })
  await row.dblclick()
  await expect(page.getByTestId('receipt-detail-page')).toBeVisible({ timeout: 30_000 })
  const responsePromise = page.waitForResponse((response) => (
    new URL(response.url()).pathname === `/api/receipts/${receiptId}/approve` && response.request().method() === 'POST'
  ))
  await page.getByRole('button', { name: 'Goedkeuren', exact: true }).click()
  expect((await responsePromise).ok()).toBeTruthy()
}

async function resolveApprovedBatch(page, householdId, receiptId) {
  let resolved = null
  await expect.poll(async () => {
    const response = await page.request.get(`/api/unpack-start-batches?householdId=${encodeURIComponent(householdId)}`)
    if (!response.ok()) return ''
    const payload = await response.json()
    const items = Array.isArray(payload?.items) ? payload.items : []
    resolved = items.find((item) => String(item?.receipt_table_id || '') === receiptId) || null
    return String(resolved?.batch_id || '')
  }, { timeout: 30_000 }).not.toBe('')
  return resolved
}

async function readBatch(page, batchId) {
  const response = await page.request.get(`/api/purchase-import-batches/${encodeURIComponent(batchId)}`)
  expect(response.ok()).toBeTruthy()
  return response.json()
}

async function assignLocationToLine(page, lineId, locationName) {
  const locationButton = page.getByTestId(`receipt-line-location-select-${lineId}`)
  await expect(locationButton).toBeVisible({ timeout: 30_000 })
  await locationButton.click()
  const dialog = page.getByRole('dialog', { name: 'Locatie / sublocatie kiezen' })
  await expect(dialog).toBeVisible()
  const savePromise = page.waitForResponse((response) => (
    response.url().includes(`/api/purchase-import-lines/${lineId}/target-location`)
      && response.request().method() === 'POST'
  ))
  await dialog.getByRole('button', { name: locationName, exact: true }).click()
  const response = await savePromise
  expect(response.ok()).toBeTruthy()
  const payload = await response.json()
  await expect(locationButton).toContainText(locationName)
  return String(payload?.target_location_id || payload?.resolved_location?.location_id || payload?.resolved_location?.space_id || '').trim()
}

test('F5-09 Niet ingedeeld remains valid in ready-only unpacking', async ({ page, request }, testInfo) => {
  test.setTimeout(360_000)
  const accountEmail = required('PLAYWRIGHT_F5_09_EMAIL', email).toLowerCase()
  const accountPassword = required('PLAYWRIGHT_F5_09_PASSWORD', password)
  const expectedHouseholdName = required('PLAYWRIGHT_F5_09_HOUSEHOLD', householdName)
  const baseURL = required('PLAYWRIGHT_BASE_URL', testInfo.project.use.baseURL)
  const locationName = `F5-09 voorraad ${Date.now()}`

  await registerLocationsOnHousehold(page, accountEmail, accountPassword, expectedHouseholdName)
  const session = await readSession(page)
  expect(session.role).toBe('admin')
  const householdId = String(session.active_household_id || '')
  expect(householdId).not.toBe('')
  await createSpaceThroughUi(page, locationName)

  const receiptId = await uploadReceiptThroughKassa(page, await loadCanonicalReceiptFixture(request, baseURL))
  await approveReceiptThroughKassa(page, receiptId)
  const batchId = String((await resolveApprovedBatch(page, householdId, receiptId)).batch_id)
  const batchBefore = await readBatch(page, batchId)
  const lines = Array.isArray(batchBefore?.lines) ? batchBefore.lines : []
  const targetLine = lines.find((item) => {
    const quantity = Number(item?.quantity_raw || 0)
    return Number.isInteger(quantity) && quantity > 0 && String(item?.processing_status || '') !== 'processed'
  })
  expect(targetLine, `Geen F5-09-doelregel met geldige hoeveelheid gevonden in ${JSON.stringify(batchBefore)}`).toBeTruthy()
  const incompleteLine = lines.find((item) => (
    String(item?.id || '') !== String(targetLine.id)
      && Number(item?.quantity_raw || 0) > 0
      && String(item?.processing_status || '') !== 'processed'
  ))
  expect(incompleteLine, `Geen tweede incomplete regel gevonden in ${JSON.stringify(batchBefore)}`).toBeTruthy()
  const lineId = String(targetLine.id)
  const incompleteLineId = String(incompleteLine.id)

  await page.goto(`/kassabonnen?batch=${encodeURIComponent(batchId)}`)
  await expect(page.getByTestId('receipts-page')).toBeVisible()

  const groupSelect = page.getByTestId(`receipt-line-article-group-select-${lineId}`)
  await expect(groupSelect).toBeVisible({ timeout: 30_000 })
  await expect(groupSelect.locator('option[value=""]')).toHaveText('Niet ingedeeld')
  await groupSelect.selectOption('')
  await expect(groupSelect).toHaveValue('')

  const targetLocationId = await assignLocationToLine(page, lineId, locationName)
  expect(targetLocationId).not.toBe('')

  const targetSelect = page.getByTestId(`receipt-line-select-${lineId}`)
  if (!(await targetSelect.isChecked())) await targetSelect.check()
  const incompleteSelect = page.getByTestId(`receipt-line-select-${incompleteLineId}`)
  if (!(await incompleteSelect.isChecked())) await incompleteSelect.check()

  await expect(page.getByTestId('receipt-process-button')).toBeEnabled()
  await page.getByTestId('receipt-process-button').click()
  const confirm = page.getByRole('dialog', { name: 'Niet alle geselecteerde regels zijn compleet' })
  await expect(confirm).toBeVisible()
  await expect(confirm).toContainText('1 geselecteerde regel(s) zijn klaar voor verwerking')

  const processResponsePromise = page.waitForResponse((response) => (
    new URL(response.url()).pathname === `/api/purchase-import-batches/${batchId}/process`
      && response.request().method() === 'POST'
  ))
  await confirm.getByRole('button', { name: 'Verwerk alleen complete regels', exact: true }).click()
  const processResponse = await processResponsePromise
  expect(processResponse.ok()).toBeTruthy()
  const processPayload = await processResponse.json()
  expect(Number(processPayload?.processed_count || 0), JSON.stringify(processPayload)).toBeGreaterThanOrEqual(1)
  expect(JSON.stringify(processPayload)).not.toContain('Nog geen artikelgroep gekozen')

  await expect(page.getByRole('dialog', { name: /^(Verwerking afgerond|Geselecteerde artikelen verwerkt)$/ })).toBeVisible({ timeout: 30_000 })
  await page.getByRole('dialog', { name: /^(Verwerking afgerond|Geselecteerde artikelen verwerkt)$/ }).getByRole('button', { name: 'OK' }).click()
  await expect(page.getByTestId(`receipt-line-${lineId}`)).toHaveCount(0, { timeout: 20_000 })

  const batchAfter = await readBatch(page, batchId)
  const afterLines = Array.isArray(batchAfter?.lines) ? batchAfter.lines : []
  const processedLine = afterLines.find((item) => String(item?.id || '') === lineId)
  const stillIncompleteLine = afterLines.find((item) => String(item?.id || '') === incompleteLineId)
  expect(processedLine).toBeTruthy()
  expect(String(processedLine.processing_status || '')).toBe('processed')
  expect(String(processedLine.article_group_id || processedLine.selected_article_group_id || '')).toBe('')
  expect(String(processedLine.processed_event_id || '')).not.toBe('')
  expect(stillIncompleteLine).toBeTruthy()
  expect(String(stillIncompleteLine.processing_status || '')).not.toBe('processed')

  writeFileSync('f5-09-browser-proof.json', JSON.stringify({
    householdId,
    receiptId,
    batchId,
    lineId,
    incompleteLineId,
    processedEventId: String(processedLine.processed_event_id),
    articleGroupId: null,
    targetLocationId,
    locationTrackingLevel: 'exact',
    processMode: 'ready_only',
  }, null, 2))

  console.log('F5_09_UNCLASSIFIED_READY_ONLY_BROWSER_GREEN')
  console.log('F5_09_UNCLASSIFIED_UNPACKING_BROWSER_GREEN')
})
