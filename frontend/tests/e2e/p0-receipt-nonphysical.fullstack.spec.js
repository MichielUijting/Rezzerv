import { readFileSync, writeFileSync } from 'node:fs'
import { test, expect } from '@playwright/test'

const email = process.env.PLAYWRIGHT_P0_NONPHYSICAL_EMAIL
const password = process.env.PLAYWRIGHT_P0_NONPHYSICAL_PASSWORD
const householdName = process.env.PLAYWRIGHT_P0_NONPHYSICAL_HOUSEHOLD
const fixturePath = process.env.PLAYWRIGHT_P0_NONPHYSICAL_FIXTURE

function required(name, value) {
  if (!String(value || '').trim()) throw new Error(`${name} ontbreekt voor P0 nonphysical receipt authority`)
  return String(value).trim()
}

async function registerLocationsOnHousehold(page, accountEmail, accountPassword, expectedHouseholdName) {
  await page.goto('/registreren')
  await expect(page.getByTestId('register-page')).toBeVisible()
  await page.getByTestId('register-email').fill(accountEmail)
  await page.getByTestId('register-password').fill(accountPassword)
  await page.getByTestId('register-password-repeat').fill(accountPassword)
  const registration = page.waitForResponse((response) => response.url().includes('/api/auth/register') && response.request().method() === 'POST')
  await page.getByTestId('register-submit').click()
  expect((await registration).status()).toBe(201)

  await expect(page.getByTestId('onboarding-use-case-page')).toBeVisible()
  await page.getByTestId('onboarding-choice-wat_inhuis').check()
  const primary = page.waitForResponse((response) => response.url().includes('/api/onboarding/primary-use-case') && response.request().method() === 'POST')
  await page.getByTestId('onboarding-primary-continue').click()
  expect((await primary).ok()).toBeTruthy()

  await expect(page.getByTestId('onboarding-wat-inhuis-follow-up')).toBeVisible()
  await page.getByTestId('wat-inhuis-tracking-quantity').check()
  await page.getByTestId('wat-inhuis-global-locations-yes').check()
  await page.getByTestId('wat-inhuis-almost-out-yes').check()
  await page.getByTestId('wat-inhuis-shopping-yes').check()
  const product = page.waitForResponse((response) => response.url().includes('/api/onboarding/wat-inhuis') && response.request().method() === 'POST')
  await page.getByTestId('wat-inhuis-finish').click()
  expect((await product).ok()).toBeTruthy()

  await expect(page.getByTestId('onboarding-shared-household-minimum')).toBeVisible()
  await page.getByTestId('shared-household-name').fill(expectedHouseholdName)
  await page.getByTestId('shared-household-usage-alone').check()
  const household = page.waitForResponse((response) => response.url().includes('/api/onboarding/shared-household-minimum') && response.request().method() === 'POST')
  await page.getByTestId('shared-household-finish').click()
  expect((await household).ok()).toBeTruthy()
  await expect(page).toHaveURL(/\/home$/)
}

async function readSession(page) {
  const response = await page.request.get('/api/session')
  expect(response.ok()).toBeTruthy()
  return response.json()
}

function receiptIdFromImport(payload) {
  return String(payload?.receipt_table_id || payload?.receiptTableId || payload?.existing_receipt?.receipt_table_id || '').trim()
}

function supportedEmlFixture(sourcePath) {
  const body = readFileSync(sourcePath, 'utf8').trimEnd()
  const eml = [
    'From: kassabon@jumbo.example',
    'To: rezzerv-test@example.com',
    'Subject: Jumbo kassabon met koopzegels',
    'MIME-Version: 1.0',
    'Content-Type: text/plain; charset=UTF-8',
    'Content-Transfer-Encoding: 8bit',
    '',
    body,
    '',
  ].join('\r\n')
  return {
    name: `p0-nonphysical-jumbo-${Date.now()}.eml`,
    mimeType: 'message/rfc822',
    buffer: Buffer.from(eml, 'utf8'),
  }
}

async function uploadReceiptThroughKassa(page, sourcePath) {
  const path = supportedEmlFixture(sourcePath)
  await page.goto('/kassa/nieuw')
  await expect(page.getByTestId('kassa-add-page')).toBeVisible()
  const importResponsePromise = page.waitForResponse((response) => (
    new URL(response.url()).pathname === '/api/receipts/picnic-email-import' && response.request().method() === 'POST'
  ), { timeout: 180_000 })
  await page.getByTestId('kassa-manual-file-input').setInputFiles(path)
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

async function inspectAndApproveReceipt(page, receiptId) {
  await page.goto('/kassa')
  const row = page.getByTestId(`kassa-row-${receiptId}`)
  await expect(row).toBeVisible({ timeout: 60_000 })
  await row.dblclick()
  await expect(page.getByTestId('receipt-detail-page')).toBeVisible({ timeout: 30_000 })
  const receiptTable = page.getByTestId('receipt-lines-table')
  await expect(receiptTable).toBeVisible({ timeout: 30_000 })
  const articleInputs = receiptTable.locator('tbody tr td:nth-child(2) input')
  await expect.poll(
    async () => articleInputs.evaluateAll((inputs) => inputs.map((input) => String(input.value || '')).join('\n')),
    { timeout: 12_000 },
  ).toMatch(/KOOPZEGELS/i)

  const approval = page.waitForResponse((response) => (
    new URL(response.url()).pathname === `/api/receipts/${receiptId}/approve` && response.request().method() === 'POST'
  ))
  await page.getByRole('button', { name: 'Goedkeuren', exact: true }).click()
  expect((await approval).ok()).toBeTruthy()
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

async function createSpaceThroughUi(page, locationName) {
  await page.goto('/instellingen/locaties')
  await expect(page.getByTestId('settings-locations-page')).toBeVisible({ timeout: 30_000 })
  await page.locator('#new-main-location').fill(locationName)
  const createPromise = page.waitForResponse((response) => (
    new URL(response.url()).pathname === '/api/spaces' && response.request().method() === 'POST'
  ))
  await page.getByTestId('new-main-location-row').getByRole('button', { name: 'Toevoegen', exact: true }).click()
  expect((await createPromise).ok()).toBeTruthy()
}

async function assignLocationToLine(page, lineId, locationName) {
  const locationButton = page.getByTestId(`receipt-line-location-select-${lineId}`)
  await expect(locationButton).toBeVisible({ timeout: 30_000 })
  await locationButton.click()
  const dialog = page.getByRole('dialog', { name: 'Locatie kiezen' })
  await expect(dialog).toBeVisible()
  const savePromise = page.waitForResponse((response) => (
    response.url().includes(`/api/purchase-import-lines/${lineId}/target-location`) && response.request().method() === 'POST'
  ))
  await dialog.getByRole('button', { name: locationName, exact: true }).click()
  const response = await savePromise
  expect(response.ok()).toBeTruthy()
  const payload = await response.json()
  return String(payload?.target_location_id || payload?.resolved_location?.location_id || payload?.resolved_location?.space_id || '').trim()
}

async function processOnePhysicalLine(page, batchId, batchBefore, locationName) {
  const lines = Array.isArray(batchBefore?.lines) ? batchBefore.lines : []
  expect(lines.length, JSON.stringify(batchBefore)).toBeGreaterThan(0)
  expect(lines.some((item) => /koopzegel/i.test(String(item?.article_name_raw || item?.external_article_code || '')))).toBe(false)

  const targetLine = lines.find((item) => {
    const quantity = Number(item?.quantity_raw || 0)
    return Number.isInteger(quantity) && quantity > 0 && String(item?.processing_status || '') !== 'processed'
  })
  expect(targetLine, `Geen fysieke doelregel gevonden in ${JSON.stringify(batchBefore)}`).toBeTruthy()
  const lineId = String(targetLine.id)

  await page.goto(`/kassabonnen?batch=${encodeURIComponent(batchId)}`)
  await expect(page.getByTestId('receipts-page')).toBeVisible()
  await expect(page.getByTestId('receipt-lines-table')).not.toContainText(/KOOPZEGELS/i)

  const groupSelect = page.getByTestId(`receipt-line-article-group-select-${lineId}`)
  await expect(groupSelect).toBeVisible({ timeout: 30_000 })
  await expect(groupSelect.locator('option[value=""]')).toHaveText('Niet ingedeeld')
  await groupSelect.selectOption('')

  const targetLocationId = await assignLocationToLine(page, lineId, locationName)
  expect(targetLocationId).not.toBe('')

  for (const item of lines) {
    const select = page.getByTestId(`receipt-line-select-${String(item.id)}`)
    if ((await select.count()) === 0) continue
    if (String(item.id) === lineId) {
      if (!(await select.isChecked())) await select.check()
    } else if (await select.isChecked()) {
      await select.uncheck()
    }
  }

  await expect(page.getByTestId('receipt-process-button')).toBeEnabled()
  const processResponsePromise = page.waitForResponse((response) => (
    new URL(response.url()).pathname === `/api/purchase-import-batches/${batchId}/process` && response.request().method() === 'POST'
  ))
  await page.getByTestId('receipt-process-button').click()
  const response = await processResponsePromise
  expect(response.ok()).toBeTruthy()
  const payload = await response.json()
  expect(Number(payload?.processed_count || 0), JSON.stringify(payload)).toBeGreaterThanOrEqual(1)
  await expect(page.getByRole('dialog', { name: 'Verwerking afgerond' })).toBeVisible({ timeout: 30_000 })
  await page.getByRole('dialog', { name: 'Verwerking afgerond' }).getByRole('button', { name: 'Sluiten' }).click()

  const batchAfter = await readBatch(page, batchId)
  const processedLine = (Array.isArray(batchAfter?.lines) ? batchAfter.lines : []).find((item) => String(item?.id || '') === lineId)
  expect(processedLine).toBeTruthy()
  expect(String(processedLine.processing_status || '')).toBe('processed')
  expect(String(processedLine.processed_event_id || '')).not.toBe('')
  return { processedLine, targetLocationId }
}

test('prepare global-location unpacking household', async ({ page }) => {
  await registerLocationsOnHousehold(page, required('email', email), required('password', password), required('household', householdName))
  const session = await readSession(page)
  expect(session.role).toBe('admin')
  expect(String(session.active_household_id || '')).not.toBe('')
  writeFileSync('p0-receipt-nonphysical-setup.json', JSON.stringify({ householdId: session.active_household_id }))
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

test('P0 nonphysical receipt line stays in Kassa and never mutates inventory', async ({ page }) => {
  test.setTimeout(360_000)
  const accountEmail = required('PLAYWRIGHT_P0_NONPHYSICAL_EMAIL', email).toLowerCase()
  const accountPassword = required('PLAYWRIGHT_P0_NONPHYSICAL_PASSWORD', password)
  const receiptFixturePath = required('PLAYWRIGHT_P0_NONPHYSICAL_FIXTURE', fixturePath)
  const locationName = `P0 nonphysical ${Date.now()}`

  await loginConfiguredHousehold(page, accountEmail, accountPassword)
  const session = await readSession(page)
  expect(session.role).toBe('admin')
  const householdId = String(session.active_household_id || '')
  expect(householdId).not.toBe('')
  await createSpaceThroughUi(page, locationName)

  const receiptId = await uploadReceiptThroughKassa(page, receiptFixturePath)
  await inspectAndApproveReceipt(page, receiptId)
  const approvedBatch = await resolveApprovedBatch(page, householdId, receiptId)
  const batchId = String(approvedBatch.batch_id)
  const batchBefore = await readBatch(page, batchId)
  const { processedLine, targetLocationId } = await processOnePhysicalLine(page, batchId, batchBefore, locationName)

  const inventoryResponse = await page.request.get('/api/dev/inventory-preview')
  expect(inventoryResponse.ok()).toBeTruthy()
  const inventoryPayload = await inventoryResponse.json()
  const inventoryRows = Array.isArray(inventoryPayload?.rows) ? inventoryPayload.rows : []
  expect(inventoryRows.some((row) => /koopzegel/i.test(String(row?.artikel || row?.household_article_name || '')))).toBe(false)

  await page.goto('/bijna-op')
  await expect(page.getByTestId('almost-out-page')).toBeVisible({ timeout: 30_000 })
  await expect(page.getByTestId('almost-out-table')).not.toContainText(/KOOPZEGELS/i)

  writeFileSync('p0-nonphysical-browser-proof.json', JSON.stringify({
    householdId,
    receiptId,
    batchId,
    processedPhysicalLineId: String(processedLine.id),
    processedPhysicalEventId: String(processedLine.processed_event_id),
    processedPhysicalExternalRef: String(processedLine.external_line_ref || ''),
    targetLocationId,
    nonphysicalLabel: 'KOOPZEGELS',
  }, null, 2))

  console.log('P0_NONPHYSICAL_RECEIPT_BROWSER_GREEN')
  console.log('P0_NONPHYSICAL_NO_INVENTORY_MUTATION_BROWSER_GREEN')
})
