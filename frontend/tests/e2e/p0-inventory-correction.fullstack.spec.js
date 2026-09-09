import { writeFileSync } from 'node:fs'
import { test, expect } from '@playwright/test'

const email = process.env.PLAYWRIGHT_P0_INVENTORY_EMAIL
const password = process.env.PLAYWRIGHT_P0_INVENTORY_PASSWORD
const articleId = process.env.PLAYWRIGHT_P0_INVENTORY_ARTICLE_ID
const articleName = process.env.PLAYWRIGHT_P0_INVENTORY_ARTICLE_NAME
const inventoryId = process.env.PLAYWRIGHT_P0_INVENTORY_INVENTORY_ID
const targetQuantity = process.env.PLAYWRIGHT_P0_INVENTORY_TARGET_QUANTITY
const note = process.env.PLAYWRIGHT_P0_INVENTORY_NOTE

function required(name, value) {
  if (!String(value || '').trim()) throw new Error(`${name} ontbreekt voor P0 Inventory authority`)
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

async function openInventoryArticle(page, expectedArticleId) {
  await page.goto('/voorraad')
  await expect(page.getByTestId('inventory-page')).toBeVisible({ timeout: 30_000 })
  const row = page.getByTestId(`inventory-row-${expectedArticleId}`)
  await expect(row).toBeVisible({ timeout: 30_000 })
  const detailsResponsePromise = page.waitForResponse((response) => (
    new URL(response.url()).pathname === `/api/household-articles/${encodeURIComponent(expectedArticleId)}`
      && response.request().method() === 'GET'
  ))
  await row.locator('[title="Dubbelklik op de rij voor details"]').dblclick()
  expect((await detailsResponsePromise).ok()).toBeTruthy()
  await expect(page.getByTestId('article-detail-page')).toBeVisible({ timeout: 30_000 })
}

test('P0 Inventory corrects exact non-financial decimal through visible stock and history', async ({ page }) => {
  test.setTimeout(180_000)
  const accountEmail = required('PLAYWRIGHT_P0_INVENTORY_EMAIL', email).toLowerCase()
  const accountPassword = required('PLAYWRIGHT_P0_INVENTORY_PASSWORD', password)
  const expectedArticleId = required('PLAYWRIGHT_P0_INVENTORY_ARTICLE_ID', articleId)
  const expectedArticleName = required('PLAYWRIGHT_P0_INVENTORY_ARTICLE_NAME', articleName)
  const expectedInventoryId = required('PLAYWRIGHT_P0_INVENTORY_INVENTORY_ID', inventoryId)
  const expectedTargetQuantity = required('PLAYWRIGHT_P0_INVENTORY_TARGET_QUANTITY', targetQuantity)
  const expectedNote = required('PLAYWRIGHT_P0_INVENTORY_NOTE', note)

  await login(page, accountEmail, accountPassword)
  await openInventoryArticle(page, expectedArticleId)

  await page.getByRole('tab', { name: 'Voorraad', exact: true }).click()
  const adjustButton = page.getByTestId(`article-stock-adjust-${expectedInventoryId}`)
  await expect(adjustButton).toBeVisible({ timeout: 20_000 })
  await adjustButton.click()

  const form = page.getByTestId('article-stock-mutation-form')
  await expect(form).toBeVisible()
  const quantityInput = form.getByLabel('Nieuwe hoeveelheid')
  await expect(quantityInput).toHaveAttribute('step', 'any')
  await quantityInput.fill(expectedTargetQuantity)
  await expect(quantityInput).toHaveValue(expectedTargetQuantity)
  const inputValueBeforeSave = await quantityInput.inputValue()
  await form.getByLabel('Reden / notitie').fill(expectedNote)

  const mutationResponsePromise = page.waitForResponse((response) => (
    new URL(response.url()).pathname === `/api/household-articles/${encodeURIComponent(expectedArticleId)}/inventory-events`
      && response.request().method() === 'POST'
  ))
  const previewResponsePromise = page.waitForResponse((response) => (
    new URL(response.url()).pathname === '/api/dev/inventory-preview'
      && response.request().method() === 'GET'
  ))
  const detailRefreshResponsePromise = page.waitForResponse((response) => (
    new URL(response.url()).pathname === `/api/household-articles/${encodeURIComponent(expectedArticleId)}`
      && response.request().method() === 'GET'
  ))

  await form.getByRole('button', { name: 'Opslaan', exact: true }).click()
  const mutationResponse = await mutationResponsePromise
  const mutationData = await mutationResponse.json().catch(() => ({}))
  expect(mutationResponse.ok(), JSON.stringify(mutationData)).toBeTruthy()

  const [previewResponse, detailRefreshResponse] = await Promise.all([
    previewResponsePromise,
    detailRefreshResponsePromise,
  ])
  const previewData = await previewResponse.json().catch(() => ({}))
  const detailRefreshData = await detailRefreshResponse.json().catch(() => ({}))
  const previewRow = (Array.isArray(previewData?.rows) ? previewData.rows : []).find(
    (row) => String(row?.id || '') === expectedInventoryId,
  ) || null
  const detailInventory = Array.isArray(detailRefreshData?.inventory) ? detailRefreshData.inventory : []
  const detailInventoryRow = detailInventory.find((row) => String(row?.id || '') === expectedInventoryId) || null
  const diagnostic = {
    inputValue: inputValueBeforeSave,
    requestPostData: mutationResponse.request().postDataJSON?.() || mutationResponse.request().postData(),
    mutationRowQuantity: mutationData?.inventory?.quantity ?? mutationData?.inventory?.aantal ?? null,
    mutationRowNewQuantity: mutationData?.row_new_quantity ?? null,
    previewQuantity: previewRow?.aantal ?? null,
    detailQuantity: detailInventoryRow?.quantity ?? detailInventoryRow?.aantal ?? null,
  }
  console.log(`P0_INVENTORY_DECIMAL_DIAGNOSTIC=${JSON.stringify(diagnostic)}`)

  await expect(page.getByTestId('article-stock-mutation-success')).toContainText('Voorraadcorrectie is opgeslagen.', { timeout: 20_000 })

  const stockRow = page.getByTestId(new RegExp(`^article-stock-row-${expectedInventoryId}-`))
  await expect(stockRow).toContainText(expectedTargetQuantity, { timeout: 20_000 })

  await page.getByRole('tab', { name: 'Historie', exact: true }).click()
  await expect(page.getByTestId('history-page')).toBeVisible({ timeout: 30_000 })
  const correctionHistory = page.locator('[data-testid^="history-row-"]').filter({ hasText: expectedNote }).first()
  await expect(correctionHistory).toBeVisible({ timeout: 30_000 })
  await expect(correctionHistory).toContainText('Handmatige voorraadaanpassing')
  await expect(correctionHistory).toContainText(expectedTargetQuantity)

  writeFileSync('p0-inventory-browser-proof.json', JSON.stringify({
    email: accountEmail,
    articleId: expectedArticleId,
    articleName: expectedArticleName,
    inventoryId: expectedInventoryId,
    targetQuantity: expectedTargetQuantity,
    note: expectedNote,
  }, null, 2))

  console.log('P0_INVENTORY_CORRECTION_BROWSER_GREEN')
  console.log('P0_INVENTORY_DECIMAL_BROWSER_GREEN')
})