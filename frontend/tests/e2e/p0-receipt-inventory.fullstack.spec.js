import { writeFileSync } from 'node:fs'
import { join } from 'node:path'
import { test, expect } from '@playwright/test'

const email = process.env.PLAYWRIGHT_L4_RECEIPT_EMAIL
const password = process.env.PLAYWRIGHT_L4_RECEIPT_PASSWORD
const householdName = process.env.PLAYWRIGHT_L4_RECEIPT_HOUSEHOLD
const locationName = process.env.PLAYWRIGHT_L4_RECEIPT_LOCATION

function required(name, value) {
  if (!String(value || '').trim()) throw new Error(`${name} ontbreekt voor L4-03`)
  return String(value).trim()
}

async function registerLocationsOnHousehold(page, accountEmail, accountPassword, expectedHouseholdName) {
  // Standard consumer onboarding is one atomic registration request.
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
  const result = await response.json()
  expect(result.onboarding?.onboarding_status).toBe('completed')
  expect(result.onboarding?.primary_use_case).toBe('wat_inhuis')
  expect(result.onboarding?.household_usage_mode).toBe('alone')
  expect(result.onboarding?.household_name).toBe(expectedHouseholdName)
  expect(result.onboarding?.product_configuration?.inventory_tracking_level).toBe('quantity')
  await expect(page).toHaveURL(/\/onboarding\/winkels$/)
  await expect(page.getByTestId('onboarding-stores-step')).toBeVisible()
  await page.getByTestId('onboarding-stores-later').click()
  await expect(page).toHaveURL(/\/home$/)

  // Locations are now an explicit post-onboarding preference, not a first-use question.
  // Keep this existing receipt/inventory authority's global-location scenario.
  await page.goto('/instellingen/mogelijkheden')
  await expect(page.getByTestId('settings-capabilities-page')).toBeVisible()
  await page.getByTestId('workflow-location-level').selectOption('global')
  const workflowResponsePromise = page.waitForResponse((response) => (
    new URL(response.url()).pathname === '/api/onboarding/workflow-preferences'
    && response.request().method() === 'PUT'
  ))
  await page.getByTestId('workflow-preferences-save').click()
  const workflowResponse = await workflowResponsePromise
  expect(workflowResponse.ok()).toBeTruthy()
  expect((await workflowResponse.json()).product_configuration?.location_tracking_level).toBe('global')
  await page.goto('/home')
}

async function readSession(page) {
  const response = await page.request.get('/api/session')
  expect(response.ok()).toBeTruthy()
  return response.json()
}

async function loadCanonicalReceiptFixture(request, baseURL) {
  const response = await request.get(`${baseURL}/api/testing/fixtures/receipt/file?kind=manual`)
  expect(response.ok(), 'Canonieke Jumbo-kassabonfixture moet beschikbaar zijn.').toBeTruthy()
  return { name: `l4-03-jumbo-${Date.now()}.jpg`, mimeType: 'image/jpeg', buffer: await response.body() }
}

function receiptIdFromImport(payload) {
  return String(payload?.receipt_table_id || payload?.receiptTableId || payload?.existing_receipt?.receipt_table_id || '').trim()
}

async function uploadReceiptThroughKassa(page, file) {
  // This canonical JPG depicts an older purchase. A new household must
  // retain it as history, outside the actionable Kassa projection.
  // Upload from Kassa so that its real Bonkop remains available for correction.
  await page.goto('/kassa')
  await expect(page.getByTestId('kassa-table')).toBeVisible({ timeout: 30_000 })
  const fileInput = page.getByTestId('kassa-manual-file-input')
  await expect(fileInput).toHaveCount(1)
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

  // Prove that historical receipts are preserved and cannot be processed as
  // current stock before the owner explicitly corrects the purchase date.
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

  // The following L4 test specifically verifies a CURRENT purchase flow.
  // Use the regular authorized Bonkop editor, not a test-only API bypass.
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

  // The receipt must be present in the actual Kassa server projection after
  // reloading; the temporary optimistic upload row is not sufficient proof.
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

async function openInventoryArticle(page, householdArticleId) {
  await page.goto('/voorraad')
  await expect(page.getByTestId('inventory-page')).toBeVisible({ timeout: 30_000 })
  const row = page.getByTestId(`inventory-row-${householdArticleId}`)
  await expect(row).toBeVisible({ timeout: 30_000 })
  const detailsResponsePromise = page.waitForResponse((response) => new URL(response.url()).pathname === `/api/household-articles/${encodeURIComponent(householdArticleId)}` && response.request().method() === 'GET')
  await row.locator('[title="Dubbelklik op de rij voor details"]').dblclick()
  const detailsResponse = await detailsResponsePromise
  expect(detailsResponse.ok()).toBeTruthy()
  await expect(page.getByTestId('article-detail-page')).toBeVisible({ timeout: 30_000 })
}

async function configureAlmostOutThreshold(page, minStock, idealStock) {
  await page.getByTestId('article-overview-subtab-household').click()
  const settingsSection = page.getByTestId('article-household-settings-section')
  await expect(settingsSection).toBeVisible()
  const minStockInput = page.getByTestId('article-details-input-min_stock')
  const idealStockInput = page.getByTestId('article-details-input-ideal_stock')

  if (!(await minStockInput.isVisible())) {
    const sectionToggle = settingsSection.getByRole('button', { name: 'Instellingen voor dit huishouden', exact: true })
    if ((await sectionToggle.count()) > 0 && (await sectionToggle.getAttribute('aria-expanded')) !== 'true') await sectionToggle.click()
  }

  await expect(minStockInput).toBeVisible()
  await expect(idealStockInput).toBeVisible()
  await minStockInput.fill(String(minStock))
  await idealStockInput.fill(String(idealStock))
  await expect(minStockInput).toHaveValue(String(minStock))
  await expect(idealStockInput).toHaveValue(String(idealStock))
  const settingsResponsePromise = page.waitForResponse((response) => response.url().includes('/api/household-articles/') && response.url().includes('/settings') && response.request().method() === 'PUT')
  await page.getByTestId('article-household-settings-save').click()
  expect((await settingsResponsePromise).ok()).toBeTruthy()

  await page.reload()
  await expect(page.getByTestId('article-detail-page')).toBeVisible({ timeout: 30_000 })
  await page.getByTestId('article-overview-subtab-household').click()
  const persistedSection = page.getByTestId('article-household-settings-section')
  await expect(persistedSection).toBeVisible()
  const persistedMinStockInput = page.getByTestId('article-details-input-min_stock')
  const persistedIdealStockInput = page.getByTestId('article-details-input-ideal_stock')
  if (!(await persistedMinStockInput.isVisible())) {
    const persistedToggle = persistedSection.getByRole('button', { name: 'Instellingen voor dit huishouden', exact: true })
    if ((await persistedToggle.count()) > 0 && (await persistedToggle.getAttribute('aria-expanded')) !== 'true') await persistedToggle.click()
  }
  await expect(persistedMinStockInput).toHaveValue(String(minStock))
  await expect(persistedIdealStockInput).toHaveValue(String(idealStock))
}

async function expectAlmostOutAbsence(page, articleName) {
  await page.goto('/bijna-op')
  await expect(page.getByTestId('almost-out-page')).toBeVisible({ timeout: 30_000 })
  const table = page.getByTestId('almost-out-table')
  await expect(table).toBeVisible()
  await expect(table.getByText(articleName, { exact: true })).toHaveCount(0)
}

async function expectAlmostOutPresence(page, articleName, finalQuantity, minStock) {
  await page.goto('/bijna-op')
  await expect(page.getByTestId('almost-out-page')).toBeVisible({ timeout: 30_000 })
  const table = page.getByTestId('almost-out-table')
  await expect(table).toBeVisible()
  const row = table.getByRole('row').filter({ hasText: articleName })
  await expect(row).toHaveCount(1)
  await expect(row).toContainText(String(finalQuantity))
  await expect(row).toContainText(String(minStock))
}

async function consumeThroughArticleStock(page, householdArticleId, inventoryId, consumeQuantity) {
  await openInventoryArticle(page, householdArticleId)
  await page.getByRole('tab', { name: 'Voorraad', exact: true }).click()
  const consumeButton = page.getByTestId(`article-stock-consume-${inventoryId}`)
  await expect(consumeButton).toBeVisible({ timeout: 20_000 })
  await consumeButton.click()
  const form = page.getByTestId('article-stock-mutation-form')
  await expect(form).toBeVisible()
  await form.getByLabel('Aantal afboeken').fill(String(consumeQuantity))
  await form.getByLabel('Reden / notitie').fill('L4-03 Bijna-op drempelovergang')
  const mutationResponsePromise = page.waitForResponse((response) => new URL(response.url()).pathname === `/api/household-articles/${encodeURIComponent(householdArticleId)}/inventory-events` && response.request().method() === 'POST')
  await form.getByRole('button', { name: 'Opslaan', exact: true }).click()
  expect((await mutationResponsePromise).ok()).toBeTruthy()
  await expect(page.getByTestId('app-feedback-success')).toContainText('Voorraad is afgeboekt.', { timeout: 20_000 })
}

test('prepare global-location unpacking household', async ({ page }) => {
  await registerLocationsOnHousehold(page, required('email', email), required('password', password), required('household', householdName))
  const session = await readSession(page)
  expect(session.role).toBe('admin')
  expect(String(session.active_household_id || '')).not.toBe('')
  writeFileSync('p0-receipt-inventory-setup.json', JSON.stringify({ householdId: session.active_household_id }))
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

test('L4-03 receipt -> Kassa -> approve -> Uitpakken -> location -> Voorraad -> history -> Bijna-op NEE -> JA', async ({ page, request }, testInfo) => {
  test.setTimeout(360_000)
  const accountEmail = required('PLAYWRIGHT_L4_RECEIPT_EMAIL', email).toLowerCase()
  const accountPassword = required('PLAYWRIGHT_L4_RECEIPT_PASSWORD', password)
  const expectedLocationName = required('PLAYWRIGHT_L4_RECEIPT_LOCATION', locationName)
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
  expect(line, `Geen gehele verwerkbare bonregel gevonden voor de Afboeken/Bijna-op-keten in ${JSON.stringify(batchBefore)}`).toBeTruthy()
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
  const locationCreatedDialog = page.getByRole('dialog', { name: 'Gelukt' })
  await expect(locationCreatedDialog).toContainText(`Locatie ${expectedLocationName} is toegevoegd en geselecteerd.`)
  await locationCreatedDialog.getByRole('button', { name: 'OK', exact: true }).click()
  await expect(locationCreatedDialog).toBeHidden()

  const lineSelect = page.getByTestId(`receipt-line-select-${lineId}`)
  if (!(await lineSelect.isChecked())) await lineSelect.check()
  const processResponsePromise = page.waitForResponse((response) => new URL(response.url()).pathname === `/api/purchase-import-batches/${batchId}/process` && response.request().method() === 'POST')
  await page.getByTestId('receipt-process-button').click()
  expect((await processResponsePromise).ok()).toBeTruthy()
  await expect(page.getByRole('dialog', { name: /^(Verwerking afgerond|Geselecteerde artikelen verwerkt)$/ })).toBeVisible({ timeout: 30_000 })
  await page.getByRole('dialog', { name: /^(Verwerking afgerond|Geselecteerde artikelen verwerkt)$/ }).getByRole('button', { name: 'OK' }).click()
  await expect(page.getByTestId(`receipt-line-${lineId}`)).toHaveCount(0, { timeout: 20_000 })
  // Verwerkte regels verdwijnen uit Uitpakken: controleer de echte bonstatus.
  const batchAfter = await readBatch(page, batchId)
  const processedLine = (batchAfter?.lines || []).find((item) => String(item.id) === lineId)
  expect(processedLine, JSON.stringify(batchAfter)).toBeTruthy()
  expect(String(processedLine.processing_status || '')).toBe('processed')
  expect(String(processedLine.processed_event_id || '')).not.toBe('')

  const inventoryResponse = await page.request.get('/api/dev/inventory-preview')
  expect(inventoryResponse.ok()).toBeTruthy()
  const inventory = await inventoryResponse.json()
  const inventoryRows = Array.isArray(inventory?.rows) ? inventory.rows : []
  const locationRows = inventoryRows.filter((item) => String(item?.locatie || '') === expectedLocationName)
  expect(locationRows.length).toBeGreaterThan(0)
  const targetInventory = locationRows.find((item) => Number(item?.aantal || 0) > 0 && String(item?.id || '').trim() && String(item?.household_article_id || '').trim())
  expect(targetInventory, JSON.stringify(locationRows)).toBeTruthy()

  const inventoryId = String(targetInventory.id)
  const householdArticleId = String(targetInventory.household_article_id)
  const articleName = String(targetInventory.artikel || targetInventory.household_article_name || '').trim()
  const initialQuantity = Number(targetInventory.aantal || 0)
  expect(articleName).not.toBe('')
  expect(Number.isInteger(initialQuantity)).toBeTruthy()
  expect(initialQuantity).toBeGreaterThan(0)
  const minStock = Math.max(initialQuantity - 1, 0)
  const idealStock = initialQuantity
  const consumeQuantity = 1
  const finalQuantity = initialQuantity - consumeQuantity

  await openInventoryArticle(page, householdArticleId)
  await configureAlmostOutThreshold(page, minStock, idealStock)
  await expectAlmostOutAbsence(page, articleName)
  await consumeThroughArticleStock(page, householdArticleId, inventoryId, consumeQuantity)
  await expectAlmostOutPresence(page, articleName, finalQuantity, minStock)

  writeFileSync(join(process.cwd(), 'p0-l4-03-browser-proof.json'), JSON.stringify({
    email: accountEmail, householdId, receiptId, batchId, lineId, locationName: expectedLocationName,
    inventoryId, householdArticleId, articleName, initialQuantity, minStock, idealStock, consumeQuantity, finalQuantity,
    almostOutBefore: false, almostOutAfter: true,
  }, null, 2))
  console.log('P0_L4_03_RECEIPT_INVENTORY_BROWSER_GREEN')
  console.log('P0_L4_03_ALMOST_OUT_TRANSITION_BROWSER_GREEN')
})
