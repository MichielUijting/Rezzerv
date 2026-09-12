import { writeFileSync } from 'node:fs'
import { join } from 'node:path'
import { test, expect } from '@playwright/test'

const email = process.env.PLAYWRIGHT_F6_RECEIPT_EMAIL
const password = process.env.PLAYWRIGHT_F6_RECEIPT_PASSWORD
const householdName = process.env.PLAYWRIGHT_F6_RECEIPT_HOUSEHOLD
const locationName = process.env.PLAYWRIGHT_F6_RECEIPT_LOCATION

function required(name, value) {
  if (!String(value || '').trim()) throw new Error(`${name} ontbreekt voor F6 Receipt`)
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
  return { name: `f6-receipt-${Date.now()}.jpg`, mimeType: 'image/jpeg', buffer: await response.body() }
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
  await expect(page.getByTestId(`kassa-row-${receiptId}`)).toHaveCount(0, { timeout: 30_000 })
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

async function almostOutRowCount(page) {
  await page.goto('/bijna-op')
  await expect(page.getByTestId('almost-out-page')).toBeVisible({ timeout: 30_000 })
  const table = page.getByTestId('almost-out-table')
  await expect(table).toBeVisible()
  return table.getByRole('row').count()
}

function lineById(batch, lineId) {
  return (Array.isArray(batch?.lines) ? batch.lines : []).find((item) => String(item?.id || '') === String(lineId))
}

test('prepare global-location unpacking household', async ({ page }) => {
  await registerLocationsOnHousehold(page, required('email', email), required('password', password), required('household', householdName))
  const session = await readSession(page)
  expect(session.role).toBe('admin')
  expect(String(session.active_household_id || '')).not.toBe('')
  writeFileSync('f6-receipt-controlled-5xx-setup.json', JSON.stringify({ householdId: session.active_household_id }))
})

async function loginConfiguredHousehold(page, accountEmail, accountPassword) {
  await page.goto('/login')
  await page.getByTestId('login-email').fill(accountEmail)
  await page.getByTestId('login-password').fill(accountPassword)
  const responsePromise = page.waitForResponse(response => new URL(response.url()).pathname === '/api/auth/login' && response.request().method() === 'POST')
  await page.getByTestId('login-submit').click()
  expect((await responsePromise).ok()).toBeTruthy()
  await expect(page).toHaveURL(/\/home$/)
  const response = await page.request.get('/api/onboarding/capabilities')
  expect(response.ok()).toBeTruthy()
  const capabilities = await response.json()
  expect(capabilities.product_configuration.unpacking_enabled).toBe(true)
  expect(capabilities.product_configuration.location_tracking_level).toBe('global')
}

test('F6-01 Receipt controlled 500 shows standard feedback and rolls full receipt transaction back', async ({ page, request }, testInfo) => {
  test.setTimeout(360_000)
  const accountEmail = required('PLAYWRIGHT_F6_RECEIPT_EMAIL', email).toLowerCase()
  const accountPassword = required('PLAYWRIGHT_F6_RECEIPT_PASSWORD', password)
  const expectedLocationName = required('PLAYWRIGHT_F6_RECEIPT_LOCATION', locationName)
  const baseURL = required('PLAYWRIGHT_BASE_URL', testInfo.project.use.baseURL)

  await loginConfiguredHousehold(page, accountEmail, accountPassword)
  const session = await readSession(page)
  expect(session.role).toBe('admin')
  const householdId = String(session.active_household_id || '')
  expect(householdId).not.toBe('')

  const fixture = await loadCanonicalReceiptFixture(request, baseURL)
  const receiptId = await uploadReceiptThroughKassa(page, fixture)
  await approveReceiptThroughKassa(page, receiptId)
  const approvedBatch = await resolveApprovedBatch(page, householdId, receiptId)
  const batchId = String(approvedBatch.batch_id)
  const batchBefore = await readBatch(page, batchId)
  const lines = Array.isArray(batchBefore?.lines) ? batchBefore.lines : []
  const line = lines.find((item) => {
    const quantity = Number(item?.quantity_raw || 0)
    return Number.isInteger(quantity) && quantity > 0 && String(item?.processing_status || '') !== 'processed'
  })
  expect(line, `Geen verwerkbare bonregel gevonden in ${JSON.stringify(batchBefore)}`).toBeTruthy()
  const lineId = String(line.id)

  await page.goto(`/kassabonnen?batch=${encodeURIComponent(batchId)}`)
  await expect(page.getByTestId('receipts-page')).toBeVisible()
  await expect(page.getByTestId(`receipt-line-${lineId}`)).toBeVisible({ timeout: 30_000 })
  const locationButton = page.getByTestId(`receipt-line-location-select-${lineId}`)
  await locationButton.click()
  const locationDialog = page.getByRole('dialog', { name: 'Locatie / sublocatie kiezen' })
  await expect(locationDialog).toBeVisible()
  await page.getByTestId('receipt-location-create-space').click()
  await page.getByTestId('receipt-location-create-name').fill(expectedLocationName)
  await page.getByTestId('receipt-location-create-save').click()
  await expect(locationButton).toContainText(expectedLocationName, { timeout: 20_000 })
  const createdDialog = page.getByRole('dialog', { name: 'Gelukt' })
  await expect(createdDialog).toContainText(`Locatie ${expectedLocationName} is toegevoegd en geselecteerd.`)
  await createdDialog.getByRole('button', { name: 'OK', exact: true }).click()

  const persistedBefore = await readBatch(page, batchId)
  const lineBefore = lineById(persistedBefore, lineId)
  expect(lineBefore).toBeTruthy()
  const batchProcessingStatusBefore = String(persistedBefore?.processing_status || '')
  const lineProcessingStatusBefore = String(lineBefore?.processing_status || '')
  const processedEventIdBefore = lineBefore?.processed_event_id ?? null
  expect(lineProcessingStatusBefore).not.toBe('processed')
  expect(processedEventIdBefore).toBeNull()

  const almostOutRowsBefore = await almostOutRowCount(page)

  await page.goto(`/kassabonnen?batch=${encodeURIComponent(batchId)}`)
  await expect(page.getByTestId(`receipt-line-${lineId}`)).toBeVisible({ timeout: 30_000 })
  const lineSelect = page.getByTestId(`receipt-line-select-${lineId}`)
  if (!(await lineSelect.isChecked())) await lineSelect.check()

  const processResponsePromise = page.waitForResponse((response) => new URL(response.url()).pathname === `/api/purchase-import-batches/${batchId}/process` && response.request().method() === 'POST')
  await page.getByTestId('receipt-process-button').click()
  const processResponse = await processResponsePromise
  expect(processResponse.status()).toBe(500)
  await expect(page.getByText('Verwerken van bonregels is mislukt.', { exact: true })).toBeVisible({ timeout: 30_000 })
  await expect(page.getByText(/Interne serverfout in de API/)).toHaveCount(0)

  await page.reload()
  await expect(page.getByTestId('receipts-page')).toBeVisible({ timeout: 30_000 })
  await expect(page.getByTestId(`receipt-line-${lineId}`)).toBeVisible({ timeout: 30_000 })

  const batchAfter = await readBatch(page, batchId)
  const lineAfter = lineById(batchAfter, lineId)
  expect(lineAfter).toBeTruthy()
  expect(String(batchAfter?.processing_status || '')).toBe(batchProcessingStatusBefore)
  expect(String(lineAfter?.processing_status || '')).toBe(lineProcessingStatusBefore)
  expect(lineAfter?.processed_event_id ?? null).toBe(processedEventIdBefore)

  const inventoryResponse = await page.request.get('/api/dev/inventory-preview')
  expect(inventoryResponse.ok()).toBeTruthy()
  const inventoryPayload = await inventoryResponse.json()
  const inventoryRows = Array.isArray(inventoryPayload?.rows) ? inventoryPayload.rows : []
  expect(inventoryRows).toHaveLength(0)

  const almostOutRowsAfter = await almostOutRowCount(page)
  expect(almostOutRowsAfter).toBe(almostOutRowsBefore)

  writeFileSync(join(process.cwd(), 'f6-receipt-controlled-5xx-browser-proof.json'), JSON.stringify({
    email: accountEmail,
    householdId,
    receiptId,
    batchId,
    lineId,
    locationName: expectedLocationName,
    batchProcessingStatusBefore,
    lineProcessingStatusBefore,
    processedEventIdBefore,
    almostOutRowsBefore,
    almostOutRowsAfter,
    processStatus: processResponse.status(),
    inventoryRowsAfter: inventoryRows.length,
  }, null, 2))

  console.log('F6_RECEIPT_REAL_500_FEEDBACK_GREEN')
  console.log('F6_RECEIPT_BROWSER_ROLLBACK_GREEN')
  console.log('F6_RECEIPT_ALMOST_OUT_UNCHANGED_GREEN')
})
