import { expect, test } from '@playwright/test'

const permission = 'platform.functional_features.manage'
const shoppingKey = 'action.home.winkelen'
const inventoryKey = 'action.home.voorraad'
const gerechtenKey = 'feature.gerechten'

function metadata(key) {
  if (key === shoppingKey) return ['winkelen', 'Winkelen']
  if (key === inventoryKey) return ['voorraad', 'Voorraad']
  return ['recepten', 'Gerechten']
}

function actionItem(key, enabled, sortOrder) {
  const [homeTileKey, label] = metadata(key)
  return {
    key,
    category: key === gerechtenKey ? 'functional' : 'action_button',
    group: 'Startpagina',
    label,
    description: `${label} op de Startpagina platformbreed beheren.`,
    home_tile_key: homeTileKey,
    enabled,
    sort_order: sortOrder,
    default_enabled: key === gerechtenKey ? false : true,
    source: enabled === (key !== gerechtenKey) ? 'default' : 'override',
    updated_by: null,
    updated_at: null,
  }
}

function enabledFor(state, key) {
  if (key === shoppingKey) return state.shoppingEnabled
  if (key === inventoryKey) return state.inventoryEnabled
  return state.gerechtenEnabled
}

function orderedItems(state) {
  return state.order.map((key, index) => actionItem(key, enabledFor(state, key), index))
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
      user: { id: actor, email: `${actor}@example.test` }, user_id: actor, email: `${actor}@example.test`,
      permissions, supported_permissions: Object.keys(permissions), context_type: superuser ? 'system' : 'regular',
      active_household_id: superuser ? '0' : 'test-household', role: superuser ? 'owner' : 'member',
      display_role: superuser ? 'owner' : 'member', is_platform_superuser: superuser, is_frontteam: false,
    })
    if (path === '/api/onboarding') return json({ onboarding_status: 'completed', primary_use_case: null })
    if (path === '/api/features') return json({ features: { [gerechtenKey]: state.gerechtenEnabled } })

    if (path === '/api/action-buttons') {
      state.productReads++
      if (state.productGate?.promise) await state.productGate.promise
      return json({ items: orderedItems(state).map(({ key, home_tile_key, enabled, sort_order }) => ({ key, home_tile_key, enabled, sort_order })) })
    }

    if (path === '/api/platform/action-buttons') {
      state.managementReads++
      if (!superuser) return json({}, 403)
      return json({ items: orderedItems(state) })
    }

    if (path === '/api/platform/action-buttons/order' && request.method() === 'PUT') {
      if (!superuser) return json({}, 403)
      const payload = request.postDataJSON()
      state.orderUpdates.push(payload.keys)
      state.order = [...payload.keys]
      return json({ items: orderedItems(state) })
    }

    if (path.startsWith('/api/platform/action-buttons/') && request.method() === 'PUT') {
      if (!superuser) return json({}, 403)
      const key = decodeURIComponent(path.slice('/api/platform/action-buttons/'.length))
      const payload = request.postDataJSON()
      state.updates.push({ key, payload })
      if (key === shoppingKey) state.shoppingEnabled = payload.enabled
      if (key === inventoryKey) state.inventoryEnabled = payload.enabled
      if (key === gerechtenKey) state.gerechtenEnabled = payload.enabled
      return json({ item: actionItem(key, payload.enabled, state.order.indexOf(key)) })
    }

    if (path === '/api/shopping-list') return json({ items: [{
      id: 'shopping-1', article_name: 'Melk', product_type_name: 'Zuivel', size: '', note: '', checked: false,
    }], item_count: 1 })
    return json({}, 404)
  })
}

function initialState(overrides = {}) {
  return {
    shoppingEnabled: true, inventoryEnabled: true, gerechtenEnabled: false,
    productReads: 0, managementReads: 0, updates: [], orderUpdates: [],
    order: [shoppingKey, inventoryKey, gerechtenKey],
    ...overrides,
  }
}

test('Superuser manages Startpagina actions with an inline confirmation on the selected action', async ({ page }) => {
  const state = initialState()
  await mockApi(page, 'superuser', state)
  await page.goto('/superuser')
  await page.getByTestId('superuser-control-tab-action-buttons').click()
  await expect.poll(() => state.managementReads).toBeGreaterThan(0)
  const item = page.getByTestId(`superuser-action-button-${shoppingKey}`)
  const otherItem = page.getByTestId(`superuser-action-button-${inventoryKey}`)
  await item.getByRole('button', { name: 'Uitschakelen', exact: true }).click()
  const confirmation = item.getByTestId('superuser-action-button-confirmation')
  await expect(confirmation).toBeVisible()
  await expect(item.getByRole('button', { name: 'Uitschakelen', exact: true })).toBeDisabled()
  await expect(otherItem.getByRole('button', { name: 'Uitschakelen', exact: true })).toBeEnabled()
  await confirmation.getByRole('button', { name: 'Definitief bevestigen', exact: true }).click()
  await expect(item).toContainText('Niet beschikbaar')
  expect(state.updates).toEqual([{ key: shoppingKey, payload: { enabled: false } }])
})

test('Superuser drags an action before another action and persists the shifted order', async ({ page }) => {
  const state = initialState()
  await mockApi(page, 'superuser', state)
  await page.goto('/superuser')
  await page.getByTestId('superuser-control-tab-action-buttons').click()
  await expect.poll(() => state.managementReads).toBeGreaterThan(0)

  const inventory = page.getByTestId(`superuser-action-order-item-${inventoryKey}`)
  const shopping = page.getByTestId(`superuser-action-order-item-${shoppingKey}`)
  await inventory.dragTo(shopping)

  await expect.poll(() => state.orderUpdates.length).toBe(1)
  expect(state.orderUpdates[0]).toEqual([inventoryKey, shoppingKey, gerechtenKey])
  await expect(inventory).toHaveAttribute('data-sort-order', '0')
  await expect(shopping).toHaveAttribute('data-sort-order', '1')
  await expect(page.getByTestId('superuser-action-order-status')).toContainText('Voorraad staat nu voor Winkelen')
})

test('Startpagina waits for the current server projection before rendering managed actions', async ({ page }) => {
  let releaseProjection
  const state = initialState({
    shoppingEnabled: false,
    productGate: { promise: new Promise((resolve) => { releaseProjection = resolve }) },
  })
  await mockApi(page, 'member', state)
  await page.goto('/home')
  await expect.poll(() => state.productReads).toBeGreaterThan(0)
  await expect(page.getByTestId('home-action-availability-loading')).toBeVisible()
  releaseProjection()
  await expect(page.getByTestId('home-action-availability-loading')).toHaveCount(0)
  await expect(page.getByTestId('home-tile-winkelen')).toHaveCount(0)
  await expect(page.getByTestId('home-tile-voorraad')).toBeVisible()
})

test('ordinary user sees enabled Startpagina actions in the server-managed order', async ({ page }) => {
  const state = initialState({ order: [inventoryKey, shoppingKey, gerechtenKey] })
  await mockApi(page, 'member', state)
  await page.goto('/home')
  await expect.poll(() => state.productReads).toBeGreaterThan(0)
  const navigation = page.getByTestId('legacy-home-navigation')
  const positions = await navigation.locator('[data-testid^="home-tile-"]').evaluateAll((nodes) => nodes.map((node) => node.getAttribute('data-testid')))
  expect(positions.indexOf('home-tile-voorraad')).toBeLessThan(positions.indexOf('home-tile-winkelen'))
})

test('disabled Startpagina action hides only the home tile and leaves internal buttons intact', async ({ page }) => {
  const state = initialState({ shoppingEnabled: false })
  await mockApi(page, 'member', state)
  await page.goto('/home')
  await expect.poll(() => state.productReads).toBeGreaterThan(0)
  await expect(page.getByTestId('home-tile-winkelen')).toHaveCount(0)
  await expect(page.getByTestId('home-tile-voorraad')).toBeVisible()
  await page.goto('/winkelen')
  await expect(page.getByTestId('shopping-page')).toBeVisible()
  await expect(page.getByRole('button', { name: 'Winkelen afgerond', exact: true })).toBeVisible()
})

test('ordinary member cannot enter Superuser Startpagina-action management', async ({ page }) => {
  const state = initialState()
  await mockApi(page, 'member', state)
  await page.goto('/superuser')
  await expect(page).toHaveURL(/\/home$/)
  await expect(page.getByTestId('superuser-control-tab-action-buttons')).toHaveCount(0)
  expect(state.managementReads).toBe(0)
})
