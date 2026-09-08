import { writeFileSync } from 'node:fs'
import { test, expect } from '@playwright/test'

const email = process.env.PLAYWRIGHT_P0_KASSA_REVIEW_EMAIL
const password = process.env.PLAYWRIGHT_P0_KASSA_REVIEW_PASSWORD
const uncertainReceiptId = process.env.PLAYWRIGHT_P0_KASSA_REVIEW_UNCERTAIN_RECEIPT_ID
const uncertainLineId = process.env.PLAYWRIGHT_P0_KASSA_REVIEW_UNCERTAIN_LINE_ID
const financialReceiptId = process.env.PLAYWRIGHT_P0_KASSA_REVIEW_FINANCIAL_RECEIPT_ID

function required(name, value) {
  if (!String(value || '').trim()) throw new Error(`${name} ontbreekt voor P0 Kassa review authority`)
  return String(value).trim()
}

async function login(page, accountEmail, accountPassword) {
  await page.goto('/login')
  await expect(page.getByTestId('login-page')).toBeVisible()
  await page.getByTestId('login-email').fill(accountEmail)
  await page.getByTestId('login-password').fill(accountPassword)
  const loginResponsePromise = page.waitForResponse((response) => (
    new URL(response.url()).pathname === '/api/auth/login'
    && response.request().method() === 'POST'
  ))
  await page.getByTestId('login-submit').click()
  expect((await loginResponsePromise).ok()).toBeTruthy()
  await expect(page).toHaveURL(/\/home$/)
}

async function openReceipt(page, receiptId, expectedStore) {
  await page.goto('/kassa')
  await expect(page.getByTestId('kassa-page')).toBeVisible({ timeout: 30_000 })
  const row = page.getByTestId(`kassa-row-${receiptId}`)
  await expect(row).toBeVisible({ timeout: 30_000 })
  await row.dblclick()
  await expect(page.getByTestId('receipt-detail-page')).toBeVisible({ timeout: 30_000 })
  await expect(page.getByTestId('receipt-detail-title')).toHaveText(expectedStore)
}

async function reviewUncertainLineThroughBrowser(page, receiptId, lineId) {
  await openReceipt(page, receiptId, 'L4 Onzekere Match')
  const lineSelect = page.getByTestId(`receipt-line-select-${lineId}`)
  await expect(lineSelect).toBeVisible()
  await lineSelect.check()

  const reviewResponsePromise = page.waitForResponse((response) => (
    new URL(response.url()).pathname === `/api/receipts/${receiptId}/lines/${lineId}`
    && response.request().method() === 'PATCH'
  ))
  await page.getByTestId('receipt-lines-mark-reviewed').click()
  const reviewResponse = await reviewResponsePromise
  expect(reviewResponse.ok()).toBeTruthy()

  const approvalResponsePromise = page.waitForResponse((response) => (
    new URL(response.url()).pathname === `/api/receipts/${receiptId}/approve`
    && response.request().method() === 'POST'
  ))
  await page.getByRole('button', { name: 'Goedkeuren', exact: true }).click()
  expect((await approvalResponsePromise).ok()).toBeTruthy()
  await expect(page.getByTestId(`kassa-row-${receiptId}`)).toHaveCount(0)
}

async function approveFinancialMismatchThroughBrowser(page, receiptId) {
  await openReceipt(page, receiptId, 'L4 Financiele Review')
  await expect(page.getByTestId('receipt-detail-page')).toContainText('Totaalbedrag wijkt af van de bonregels')
  await expect(page.getByTestId('receipt-detail-page')).toContainText("Je kunt deze afwijking overrulen via 'Goedkeuren'.")

  const approvalResponsePromise = page.waitForResponse((response) => (
    new URL(response.url()).pathname === `/api/receipts/${receiptId}/approve`
    && response.request().method() === 'POST'
  ))
  await page.getByRole('button', { name: 'Goedkeuren', exact: true }).click()
  expect((await approvalResponsePromise).ok()).toBeTruthy()
  await expect(page.getByTestId(`kassa-row-${receiptId}`)).toHaveCount(0)
}

test('P0 Kassa browser review closes uncertain match and financial mismatch', async ({ page }) => {
  test.setTimeout(180_000)
  const accountEmail = required('PLAYWRIGHT_P0_KASSA_REVIEW_EMAIL', email).toLowerCase()
  const accountPassword = required('PLAYWRIGHT_P0_KASSA_REVIEW_PASSWORD', password)
  const uncertainId = required('PLAYWRIGHT_P0_KASSA_REVIEW_UNCERTAIN_RECEIPT_ID', uncertainReceiptId)
  const uncertainReviewLineId = required('PLAYWRIGHT_P0_KASSA_REVIEW_UNCERTAIN_LINE_ID', uncertainLineId)
  const financialId = required('PLAYWRIGHT_P0_KASSA_REVIEW_FINANCIAL_RECEIPT_ID', financialReceiptId)

  await login(page, accountEmail, accountPassword)
  await reviewUncertainLineThroughBrowser(page, uncertainId, uncertainReviewLineId)
  await approveFinancialMismatchThroughBrowser(page, financialId)

  writeFileSync('p0-kassa-review-browser-proof.json', JSON.stringify({
    email: accountEmail,
    uncertainReceiptId: uncertainId,
    uncertainLineId: uncertainReviewLineId,
    financialReceiptId: financialId,
  }, null, 2))

  console.log('P0_KASSA_UNCERTAIN_BROWSER_REVIEW_GREEN')
  console.log('P0_KASSA_FINANCIAL_BROWSER_REVIEW_GREEN')
})
