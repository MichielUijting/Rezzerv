import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'

const dataTable = readFileSync(new URL('../src/ui/DataTable.jsx', import.meta.url), 'utf8')
const productGroups = readFileSync(new URL('../src/features/productGroups/ProductGroupsPage.jsx', import.meta.url), 'utf8')

assert.match(dataTable, /pagination = true,/)
assert.match(dataTable, /pageSize = 10,/)
assert.match(dataTable, /pageCount > 1 \|\| paginationActions/)
assert.match(dataTable, /pageCount > 1 \? <Pagination/)
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

console.log('APP_WIDE_PAGINATION_CONTRACT_GREEN')
