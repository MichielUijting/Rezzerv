import { writeFileSync } from 'node:fs'
import { test, expect } from '@playwright/test'

const email = process.env.PLAYWRIGHT_F6_UNPACKING_EMAIL
const password = process.env.PLAYWRIGHT_F6_UNPACKING_PASSWORD
const batchId = process.env.PLAYWRIGHT_F6_UNPACKING_BATCH_ID
const lineId = process.env.PLAYWRIGHT_F6_UNPACKING_LINE_ID
const articleName = process.env.PLAYWRIGHT_F6_UNPACKING_ARTICLE_NAME

function required(name, value) {
  if (!String(value || '').trim()) throw new Error(`${name} ontbreekt voor F6 Uitpakken authority`)
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

test('F6 Uitpakken controlled 500 shows safe feedback and leaves the batch retryable', async ({ page }) => {
  test.setTimeout(180_000)
  const accountEmail = required('PLAYWRIGHT_F6_UNPACKING_EMAIL', email).toLowerCase()
  const accountPassword = required('PLAYWRIGHT_F6_UNPACKING_PASSWORD', password)
  const expectedBatchId = required('PLAYWRIGHT_F6_UNPACKING_BATCH_ID', batchId)
  const expectedLineId = required('PLAYWRIGHT_F6_UNPACKING_LINE_ID', lineId)
  const expectedArticleName = required('PLAYWRIGHT_F6_UNPACKING_ARTICLE_NAME', articleName)

  await login(page, accountEmail, accountPassword)
  await page.goto(`/kassabonnen?batch=${encodeURIComponent(expectedBatchId)}`)
  await expect(page.getByTestId('receipts-page')).toBeVisible({ timeout: 30_000 })

  const row = page.getByTestId(`receipt-line-${expectedLineId}`)
  await expect(row).toBeVisible({ timeout: 30_000 })
  await expect(row).toContainText(expectedArticleName)

  const locationButton = page.getByTestId(`receipt-line-location-select-${expectedLineId}`)
  await expect(locationButton).toBeVisible({ timeout: 30_000 })
  await expect(locationButton).toContainText('Direct')

  const lineSelect = page.getByTestId(`receipt-line-select-${expectedLineId}`)
  await expect(lineSelect).toBeVisible()
  if (!(await lineSelect.isChecked())) await lineSelect.check()

  const processButton = page.getByTestId('receipt-process-button')
  await expect(processButton).toBeEnabled()
  const processResponsePromise = page.waitForResponse((response) => (
    new URL(response.url()).pathname === `/api/purchase-import-batches/${expectedBatchId}/process`
      && response.request().method() === 'POST'
  ))
  await processButton.click()
  const processResponse = await processResponsePromise
  expect(processResponse.status()).toBe(500)

  const userFeedback = page.getByText('Verwerken van bonregels is mislukt.', { exact: true }).first()
  await expect(userFeedback).toBeVisible({ timeout: 20_000 })
  await expect(page.locator('body')).not.toContainText('RuntimeError')
  await expect(page.locator('body')).not.toContainText('F6 controlled Unpacking finalization failure')

  await expect(row).toBeVisible({ timeout: 20_000 })
  await expect(row).toContainText(expectedArticleName)
  await expect(processButton).toBeEnabled({ timeout: 20_000 })

  await page.reload()
  await expect(page.getByTestId('receipts-page')).toBeVisible({ timeout: 30_000 })
  const rowAfterReload = page.getByTestId(`receipt-line-${expectedLineId}`)
  await expect(rowAfterReload).toBeVisible({ timeout: 30_000 })
  await expect(rowAfterReload).toContainText(expectedArticleName)
  await expect(page.getByTestId('receipt-process-button')).toBeEnabled({ timeout: 20_000 })

  writeFileSync('f6-unpacking-controlled-5xx-browser-proof.json', JSON.stringify({
    email: accountEmail,
    batchId: expectedBatchId,
    lineId: expectedLineId,
    articleName: expectedArticleName,
    processStatus: processResponse.status(),
    feedback: 'Verwerken van bonregels is mislukt.',
    lineVisibleAfterFailure: true,
    lineVisibleAfterReload: true,
    retryButtonEnabledAfterReload: true,
  }, null, 2))

  console.log('F6_UNPACKING_REAL_500_FEEDBACK_GREEN')
  console.log('F6_UNPACKING_BROWSER_ROLLBACK_VISIBLE_GREEN')
  console.log('F6_UNPACKING_BROWSER_RETRYABLE_STATE_GREEN')
})
