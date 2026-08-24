import { expect, test } from '@playwright/test'

const INTEGRATIONS_PERMISSION = 'platform.integrations.manage'
const INTEGRATIONS_ENDPOINT = '**/api/platform/integrations'

const noneSession = {
  user: { id: 'platform-integrations-user', email: 'platform-integrations@example.test' },
  user_id: 'platform-integrations-user',
  email: 'platform-integrations@example.test',
  context_type: 'none',
  active_household_id: null,
  active_household_name: '',
  role: null,
  display_role: null,
  permissions: { [INTEGRATIONS_PERMISSION]: true },
  supported_permissions: [INTEGRATIONS_PERMISSION],
  is_platform_superuser: false,
  is_frontteam: false,
}

async function mockSession(page, session) {
  await page.route('**/api/session', async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify(session),
    })
  })
}

test('integrations page reads only the canonical secret-free platform status endpoint', async ({ page }) => {
  await mockSession(page, noneSession)
  const requests = []

  await page.route(INTEGRATIONS_ENDPOINT, async (route) => {
    const request = route.request()
    requests.push({
      method: request.method(),
      url: request.url(),
      headers: request.headers(),
      postData: request.postData(),
    })
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        items: [
          {
            key: 'receipt-scanner',
            label: 'Kassabonscanner',
            scope: 'platform',
            provider: 'rezzerv-legacy',
            status: 'ready',
            contract_version: '1.0',
            available_providers: ['rezzerv-legacy'],
          },
          {
            key: 'outbound-email',
            label: 'Uitgaande e-mail',
            scope: 'platform',
            provider: 'resend',
            status: 'incomplete',
            delivery_enabled: true,
            api_key_configured: true,
            sender_configured: false,
          },
        ],
        count: 2,
        read_only: true,
        household_context_used: false,
      }),
    })
  })

  await page.goto('/home')
  await expect(page.getByTestId('platform-home-tile-integrations')).toBeVisible()
  await expect(page.locator('[data-testid^="platform-home-tile-"]')).toHaveCount(1)

  await page.goto('/platform/integraties')
  await expect(page.getByTestId('platform-integrations-page')).toBeVisible()
  await expect(page.getByText('Er is geen actief huishouden en deze pagina valt nooit terug op huishouden 0.')).toBeVisible()
  await expect(page.getByText('Huishoudgebonden Gmail-koppelingen en externe-productkoppelingen met eigen platformpermissies vallen bewust buiten deze pagina.')).toBeVisible()

  const scanner = page.getByTestId('platform-integration-receipt-scanner')
  await expect(scanner).toContainText('Kassabonscanner')
  await expect(scanner).toContainText('Status: Gereed')
  await expect(scanner).toContainText('Provider: rezzerv-legacy')
  await expect(scanner).toContainText('Contractversie: 1.0')

  const email = page.getByTestId('platform-integration-outbound-email')
  await expect(email).toContainText('Uitgaande e-mail')
  await expect(email).toContainText('Status: Onvolledig geconfigureerd')
  await expect(email).toContainText('Provider: resend')
  await expect(email).toContainText('API-sleutel geconfigureerd: ja')
  await expect(email).toContainText('Afzender geconfigureerd: nee')

  expect(requests).toHaveLength(1)
  expect(requests[0].method).toBe('GET')
  expect(requests[0].postData).toBeNull()
  expect(requests[0].url).not.toContain('household')
  expect(requests[0].headers.authorization).toBeUndefined()
  expect(requests[0].headers['x-admin-key']).toBeUndefined()

  await page.getByRole('button', { name: 'Status vernieuwen', exact: true }).click()
  await expect.poll(() => requests.length).toBe(2)
  expect(requests[1].method).toBe('GET')
  expect(requests[1].postData).toBeNull()
})

test('integrations direct route stays closed without permission and performs no integration read', async ({ page }) => {
  const auditOnlySession = {
    ...noneSession,
    permissions: { 'platform.audit.view': true },
    supported_permissions: ['platform.audit.view'],
  }
  await mockSession(page, auditOnlySession)
  let integrationReads = 0

  await page.route(INTEGRATIONS_ENDPOINT, async (route) => {
    integrationReads += 1
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: '{"items":[]}',
    })
  })

  await page.goto('/platform/integraties')
  await expect(page).toHaveURL(/\/home$/)
  await expect(page.getByTestId('none-session-home')).toBeVisible()
  expect(integrationReads).toBe(0)
})
