import { test, expect } from '@playwright/test'

const wrongAccountToken = 'ui-wrong-account-token'
const newAccountToken = 'ui-new-account-token'

test('invitation keeps its token while switching away from the wrong authenticated account', async ({ page }) => {
  let logoutCalled = false

  await page.route(`**/api/household/invitations/accept/${wrongAccountToken}`, async (route) => {
    if (route.request().method() !== 'GET') return route.continue()
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        status: 'pending',
        household_name: 'Samen thuis',
        invitee_email_masked: 'u***r@example.com',
        account_exists: true,
        expires_at: '2099-01-01T00:00:00+00:00',
        authenticated: true,
        authenticated_email_matches: false,
      }),
    })
  })

  await page.route('**/api/auth/logout', async (route) => {
    logoutCalled = true
    await route.fulfill({ status: 200, contentType: 'application/json', body: '{"ok":true}' })
  })

  await page.goto(`/uitnodiging/${wrongAccountToken}`)
  await expect(page.getByTestId('invitation-acceptance-page')).toBeVisible()
  await expect(page.getByTestId('invitation-wrong-account-actions')).toBeVisible()
  await expect(page.getByTestId('invitation-accept-current')).toHaveCount(0)

  await page.getByTestId('invitation-use-another-account').click()
  await expect(page).toHaveURL(new RegExp(`/uitnodiging/${wrongAccountToken}$`))
  await expect(page.getByTestId('invitation-login-form')).toBeVisible()
  expect(logoutCalled).toBe(true)
})

test('new-account invitation UI posts only to invitation-specific registration', async ({ page }) => {
  let registrationPayload = null
  let genericRegistrationCalled = false

  await page.route(`**/api/household/invitations/accept/${newAccountToken}`, async (route) => {
    if (route.request().method() !== 'GET') return route.continue()
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        status: 'pending',
        household_name: 'Samen thuis',
        invitee_email_masked: 'n********n@example.com',
        account_exists: false,
        expires_at: '2099-01-01T00:00:00+00:00',
        authenticated: false,
        authenticated_email_matches: false,
      }),
    })
  })

  await page.route(`**/api/household/invitations/accept/${newAccountToken}/register`, async (route) => {
    registrationPayload = route.request().postDataJSON()
    await route.fulfill({
      status: 201,
      contentType: 'application/json',
      body: JSON.stringify({
        context_type: 'regular',
        user_id: 'new-person-id',
        email: 'new-person@example.com',
        active_household_id: 'hh-invite',
        active_household_name: 'Samen thuis',
        role: 'member',
        is_frontteam: false,
        is_superuser: false,
        invitation_accepted: true,
      }),
    })
  })

  await page.route('**/api/auth/register', async (route) => {
    genericRegistrationCalled = true
    await route.abort()
  })

  await page.goto(`/uitnodiging/${newAccountToken}`)
  await expect(page.getByTestId('invitation-register-form')).toBeVisible()
  await expect(page.getByText('er wordt geen extra leeg huishouden aangemaakt', { exact: false })).toBeVisible()

  await page.getByTestId('invitation-register-email').fill('new-person@example.com')
  await page.getByTestId('invitation-register-password').fill('NewPersonPassword123')
  await page.getByTestId('invitation-register-password-repeat').fill('NewPersonPassword123')

  const requestPromise = page.waitForRequest((request) => (
    request.method() === 'POST'
      && request.url().includes(`/api/household/invitations/accept/${newAccountToken}/register`)
  ))
  await page.getByTestId('invitation-register-submit').click()
  await requestPromise

  expect(registrationPayload).toEqual({
    email: 'new-person@example.com',
    password: 'NewPersonPassword123',
  })
  expect(genericRegistrationCalled).toBe(false)
})
