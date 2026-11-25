import { createHash } from 'node:crypto'
import { writeFileSync } from 'node:fs'
import { test, expect } from '@playwright/test'

const adminEmail = process.env.PLAYWRIGHT_L4_MEMBERSHIP_ADMIN_EMAIL
const memberEmail = process.env.PLAYWRIGHT_L4_MEMBERSHIP_MEMBER_EMAIL
const password = process.env.PLAYWRIGHT_L4_MEMBERSHIP_PASSWORD
const adminHousehold = process.env.PLAYWRIGHT_L4_MEMBERSHIP_ADMIN_HOUSEHOLD
const memberHousehold = process.env.PLAYWRIGHT_L4_MEMBERSHIP_MEMBER_HOUSEHOLD
const resendSinkUrl = process.env.PLAYWRIGHT_L4_RESEND_SINK_URL

function required(name, value) {
  if (!String(value || '').trim()) throw new Error(`${name} ontbreekt voor L4-02`)
  return String(value).trim()
}

async function registerAndCompleteWatInhuis(page, email, accountPassword, householdName) {
  // The one-screen quick start creates account and configured household atomically.
  // Preserve this P0 journey after the optional store-connection step.
  await page.goto('/registreren')
  await expect(page.getByTestId('register-page')).toBeVisible()
  await expect(page.getByTestId('register-password-repeat')).toHaveCount(0)
  await expect(page.getByTestId('register-quick-start-defaults')).toContainText('Wat Inhuis · Aantallen · Alleen')
  await page.getByTestId('register-email').fill(email)
  await page.getByTestId('register-password').fill(accountPassword)
  await page.getByTestId('register-household-name').fill(householdName)
  const responsePromise = page.waitForResponse((response) => (
    new URL(response.url()).pathname === '/api/auth/register'
    && response.request().method() === 'POST'
  ))
  await page.getByTestId('register-submit').click()
  const response = await responsePromise
  expect(response.status()).toBe(201)
  const registration = await response.json()
  expect(registration.onboarding?.onboarding_status).toBe('completed')
  expect(registration.onboarding?.primary_use_case).toBe('wat_inhuis')
  expect(registration.onboarding?.household_usage_mode).toBe('alone')
  expect(registration.onboarding?.household_name).toBe(householdName)
  expect(registration.onboarding?.product_configuration?.inventory_tracking_level).toBe('quantity')
  await expect(page).toHaveURL(/\/onboarding\/winkels$/)
  // The household journey must use the PO-approved independent store choice
  // instead of the now-retired three-arrow/settings overview walkthrough.
  await expect(page.getByTestId('store-onboarding-selection')).toBeVisible()
  await expect(page.getByTestId('receipt-connections-overview')).toHaveCount(0)
  await expect(page.getByTestId('onboarding-store-arrow')).toHaveCount(0)
  await page.setViewportSize({ width: 390, height: 844 })
  await expect(page.getByTestId('store-onboarding-selection')).toBeVisible()
  for (const store of ['ah', 'jumbo', 'lidl']) {
    const row = page.getByTestId(`onboarding-store-row-${store}`)
    await expect(row).toBeVisible()
    await expect(row).toHaveAttribute('data-result', 'neutral')
    await expect(page.getByTestId(`onboarding-select-${store}`)).not.toBeChecked()
    // The store name is the semantic row header (th); two data cells follow.
    await expect(row.locator('th, td')).toHaveCount(3)
  }
  await page.setViewportSize({ width: 1280, height: 720 })
  await page.getByTestId('onboarding-stores-later').click()
  await expect(page).toHaveURL(/\/home\?wegwijs=1$/)
  await expect(page.getByTestId('first-use-dashboard-guide')).toBeVisible()
  await page.keyboard.press('Escape')
  await expect(page.getByTestId('first-use-dashboard-guide')).toHaveCount(0)
  await expect(page).toHaveURL(/\/home$/)
}

async function readSession(page) {
  const response = await page.request.get('/api/session')
  expect(response.ok()).toBeTruthy()
  return response.json()
}

async function switchHouseholdAndWait(page, switcher, label, expectedHouseholdId) {
  const expectedId = String(expectedHouseholdId || '').trim()
  expect(expectedId).not.toBe('')

  const switchResponsePromise = page.waitForResponse((response) => (
    response.url().includes('/api/session/household')
    && response.request().method() === 'POST'
  ))

  await switcher.selectOption({ label })
  const switchResponse = await switchResponsePromise
  expect(switchResponse.ok()).toBeTruthy()
  const switchPayload = await switchResponse.json()
  expect(String(switchPayload?.active_household_id || '')).toBe(expectedId)

  await expect.poll(async () => {
    const response = await page.request.get('/api/session')
    if (!response.ok()) return ''
    const session = await response.json()
    return String(session?.active_household_id || '')
  }, { timeout: 12_000 }).toBe(expectedId)
}

async function latestInvitationToken(request, sinkUrl) {
  await expect.poll(async () => {
    const response = await request.get(`${sinkUrl}/latest`)
    return response.status()
  }, { timeout: 10_000 }).toBe(200)

  const response = await request.get(`${sinkUrl}/latest`)
  expect(response.ok()).toBeTruthy()
  const payload = await response.json()
  const text = String(payload?.text || '')
  const match = text.match(/\/uitnodiging\/([^\s]+)/)
  expect(match, 'uitnodigingstoken ontbreekt in afgevangen externe mail').not.toBeNull()
  return decodeURIComponent(match[1])
}

test('L4-02 admin invite -> accept -> permissions -> household switch -> isolation', async ({ browser, request }, testInfo) => {
  const expectedAdminEmail = required('PLAYWRIGHT_L4_MEMBERSHIP_ADMIN_EMAIL', adminEmail).toLowerCase()
  const expectedMemberEmail = required('PLAYWRIGHT_L4_MEMBERSHIP_MEMBER_EMAIL', memberEmail).toLowerCase()
  const accountPassword = required('PLAYWRIGHT_L4_MEMBERSHIP_PASSWORD', password)
  const expectedAdminHousehold = required('PLAYWRIGHT_L4_MEMBERSHIP_ADMIN_HOUSEHOLD', adminHousehold)
  const expectedMemberHousehold = required('PLAYWRIGHT_L4_MEMBERSHIP_MEMBER_HOUSEHOLD', memberHousehold)
  const sinkUrl = required('PLAYWRIGHT_L4_RESEND_SINK_URL', resendSinkUrl)
  const baseURL = required('PLAYWRIGHT_BASE_URL', testInfo.project.use.baseURL)

  const adminContext = await browser.newContext({ baseURL })
  const memberContext = await browser.newContext({ baseURL })
  const adminPage = await adminContext.newPage()
  const memberPage = await memberContext.newPage()

  try {
    await registerAndCompleteWatInhuis(adminPage, expectedAdminEmail, accountPassword, expectedAdminHousehold)
    const adminSessionBeforeInvite = await readSession(adminPage)
    expect(adminSessionBeforeInvite.role).toBe('admin')
    expect(adminSessionBeforeInvite.active_household_name).toBe(expectedAdminHousehold)

    await registerAndCompleteWatInhuis(memberPage, expectedMemberEmail, accountPassword, expectedMemberHousehold)
    const memberOwnSession = await readSession(memberPage)
    expect(memberOwnSession.role).toBe('admin')
    expect(memberOwnSession.active_household_name).toBe(expectedMemberHousehold)
    expect(memberOwnSession.active_household_id).not.toBe(adminSessionBeforeInvite.active_household_id)

    await adminPage.goto('/instellingen/huishouden')
    await expect(adminPage.getByTestId('household-settings-page')).toBeVisible()
    await expect(adminPage.getByTestId('household-invitation-email-input')).toBeEnabled()
    await adminPage.getByTestId('household-invitation-email-input').fill(expectedMemberEmail)

    const invitationResponsePromise = adminPage.waitForResponse((response) => (
      response.url().includes('/api/household/invitations')
      && response.request().method() === 'POST'
    ))
    await adminPage.getByTestId('household-invitation-submit').click()
    const invitationResponse = await invitationResponsePromise
    expect(invitationResponse.status()).toBe(201)
    const invitationPayload = await invitationResponse.json()
    expect(invitationPayload.delivery.status).toBe('sent')
    await expect(adminPage.getByTestId('household-invitations-list')).toContainText(expectedMemberEmail)
    await expect(adminPage.getByTestId('household-invitations-list')).toContainText('In afwachting')

    const rawToken = await latestInvitationToken(request, sinkUrl)
    const acceptedInvitationTokenHash = createHash('sha256')
      .update(rawToken.trim(), 'utf8')
      .digest('hex')
    writeFileSync(
      'p0-l4-02-invitation-token-hash.txt',
      `${acceptedInvitationTokenHash}\n`,
      'utf8',
    )

    await memberPage.goto(`/uitnodiging/${encodeURIComponent(rawToken)}`)
    await expect(memberPage.getByTestId('invitation-acceptance-page')).toBeVisible()
    await expect(memberPage.getByTestId('invitation-authenticated-actions')).toBeVisible()
    await expect(memberPage.getByText(expectedAdminHousehold, { exact: false })).toBeVisible()

    const acceptResponsePromise = memberPage.waitForResponse((response) => (
      response.url().includes('/api/household/invitations/accept/')
      && response.request().method() === 'POST'
    ))
    await memberPage.getByTestId('invitation-accept-current').click()
    const acceptResponse = await acceptResponsePromise
    expect(acceptResponse.ok()).toBeTruthy()
    await expect(memberPage).toHaveURL(/\/home$/)

    const memberInAdminHousehold = await readSession(memberPage)
    expect(memberInAdminHousehold.role).toBe('member')
    expect(memberInAdminHousehold.active_household_name).toBe(expectedAdminHousehold)

    await memberPage.goto('/instellingen/huishouden')
    await expect(memberPage).toHaveURL(/\/home$/)
    await expect(memberPage.getByTestId('household-settings-page')).toHaveCount(0)

    const switcherInAdminHousehold = memberPage.getByTestId('household-switcher')
    await expect(switcherInAdminHousehold).toBeVisible()
    await expect(switcherInAdminHousehold.locator('option')).toHaveCount(2)
    await switchHouseholdAndWait(
      memberPage,
      switcherInAdminHousehold,
      expectedMemberHousehold,
      memberOwnSession.active_household_id,
    )

    const memberBackInOwnHousehold = await readSession(memberPage)
    expect(memberBackInOwnHousehold.role).toBe('admin')
    expect(memberBackInOwnHousehold.active_household_name).toBe(expectedMemberHousehold)

    await memberPage.goto('/instellingen/huishouden')
    await expect(memberPage.getByTestId('household-settings-page')).toBeVisible()
    await expect(memberPage.getByTestId('household-invitation-email-input')).toBeEnabled()
    await expect(memberPage.getByTestId(`household-member-${expectedMemberEmail}`)).toBeVisible()
    await expect(memberPage.getByTestId(`household-member-${expectedAdminEmail}`)).toHaveCount(0)

    const switcherInOwnHousehold = memberPage.getByTestId('household-switcher')
    await expect(switcherInOwnHousehold).toBeVisible()
    await switchHouseholdAndWait(
      memberPage,
      switcherInOwnHousehold,
      expectedAdminHousehold,
      adminSessionBeforeInvite.active_household_id,
    )

    const memberBackInAdminHousehold = await readSession(memberPage)
    expect(memberBackInAdminHousehold.role).toBe('member')
    expect(memberBackInAdminHousehold.active_household_name).toBe(expectedAdminHousehold)

    await adminPage.reload()
    await expect(adminPage.getByTestId('household-invitations-list')).toContainText(expectedMemberEmail)
    await expect(adminPage.getByTestId('household-invitations-list')).toContainText('Geaccepteerd')

    console.log('P0_L4_02_MEMBERSHIP_SWITCH_BROWSER_GREEN')
  } finally {
    await adminContext.close()
    await memberContext.close()
  }
})
