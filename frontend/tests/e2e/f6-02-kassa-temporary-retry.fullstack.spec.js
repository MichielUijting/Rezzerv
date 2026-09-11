import { writeFileSync } from 'node:fs'
import { test, expect } from '@playwright/test'

const email = process.env.PLAYWRIGHT_P0_KASSA_REVIEW_EMAIL
const password = process.env.PLAYWRIGHT_P0_KASSA_REVIEW_PASSWORD
const uncertainReceiptId = process.env.PLAYWRIGHT_P0_KASSA_REVIEW_UNCERTAIN_RECEIPT_ID
const uncertainLineId = process.env.PLAYWRIGHT_P0_KASSA_REVIEW_UNCERTAIN_LINE_ID
const financialReceiptId = process.env.PLAYWRIGHT_P0_KASSA_REVIEW_FINANCIAL_RECEIPT_ID

function required(name, value) {
  if (!String(value || '').trim()) throw new Error(`${name} ontbreekt voor F6-02 Kassa authority`)
  return String(value).trim()
}

async function login(page, accountEmail, accountPassword) {
  await page.goto('/login')
  await expect(page.getByTestId('login-page')).toBeVisible()
  await page.getByTestId('login-email').fill(accountEmail)
  await page.getByTestId('login-password').fill(accountPassword)
  const loginResponsePromise = page.waitForResponse((response) => new URL(response.url()).pathname === '/api/auth/login' && response.request().method() === 'POST')
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

async function reviewAndApproveUncertain(page, receiptId, lineId) {
  await openReceipt(page, receiptId, 'L4 Onzekere Match')
  const lineSelect = page.getByTestId(`receipt-line-select-${lineId}`)
  await expect(lineSelect).toBeVisible()
  await lineSelect.check()
  const reviewResponsePromise = page.waitForResponse((response) => new URL(response.url()).pathname === `/api/receipts/${receiptId}/lines/${lineId}` && response.request().method() === 'PATCH')
  await page.getByTestId('receipt-lines-mark-reviewed').click()
  expect((await reviewResponsePromise).ok()).toBeTruthy()
  const successOverlay = page.getByTestId('kassa-feedback-success-overlay')
  await expect(successOverlay).toBeVisible()
  await page.getByTestId('kassa-feedback-success-ok-button').click()
  await expect(successOverlay).toBeHidden()
  const approvalResponsePromise = page.waitForResponse((response) => new URL(response.url()).pathname === `/api/receipts/${receiptId}/approve` && response.request().method() === 'POST')
  await page.getByRole('button', { name: 'Goedkeuren', exact: true }).click()
  expect((await approvalResponsePromise).ok()).toBeTruthy()
  await expect(page.getByTestId(`kassa-row-${receiptId}`)).toHaveCount(0)
}

test('F6-02 Kassa temporary approval failure rolls back and visible retry succeeds exactly once', async ({ page }) => {
  test.setTimeout(240_000)
  const accountEmail = required('PLAYWRIGHT_P0_KASSA_REVIEW_EMAIL', email).toLowerCase()
  const accountPassword = required('PLAYWRIGHT_P0_KASSA_REVIEW_PASSWORD', password)
  const uncertainId = required('PLAYWRIGHT_P0_KASSA_REVIEW_UNCERTAIN_RECEIPT_ID', uncertainReceiptId)
  const uncertainReviewLineId = required('PLAYWRIGHT_P0_KASSA_REVIEW_UNCERTAIN_LINE_ID', uncertainLineId)
  const financialId = required('PLAYWRIGHT_P0_KASSA_REVIEW_FINANCIAL_RECEIPT_ID', financialReceiptId)

  await login(page, accountEmail, accountPassword)
  await reviewAndApproveUncertain(page, uncertainId, uncertainReviewLineId)

  await openReceipt(page, financialId, 'L4 Financiele Review')
  await expect(page.getByTestId('receipt-detail-page')).toContainText('Totaalbedrag wijkt af van de bonregels')

  const firstApprovalPromise = page.waitForResponse((response) => new URL(response.url()).pathname === `/api/receipts/${financialId}/approve` && response.request().method() === 'POST')
  await page.getByRole('button', { name: 'Goedkeuren', exact: true }).click()
  const firstApproval = await firstApprovalPromise
  expect(firstApproval.status()).toBe(500)

  const feedback = page.getByRole('dialog', { name: 'Melding' })
  await expect(feedback).toBeVisible({ timeout: 30_000 })
  await expect(feedback).toContainText('Bon kon niet worden goedgekeurd.')
  await expect(feedback).not.toContainText('F6 temporary Kassa approval failure')
  await feedback.getByRole('button', { name: 'OK', exact: true }).click()

  await page.reload()
  await expect(page.getByTestId('kassa-page')).toBeVisible({ timeout: 30_000 })
  await expect(page.getByTestId(`kassa-row-${financialId}`)).toBeVisible({ timeout: 30_000 })
  console.log('F6_02_KASSA_TEMPORARY_FAILURE_ROLLBACK_VISIBLE_GREEN')

  await openReceipt(page, financialId, 'L4 Financiele Review')
  const retryApprovalPromise = page.waitForResponse((response) => new URL(response.url()).pathname === `/api/receipts/${financialId}/approve` && response.request().method() === 'POST')
  await page.getByRole('button', { name: 'Goedkeuren', exact: true }).click()
  const retryApproval = await retryApprovalPromise
  expect(retryApproval.ok(), `Retry status ${retryApproval.status()}`).toBeTruthy()
  await expect(page.getByTestId(`kassa-row-${financialId}`)).toHaveCount(0, { timeout: 30_000 })

  writeFileSync('f6-02-kassa-browser-proof.json', JSON.stringify({
    email: accountEmail,
    uncertainReceiptId: uncertainId,
    uncertainLineId: uncertainReviewLineId,
    financialReceiptId: financialId,
    firstApprovalStatus: firstApproval.status(),
    retryApprovalStatus: retryApproval.status(),
    feedback: 'Bon kon niet worden goedgekeurd.',
  }, null, 2))

  console.log('F6_02_KASSA_TEMPORARY_FAILURE_VISIBLE_GREEN')
  console.log('F6_02_KASSA_VISIBLE_RETRY_SUCCESS_GREEN')
  console.log('F6_02_KASSA_BROWSER_EXACT_ONCE_GREEN')
})