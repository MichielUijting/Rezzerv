import { test, expect } from '@playwright/test'

const email = process.env.PLAYWRIGHT_P0_AUTH_LEGACY_EMAIL
const password = process.env.PLAYWRIGHT_P0_AUTH_LEGACY_PASSWORD

function required(name, value) {
  if (!String(value || '').trim()) throw new Error(`${name} ontbreekt voor P0 authorization/isolation authority`)
  return String(value).trim()
}

test('P0 authorization legacy advanced_member -> canonical permissions -> browser admin authority', async ({ page }) => {
  const accountEmail = required('PLAYWRIGHT_P0_AUTH_LEGACY_EMAIL', email).toLowerCase()
  const accountPassword = required('PLAYWRIGHT_P0_AUTH_LEGACY_PASSWORD', password)

  await page.goto('/login')
  await expect(page.getByTestId('login-page')).toBeVisible()
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

  const sessionResponse = await page.request.get('/api/session')
  expect(sessionResponse.ok()).toBeTruthy()
  const session = await sessionResponse.json()
  expect(session.email).toBe(accountEmail)
  expect(session.context_type).toBe('regular')
  expect(session.active_household_id).toBeTruthy()
  expect(session.role).toBe('advanced_member')
  expect(session.permissions?.['admin.access']).toBe(true)
  expect(session.permissions?.['members.manage']).toBe(true)
  expect(session.permissions?.['household_settings.manage']).toBe(true)
  expect(session.permissions?.['gpc.update']).toBe(true)
  expect(Boolean(session.permissions?.['catalog.update'])).toBe(false)

  // AdminGuard must follow the server-side permission projection, not a hard-coded
  // legacy role-name allowlist.
  await page.goto('/admin')
  await expect(page).toHaveURL(/\/admin$/)
  await expect(page.getByTestId('admin-page')).toBeVisible()

  await page.goto('/instellingen/huishouden/autorisaties')
  await expect(page).toHaveURL(/\/instellingen\/huishouden\/autorisaties$/)
  await expect(page.getByTestId('authorization-settings-page')).toBeVisible()
  await expect(page.getByTestId('authorization-role-matrix')).toBeVisible()

  const membersResponse = await page.request.get(
    `/api/households/${encodeURIComponent(session.active_household_id)}/authorization/members`,
  )
  expect(membersResponse.ok()).toBeTruthy()
  const members = await membersResponse.json()
  expect(members.total).toBe(1)
  expect(members.items[0].email).toBe(accountEmail)
  expect(members.items[0].legacy_role).toBe('advanced_member')
  expect(members.items[0].role_key).toBe('household.advanced_member')
  expect(members.items[0].is_current_user).toBe(true)

  console.log('P0_AUTHORIZATION_LEGACY_ROLE_BROWSER_GREEN')
})
