import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { deriveReceiptConnectionOverview, receiptConnectionSummary, displayedImportDate, firstImportDate, safeImportDate } from '../src/features/storeConnections/receiptConnectionOverviewModel.js'

const clock = new Date('2026-10-23T12:00:00')
assert.equal(firstImportDate(clock), '2025-01-01')
assert.equal(displayedImportDate(undefined, clock).label, '01-01-2025')
assert.equal(displayedImportDate('2026-10-19', clock).label, '19-10-2026')
assert.equal(displayedImportDate('2026-10-19', clock).isDefault, false)
assert.equal(safeImportDate('2026-02-30', clock), null)
assert.equal(safeImportDate('2027-01-01', clock), null)
assert.equal(safeImportDate('2026-10-19 15:04:06', clock), null)
const seenRows = deriveReceiptConnectionOverview([], { connected: false },
  { jumbo: '2026-10-19', lidl: '2026-10-21' }, clock)
assert.equal(seenRows.find(row => row.providerCode === 'jumbo').lastSyncLabel, '19-10-2026')
assert.equal(seenRows.find(row => row.providerCode === 'jumbo').lastUpdatedDate, '2026-10-19')
assert.equal(seenRows.find(row => row.providerCode === 'lidl').lastSyncLabel, '21-10-2026')

const rows = deriveReceiptConnectionOverview(
  [
    { providerCode: 'ah', providerName: 'Albert Heijn', statusLabel: 'gekoppeld', lastSyncLabel: '22-10-2026 15:00' },
    { providerCode: 'jumbo', providerName: 'Jumbo', statusLabel: 'gekoppeld', connectionSource: 'store_connection', cardNumber: '123456' },
    { providerCode: 'lidl', providerName: 'Lidl', statusLabel: 'gekoppeld', connectionSource: 'store_connection' },
  ],
  { connected: true },
)
assert.deepEqual(rows.map(row => row.providerCode), ['ah', 'jumbo', 'lidl', 'picnic', 'aldi', 'plus'])
assert.equal(rows.find(row => row.providerCode === 'ah').statusLabel, 'Gekoppeld')
assert.equal(rows.find(row => row.providerCode === 'ah').isAutomatic, true)
assert.equal(rows.find(row => row.providerCode === 'ah').lastSyncLabel, '22-10-2026 15:00')
for (const code of ['jumbo', 'lidl']) {
  const row = rows.find(item => item.providerCode === code)
  assert.equal(row.isAutomatic, false)
  assert.equal(row.statusLabel, 'Browserstap nodig')
  assert.equal(row.actionLabel, 'Bonnen ophalen')
  assert.equal(row.lastSyncLabel, displayedImportDate(undefined).label)
  assert.equal(row.lastUpdatedDate, firstImportDate())
  assert.equal(row.isDefaultImportDate, true)
  assert.equal(row.cardNumber, undefined)
}
const picnic = rows.find(row => row.providerCode === 'picnic')
assert.equal(picnic.isAvailable, false)
assert.equal(picnic.statusLabel, 'Nog niet beschikbaar')
for (const code of ['aldi', 'plus']) {
  const row = rows.find(item => item.providerCode === code)
  assert.equal(row.isAvailable, false)
  assert.equal(row.statusLabel, 'Geen koppeling mogelijk')
  assert.equal(row.actionLabel, 'Geen koppeling mogelijk')
}
assert.deepEqual(receiptConnectionSummary(rows), { automatic: 1, browser: 2, unavailable: 3 })
const disconnected = deriveReceiptConnectionOverview([], { connected: false })
assert.equal(disconnected.find(row => row.providerCode === 'ah').statusLabel, 'Niet gekoppeld')
assert.equal(disconnected.find(row => row.providerCode === 'ah').isAutomatic, false)
assert.equal(receiptConnectionSummary(disconnected).automatic, 0)

const page = readFileSync(new URL('../src/features/storeConnections/StoreConnectionsPage.jsx', import.meta.url), 'utf8')
assert.match(page, /receipt-connections-overview-table/)
assert.doesNotMatch(page, /data-testid="receipt-connection-summary"/)
assert.match(page, /data-testid="receipt-connection-details"/)
assert.match(page, /\/api\/receipts\/retailers\/last-updated/)
assert.match(page, /maxWidth: '760px'/)
assert.match(page, /gridTemplateColumns: 'minmax\(0, 1fr\)'/)
assert.match(page, /jumbo-from-date/)
assert.match(page, /jumbo-bookmarklet-dialog/)
assert.match(page, /jumbo-help-open/)
assert.match(page, /jumbo-help-ok/)
assert.match(page, /createPortal/)
assert.match(page, /event\.key === 'Escape'/)
assert.match(page, /setJumboHelpOpen\(false\)/)
assert.doesNotMatch(page, /<summary[^>]*>Eerste keer\? Stel de Jumbo-favoriet in/)

assert.doesNotMatch(page, /loyalty-connections-settings/)
assert.doesNotMatch(page, /Klantenkaarten en bestaande winkelinstellingen/)
assert.doesNotMatch(page, /Kies je supermarkt in het overzicht/)
assert.doesNotMatch(page, /server/i)
assert.doesNotMatch(page, /<h2[^>]*>Winkelkoppelingen<\/h2>/)
assert.match(page, /Deze winkelketen biedt geen digitale kassabonnen aan via haar website of klantenpas/)
const columns = page.slice(page.indexOf('const receiptConnectionColumns'), page.indexOf('const storeConnectionColumns'))
assert.deepEqual([...columns.matchAll(/header: '([^']+)'/g)].map(match => match[1]),
  ['Winkel', 'Laatst bijgewerkt', 'Status'])
assert.doesNotMatch(columns, /header: 'Bonnen ophalen'/)
assert.doesNotMatch(columns, /header: 'Actie'/)
assert.match(columns, /data-testid={`receipt-connection-status-/)
assert.match(columns, /<Button/)
assert.match(columns, /isMobileViewport \? 90 : 190/)
assert.match(page, /activeProvider === 'jumbo'/)
assert.match(page, /activeProvider === 'lidl'/)
assert.match(page, /activeProvider === 'ah'/)
assert.match(page, /<ImportProgress store="Jumbo"/)
assert.match(page, /<ImportProgress store="Lidl"/)
assert.match(page, /<ImportProgress store="Albert Heijn"/)
assert.match(page, /isMobileViewport/)
assert.doesNotMatch(page, /automatisch bonnen ophalen zonder opnieuw te koppelen/)

const kassa = readFileSync(new URL('../src/features/kassa/KassaPage.jsx', import.meta.url), 'utf8')
assert.match(kassa, /minimumInterval = 15 \* 60 \* 1000/)
assert.match(kassa, /inFlight/)
assert.match(kassa, /visibilitychange/)
assert.match(kassa, /window\.clearInterval\(interval\)/)
assert.match(kassa, /\/api\/receipts\/retailers\/ah\/sync/)
const notice = readFileSync(new URL('../src/features/platform/MaintenanceNotice.jsx', import.meta.url), 'utf8')
assert.match(notice, /Onderhoud aan Inhuis/)
assert.doesNotMatch(notice, /Serveronderhoud/)
const maintenance = readFileSync(new URL('../src/features/platform/PlatformMaintenancePanel.jsx', import.meta.url), 'utf8')
assert.match(maintenance, /Onderhoud aan Inhuis/)
const account = readFileSync(new URL('../src/features/settings/SettingsMyAccountPage.jsx', import.meta.url), 'utf8')
assert.match(account, /actieve Inhuis-sessie/)

console.log('RECEIPT_CONNECTION_OVERVIEW_GREEN')
