import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { deriveStoreConnectionRows } from '../src/features/storeConnections/storeConnectionsModel.js'

const connectedAh = deriveStoreConnectionRows([], [], {
  connected: true,
  persistence: 'encrypted_database',
  last_sync_at: '2026-10-06T12:30:00Z',
})
assert.equal(connectedAh.length, 1)
assert.equal(connectedAh[0].providerCode, 'ah')
assert.equal(connectedAh[0].providerName, 'Albert Heijn')
assert.equal(connectedAh[0].statusLabel, 'gekoppeld')
assert.equal(connectedAh[0].typeLabel, 'digitale kassabonnen')
assert.equal(connectedAh[0].actionLabel, 'Beheren')
assert.equal(connectedAh[0].connectionSource, 'ah_account')
assert.notEqual(connectedAh[0].lastSyncLabel, '—')

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
assert.equal(secureAhOverridesLegacy[0].typeLabel, 'digitale kassabonnen')
assert.equal(secureAhOverridesLegacy[0].cardNumber, '')

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

const page = readFileSync(new URL('../src/features/storeConnections/StoreConnectionsPage.jsx', import.meta.url), 'utf8')
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
console.log('STORE_CONNECTIONS_AH_TABLE_GREEN')
