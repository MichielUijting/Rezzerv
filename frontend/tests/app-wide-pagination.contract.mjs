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
console.log('APP_WIDE_PAGINATION_CONTRACT_GREEN')
