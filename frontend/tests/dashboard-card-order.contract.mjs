import assert from 'node:assert/strict'
import {
  DEFAULT_DASHBOARD_CARD_ORDER,
  readDashboardCardOrder,
  writeDashboardCardOrder,
} from '../src/features/home/dashboardCardOrder.js'

const store = new Map()
global.window = {
  localStorage: {
    getItem: (key) => store.has(key) ? store.get(key) : null,
    setItem: (key, value) => store.set(key, String(value)),
  },
}

const userA = { user_id: 'user-a' }
const userB = { user_id: 'user-b' }

assert.deepEqual(readDashboardCardOrder(userA), [...DEFAULT_DASHBOARD_CARD_ORDER])

const customOrder = ['begroting', 'winkels', 'uitgaven', 'uitgaven-vorig-jaar']
assert.deepEqual(writeDashboardCardOrder(customOrder, userA), customOrder)
assert.deepEqual(readDashboardCardOrder(userA), customOrder)

assert.deepEqual(readDashboardCardOrder(userB), [...DEFAULT_DASHBOARD_CARD_ORDER])

store.set('inhuis_dashboard_card_order_v1:user-b', JSON.stringify(['winkels', 'onbekend', 'winkels']))
assert.deepEqual(
  readDashboardCardOrder(userB),
  ['winkels', 'uitgaven-vorig-jaar', 'uitgaven', 'begroting'],
)

console.log('DASHBOARD_CARD_ORDER_CONTRACT_GREEN')
