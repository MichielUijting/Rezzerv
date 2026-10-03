import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'

const shopping = readFileSync(new URL('../src/features/shopping/MobileShopping.jsx', import.meta.url), 'utf8')
const css = readFileSync(new URL('../src/features/shopping/mobileShopping.css', import.meta.url), 'utf8')
const row = readFileSync(new URL('../src/ui/MobileArticleRow.jsx', import.meta.url), 'utf8')

assert.match(shopping, /onActivate=\{\(\) => moveItem\(item\)\}/)
assert.match(shopping, /checked: !Boolean\(item\.checked\)/)
assert.match(shopping, /activationRole="button"/)
assert.match(shopping, /rz-mobile-shopping-delete/)
assert.match(shopping, /mobile-shopping-delete-\$\{item\.id\}/)
assert.doesNotMatch(shopping, /selectedItemIds/)
assert.doesNotMatch(shopping, /mobile-shopping-delete-selected/)
assert.doesNotMatch(shopping, /mobile-shopping-move-to-cart/)
assert.doesNotMatch(shopping, /mobile-shopping-return-to-buy/)
assert.doesNotMatch(shopping, /type="checkbox"/)

assert.match(css, /grid-template-columns: 44px minmax\(0, 1fr\) auto/)
assert.match(css, /\.rz-mobile-shopping-delete[\s\S]*width: 31px[\s\S]*height: 44px/)
assert.match(css, /\.rz-mobile-shopping-row-actions/)

assert.match(row, /activationRole = 'link'/)
assert.match(row, /role=\{interactive \? activationRole : undefined\}/)

console.log('SHOPPING_ROW_INTERACTION_CONTRACT_GREEN')
