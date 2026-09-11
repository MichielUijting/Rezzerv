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
  await page.goto('/registreren')
  await expect(page.getByTestId('register-page')).toBeVisible()
  await page.getByTestId('register-email').fill(accountEmail)
  await page.getByTestId('register-password').fill(accountPassword)
  await page.getByTestId('register-password-repeat').fill(accountPassword)
  const registrationResponsePromise = page.waitForResponse((response) => response.url().includes('/api/auth/register') && response.request().method() === 'POST')
  await page.getByTestId('register-submit').click()
  expect((await registrationResponsePromise).status()).toBe(201)

  await expect(page.getByTestId('onboarding-use-case-page')).toBeVisible()
  await page.getByTestId('onboarding-choice-wat_inhuis').check()
  const primaryResponsePromise = page.waitForResponse((response) => response.url().includes('/api/onboarding/primary-use-case') && response.request().method() === 'POST')
  await page.getByTestId('onboarding-primary-continue').click()
  expect((await primaryResponsePromise).ok()).toBeTruthy()

  await expect(page.getByTestId('onboarding-wat-inhuis-follow-up')).toBeVisible()
  await page.getByTestId('wat-inhuis-tracking-quantity').check()
  await page.getByTestId('wat-inhuis-global-locations-yes').check()
  await page.getByTestId('wat-inhuis-almost-out-yes').check()
  await page.getByTestId('wat-inhuis-shopping-yes').check()
  const productResponsePromise = page.waitForResponse((response) => response.url().includes('/api/onboarding/wat-inhuis') && response.request().method() === 'POST')
  await page.getByTestId('wat-inhuis-finish').click()
  expect((await productResponsePromise).ok()).toBeTruthy()

  await expect(page.getByTestId('onboarding-shared-household-minimum')).toBeVisible()
  await page.getByTestId('shared-household-name').fill(expectedHouseholdName)
  await page.getByTestId('shared-household-usage-alone').check()
  const householdResponsePromise = page.waitForResponse((response) => response.url().includes('/api/onboarding/shared-household-minimum') && response.request().method() === 'POST')
  await page.getByTestId('shared-household-finish').click()
  expect((await householdResponsePromise).ok()).toBeTruthy()
  await expect(page).toHaveURL(/\/home$/)
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
  await page.goto('/kassa/nieuw')
  await expect(page.getByTestId('kassa-add-page')).toBeVisible()
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
  expect((await approvalResponsePromise).ok()).toBeTruthy()
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
  await expect(locationButton).toContainText(expectedLocationName, { timeout: 20_000 })
  const createdDialog = page.getByRole('dialog', { name: 'Gelukt' })
  await expect(createdDialog).toContainText(`Locatie ${expectedLocationName} is toegevoegd en geselecteerd.`)
  await createdDialog.getByRole('button', { name: 'OK', exact: true }).click()

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

  const completedDialog = page.getByRole('dialog', { name: 'Verwerking afgerond' })
  await expect(completedDialog).toBeVisible({ timeout: 30_000 })
  await completedDialog.getByRole('button', { name: 'Sluiten' }).click()

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