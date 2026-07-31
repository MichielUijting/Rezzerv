import { test, expect } from '@playwright/test'

const staleSuperuserContext = {
  user_id: 'supergebruiker@rezzerv.local',
  email: 'supergebruiker@rezzerv.local',
  active_household_id: '0',
  active_household_name: 'Regressietest huishouden 0',
  display_role: 'admin',
  memberships: [{ household_id: '0', role: 'owner' }],
}

const regularOwnerContext = {
  user_id: 'beheerder2@rezzerv.local',
  email: 'beheerder2@rezzerv.local',
  active_household_id: '2',
  active_household_name: 'Testhuishouden 2',
  display_role: 'admin',
  memberships: [{ household_id: '2', role: 'owner' }],
  permissions: { 'notifications.view': true },
}

async function mockRegularOwnerApis(page) {
  await page.route('**/api/auth/login', async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({ token: 'rezzerv-dev-token::beheerder2@rezzerv.local' }),
    })
  })
  await page.route('**/api/auth/context', async (route) => {
    await route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(regularOwnerContext) })
  })
  await page.route('**/api/household', async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({ id: '2', naam: 'Testhuishouden 2', is_household_admin: false, is_viewer: false }),
    })
  })
  await page.route('**/api/platform/toegang?*', async (route) => {
    await route.fulfill({ status: 403, contentType: 'application/json', body: JSON.stringify({ detail: 'Geen centrale bevoegdheid' }) })
  })
}

test.describe('Sessiewissel en centrale tegelisolatie', () => {
  test('wist Supergebruikerscontext, behoudt Meldingen en verbergt centrale tegels', async ({ page }) => {
    await mockRegularOwnerApis(page)
    await page.addInitScript((context) => {
      localStorage.setItem('rezzerv_token', 'rezzerv-dev-token::supergebruiker@rezzerv.local')
      localStorage.setItem('rezzerv_user_email', 'supergebruiker@rezzerv.local')
      localStorage.setItem('rezzerv_household_name', 'Regressietest huishouden 0')
      localStorage.setItem('rezzerv_auth_context', JSON.stringify(context))
      sessionStorage.setItem('rezzerv_auth_checked_token', 'rezzerv-dev-token::supergebruiker@rezzerv.local')
    }, staleSuperuserContext)

    await page.goto('/login')
    await page.getByTestId('login-email').fill('beheerder2@rezzerv.local')
    await page.getByTestId('login-password').fill('Rezzerv123')
    await page.getByTestId('login-submit').click()

    await expect(page).toHaveURL(/\/home$/)
    await expect(page.getByText(/Huishouden:\s*Testhuishouden 2/)).toBeVisible()
    await expect(page.getByText('Meldingen', { exact: true })).toBeVisible()
    await expect(page.getByText('Externe databases', { exact: true })).toHaveCount(0)
    await expect(page.getByText('Catalogus', { exact: true })).toHaveCount(0)
    await expect(page.getByText('Admin', { exact: true })).toHaveCount(0)

    const storedContext = await page.evaluate(() => JSON.parse(localStorage.getItem('rezzerv_auth_context') || '{}'))
    expect(storedContext.email).toBe('beheerder2@rezzerv.local')
    expect(storedContext.active_household_id).toBe('2')
  })

  test('negeert een vertraagde Supergebruikerscontext nadat Beheerder2 actief is geworden', async ({ page }) => {
    let releaseStaleResponse
    let reportStaleRequestStarted
    const staleResponseGate = new Promise((resolve) => { releaseStaleResponse = resolve })
    const staleRequestStarted = new Promise((resolve) => { reportStaleRequestStarted = resolve })

    await page.route('**/api/auth/context', async (route) => {
      const authorization = String(route.request().headers().authorization || '')
      if (authorization.includes('supergebruiker@rezzerv.local')) {
        reportStaleRequestStarted()
        await staleResponseGate
        await route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(staleSuperuserContext) })
        return
      }
      await route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(regularOwnerContext) })
    })
    await page.route('**/api/household', async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({ id: '2', naam: 'Testhuishouden 2', is_household_admin: false, is_viewer: false }),
      })
    })
    await page.route('**/api/platform/toegang?*', async (route) => {
      await route.fulfill({ status: 403, contentType: 'application/json', body: JSON.stringify({ detail: 'Geen centrale bevoegdheid' }) })
    })
    await page.addInitScript(() => {
      localStorage.setItem('rezzerv_token', 'rezzerv-dev-token::supergebruiker@rezzerv.local')
      localStorage.removeItem('rezzerv_auth_context')
      localStorage.removeItem('rezzerv_user_email')
      localStorage.removeItem('rezzerv_household_name')
      sessionStorage.removeItem('rezzerv_auth_checked_token')
    })

    await page.goto('/home')
    await staleRequestStarted

    await page.evaluate((context) => {
      localStorage.setItem('rezzerv_token', 'rezzerv-dev-token::beheerder2@rezzerv.local')
      localStorage.setItem('rezzerv_user_email', 'beheerder2@rezzerv.local')
      localStorage.setItem('rezzerv_household_name', 'Testhuishouden 2')
      localStorage.setItem('rezzerv_auth_context', JSON.stringify(context))
      sessionStorage.setItem('rezzerv_auth_checked_token', 'rezzerv-dev-token::beheerder2@rezzerv.local')
    }, regularOwnerContext)

    releaseStaleResponse()

    await expect(page).toHaveURL(/\/home$/)
    await expect(page.getByText(/Huishouden:\s*Testhuishouden 2/)).toBeVisible()
    await expect(page.getByText('Meldingen', { exact: true })).toBeVisible()
    await expect(page.getByText('Externe databases', { exact: true })).toHaveCount(0)
    await expect(page.getByText('Catalogus', { exact: true })).toHaveCount(0)
    await expect(page.getByText('Admin', { exact: true })).toHaveCount(0)

    const storedSession = await page.evaluate(() => ({
      token: localStorage.getItem('rezzerv_token'),
      email: localStorage.getItem('rezzerv_user_email'),
      household: localStorage.getItem('rezzerv_household_name'),
      context: JSON.parse(localStorage.getItem('rezzerv_auth_context') || '{}'),
    }))
    expect(storedSession.token).toBe('rezzerv-dev-token::beheerder2@rezzerv.local')
    expect(storedSession.email).toBe('beheerder2@rezzerv.local')
    expect(storedSession.household).toBe('Testhuishouden 2')
    expect(storedSession.context.active_household_id).toBe('2')
  })

  test('weigert een reguliere Eigenaar directe toegang tot technisch admin', async ({ page }) => {
    await page.route('**/api/auth/context', async (route) => {
      await route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(regularOwnerContext) })
    })
    await page.route('**/api/platform/toegang?*', async (route) => {
      await route.fulfill({ status: 403, contentType: 'application/json', body: JSON.stringify({ detail: 'Geen centrale bevoegdheid' }) })
    })
    await page.addInitScript((context) => {
      localStorage.setItem('rezzerv_token', 'rezzerv-dev-token::beheerder2@rezzerv.local')
      localStorage.setItem('rezzerv_auth_context', JSON.stringify(context))
      sessionStorage.removeItem('rezzerv_auth_checked_token')
    }, regularOwnerContext)

    await page.goto('/admin')
    await expect(page).toHaveURL(/\/home$/)
  })
})
