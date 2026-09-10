import { writeFileSync } from 'node:fs'
import { test, expect } from '@playwright/test'

const email = process.env.PLAYWRIGHT_F6_KASSA_EMAIL
const password = process.env.PLAYWRIGHT_F6_KASSA_PASSWORD
const receiptId = process.env.PLAYWRIGHT_F6_KASSA_RECEIPT_ID

function required(name, value) {
  const normalized = String(value || '').trim()
  if (!normalized) throw new Error(`${name} ontbreekt voor F6 Kassa authority`)
  return normalized
}

async function login(page, accountEmail, accountPassword) {
  await page.goto('/login')
  await expect(page.getByTestId('login-page')).toBeVisible()
  await page.getByTestId('login-email').fill(accountEmail)
  await page.getByTestId('login-password').fill(accountPassword)
  const responsePromise = page.waitForResponse((response) => (
    new URL(response.url()).pathname === '/api/auth/login'
    && response.request().method() === 'POST'
  ))
  await page.getByTestId('login-submit').click()
  expect((await responsePromise).ok()).toBeTruthy()
  await expect(page).toHaveURL(/\/home$/)
}

async function openFinancialReview(page, targetReceiptId) {
  await page.goto('/kassa')
  await expect(page.getByTestId('kassa-page')).toBeVisible({ timeout: 30_000 })
  const row = page.getByTestId(`kassa-row-${targetReceiptId}`)
  await expect(row).toBeVisible({ timeout: 30_000 })
  await row.dblclick()
  await expect(page.getByTestId('receipt-detail-page')).toBeVisible({ timeout: 30_000 })
  await expect(page.getByTestId('receipt-detail-title')).toHaveText('L4 Financiele Review')
  await expect(page.getByTestId('receipt-detail-page')).toContainText('Totaalbedrag wijkt af van de bonregels')
}

test('F6-01 Kassa approval controlled 500 shows standard feedback and rolls approval back', async ({ page }) => {
  test.setTimeout(180_000)
  const accountEmail = required('PLAYWRIGHT_F6_KASSA_EMAIL', email).toLowerCase()
  const accountPassword = required('PLAYWRIGHT_F6_KASSA_PASSWORD', password)
  const targetReceiptId = required('PLAYWRIGHT_F6_KASSA_RECEIPT_ID', receiptId)

  await login(page, accountEmail, accountPassword)
  await openFinancialReview(page, targetReceiptId)

  const approvalResponsePromise = page.waitForResponse((response) => (
    new URL(response.url()).pathname === `/api/receipts/${targetReceiptId}/approve`
    && response.request().method() === 'POST'
  ))
  await page.getByRole('button', { name: 'Goedkeuren', exact: true }).click()
  const approvalResponse = await approvalResponsePromise
  expect(approvalResponse.status()).toBe(500)

  const feedback = page.getByTestId('app-feedback-error')
  await expect(feedback).toBeVisible({ timeout: 30_000 })
  await expect(feedback).toContainText('Bon kon niet worden goedgekeurd.')
  await expect(feedback).not.toContainText('Interne serverfout in de API')
  await expect(feedback).not.toContainText('F6 controlled Kassa')
  console.log('F6_KASSA_REAL_500_FEEDBACK_GREEN')

  await page.getByTestId('app-feedback-error-ok-button').click()
  await page.reload()
  await expect(page.getByTestId('receipt-detail-page')).toBeVisible({ timeout: 30_000 })
  await expect(page.getByTestId('receipt-detail-page')).toContainText('Totaalbedrag wijkt af van de bonregels')
  await expect(page.getByRole('button', { name: 'Goedkeuren', exact: true })).toBeVisible()

  await page.goto('/kassa')
  await expect(page.getByTestId(`kassa-row-${targetReceiptId}`)).toBeVisible({ timeout: 30_000 })
  console.log('F6_KASSA_BROWSER_ROLLBACK_GREEN')

  writeFileSync('f6-kassa-review-controlled-5xx-browser-proof.json', JSON.stringify({
    email: accountEmail,
    receiptId: targetReceiptId,
    approvalStatus: approvalResponse.status(),
    feedback: 'Bon kon niet worden goedgekeurd.',
    receiptRemainsInInbox: true,
  }, null, 2))
})
