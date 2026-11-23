import { writeFileSync } from 'node:fs'
import { join } from 'node:path'
import { test, expect } from '@playwright/test'

const email = process.env.PLAYWRIGHT_F6_02_RECEIPT_EMAIL
const password = process.env.PLAYWRIGHT_F6_02_RECEIPT_PASSWORD
const householdName = process.env.PLAYWRIGHT_F6_02_RECEIPT_HOUSEHOLD
const locationName = process.env.PLAYWRIGHT_F6_02_RECEIPT_LOCATION

function required(name, value) {
  if (!String(value || '').trim()) throw new Error(`${name} ontbreekt voor F6-02 Receipt`)
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

async function readSession(page) {
  const response = await page.request.get('/api/session')
  expect(response.ok()).toBeTruthy()
  return response.json()
}

async function loadCanonicalReceiptFixture(request, baseURL) {
  const response = await request.get(`${baseURL}/api/testing/fixtures/receipt/file?kind=manual`)
  expect(response.ok(), 'Canonieke kassabonfixture moet beschikbaar zijn.').toBeTruthy()
  return { name: `f6-02-receipt-${Date.now()}.jpg`, mimeType: 'image/jpeg', buffer: await response.body() }
}

function receiptIdFromImport(payload) {
  return String(payload?.receipt_table_id || payload?.receiptTableId || payload?.existing_receipt?.receipt_table_id || '').trim()
}

async function uploadReceiptThroughKassa(page, file) {
  await page.goto('/kassa')
  await expect(page.getByTestId('kassa-table')).toBeVisible({ timeout: 30_000 })
  const importResponsePromise = page.waitForResponse((response) => new URL(response.url()).pathname === '/api/receipts/import' && response.request().method() === 'POST', { timeout: 180_000 })
  await page.getByTestId('kassa-manual-file-input').setInputFiles(file)
  const response = await importResponsePromise
  const text = await response.text()
  let payload = null
  try { payload = text ? JSON.parse(text) : null } catch { throw new Error(`Kassa-import gaf geen JSON terug: HTTP ${response.status()} ${text.slice(0, 500)}`) }
  expect([200, 201], JSON.stringify(payload)).toContain(response.status())
  expect(payload?.duplicate).not.toBe(true)
  const receiptId = receiptIdFromImport(payload)
  expect(receiptId).not.toBe('')

  // This canonical receipt predates the fresh household cutover. Do not
  // bypass the historical-receipt policy: prove history-only first and
  // correct the purchase date through the real Bonkop UI for this CURRENT
  // receipt retry scenario.
  const householdResponse = await page.request.get('/api/household')
  expect(householdResponse.ok()).toBeTruthy()
  const household = await householdResponse.json()
  const householdId = String(household?.active_household_id || household?.id || '')
  expect(householdId).not.toBe('')
  const params = new URLSearchParams({ householdId, page: '1', page_size: '10' })
  const current = await page.request.get(`/api/kassa/receipts-page?${params.toString()}`)
  expect(current.ok()).toBeTruthy()
  expect((await current.json()).items.some((row) => String(row.receipt_table_id) === receiptId)).toBe(false)

  const history = await page.request.get(
    `/api/kassa/historical-receipts-page?householdId=${encodeURIComponent(householdId)}&page=1&page_size=100`
  )
  expect(history.ok()).toBeTruthy()
  expect((await history.json()).items.some((row) => String(row.receipt_table_id) === receiptId)).toBe(true)

  await expect(page.getByTestId('receipt-detail-page')).toBeVisible({ timeout: 90_000 })
  await page.getByRole('tab', { name: 'Bonkop', exact: true }).click()
  const date = page.getByLabel('Aankoopdatum', { exact: true })
  await expect(date).toBeVisible()
  const saved = page.waitForResponse((response) => (
    new URL(response.url()).pathname === `/api/receipts/${receiptId}`
    && response.request().method() === 'PATCH'
  ))
  await date.fill(new Date().toISOString().slice(0, 10))
  await date.blur()
  expect((await saved).ok()).toBeTruthy()
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
  await expect(page.getByTestId('receipt-lines-table')).toBeVisible({ timeout: 30_000 })
  const approvalResponsePromise = page.waitForResponse((response) => new URL(response.url()).pathname === `/api/receipts/${receiptId}/approve` && response.request().method() === 'POST')
  await page.getByRole('button', { name: 'Goedkeuren', exact: true }).click()
  const approvalResponse = await approvalResponsePromise
  const approvalText = await approvalResponse.text()
  expect(approvalResponse.ok(), `Approval status ${approvalResponse.status()}: ${approvalText.slice(0, 1000)}`).toBeTruthy()
}

async function resolveApprovedBatch(page, householdId, receiptId) {
  let resolved = null
  await expect.poll(async () => {
    const response = await page.request.get(`/api/unpack-start-batches?householdId=${encodeURIComponent(householdId)}`)
    if (!response.ok()) return ''
    const payload = await response.json()
    const items = Array.isArray(payload?.items) ? payload.items : []
    resolved = items.find((item) => String(item?.receipt_table_id || '') === receiptId) || (items.length === 1 ? items[0] : null)
    return String(resolved?.batch_id || '')
  }, { timeout: 30_000 }).not.toBe('')
  return resolved
}

async function readBatch(page, batchId) {
  const response = await page.request.get(`/api/purchase-import-batches/${encodeURIComponent(batchId)}`)
  expect(response.ok()).toBeTruthy()
  return response.json()
}

async function selectLineAndProcess(page, batchId, lineId) {
  await page.goto(`/kassabonnen?batch=${encodeURIComponent(batchId)}`)
  await expect(page.getByTestId('receipts-page')).toBeVisible({ timeout: 30_000 })
  await expect(page.getByTestId(`receipt-line-${lineId}`)).toBeVisible({ timeout: 30_000 })
  const lineSelect = page.getByTestId(`receipt-line-select-${lineId}`)
  if (!(await lineSelect.isChecked())) await lineSelect.check()
  const responsePromise = page.waitForResponse((response) => new URL(response.url()).pathname === `/api/purchase-import-batches/${batchId}/process` && response.request().method() === 'POST')
  await page.getByTestId('receipt-process-button').click()
  return responsePromise
}

test('F6-02 Receipt temporary failure rolls back and visible retry succeeds exactly once', async ({ page, request }, testInfo) => {
  test.setTimeout(360_000)
  const accountEmail = required('PLAYWRIGHT_F6_02_RECEIPT_EMAIL', email).toLowerCase()
  const accountPassword = required('PLAYWRIGHT_F6_02_RECEIPT_PASSWORD', password)
  const expectedHouseholdName = required('PLAYWRIGHT_F6_02_RECEIPT_HOUSEHOLD', householdName)
  const expectedLocationName = required('PLAYWRIGHT_F6_02_RECEIPT_LOCATION', locationName)
  const baseURL = required('PLAYWRIGHT_BASE_URL', testInfo.project.use.baseURL)

  await registerLocationsOnHousehold(page, accountEmail, accountPassword, expectedHouseholdName)
  const session = await readSession(page)
  const householdId = String(session.active_household_id || '')
  expect(session.role).toBe('admin')
  expect(householdId).not.toBe('')

  const fixture = await loadCanonicalReceiptFixture(request, baseURL)
  const receiptId = await uploadReceiptThroughKassa(page, fixture)
  await approveReceiptThroughKassa(page, receiptId)
  const approvedBatch = await resolveApprovedBatch(page, householdId, receiptId)
  const batchId = String(approvedBatch.batch_id || '')
  expect(batchId).not.toBe('')

  const batchBefore = await readBatch(page, batchId)
  const line = (batchBefore?.lines || []).find((item) => Number.isInteger(Number(item?.quantity_raw || 0)) && Number(item?.quantity_raw || 0) > 0 && String(item?.processing_status || '') !== 'processed')
  expect(line, `Geen verwerkbare bonregel gevonden in ${JSON.stringify(batchBefore)}`).toBeTruthy()
  const lineId = String(line.id)
  const expectedQuantity = Number(line.quantity_raw)

  await page.goto(`/kassabonnen?batch=${encodeURIComponent(batchId)}`)
  await expect(page.getByTestId(`receipt-line-${lineId}`)).toBeVisible({ timeout: 30_000 })
  const locationButton = page.getByTestId(`receipt-line-location-select-${lineId}`)
  await locationButton.click()
  await expect(page.getByRole('dialog', { name: 'Locatie / sublocatie kiezen' })).toBeVisible()
  await page.getByTestId('receipt-location-create-space').click()
  await page.getByTestId('receipt-location-create-name').fill(expectedLocationName)
  await page.getByTestId('receipt-location-create-save').click()
  const createdDialog = page.getByRole('dialog', { name: 'Gelukt' })
  const sublocationName = 'Voorraadkast'
  if (await page.getByTestId('receipt-location-create-name').isVisible()) {
    // Exacte locatiebewaking: een hoofdlocatie is pas selecteerbaar met sublocatie.
    await expect(createdDialog).toContainText(`Locatie ${expectedLocationName} toegevoegd. Voeg nu een sublocatie toe.`)
    await createdDialog.getByRole('button', { name: 'OK', exact: true }).click()
    await page.getByTestId('receipt-location-create-name').fill(sublocationName)
    await page.getByTestId('receipt-location-create-save').click()
    await expect(createdDialog).toContainText(`Sublocatie ${sublocationName} is toegevoegd en geselecteerd.`)
  } else {
    await expect(createdDialog).toContainText(`Locatie ${expectedLocationName} is toegevoegd en geselecteerd.`)
  }
  await createdDialog.getByRole('button', { name: 'OK', exact: true }).click()
  await expect(locationButton).toContainText(expectedLocationName, { timeout: 20_000 })

  const firstResponse = await selectLineAndProcess(page, batchId, lineId)
  expect(firstResponse.status()).toBe(500)
  await expect(page.getByText('Verwerken van bonregels is mislukt.', { exact: true })).toBeVisible({ timeout: 30_000 })
  await expect(page.locator('body')).not.toContainText('F6 temporary receipt finalization failure')

  await page.reload()
  await expect(page.getByTestId(`receipt-line-${lineId}`)).toBeVisible({ timeout: 30_000 })
  const retryResponse = await selectLineAndProcess(page, batchId, lineId)
  expect(retryResponse.ok(), `Retry status ${retryResponse.status()}`).toBeTruthy()
  const retryPayload = await retryResponse.json()
  expect(Number(retryPayload?.processed_count || 0), JSON.stringify(retryPayload)).toBe(1)
  expect(Number(retryPayload?.failed_count || 0), JSON.stringify(retryPayload)).toBe(0)

  const completedDialog = page.getByRole('dialog', { name: /^(Verwerking afgerond|Geselecteerde artikelen verwerkt)$/ })
  await expect(completedDialog).toBeVisible({ timeout: 30_000 })
  await completedDialog.getByRole('button', { name: 'OK' }).click()

  const batchAfter = await readBatch(page, batchId)
  const processedLine = (batchAfter?.lines || []).find((item) => String(item?.id || '') === lineId)
  expect(processedLine).toBeTruthy()
  expect(String(processedLine.processing_status || '')).toBe('processed')
  const processedEventId = String(processedLine.processed_event_id || '')
  const householdArticleId = String(processedLine.matched_household_article_id || '')
  const targetLocationId = String(processedLine.target_location_id || processedLine.final_location_id || '')
  expect(processedEventId).not.toBe('')
  expect(householdArticleId).not.toBe('')
  expect(targetLocationId).not.toBe('')

  const inventoryResponse = await page.request.get('/api/dev/inventory-preview')
  expect(inventoryResponse.ok()).toBeTruthy()
  const inventoryPayload = await inventoryResponse.json()
  const matchingInventory = (inventoryPayload?.rows || []).filter((row) => String(row?.household_article_id || '') === householdArticleId)
  const browserInventoryTotal = matchingInventory.reduce((sum, row) => sum + Number(row?.aantal || 0), 0)
  expect(browserInventoryTotal).toBe(expectedQuantity)

  writeFileSync(join(process.cwd(), 'f6-02-receipt-browser-proof.json'), JSON.stringify({
    householdId,
    receiptId,
    batchId,
    lineId,
    expectedQuantity,
    processedEventId,
    householdArticleId,
    targetLocationId,
    processResponseCount: 2,
    processStatuses: [firstResponse.status(), retryResponse.status()],
    browserInventoryTotal,
  }, null, 2), 'utf8')

  console.log('F6_02_RECEIPT_TEMPORARY_FAILURE_VISIBLE_GREEN')
  console.log('F6_02_RECEIPT_VISIBLE_RETRY_SUCCESS_GREEN')
  console.log('F6_02_RECEIPT_BROWSER_EXACT_ONCE_GREEN')
})
