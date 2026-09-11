import { writeFileSync } from 'node:fs'
import { test, expect } from '@playwright/test'

const email = process.env.PLAYWRIGHT_P0_UNPACKING_EMAIL
const password = process.env.PLAYWRIGHT_P0_UNPACKING_PASSWORD
const batchId = process.env.PLAYWRIGHT_P0_UNPACKING_BATCH_ID
const lineId = process.env.PLAYWRIGHT_P0_UNPACKING_LINE_ID
const articleName = process.env.PLAYWRIGHT_P0_UNPACKING_ARTICLE_NAME

function required(name, value) {
  if (!String(value || '').trim()) throw new Error(`${name} ontbreekt voor F6-02 Uitpakken authority`)
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

async function selectAndProcess(page, expectedBatchId, expectedLineId, expectedArticleName) {
  await page.goto(`/kassabonnen?batch=${encodeURIComponent(expectedBatchId)}`)
  await expect(page.getByTestId('receipts-page')).toBeVisible({ timeout: 30_000 })
  const row = page.getByTestId(`receipt-line-${expectedLineId}`)
  await expect(row).toBeVisible({ timeout: 30_000 })
  await expect(row).toContainText(expectedArticleName)
  await expect(page.getByTestId(`receipt-line-location-select-${expectedLineId}`)).toContainText('Direct')
  const lineSelect = page.getByTestId(`receipt-line-select-${expectedLineId}`)
  if (!(await lineSelect.isChecked())) await lineSelect.check()
  const processButton = page.getByTestId('receipt-process-button')
  await expect(processButton).toBeEnabled()
  const responsePromise = page.waitForResponse((response) => new URL(response.url()).pathname === `/api/purchase-import-batches/${expectedBatchId}/process` && response.request().method() === 'POST')
  await page.getByTestId('receipt-process-button').click()
  return responsePromise
}

test('F6-02 Uitpakken temporary failure leaves retryable state and visible retry succeeds exactly once', async ({ page }) => {
  test.setTimeout(240_000)
  const accountEmail = required('PLAYWRIGHT_P0_UNPACKING_EMAIL', email).toLowerCase()
  const accountPassword = required('PLAYWRIGHT_P0_UNPACKING_PASSWORD', password)
  const expectedBatchId = required('PLAYWRIGHT_P0_UNPACKING_BATCH_ID', batchId)
  const expectedLineId = required('PLAYWRIGHT_P0_UNPACKING_LINE_ID', lineId)
  const expectedArticleName = required('PLAYWRIGHT_P0_UNPACKING_ARTICLE_NAME', articleName)

  await login(page, accountEmail, accountPassword)

  const firstResponse = await selectAndProcess(page, expectedBatchId, expectedLineId, expectedArticleName)
  expect(firstResponse.status()).toBe(500)
  await expect(page.getByText('Verwerken van bonregels is mislukt.', { exact: true }).first()).toBeVisible({ timeout: 20_000 })
  await expect(page.locator('body')).not.toContainText('F6 temporary Unpacking finalization failure')
  await expect(page.getByTestId(`receipt-line-${expectedLineId}`)).toBeVisible({ timeout: 20_000 })
  console.log('F6_02_UNPACKING_TEMPORARY_FAILURE_ROLLBACK_VISIBLE_GREEN')

  await page.reload()
  await expect(page.getByTestId(`receipt-line-${expectedLineId}`)).toBeVisible({ timeout: 30_000 })

  const retryResponse = await selectAndProcess(page, expectedBatchId, expectedLineId, expectedArticleName)
  expect(retryResponse.ok(), `Retry status ${retryResponse.status()}`).toBeTruthy()
  const retryPayload = await retryResponse.json()
  expect(Number(retryPayload?.processed_count || 0), JSON.stringify(retryPayload)).toBe(1)
  expect(Number(retryPayload?.failed_count || 0), JSON.stringify(retryPayload)).toBe(0)
  expect(JSON.stringify(retryPayload)).toContain('inventory_mutation_skipped')
  expect(JSON.stringify(retryPayload)).toContain('direct_consumption')

  const completedDialog = page.getByRole('dialog', { name: 'Verwerking afgerond' })
  await expect(completedDialog).toBeVisible({ timeout: 30_000 })
  await completedDialog.getByRole('button', { name: 'Sluiten' }).click()
  await expect(page.getByTestId(`receipt-line-${expectedLineId}`)).toHaveCount(0, { timeout: 20_000 })

  writeFileSync('f6-02-unpacking-browser-proof.json', JSON.stringify({
    email: accountEmail,
    batchId: expectedBatchId,
    lineId: expectedLineId,
    articleName: expectedArticleName,
    firstProcessStatus: firstResponse.status(),
    retryProcessStatus: retryResponse.status(),
    processedCount: Number(retryPayload?.processed_count || 0),
    failedCount: Number(retryPayload?.failed_count || 0),
  }, null, 2))

  console.log('F6_02_UNPACKING_TEMPORARY_FAILURE_VISIBLE_GREEN')
  console.log('F6_02_UNPACKING_VISIBLE_RETRY_SUCCESS_GREEN')
  console.log('F6_02_UNPACKING_BROWSER_EXACT_ONCE_GREEN')
})