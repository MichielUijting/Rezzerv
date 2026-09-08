import { writeFileSync } from 'node:fs'
import { test, expect } from '@playwright/test'

const email = process.env.PLAYWRIGHT_P0_UNPACKING_EMAIL
const password = process.env.PLAYWRIGHT_P0_UNPACKING_PASSWORD
const batchId = process.env.PLAYWRIGHT_P0_UNPACKING_BATCH_ID
const lineId = process.env.PLAYWRIGHT_P0_UNPACKING_LINE_ID
const articleName = process.env.PLAYWRIGHT_P0_UNPACKING_ARTICLE_NAME

function required(name, value) {
  if (!String(value || '').trim()) throw new Error(`${name} ontbreekt voor P0 Uitpakken authority`)
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

test('P0 Uitpakken processes canonical day article through Direct without changing existing stock', async ({ page }) => {
  test.setTimeout(180_000)
  const accountEmail = required('PLAYWRIGHT_P0_UNPACKING_EMAIL', email).toLowerCase()
  const accountPassword = required('PLAYWRIGHT_P0_UNPACKING_PASSWORD', password)
  const expectedBatchId = required('PLAYWRIGHT_P0_UNPACKING_BATCH_ID', batchId)
  const expectedLineId = required('PLAYWRIGHT_P0_UNPACKING_LINE_ID', lineId)
  const expectedArticleName = required('PLAYWRIGHT_P0_UNPACKING_ARTICLE_NAME', articleName)

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
  expect(processResponse.ok()).toBeTruthy()
  const processPayload = await processResponse.json()
  expect(Number(processPayload?.processed_count || 0), JSON.stringify(processPayload)).toBe(1)
  expect(Number(processPayload?.failed_count || 0), JSON.stringify(processPayload)).toBe(0)
  expect(JSON.stringify(processPayload)).toContain('inventory_mutation_skipped')
  expect(JSON.stringify(processPayload)).toContain('direct_consumption')

  const completedDialog = page.getByRole('dialog', { name: 'Verwerking afgerond' })
  await expect(completedDialog).toBeVisible({ timeout: 30_000 })
  await completedDialog.getByRole('button', { name: 'Sluiten' }).click()
  await expect(page.getByTestId(`receipt-line-${expectedLineId}`)).toHaveCount(0, { timeout: 20_000 })

  writeFileSync('p0-unpacking-browser-proof.json', JSON.stringify({
    email: accountEmail,
    batchId: expectedBatchId,
    lineId: expectedLineId,
    articleName: expectedArticleName,
    destination: 'Direct',
    processedCount: Number(processPayload?.processed_count || 0),
    failedCount: Number(processPayload?.failed_count || 0),
  }, null, 2))

  console.log('P0_UNPACKING_DAY_ARTICLE_BROWSER_GREEN')
  console.log('P0_UNPACKING_DIRECT_CONSUMPTION_BROWSER_GREEN')
})
