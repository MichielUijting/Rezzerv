import { test, expect } from '@playwright/test'

const email = process.env.PLAYWRIGHT_P0_ACCOUNT_SESSION_EMAIL
const password = process.env.PLAYWRIGHT_P0_ACCOUNT_SESSION_PASSWORD
const householdName = process.env.PLAYWRIGHT_P0_ACCOUNT_SESSION_HOUSEHOLD

function required(name, value) {
  if (!String(value || '').trim()) throw new Error(`${name} ontbreekt voor P0 account/session authority`)
  return String(value).trim()
}

async function completeInitialRegistrationAndOnboarding(page, accountEmail, accountPassword, expectedHouseholdName) {
  await page.goto('/registreren')
  await expect(page.getByTestId('register-page')).toBeVisible()
  await page.getByTestId('register-email').fill(accountEmail)
  await page.getByTestId('register-password').fill(accountPassword)
  await page.getByTestId('register-password-repeat').fill(accountPassword)

  const registrationResponsePromise = page.waitForResponse((response) => (
    response.url().includes('/api/auth/register')
    && response.request().method() === 'POST'
  ))
  await page.getByTestId('register-submit').click()
  const registrationResponse = await registrationResponsePromise
  expect(registrationResponse.status()).toBe(201)

  await expect(page.getByTestId('onboarding-use-case-page')).toBeVisible()
  await page.getByTestId('onboarding-choice-wat_inhuis').check()
  await page.getByTestId('onboarding-primary-continue').click()

  await expect(page.getByTestId('onboarding-wat-inhuis-follow-up')).toBeVisible()
  await page.getByTestId('wat-inhuis-tracking-quantity').check()
  await page.getByTestId('wat-inhuis-global-locations-no').check()
  await page.getByTestId('wat-inhuis-almost-out-yes').check()
  await page.getByTestId('wat-inhuis-shopping-yes').check()
  await page.getByTestId('wat-inhuis-finish').click()

  await expect(page.getByTestId('onboarding-shared-household-minimum')).toBeVisible()
  await page.getByTestId('shared-household-name').fill(expectedHouseholdName)
  await page.getByTestId('shared-household-usage-alone').check()
  await page.getByTestId('shared-household-finish').click()

  await expect(page).toHaveURL(/\/home$/)
  await expect(page.getByTestId('dynamic-home-navigation')).toBeVisible()
}

async function logoutThroughMyAccount(page) {
  await page.goto('/instellingen/mijn-account')
  await expect(page.getByTestId('settings-my-account-page')).toBeVisible()
  await expect(page.getByTestId('my-account-logout')).toBeVisible()

  const logoutResponsePromise = page.waitForResponse((response) => (
    response.url().includes('/api/auth/logout')
    && response.request().method() === 'POST'
  ))
  await page.getByTestId('my-account-logout').click()
  const logoutResponse = await logoutResponsePromise
  expect(logoutResponse.status()).toBe(204)
  await expect(page).toHaveURL(/\/login$/)
  await expect(page.getByTestId('login-page')).toBeVisible()
}

test('P0 account/session existing-user login -> server session -> logout -> stale session 401', async ({ page, request }) => {
  const accountEmail = required('PLAYWRIGHT_P0_ACCOUNT_SESSION_EMAIL', email)
  const accountPassword = required('PLAYWRIGHT_P0_ACCOUNT_SESSION_PASSWORD', password)
  const expectedHouseholdName = required('PLAYWRIGHT_P0_ACCOUNT_SESSION_HOUSEHOLD', householdName)

  // Fixture setup through the real user flow. The account is existing before the login authority starts.
  await completeInitialRegistrationAndOnboarding(page, accountEmail, accountPassword, expectedHouseholdName)
  await logoutThroughMyAccount(page)

  // Explicit existing-user browser login.
  await page.getByTestId('login-email').fill(accountEmail)
  await page.getByTestId('login-password').fill(accountPassword)
  const loginResponsePromise = page.waitForResponse((response) => (
    response.url().includes('/api/auth/login')
    && response.request().method() === 'POST'
  ))
  await page.getByTestId('login-submit').click()
  const loginResponse = await loginResponsePromise
  expect(loginResponse.ok()).toBeTruthy()

  await expect(page).toHaveURL(/\/home$/)
  await expect(page.getByTestId('dynamic-home-navigation')).toBeVisible()

  const liveSessionResponse = await page.request.get('/api/session')
  expect(liveSessionResponse.ok()).toBeTruthy()
  const liveSession = await liveSessionResponse.json()
  expect(liveSession.email).toBe(accountEmail.toLowerCase())
  expect(liveSession.context_type).toBe('regular')
  expect(liveSession.role).toBe('admin')

  const sessionCookie = (await page.context().cookies()).find((cookie) => cookie.name === 'rezzerv_session')
  expect(sessionCookie?.value).toBeTruthy()
  const staleCookieHeader = `rezzerv_session=${sessionCookie.value}`

  // Explicit browser logout must revoke the server-side session, not only remove browser state.
  await logoutThroughMyAccount(page)

  const cookiesAfterLogout = await page.context().cookies()
  expect(cookiesAfterLogout.some((cookie) => cookie.name === 'rezzerv_session')).toBe(false)

  const staleSessionResponse = await request.get('/api/session', {
    headers: { Cookie: staleCookieHeader },
  })
  expect(staleSessionResponse.status()).toBe(401)

  await page.goto('/voorraad')
  await expect(page).toHaveURL(/\/login$/)
  await expect(page.getByTestId('login-page')).toBeVisible()

  console.log('P0_ACCOUNT_SESSION_BROWSER_AUTHORITY_GREEN')
})
