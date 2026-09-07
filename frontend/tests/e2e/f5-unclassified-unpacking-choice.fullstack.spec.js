import { writeFileSync } from 'node:fs'
import { test, expect } from '@playwright/test'

const email = process.env.PLAYWRIGHT_F5_09_EMAIL
const password = process.env.PLAYWRIGHT_F5_09_PASSWORD
const householdName = process.env.PLAYWRIGHT_F5_09_HOUSEHOLD

function required(name, value) {
  if (!String(value || '').trim()) throw new Error(`${name} ontbreekt voor F5-09`)
  return String(value).trim()
}

async function registerLocationsOffHousehold(page, accountEmail, accountPassword, expectedHouseholdName) {
  await page.goto('/registreren')
  await expect(page.getByTestId('register-page')).toBeVisible()
  await page.getByTestId('register-email').fill(accountEmail)
  await page.getByTestId('register-password').fill(accountPassword)
  await page.getByTestId('register-password-repeat').fill(accountPassword)

  const registration = page.waitForResponse((response) => (
    response.url().includes('/api/auth/register') && response.request().method() === 'POST'
  ))
  await page.getByTestId('register-submit').click()
  expect((await registration).status()).toBe(201)

  await expect(page.getByTestId('onboarding-use-case-page')).toBeVisible()
  await page.getByTestId('onboarding-choice-wat_inhuis').check()
  const primary = page.waitForResponse((response) => (
    response.url().includes('/api/onboarding/primary-use-case') && response.request().method() === 'POST'
  ))
  await page.getByTestId('onboarding-primary-continue').click()
  expect((await primary).ok()).toBeTruthy()

  await expect(page.getByTestId('onboarding-wat-inhuis-follow-up')).toBeVisible()
  await page.getByTestId('wat-inhuis-tracking-quantity').check()
  await page.getByTestId('wat-inhuis-global-locations-no').check()
  await page.getByTestId('wat-inhuis-almost-out-yes').check()
  await page.getByTestId('wat-inhuis-shopping-yes').check()
  const product = page.waitForResponse((response) => (
    response.url().includes('/api/onboarding/wat-inhuis') && response.request().method() === 'POST'
  ))
  await page.getByTestId('wat-inhuis-finish').click()
  expect((await product).ok()).toBeTruthy()

  await expect(page.getByTestId('onboarding-shared-household-minimum')).toBeVisible()
  await page.getByTestId('shared-household-name').fill(expectedHouseholdName)
  await page.getByTestId('shared-household-usage-alone').check()
  const household = page.waitForResponse((response) => (
    response.url().includes('/api/onboarding/shared-household-minimum') && response.request().method() === 'POST'
  ))
  await page.getByTestId('shared-household-finish').click()
  expect((await household).ok()).toBeTruthy()
  await expect(page).toHaveURL(/\/home$/)

  const capabilitiesResponse = await page.request.get('/api/onboarding/capabilities')
  expect(capabilitiesResponse.ok()).toBeTruthy()
  const capabilities = await capabilitiesResponse.json()
  expect(capabilities.product_configuration.location_tracking_level).toBe('none')
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
  await page.goto('/kassa/nieuw')
  await expect(page.getByTestId('kassa-add-page')).toBeVisible()
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

test('F5-09 Niet ingedeeld is a valid unpacking choice', async ({ page, request }, testInfo) => {
  test.setTimeout(360_000)
  const accountEmail = required('PLAYWRIGHT_F5_09_EMAIL', email).toLowerCase()
  const accountPassword = required('PLAYWRIGHT_F5_09_PASSWORD', password)
  const expectedHouseholdName = required('PLAYWRIGHT_F5_09_HOUSEHOLD', householdName)
  const baseURL = required('PLAYWRIGHT_BASE_URL', testInfo.project.use.baseURL)

  await registerLocationsOffHousehold(page, accountEmail, accountPassword, expectedHouseholdName)
  const session = await readSession(page)
  expect(session.role).toBe('admin')
  const householdId = String(session.active_household_id || '')
  expect(householdId).not.toBe('')

  const receiptId = await uploadReceiptThroughKassa(page, await loadCanonicalReceiptFixture(request, baseURL))
  await approveReceiptThroughKassa(page, receiptId)
  const batchId = String((await resolveApprovedBatch(page, householdId, receiptId)).batch_id)
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
  const groupSelect = page.getByTestId(`receipt-line-article-group-select-${lineId}`)
  await expect(groupSelect).toBeVisible({ timeout: 30_000 })
  await expect(groupSelect.locator('option[value=""]')).toHaveText('Niet ingedeeld')
  await groupSelect.selectOption('')
  await expect(groupSelect).toHaveValue('')

  const lineSelect = page.getByTestId(`receipt-line-select-${lineId}`)
  if (!(await lineSelect.isChecked())) await lineSelect.check()
  await expect(page.getByTestId('receipt-process-button')).toBeEnabled()

  const processResponsePromise = page.waitForResponse((response) => (
    new URL(response.url()).pathname === `/api/purchase-import-batches/${batchId}/process`
      && response.request().method() === 'POST'
  ))
  await page.getByTestId('receipt-process-button').click()
  const processResponse = await processResponsePromise
  expect(processResponse.ok()).toBeTruthy()
  const processPayload = await processResponse.json()
  expect(Number(processPayload?.processed_count || 0), JSON.stringify(processPayload)).toBeGreaterThanOrEqual(1)
  expect(JSON.stringify(processPayload)).not.toContain('Nog geen artikelgroep gekozen')

  await expect(page.getByRole('dialog', { name: 'Verwerking afgerond' })).toBeVisible({ timeout: 30_000 })
  await page.getByRole('dialog', { name: 'Verwerking afgerond' }).getByRole('button', { name: 'Sluiten' }).click()
  await expect(page.getByTestId(`receipt-line-${lineId}`)).toHaveCount(0, { timeout: 20_000 })

  const batchAfter = await readBatch(page, batchId)
  const processedLine = (Array.isArray(batchAfter?.lines) ? batchAfter.lines : []).find((item) => String(item?.id || '') === lineId)
  expect(processedLine).toBeTruthy()
  expect(String(processedLine.processing_status || '')).toBe('processed')
  expect(String(processedLine.article_group_id || '')).toBe('')
  expect(String(processedLine.processed_event_id || '')).not.toBe('')

  writeFileSync('f5-09-browser-proof.json', JSON.stringify({
    householdId,
    receiptId,
    batchId,
    lineId,
    processedEventId: String(processedLine.processed_event_id),
    articleGroupId: null,
    locationTrackingLevel: 'none',
  }, null, 2))

  console.log('F5_09_UNCLASSIFIED_UNPACKING_BROWSER_GREEN')
})
