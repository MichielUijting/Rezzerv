import { writeFileSync } from 'node:fs'
import { test, expect } from '@playwright/test'

const email = process.env.PLAYWRIGHT_L4_04_EMAIL
const password = process.env.PLAYWRIGHT_L4_04_PASSWORD
const householdName = process.env.PLAYWRIGHT_L4_04_HOUSEHOLD

function required(name, value) {
  if (!String(value || '').trim()) throw new Error(`${name} ontbreekt voor L4-04`)
  return String(value).trim()
}

async function registerLocationsOffHousehold(page, accountEmail, accountPassword, expectedHouseholdName) {
  await page.goto('/registreren')
  await expect(page.getByTestId('register-page')).toBeVisible()
  await page.getByTestId('register-email').fill(accountEmail)
  await page.getByTestId('register-password').fill(accountPassword)
  await page.getByTestId('register-password-repeat').fill(accountPassword)

  const registrationResponsePromise = page.waitForResponse((response) => (
    response.url().includes('/api/auth/register') && response.request().method() === 'POST'
  ))
  await page.getByTestId('register-submit').click()
  expect((await registrationResponsePromise).status()).toBe(201)

  await expect(page.getByTestId('onboarding-use-case-page')).toBeVisible()
  await page.getByTestId('onboarding-choice-wat_inhuis').check()
  const primaryResponsePromise = page.waitForResponse((response) => (
    response.url().includes('/api/onboarding/primary-use-case') && response.request().method() === 'POST'
  ))
  await page.getByTestId('onboarding-primary-continue').click()
  expect((await primaryResponsePromise).ok()).toBeTruthy()

  await expect(page.getByTestId('onboarding-wat-inhuis-follow-up')).toBeVisible()
  await page.getByTestId('wat-inhuis-tracking-quantity').check()
  await page.getByTestId('wat-inhuis-global-locations-no').check()
  await page.getByTestId('wat-inhuis-almost-out-yes').check()
  await page.getByTestId('wat-inhuis-shopping-yes').check()
  const productResponsePromise = page.waitForResponse((response) => (
    response.url().includes('/api/onboarding/wat-inhuis') && response.request().method() === 'POST'
  ))
  await page.getByTestId('wat-inhuis-finish').click()
  expect((await productResponsePromise).ok()).toBeTruthy()

  await expect(page.getByTestId('onboarding-shared-household-minimum')).toBeVisible()
  await page.getByTestId('shared-household-name').fill(expectedHouseholdName)
  await page.getByTestId('shared-household-usage-alone').check()
  const householdResponsePromise = page.waitForResponse((response) => (
    response.url().includes('/api/onboarding/shared-household-minimum') && response.request().method() === 'POST'
  ))
  await page.getByTestId('shared-household-finish').click()
  expect((await householdResponsePromise).ok()).toBeTruthy()
  await expect(page).toHaveURL(/\/home$/)

  const capabilitiesResponse = await page.request.get('/api/onboarding/capabilities')
  expect(capabilitiesResponse.ok()).toBeTruthy()
  const capabilities = await capabilitiesResponse.json()
  expect(capabilities.product_configuration.location_tracking_level).toBe('none')
  await expect(page.getByTestId('home-tile-locaties')).toHaveCount(0)
}

async function readSession(page) {
  const response = await page.request.get('/api/session')
  expect(response.ok()).toBeTruthy()
  return response.json()
}

async function loadCanonicalReceiptFixture(request, baseURL) {
  const response = await request.get(`${baseURL}/api/testing/fixtures/receipt/file?kind=manual`)
  expect(response.ok(), 'Canonieke Jumbo-kassabonfixture moet beschikbaar zijn.').toBeTruthy()
  return { name: `l4-04-jumbo-${Date.now()}.jpg`, mimeType: 'image/jpeg', buffer: await response.body() }
}

function receiptIdFromImport(payload) {
  return String(payload?.receipt_table_id || payload?.receiptTableId || payload?.existing_receipt?.receipt_table_id || '').trim()
}

async function uploadReceiptThroughKassa(page, file) {
  await page.goto('/kassa/nieuw')
  await expect(page.getByTestId('kassa-add-page')).toBeVisible()
  const importResponsePromise = page.waitForResponse((response) => (
    new URL(response.url()).pathname === '/api/receipts/import' && response.request().method() === 'POST'
  ), { timeout: 180_000 })
  await page.getByTestId('kassa-manual-file-input').setInputFiles(file)
  const response = await importResponsePromise
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
  const approvalResponsePromise = page.waitForResponse((response) => (
    new URL(response.url()).pathname === `/api/receipts/${receiptId}/approve` && response.request().method() === 'POST'
  ))
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

async function openInventoryArticle(page, householdArticleId) {
  await page.goto('/voorraad')
  await expect(page.getByTestId('inventory-page')).toBeVisible({ timeout: 30_000 })
  const row = page.getByTestId(`inventory-row-${householdArticleId}`)
  await expect(row).toBeVisible({ timeout: 30_000 })
  await row.locator('[title="Dubbelklik op de rij voor details"]').dblclick()
  await expect(page.getByTestId('article-detail-page')).toBeVisible({ timeout: 30_000 })
}

async function configureAlmostOutThreshold(page, minStock, idealStock) {
  await page.getByTestId('article-overview-subtab-household').click()
  const section = page.getByTestId('article-household-settings-section')
  await expect(section).toBeVisible()
  const minStockInput = page.getByTestId('article-details-input-min_stock')
  const idealStockInput = page.getByTestId('article-details-input-ideal_stock')
  if (!(await minStockInput.isVisible())) {
    const toggle = section.getByRole('button', { name: 'Instellingen voor dit huishouden', exact: true })
    if ((await toggle.count()) > 0 && (await toggle.getAttribute('aria-expanded')) !== 'true') await toggle.click()
  }
  await minStockInput.fill(String(minStock))
  await idealStockInput.fill(String(idealStock))
  const savePromise = page.waitForResponse((response) => (
    response.url().includes('/api/household-articles/') && response.url().includes('/settings') && response.request().method() === 'PUT'
  ))
  await page.getByTestId('article-household-settings-save').click()
  expect((await savePromise).ok()).toBeTruthy()
}

async function consumeThroughArticleStock(page, householdArticleId, inventoryId, consumeQuantity) {
  await openInventoryArticle(page, householdArticleId)
  await page.getByRole('tab', { name: 'Voorraad', exact: true }).click()
  await page.getByTestId(`article-stock-consume-${inventoryId}`).click()
  const form = page.getByTestId('article-stock-mutation-form')
  await expect(form).toBeVisible()
  await form.getByLabel('Aantal afboeken').fill(String(consumeQuantity))
  await form.getByLabel('Reden / notitie').fill('L4-04 locaties UIT Bijna-op drempelovergang')
  const mutationPromise = page.waitForResponse((response) => (
    new URL(response.url()).pathname === `/api/household-articles/${encodeURIComponent(householdArticleId)}/inventory-events`
    && response.request().method() === 'POST'
  ))
  await form.getByRole('button', { name: 'Opslaan', exact: true }).click()
  expect((await mutationPromise).ok()).toBeTruthy()
  await expect(page.getByTestId('article-stock-mutation-success')).toContainText('Voorraad is afgeboekt.')
}

test('L4-04 receipt chain works with locations OFF and no location UI/validation', async ({ page, request }, testInfo) => {
  test.setTimeout(360_000)
  const accountEmail = required('PLAYWRIGHT_L4_04_EMAIL', email).toLowerCase()
  const accountPassword = required('PLAYWRIGHT_L4_04_PASSWORD', password)
  const expectedHouseholdName = required('PLAYWRIGHT_L4_04_HOUSEHOLD', householdName)
  const baseURL = required('PLAYWRIGHT_BASE_URL', testInfo.project.use.baseURL)

  await registerLocationsOffHousehold(page, accountEmail, accountPassword, expectedHouseholdName)
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
  expect(line, `Geen gehele verwerkbare bonregel gevonden in ${JSON.stringify(batchBefore)}`).toBeTruthy()
  const lineId = String(line.id)

  await page.goto(`/kassabonnen?batch=${encodeURIComponent(batchId)}`)
  await expect(page.getByTestId('receipts-page')).toBeVisible()
  const receiptTable = page.getByTestId('receipt-lines-table')
  await expect(receiptTable).toBeVisible({ timeout: 30_000 })
  await expect(receiptTable.getByRole('columnheader', { name: 'Locatie', exact: true })).toHaveCount(0)
  await expect(page.getByLabel('Filter op locatie')).toBeHidden()
  await expect(page.getByTestId('receipt-bulk-location-button')).toBeHidden()
  await expect(page.getByTestId(`receipt-line-location-select-${lineId}`)).toBeHidden()

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
  expect(Number(processPayload?.processed_count || 0)).toBeGreaterThanOrEqual(1)
  await expect(page.getByRole('dialog', { name: 'Verwerking afgerond' })).toBeVisible({ timeout: 30_000 })
  await page.getByRole('dialog', { name: 'Verwerking afgerond' }).getByRole('button', { name: 'Sluiten' }).click()
  await expect(page.getByTestId(`receipt-line-${lineId}`)).toHaveCount(0, { timeout: 20_000 })

  const inventoryResponse = await page.request.get('/api/dev/inventory-preview')
  expect(inventoryResponse.ok()).toBeTruthy()
  const inventoryPayload = await inventoryResponse.json()
  const inventoryRows = Array.isArray(inventoryPayload?.rows) ? inventoryPayload.rows : []
  const targetInventory = inventoryRows.find((item) => Number(item?.aantal || 0) > 0 && String(item?.id || '').trim() && String(item?.household_article_id || '').trim())
  expect(targetInventory, JSON.stringify(inventoryPayload)).toBeTruthy()
  const inventoryId = String(targetInventory.id)
  const householdArticleId = String(targetInventory.household_article_id)
  const articleName = String(targetInventory.artikel || targetInventory.household_article_name || '').trim()
  const initialQuantity = Number(targetInventory.aantal || 0)
  expect(articleName).not.toBe('')
  expect(Number.isInteger(initialQuantity)).toBeTruthy()
  expect(initialQuantity).toBeGreaterThan(0)

  await openInventoryArticle(page, householdArticleId)
  const minStock = Math.max(initialQuantity - 1, 0)
  const idealStock = initialQuantity
  await configureAlmostOutThreshold(page, minStock, idealStock)

  await page.goto('/bijna-op')
  await expect(page.getByTestId('almost-out-page')).toBeVisible()
  await expect(page.getByTestId('almost-out-table').getByText(articleName, { exact: true })).toHaveCount(0)

  await consumeThroughArticleStock(page, householdArticleId, inventoryId, initialQuantity)

  await page.goto('/bijna-op')
  await expect(page.getByTestId('almost-out-page')).toBeVisible()
  await expect(page.getByTestId('almost-out-table').getByText(articleName, { exact: true })).toHaveCount(1)

  writeFileSync('p0-l4-04-browser-proof.json', JSON.stringify({
    householdId,
    receiptId,
    batchId,
    lineId,
    inventoryId,
    householdArticleId,
    initialQuantity,
    minStock,
    idealStock,
    consumeQuantity: initialQuantity,
    finalQuantity: 0,
    locationTrackingLevel: 'none',
  }, null, 2))

  console.log('P0_L4_04_LOCATIONS_OFF_BROWSER_GREEN')
  console.log('P0_L4_04_LOCATIONLESS_INVENTORY_BROWSER_GREEN')
})
