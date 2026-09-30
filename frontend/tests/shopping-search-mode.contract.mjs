import assert from 'node:assert/strict'
import {
  DEFAULT_SHOPPING_SEARCH_MODE,
  combineShoppingSearchResults,
  readShoppingSearchModePreference,
  shoppingSearchScopes,
  writeShoppingSearchModePreference,
} from '../src/features/shopping/shoppingSearchMode.js'

const store = new Map()
global.window = {
  localStorage: {
    getItem: (key) => store.has(key) ? store.get(key) : null,
    setItem: (key, value) => store.set(key, String(value)),
  },
}

const userA = { user_id: 'user-a' }
const userB = { user_id: 'user-b' }

assert.equal(DEFAULT_SHOPPING_SEARCH_MODE, 'specific')
assert.deepEqual(shoppingSearchScopes('specific'), ['global_products', 'household_articles'])
assert.deepEqual(shoppingSearchScopes('generic'), ['product_types', 'article_groups'])
assert.equal(readShoppingSearchModePreference(userA), 'specific')
assert.equal(writeShoppingSearchModePreference('generic', userA), 'generic')
assert.equal(readShoppingSearchModePreference(userA), 'generic')
assert.equal(readShoppingSearchModePreference(userB), 'specific')
assert.equal(writeShoppingSearchModePreference('specific', userB), 'specific')
assert.equal(readShoppingSearchModePreference(userB), 'specific')

assert.deepEqual(
  combineShoppingSearchResults([
    { items: [{ source_type: 'global_product', source_id: '1', label: 'Exact' }] },
    { items: [
      { source_type: 'global_product', source_id: '1', label: 'Dubbel' },
      { source_type: 'household_article', source_id: '2', label: 'Huishoud' },
    ] },
  ], 5).map((item) => item.label),
  ['Exact', 'Huishoud'],
)

console.log('SHOPPING_SEARCH_MODE_CONTRACT_GREEN')
