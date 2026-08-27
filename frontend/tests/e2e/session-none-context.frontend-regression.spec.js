import { expect, test } from '@playwright/test'

const platformPermissions = {
  'platform.audit.view': true,
  'platform.background_jobs.manage': true,
  'platform.diagnostics.view': true,
  'platform.feature_flags.manage': true,
  'platform.integrations.manage': true,
  'platform.logs.view': true,
  'platform.permissions.manage': true,
  'platform.recovery.manage': true,
  'platform.sessions.revoke': true,
  'platform.technical_configuration.manage': true,
  'platform.test_fixtures.manage': true,
  'platform.users.suspend': true,
}

const platformLabels = [
  'Diagnostiek',
  'Logs',
  'Audit',
  'Integraties',
  'Achtergrondtaken',
  'Herstel',
  'Technische configuratie',
  'Testfixtures',
  'Featureflags',
  'Sessies',
  'Gebruikers',
  'Platformautorisaties',
]

const noneSession = {
  user: { id: 'platform-user', email: 'platform@example.test' },
  user_id: 'platform-user',
  email: 'platform@example.test',
  context_type: 'none',
  active_household_id: null,
  active_household_name: '',
  role: null,
  display_role: null,
  permissions: platformPermissions,
  supported_permissions: Object.keys(platformPermissions).sort(),
  is_platform_superuser: false,
  is_frontteam: false,
}

async function mockNoneSession(page, session = noneSession) {
  await page.route('**/api/session', async (route) => {
    await route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(session) })
  })
}

test('none session gets a permission-driven platform landing and stays household-free', async ({ page }) => {
  let loginCalled = false
  let logoutCalled = false
  const diagnosticRequests = []

  await page.route('**/api/auth/login', async (route) => {
    loginCalled = true
    await route.fulfill({ status: 200, contentType: 'application/json', body: '{}' })
  })
  await mockNoneSession(page)
  await page.route('**/api/auth/logout', async (route) => {
    logoutCalled = true
    await route.fulfill({ status: 200, contentType: 'application/json', body: '{}' })
  })
  await page.route('**/api/admin/kassa-regression/status', async (route) => {
    diagnosticRequests.push(route.request().method())
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        status: 'idle',
        message: 'Nog niet gestart',
        progress_current: 0,
        progress_total: 18,
        finished_at: null,
      }),
    })
  })
  await page.route('**/api/admin/kassa-smoke/status', async (route) => {
    diagnosticRequests.push(route.request().method())
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        status: 'passed',
        message: 'Kassa smoke-check afgerond',
        progress_current: 6,
        progress_total: 6,
        finished_at: '2026-08-24T11:30:00+00:00',
      }),
    })
  })

  await page.goto('/login')
  await page.getByTestId('login-submit').click()

  await expect(page).toHaveURL(/\/home$/)
  expect(loginCalled).toBe(true)
  await expect(page.getByTestId('none-session-home')).toBeVisible()
  await expect(page.getByText('Platformbeheerder', { exact: true }).first()).toBeVisible()
  await expect(page.getByText('Er is geen huishoudcontext actief.')).toBeVisible()
  await expect(page.getByText('platform@example.test')).toBeVisible()
  await expect(page.getByText('Huishouden:', { exact: false })).toHaveCount(0)
  await expect(page.getByTestId('platform-home-navigation')).toBeVisible()
  await expect(page.locator('[data-testid^="platform-home-tile-"]')).toHaveCount(12)

  for (const label of platformLabels) {
    await expect(page.getByText(label, { exact: true })).toBeVisible()
  }

  for (const tile of ['Voorraad', 'Winkelen', 'Instellingen', 'Admin', 'Superuser']) {
    await expect(page.getByText(tile, { exact: true })).toHaveCount(0)
  }

  await page.getByTestId('platform-home-tile-diagnostics').click()
  await expect(page).toHaveURL(/\/platform\/diagnostiek$/)
  await expect(page.getByTestId('platform-diagnostics-page')).toBeVisible()
  await expect(page.getByTestId('platform-diagnostic-regression')).toContainText('Status: idle')
  await expect(page.getByTestId('platform-diagnostic-regression')).toContainText('Voortgang: 0 / 18')
  await expect(page.getByTestId('platform-diagnostic-smoke')).toContainText('Status: passed')
  await expect(page.getByTestId('platform-diagnostic-smoke')).toContainText('Voortgang: 6 / 6')
  expect(diagnosticRequests).toEqual(['GET', 'GET'])
  await expect(page.getByText('Het starten van controles hoort bij Achtergrondtaken en is hier niet beschikbaar.')).toBeVisible()
  await page.goBack()
  await expect(page).toHaveURL(/\/home$/)

  await page.goto('/voorraad')
  await expect(page).toHaveURL(/\/home$/)
  await expect(page.getByTestId('none-session-home')).toBeVisible()

  await page.goto('/superuser')
  await expect(page).toHaveURL(/\/home$/)
  await expect(page.getByTestId('none-session-home')).toBeVisible()

  await page.getByTestId('none-session-logout').click()
  await expect(page).toHaveURL(/\/login$/)
  expect(logoutCalled).toBe(true)
})

test('none context cannot cross into a household route even with a household permission', async ({ page }) => {
  const spoofedSession = {
    ...noneSession,
    permissions: { ...platformPermissions, 'shopping_list.view': true },
    supported_permissions: [...Object.keys(platformPermissions), 'shopping_list.view'].sort(),
  }
  await mockNoneSession(page, spoofedSession)

  await page.goto('/winkelen')
  await expect(page).toHaveURL(/\/home$/)
  await expect(page.getByTestId('none-session-home')).toBeVisible()
})

test('platform navigation and direct routes both fail closed without the concrete permission', async ({ page }) => {
  const auditOnlySession = {
    ...noneSession,
    permissions: { 'platform.audit.view': true },
    supported_permissions: ['platform.audit.view'],
  }
  const auditRequests = []
  await mockNoneSession(page, auditOnlySession)
  await page.route('**/api/platform/audit*', async (route) => {
    auditRequests.push(route.request().method())
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        count: 2,
        limit: 50,
        items: [
          {
            id: 'audit-platform',
            actor_user_id: 'actor-platform',
            actor_type: 'platform',
            household_id: null,
            action: 'permission_changed',
            object_type: 'platform_role',
            object_id: 'platform.platform_admin',
            created_at: '2026-08-24T12:00:00+00:00',
          },
          {
            id: 'audit-household',
            actor_user_id: 'actor-household',
            actor_type: 'household',
            household_id: 'household-1',
            action: 'role_changed',
            object_type: 'membership',
            object_id: 'member-1',
            created_at: '2026-08-23T12:00:00+00:00',
          },
        ],
      }),
    })
  })

  await page.goto('/home')
  await expect(page.getByTestId('platform-home-tile-audit')).toBeVisible()
  await expect(page.getByTestId('platform-home-tile-logs')).toHaveCount(0)
  await expect(page.locator('[data-testid^="platform-home-tile-"]')).toHaveCount(1)

  await page.goto('/platform/audit')
  await expect(page.getByTestId('platform-audit-page')).toBeVisible()
  await expect(page.getByTestId('platform-audit-item-audit-platform')).toContainText('permission_changed')
  await expect(page.getByTestId('platform-audit-item-audit-platform')).toContainText('Context: Platformbreed')
  await expect(page.getByTestId('platform-audit-item-audit-household')).toContainText('Context: Huishouden household-1')
  await expect(page.getByText('Gevoelige auditpayloads, redenen en ticketreferenties worden hier niet getoond.')).toBeVisible()
  expect(auditRequests).toEqual(['GET'])

  await page.goto('/platform/logs')
  await expect(page).toHaveURL(/\/home$/)
  await expect(page.getByTestId('none-session-home')).toBeVisible()
})

test('diagnostics direct route stays closed without platform.diagnostics.view and performs no status reads', async ({ page }) => {
  const auditOnlySession = {
    ...noneSession,
    permissions: { 'platform.audit.view': true },
    supported_permissions: ['platform.audit.view'],
  }
  let diagnosticReads = 0
  await mockNoneSession(page, auditOnlySession)
  await page.route('**/api/admin/kassa-*/status', async (route) => {
    diagnosticReads += 1
    await route.fulfill({ status: 200, contentType: 'application/json', body: '{}' })
  })

  await page.goto('/platform/diagnostiek')
  await expect(page).toHaveURL(/\/home$/)
  await expect(page.getByTestId('none-session-home')).toBeVisible()
  expect(diagnosticReads).toBe(0)
})

test('audit direct route stays closed without platform.audit.view and performs no audit read', async ({ page }) => {
  const logsOnlySession = {
    ...noneSession,
    permissions: { 'platform.logs.view': true },
    supported_permissions: ['platform.logs.view'],
  }
  let auditReads = 0
  await mockNoneSession(page, logsOnlySession)
  await page.route('**/api/platform/audit*', async (route) => {
    auditReads += 1
    await route.fulfill({ status: 200, contentType: 'application/json', body: '{"items":[]}' })
  })

  await page.goto('/platform/audit')
  await expect(page).toHaveURL(/\/home$/)
  await expect(page.getByTestId('none-session-home')).toBeVisible()
  expect(auditReads).toBe(0)
})

test('technical configuration requires explicit confirmation and uses only canonical platform actions', async ({ page }) => {
  const technicalOnlySession = {
    ...noneSession,
    permissions: { 'platform.technical_configuration.manage': true },
    supported_permissions: ['platform.technical_configuration.manage'],
  }
  const technicalRequests = []
  let bundledRequests = 0
  await mockNoneSession(page, technicalOnlySession)

  await page.route('**/api/admin/inventory/groups/ensure-schema', async (route) => {
    technicalRequests.push(`${route.request().method()} schema`)
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        ok: true,
        schema: 'product_inventory_groups',
        seed: 'm2c2i30a_seed',
        mutates_inventory: false,
      }),
    })
  })
  await page.route('**/api/admin/product-groups/import-gpc-nl', async (route) => {
    technicalRequests.push(`${route.request().method()} gpc-nl`)
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        ok: true,
        source: 'gs1_gpc_api',
        language_code: 'nl',
        source_version: '2026-Q3',
        total_bricks: 1200,
        total_families: 80,
        total_classes: 240,
        product_groups_created: 25,
        product_groups_updated: 1175,
        mutates_inventory: false,
      }),
    })
  })
  await page.route('**/api/admin/product-groups/import-gpc-en-bundled', async (route) => {
    bundledRequests += 1
    await route.fulfill({ status: 500, contentType: 'application/json', body: '{}' })
  })

  await page.goto('/home')
  await expect(page.getByTestId('platform-home-tile-technical-configuration')).toBeVisible()
  await expect(page.locator('[data-testid^="platform-home-tile-"]')).toHaveCount(1)

  await page.goto('/platform/technische-configuratie')
  await expect(page.getByTestId('platform-technical-configuration-page')).toBeVisible()
  await expect(page.getByText('De legacy bundled GPC-import met admin-key is hier bewust niet beschikbaar.')).toBeVisible()
  expect(technicalRequests).toEqual([])
  expect(bundledRequests).toBe(0)

  await page.getByRole('button', { name: 'Voorraadgroepschema initialiseren' }).click()
  await expect(page.getByTestId('platform-technical-confirm-schema')).toBeVisible()
  expect(technicalRequests).toEqual([])
  await page.getByRole('button', { name: 'Schema-initialisatie bevestigen' }).click()
  await expect(page.getByTestId('platform-technical-result-schema')).toContainText('Schema: product_inventory_groups')
  await expect(page.getByTestId('platform-technical-result-schema')).toContainText('Huishoudvoorraad gewijzigd: nee')
  expect(technicalRequests).toEqual(['POST schema'])

  await page.getByRole('button', { name: 'GS1 GPC NL bijwerken' }).click()
  await expect(page.getByTestId('platform-technical-confirm-gpc-nl')).toBeVisible()
  expect(technicalRequests).toEqual(['POST schema'])
  await page.getByRole('button', { name: 'GPC NL-import bevestigen' }).click()
  await expect(page.getByTestId('platform-technical-result-gpc-nl')).toContainText('Bronversie: 2026-Q3')
  await expect(page.getByTestId('platform-technical-result-gpc-nl')).toContainText('GPC bricks: 1200')
  await expect(page.getByTestId('platform-technical-result-gpc-nl')).toContainText('Huishoudvoorraad gewijzigd: nee')
  expect(technicalRequests).toEqual(['POST schema', 'POST gpc-nl'])
  expect(bundledRequests).toBe(0)
})

test('technical configuration direct route stays closed without permission and performs no mutation', async ({ page }) => {
  const auditOnlySession = {
    ...noneSession,
    permissions: { 'platform.audit.view': true },
    supported_permissions: ['platform.audit.view'],
  }
  let technicalMutations = 0
  await mockNoneSession(page, auditOnlySession)
  await page.route('**/api/admin/inventory/groups/ensure-schema', async (route) => {
    technicalMutations += 1
    await route.fulfill({ status: 200, contentType: 'application/json', body: '{}' })
  })
  await page.route('**/api/admin/product-groups/import-gpc-nl', async (route) => {
    technicalMutations += 1
    await route.fulfill({ status: 200, contentType: 'application/json', body: '{}' })
  })

  await page.goto('/platform/technische-configuratie')
  await expect(page).toHaveURL(/\/home$/)
  await expect(page.getByTestId('none-session-home')).toBeVisible()
  expect(technicalMutations).toBe(0)
})
