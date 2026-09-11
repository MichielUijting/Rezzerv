import { writeFileSync } from 'node:fs'
import { join } from 'node:path'
import { test, expect } from '@playwright/test'

// This spec is explicitly selected by playwright.fullstack.config.js for the F6-03 authority.
const email = process.env.PLAYWRIGHT_F6_03_EMAIL
const password = process.env.PLAYWRIGHT_F6_03_PASSWORD
const householdName = process.env.PLAYWRIGHT_F6_03_HOUSEHOLD

function required(name, value) {
  if (!String(value || '').trim()) throw new Error(`${name} ontbreekt voor F6-03`)
  return String(value).trim()
}

async function registerHousehold(page, accountEmail, accountPassword, expectedHouseholdName) {
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

async function readReceiptList(page, householdId) {
  const response = await page.request.get(`/api/receipts?householdId=${encodeURIComponent(householdId)}`)
  expect(response.ok()).toBeTruthy()
  const payload = await response.json()
  return Array.isArray(payload?.items) ? payload.items : []
}

async function readUnpackingBatches(page, householdId) {
  const response = await page.request.get(`/api/unpack-start-batches?householdId=${encodeURIComponent(householdId)}`)
  expect(response.ok()).toBeTruthy()
  const payload = await response.json()
  return Array.isArray(payload?.items) ? payload.items : []
}

async function readInventoryRows(page) {
  const response = await page.request.get('/api/dev/inventory-preview')
  expect(response.ok()).toBeTruthy()
  const payload = await response.json()
  return Array.isArray(payload?.rows) ? payload.rows : []
}

test('F6-03 invalid receipt import is visibly rejected and leaves no receipt batch or inventory pollution', async ({ page }) => {
  test.setTimeout(240_000)
  const accountEmail = required('PLAYWRIGHT_F6_03_EMAIL', email).toLowerCase()
  const accountPassword = required('PLAYWRIGHT_F6_03_PASSWORD', password)
  const expectedHouseholdName = required('PLAYWRIGHT_F6_03_HOUSEHOLD', householdName)

  await registerHousehold(page, accountEmail, accountPassword, expectedHouseholdName)
  const session = await readSession(page)
  const householdId = String(session.active_household_id || '').trim()
  expect(session.role).toBe('admin')
  expect(householdId).not.toBe('')

  expect(await readReceiptList(page, householdId)).toHaveLength(0)
  expect(await readUnpackingBatches(page, householdId)).toHaveLength(0)
  expect(await readInventoryRows(page)).toHaveLength(0)

  await page.goto('/kassa/nieuw')
  await expect(page.getByTestId('kassa-add-page')).toBeVisible()
  await expect(page.getByTestId('kassa-manual-file-input')).toHaveCount(1)

  const importResponsePromise = page.waitForResponse(
    (response) => {
      try {
        return new URL(response.url()).pathname === '/api/receipts/import'
          && response.request().method() === 'POST'
      } catch {
        return false
      }
    },
    { timeout: 120_000 },
  )

  await page.getByTestId('kassa-manual-file-input').setInputFiles({
    name: 'f6-03-empty-invalid-receipt.pdf',
    mimeType: 'application/pdf',
    buffer: Buffer.alloc(0),
  })

  const response = await importResponsePromise
  const responseText = await response.text()
  let payload = null
  try { payload = responseText ? JSON.parse(responseText) : null } catch { payload = responseText }
  const responseDetail = String(payload?.detail || '')

  expect(response.status(), JSON.stringify(payload)).toBe(400)
  expect(responseDetail).toBe('Leeg bestand')
  await expect(page).toHaveURL(/\/kassa\/nieuw$/)
  const rejectionFeedback = page.getByTestId('kassa-upload-rejected')
  await expect(rejectionFeedback).toBeVisible({ timeout: 20_000 })
  await expect(rejectionFeedback).toContainText(/Leeg bestand/i)

  const receiptsAfter = await readReceiptList(page, householdId)
  const batchesAfter = await readUnpackingBatches(page, householdId)
  const inventoryAfter = await readInventoryRows(page)
  expect(receiptsAfter).toHaveLength(0)
  expect(batchesAfter).toHaveLength(0)
  expect(inventoryAfter).toHaveLength(0)

  await page.goto('/kassa')
  await expect(page.locator('body')).not.toContainText('f6-03-empty-invalid-receipt.pdf')

  writeFileSync(join(process.cwd(), 'f6-03-invalid-import-browser-proof.json'), JSON.stringify({
    householdId,
    importStatus: response.status(),
    detail: responseDetail,
    receiptCount: receiptsAfter.length,
    batchCount: batchesAfter.length,
    inventoryRowCount: inventoryAfter.length,
  }, null, 2), 'utf8')

  console.log('F6_03_INVALID_IMPORT_HTTP_REJECTED_GREEN')
  console.log('F6_03_INVALID_IMPORT_VISIBLE_REJECTION_GREEN')
  console.log('F6_03_RECEIPT_NO_POLLUTION_BROWSER_GREEN')
  console.log('F6_03_KASSA_NO_POLLUTION_BROWSER_GREEN')
})
