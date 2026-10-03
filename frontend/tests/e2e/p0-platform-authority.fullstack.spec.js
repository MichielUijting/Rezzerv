import { writeFileSync } from 'node:fs'
import { test, expect } from '@playwright/test'

const platformEmail = process.env.PLAYWRIGHT_L4_07_PLATFORM_EMAIL
const platformPassword = process.env.PLAYWRIGHT_L4_07_PLATFORM_PASSWORD
const superuserEmail = process.env.PLAYWRIGHT_L4_07_SUPERUSER_EMAIL
const superuserPassword = process.env.PLAYWRIGHT_L4_07_SUPERUSER_PASSWORD
const ipOwnerEmail = process.env.PLAYWRIGHT_L4_07_IP_OWNER_EMAIL
const ipOwnerPassword = process.env.PLAYWRIGHT_L4_07_IP_OWNER_PASSWORD
const ipOwnerUserId = process.env.PLAYWRIGHT_L4_07_IP_OWNER_USER_ID
const standaloneEmail = process.env.PLAYWRIGHT_L4_07_STANDALONE_EMAIL
const standaloneUserId = process.env.PLAYWRIGHT_L4_07_STANDALONE_USER_ID
const targetEmail = process.env.PLAYWRIGHT_L4_07_TARGET_EMAIL
const targetPassword = process.env.PLAYWRIGHT_L4_07_TARGET_PASSWORD
const targetHousehold = process.env.PLAYWRIGHT_L4_07_TARGET_HOUSEHOLD

test.describe.configure({ mode: 'serial' })

function required(name, value) {
  if (!String(value || '').trim()) throw new Error(`${name} ontbreekt voor L4-07`)
  return String(value).trim()
}

async function registerRegularHousehold(page, email, password, householdName) {
  await page.goto('/registreren')
  await expect(page.getByTestId('register-page')).toBeVisible()
  await page.getByTestId('register-email').fill(email)
  await page.getByTestId('register-password').fill(password)
  await page.getByTestId('register-password-repeat').fill(password)

  const registrationResponsePromise = page.waitForResponse((response) => (
    response.url().includes('/api/auth/register') && response.request().method() === 'POST'
  ))
  await page.getByTestId('register-submit').click()
  expect((await registrationResponsePromise).status()).toBe(201)

  await expect(page.getByTestId('onboarding-use-case-page')).toBeVisible()
  await page.getByTestId('onboarding-choice-wat_inhuis').check()
  const primaryResponsePromise = page.waitForResponse((response) => (
    response.url().includes('/api/onboarding/primary-use-case') && response.request().method() === 'POST'
  ))
  await page.getByTestId('onboarding-primary-continue').click()
  expect((await primaryResponsePromise).ok()).toBeTruthy()

  await expect(page.getByTestId('onboarding-wat-inhuis-follow-up')).toBeVisible()
  await page.getByTestId('wat-inhuis-tracking-quantity').check()
  await page.getByTestId('wat-inhuis-global-locations-no').check()
  await page.getByTestId('wat-inhuis-almost-out-yes').check()
  await page.getByTestId('wat-inhuis-shopping-yes').check()
  const productResponsePromise = page.waitForResponse((response) => (
    response.url().includes('/api/onboarding/wat-inhuis') && response.request().method() === 'POST'
  ))
  await page.getByTestId('wat-inhuis-finish').click()
  expect((await productResponsePromise).ok()).toBeTruthy()

  await expect(page.getByTestId('onboarding-shared-household-minimum')).toBeVisible()
  await page.getByTestId('shared-household-name').fill(householdName)
  await page.getByTestId('shared-household-usage-alone').check()
  const householdResponsePromise = page.waitForResponse((response) => (
    response.url().includes('/api/onboarding/shared-household-minimum') && response.request().method() === 'POST'
  ))
  await page.getByTestId('shared-household-finish').click()
  expect((await householdResponsePromise).ok()).toBeTruthy()
  await expect(page).toHaveURL(/\/home$/)
}

async function login(page, email, password) {
  await page.goto('/login')
  await expect(page.getByTestId('login-page')).toBeVisible()
  await page.getByTestId('login-email').fill(email)
  await page.getByTestId('login-password').fill(password)
  const loginResponsePromise = page.waitForResponse((response) => (
    response.url().includes('/api/auth/login') && response.request().method() === 'POST'
  ))
  await page.getByTestId('login-submit').click()
  const response = await loginResponsePromise
  expect(response.ok()).toBeTruthy()
  await expect(page).toHaveURL(/\/home$/)
}

async function readSession(page) {
  const response = await page.request.get('/api/session')
  expect(response.ok()).toBeTruthy()
  return response.json()
}

test('L4-07 platform admin revokes a household session without gaining household access', async ({ browser }) => {
  test.setTimeout(300_000)
  const adminEmail = required('PLAYWRIGHT_L4_07_PLATFORM_EMAIL', platformEmail).toLowerCase()
  const adminPassword = required('PLAYWRIGHT_L4_07_PLATFORM_PASSWORD', platformPassword)
  const householdUserEmail = required('PLAYWRIGHT_L4_07_TARGET_EMAIL', targetEmail).toLowerCase()
  const householdUserPassword = required('PLAYWRIGHT_L4_07_TARGET_PASSWORD', targetPassword)
  const householdName = required('PLAYWRIGHT_L4_07_TARGET_HOUSEHOLD', targetHousehold)

  const targetContext = await browser.newContext()
  const targetPage = await targetContext.newPage()
  await registerRegularHousehold(targetPage, householdUserEmail, householdUserPassword, householdName)
  const targetSession = await readSession(targetPage)
  expect(targetSession.context_type).toBe('regular')
  const targetHouseholdId = String(targetSession.active_household_id || '')
  expect(targetHouseholdId).not.toBe('')

  const platformContext = await browser.newContext()
  const platformPage = await platformContext.newPage()
  await login(platformPage, adminEmail, adminPassword)
  await expect(platformPage.getByTestId('none-session-home')).toBeVisible({ timeout: 30_000 })
  await expect(platformPage.getByTestId('platform-home-navigation')).toBeVisible()
  await expect(platformPage.getByTestId('platform-home-tile-sessions')).toBeVisible()
  await expect(platformPage.getByTestId('home-tile-voorraad')).toHaveCount(0)

  const platformSession = await readSession(platformPage)
  expect(platformSession.context_type).toBe('none')
  expect(platformSession.active_household_id ?? null).toBeNull()

  const householdsResponse = await platformPage.request.get('/api/session/households')
  expect(householdsResponse.ok()).toBeTruthy()
  expect(await householdsResponse.json()).toEqual({ items: [], total: 0, can_switch_households: false })

  await platformPage.getByTestId('platform-home-tile-sessions').click()
  await expect(platformPage).toHaveURL(/\/platform\/sessies$/)
  await expect(platformPage.getByTestId('platform-sessions-page')).toBeVisible({ timeout: 30_000 })
  await expect(platformPage.getByText(householdName, { exact: true })).toHaveCount(0)

  const targetSessionCard = platformPage
    .locator('[data-testid^="platform-session-"]')
    .filter({ hasText: householdUserEmail })
    .first()
  await expect(targetSessionCard).toBeVisible({ timeout: 30_000 })
  await expect(targetSessionCard).toContainText('Andere actieve sessie')
  await targetSessionCard.getByRole('button', { name: 'Sessie intrekken' }).click()

  const confirmation = platformPage.getByTestId('platform-session-confirmation')
  await expect(confirmation).toBeVisible()
  await expect(confirmation).toContainText(householdUserEmail)
  const revokeResponsePromise = platformPage.waitForResponse((response) => (
    new URL(response.url()).pathname.startsWith('/api/platform/sessions/')
    && new URL(response.url()).pathname.endsWith('/revoke')
    && response.request().method() === 'POST'
  ))
  await confirmation.getByRole('button', { name: 'Definitief intrekken' }).click()
  const revokeResponse = await revokeResponsePromise
  expect(revokeResponse.ok()).toBeTruthy()
  const revokePayload = await revokeResponse.json()
  const revokedSessionId = String(revokePayload?.item?.session_id || '')
  expect(revokedSessionId).not.toBe('')
  expect(revokePayload?.household_context_used).toBe(false)
  expect(revokePayload?.context_type).toBe('none')
  await expect(platformPage.getByRole('status')).toContainText(`Sessie van ${householdUserEmail} is ingetrokken.`)
  await expect(targetSessionCard).toHaveCount(0)

  const revokedTargetApi = await targetPage.request.get('/api/session')
  expect(revokedTargetApi.status()).toBe(401)
  await targetPage.goto('/voorraad')
  await expect(targetPage.getByTestId('login-page')).toBeVisible({ timeout: 30_000 })
  await expect(targetPage).toHaveURL(/\/login$/)

  await platformPage.goto('/voorraad')
  await expect(platformPage.getByTestId('none-session-home')).toBeVisible({ timeout: 30_000 })
  await expect(platformPage).toHaveURL(/\/home$/)
  await expect(platformPage.getByTestId('inventory-page')).toHaveCount(0)

  writeFileSync('p0-l4-07-browser-proof.json', JSON.stringify({
    platformEmail: adminEmail,
    targetEmail: householdUserEmail,
    targetHouseholdId,
    revokedSessionId,
  }, null, 2))

  console.log(`P0_L4_07_TARGET_HOUSEHOLD_ID=${targetHouseholdId}`)
  console.log(`P0_L4_07_REVOKED_SESSION_ID=${revokedSessionId}`)
  console.log('P0_L4_07_PLATFORM_LOGIN_NONE_CONTEXT_GREEN')
  console.log('P0_L4_07_SESSION_REVOKE_THROUGH_UI_GREEN')
  console.log('P0_L4_07_REVOKED_TARGET_SESSION_GREEN')
  console.log('P0_L4_07_NO_HOUSEHOLD_PRIVILEGE_ESCALATION_GREEN')

  await platformContext.close()
  await targetContext.close()
})

test('L4-07 superuser uses the visible read-only system management journey', async ({ page }) => {
  test.setTimeout(180_000)
  const email = required('PLAYWRIGHT_L4_07_SUPERUSER_EMAIL', superuserEmail).toLowerCase()
  const password = required('PLAYWRIGHT_L4_07_SUPERUSER_PASSWORD', superuserPassword)
  const householdName = required('PLAYWRIGHT_L4_07_TARGET_HOUSEHOLD', targetHousehold)

  await login(page, email, password)
  const session = await readSession(page)
  expect(session.context_type).toBe('system')
  expect(String(session.active_household_id)).toBe('0')

  await expect(page.getByTestId('home-tile-superuser')).toBeVisible({ timeout: 30_000 })
  await page.getByTestId('home-tile-superuser').click()
  await expect(page).toHaveURL(/\/superuser$/)
  await expect(page.getByTestId('superuser-dashboard')).toBeVisible({ timeout: 30_000 })
  await expect(page.getByRole('status', { name: 'Superuser alleen-lezen status' })).toContainText('alleen lezen')
  await page.getByRole('tab', { name: 'Huishoudens', exact: true }).click()
  await expect(page.getByTestId('superuser-households')).toBeVisible()
  await expect(page.getByTestId('superuser-households-table')).toContainText(householdName)
  await expect(page.getByTestId('platform-authorizations-page')).toHaveCount(0)

  writeFileSync('p0-l4-07-superuser-browser-proof.json', JSON.stringify({
    email,
    contextType: session.context_type,
    activeHouseholdId: session.active_household_id,
    householdName,
    authority: 'read-only-system-management',
  }, null, 2))

  console.log('P0_L4_07_SUPERUSER_SYSTEM_CONTEXT_GREEN')
  console.log('P0_L4_07_SUPERUSER_READ_ONLY_BROWSER_GREEN')
  console.log('P0_L4_07_SUPERUSER_NO_IP_OWNER_AUTHORITY_GREEN')
})

test('L4-07 IP owner manages only Superusers from a none-context landing', async ({ page }) => {
  test.setTimeout(180_000)
  const email = required('PLAYWRIGHT_L4_07_IP_OWNER_EMAIL', ipOwnerEmail).toLowerCase()
  const password = required('PLAYWRIGHT_L4_07_IP_OWNER_PASSWORD', ipOwnerPassword)
  const ownerId = required('PLAYWRIGHT_L4_07_IP_OWNER_USER_ID', ipOwnerUserId)
  const standaloneTargetEmail = required('PLAYWRIGHT_L4_07_STANDALONE_EMAIL', standaloneEmail).toLowerCase()
  const standaloneTargetId = required('PLAYWRIGHT_L4_07_STANDALONE_USER_ID', standaloneUserId)

  await login(page, email, password)
  const session = await readSession(page)
  expect(session.context_type).toBe('none')
  expect(session.active_household_id).toBeNull()
  expect(session.permissions?.['platform.special_roles.manage']).toBe(true)
  expect(session.permissions?.['platform.permissions.manage']).not.toBe(true)
  expect(session.permissions?.['platform.frontteam_roles.manage']).not.toBe(true)

  await page.goto('/home')
  await expect(page.getByTestId('ip-owner-home')).toBeVisible({ timeout: 30_000 })
  await expect(page.getByTestId('ip-owner-superusers-tile')).toBeVisible()
  await expect(page.getByText('Voorraad', { exact: true })).toHaveCount(0)
  await expect(page.getByText('Platformbeheer', { exact: true })).toHaveCount(0)

  await page.getByTestId('ip-owner-superusers-tile').click()
  await expect(page).toHaveURL(/\/ip-eigenaar\/superusers$/)
  await expect(page.getByTestId('ip-owner-superusers-page')).toBeVisible({ timeout: 30_000 })
  await expect(page.getByText('Platformbeheerder', { exact: true })).toHaveCount(0)
  await expect(page.getByText('Frontteamlid', { exact: true })).toHaveCount(0)

  const ownerCard = page.getByTestId(`ip-owner-superuser-${ownerId}`)
  await expect(ownerCard).toBeVisible()
  await expect(ownerCard).toContainText('IP-eigenaar')
  await expect(ownerCard.getByRole('button')).toHaveCount(0)

  const targetCard = page.getByTestId(`ip-owner-superuser-${standaloneTargetId}`)
  await expect(targetCard).toBeVisible()
  await expect(targetCard).toContainText(standaloneTargetEmail)

  const grantButton = targetCard.getByRole('button', { name: 'Superuser maken' })
  if (await grantButton.count()) {
    const grantResponsePromise = page.waitForResponse((response) => (
      new URL(response.url()).pathname === `/api/platform/authorizations/users/${standaloneTargetId}/superuser/grant`
      && response.request().method() === 'POST'
    ))
    await grantButton.click()
    const grantResponse = await grantResponsePromise
    expect(grantResponse.ok()).toBeTruthy()
  }

  await expect(targetCard.getByRole('button', { name: 'Deactiveren' })).toBeVisible()
  const revokeResponsePromise = page.waitForResponse((response) => (
    new URL(response.url()).pathname === `/api/platform/authorizations/users/${standaloneTargetId}/superuser/revoke`
    && response.request().method() === 'POST'
  ))
  await targetCard.getByRole('button', { name: 'Deactiveren' }).click()
  const revokeResponse = await revokeResponsePromise
  expect(revokeResponse.ok()).toBeTruthy()

  writeFileSync('p0-l4-07-ip-owner-browser-proof.json', JSON.stringify({
    email,
    userId: ownerId,
    contextType: session.context_type,
    activeHouseholdId: session.active_household_id,
    standaloneTargetEmail,
    standaloneTargetId,
    managedRole: 'platform.superuser',
  }, null, 2))

  console.log('P0_L4_07_IP_OWNER_NONE_CONTEXT_GREEN')
  console.log('P0_L4_07_IP_OWNER_SUPERUSER_ONLY_UI_GREEN')
  console.log('P0_L4_07_IP_OWNER_SUPERUSER_GRANT_REVOKE_GREEN')
})
