import { writeFileSync } from 'node:fs'
import { test, expect } from '@playwright/test'

function required(name) {
  const value = String(process.env[name] || '').trim()
  if (!value) throw new Error(`${name} ontbreekt voor F6-04 authority`)
  return value
}

async function register(page, email, password) {
  await page.goto('/registreren')
  await expect(page.getByTestId('register-page')).toBeVisible()
  await page.getByTestId('register-email').fill(email)
  await page.getByTestId('register-password').fill(password)
  await page.getByTestId('register-password-repeat').fill(password)
  const responsePromise = page.waitForResponse((response) => (
    new URL(response.url()).pathname === '/api/auth/register'
    && response.request().method() === 'POST'
  ))
  await page.getByTestId('register-submit').click()
  expect((await responsePromise).status()).toBe(201)
  await expect(page.getByTestId('onboarding-use-case-page')).toBeVisible()
}

async function login(page, email, password) {
  await page.goto('/login')
  await expect(page.getByTestId('login-page')).toBeVisible()
  await page.getByTestId('login-email').fill(email)
  await page.getByTestId('login-password').fill(password)
  const responsePromise = page.waitForResponse((response) => (
    new URL(response.url()).pathname === '/api/auth/login'
    && response.request().method() === 'POST'
  ))
  await page.getByTestId('login-submit').click()
  expect((await responsePromise).ok()).toBeTruthy()
}

async function selectPrimaryUseCase(page, useCase) {
  await page.getByTestId(`onboarding-choice-${useCase}`).check()
  const responsePromise = page.waitForResponse((response) => (
    new URL(response.url()).pathname === '/api/onboarding/primary-use-case'
    && response.request().method() === 'POST'
  ))
  await page.getByTestId('onboarding-primary-continue').click()
  expect((await responsePromise).ok()).toBeTruthy()
}

async function submitWatInhuisProfile(page, expectedStatus) {
  await expect(page.getByTestId('onboarding-wat-inhuis-follow-up')).toBeVisible({ timeout: 30_000 })
  await page.getByTestId('wat-inhuis-tracking-quantity').check()
  await page.getByTestId('wat-inhuis-global-locations-no').check()
  await page.getByTestId('wat-inhuis-almost-out-yes').check()
  await page.getByTestId('wat-inhuis-shopping-yes').check()
  const responsePromise = page.waitForResponse((response) => (
    new URL(response.url()).pathname === '/api/onboarding/wat-inhuis'
    && response.request().method() === 'POST'
  ))
  await page.getByTestId('wat-inhuis-finish').click()
  const response = await responsePromise
  expect(response.status()).toBe(expectedStatus)
  return response
}

async function completeInhuisHalenOnboarding(page, email, password, householdName) {
  await register(page, email, password)
  await selectPrimaryUseCase(page, 'inhuis_halen')
  await expect(page.getByTestId('onboarding-inhuis-halen-follow-up')).toBeVisible()
  const profileResponsePromise = page.waitForResponse((response) => (
    new URL(response.url()).pathname === '/api/onboarding/inhuis-halen'
    && response.request().method() === 'POST'
  ))
  await page.getByTestId('inhuis-halen-finish').click()
  expect((await profileResponsePromise).ok()).toBeTruthy()
  await expect(page.getByTestId('onboarding-shared-household-minimum')).toBeVisible()
  await page.getByTestId('shared-household-name').fill(householdName)
  await page.getByTestId('shared-household-usage-alone').check()
  const finishResponsePromise = page.waitForResponse((response) => (
    new URL(response.url()).pathname === '/api/onboarding/shared-household-minimum'
    && response.request().method() === 'POST'
  ))
  await page.getByTestId('shared-household-finish').click()
  expect((await finishResponsePromise).ok()).toBeTruthy()
  await expect(page).toHaveURL(/\/home$/, { timeout: 30_000 })
}

async function submitSettingsWatInhuisExpansion(page, expectedStatus) {
  await page.goto('/instellingen/mogelijkheden')
  await expect(page.getByTestId('settings-capabilities-page')).toBeVisible({ timeout: 30_000 })
  await page.getByTestId('capability-add-wat_inhuis').click()
  await expect(page.getByTestId('capability-expansion-form-wat_inhuis')).toBeVisible()
  await expect(page.getByTestId('capability-wat-global-locations')).toBeVisible()
  await page.getByTestId('capability-wat-global-locations').check()
  const responsePromise = page.waitForResponse((response) => (
    new URL(response.url()).pathname === '/api/onboarding/expand/wat-inhuis'
    && response.request().method() === 'POST'
  ))
  await page.getByTestId('capability-expansion-submit').click()
  const response = await responsePromise
  expect(response.status()).toBe(expectedStatus)
  return response
}

async function openInventoryArticle(page, articleId) {
  await page.goto('/voorraad')
  await expect(page.getByTestId('inventory-page')).toBeVisible({ timeout: 30_000 })
  const row = page.getByTestId(`inventory-row-${articleId}`)
  await expect(row).toBeVisible({ timeout: 30_000 })
  await row.locator('[title="Dubbelklik op de rij voor details"]').dblclick()
  await expect(page.getByTestId('article-detail-page')).toBeVisible({ timeout: 30_000 })
  await page.getByRole('tab', { name: 'Voorraad', exact: true }).click()
}

async function submitInventoryCorrection(page, inventoryId, targetQuantity, note, expectedStatus) {
  await page.getByTestId(`article-stock-adjust-${inventoryId}`).click()
  const form = page.getByTestId('article-stock-mutation-form')
  await expect(form).toBeVisible()
  await form.getByLabel('Nieuwe hoeveelheid').fill(targetQuantity)
  await form.getByLabel('Reden / notitie').fill(note)
  const responsePromise = page.waitForResponse((response) => (
    response.request().method() === 'POST'
    && /\/api\/household-articles\/[^/]+\/inventory-events$/.test(new URL(response.url()).pathname)
  ))
  await form.getByRole('button', { name: 'Opslaan', exact: true }).click()
  const response = await responsePromise
  expect(response.status()).toBe(expectedStatus)
  return response
}

test('F6-04 Onboarding interrupted mutation leaves profile step intact', async ({ page }) => {
  test.setTimeout(180_000)
  const email = required('PLAYWRIGHT_F6_04_ONBOARDING_EMAIL').toLowerCase()
  const password = required('PLAYWRIGHT_F6_04_ONBOARDING_PASSWORD')
  await register(page, email, password)
  await selectPrimaryUseCase(page, 'wat_inhuis')
  await submitWatInhuisProfile(page, 500)
  await expect(page.locator('.rz-alert')).toBeVisible({ timeout: 20_000 })
  await expect(page.getByTestId('onboarding-wat-inhuis-follow-up')).toBeVisible()
  writeFileSync('f6-04-onboarding-interrupted-browser-proof.json', JSON.stringify({ email, responseStatus: 500 }, null, 2))
  console.log('F6_04_ONBOARDING_INTERRUPTED_BROWSER_GREEN')
})

test('F6-04 Onboarding resumes through a new visible user action', async ({ page }) => {
  test.setTimeout(180_000)
  const email = required('PLAYWRIGHT_F6_04_ONBOARDING_EMAIL').toLowerCase()
  const password = required('PLAYWRIGHT_F6_04_ONBOARDING_PASSWORD')
  await login(page, email, password)
  await submitWatInhuisProfile(page, 200)
  await expect(page.getByTestId('onboarding-shared-household-minimum')).toBeVisible({ timeout: 30_000 })
  writeFileSync('f6-04-onboarding-resume-browser-proof.json', JSON.stringify({ email, responseStatus: 200 }, null, 2))
  console.log('F6_04_ONBOARDING_SAFE_RESUME_BROWSER_GREEN')
})

test('F6-04 Settings projection interruption rolls expansion back', async ({ page }) => {
  test.setTimeout(240_000)
  const email = required('PLAYWRIGHT_F6_04_SETTINGS_EMAIL').toLowerCase()
  const password = required('PLAYWRIGHT_F6_04_SETTINGS_PASSWORD')
  const householdName = required('PLAYWRIGHT_F6_04_SETTINGS_HOUSEHOLD')
  await completeInhuisHalenOnboarding(page, email, password, householdName)
  await submitSettingsWatInhuisExpansion(page, 500)
  await expect(page.locator('.rz-alert')).toBeVisible({ timeout: 20_000 })
  await expect(page.getByTestId('capability-expansion-form-wat_inhuis')).toBeVisible()
  writeFileSync('f6-04-settings-interrupted-browser-proof.json', JSON.stringify({ email, responseStatus: 500 }, null, 2))
  console.log('F6_04_SETTINGS_INTERRUPTED_BROWSER_GREEN')
})

test('F6-04 Settings projection resumes through a new visible user action', async ({ page }) => {
  test.setTimeout(180_000)
  const email = required('PLAYWRIGHT_F6_04_SETTINGS_EMAIL').toLowerCase()
  const password = required('PLAYWRIGHT_F6_04_SETTINGS_PASSWORD')
  await login(page, email, password)
  await expect(page).toHaveURL(/\/home$/, { timeout: 30_000 })
  await submitSettingsWatInhuisExpansion(page, 200)
  await expect(page.getByTestId('capability-active-wat_inhuis')).toBeVisible({ timeout: 20_000 })
  writeFileSync('f6-04-settings-resume-browser-proof.json', JSON.stringify({ email, responseStatus: 200 }, null, 2))
  console.log('F6_04_SETTINGS_SAFE_RESUME_BROWSER_GREEN')
})

test('F6-04 Inventory interruption leaves stock and history unchanged', async ({ page }) => {
  test.setTimeout(180_000)
  const email = required('PLAYWRIGHT_F6_04_INVENTORY_EMAIL').toLowerCase()
  const password = required('PLAYWRIGHT_F6_04_INVENTORY_PASSWORD')
  const articleId = required('PLAYWRIGHT_F6_04_INVENTORY_ARTICLE_ID')
  const inventoryId = required('PLAYWRIGHT_F6_04_INVENTORY_INVENTORY_ID')
  const initialQuantity = required('PLAYWRIGHT_F6_04_INVENTORY_INITIAL_QUANTITY')
  const targetQuantity = required('PLAYWRIGHT_F6_04_INVENTORY_TARGET_QUANTITY')
  const note = required('PLAYWRIGHT_F6_04_INVENTORY_NOTE')
  await login(page, email, password)
  await expect(page).toHaveURL(/\/home$/, { timeout: 30_000 })
  await openInventoryArticle(page, articleId)
  await expect(page.getByTestId(new RegExp(`^article-stock-row-${inventoryId}-`))).toContainText(initialQuantity)
  await submitInventoryCorrection(page, inventoryId, targetQuantity, note, 500)
  await expect(page.getByTestId('article-stock-mutation-error')).toBeVisible({ timeout: 20_000 })
  writeFileSync('f6-04-inventory-interrupted-browser-proof.json', JSON.stringify({ email, articleId, inventoryId, responseStatus: 500 }, null, 2))
  console.log('F6_04_INVENTORY_INTERRUPTED_BROWSER_GREEN')
})

test('F6-04 Inventory resumes through the same visible correction exactly once', async ({ page }) => {
  test.setTimeout(180_000)
  const email = required('PLAYWRIGHT_F6_04_INVENTORY_EMAIL').toLowerCase()
  const password = required('PLAYWRIGHT_F6_04_INVENTORY_PASSWORD')
  const articleId = required('PLAYWRIGHT_F6_04_INVENTORY_ARTICLE_ID')
  const inventoryId = required('PLAYWRIGHT_F6_04_INVENTORY_INVENTORY_ID')
  const targetQuantity = required('PLAYWRIGHT_F6_04_INVENTORY_TARGET_QUANTITY')
  const note = required('PLAYWRIGHT_F6_04_INVENTORY_NOTE')
  await login(page, email, password)
  await expect(page).toHaveURL(/\/home$/, { timeout: 30_000 })
  await openInventoryArticle(page, articleId)
  await submitInventoryCorrection(page, inventoryId, targetQuantity, note, 200)
  await expect(page.getByTestId('article-stock-mutation-success')).toContainText('Voorraadcorrectie is opgeslagen.', { timeout: 20_000 })
  await expect(page.getByTestId(new RegExp(`^article-stock-row-${inventoryId}-`))).toContainText(targetQuantity)
  writeFileSync('f6-04-inventory-resume-browser-proof.json', JSON.stringify({ email, articleId, inventoryId, responseStatus: 200 }, null, 2))
  console.log('F6_04_INVENTORY_SAFE_RESUME_BROWSER_GREEN')
})
