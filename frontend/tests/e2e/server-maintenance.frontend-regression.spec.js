import { expect, test } from '@playwright/test'

const session = {
  user: { id: 'maintenance-platform-user', email: 'maintenance@example.test' },
  user_id: 'maintenance-platform-user', email: 'maintenance@example.test', context_type: 'none',
  active_household_id: null, role: null, display_role: null,
  permissions: { 'platform.recovery.manage': true, 'platform.sessions.revoke': true }, supported_permissions: ['platform.recovery.manage', 'platform.sessions.revoke'],
  is_platform_superuser: false, is_frontteam: false,
}

test('maintenance actions use exact generation and never offer an unproved Windows reboot', async ({ page }) => {
  let state = { state: 'normal', generation: 0, active_operations: 0, restart_allowed: false, host_agent_ready: true }
  const requests = []
  const sessionClosures = []
  await page.route('**/api/session', route => route.fulfill({ json: session }))
  await page.route('**/api/maintenance/status', route => route.fulfill({ json: { state: 'normal' } }))
  await page.route('**/api/platform/maintenance', async route => {
    if (route.request().method() === 'POST') {
      const payload = route.request().postDataJSON()
      requests.push(payload)
      expect(payload.expected_generation).toBe(state.generation)
      const target = { announce: 'announced', drain: 'draining', prepare: 'locked' }[payload.action]
      state = { ...state, state: target, generation: state.generation + 1, runtime_checks_passed: payload.action === 'prepare' }
    }
    await route.fulfill({ json: state })
  })
  await page.route('**/api/platform/maintenance/sessions/close', route => {
    sessionClosures.push(route.request().postDataJSON())
    return route.fulfill({ json: { sessions_revoked: 2, current_session_preserved: true, operations_untouched: true } })
  })
  await page.goto('/platform/herstel')
  const panel = page.getByTestId('platform-maintenance-panel')
  await expect(panel.getByRole('button', { name: 'Onderhoud aankondigen' })).toBeDisabled()
  await panel.getByLabel('Onderhoudsvenster en verwachte duur').fill('Morgen 10:00 Europe/Amsterdam, 15 minuten')
  await panel.getByRole('button', { name: 'Onderhoud aankondigen' }).click()
  await panel.getByRole('button', { name: 'Resterende sessies beëindigen' }).click()
  await expect(panel.getByText('Niet-opgeslagen invoer van andere gebruikers kan verloren gaan.', { exact: false })).toBeVisible()
  await panel.getByRole('button', { name: 'Ja, andere sessies beëindigen' }).click()
  await expect(panel.getByText('2 andere inlogsessie(s) beëindigd.', { exact: false })).toBeVisible()
  expect(sessionClosures).toEqual([{ expected_generation: 1, confirmed: true }])
  await panel.getByRole('button', { name: 'Verwerkingen veilig stoppen' }).click()
  await panel.getByRole('button', { name: 'Actuele veiligheidscontroles uitvoeren' }).click()
  await expect(panel.getByText('Herstarttoestemming ontbreekt of is verlopen.', { exact: false })).toBeVisible()
  await expect(panel.getByText('Alle veiligheidscontroles zijn geslaagd.', { exact: false })).toHaveCount(0)
  expect(requests.map(x => x.action)).toEqual(['announce', 'drain', 'prepare'])
})

for (const viewport of [{ width: 1280, height: 800 }, { width: 390, height: 844 }, { width: 320, height: 640 }]) {
  test(`regular user sees bold maintenance overlay on header at ${viewport.width}px`, async ({ page }) => {
    await page.setViewportSize(viewport)
    await page.clock.install()
    let status = { state: 'normal' }
    await page.route('**/api/session', route => route.fulfill({ json: {
      ...session, context_type: 'regular', active_household_id: 'household-1',
      active_household_name: 'Test huishouden', role: 'member', display_role: 'member',
      permissions: {}, supported_permissions: [],
    } }))
    await page.route('**/api/session/households', route => route.fulfill({ json: { items: [], can_switch_households: false } }))
    await page.route('**/api/account/profile', route => route.fulfill({ json: { email: session.email, display_name: 'Test gebruiker' } }))
    await page.route('**/api/onboarding', route => route.fulfill({ json: {} }))
    await page.route('**/api/maintenance/status', route => route.fulfill({ json: status }))
    await page.goto('/instellingen/mijn-account')
    const header = viewport.width > 720 ? page.getByTestId('app-header') : page.locator('.rz-mobile-app-header')
    const notice = page.getByTestId('maintenance-notice')
    await expect(header).toBeVisible()
    await expect(notice).toHaveCount(0)
    const before = await header.boundingBox()

    status = { state: 'announced', announcement: 'Onderhoud aan Inhuis morgen om 10:00 Europe/Amsterdam, verwachte duur 15 minuten.' }
    await page.clock.fastForward(15000)
    await expect(notice).toHaveText(status.announcement)
    await expect(notice).toHaveAttribute('role', 'status')
    await expect(notice.locator('strong')).toHaveCSS('font-weight', '700')
    await expect(notice).toHaveCSS('position', 'fixed')
    await expect(notice).toHaveCSS('background-color', 'rgb(255, 241, 220)')
    const overlay = await notice.boundingBox()
    const after = await header.boundingBox()
    expect(after.y).toBe(before.y)
    expect(overlay.y).toBeLessThan(after.y + after.height)
    expect(overlay.y + overlay.height).toBeGreaterThan(after.y)
    expect(overlay.x).toBeGreaterThanOrEqual(0)
    expect(overlay.x + overlay.width).toBeLessThanOrEqual(viewport.width)
    expect(await notice.evaluate(el => {
      const rect = el.getBoundingClientRect()
      return el.contains(document.elementFromPoint(rect.x + rect.width / 2, rect.y + 4))
    })).toBe(true)

    status = { state: 'announced', announcement: 'Langonderhoudsbericht'.repeat(100) }
    await page.clock.fastForward(15000)
    await expect(notice).toHaveText(status.announcement)
    expect(await notice.evaluate(el => el.scrollWidth <= el.clientWidth)).toBe(true)
    expect((await notice.boundingBox()).height).toBeLessThanOrEqual(viewport.height * 0.4 + 1)

    for (const state of ['draining', 'locked', 'verifying', 'blocked']) {
      status = { state, announcement: 'Bericht van de platformbeheerder: Windows wordt bijgewerkt.' }
      await page.clock.fastForward(15000)
      await expect(notice).toHaveText(status.announcement)
    }
    status = { state: 'draining', announcement: '   ' }
    await page.clock.fastForward(15000)
    await expect(notice).toContainText('nieuwe verwerkingen zijn tijdelijk geblokkeerd')
    status = { state: 'normal' }
    await page.clock.fastForward(15000)
    await expect(notice).toHaveCount(0)
    await expect(header).toBeVisible()
  })
}
