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
assert.match(page, /Aldi en PLUS/) 
assert.match(page, /geen digitaal toegankelijke kassabonnen voor een rechtstreekse koppeling/)
assert.match(page, /row.providerCode === 'aldi'/)
assert.doesNotMatch(page, /importAldiDigitalFile|aldi-digital-import|aldi-digital-file/)
assert.match(page, /import DataTable from '..\/..\/ui\/DataTable\.jsx'/)
assert.match(page, /dataTestId="store-connections-table"/)
assert.match(page, /tableClassName="rz-store-review-table"/)
assert.match(page, /key: 'providerName',[\s\S]*width: 180/)
assert.match(page, /key: 'typeLabel',[\s\S]*width: 190/)
assert.match(page, /key: 'statusLabel',[\s\S]*width: 130/)
assert.match(page, /key: 'lastSyncLabel',[\s\S]*width: 210/)
assert.match(page, /key: 'action',[\s\S]*width: 210/)
assert.doesNotMatch(page, /<table className="rz-table" data-testid="store-connections-table"/)

const table = readFileSync(new URL('../src/ui/Table.jsx', import.meta.url), 'utf8')
assert.match(table, /columnIndex >= widths\.length - 1\) return/)
assert.match(table, /RESIZE_HIT_ZONE_PX/)
const lidlBridge = readFileSync(new URL('../src/features/storeConnections/lidlWebReceiptBridge.js', import.meta.url), 'utf8')
assert.ok(lidlBridge.includes("test(description) ? 'deposit' : 'product'"))
assert.ok(lidlBridge.includes("lineType: 'deposit'"))
assert.ok(lidlBridge.includes("product.lineType !== 'deposit'"))
assert.ok(lidlBridge.includes("product.lineType === 'deposit'"))

console.log('STORE_CONNECTIONS_AH_TABLE_GREEN')
