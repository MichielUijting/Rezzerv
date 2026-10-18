import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'

const dataTable = readFileSync(new URL('../src/ui/DataTable.jsx', import.meta.url), 'utf8')
const productGroups = readFileSync(new URL('../src/features/productGroups/ProductGroupsPage.jsx', import.meta.url), 'utf8')

assert.match(dataTable, /pagination = true,/)
assert.match(dataTable, /pageSize = 10,/)
assert.match(dataTable, /pageCount > 1 \|\| paginationActions/)
assert.match(dataTable, /pageCount > 1 \? <Pagination/)
assert.match(dataTable, /resizableColumns/)
assert.match(dataTable, /onColumnResize=/)
assert.match(dataTable, /setColumnWidth\(columnKey, width\)/)
assert.doesNotMatch(dataTable, /\[activeFilters, activeSort, data, normalizedPageSize, effectivePagination\]/)
assert.match(productGroups, /Math\.ceil\(filteredRows\.length \/ 10\)/)
assert.match(productGroups, /filteredRows\.slice\(\(currentPage - 1\) \* 10, currentPage \* 10\)/)
assert.match(productGroups, /visibleRows\.map\(\(row\)/)
assert.match(productGroups, /pageCount > 1 \? <Pagination/)
const kassa = readFileSync(new URL('../src/features/receipts/KassaPage.jsx', import.meta.url), 'utf8')
const unpacking = readFileSync(new URL('../src/features/stores/StoreBatchDetailPage.jsx', import.meta.url), 'utf8')
const mobilePagination = readFileSync(new URL('../src/ui/MobilePagination.jsx', import.meta.url), 'utf8')
for (const [label, source, expected] of [
  ['Kassa page count', kassa, 'const inboxPageCount = Math.max(1, Math.ceil(listItems.length / 10))'],
  ['Kassa page slicing', kassa, 'const pageInboxItems = listItems.slice((currentInboxPage - 1) * 10, currentInboxPage * 10)'],
  ['Kassa page selection', kassa, 'const allVisibleSelected = pageInboxItems.length > 0'],
  ['Kassa controls', kassa, 'inboxPageCount > 1 ? <Pagination'],
  ['Uitpakken desktop slicing', unpacking, 'const desktopPageLines = visibleLineUiStates.slice((currentDesktopLinePage - 1) * 10, currentDesktopLinePage * 10)'],
  ['Uitpakken viewport', unpacking, 'const renderedLineUiStates = isMobileViewport ? mobileLinePagination.pageItems : desktopPageLines'],
  ['Uitpakken controls', unpacking, 'desktopLinePageCount > 1 ? <Pagination'],
  ['Mobile page size', mobilePagination, 'export const MOBILE_PAGE_SIZE = 10'],
]) {
  assert.ok(source.includes(expected), label + ' ontbreekt')
}
const newlyCovered = [
  ['Stores', '../src/features/stores/StoresPage.jsx', ['visibleBatches.map(', 'visibleStores.map(', 'batchPageCount > 1 ? <Pagination', 'storePageCount > 1 ? <Pagination']],
  ['Authorization', '../src/features/settings/SettingsAuthorizationPage.jsx', ['visibleRows.map(', 'pageCount > 1 ? <Pagination']],
  ['Platform audit', '../src/features/platform/PlatformAuditPage.jsx', ['visibleItems.map(', 'pageCount > 1 ? <Pagination']],
  ['Platform logs', '../src/features/platform/PlatformLogsPage.jsx', ['visibleItems.map(', 'pageCount > 1 ? <Pagination']],
  ['Platform users', '../src/features/platform/PlatformUsersPage.jsx', ['visibleItems.map(', 'pageCount > 1 ? <Pagination']],
  ['Platform sessions', '../src/features/platform/PlatformSessionsPage.jsx', ['visibleItems.map(', 'pageCount > 1 ? <Pagination']],
  ['Platform integrations', '../src/features/platform/PlatformIntegrationsPage.jsx', ['visibleItems.map(', 'pageCount > 1 ? <Pagination']],
  ['Platform flags', '../src/features/platform/PlatformFeatureFlagsPage.jsx', ['visibleItems.map(', 'pageCount > 1 ? <Pagination']],
  ['Household support', '../src/features/support/HouseholdSupportPage.jsx', ['visibleThreads.map(', 'threadPageCount > 1 ? <Pagination']],
  ['Platform support', '../src/features/support/PlatformSupportPage.jsx', ['visibleThreads.map(', 'threadPageCount > 1 ? <Pagination']],
]
for (const [label, path, expectations] of newlyCovered) {
  const source = readFileSync(new URL(path, import.meta.url), 'utf8')
  for (const expected of expectations) assert.ok(source.includes(expected), label + ': missing ' + expected)
}

const dashboardDetail = readFileSync(new URL('../src/features/home/DashboardDetailPage.jsx', import.meta.url), 'utf8')
for (const expected of [
  'function useDashboardPagination(rows)',
  'const pageCount = Math.max(1, Math.ceil(rows.length / 10))',
  'rows.slice((currentPage - 1) * 10, currentPage * 10)',
  'visibleRows.map((receipt)',
  'visibleRows.map((group)',
  'visibleRows.map((article)',
  'visibleRows.map((item, index)',
  'pageCount > 1 ? <Pagination',
]) assert.ok(dashboardDetail.includes(expected), 'Dashboard detail: missing ' + expected)

const receiptsPage = readFileSync(new URL('../src/features/receipts/ReceiptsPage.jsx', import.meta.url), 'utf8')
for (const expected of [
  'const [selectedBatchesById, setSelectedBatchesById] = useState({})',
  '.map((id) => selectedBatchesById[id])',
  'const selected = selectedBatches',
  'const rows = selectedBatches',
  'else mobileVisibleItems.forEach((item) => { next[item.batch_id] = item })',
  'if (allVisibleSelected) visibleIds.forEach((id) => { delete next[id] })',
  'setSelectedBatchesById({})',
  'if (selectedBatches.length !== selectedBatchIds.length) return',
]) assert.ok(receiptsPage.includes(expected), 'Uitpakken cross-page selection: missing ' + expected)
assert.doesNotMatch(receiptsPage, /setSelectedBatchIds\(\(current\) => current\.filter\(\(id\) => visibleIds\.has\(id\)\)\)/)
assert.doesNotMatch(receiptsPage, /listItems\.filter\(\(item\) => selectedBatchIds\.includes\(item\.batch_id\)\)/)

// Existing Uitpakken lines must not trigger an unused historic-processing lookup.
const backend = readFileSync(new URL('../../backend/app/main.py', import.meta.url), 'utf8')
const syncStart = backend.indexOf('def sync_unpack_batch_lines_for_receipt(')
const syncEnd = backend.indexOf('def ensure_unpack_batch_for_receipt(', syncStart)
assert.ok(syncStart >= 0 && syncEnd > syncStart, 'Uitpakken synchronization function missing')
const syncBody = backend.slice(syncStart, syncEnd)
const existingBranch = syncBody.indexOf('if existing_line:')
const insertLookup = syncBody.indexOf('prior_processed = get_prior_processed_line_fact(')
const insertStatement = syncBody.indexOf('INSERT INTO purchase_import_lines (')
assert.ok(existingBranch >= 0 && insertLookup > existingBranch && insertStatement > insertLookup,
  'Prior processing lookup must occur only for newly imported lines')
assert.equal(syncBody.match(/prior_processed = get_prior_processed_line_fact\(/g)?.length, 1)

// List requests must not synchronize every existing receipt; detail requests still do.
const unpackStart = backend.indexOf('@app.get("/api/unpack-start-batches")')
const unpackEnd = backend.indexOf('@app.get("/api/receipts")', unpackStart)
const unpackList = backend.slice(unpackStart, unpackEnd)
assert.ok(unpackList.includes('batch_by_reference.get(receipt_reference)'))
assert.ok(unpackList.includes('if not batch_id:'))
assert.ok(unpackList.includes('batch_id = ensure_unpack_batch_for_receipt(conn, serialized)'))
assert.ok(!unpackList.includes('sync_unpack_batch_lines_for_receipt(conn,'))
const batchDetailStart = backend.indexOf('@app.get("/api/purchase-import-batches/{batch_id}")')
const batchDetail = backend.slice(batchDetailStart, batchDetailStart + 2400)
assert.ok(batchDetail.includes('sync_unpack_batch_lines_for_receipt(conn, batch_id, dict(receipt_header))'))

// Stale-while-revalidate contract for paginated UI: keep previously
// received rows visible until the next response has been committed.
const retainedRows = [
  ['../src/features/receipts/ReceiptsPage.jsx', 'listItems.length === 0 ?', 'aria-busy={isLoading}'],
  ['../src/features/receipts/KassaPage.jsx', 'listItems.length === 0 ?', 'pageInboxItems.map((item)'],
  ['../src/features/catalog/CatalogPage.jsx', 'items.length ? items.map((item)', 'DelayedTableLoadingOverlay'],
  ['../src/features/catalog/MobileCatalogPage.jsx', 'items.length > 0 ? (', 'aria-busy={isLoading}'],
  ['../src/features/platform/PlatformAuditPage.jsx', '!error && items.length > 0 ?', 'aria-busy={loading}'],
  ['../src/features/platform/PlatformLogsPage.jsx', '!error && items.length > 0 ?', 'aria-busy={loading}'],
  ['../src/features/platform/PlatformUsersPage.jsx', 'visibleItems.map((user)', 'setLoading(true)'],
  ['../src/features/platform/PlatformSessionsPage.jsx', 'visibleItems.map((session)', 'setLoading(true)'],
  ['../src/features/stores/StoresPage.jsx', 'batchItems.length === 0 ?', 'aria-busy={isLoading}'],
  ['../src/features/shopping/MobileShopping.jsx', '(list.items || []).length > 0 ?', 'aria-busy={loading}'],
  ['../src/features/kassa/MobileKassa.jsx', 'receiptsLoading && filteredReceipts.length === 0', 'aria-busy={receiptsLoading}'],
  ['../src/features/almostOut/MobileAlmostOut.jsx', 'filteredRows.length > 0 ?', 'aria-busy={isLoading}'],
  ['../src/pages/MobileVoorraad.jsx', 'filteredRows.length > 0 ?', 'aria-busy={isLoading}'],
  ['../src/features/almostOut/AlmostOutPage.jsx', 'filteredRows.length === 0 ?', 'visibleAlmostOutRows.map((row)'],
  ['../src/features/settings/SettingsArticleGroupsPage.jsx', 'filteredGroups.length === 0 ?', 'pageArticles.map((article)'],
  ['../src/features/settings/SettingsSpacesPage.jsx', 'filteredItems.length === 0 ?', 'pageItems.map((item)'],
  ['../src/features/settings/SettingsSublocationsPage.jsx', 'filteredItems.length === 0 ?', 'pageItems.map((item)'],
  ['../src/features/settings/SettingsAuthorizationPage.jsx', 'loading && overview.roles.length === 0', 'authorization-role-matrix'],
  ['../src/features/platform/PlatformIntegrationsPage.jsx', '!error ? visibleItems.map((item)', 'setLoading(true)'],
]
for (const [relative, renderGuard, loadingIndicator] of retainedRows) {
  const content = readFileSync(new URL(relative, import.meta.url), 'utf8')
  assert.ok(content.includes(renderGuard), `Rows not retained while fetching: ${relative}`)
  assert.ok(content.includes(loadingIndicator), `Loading feedback missing: ${relative}`)
}

// Coverage of nested detail lists and less frequently used management screens.
const longListSources = [
  ['../src/features/catalog/CatalogDetailPageV2.jsx', 'identityPagination.pageItems.map(', 'receiptPagination.pageItems.map('],
  ['../src/features/platform/PlatformAuthorizationsPage.jsx', 'visibleUsers.map(', 'pageCount > 1 ? <Pagination'],
  ['../src/features/platform/IpOwnerSuperusersPage.jsx', 'visibleUsers.map(', 'pageCount > 1 ? <Pagination'],
  ['../src/features/settings/SettingsMyHouseholdsPage.jsx', 'visibleHouseholds.map(', 'pageCount > 1 ? <Pagination'],
  ['../src/features/settings/SettingsHouseholdPage.jsx', 'visibleMembers.map(', 'visibleInvitations.map('],
]
for (const [relative, rows, pagination] of longListSources) {
  const source = readFileSync(new URL(relative, import.meta.url), 'utf8')
  assert.ok(source.includes(rows), `Missing paginated rows: ${relative}`)
  assert.ok(source.includes(pagination), `Missing paginator: ${relative}`)
}
const catalogDetail = readFileSync(new URL('../src/features/catalog/CatalogDetailPageV2.jsx', import.meta.url), 'utf8')
for (const pager of ['identityPagination', 'articlePagination', 'receiptPagination']) {
  assert.ok(catalogDetail.includes(`useMobilePagination(`))
  assert.ok(catalogDetail.includes(`<MobilePaginationControls {...${pager}}`))
  assert.ok(catalogDetail.includes(`page={${pager}.page}`))
}

// PR590 follow-up: central numeric pagination and first-screen UX.
const paginationUi = readFileSync(new URL('../src/ui/Pagination.jsx', import.meta.url), 'utf8')
assert.match(paginationUi, /\{currentPage\}/)
assert.doesNotMatch(paginationUi, /Pagina \{currentPage\} van \{totalPages\}/)
const loadingOverlay = readFileSync(new URL('../src/ui/DelayedTableLoadingOverlay.jsx', import.meta.url), 'utf8')
assert.doesNotMatch(loadingOverlay, /inhuis-loading-mark\.svg|table-loading-logo/)
const catalogPage = readFileSync(new URL('../src/features/catalog/CatalogPage.jsx', import.meta.url), 'utf8')
assert.match(catalogPage, /<Pagination page=\{currentPage\}/)
assert.doesNotMatch(catalogPage, />Eerste<|>Vorige<|>Volgende<|>Laatste</)
assert.match(catalogPage, /hasRequestedCatalogRef/)
const kassaPage = readFileSync(new URL('../src/features/receipts/KassaPage.jsx', import.meta.url), 'utf8')
assert.match(kassaPage, /height: '100%'/)
const shoppingPage = readFileSync(new URL('../src/features/shopping/ShoppingPage.jsx', import.meta.url), 'utf8')
assert.match(shoppingPage, /gridTemplateColumns: 'minmax\(0, 1fr\) auto', gap: 8, alignItems: 'end'/)
assert.doesNotMatch(shoppingPage, /paddingTop: '26px', alignSelf: 'start'/)
const almostOutPage = readFileSync(new URL('../src/features/almostOut/AlmostOutPage.jsx', import.meta.url), 'utf8')
const mobileAlmostOutPage = readFileSync(new URL('../src/features/almostOut/MobileAlmostOut.jsx', import.meta.url), 'utf8')
for (const [screen, source] of [['desktop', almostOutPage], ['mobiel', mobileAlmostOutPage]]) {
  assert.match(source, /toggleSelected|selectedIds/, screen)
  assert.match(source, /handleBulkAction\('export'\)/, screen)
  assert.match(source, /handleBulkAction\('hide'\)/, screen)
  assert.match(source, /handleBulkAction\('shopping'\)/, screen)
  assert.match(source, /handleBulkAction\('restore'\)/, screen)
}
const externalReceiptItems = readFileSync(new URL('../src/features/externalDatabases/ReceiptItemsOverview.jsx', import.meta.url), 'utf8')
assert.match(externalReceiptItems, /<Pagination page=\{currentPage\}/)
assert.doesNotMatch(externalReceiptItems, />Eerste<|>Vorige<|>Volgende<|>Laatste</)
const inventoryPage = readFileSync(new URL('../src/pages/Voorraad.jsx', import.meta.url), 'utf8')
assert.match(inventoryPage, /const inventoryPromise = fetchInventoryRows\(\)/)
assert.match(inventoryPage, /const articleOptionsPromise = fetchArticleGroupOptions\(\)/)

// Regression: catalog page reads never launch a full write/backfill of all
// products, and unavailable receipt previews must not render as blank panels.
const catalogRouteSource = readFileSync(new URL('../../backend/app/api/catalog_routes.py', import.meta.url), 'utf8')
const listCatalogBody = catalogRouteSource.split('def list_catalog(', 2)[1]?.split('\ndef ', 1)[0] || ''
assert.ok(listCatalogBody, 'Catalog list route missing')
assert.doesNotMatch(listCatalogBody, /ensure_dutch_gpc_assignments\(/)
assert.match(listCatalogBody, /LIMIT :limit OFFSET :offset/)
assert.match(kassaPage, /previewState\.error \|\| 'De originele kassabon kon niet worden geladen\.'/)
assert.match(kassaPage, /Van deze kassabon is geen ondersteund voorbeeld beschikbaar/)

const mobileCatalogSearch = readFileSync(new URL('../src/features/catalog/MobileCatalogPage.jsx', import.meta.url), 'utf8')
assert.match(mobileCatalogSearch, /params\.set\('search', query\.trim\(\)\)/)
assert.match(catalogRouteSource, /normalized_search =/)
assert.match(catalogRouteSource, /"gpc_brick_code", "gpc_brick_name"/)
const mobileInventoryPage = readFileSync(new URL('../src/pages/MobileVoorraad.jsx', import.meta.url), 'utf8')
assert.match(mobileInventoryPage, /groupPromise/)
assert.match(mobileInventoryPage, /setRows\(initialRows\)/)
const mobileHomePage = readFileSync(new URL('../src/features/home/MobileHomePage.jsx', import.meta.url), 'utf8')
assert.match(mobileHomePage, /huishoud-dashboard is alleen beschikbaar/)
assert.match(mobileHomePage, /pendingReceipts\.pending_downloads \?\? 0/)
// Bijna op: only a confirmed Shopping transfer may hide the source alert.
const almostOutBulk = readFileSync(new URL('../src/features/almostOut/almostOutBulk.js', import.meta.url), 'utf8')
const addToShopping = almostOutBulk.indexOf("await almostOutRequest('/api/shopping-list/items'")
const markTransferred = almostOutBulk.indexOf("await almostOutRequest('/api/households/' + id + '/almost-out/mark-in-shopping'")
assert.ok(addToShopping >= 0 && markTransferred > addToShopping, 'Do not hide Bijna op items before Shopping accepts them')
const backendMain = readFileSync(new URL('../../backend/app/main.py', import.meta.url), 'utf8')
assert.match(backendMain, /@app\.post\("\/api\/households\/\{household_id\}\/almost-out\/mark-in-shopping"\)/)
for (const [name, component, containerClose] of [
  ['desktop', almostOutPage, '</ScreenCard>'],
  ['mobile', mobileAlmostOutPage, '</main>'],
]) {
  const restoreButton = component.indexOf('>Verwijderingen ongedaan maken</Button>')
  const panelEnd = component.lastIndexOf(containerClose)
  assert.ok(restoreButton > panelEnd, `The undo action must be below the table panel on ${name}`)
  assert.ok(component.includes("action === 'shopping'"), `Refresh transferred rows on ${name}`)
  assert.ok(!component.includes('>Verborgen meldingen herstellen</Button>'), `Old undo label remains on ${name}`)
}

const voorraadFirstPage = readFileSync(new URL('../src/pages/Voorraad.jsx', import.meta.url), 'utf8')
assert.match(voorraadFirstPage, /const inventoryPromise = fetchInventoryRows\(\)/)
assert.match(voorraadFirstPage, /assignmentPromise\.then\(\(assignments\) =>/)
assert.doesNotMatch(voorraadFirstPage, /const inventoryPromise = Promise\.all\(\[/)

console.log('APP_WIDE_PAGINATION_CONTRACT_GREEN')
