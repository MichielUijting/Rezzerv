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
  await page.goto('/registreren')
  await expect(page.getByTestId('register-page')).toBeVisible()
  await page.getByTestId('register-email').fill(accountEmail)
  await page.getByTestId('register-password').fill(accountPassword)
  await page.getByTestId('register-password-repeat').fill(accountPassword)

  const registrationResponsePromise = page.waitForResponse((response) => (
    response.url().includes('/api/auth/register')
    && response.request().method() === 'POST'
  ))
  await page.getByTestId('register-submit').click()
  expect((await registrationResponsePromise).status()).toBe(201)

  await expect(page.getByTestId('onboarding-use-case-page')).toBeVisible()
  await page.getByTestId('onboarding-choice-wat_inhuis').check()
  const primaryResponsePromise = page.waitForResponse((response) => (
    response.url().includes('/api/onboarding/primary-use-case')
    && response.request().method() === 'POST'
  ))
  await page.getByTestId('onboarding-primary-continue').click()
  expect((await primaryResponsePromise).ok()).toBeTruthy()

  await expect(page.getByTestId('onboarding-wat-inhuis-follow-up')).toBeVisible()
  await page.getByTestId('wat-inhuis-tracking-quantity').check()
  await page.getByTestId('wat-inhuis-global-locations-yes').check()
  await page.getByTestId('wat-inhuis-almost-out-yes').check()
  await page.getByTestId('wat-inhuis-shopping-yes').check()

  const productResponsePromise = page.waitForResponse((response) => (
    response.url().includes('/api/onboarding/wat-inhuis')
    && response.request().method() === 'POST'
  ))
  await page.getByTestId('wat-inhuis-finish').click()
  expect((await productResponsePromise).ok()).toBeTruthy()

  await expect(page.getByTestId('onboarding-shared-household-minimum')).toBeVisible()
  await page.getByTestId('shared-household-name').fill(expectedHouseholdName)
  await page.getByTestId('shared-household-usage-alone').check()
  const householdResponsePromise = page.waitForResponse((response) => (
    response.url().includes('/api/onboarding/shared-household-minimum')
    && response.request().method() === 'POST'
  ))
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
  return {
    name: `l4-03-jumbo-${Date.now()}.jpg`,
    mimeType: 'image/jpeg',
    buffer: await response.body(),
  }
}

function receiptIdFromImport(payload) {
  return String(
    payload?.receipt_table_id
    || payload?.receiptTableId
    || payload?.existing_receipt?.receipt_table_id
    || ''
  ).trim()
}

async function uploadReceiptThroughKassa(page, file) {
  await page.goto('/kassa/nieuw')
  await expect(page.getByTestId('kassa-add-page')).toBeVisible()
  const fileInput = page.getByTestId('kassa-manual-file-input')
  await expect(fileInput).toHaveCount(1)

  const importResponsePromise = page.waitForResponse((response) => (
    new URL(response.url()).pathname === '/api/receipts/import'
    && response.request().method() === 'POST'
  ), { timeout: 180_000 })

  await fileInput.setInputFiles(file)
  const response = await importResponsePromise
  const text = await response.text()
  let payload = null
  try {
    payload = text ? JSON.parse(text) : null
  } catch {
    throw new Error(`Kassa-import gaf geen JSON terug: HTTP ${response.status()} ${text.slice(0, 500)}`)
  }

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

  const approvalResponsePromise = page.waitForResponse((response) => (
    new URL(response.url()).pathname === `/api/receipts/${receiptId}/approve`
    && response.request().method() === 'POST'
  ))
  await page.getByRole('button', { name: 'Goedkeuren', exact: true }).click()
  const approvalResponse = await approvalResponsePromise
  expect(approvalResponse.ok()).toBeTruthy()

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
  await row.dblclick()
  await expect(page.getByTestId('article-detail-page')).toBeVisible({ timeout: 30_000 })
}

async function configureAlmostOutThreshold(page, minStock, idealStock) {
  await page.getByTestId('article-overview-subtab-household').click()
  const settingsSection = page.getByTestId('article-household-settings-section')
  await expect(settingsSection).toBeVisible()
  const sectionToggle = settingsSection.getByRole('button', { name: 'Instellingen voor dit huishouden', exact: true })
  if ((await sectionToggle.getAttribute('aria-expanded')) !== 'true') await sectionToggle.click()

  await page.getByTestId('article-details-input-min_stock').fill(String(minStock))
  await page.getByTestId('article-details-input-ideal_stock').fill(String(idealStock))
  const settingsResponsePromise = page.waitForResponse((response) => (
    response.url().includes('/api/household-articles/')
    && response.url().includes('/settings')
    && response.request().method() === 'PUT'
  ))
  await page.getByTestId('article-household-settings-save').click()
  expect((await settingsResponsePromise).ok()).toBeTruthy()
  await expect(page.getByTestId('article-settings-save-success')).toBeVisible({ timeout: 20_000 })
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
  await page.getByRole('button', { name: 'Voorraad', exact: true }).click()
  const consumeButton = page.getByTestId(`article-stock-consume-${inventoryId}`)
  await expect(consumeButton).toBeVisible({ timeout: 20_000 })
  await consumeButton.click()

  const form = page.getByTestId('article-stock-mutation-form')
  await expect(form).toBeVisible()
  await form.getByLabel('Aantal afboeken').fill(String(consumeQuantity))
  await form.getByLabel('Reden / notitie').fill('L4-03 Bijna-op drempelovergang')
  const mutationResponsePromise = page.waitForResponse((response) => (
    new URL(response.url()).pathname === `/api/household-articles/${encodeURIComponent(householdArticleId)}/inventory-events`
    && response.request().method() === 'POST'
  ))
  await form.getByRole('button', { name: 'Opslaan', exact: true }).click()
  expect((await mutationResponsePromise).ok()).toBeTruthy()
  await expect(page.getByTestId('article-stock-mutation-success')).toContainText('Voorraad is afgeboekt.', { timeout: 20_000 })
}

test('L4-03 receipt -> Kassa -> approve -> Uitpakken -> location -> Voorraad -> history -> Bijna-op NEE -> JA', async ({ page, request }, testInfo) => {
  test.setTimeout(360_000)

  const accountEmail = required('PLAYWRIGHT_L4_RECEIPT_EMAIL', email).toLowerCase()
  const accountPassword = required('PLAYWRIGHT_L4_RECEIPT_PASSWORD', password)
  const expectedHouseholdName = required('PLAYWRIGHT_L4_RECEIPT_HOUSEHOLD', householdName)
  const expectedLocationName = required('PLAYWRIGHT_L4_RECEIPT_LOCATION', locationName)
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
  const processResponsePromise = page.waitForResponse((response) => (
    new URL(response.url()).pathname === `/api/purchase-import-batches/${batchId}/process`
    && response.request().method() === 'POST'
  ))
  await page.getByTestId('receipt-process-button').click()
  expect((await processResponsePromise).ok()).toBeTruthy()

  await expect(page.getByRole('dialog', { name: 'Verwerking afgerond' })).toBeVisible({ timeout: 30_000 })
  await page.getByRole('dialog', { name: 'Verwerking afgerond' }).getByRole('button', { name: 'Sluiten' }).click()
  await expect(page.getByTestId(`receipt-line-${lineId}`)).toHaveCount(0, { timeout: 20_000 })
  await expect(page.getByText('Status: Verwerkt naar voorraad', { exact: false })).toBeVisible()
  await expect(page.getByText(/Verwerkt:\s*1/)).toBeVisible()

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
    email: accountEmail,
    householdId,
    receiptId,
    batchId,
    lineId,
    locationName: expectedLocationName,
    inventoryId,
    householdArticleId,
    articleName,
    initialQuantity,
    minStock,
    idealStock,
    consumeQuantity,
    finalQuantity,
    almostOutBefore: false,
    almostOutAfter: true,
  }, null, 2))

  console.log('P0_L4_03_RECEIPT_INVENTORY_BROWSER_GREEN')
  console.log('P0_L4_03_ALMOST_OUT_TRANSITION_BROWSER_GREEN')
})
