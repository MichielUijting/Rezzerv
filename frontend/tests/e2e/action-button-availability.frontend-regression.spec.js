import { expect, test } from '@playwright/test'

const permission = 'platform.functional_features.manage'
const shoppingKey = 'action.shopping.complete'
const inventoryKey = 'action.inventory.add_incidental_purchase'

function actionItem(key, label, enabled, group = 'Winkelen', extra = {}) {
  return {
    key,
    category: 'action_button',
    group,
    label,
    description: `${label} platformbreed beheren.`,
    enabled,
    default_enabled: true,
    source: enabled ? 'default' : 'override',
    updated_by: null,
    updated_at: null,
    test_id: null,
    match_text: null,
    ...extra,
  }
}

async function mockApi(page, actor, state) {
  const superuser = actor === 'superuser'
  const permissions = superuser
    ? { [permission]: true, 'platform.system_household.access': true }
    : { 'shopping_list.view': true }

  await page.route('**/api/**', async (route) => {
    const request = route.request()
    const path = new URL(request.url()).pathname
    const json = (payload, status = 200) => route.fulfill({ status, json: payload })

    if (path === '/api/session') return json({
      user: { id: actor, email: `${actor}@example.test` },
      user_id: actor,
      email: `${actor}@example.test`,
      permissions,
      supported_permissions: Object.keys(permissions),
      context_type: superuser ? 'system' : 'regular',
      active_household_id: superuser ? '0' : 'test-household',
      role: superuser ? 'owner' : 'member',
      display_role: superuser ? 'owner' : 'member',
      is_platform_superuser: superuser,
      is_frontteam: false,
    })
    if (path === '/api/onboarding') return json({ onboarding_status: 'completed', primary_use_case: null })

    if (path === '/api/action-buttons') {
      state.productReads++
      return json({ items: [
        { key: shoppingKey, test_id: null, match_text: 'Winkelen afgerond', enabled: state.shoppingEnabled },
        { key: inventoryKey, test_id: 'inventory-add-incidental-purchase', match_text: null, enabled: state.inventoryEnabled },
      ] })
    }

    if (path === '/api/platform/action-buttons') {
      state.managementReads++
      if (!superuser) return json({}, 403)
      return json({ items: [
        actionItem(shoppingKey, 'Winkelen afgerond', state.shoppingEnabled),
        actionItem(inventoryKey, 'Incidentele aankoop toevoegen', state.inventoryEnabled, 'Voorraad', { test_id: 'inventory-add-incidental-purchase' }),
      ] })
    }

    if (path.startsWith('/api/platform/action-buttons/') && request.method() === 'PUT') {
      if (!superuser) return json({}, 403)
      const key = decodeURIComponent(path.slice('/api/platform/action-buttons/'.length))
      const payload = request.postDataJSON()
      state.updates.push({ key, payload })
      if (key === shoppingKey) state.shoppingEnabled = payload.enabled
      if (key === inventoryKey) state.inventoryEnabled = payload.enabled
      const label = key === shoppingKey ? 'Winkelen afgerond' : 'Incidentele aankoop toevoegen'
      const group = key === shoppingKey ? 'Winkelen' : 'Voorraad'
      return json({ item: actionItem(key, label, payload.enabled, group, key === inventoryKey ? { test_id: 'inventory-add-incidental-purchase' } : {}) })
    }

    if (path === '/api/shopping-list') return json({ items: [{
      id: 'shopping-1', article_name: 'Melk', product_type_name: 'Zuivel', size: '', note: '', checked: false,
    }], item_count: 1 })

    return json({}, 404) // Never forward a test request to a real backend.
  })
}

test('Superuser manages global action buttons from the Actieknoppen tab with confirmation', async ({ page }) => {
  const state = { shoppingEnabled: true, inventoryEnabled: true, productReads: 0, managementReads: 0, updates: [] }
  await mockApi(page, 'superuser', state)

  await page.goto('/superuser')
  const actionTab = page.getByTestId('superuser-control-tab-action-buttons')
  await expect(actionTab).toBeVisible()
  await actionTab.click()

  await expect(page.getByTestId('superuser-action-buttons')).toBeVisible()
  await expect.poll(() => state.managementReads).toBeGreaterThan(0)
  const item = page.getByTestId(`superuser-action-button-${shoppingKey}`)
  await expect(item).toContainText('Beschikbaar')

  await item.getByRole('button', { name: 'Uitschakelen', exact: true }).click()
  expect(state.updates).toEqual([])
  await expect(page.getByTestId('superuser-action-button-confirmation')).toBeVisible()
  await page.getByRole('button', { name: 'Definitief bevestigen', exact: true }).click()

  await expect(item).toContainText('Niet beschikbaar')
  expect(state.updates).toEqual([{ key: shoppingKey, payload: { enabled: false } }])
})

test('globally disabled shopping action disappears while unrelated actions stay available', async ({ page }) => {
  const state = { shoppingEnabled: false, inventoryEnabled: true, productReads: 0, managementReads: 0, updates: [] }
  await mockApi(page, 'member', state)

  await page.goto('/winkelen')
  await expect(page.getByTestId('shopping-page')).toBeVisible()
  await expect.poll(() => state.productReads).toBeGreaterThan(0)
  await expect(page.getByRole('button', { name: 'Winkelen afgerond', exact: true })).toHaveCount(0)
  await expect(page.getByRole('button', { name: 'Toevoegen', exact: true })).toBeVisible()
  await expect(page.getByRole('button', { name: 'Verwijderen', exact: true })).toBeVisible()

  state.shoppingEnabled = true
  await page.evaluate(() => window.dispatchEvent(new Event('rezzerv-action-buttons-changed')))
  await expect(page.getByRole('button', { name: 'Winkelen afgerond', exact: true })).toBeVisible()
})

test('ordinary member cannot enter Superuser action-button management', async ({ page }) => {
  const state = { shoppingEnabled: true, inventoryEnabled: true, productReads: 0, managementReads: 0, updates: [] }
  await mockApi(page, 'member', state)
  await page.goto('/superuser')
  await expect(page).toHaveURL(/\/home$/)
  await expect(page.getByTestId('superuser-control-tab-action-buttons')).toHaveCount(0)
  expect(state.managementReads).toBe(0)
})
