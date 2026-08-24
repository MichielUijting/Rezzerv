import { expect, test } from '@playwright/test'

const RECOVERY_PERMISSION = 'platform.recovery.manage'
const PURGE_ENDPOINT = '**/api/admin/receipts/purge-archived'

const noneSession = {
  user: { id: 'platform-recovery-user', email: 'platform-recovery@example.test' },
  user_id: 'platform-recovery-user',
  email: 'platform-recovery@example.test',
  context_type: 'none',
  active_household_id: null,
  active_household_name: '',
  role: null,
  display_role: null,
  permissions: { [RECOVERY_PERMISSION]: true },
  supported_permissions: [RECOVERY_PERMISSION],
  is_platform_superuser: false,
  is_frontteam: false,
}

async function mockSession(page, session) {
  await page.route('**/api/session', async (route) => {
    await route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(session) })
  })
}

test('recovery page requires an explicit target and exact typed confirmation before purge', async ({ page }) => {
  await mockSession(page, noneSession)
  const purgeRequests = []

  await page.route(PURGE_ENDPOINT, async (route) => {
    const request = route.request()
    purgeRequests.push({
      method: request.method(),
      body: request.postDataJSON(),
      headers: request.headers(),
    })
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({ ok: true }),
    })
  })

  await page.goto('/home')
  await expect(page.getByTestId('platform-home-tile-recovery')).toBeVisible()
  await expect(page.locator('[data-testid^="platform-home-tile-"]')).toHaveCount(1)

  await page.goto('/platform/herstel')
  await expect(page.getByTestId('platform-recovery-page')).toBeVisible()
  await expect(page.getByText('Deze actie gebruikt geen actief huishouden en valt nooit terug op huishouden 0.')).toBeVisible()
  expect(purgeRequests).toEqual([])

  const targetInput = page.getByTestId('platform-recovery-household-id')
  const openButton = page.getByRole('button', { name: 'Gearchiveerde bonnen definitief verwijderen', exact: true })

  await expect(openButton).toBeDisabled()
  await targetInput.fill('   ')
  await expect(openButton).toBeDisabled()
  expect(purgeRequests).toEqual([])

  await targetInput.fill('  household-recovery-target  ')
  await expect(openButton).toBeEnabled()
  await openButton.click()
  await expect(page.getByTestId('platform-recovery-confirmation')).toBeVisible()
  await expect(targetInput).toBeDisabled()
  expect(purgeRequests).toEqual([])

  const confirmationInput = page.getByTestId('platform-recovery-confirm-household-id')
  const confirmButton = page.getByRole('button', { name: 'Definitieve verwijdering bevestigen', exact: true })

  await expect(confirmButton).toBeDisabled()
  await confirmationInput.fill('household-other-target')
  await expect(confirmButton).toBeDisabled()
  expect(purgeRequests).toEqual([])

  await confirmationInput.fill('household-recovery-target')
  await expect(confirmButton).toBeEnabled()
  await confirmButton.click()

  const result = page.getByTestId('platform-recovery-result')
  await expect(result).toContainText('Herstelactie afgerond voor huishouden: household-recovery-target')
  await expect(result).toContainText('De server heeft de definitieve verwijdering succesvol verwerkt.')

  expect(purgeRequests).toHaveLength(1)
  expect(purgeRequests[0].method).toBe('POST')
  expect(purgeRequests[0].body).toEqual({ household_id: 'household-recovery-target' })
  expect(purgeRequests[0].headers.authorization).toBeUndefined()
  expect(purgeRequests[0].headers['x-admin-key']).toBeUndefined()
})

test('recovery confirmation can be cancelled without issuing a purge request', async ({ page }) => {
  await mockSession(page, noneSession)
  let purgeCalls = 0

  await page.route(PURGE_ENDPOINT, async (route) => {
    purgeCalls += 1
    await route.fulfill({ status: 200, contentType: 'application/json', body: '{"ok":true}' })
  })

  await page.goto('/platform/herstel')
  await page.getByTestId('platform-recovery-household-id').fill('household-recovery-target')
  await page.getByRole('button', { name: 'Gearchiveerde bonnen definitief verwijderen', exact: true }).click()
  await page.getByTestId('platform-recovery-confirm-household-id').fill('household-recovery-target')
  await page.getByRole('button', { name: 'Annuleren', exact: true }).click()

  await expect(page.getByTestId('platform-recovery-confirmation')).toHaveCount(0)
  expect(purgeCalls).toBe(0)
})

test('recovery direct route stays closed without permission and performs no purge', async ({ page }) => {
  const auditOnlySession = {
    ...noneSession,
    permissions: { 'platform.audit.view': true },
    supported_permissions: ['platform.audit.view'],
  }
  await mockSession(page, auditOnlySession)
  let purgeCalls = 0

  await page.route(PURGE_ENDPOINT, async (route) => {
    purgeCalls += 1
    await route.fulfill({ status: 200, contentType: 'application/json', body: '{"ok":true}' })
  })

  await page.goto('/platform/herstel')
  await expect(page).toHaveURL(/\/home$/)
  await expect(page.getByTestId('none-session-home')).toBeVisible()
  expect(purgeCalls).toBe(0)
})
