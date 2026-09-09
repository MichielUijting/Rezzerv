import { writeFileSync } from 'node:fs'
import { test, expect } from '@playwright/test'

const email = process.env.PLAYWRIGHT_F6_INVENTORY_EMAIL
const password = process.env.PLAYWRIGHT_F6_INVENTORY_PASSWORD
const articleId = process.env.PLAYWRIGHT_F6_INVENTORY_ARTICLE_ID
const inventoryId = process.env.PLAYWRIGHT_F6_INVENTORY_INVENTORY_ID
const initialQuantity = process.env.PLAYWRIGHT_F6_INVENTORY_INITIAL_QUANTITY
const targetQuantity = process.env.PLAYWRIGHT_F6_INVENTORY_TARGET_QUANTITY
const failureNote = process.env.PLAYWRIGHT_F6_INVENTORY_FAILURE_NOTE

function required(name, value) {
  if (!String(value || '').trim()) throw new Error(`${name} ontbreekt voor F6-01 Inventory authority`)
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
  await row.locator('[title="Dubbelklik op de rij voor details"]').dblclick()
  await expect(page.getByTestId('article-detail-page')).toBeVisible({ timeout: 30_000 })
}

test('F6-01 Inventory controlled 500 shows feedback and PostgreSQL state stays unchanged', async ({ page }) => {
  test.setTimeout(180_000)
  const accountEmail = required('PLAYWRIGHT_F6_INVENTORY_EMAIL', email).toLowerCase()
  const accountPassword = required('PLAYWRIGHT_F6_INVENTORY_PASSWORD', password)
  const expectedArticleId = required('PLAYWRIGHT_F6_INVENTORY_ARTICLE_ID', articleId)
  const expectedInventoryId = required('PLAYWRIGHT_F6_INVENTORY_INVENTORY_ID', inventoryId)
  const expectedInitialQuantity = required('PLAYWRIGHT_F6_INVENTORY_INITIAL_QUANTITY', initialQuantity)
  const expectedTargetQuantity = required('PLAYWRIGHT_F6_INVENTORY_TARGET_QUANTITY', targetQuantity)
  const expectedFailureNote = required('PLAYWRIGHT_F6_INVENTORY_FAILURE_NOTE', failureNote)

  await login(page, accountEmail, accountPassword)
  await openInventoryArticle(page, expectedArticleId)
  await page.getByRole('tab', { name: 'Voorraad', exact: true }).click()

  const stockRow = page.getByTestId(new RegExp(`^article-stock-row-${expectedInventoryId}-`))
  await expect(stockRow).toContainText(expectedInitialQuantity)

  await page.getByTestId(`article-stock-adjust-${expectedInventoryId}`).click()
  const form = page.getByTestId('article-stock-mutation-form')
  await expect(form).toBeVisible()
  await form.getByLabel('Nieuwe hoeveelheid').fill(expectedTargetQuantity)
  await form.getByLabel('Reden / notitie').fill(expectedFailureNote)

  const mutationResponsePromise = page.waitForResponse((response) => (
    new URL(response.url()).pathname === `/api/household-articles/${encodeURIComponent(expectedArticleId)}/inventory-events`
    && response.request().method() === 'POST'
  ))

  await form.getByRole('button', { name: 'Opslaan', exact: true }).click()
  const mutationResponse = await mutationResponsePromise
  expect(mutationResponse.status()).toBe(500)

  const visibleError = page.getByTestId('article-stock-mutation-error')
  await expect(visibleError).toBeVisible({ timeout: 20_000 })
  await expect(visibleError).toContainText('Voorraadmutatie kon niet worden opgeslagen.')
  const visibleFeedbackText = String(await visibleError.textContent() || '').trim()
  await expect(page.getByTestId('article-stock-mutation-success')).toHaveCount(0)

  await page.reload()
  await expect(page.getByTestId('article-detail-page')).toBeVisible({ timeout: 30_000 })
  await page.getByRole('tab', { name: 'Voorraad', exact: true }).click()
  await expect(page.getByTestId(new RegExp(`^article-stock-row-${expectedInventoryId}-`))).toContainText(expectedInitialQuantity)

  await page.getByRole('tab', { name: 'Historie', exact: true }).click()
  await expect(page.getByTestId('history-page')).toBeVisible({ timeout: 30_000 })
  await expect(page.locator('[data-testid^="history-row-"]').filter({ hasText: expectedFailureNote })).toHaveCount(0)

  writeFileSync('f6-inventory-controlled-5xx-browser-proof.json', JSON.stringify({
    email: accountEmail,
    articleId: expectedArticleId,
    inventoryId: expectedInventoryId,
    initialQuantity: expectedInitialQuantity,
    targetQuantity: expectedTargetQuantity,
    responseStatus: mutationResponse.status(),
    visibleFeedback: visibleFeedbackText,
  }, null, 2))

  console.log('F6_INVENTORY_CONTROLLED_500_BROWSER_GREEN')
  console.log('F6_INVENTORY_STANDARD_FEEDBACK_GREEN')
})
