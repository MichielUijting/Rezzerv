import { expect, test } from '@playwright/test'

const USERS_PERMISSION = 'platform.users.suspend'
const USERS_ENDPOINT = '**/api/platform/users'
const USER_SUSPEND_ENDPOINT = '**/api/platform/users/target-user/suspend'

const noneSession = {
  user: { id: 'platform-users-actor', email: 'platform-users@example.test' },
  user_id: 'platform-users-actor',
  email: 'platform-users@example.test',
  context_type: 'none',
  active_household_id: null,
  active_household_name: '',
  role: null,
  display_role: null,
  permissions: { [USERS_PERMISSION]: true },
  supported_permissions: [USERS_PERMISSION],
  is_platform_superuser: false,
  is_frontteam: false,
}

const users = [
  {
    user_id: 'platform-users-actor',
    email: 'platform-users@example.test',
    account_status: 'active',
    suspended_at: null,
    active_session_count: 1,
    is_current: true,
  },
  {
    user_id: 'target-user',
    email: 'target-user@example.test',
    account_status: 'active',
    suspended_at: null,
    active_session_count: 2,
    is_current: false,
  },
  {
    user_id: 'already-suspended',
    email: 'already-suspended@example.test',
    account_status: 'suspended',
    suspended_at: '2026-08-24T18:00:00+00:00',
    active_session_count: 0,
    is_current: false,
  },
]

async function mockSession(page, session) {
  await page.route('**/api/session', async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify(session),
    })
  })
}

test('users page suspends only after explicit confirmation and never exposes credential authority', async ({ page }) => {
  await mockSession(page, noneSession)
  const reads = []
  const suspends = []

  await page.route(USERS_ENDPOINT, async (route) => {
    const request = route.request()
    reads.push({
      method: request.method(),
      url: request.url(),
      headers: request.headers(),
      postData: request.postData(),
    })
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        items: users,
        count: users.length,
        household_context_used: false,
        context_type: 'none',
      }),
    })
  })

  await page.route(USER_SUSPEND_ENDPOINT, async (route) => {
    const request = route.request()
    suspends.push({
      method: request.method(),
      url: request.url(),
      headers: request.headers(),
      postData: request.postData(),
    })
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        item: {
          user_id: 'target-user',
          email: 'target-user@example.test',
          account_status: 'suspended',
          suspended_at: '2026-08-24T20:00:00+00:00',
          active_sessions_revoked: 2,
        },
        household_context_used: false,
        context_type: 'none',
      }),
    })
  })

  await page.goto('/home')
  await expect(page.getByTestId('platform-home-tile-users')).toBeVisible()
  await expect(page.locator('[data-testid^="platform-home-tile-"]')).toHaveCount(1)

  await page.goto('/platform/gebruikers')
  await expect(page.getByTestId('platform-users-page')).toBeVisible()
  await expect(page.getByTestId('platform-users-panel')).toBeVisible()
  await expect(page.getByTestId('platform-users-table')).toBeVisible()
  await expect(page.getByTestId('platform-users-table')
    .getByRole('columnheader', { name: 'Gebruiker-ID' })).toHaveCount(0)
  await expect(page.getByTestId('platform-users-page').locator('.rz-card')).toHaveCount(0)

  const current = page.getByTestId('platform-user-platform-users-actor')
  const target = page.getByTestId('platform-user-target-user')
  const suspended = page.getByTestId('platform-user-already-suspended')

  await expect(current).toContainText('Huidig beheeraccount')
  await expect(current.getByRole('checkbox', { name: 'Selecteer platform-users@example.test' })).toBeDisabled()
  await expect(target.getByRole('cell', { name: '2', exact: true })).toBeVisible()
  await expect(suspended.getByRole('cell', { name: 'Geschorst', exact: true })).toBeVisible()
  await expect(page.getByRole('button', { name: 'Schorsen', exact: true })).toBeDisabled()

  expect(reads).toHaveLength(1)
  expect(reads[0].method).toBe('GET')
  expect(reads[0].postData).toBeNull()
  expect(reads[0].url).not.toContain('household')
  expect(reads[0].headers.authorization).toBeUndefined()
  expect(reads[0].headers['x-admin-key']).toBeUndefined()
  expect(suspends).toHaveLength(0)

  await target.getByRole('checkbox', { name: 'Selecteer target-user@example.test' }).check()
  await page.getByRole('button', { name: 'Schorsen', exact: true }).click()
  await expect(page.getByTestId('platform-user-suspend-confirmation')).toBeVisible()
  await expect(page.getByTestId('platform-user-suspend-confirmation')).toHaveAttribute('aria-modal', 'true')
  await expect(page.getByTestId('platform-user-suspend-confirmation-overlay')).toBeVisible()
  await expect(page.getByTestId('platform-users-page').getByTestId('platform-user-suspend-confirmation')).toHaveCount(0)
  expect(suspends).toHaveLength(0)

  await page.getByRole('button', { name: 'Annuleren', exact: true }).click()
  await expect(page.getByTestId('platform-user-suspend-confirmation')).toHaveCount(0)
  expect(suspends).toHaveLength(0)

  await page.getByRole('button', { name: 'Schorsen', exact: true }).click()
  await page.getByRole('button', { name: 'Definitief schorsen', exact: true }).click()
  await expect.poll(() => suspends.length).toBe(1)

  expect(suspends[0].method).toBe('POST')
  expect(suspends[0].postData).toBeNull()
  expect(suspends[0].url).toContain('/api/platform/users/target-user/suspend')
  expect(suspends[0].url).not.toContain('household')
  expect(suspends[0].headers.authorization).toBeUndefined()
  expect(suspends[0].headers['x-admin-key']).toBeUndefined()

  await expect(target.getByRole('cell', { name: 'Geschorst', exact: true })).toBeVisible()
  await expect(target.getByRole('cell', { name: '0', exact: true })).toBeVisible()
  await expect(page.getByRole('button', { name: 'Schorsen', exact: true })).toBeDisabled()
  await expect(page.getByTestId('app-feedback-success')).toContainText('2 actieve sessie(s) ingetrokken')
})

test('users direct route stays closed without permission and performs no user-management request', async ({ page }) => {
  const auditOnlySession = {
    ...noneSession,
    permissions: { 'platform.audit.view': true },
    supported_permissions: ['platform.audit.view'],
  }
  await mockSession(page, auditOnlySession)
  let reads = 0
  let suspends = 0

  await page.route(USERS_ENDPOINT, async (route) => {
    reads += 1
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: '{"items":[]}',
    })
  })
  await page.route('**/api/platform/users/*/suspend', async (route) => {
    suspends += 1
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: '{}',
    })
  })

  await page.goto('/platform/gebruikers')
  await expect(page).toHaveURL(/\/home$/)
  await expect(page.getByTestId('none-session-home')).toBeVisible()
  expect(reads).toBe(0)
  expect(suspends).toBe(0)
})

test('pagination supports eleven users across two pages', async ({ page }) => {
  await mockSession(page, noneSession)
  const manyUsers = Array.from({ length: 11 }, (_, i) => ({ user_id: 'page-user-' + i, email: 'user' + i + '@example.test', account_status: 'active', active_session_count: 0 }))
  await page.route(USERS_ENDPOINT, route => route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({ items: manyUsers }) }))
  await page.goto('/platform/gebruikers')
  const pagination = page.getByRole('navigation', { name: 'Paginering' })
  const pageIndicator = pagination.locator('[aria-current="page"]')
  await expect(pageIndicator).toHaveAttribute('aria-label', 'Pagina 1 van 2')
  await expect(page.locator('[data-testid^="platform-user-page-user-"]')).toHaveCount(8)
  await pagination.getByRole('button', { name: '+', exact: true }).click()
  await expect(pageIndicator).toHaveAttribute('aria-label', 'Pagina 2 van 2')
  await expect(page.locator('[data-testid^="platform-user-page-user-"]')).toHaveCount(3)
})

test('a suspended user can be reactivated only after confirmation without restoring sessions', async ({ page }) => {
  await mockSession(page, noneSession)
  await page.route(USERS_ENDPOINT, route => route.fulfill({
    status: 200, contentType: 'application/json',
    body: JSON.stringify({ items: users, can_delete: false }),
  }))
  const reactivations = []
  await page.route('**/api/platform/users/already-suspended/unsuspend', async route => {
    reactivations.push({ method: route.request().method(), body: route.request().postData() })
    await route.fulfill({
      status: 200, contentType: 'application/json',
      body: JSON.stringify({ item: { account_status: 'active', suspended_at: null, active_sessions_restored: 0 } }),
    })
  })

  await page.goto('/platform/gebruikers')
  const user = page.getByTestId('platform-user-already-suspended')
  await user.getByRole('checkbox', { name: 'Selecteer already-suspended@example.test' }).check()
  await page.getByRole('button', { name: 'Schorsing annuleren', exact: true }).click()
  await expect(page.getByTestId('platform-user-unsuspend-confirmation')).toBeVisible()
  await expect(page.getByTestId('platform-user-unsuspend-confirmation')).toHaveAttribute('aria-modal', 'true')
  await expect(page.getByTestId('platform-user-unsuspend-confirmation-overlay')).toBeVisible()
  await expect(page.getByTestId('platform-users-page').getByTestId('platform-user-unsuspend-confirmation')).toHaveCount(0)
  expect(reactivations).toHaveLength(0)
  await page.getByRole('button', { name: 'Annuleren', exact: true }).click()
  expect(reactivations).toHaveLength(0)
  await page.getByRole('button', { name: 'Schorsing annuleren', exact: true }).click()
  await page.getByRole('button', { name: 'Schorsing annuleren bevestigen' }).click()
  await expect.poll(() => reactivations.length).toBe(1)
  expect(reactivations[0]).toEqual({ method: 'POST', body: null })
  await expect(user.getByRole('cell', { name: 'Actief', exact: true })).toBeVisible()
  await expect(user.getByRole('cell', { name: '0', exact: true })).toBeVisible()
  await expect(page.getByTestId('app-feedback-success')).toContainText('Eerdere sessies blijven ingetrokken')
})

test('platformbeheerder deletion requires preview and typed exact email and preserves shared household', async ({ page }) => {
  await mockSession(page, {
    ...noneSession,
    permissions: { [USERS_PERMISSION]: true, 'platform.users.delete': true },
    supported_permissions: [USERS_PERMISSION, 'platform.users.delete'],
  })
  await page.route(USERS_ENDPOINT, route => route.fulfill({
    status: 200, contentType: 'application/json',
    body: JSON.stringify({ items: users, can_delete: true }),
  }))
  let previews = 0
  const deletes = []
  await page.route('**/api/platform/users/target-user/deletion-preview', async route => {
    previews += 1
    expect(route.request().method()).toBe('GET')
    await route.fulfill({
      status: 200, contentType: 'application/json',
      body: JSON.stringify({
        user_id: 'target-user', households_to_keep: 1, households_to_delete: 0,
      }),
    })
  })
  await page.route('**/api/platform/users/target-user', async route => {
    deletes.push({ method: route.request().method(), body: route.request().postDataJSON() })
    await route.fulfill({
      status: 200, contentType: 'application/json',
      body: JSON.stringify({ deleted: true, households_preserved: 1, households_deleted: 0 }),
    })
  })
  await page.goto('/platform/gebruikers')
  const actor = page.getByTestId('platform-user-platform-users-actor')
  const target = page.getByTestId('platform-user-target-user')
  await expect(actor.getByRole('checkbox', { name: 'Selecteer platform-users@example.test' })).toBeDisabled()
  await expect(page.getByRole('button', { name: 'Gebruiker verwijderen' })).toBeDisabled()
  await target.getByRole('checkbox', { name: 'Selecteer target-user@example.test' }).check()
  await page.getByRole('button', { name: 'Gebruiker verwijderen' }).click()
  await expect(page.getByTestId('platform-user-delete-confirmation')).toContainText('1 gedeelde huishouden(s)')
  await expect(page.getByTestId('platform-user-delete-confirmation')).toHaveAttribute('aria-modal', 'true')
  await expect(page.getByTestId('platform-user-delete-confirmation-overlay')).toBeVisible()
  await expect(page.getByTestId('platform-users-page').getByTestId('platform-user-delete-confirmation')).toHaveCount(0)
  expect(previews).toBe(1)
  expect(deletes).toHaveLength(0)
  const confirm = page.getByTestId('platform-user-delete-confirmation-field-confirmation')
  await confirm.fill('VERWIJDER onjuist@example.test')
  await expect(page.getByRole('button', { name: 'Gebruiker definitief verwijderen' })).toBeDisabled()
  expect(deletes).toHaveLength(0)
  await confirm.fill('VERWIJDER target-user@example.test')
  await page.getByRole('button', { name: 'Gebruiker definitief verwijderen' }).click()
  await expect.poll(() => deletes.length).toBe(1)
  expect(deletes[0]).toEqual({
    method: 'DELETE',
    body: { confirmation: 'VERWIJDER target-user@example.test' },
  })
  await expect(page.getByTestId('platform-user-target-user')).toHaveCount(0)
  await expect(page.getByTestId('app-feedback-success')).toContainText('definitief verwijderd')
})

test('failed suspend remains in standard overlay with an actionable error and no state change', async ({ page }) => {
  await mockSession(page, noneSession)
  await page.route(USERS_ENDPOINT, route => route.fulfill({
    status: 200, contentType: 'application/json', body: JSON.stringify({ items: users }),
  }))
  let attempts = 0
  await page.route(USER_SUSPEND_ENDPOINT, route => {
    attempts += 1
    return route.fulfill({
      status: 409, contentType: 'application/json',
      body: JSON.stringify({ detail: 'Schorsing is momenteel niet toegestaan.' }),
    })
  })
  await page.goto('/platform/gebruikers')
  const target = page.getByTestId('platform-user-target-user')
  await target.getByRole('checkbox', { name: 'Selecteer target-user@example.test' }).check()
  await page.getByRole('button', { name: 'Schorsen', exact: true }).click()
  await page.getByRole('button', { name: 'Definitief schorsen' }).click()
  await expect(page.getByTestId('platform-user-suspend-confirmation-action-error'))
    .toContainText('Schorsing is momenteel niet toegestaan.')
  expect(attempts).toBe(1)
  await expect(target.getByRole('cell', { name: 'Actief', exact: true })).toBeVisible()
  await expect(page.getByTestId('platform-user-suspend-confirmation')).toBeVisible()
  await page.getByTestId('platform-user-suspend-confirmation-secondary-button').click()
  await expect(page.getByTestId('platform-user-suspend-confirmation')).toHaveCount(0)
})

test('rejected deletion preview shows central error overlay and never deletes an account', async ({ page }) => {
  await mockSession(page, {
    ...noneSession,
    permissions: { [USERS_PERMISSION]: true, 'platform.users.delete': true },
    supported_permissions: [USERS_PERMISSION, 'platform.users.delete'],
  })
  await page.route(USERS_ENDPOINT, route => route.fulfill({
    status: 200, contentType: 'application/json',
    body: JSON.stringify({ items: users, can_delete: true }),
  }))
  let deletionCalls = 0
  await page.route('**/api/platform/users/target-user/deletion-preview', route => route.fulfill({
    status: 403, contentType: 'application/json',
    body: JSON.stringify({ detail: 'Dit platformaccount is beschermd.' }),
  }))
  await page.route('**/api/platform/users/target-user', route => {
    deletionCalls += 1
    return route.fulfill({ status: 200, body: '{}' })
  })
  await page.goto('/platform/gebruikers')
  await page.getByTestId('platform-user-target-user')
    .getByRole('checkbox', { name: 'Selecteer target-user@example.test' }).check()
  await page.getByRole('button', { name: 'Gebruiker verwijderen' }).click()
  await expect(page.getByTestId('app-feedback-error')).toContainText('Dit platformaccount is beschermd.')
  await expect(page.getByTestId('app-feedback-error')).toHaveAttribute('aria-modal', 'true')
  expect(deletionCalls).toBe(0)
  await expect(page.getByTestId('platform-user-target-user').getByRole('cell', { name: 'Actief', exact: true })).toBeVisible()
})

test('table has filtered and current-page selections and paginates eight rows', async ({ page }) => {
  await mockSession(page, noneSession)
  const rows = [users[0], ...Array.from({ length: 9 }, (_, i) => ({
    user_id: 'user-' + i, email: 'user-' + i + '@example.test',
    account_status: 'active', suspended_at: null, active_session_count: 0,
    is_current: false,
  }))]
  await page.route(USERS_ENDPOINT, route => route.fulfill({
    status: 200, contentType: 'application/json', body: JSON.stringify({ items: rows, can_delete: true }),
  }))
  await page.goto('/platform/gebruikers')
  await expect(page.getByTestId('platform-users-table')).toBeVisible()
  await expect(page.getByTestId('platform-users-table').getByRole('row')).toHaveCount(10) // header + filters + 8
  await expect(page.getByRole('button', { name: 'Schorsen', exact: true })).toBeDisabled()
  await expect(page.getByRole('button', { name: 'Gebruiker verwijderen', exact: true })).toBeDisabled()

  await page.getByRole('checkbox', { name: 'Alle rijen op deze pagina' }).check()
  await expect(page.getByTestId('platform-users-selection-count')).toContainText('Geselecteerd: 7')
  await expect(page.getByRole('button', { name: 'Gebruiker verwijderen', exact: true })).toBeDisabled()
  const paging = page.getByRole('navigation', { name: 'Paginering' })
  await paging.getByRole('button', { name: '+', exact: true }).click()
  await expect(page.getByTestId('platform-users-selection-count')).toContainText('Geselecteerd: 7')
  await page.getByRole('checkbox', { name: 'Alle rijen in de tabel' }).check()
  await expect(page.getByTestId('platform-users-selection-count')).toContainText('Geselecteerd: 9')
  await expect(page.getByRole('checkbox', { name: 'Alle rijen op deze pagina' })).toBeChecked()
  await paging.getByRole('button', { name: '1', exact: true }).click()
  await expect(page.getByRole('checkbox', { name: 'Selecteer platform-users@example.test' })).toBeDisabled()
  await expect(page.getByRole('checkbox', { name: 'Alle rijen op deze pagina' })).toBeChecked()
  await page.getByRole('checkbox', { name: 'Alle rijen in de tabel' }).uncheck()
  await expect(page.getByTestId('platform-users-selection-count')).toContainText('Geselecteerd: 0')
})

test('bulk selection acts only on applicable statuses and retains failures without deleting other accounts', async ({ page }) => {
  await mockSession(page, noneSession)
  const second = { ...users[1], user_id: 'target-two', email: 'target-two@example.test', active_session_count: 1 }
  await page.route(USERS_ENDPOINT, route => route.fulfill({
    status: 200, contentType: 'application/json',
    body: JSON.stringify({ items: [...users, second], can_delete: true }),
  }))
  const requests = []
  await page.route('**/api/platform/users/*/suspend', route => {
    const request = route.request()
    requests.push({ url: request.url(), method: request.method() })
    const failed = request.url().includes('/target-two/')
    return route.fulfill({
      status: failed ? 409 : 200, contentType: 'application/json',
      body: JSON.stringify(failed
        ? { detail: 'Dit account mag niet worden geschorst.' }
        : { item: { suspended_at: '2026-08-24T20:00:00+00:00', active_sessions_revoked: 2 } }),
    })
  })
  await page.goto('/platform/gebruikers')
  await page.getByRole('checkbox', { name: 'Selecteer target-user@example.test' }).check()
  await page.getByRole('checkbox', { name: 'Selecteer target-two@example.test' }).check()
  await expect(page.getByRole('button', { name: 'Gebruiker verwijderen' })).toBeDisabled()
  await page.getByRole('button', { name: 'Schorsen', exact: true }).click()
  await expect(page.getByTestId('platform-user-suspend-confirmation')).toContainText('2 geselecteerde actieve gebruikers')
  expect(requests).toHaveLength(0)
  await page.getByRole('button', { name: 'Definitief schorsen' }).click()
  await expect.poll(() => requests.length).toBe(2)
  await expect(page.getByTestId('app-feedback-error')).toContainText('1 geschorst; 1 niet verwerkt')
  await expect(page.getByTestId('platform-user-target-user').getByRole('cell', { name: 'Geschorst', exact: true })).toBeVisible()
  await expect(page.getByTestId('platform-user-target-two').getByRole('cell', { name: 'Actief', exact: true })).toBeVisible()
  await expect(page.getByRole('checkbox', { name: 'Selecteer target-user@example.test' })).not.toBeChecked()
  await expect(page.getByRole('checkbox', { name: 'Selecteer target-two@example.test' })).toBeChecked()
  await expect(page.getByTestId('platform-users-selection-count')).toContainText('Geselecteerd: 1')
})

test('exporter downloads only selected users without invoking any account mutation', async ({ page }) => {
  await mockSession(page, noneSession)
  await page.route(USERS_ENDPOINT, route => route.fulfill({
    status: 200, contentType: 'application/json', body: JSON.stringify({ items: users }),
  }))
  let mutations = 0
  await page.route('**/api/platform/users/*/suspend', route => {
    mutations += 1
    return route.fulfill({ status: 500, body: '{}' })
  })
  await page.goto('/platform/gebruikers')
  await expect(page.getByRole('button', { name: 'Exporteren' })).toBeDisabled()
  await page.getByRole('checkbox', { name: 'Selecteer target-user@example.test' }).check()
  const downloading = page.waitForEvent('download')
  await page.getByRole('button', { name: 'Exporteren' }).click()
  const download = await downloading
  expect(download.suggestedFilename()).toBe('Inhuis_Platformgebruikers.csv')
  expect(mutations).toBe(0)
  await expect(page.getByTestId('app-feedback-success')).toContainText('1 geselecteerde gebruiker(s) geëxporteerd')
})

test('bulk cancellation of suspensions uses only suspended accounts and preserves other selections', async ({ page }) => {
  await mockSession(page, noneSession)
  const secondSuspended = {
    ...users[2], user_id: 'suspended-two', email: 'suspended-two@example.test',
  }
  await page.route(USERS_ENDPOINT, route => route.fulfill({
    status: 200, contentType: 'application/json',
    body: JSON.stringify({ items: [...users, secondSuspended], can_delete: true }),
  }))
  const requests = []
  await page.route('**/api/platform/users/*/unsuspend', route => {
    requests.push({ url: route.request().url(), method: route.request().method() })
    return route.fulfill({
      status: 200, contentType: 'application/json',
      body: JSON.stringify({ item: { account_status: 'active', suspended_at: null, active_sessions_restored: 0 } }),
    })
  })
  await page.goto('/platform/gebruikers')
  await page.getByRole('checkbox', { name: 'Selecteer target-user@example.test' }).check()
  await page.getByRole('checkbox', { name: 'Selecteer already-suspended@example.test' }).check()
  await page.getByRole('checkbox', { name: 'Selecteer suspended-two@example.test' }).check()
  await expect(page.getByRole('button', { name: 'Gebruiker verwijderen' })).toBeDisabled()
  await page.getByRole('button', { name: 'Schorsing annuleren', exact: true }).click()
  await expect(page.getByTestId('platform-user-unsuspend-confirmation')).toContainText('2 geselecteerde geschorste gebruikers')
  expect(requests).toHaveLength(0)
  await page.getByRole('button', { name: 'Schorsing annuleren bevestigen' }).click()
  await expect.poll(() => requests.length).toBe(2)
  expect(requests.every((request) => request.method === 'POST')).toBe(true)
  expect(requests.some((request) => request.url.includes('/target-user/'))).toBe(false)
  await expect(page.getByTestId('platform-user-already-suspended').getByRole('cell', { name: 'Actief', exact: true })).toBeVisible()
  await expect(page.getByTestId('platform-user-suspended-two').getByRole('cell', { name: 'Actief', exact: true })).toBeVisible()
  await expect(page.getByTestId('platform-user-target-user').getByRole('cell', { name: 'Actief', exact: true })).toBeVisible()
  await expect(page.getByTestId('platform-users-selection-count')).toContainText('Geselecteerd: 1')
})

test('users panel contains header selector, table, paging and actions within the same width', async ({ page }) => {
  await page.setViewportSize({ width: 1440, height: 900 })
  await mockSession(page, noneSession)
  const manyUsers = [users[0], ...Array.from({ length: 10 }, (_, i) => ({
    user_id: 'alignment-user-' + i, email: 'alignment-' + i + '@example.test',
    account_status: 'active', suspended_at: null, active_session_count: 0, is_current: false,
  }))]
  await page.route(USERS_ENDPOINT, route => route.fulfill({
    status: 200, contentType: 'application/json',
    body: JSON.stringify({ items: manyUsers, can_delete: true }),
  }))
  await page.goto('/platform/gebruikers')
  const panel = page.getByTestId('platform-users-panel')
  const table = panel.getByTestId('platform-users-table')
  const selector = panel.getByTestId('platform-users-select-all')
  const actions = panel.locator('.rz-data-table-actions')
  const paging = panel.getByRole('navigation', { name: 'Paginering' })
  await expect(table).toBeVisible()
  await expect(panel.getByRole('columnheader', { name: 'Gebruiker-ID' })).toHaveCount(0)
  await expect(page.getByText(/platform\.users\.suspend/)).toHaveCount(0)
  await expect(panel.getByRole('button', { name: 'Exporteren' })).toBeVisible()
  await expect(panel.getByRole('button', { name: 'Schorsen', exact: true })).toBeVisible()
  await expect(panel.getByRole('button', { name: 'Schorsing annuleren' })).toBeVisible()
  await expect(panel.getByRole('button', { name: 'Gebruiker verwijderen' })).toBeVisible()
  const panelBox = await panel.boundingBox()
  const pageBox = await page.getByTestId('platform-users-page').boundingBox()
  const tableBox = await table.boundingBox()
  const selectorBox = await selector.boundingBox()
  const actionsBox = await actions.boundingBox()
  const pagingBox = await paging.boundingBox()
  expect(panelBox).not.toBeNull()
  expect(pageBox).not.toBeNull()
  expect(Math.abs((panelBox.x + panelBox.width / 2) - (pageBox.x + pageBox.width / 2))).toBeLessThanOrEqual(2)
  expect(tableBox).not.toBeNull()
  expect(selectorBox).not.toBeNull()
  expect(actionsBox).not.toBeNull()
  expect(pagingBox).not.toBeNull()
  const right = panelBox.x + panelBox.width
  expect(tableBox.x).toBeGreaterThanOrEqual(panelBox.x - 1)
  expect(tableBox.x + tableBox.width).toBeLessThanOrEqual(right + 2)
  expect(selectorBox.x + selectorBox.width).toBeLessThanOrEqual(right + 2)
  expect(actionsBox.x + actionsBox.width).toBeLessThanOrEqual(right + 2)
  expect(actionsBox.y).toBeGreaterThan(pagingBox.y)
  for (const button of await actions.getByRole('button').all()) {
    const box = await button.boundingBox()
    expect(box.x + box.width).toBeLessThanOrEqual(right + 2)
  }
})

test('users panel bulk buttons wrap within panel on narrow screens', async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 820 })
  await mockSession(page, noneSession)
  await page.route(USERS_ENDPOINT, route => route.fulfill({
    status: 200, contentType: 'application/json',
    body: JSON.stringify({ items: users, can_delete: true }),
  }))
  await page.goto('/platform/gebruikers')
  const panel = page.getByTestId('platform-users-panel')
  await expect(panel).toBeVisible()
  const panelBox = await panel.boundingBox()
  const pageBox = await page.getByTestId('platform-users-page').boundingBox()
  const selectorBox = await panel.getByTestId('platform-users-select-all').boundingBox()
  expect(panelBox).not.toBeNull()
  expect(pageBox).not.toBeNull()
  expect(Math.abs((panelBox.x + panelBox.width / 2) - (pageBox.x + pageBox.width / 2))).toBeLessThanOrEqual(2)
  expect(selectorBox.x + selectorBox.width).toBeLessThanOrEqual(panelBox.x + panelBox.width + 2)
  // Inhuis contract: Exporteren is desktop-only (theme.css), so it must not
  // contribute to mobile geometry assertions or be made visible by this page.
  await expect(panel.getByRole('button', { name: 'Exporteren', includeHidden: true })).toBeHidden()
  for (const label of ['Schorsen', 'Schorsing annuleren', 'Gebruiker verwijderen']) {
    const button = panel.getByRole('button', { name: label, exact: true })
    await expect(button).toBeVisible()
    const box = await button.boundingBox()
    expect(box).not.toBeNull()
    expect(box.x + box.width).toBeLessThanOrEqual(panelBox.x + panelBox.width + 2)
  }
})
