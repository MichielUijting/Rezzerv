import assert from 'node:assert/strict'
import fs from 'node:fs'
import { isEmptyTableCell, matchesTableFilter } from '../src/ui/dataTableFilter.js'

for (const value of [null, undefined, '', '   ', '\t', []]) {
  assert.equal(isEmptyTableCell(value), true)
  assert.equal(matchesTableFilter(value, '=leeg'), true)
  assert.equal(matchesTableFilter(value, '=nietleeg'), false)
}
for (const value of ['melk', '  melk  ', 0, false, ['melk'], '—']) {
  assert.equal(isEmptyTableCell(value), false)
  assert.equal(matchesTableFilter(value, '=leeg'), false)
  assert.equal(matchesTableFilter(value, '=nietleeg'), true)
}
assert.equal(matchesTableFilter('Halfvolle MELK', 'melk'), true)
assert.equal(matchesTableFilter('Halfvolle melk', 'kaas'), false)
assert.equal(matchesTableFilter('=leegte', '=leeg'), false)
assert.equal(matchesTableFilter('Kop =leeg', '=leeg '), false)
assert.equal(matchesTableFilter('Niet', ' =NIETLEEG '), true)
assert.equal(matchesTableFilter('melk', ''), true)

const src = fs.readFileSync(new URL('../src/ui/DataTable.jsx', import.meta.url), 'utf8')
assert.match(src, /matchesTableFilter\(rawValue, activeFilterValue\)/)
assert.match(src, /filterValue !== '=leeg' && filterValue !== '=nietleeg'/)
assert.match(src, /column\.getFilterValue\(row\)/)
assert.match(src, /column\.getValue\(row\)/)
assert.match(src, /defaultGetValue\(row, column\)/)
assert.match(src, /column\.filterPredicate\(row, activeFilterValue\)/)
// Artikelbeheer's Art./Barcode cell shows the confirmed code OR the manual
// barcode. The special filters must use exactly that same visible fallback.
const artikelbeheer = fs.readFileSync(new URL('../src/features/externalDatabases/ExternalDatabases2Page.jsx', import.meta.url), 'utf8')
assert.match(artikelbeheer, /getSortValue: \(row\) => row\.article_code \|\| row\.manual_barcode \|\| ''/)
assert.match(artikelbeheer, /getFilterValue: \(row\) => row\.article_code \|\| row\.manual_barcode \|\| ''/)
assert.match(artikelbeheer, /renderCell: \(row\) => row\.article_code \|\| \(row\.manual_barcode/)

const visibleBarcode = (row) => row.article_code || row.manual_barcode || ''
const manualBarcode = { article_code: '', manual_barcode: '2008218100008' }
const confirmedBarcode = { article_code: '8712345678906', manual_barcode: '' }
const noBarcode = { article_code: '', manual_barcode: '' }
assert.equal(matchesTableFilter(visibleBarcode(manualBarcode), '=leeg'), false)
assert.equal(matchesTableFilter(visibleBarcode(manualBarcode), '=nietleeg'), true)
assert.equal(matchesTableFilter(visibleBarcode(confirmedBarcode), '=leeg'), false)
assert.equal(matchesTableFilter(visibleBarcode(noBarcode), '=leeg'), true)
assert.equal(matchesTableFilter(visibleBarcode(noBarcode), '=nietleeg'), false)

console.log('DATA_TABLE_EMPTY_FILTER_CONTRACT_GREEN')
