import { expect, test } from '@playwright/test'

const permission = 'platform.functional_features.manage'
const shoppingKey = 'action.home.winkelen'
const inventoryKey = 'action.home.voorraad'
const gerechtenKey = 'feature.gerechten'

function actionItem(key, homeTileKey, label, enabled) {
  return {
    key,
    category: key === gerechtenKey ? 'functional' : 'action_button',
    group: 'Startpagina',
    label,
    description: `${label} op de Startpagina platformbreed beheren.`,
    home_tile_key: homeTileKey,
    enabled,
    default_enabled: key === gerechtenKey ? false : true,
    source: enabled === (key !== gerechtenKey) ? 'default' : 'override',
    updated_by: null,
    updated_at: null,
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
      if (state.productGate?.promise) await state.productGate.promise
      return json({ items: [
        { key: shoppingKey, home_tile_key: 'winkelen', enabled: state.shoppingEnabled },
        { key: inventoryKey, home_tile_key: 'voorraad', enabled: state.inventoryEnabled },
        { key: gerechtenKey, home_tile_key: 'recepten', enabled: state.gerechtenEnabled },
      ] })
    }

    if (path === '/api/platform/action-buttons') {
      state.managementReads++
      if (!superuser) return json({}, 403)
      return json({ items: [
        actionItem(shoppingKey, 'winkelen', 'Winkelen', state.shoppingEnabled),
        actionItem(inventoryKey, 'voorraad', 'Voorraad', state.inventoryEnabled),
        actionItem(gerechtenKey, 'recepten', 'Gerechten', state.gerechtenEnabled),
      ] })
    }

    if (path.startsWith('/api/platform/action-buttons/') && request.method() === 'PUT') {
      if (!superuser) return json({}, 403)
      const key = decodeURIComponent(path.slice('/api/platform/action-buttons/'.length))
      const payload = request.postDataJSON()
      state.updates.push({ key, payload })
      if (key === shoppingKey) state.shoppingEnabled = payload.enabled
      if (key === inventoryKey) state.inventoryEnabled = payload.enabled
      if (key === gerechtenKey) state.gerechtenEnabled = payload.enabled
      const metadata = key === shoppingKey
        ? ['winkelen', 'Winkelen']
        : key === inventoryKey
          ? ['voorraad', 'Voorraad']
          : ['recepten', 'Gerechten']
      return json({ item: actionItem(key, metadata[0], metadata[1], payload.enabled) })
    }

    if (path === '/api/shopping-list') return json({ items: [{
      id: 'shopping-1', article_name: 'Melk', product_type_name: 'Zuivel', size: '', note: '', checked: false,
    }], item_count: 1 })

    return json({}, 404) // Never forward a test request to a real backend.
  })
}

test('Superuser manages Startpagina actions with an inline confirmation on the selected action', async ({ page }) => {
  const state = {
    shoppingEnabled: true,
    inventoryEnabled: true,
    gerechtenEnabled: false,
    productReads: 0,
    managementReads: 0,
    updates: [],
  }
  await mockApi(page, 'superuser', state)

  await page.goto('/superuser')
  const actionTab = page.getByTestId('superuser-control-tab-action-buttons')
  await expect(actionTab).toBeVisible()
  await actionTab.click()

  await expect(page.getByTestId('superuser-action-buttons')).toContainText('Actieknoppen op de Startpagina')
  await expect.poll(() => state.managementReads).toBeGreaterThan(0)
  const item = page.getByTestId(`superuser-action-button-${shoppingKey}`)
  const otherItem = page.getByTestId(`superuser-action-button-${inventoryKey}`)
  await expect(item).toContainText('Beschikbaar')

  await item.getByRole('button', { name: 'Uitschakelen', exact: true }).click()
  expect(state.updates).toEqual([])

  const confirmation = item.getByTestId('superuser-action-button-confirmation')
  await expect(confirmation).toBeVisible()
  await expect(confirmation).toContainText('Winkelen')
  await expect(item.getByRole('button', { name: 'Uitschakelen', exact: true })).toBeDisabled()
  await expect(otherItem.getByRole('button', { name: 'Uitschakelen', exact: true })).toBeEnabled()

  await confirmation.getByRole('button', { name: 'Definitief bevestigen', exact: true }).click()

  await expect(item).toContainText('Niet beschikbaar')
  await expect(item.getByTestId('superuser-action-button-confirmation')).toHaveCount(0)
  expect(state.updates).toEqual([{ key: shoppingKey, payload: { enabled: false } }])
})

test('Startpagina waits for the current server projection before rendering managed actions', async ({ page }) => {
  let releaseProjection
  const productGate = {
    promise: new Promise((resolve) => { releaseProjection = resolve }),
  }
  const state = {
    shoppingEnabled: false,
    inventoryEnabled: true,
    gerechtenEnabled: false,
    productReads: 0,
    managementReads: 0,
    updates: [],
    productGate,
  }
  await mockApi(page, 'member', state)

  await page.goto('/home')
  await expect.poll(() => state.productReads).toBeGreaterThan(0)
  await expect(page.getByTestId('home-action-availability-loading')).toBeVisible()
  await expect(page.getByTestId('home-tile-winkelen')).toHaveCount(0)
  await expect(page.getByTestId('home-tile-voorraad')).toHaveCount(0)

  releaseProjection()

  await expect(page.getByTestId('home-action-availability-loading')).toHaveCount(0)
  await expect(page.getByTestId('home-tile-winkelen')).toHaveCount(0)
  await expect(page.getByTestId('home-tile-voorraad')).toBeVisible()
})

test('disabled Startpagina action hides only the home tile and leaves internal buttons intact', async ({ page }) => {
  const state = {
    shoppingEnabled: false,
    inventoryEnabled: true,
    gerechtenEnabled: false,
    productReads: 0,
    managementReads: 0,
    updates: [],
  }
  await mockApi(page, 'member', state)

  await page.goto('/home')
  await expect.poll(() => state.productReads).toBeGreaterThan(0)
  await expect(page.getByTestId('home-tile-winkelen')).toHaveCount(0)
  await expect(page.getByTestId('home-tile-voorraad')).toBeVisible()

  await page.goto('/winkelen')
  await expect(page.getByTestId('shopping-page')).toBeVisible()
  await expect(page.getByRole('button', { name: 'Winkelen afgerond', exact: true })).toBeVisible()
  await expect(page.getByRole('button', { name: 'Toevoegen', exact: true })).toBeVisible()
  await expect(page.getByRole('button', { name: 'Verwijderen', exact: true })).toBeVisible()
})

test('ordinary member cannot enter Superuser Startpagina-action management', async ({ page }) => {
  const state = {
    shoppingEnabled: true,
    inventoryEnabled: true,
    gerechtenEnabled: false,
    productReads: 0,
    managementReads: 0,
    updates: [],
  }
  await mockApi(page, 'member', state)
  await page.goto('/superuser')
  await expect(page).toHaveURL(/\/home$/)
  await expect(page.getByTestId('superuser-control-tab-action-buttons')).toHaveCount(0)
  expect(state.managementReads).toBe(0)
})
