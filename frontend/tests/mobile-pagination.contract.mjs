import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'

const pagination = readFileSync(new URL('../src/ui/MobilePagination.jsx', import.meta.url), 'utf8')
const centralPagination = readFileSync(new URL('../src/ui/Pagination.jsx', import.meta.url), 'utf8')
const dataTable = readFileSync(new URL('../src/ui/DataTable.jsx', import.meta.url), 'utf8')
const inventory = readFileSync(new URL('../src/pages/MobileVoorraad.jsx', import.meta.url), 'utf8')
const catalog = readFileSync(new URL('../src/features/catalog/MobileCatalogPage.jsx', import.meta.url), 'utf8')
const almostOut = readFileSync(new URL('../src/features/almostOut/MobileAlmostOut.jsx', import.meta.url), 'utf8')
const shopping = readFileSync(new URL('../src/features/shopping/MobileShopping.jsx', import.meta.url), 'utf8')
const kassa = readFileSync(new URL('../src/features/kassa/MobileKassa.jsx', import.meta.url), 'utf8')
const support = readFileSync(new URL('../src/features/support/MobileSupportInbox.jsx', import.meta.url), 'utf8')
const receipts = readFileSync(new URL('../src/features/receipts/ReceiptsPage.jsx', import.meta.url), 'utf8')
const storeBatch = readFileSync(new URL('../src/features/stores/StoreBatchDetailPage.jsx', import.meta.url), 'utf8')
const mobileCss = readFileSync(new URL('../src/ui/mobileComponents.css', import.meta.url), 'utf8')

assert.match(pagination, /export const MOBILE_PAGE_SIZE = 10/)
assert.match(pagination, /slice\(start, start \+ MOBILE_PAGE_SIZE\)/)
assert.match(pagination, /<Pagination[\s\S]*page=\{page\}[\s\S]*pageCount=\{pageCount\}/)
assert.match(pagination, /<Pagination page=\{page\} pageCount=\{pageCount\} onPageChange=\{setPage\} \/>/)
assert.match(centralPagination, /first: labels\?\.first \?\? '1'/)
assert.match(centralPagination, /previous: labels\?\.previous \?\? '−'/)
assert.match(centralPagination, /next: labels\?\.next \?\? '\+'/)
assert.match(centralPagination, /last: labels\?\.last \?\? \(Number\.isFinite/)

assert.match(dataTable, /const effectivePagination = Boolean\(pagination \|\| isMobileViewport\)/)
assert.match(dataTable, /pageSize = 10/)

for (const [name, source] of [
  ['Voorraad', inventory],
  ['Bijna op', almostOut],
  ['Boodschappen', shopping],
  ['Meldingen', support],
  ['Uitpakken', receipts],
]) {
  assert.match(source, /useMobilePagination\(/, name + ' moet mobiele paginering gebruiken')
  assert.match(source, /MobilePaginationControls/, name + ' moet de centrale pagineringscomponent tonen')
}

assert.match(catalog, /const PAGE_SIZE = 10/)
assert.match(catalog, /<Pagination page=\{currentPage\} pageCount=\{pageCount\}/)

assert.match(kassa, /const receiptPagination = useMobilePagination\(filteredReceipts/)
assert.match(kassa, /const linePagination = useMobilePagination\(activeLines/)
assert.match(kassa, /const summaryPagination = useMobilePagination\(lines/)
assert.match(kassa, /Paginering Bonnen/)
assert.match(kassa, /Paginering Bonregels/)

assert.match(storeBatch, /const mobileLinePagination = useMobilePagination\(/)
assert.match(storeBatch, /const renderedLineUiStates = isMobileViewport \? mobileLinePagination\.pageItems : visibleLineUiStates/)
assert.match(storeBatch, /Paginering Bonregels Uitpakken/)

assert.match(mobileCss, /\.rz-mobile-action-bar-icon\s*\{[\s\S]*width:\s*44px;[\s\S]*height:\s*44px;/)
assert.match(mobileCss, /\.rz-mobile-action-bar-icon svg\s*\{[\s\S]*width:\s*44px;[\s\S]*height:\s*44px;/)
assert.match(mobileCss, /\.rz-mobile-action-bar-desktop-icon\s*\{[\s\S]*transform:\s*scale\(2\);/)

console.log('MOBILE_PAGINATION_CONTRACT_GREEN')
