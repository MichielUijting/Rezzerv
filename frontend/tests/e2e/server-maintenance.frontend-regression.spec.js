import { expect, test } from '@playwright/test'

const session = {
  user: { id: 'maintenance-platform-user', email: 'maintenance@example.test' },
  user_id: 'maintenance-platform-user', email: 'maintenance@example.test', context_type: 'none',
  active_household_id: null, role: null, display_role: null,
  permissions: { 'platform.recovery.manage': true }, supported_permissions: ['platform.recovery.manage'],
  is_platform_superuser: false, is_frontteam: false,
}

test('maintenance actions use exact generation and never offer an unproved Windows reboot', async ({ page }) => {
  let state = { state: 'normal', generation: 0, active_operations: 0, restart_allowed: false, host_agent_ready: true }
  const requests = []
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
  await page.goto('/platform/herstel')
  const panel = page.getByTestId('platform-maintenance-panel')
  await expect(panel.getByRole('button', { name: 'Onderhoud aankondigen' })).toBeDisabled()
  await panel.getByLabel('Onderhoudsvenster en verwachte duur').fill('Morgen 10:00 Europe/Amsterdam, 15 minuten')
  await panel.getByRole('button', { name: 'Onderhoud aankondigen' }).click()
  await panel.getByRole('button', { name: 'Verwerkingen veilig stoppen' }).click()
  await panel.getByRole('button', { name: 'Actuele veiligheidscontroles uitvoeren' }).click()
  await expect(panel.getByText('Herstarttoestemming ontbreekt of is verlopen.', { exact: false })).toBeVisible()
  await expect(panel.getByText('Alle veiligheidscontroles zijn geslaagd.', { exact: false })).toHaveCount(0)
  expect(requests.map(x => x.action)).toEqual(['announce', 'drain', 'prepare'])
})
