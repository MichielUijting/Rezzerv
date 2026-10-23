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
assert.match(page, /jumbo-help-open/)
assert.match(page, /lidl-help-open/)
assert.match(page, /provider="jumbo"/)
assert.match(page, /provider="lidl"/)
assert.match(page, /RetailerBookmarkletHelp/)
assert.match(page, /setupHelpStore === 'jumbo'/)
assert.match(page, /setupHelpStore === 'lidl'/)
assert.doesNotMatch(page, /<details data-testid="lidl-bookmarklet-help"/)
assert.match(page, /data-testid={`receipt-connection-unavailable-/)
assert.match(page, /row.providerCode === 'aldi' \|\| row.providerCode === 'plus'/)
assert.match(page, /color: 'var\(--color-ui-primary\)'/)
assert.match(page, /lidl-from-date/)
assert.match(page, /lidl-to-date/)
assert.doesNotMatch(page, /lidl-save-period/)
assert.doesNotMatch(page, /lidl-reset-period/)
assert.match(page, /retailer="Lidl"/)
assert.match(page, /openTestId="lidl-web-open-history"/)
assert.match(page, /onOpen={openLidlWithSavedPeriod}/)
assert.match(page, /async function openLidlWithSavedPeriod\(\)/)
assert.match(page, /const needsSave = lidlPeriodUnsaved/)
assert.match(page, /needsSave && !lidlWindow\.can_manage/)
assert.match(page, /window\.open\('about:blank', '_blank'\)/)
assert.match(page, /lidlTab\.location\.replace\(LIDL_HISTORY_URL\)/)
assert.match(page, /data\?\.configured_from_date !== lidlFrom/)
assert.match(page, /lidlTab\.close\(\)/)
assert.doesNotMatch(page, /Sla de gekozen periode eerst op/)
assert.doesNotMatch(page, /Automatische periode hersteld/)
assert.doesNotMatch(page, /lidl-period-unsaved/)

assert.match(page, /helpTestId="lidl-help-open"/)

const openLidl = page.slice(page.indexOf('async function openLidlWithSavedPeriod'), page.indexOf('useEffect(() => {', page.indexOf('async function openLidlWithSavedPeriod')))
assert.ok(openLidl.indexOf("window.open('about:blank'") < openLidl.indexOf("method: 'PUT'"),
  'Browser popup must be opened synchronously in the user gesture')
assert.ok(openLidl.indexOf("method: 'PUT'") < openLidl.indexOf('lidlTab.location.replace'),
  'Lidl must not navigate until the save is confirmed')

const retailerPanel = readFileSync(
  new URL('../src/features/storeConnections/RetailerReceiptPanel.jsx', import.meta.url),
  'utf8',
)
assert.equal((page.match(/<RetailerReceiptPanel\b/g) || []).length, 2,
  'Jumbo en Lidl moeten dezelfde component gebruiken')
assert.match(retailerPanel, /{retailer} digitale kassabonnen/)
assert.match(retailerPanel, /Kies de periode en haal je kassabonnen op\./)
assert.equal((retailerPanel.match(/<Input\b/g) || []).length, 2)
assert.match(retailerPanel, /gridTemplateColumns: isMobileViewport/)
assert.match(retailerPanel, /160px/)
assert.match(retailerPanel, /240px/)
assert.match(retailerPanel, /width: '100%'/)
assert.match(retailerPanel, /Open mijn {retailer}/)
assert.match(retailerPanel, /Eerste keer koppelen met {retailer}\?/)
assert.match(retailerPanel, /data-testid={openTestId}/)
assert.match(retailerPanel, /data-testid={helpTestId}/)
assert.doesNotMatch(page, /Kies de periode en haal je kassabonnen op\./)

// PO correction: regular vertical spacing in every store detail,
// without changing desktop spacing or the global input component.
assert.match(retailerPanel, /rowGap: '12px'/)
assert.match(retailerPanel, /margin: '6px 0 0'/)
assert.match(retailerPanel, /columnGap: '12px', rowGap: '12px'/)
assert.match(retailerPanel, /className=\{isMobileViewport \? 'rz-store-receipt-panel--mobile'/)
const compactCss = readFileSync(new URL('../src/features/storeConnections/retailerReceiptPanel.css', import.meta.url), 'utf8')
assert.match(compactCss, /\.rz-store-receipt-panel--mobile \.rz-input-field\s*\{\s*row-gap: 6px;/)
assert.match(page, /data-testid="ah-digital-receipts" style=\{\{ display: 'grid', rowGap: '12px'/)
assert.match(page, /data-testid="aldi-digital-unavailable" role="status" style=\{\{ display: 'grid', rowGap: '6px'/)
const picnicPanel = readFileSync(new URL('../src/features/storeConnections/PicnicAccountResearchPanel.jsx', import.meta.url), 'utf8')
assert.match(picnicPanel, /rowGap: '12px'/)

const bookmarkletHelp = readFileSync(new URL('../src/features/storeConnections/RetailerBookmarkletHelp.jsx', import.meta.url), 'utf8')
assert.match(bookmarkletHelp, /createPortal/)
assert.match(bookmarkletHelp, /role="dialog"/)
assert.match(bookmarkletHelp, /aria-modal="true"/)
assert.match(bookmarkletHelp, /provider \+ '-bookmarklet-dialog'/)
assert.match(bookmarkletHelp, /provider \+ '-help-ok'/)
assert.match(bookmarkletHelp, /event\.key === 'Escape'/)
assert.match(bookmarkletHelp, /onClick={onClose}/)
assert.match(bookmarkletHelp, /draggable={valid}/)
assert.doesNotMatch(bookmarkletHelp, /onClick=\{onClose\}[^<]*<\/div>/)
assert.doesNotMatch(page, /<summary[^>]*>Eerste keer\? Stel de Jumbo-favoriet in/)

assert.doesNotMatch(page, /loyalty-connections-settings/)
assert.doesNotMatch(page, /Klantenkaarten en bestaande winkelinstellingen/)
assert.doesNotMatch(page, /Kies je supermarkt in het overzicht/)
assert.doesNotMatch(page, /server/i)
assert.doesNotMatch(page, /<h2[^>]*>Winkelkoppelingen<\/h2>/)
assert.match(page, /Deze winkelketen biedt geen digitale kassabonnen aan via haar website of klantenpas/)
// The main mobile table stays one compact row per shop; never revert to
// Settings' label-per-cell card layout or affect other tables.
assert.match(page, /receipt-connection-mobile-heading/)
assert.match(page, /rz-receipt-connection-compact-table/)
assert.match(page, /isMobileViewport \? \(/)
const mobileCompact = readFileSync(
  new URL('../src/features/storeConnections/receiptConnectionCompact.css', import.meta.url), 'utf8',
)
assert.match(mobileCompact, /@media \(max-width: 720px\)/)
assert.match(mobileCompact, /rz-receipt-connection-mobile-heading/)
assert.match(mobileCompact, /grid-template-columns: minmax\(0, 1fr\) minmax\(0, 1.2fr\) minmax\(0, 1.5fr\)/)
assert.match(mobileCompact, /rz-receipt-connection-compact-table tbody tr/)
assert.match(mobileCompact, /min-height: 44px !important/)
assert.match(mobileCompact, /tbody td\[data-mobile-label\]::before/)
assert.match(mobileCompact, /content: none/)
assert.match(mobileCompact, /tbody td button/)
assert.doesNotMatch(mobileCompact, /(?:^|\n)\s*\.rz-table tbody tr\b/)

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
