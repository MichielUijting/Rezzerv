import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'

const css = readFileSync(new URL('../src/ui/mobileComponents.css', import.meta.url), 'utf8')
const inventory = readFileSync(new URL('../src/pages/MobileVoorraad.jsx', import.meta.url), 'utf8')
const shopping = readFileSync(new URL('../src/features/shopping/MobileShopping.jsx', import.meta.url), 'utf8')
assert.match(inventory, /<QuantityStepper/)
assert.match(shopping, /<QuantityStepper/)
assert.match(css, /\.rz-mobile-inventory-list \.rz-quantity-stepper-button/)
assert.match(css, /\.rz-mobile-shopping-list \.rz-quantity-stepper-button/)
assert.match(css, /flex: 0 0 31px;/)
assert.match(css, /flex: 0 0 32px;/)
assert.match(css, /flex-basis: 36px;/)
assert.match(css, /height: 44px;/)
const originalEditableWidth = 44 + 54 + 44 + 2 * 4
const compactEditableWidth = 31 + 36 + 31 + 2 * 3
const originalShoppingWidth = 44 * 3 + 2 * 4
const compactShoppingWidth = 31 + 32 + 31 + 2 * 3
assert.ok(Math.abs(compactEditableWidth / originalEditableWidth - 0.7) < 0.02)
assert.ok(Math.abs(compactShoppingWidth / originalShoppingWidth - 0.7) < 0.02)
console.log('PASS: mobile inventory/shopping quantity controls ~30% narrower, 44px tall')
