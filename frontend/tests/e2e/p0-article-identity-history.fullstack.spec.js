import { writeFileSync } from 'node:fs'
import { test, expect } from '@playwright/test'

const email = process.env.PLAYWRIGHT_L4_06_EMAIL
const password = process.env.PLAYWRIGHT_L4_06_PASSWORD
const householdName = process.env.PLAYWRIGHT_L4_06_HOUSEHOLD
const sharedArticleName = process.env.PLAYWRIGHT_L4_06_SHARED_NAME

function required(name, value) {
  if (!String(value || '').trim()) throw new Error(`${name} ontbreekt voor L4-06`)
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
}

async function readSession(page) {
  const response = await page.request.get('/api/session')
  expect(response.ok()).toBeTruthy()
  return response.json()
}

async function loadCanonicalReceiptFixture(request, baseURL) {
  const response = await request.get(`${baseURL}/api/testing/fixtures/receipt/file?kind=manual`)
  expect(response.ok(), 'Canonieke Jumbo-kassabonfixture moet beschikbaar zijn.').toBeTruthy()
  return { name: `l4-06-jumbo-${Date.now()}.jpg`, mimeType: 'image/jpeg', buffer: await response.body() }
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

function isProcessableLine(line) {
  const quantity = Number(line?.quantity_raw || 0)
  return Number.isInteger(quantity)
    && quantity > 0
    && String(line?.processing_status || '') !== 'processed'
}

async function selectOnlyLines(page, lines, selectedLineIds) {
  const selected = new Set(selectedLineIds.map(String))
  for (const line of lines) {
    const lineId = String(line?.id || '')
    if (!lineId) continue
    const checkbox = page.getByTestId(`receipt-line-select-${lineId}`)
    if ((await checkbox.count()) === 0 || !(await checkbox.isVisible())) continue
    const shouldBeChecked = selected.has(lineId)
    if (shouldBeChecked && !(await checkbox.isChecked())) await checkbox.check()
    if (!shouldBeChecked && (await checkbox.isChecked())) await checkbox.uncheck()
  }
}

async function openInventoryArticle(page, householdArticleId) {
  await page.goto('/voorraad')
  await expect(page.getByTestId('inventory-page')).toBeVisible({ timeout: 30_000 })
  const row = page.getByTestId(`inventory-row-${householdArticleId}`)
  await expect(row).toBeVisible({ timeout: 30_000 })
  const detailsResponsePromise = page.waitForResponse((response) => (
    new URL(response.url()).pathname === `/api/household-articles/${encodeURIComponent(householdArticleId)}`
    && response.request().method() === 'GET'
  ))
  await row.locator('[title="Dubbelklik op de rij voor details"]').dblclick()
  expect((await detailsResponsePromise).ok()).toBeTruthy()
  await expect(page.getByTestId('article-detail-page')).toBeVisible({ timeout: 30_000 })
  return page.url()
}

async function renameHouseholdArticle(page, householdArticleId, nextName) {
  await openInventoryArticle(page, householdArticleId)
  await page.getByTestId('article-overview-subtab-article').click()
  const input = page.getByTestId('article-details-input-custom_name')
  await expect(input).toBeVisible({ timeout: 20_000 })
  const patchResponsePromise = page.waitForResponse((response) => (
    new URL(response.url()).pathname === `/api/household-articles/${encodeURIComponent(householdArticleId)}`
    && response.request().method() === 'PATCH'
  ))
  await input.fill(nextName)
  await input.blur()
  expect((await patchResponsePromise).ok()).toBeTruthy()
  await expect(page.getByTestId('article-details-save-success')).toContainText('Wijziging verwerkt.', { timeout: 20_000 })

  await page.reload()
  await expect(page.getByTestId('article-detail-page')).toBeVisible({ timeout: 30_000 })
  await page.getByTestId('article-overview-subtab-article').click()
  await expect(page.getByTestId('article-details-input-custom_name')).toHaveValue(nextName)
}

async function proveOwnHistoryOnly(page, householdArticleId, ownEventId, otherEventId) {
  const detailUrl = await openInventoryArticle(page, householdArticleId)
  await page.getByTestId('article-history-tab').click()
  await expect(page.getByTestId('history-page')).toBeVisible({ timeout: 30_000 })
  const ownRow = page.getByTestId(`history-row-${ownEventId}`)
  await expect(ownRow).toBeVisible({ timeout: 30_000 })
  await expect(ownRow).toContainText('Aankoop')
  await expect(ownRow).toContainText('Winkelimport')
  await expect(page.getByTestId(`history-row-${otherEventId}`)).toHaveCount(0)
  return detailUrl
}

test('L4-06 purchase identities survive same-name rename through detail and history', async ({ page, request }, testInfo) => {
  test.setTimeout(360_000)
  const accountEmail = required('PLAYWRIGHT_L4_06_EMAIL', email).toLowerCase()
  const accountPassword = required('PLAYWRIGHT_L4_06_PASSWORD', password)
  const expectedHouseholdName = required('PLAYWRIGHT_L4_06_HOUSEHOLD', householdName)
  const commonName = required('PLAYWRIGHT_L4_06_SHARED_NAME', sharedArticleName)
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
  const batchId = String(approvedBatch.batch_id || '')
  expect(batchId).not.toBe('')

  const batchBefore = await readBatch(page, batchId)
  const lines = Array.isArray(batchBefore?.lines) ? batchBefore.lines : []
  const candidates = lines.filter(isProcessableLine)
  expect(candidates.length, `L4-06 heeft twee verwerkbare bonregels nodig: ${JSON.stringify(batchBefore)}`).toBeGreaterThanOrEqual(2)
  const chosen = candidates.slice(0, 2)
  const lineAId = String(chosen[0].id)
  const lineBId = String(chosen[1].id)
  expect(lineAId).not.toBe(lineBId)

  await page.goto(`/kassabonnen?batch=${encodeURIComponent(batchId)}`)
  await expect(page.getByTestId('receipts-page')).toBeVisible()
  await expect(page.getByTestId('receipt-lines-table')).toBeVisible({ timeout: 30_000 })
  await selectOnlyLines(page, lines, [lineAId, lineBId])
  await expect(page.getByTestId(`receipt-line-select-${lineAId}`)).toBeChecked()
  await expect(page.getByTestId(`receipt-line-select-${lineBId}`)).toBeChecked()

  const processResponsePromise = page.waitForResponse((response) => (
    new URL(response.url()).pathname === `/api/purchase-import-batches/${batchId}/process`
    && response.request().method() === 'POST'
  ))
  await page.getByTestId('receipt-process-button').click()
  const processResponse = await processResponsePromise
  expect(processResponse.ok()).toBeTruthy()
  const processPayload = await processResponse.json()
  expect(Number(processPayload?.processed_count || 0)).toBeGreaterThanOrEqual(2)
  await expect(page.getByRole('dialog', { name: 'Verwerking afgerond' })).toBeVisible({ timeout: 30_000 })
  await page.getByRole('dialog', { name: 'Verwerking afgerond' }).getByRole('button', { name: 'Sluiten' }).click()

  const batchAfter = await readBatch(page, batchId)
  const processedA = (batchAfter?.lines || []).find((line) => String(line?.id || '') === lineAId)
  const processedB = (batchAfter?.lines || []).find((line) => String(line?.id || '') === lineBId)
  expect(processedA, JSON.stringify(batchAfter)).toBeTruthy()
  expect(processedB, JSON.stringify(batchAfter)).toBeTruthy()
  expect(String(processedA.processing_status || '')).toBe('processed')
  expect(String(processedB.processing_status || '')).toBe('processed')

  const articleAId = String(processedA.matched_household_article_id || '')
  const articleBId = String(processedB.matched_household_article_id || '')
  const eventAId = String(processedA.processed_event_id || '')
  const eventBId = String(processedB.processed_event_id || '')
  expect(articleAId).not.toBe('')
  expect(articleBId).not.toBe('')
  expect(eventAId).not.toBe('')
  expect(eventBId).not.toBe('')
  expect(articleAId, 'Twee verschillende aankoopregels mogen niet op dezelfde canonical identity instorten.').not.toBe(articleBId)
  expect(eventAId).not.toBe(eventBId)

  await renameHouseholdArticle(page, articleAId, commonName)
  await renameHouseholdArticle(page, articleBId, commonName)

  const detailAUrl = await proveOwnHistoryOnly(page, articleAId, eventAId, eventBId)
  const detailBUrl = await proveOwnHistoryOnly(page, articleBId, eventBId, eventAId)
  expect(detailAUrl).not.toBe(detailBUrl)

  writeFileSync('p0-l4-06-browser-proof.json', JSON.stringify({
    householdId,
    receiptId,
    batchId,
    lineAId,
    lineBId,
    articleAId,
    articleBId,
    eventAId,
    eventBId,
    sharedArticleName: commonName,
    detailAUrl,
    detailBUrl,
  }, null, 2))

  console.log(`P0_L4_06_ARTICLE_A_ID=${articleAId}`)
  console.log(`P0_L4_06_ARTICLE_B_ID=${articleBId}`)
  console.log('P0_L4_06_SAME_NAME_DIFFERENT_IDENTITY_GREEN')
  console.log('P0_L4_06_RENAME_IDENTITY_GREEN')
  console.log('P0_L4_06_DETAIL_HISTORY_IDENTITY_GREEN')
})
