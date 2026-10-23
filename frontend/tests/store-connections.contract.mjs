import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { deriveStoreConnectionRows } from '../src/features/storeConnections/storeConnectionsModel.js'

const connectedAh = deriveStoreConnectionRows([], [], {
  connected: true,
  persistence: 'encrypted_database',
  last_sync_at: '2026-10-06T12:30:00Z',
})
assert.equal(connectedAh.length, 2)
const ah = connectedAh.find(row => row.providerCode === 'ah')
assert.ok(ah)
assert.equal(ah.providerCode, 'ah')
assert.equal(ah.providerName, 'Albert Heijn')
assert.equal(ah.statusLabel, 'gekoppeld')
assert.equal(ah.typeLabel, 'digitale kassabonnen')
assert.equal(ah.actionLabel, 'Beheren')
assert.equal(ah.connectionSource, 'ah_account')
assert.notEqual(ah.lastSyncLabel, '—')

const secureAhOverridesLegacy = deriveStoreConnectionRows(
  [{ code: 'ah', name: 'Albert Heijn' }],
  [{
    store_provider_code: 'ah',
    connection_status: 'active',
    connection_type: 'klantenkaart',
    external_account_ref: 'legacy-card',
  }],
  { connected: true, persistence: 'encrypted_database' },
)
assert.equal(secureAhOverridesLegacy.find(row => row.providerCode === 'ah').typeLabel, 'digitale kassabonnen')
assert.equal(secureAhOverridesLegacy.find(row => row.providerCode === 'ah').cardNumber, '')

const legacyLidl = deriveStoreConnectionRows(
  [{ code: 'lidl', name: 'Lidl' }],
  [{
    store_provider_code: 'lidl',
    connection_status: 'active',
    connection_type: 'klantenkaart',
    external_account_ref: '12345',
    linked_at: '2026-10-01T09:00:00Z',
  }],
  { connected: false },
)
assert.equal(legacyLidl.find((row) => row.providerCode === 'lidl')?.statusLabel, 'gekoppeld')
assert.equal(legacyLidl.find((row) => row.providerCode === 'lidl')?.cardNumber, '12345')

const unavailableAldi = deriveStoreConnectionRows(
  [{ code: 'aldi', name: 'Aldi' }],
  [{ store_provider_code: 'aldi', connection_status: 'active', external_account_ref: 'old-card' }],
  { connected: false },
).find(row => row.providerCode === 'aldi')
assert.equal(unavailableAldi.statusLabel, 'niet beschikbaar')
assert.equal(unavailableAldi.actionLabel, 'Niet mogelijk')
assert.equal(unavailableAldi.connectionSource, 'unavailable')
assert.equal(unavailableAldi.connection, null)
assert.equal(unavailableAldi.cardNumber, '')

const page = readFileSync(new URL('../src/features/storeConnections/StoreConnectionsPage.jsx', import.meta.url), 'utf8')
assert.match(page, /aldi-digital-unavailable/)
assert.match(page, /Papieren kassabonnen kun je nog steeds in Kassa scannen/)
assert.match(page, /geen digitale kassabonnen aan via haar website of klantenpas/)
assert.doesNotMatch(page, /<h3 style={{ margin: 0 }}>Winkelkoppelingen<\/h3>/)
assert.doesNotMatch(page, /loyalty-connections-settings/)
assert.doesNotMatch(page, /dataTestId="store-connections-table"/)
assert.match(page, /import DataTable from '..\/..\/ui\/DataTable\.jsx'/)
assert.match(page, /dataTestId="receipt-connections-overview-table"/)
assert.match(page, /tableClassName="rz-store-review-table rz-receipt-connection-compact-table"/)
const receiptColumns = page.slice(page.indexOf("const receiptConnectionColumns"), page.indexOf("const storeConnectionColumns"))
assert.deepEqual([...receiptColumns.matchAll(/header: '([^']+)'/g)].map(match => match[1]),
  ['Winkel', 'Laatst bijgewerkt', 'Status'])
assert.match(receiptColumns, /data-testid={`receipt-connection-action-/)
assert.match(receiptColumns, /width: isMobileViewport/)
assert.doesNotMatch(receiptColumns, /header: 'Bonnen ophalen'/)

const table = readFileSync(new URL('../src/ui/Table.jsx', import.meta.url), 'utf8')
assert.match(table, /columnIndex >= widths\.length - 1\) return/)
assert.match(table, /RESIZE_HIT_ZONE_PX/)
const lidlBridge = readFileSync(new URL('../src/features/storeConnections/lidlWebReceiptBridge.js', import.meta.url), 'utf8')
assert.ok(lidlBridge.includes("test(description) ? 'deposit' : 'product'"))
assert.ok(lidlBridge.includes("lineType: 'deposit'"))
assert.ok(lidlBridge.includes("product.lineType !== 'deposit'"))
assert.ok(lidlBridge.includes("product.lineType === 'deposit'"))

console.log('STORE_CONNECTIONS_AH_TABLE_GREEN')
