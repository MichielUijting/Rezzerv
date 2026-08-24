import { test, expect } from '@playwright/test'
import { attachConsoleErrorCollector, expectNoConsoleErrors } from './helpers/rezzervAssertions.js'

async function seedAdminSession(page) {
  const permissions = {
    'household_settings.manage': true,
    'members.manage': true,
    'permissions.view': true,
  }
  await page.route('**/api/session', async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        user: { id: 'settings-authorization-admin', email: 'admin@rezzerv.local' },
        user_id: 'settings-authorization-admin',
        email: 'admin@rezzerv.local',
        active_household_id: '1',
        active_household_name: 'Testhuishouden',
        role: 'admin',
        display_role: 'admin',
        permissions,
        supported_permissions: Object.keys(permissions),
        can_manage_member_permissions: false,
        can_manage_members: true,
        is_viewer: false,
        is_platform_superuser: false,
        is_frontteam: false,
      }),
    })
  })
}

function authorizationPayload(roleKey = 'household.member') {
  return {
    household_id: '1',
    members: [
      { membership_id: 'member-admin', email: 'admin@rezzerv.local', role_key: 'household.admin', role_name: 'Beheerder', permission_overrides: [], is_current_user: true },
      { membership_id: 'member-lid', email: 'lid@rezzerv.local', role_key: roleKey, role_name: 'Lid', permission_overrides: [] },
    ],
    roles: [
      { role_key: 'household.member', name: 'Lid', permission_keys: ['inventory.view', 'inventory.update', 'members.view'] },
      { role_key: 'household.admin', name: 'Beheerder', permission_keys: ['inventory.view', 'inventory.update', 'inventory.correct', 'members.view', 'members.manage'] },
      { role_key: 'household.owner', name: 'Superuser', permission_keys: ['inventory.view', 'inventory.update', 'inventory.correct', 'members.view', 'members.manage'] },
      { role_key: 'household.frontteam', name: 'Frontteamlid', permission_keys: ['inventory.view', 'inventory.update', 'inventory.correct', 'members.view', 'members.manage'] },
    ],
    permissions: [
      { permission_key: 'inventory.view', description: 'inventory.view' },
      { permission_key: 'inventory.update', description: 'inventory.update' },
      { permission_key: 'inventory.correct', description: 'inventory.correct' },
      { permission_key: 'members.view', description: 'members.view' },
      { permission_key: 'members.manage', description: 'members.manage' },
    ],
  }
}

async function mockAuthorizationApi(page, getRoleKey, setRoleKey) {
  await page.route('**/api/households/1/authorization/members', async (route) => {
    const payload = authorizationPayload(getRoleKey())
    await route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({ household_id: '1', total: 2, items: payload.members }) })
  })
  await page.route('**/api/households/1/authorization/roles', async (route) => {
    const payload = authorizationPayload(getRoleKey())
    await route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({ household_id: '1', items: payload.roles }) })
  })
  await page.route('**/api/households/1/authorization/permissions', async (route) => {
    const payload = authorizationPayload(getRoleKey())
    await route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({ household_id: '1', items: payload.permissions }) })
  })
  await page.route('**/api/households/1/authorization/members/member-lid/role', async (route) => {
    const payload = JSON.parse(route.request().postData() || '{}')
    setRoleKey(payload.role_key)
    await route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({ ok: true, role_key: payload.role_key }) })
  })
}

test.describe('Autorisaties frontend-regressie', () => {
  test('Autorisaties toont een Nederlandse rollenmatrix zonder leden of technische sleutels', async ({ page }) => {
    const consoleErrors = attachConsoleErrorCollector(page)
    let roleKey = 'household.member'
    await seedAdminSession(page)
    await mockAuthorizationApi(page, () => roleKey, (value) => { roleKey = value })

    await page.goto('/instellingen/huishouden/autorisaties')
    const authorizationPage = page.getByTestId('authorization-settings-page')
    await expect(authorizationPage).toBeVisible()
    await expect(page.getByRole('heading', { name: 'Autorisaties', exact: true })).toBeVisible()
    await expect(page.getByTestId('authorization-role-matrix')).toBeVisible()
    await expect(page.getByRole('columnheader', { name: 'Lid', exact: true })).toBeVisible()
    await expect(page.getByRole('columnheader', { name: 'Beheerder', exact: true })).toBeVisible()
    await expect(page.getByRole('columnheader', { name: 'Superuser', exact: true })).toBeVisible()
    await expect(page.getByRole('columnheader', { name: 'Frontteamlid', exact: true })).toBeVisible()
    await expect(page.getByRole('rowheader', { name: 'Voorraad bekijken', exact: true })).toBeVisible()
    await expect(page.getByLabel('Voorraad wijzigen voor Lid: toegestaan')).toBeChecked()
    await expect(authorizationPage.getByText('admin@rezzerv.local')).toHaveCount(0)
    await expect(authorizationPage.getByText('inventory.view')).toHaveCount(0)
    await expect(authorizationPage.locator('select')).toHaveCount(0)
    await expectNoConsoleErrors(consoleErrors)
  })

  test('Huishouden beheert leden, rollen en uitnodigingen en gebruikt overlaymeldingen', async ({ page }) => {
    const consoleErrors = attachConsoleErrorCollector(page)
    await seedAdminSession(page)

    let roleKey = 'household.advanced_member'
    let householdName = 'Molenstraat 19 Driel'
    let invitations = []
    const householdPayload = () => ({
      household_name: householdName,
      member_count: 2,
      is_household_admin: true,
      permissions: { 'members.manage': true },
      members: [
        { email: 'admin@rezzerv.local', is_current_user: true, can_remove: false },
        { email: 'lid@rezzerv.local', is_current_user: false, can_remove: true },
      ],
    })

    await mockAuthorizationApi(page, () => roleKey, (value) => { roleKey = value })
    await page.route('**/api/household/members', async (route) => {
      await route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(householdPayload()) })
    })
    await page.route('**/api/household/name', async (route) => {
      const payload = JSON.parse(route.request().postData() || '{}')
      householdName = payload.name
      await route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(householdPayload()) })
    })
    await page.route('**/api/household/invitations**', async (route) => {
      const request = route.request()
      const url = new URL(request.url())
      const method = request.method()
      const path = url.pathname

      if (method === 'GET' && path === '/api/household/invitations') {
        await route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({ household_id: '1', items: invitations, total: invitations.length }) })
        return
      }

      if (method === 'POST' && path === '/api/household/invitations') {
        const payload = JSON.parse(request.postData() || '{}')
        const invitation = {
          id: 'invite-new',
          household_id: '1',
          invitee_email: payload.email,
          role_key: 'household.member',
          status: 'pending',
          expires_at: '2026-08-31T07:00:00+00:00',
          delivery_status: 'disabled',
          delivery_attempt_count: 1,
          last_delivery_error: 'Uitnodigingsmail is uitgeschakeld.',
        }
        invitations = [invitation]
        await route.fulfill({
          status: 201,
          contentType: 'application/json',
          body: JSON.stringify({
            ok: true,
            invitation,
            delivery: { status: 'disabled', message: 'Uitnodigingsmail is uitgeschakeld.', provider_message_id: null },
          }),
        })
        return
      }

      if (method === 'POST' && path === '/api/household/invitations/invite-new/resend') {
        invitations = invitations.map((item) => item.id === 'invite-new'
          ? { ...item, delivery_status: 'disabled', delivery_attempt_count: 2, last_delivery_error: 'Uitnodigingsmail is uitgeschakeld.' }
          : item)
        await route.fulfill({
          status: 503,
          contentType: 'application/json',
          body: JSON.stringify({ detail: { code: 'invitation_delivery_failed', delivery: { status: 'disabled', message: 'Uitnodigingsmail is uitgeschakeld.' } } }),
        })
        return
      }

      if (method === 'POST' && path === '/api/household/invitations/invite-new/revoke') {
        invitations = invitations.map((item) => item.id === 'invite-new' ? { ...item, status: 'revoked' } : item)
        await route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({ ok: true, invitation: invitations[0] }) })
        return
      }

      await route.fulfill({ status: 404, contentType: 'application/json', body: JSON.stringify({ detail: 'Unexpected invitation test route' }) })
    })

    await page.goto('/instellingen/huishouden')
    await expect(page.getByTestId('household-settings-page')).toBeVisible()
    await expect(page.getByText('Rechten voor leden')).toHaveCount(0)
    await expect(page.getByLabel('Rol lid@rezzerv.local')).toHaveValue('household.advanced_member')
    await expect(page.getByLabel('Rol lid@rezzerv.local').locator('option')).toHaveText([
      'Geavanceerd lid (bestaande rol)',
      'Lid',
      'Beheerder',
    ])

    await page.getByLabel('Rol lid@rezzerv.local').selectOption('household.member')
    const roleFeedback = page.getByTestId('app-feedback-success')
    await expect(roleFeedback).toContainText('De rol van lid@rezzerv.local is gewijzigd naar Lid.')
    await roleFeedback.getByRole('button', { name: 'OK' }).click()
    await expect(page.getByLabel('Rol lid@rezzerv.local')).toHaveValue('household.member')

    await page.getByTestId('household-name-input').fill('Molenstraat 19 Driel bijgewerkt')
    await page.getByTestId('household-name-save').click()
    const nameFeedback = page.getByTestId('app-feedback-success')
    await expect(nameFeedback).toContainText('Huishoudnaam opgeslagen.')
    await nameFeedback.getByRole('button', { name: 'OK' }).click()
    await expect(page.getByTestId('household-name-input')).toHaveValue('Molenstraat 19 Driel bijgewerkt')

    await expect(page.getByRole('heading', { name: 'Huishoudlid uitnodigen', exact: true })).toBeVisible()
    await expect(page.getByTestId('household-settings-page').getByLabel('Wachtwoord')).toHaveCount(0)
    await page.getByTestId('household-invitation-email-input').fill('nieuw-lid@example.com')
    await page.getByTestId('household-invitation-submit').click()
    const invitationFeedback = page.getByTestId('app-feedback-success')
    await expect(invitationFeedback).toContainText('Uitnodiging aangemaakt. E-mailverzending is nog niet geactiveerd.')
    await invitationFeedback.getByRole('button', { name: 'OK' }).click()

    const invitationCard = page.getByTestId('household-invitation-invite-new')
    await expect(invitationCard).toContainText('nieuw-lid@example.com')
    await expect(page.getByTestId('household-invitation-status-invite-new')).toHaveText('In afwachting')
    await expect(page.getByTestId('household-invitation-delivery-invite-new')).toHaveText('E-mail nog niet geactiveerd')

    await page.getByTestId('household-invitation-resend-invite-new').click()
    const resendFeedback = page.getByTestId('app-feedback-error')
    await expect(resendFeedback).toContainText('Uitnodigingsmail is uitgeschakeld.')
    await resendFeedback.getByRole('button', { name: 'OK' }).click()
    await expect(page.getByTestId('household-invitation-status-invite-new')).toHaveText('In afwachting')

    await page.getByTestId('household-invitation-revoke-invite-new').click()
    await expect(page.getByTestId('household-invitation-revoke-modal')).toBeVisible()
    await page.getByTestId('household-invitation-revoke-confirm').click()
    const revokeFeedback = page.getByTestId('app-feedback-success')
    await expect(revokeFeedback).toContainText('Uitnodiging voor nieuw-lid@example.com ingetrokken.')
    await revokeFeedback.getByRole('button', { name: 'OK' }).click()
    await expect(page.getByTestId('household-invitation-status-invite-new')).toHaveText('Ingetrokken')
    await expect(page.getByTestId('household-invitation-resend-invite-new')).toHaveCount(0)

    await expectNoConsoleErrors(consoleErrors)
  })
})
