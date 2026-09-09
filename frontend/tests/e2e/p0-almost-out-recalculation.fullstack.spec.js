import { writeFileSync } from 'node:fs'
import { test, expect } from '@playwright/test'

const email = process.env.PLAYWRIGHT_P0_ALMOST_OUT_EMAIL
const password = process.env.PLAYWRIGHT_P0_ALMOST_OUT_PASSWORD
const articleId = process.env.PLAYWRIGHT_P0_ALMOST_OUT_ARTICLE_ID
const articleName = process.env.PLAYWRIGHT_P0_ALMOST_OUT_ARTICLE_NAME
const inventoryId = process.env.PLAYWRIGHT_P0_ALMOST_OUT_INVENTORY_ID
const initialQuantity = process.env.PLAYWRIGHT_P0_ALMOST_OUT_INITIAL_QUANTITY
const targetQuantity = process.env.PLAYWRIGHT_P0_ALMOST_OUT_TARGET_QUANTITY
const minStock = process.env.PLAYWRIGHT_P0_ALMOST_OUT_MIN_STOCK
const idealStock = process.env.PLAYWRIGHT_P0_ALMOST_OUT_IDEAL_STOCK
const note = process.env.PLAYWRIGHT_P0_ALMOST_OUT_NOTE

function required(name, value) {
  if (!String(value || '').trim()) throw new Error(`${name} ontbreekt voor P0 Almost-out recalculation authority`)
  return String(value).trim()
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

async function openInventoryArticle(page, expectedArticleId) {
  await page.goto('/voorraad')
  await expect(page.getByTestId('inventory-page')).toBeVisible({ timeout: 30_000 })
  const row = page.getByTestId(`inventory-row-${expectedArticleId}`)
  await expect(row).toBeVisible({ timeout: 30_000 })
  const responsePromise = page.waitForResponse((response) => (
    new URL(response.url()).pathname === `/api/household-articles/${encodeURIComponent(expectedArticleId)}`
    && response.request().method() === 'GET'
  ))
  await row.locator('[title="Dubbelklik op de rij voor details"]').dblclick()
  expect((await responsePromise).ok()).toBeTruthy()
  await expect(page.getByTestId('article-detail-page')).toBeVisible({ timeout: 30_000 })
}

async function configureAlmostOutThreshold(page, expectedMinStock, expectedIdealStock) {
  await page.getByTestId('article-overview-subtab-household').click()
  const settingsSection = page.getByTestId('article-household-settings-section')
  await expect(settingsSection).toBeVisible()
  const minStockInput = page.getByTestId('article-details-input-min_stock')
  const idealStockInput = page.getByTestId('article-details-input-ideal_stock')
  if (!(await minStockInput.isVisible())) {
    const toggle = settingsSection.getByRole('button', { name: 'Instellingen voor dit huishouden', exact: true })
    if ((await toggle.count()) > 0 && (await toggle.getAttribute('aria-expanded')) !== 'true') await toggle.click()
  }
  await minStockInput.fill(expectedMinStock)
  await idealStockInput.fill(expectedIdealStock)
  const responsePromise = page.waitForResponse((response) => (
    response.url().includes('/api/household-articles/')
    && response.url().includes('/settings')
    && response.request().method() === 'PUT'
  ))
  await page.getByTestId('article-household-settings-save').click()
  expect((await responsePromise).ok()).toBeTruthy()
}

async function expectAlmostOutPresence(page, expectedArticleName, expectedQuantity, expectedMinStock) {
  await page.goto('/bijna-op')
  await expect(page.getByTestId('almost-out-page')).toBeVisible({ timeout: 30_000 })
  const table = page.getByTestId('almost-out-table')
  await expect(table).toBeVisible()
  const row = table.getByRole('row').filter({ hasText: expectedArticleName })
  await expect(row).toHaveCount(1)
  await expect(row).toContainText(expectedQuantity)
  await expect(row).toContainText(expectedMinStock)
}

async function expectAlmostOutAbsence(page, expectedArticleName) {
  await page.goto('/bijna-op')
  await expect(page.getByTestId('almost-out-page')).toBeVisible({ timeout: 30_000 })
  const table = page.getByTestId('almost-out-table')
  await expect(table).toBeVisible()
  await expect(table.getByText(expectedArticleName, { exact: true })).toHaveCount(0)
}

test('P0 Almost-out replays existing history and changes visible projection', async ({ page }) => {
  test.setTimeout(180_000)
  const accountEmail = required('PLAYWRIGHT_P0_ALMOST_OUT_EMAIL', email).toLowerCase()
  const accountPassword = required('PLAYWRIGHT_P0_ALMOST_OUT_PASSWORD', password)
  const expectedArticleId = required('PLAYWRIGHT_P0_ALMOST_OUT_ARTICLE_ID', articleId)
  const expectedArticleName = required('PLAYWRIGHT_P0_ALMOST_OUT_ARTICLE_NAME', articleName)
  const expectedInventoryId = required('PLAYWRIGHT_P0_ALMOST_OUT_INVENTORY_ID', inventoryId)
  const expectedInitialQuantity = required('PLAYWRIGHT_P0_ALMOST_OUT_INITIAL_QUANTITY', initialQuantity)
  const expectedTargetQuantity = required('PLAYWRIGHT_P0_ALMOST_OUT_TARGET_QUANTITY', targetQuantity)
  const expectedMinStock = required('PLAYWRIGHT_P0_ALMOST_OUT_MIN_STOCK', minStock)
  const expectedIdealStock = required('PLAYWRIGHT_P0_ALMOST_OUT_IDEAL_STOCK', idealStock)
  const expectedNote = required('PLAYWRIGHT_P0_ALMOST_OUT_NOTE', note)

  await login(page, accountEmail, accountPassword)
  await openInventoryArticle(page, expectedArticleId)
  await configureAlmostOutThreshold(page, expectedMinStock, expectedIdealStock)
  await expectAlmostOutPresence(page, expectedArticleName, expectedInitialQuantity, expectedMinStock)

  await openInventoryArticle(page, expectedArticleId)
  await page.getByRole('tab', { name: 'Voorraad', exact: true }).click()
  const adjustButton = page.getByTestId(`article-stock-adjust-${expectedInventoryId}`)
  await expect(adjustButton).toBeVisible({ timeout: 20_000 })
  await adjustButton.click()

  const form = page.getByTestId('article-stock-mutation-form')
  await expect(form).toBeVisible()
  await form.getByLabel('Nieuwe hoeveelheid').fill(expectedTargetQuantity)
  await form.getByLabel('Reden / notitie').fill(expectedNote)
  const mutationResponsePromise = page.waitForResponse((response) => (
    new URL(response.url()).pathname === `/api/household-articles/${encodeURIComponent(expectedArticleId)}/inventory-events`
    && response.request().method() === 'POST'
  ))
  await form.getByRole('button', { name: 'Opslaan', exact: true }).click()
  const mutationResponse = await mutationResponsePromise
  const mutationData = await mutationResponse.json().catch(() => ({}))
  expect(mutationResponse.ok(), JSON.stringify(mutationData)).toBeTruthy()
  expect(String(mutationResponse.request().postDataJSON()?.quantity ?? '')).toBe(expectedTargetQuantity)
  await expect(page.getByTestId('article-stock-mutation-success')).toContainText('Voorraadcorrectie is opgeslagen.', { timeout: 20_000 })

  const stockRow = page.getByTestId(new RegExp(`^article-stock-row-${expectedInventoryId}-`))
  await expect(stockRow).toContainText(expectedTargetQuantity, { timeout: 20_000 })

  await page.getByRole('tab', { name: 'Historie', exact: true }).click()
  await expect(page.getByTestId('history-page')).toBeVisible({ timeout: 30_000 })
  const correctionHistory = page.locator('[data-testid^="history-row-"]').filter({ hasText: expectedNote }).first()
  await expect(correctionHistory).toBeVisible({ timeout: 30_000 })
  await expect(correctionHistory).toContainText('Handmatige voorraadaanpassing')

  await expectAlmostOutAbsence(page, expectedArticleName)

  writeFileSync('p0-almost-out-recalculation-browser-proof.json', JSON.stringify({
    email: accountEmail,
    articleId: expectedArticleId,
    articleName: expectedArticleName,
    inventoryId: expectedInventoryId,
    initialQuantity: expectedInitialQuantity,
    targetQuantity: expectedTargetQuantity,
    minStock: expectedMinStock,
    idealStock: expectedIdealStock,
    almostOutBefore: true,
    almostOutAfter: false,
    note: expectedNote,
  }, null, 2))

  console.log('P0_ALMOST_OUT_RECALCULATION_BROWSER_GREEN')
})
