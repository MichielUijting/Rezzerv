import { writeFileSync } from 'node:fs'
import { join } from 'node:path'
import { test, expect } from '@playwright/test'

const email = process.env.PLAYWRIGHT_L4_IDEMPOTENCY_EMAIL
const password = process.env.PLAYWRIGHT_L4_IDEMPOTENCY_PASSWORD
const householdName = process.env.PLAYWRIGHT_L4_IDEMPOTENCY_HOUSEHOLD
const locationName = process.env.PLAYWRIGHT_L4_IDEMPOTENCY_LOCATION

function required(name, value) {
  if (!String(value || '').trim()) throw new Error(`${name} ontbreekt voor L4-05`)
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
  expect(response.ok(), 'Canonieke Jumbo-kassabonfixture moet beschikbaar zijn.').toBeTruthy()
  return { name: `l4-05-jumbo-${Date.now()}.jpg`, mimeType: 'image/jpeg', buffer: await response.body() }
}

function receiptIdFromImport(payload) {
  return String(payload?.receipt_table_id || payload?.receiptTableId || payload?.existing_receipt?.receipt_table_id || '').trim()
}

async function uploadReceiptThroughKassa(page, file) {
  await page.goto('/kassa/nieuw')
  await expect(page.getByTestId('kassa-add-page')).toBeVisible()
  const fileInput = page.getByTestId('kassa-manual-file-input')
  const importResponsePromise = page.waitForResponse((response) => new URL(response.url()).pathname === '/api/receipts/import' && response.request().method() === 'POST', { timeout: 180_000 })
  await fileInput.setInputFiles(file)
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

function isTargetProcessResponse(response, batchId) {
  try {
    return new URL(response.url()).pathname === `/api/purchase-import-batches/${batchId}/process`
      && response.request().method() === 'POST'
  } catch {
    return false
  }
}

test('L4-05 duplicate Naar voorraad submission is idempotent for inventory and purchase events', async ({ page, request }, testInfo) => {
  test.setTimeout(360_000)
  const accountEmail = required('PLAYWRIGHT_L4_IDEMPOTENCY_EMAIL', email).toLowerCase()
  const accountPassword = required('PLAYWRIGHT_L4_IDEMPOTENCY_PASSWORD', password)
  const expectedHouseholdName = required('PLAYWRIGHT_L4_IDEMPOTENCY_HOUSEHOLD', householdName)
  const expectedLocationName = required('PLAYWRIGHT_L4_IDEMPOTENCY_LOCATION', locationName)
  const baseURL = required('PLAYWRIGHT_BASE_URL', testInfo.project.use.baseURL)

  await registerLocationsOnHousehold(page, accountEmail, accountPassword, expectedHouseholdName)
  const session = await readSession(page)
  expect(session.role).toBe('admin')
  const householdId = String(session.active_household_id || '')
  expect(householdId).not.toBe('')

  const fixture = await loadCanonicalReceiptFixture(request, baseURL)
  const receiptId = await uploadReceiptThroughKassa(page, fixture)
  await approveReceiptThroughKassa(page, receiptId)
  const approvedBatch = await resolveApprovedBatch(page, householdId, receiptId)
  const batchId = String(approvedBatch.batch_id || '')
  expect(batchId).not.toBe('')

  const batchBefore = await readBatch(page, batchId)
  const lines = Array.isArray(batchBefore?.lines) ? batchBefore.lines : []
  const line = lines.find((item) => {
    const quantity = Number(item?.quantity_raw || 0)
    return Number.isInteger(quantity) && quantity > 0 && String(item?.processing_status || '') !== 'processed'
  })
  expect(line, `Geen gehele verwerkbare bonregel gevonden in ${JSON.stringify(batchBefore)}`).toBeTruthy()
  const lineId = String(line.id)
  const expectedQuantity = Number(line.quantity_raw)

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
  const locationCreatedDialog = page.getByRole('dialog', { name: 'Gelukt' })
  await expect(locationCreatedDialog).toContainText(`Locatie ${expectedLocationName} is toegevoegd en geselecteerd.`)
  await locationCreatedDialog.getByRole('button', { name: 'OK', exact: true }).click()

  const lineSelect = page.getByTestId(`receipt-line-select-${lineId}`)
  if (!(await lineSelect.isChecked())) await lineSelect.check()

  const processResponses = []
  const onResponse = (response) => {
    if (isTargetProcessResponse(response, batchId)) processResponses.push(response)
  }
  page.on('response', onResponse)

  const processButton = page.getByTestId('receipt-process-button')
  await expect(processButton).toBeVisible()
  await expect(processButton).toBeEnabled()
  const box = await processButton.boundingBox()
  expect(box).toBeTruthy()

  // Twee echte browser-clicks binnen dezelfde gebruikersactie simuleren een dubbele submit/retry.
  await page.mouse.dblclick(box.x + box.width / 2, box.y + box.height / 2, { delay: 10 })

  await expect.poll(() => processResponses.length, {
    timeout: 60_000,
    message: 'L4-05 moet twee process-POSTs uit dezelfde dubbele browseractie observeren.',
  }).toBeGreaterThanOrEqual(2)

  const firstTwoStatuses = processResponses.slice(0, 2).map((response) => response.status())
  expect(firstTwoStatuses.every((status) => status >= 200 && status < 300), `Dubbele process-responses: ${firstTwoStatuses.join(', ')}`).toBeTruthy()
  page.off('response', onResponse)

  await expect(page.getByRole('dialog', { name: 'Verwerking afgerond' })).toBeVisible({ timeout: 30_000 })
  await page.getByRole('dialog', { name: 'Verwerking afgerond' }).getByRole('button', { name: 'Sluiten' }).click()

  const batchAfter = await readBatch(page, batchId)
  const processedLine = (batchAfter?.lines || []).find((item) => String(item?.id || '') === lineId)
  expect(processedLine, JSON.stringify(batchAfter)).toBeTruthy()
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

  const proof = {
    householdId,
    receiptId,
    batchId,
    lineId,
    expectedQuantity,
    processedEventId,
    householdArticleId,
    targetLocationId,
    processResponseCount: processResponses.length,
    processStatuses: firstTwoStatuses,
    browserInventoryTotal,
  }
  writeFileSync(join(process.cwd(), 'p0-l4-05-browser-proof.json'), JSON.stringify(proof, null, 2), 'utf8')

  console.log(`P0_L4_05_DUPLICATE_PROCESS_POSTS=${processResponses.length}`)
  console.log('P0_L4_05_BROWSER_IDEMPOTENCY_GREEN')
})
