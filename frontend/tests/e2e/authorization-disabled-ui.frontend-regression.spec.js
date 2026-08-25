import { test, expect } from '@playwright/test'
import { attachConsoleErrorCollector, expectNoConsoleErrors } from './helpers/rezzervAssertions.js'

const MESSAGE = 'Alleen de beheerder is geautoriseerd voor deze functie.'
const HOUSEHOLD_ID = '1'

async function seedSession(page, permissions = {}, displayRole = 'member') {
  await page.route('**/api/session', async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        user: { id: 'authorization-ui-test@rezzerv.local', email: 'authorization-ui-test@rezzerv.local' },
        user_id: 'authorization-ui-test@rezzerv.local',
        email: 'authorization-ui-test@rezzerv.local',
        active_household_id: HOUSEHOLD_ID,
        active_household_name: 'Testhuishouden',
        context_type: 'regular',
        role: displayRole,
        display_role: displayRole,
        permissions,
        supported_permissions: Object.keys(permissions),
        can_manage_member_permissions: Boolean(permissions['permissions.manage']),
        can_manage_members: Boolean(permissions['members.manage']),
        is_viewer: displayRole === 'viewer',
        is_platform_superuser: false,
        is_frontteam: false,
      }),
    })
  })
  await page.route('**/api/onboarding', async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({}),
    })
  })
}

async function dismissSuccessFeedback(page) {
  const overlay = page.getByTestId('app-feedback-success-overlay')
  await expect(overlay).toBeVisible()
  await page.getByTestId('app-feedback-success-ok-button').click()
  await expect(overlay).toHaveCount(0)
}

function householdPayload({ isAdmin = true, name = 'Testhuishouden' } = {}) {
  const members = [
    { email: 'admin@rezzerv.local', is_current_user: true, can_remove: false },
    { email: 'lid@rezzerv.local', is_current_user: false, can_remove: true },
  ]
  return { household_name: name, member_count: members.length, is_household_admin: isAdmin, members }
}

function authorizationPayload() {
  return {
    members: { household_id: HOUSEHOLD_ID, items: [
      { membership_id: 'membership-admin', email: 'admin@rezzerv.local', role_key: 'household.admin' },
      { membership_id: 'membership-member', email: 'lid@rezzerv.local', role_key: 'household.member' },
    ] },
    roles: { household_id: HOUSEHOLD_ID, items: [
      { role_key: 'household.member', name: 'Lid' },
      { role_key: 'household.admin', name: 'Beheerder' },
      { role_key: 'household.owner', name: 'Superuser' },
      { role_key: 'household.frontteam', name: 'Frontteamlid' },
    ] },
    permissions: { household_id: HOUSEHOLD_ID, items: [] },
  }
}

async function mockHouseholdScreen(page, { isAdmin = true, denyMutations = false } = {}) {
  const calls = { name: 0, add: 0, role: 0, remove: 0, forbidden: 0 }
  let currentName = 'Testhuishouden'
  const auth = authorizationPayload()
  const forbidden = async (route) => {
    calls.forbidden += 1
    await route.fulfill({ status: 403, contentType: 'application/json', body: JSON.stringify({ detail: 'Niet geautoriseerd' }) })
  }

  await page.route('**/api/household/members', async (route) => {
    if (route.request().method() === 'GET') {
      await route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(householdPayload({ isAdmin, name: currentName })) })
      return
    }
    calls.add += 1
    if (denyMutations) return forbidden(route)
    await route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(householdPayload({ isAdmin, name: currentName })) })
  })

  await page.route('**/api/household/name', async (route) => {
    calls.name += 1
    if (denyMutations) return forbidden(route)
    currentName = (await route.request().postDataJSON())?.name || currentName
    await route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(householdPayload({ isAdmin, name: currentName })) })
  })

  await page.route('**/api/household/members/*', async (route) => {
    if (route.request().method() === 'DELETE') calls.remove += 1
    if (denyMutations) return forbidden(route)
    await route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(householdPayload({ isAdmin, name: currentName })) })
  })

  await page.route('**/api/household/invitations', async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({ household_id: HOUSEHOLD_ID, items: [], total: 0 }),
    })
  })

  await page.route(`**/api/households/${HOUSEHOLD_ID}/authorization/members`, (route) => route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(auth.members) }))
  await page.route(`**/api/households/${HOUSEHOLD_ID}/authorization/roles`, (route) => route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(auth.roles) }))
  await page.route(`**/api/households/${HOUSEHOLD_ID}/authorization/permissions`, (route) => route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(auth.permissions) }))
  await page.route(`**/api/households/${HOUSEHOLD_ID}/authorization/members/*/role`, async (route) => {
    calls.role += 1
    if (denyMutations) return forbidden(route)
    await route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({ ok: true }) })
  })

  return calls
}

test.describe('Autorisatiegestuurde disabled-state', () => {
  test('niet-geautoriseerde tegel blijft zichtbaar, blokkeert navigatie en toont uitleg', async ({ page }) => {
    const consoleErrors = attachConsoleErrorCollector(page)
    await seedSession(page, { 'permissions.view': true })
    await page.goto('/instellingen')
    await expect(page.getByTestId('settings-page')).toBeVisible()

    const wrapper = page.locator('[data-authorization-message]').filter({ hasText: 'Artikelgroepen' })
    await expect(wrapper.getByText('Artikelgroepen', { exact: true })).toBeVisible()
    await expect(wrapper).toHaveAttribute('aria-label', MESSAGE)
    await wrapper.hover()
    await expect(wrapper.getByRole('tooltip')).toHaveText(MESSAGE)
    await wrapper.focus()
    await expect(wrapper.getByRole('tooltip')).toBeVisible()
    await wrapper.locator('a').click({ force: true })
    await expect(page).toHaveURL(/\/instellingen$/)
    await expectNoConsoleErrors(consoleErrors)
  })

  test('toegekende autorisatie laat normale navigatie toe', async ({ page }) => {
    const consoleErrors = attachConsoleErrorCollector(page)
    await seedSession(page, { 'article_groups.manage': true, 'permissions.view': true })
    await page.goto('/instellingen')
    const tile = page.getByText('Artikelgroepen', { exact: true })
    await expect(tile.locator('xpath=ancestor::a')).not.toHaveAttribute('aria-disabled', 'true')
    await tile.click()
    await expect(page).toHaveURL(/\/instellingen\/artikelgroepen$/)
    await expectNoConsoleErrors(consoleErrors)
  })

  test('beheerder kan naam, rol en leden via actiebuttons muteren', async ({ page }) => {
    const consoleErrors = attachConsoleErrorCollector(page)
    await seedSession(page, { 'household_settings.manage': true, 'members.manage': true, 'roles.manage': true }, 'admin')
    const calls = await mockHouseholdScreen(page, { isAdmin: true })
    await page.goto('/instellingen/huishouden')

    await page.getByTestId('household-name-input').fill('Molenstraat 19 Driel')
    await page.getByTestId('household-name-save').click()
    await expect.poll(() => calls.name).toBe(1)
    await dismissSuccessFeedback(page)

    await page.getByTestId('household-role-select-lid@rezzerv.local').selectOption('household.admin')
    await expect.poll(() => calls.role).toBe(1)
    await dismissSuccessFeedback(page)

    await page.getByTestId('household-member-email-input').fill('nieuw@rezzerv.local')
    await page.getByTestId('household-member-password-input').fill('Testwachtwoord-2026')
    await page.getByTestId('household-add-member').click()
    await expect.poll(() => calls.add).toBe(1)
    await dismissSuccessFeedback(page)

    await page.getByTestId('household-remove-lid@rezzerv.local').click()
    await page.getByTestId('household-remove-confirm').click()
    await expect.poll(() => calls.remove).toBe(1)
    await dismissSuccessFeedback(page)
    await expectNoConsoleErrors(consoleErrors)
  })

  test('niet-beheerder wordt bij huishoudroute geblokkeerd en gemanipuleerde mutatie krijgt 403', async ({ page }) => {
    const consoleErrors = attachConsoleErrorCollector(page)
    await seedSession(page, { 'permissions.view': true }, 'member')
    const calls = await mockHouseholdScreen(page, { isAdmin: false, denyMutations: true })
    await page.goto('/instellingen/huishouden')

    await expect(page).toHaveURL(/\/home$/)
    await expect(page.getByTestId('household-settings-page')).toHaveCount(0)
    expect(calls.name + calls.add + calls.role + calls.remove).toBe(0)
    await expectNoConsoleErrors(consoleErrors)

    const status = await page.evaluate(async () => {
      const response = await fetch('/api/household/name', {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ name: 'Ongeoorloofde wijziging' }),
      })
      return response.status
    })
    expect(status).toBe(403)
    expect(calls.forbidden).toBe(1)
  })
})
