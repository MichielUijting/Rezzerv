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
console.log('APP_WIDE_PAGINATION_CONTRACT_GREEN')
