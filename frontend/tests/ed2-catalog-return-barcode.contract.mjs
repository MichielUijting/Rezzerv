import assert from 'node:assert/strict'
import fs from 'node:fs'
import path from 'node:path'
import { fileURLToPath } from 'node:url'
import { manualBarcodeKey } from '../src/features/externalDatabases/ed2ManualBarcodeIdentity.js'

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..')
const read = (file) => fs.readFileSync(path.join(root, file), 'utf8')

assert.equal(manualBarcodeKey('albert_heijn', 'Mélk  1 L', ' 00012 '),
  manualBarcodeKey('albert-heijn', 'melk 1 l', '00012'))
assert.notEqual(manualBarcodeKey('ah', 'melk', '12'), manualBarcodeKey('jumbo', 'melk', '12'))
assert.notEqual(manualBarcodeKey('jumbo', 'melk', '12'), manualBarcodeKey('jumbo', 'melk', '13'))

const catalog = read('src/features/catalog/CatalogPage.jsx')
const mobile = read('src/features/catalog/MobileCatalogPage.jsx')
const detail = read('src/features/catalog/CatalogDetailPageV2.jsx')
const ed2 = read('src/features/externalDatabases/ExternalDatabases2Page.jsx')
const manual = read('src/features/externalDatabases/Ed2ManualBarcodeEntry.jsx')
const search = read('src/features/externalDatabases/OffManualSearchPage.jsx')
const table = read('src/ui/DataTable.jsx')

for (const text of [catalog, mobile, ed2]) {
  assert.match(text, /replace: true/)
  assert.match(text, /location\.state/)
}
assert.match(catalog, /catalogTableState/)
assert.match(mobile, /mobileCatalogTableState/)
assert.match(detail, /returnToCatalog/)
assert.match(ed2, /ed2TableState/)
assert.match(ed2, /pageState=\{tablePage\}/)
assert.match(ed2, /sortState=\{tableSort\}/)
assert.match(ed2, /manual_barcode/)
assert.doesNotMatch(ed2, /manualBarcodeKey/)
assert.doesNotMatch(ed2, /\/api\/catalog\/ed2\/manual-barcodes/)
assert.ok(ed2.includes("label: 'Art./Barcode'"))
assert.doesNotMatch(ed2, /label: 'Ingevoerde barcode'/)
assert.match(table, /pageReady/)
assert.match(table, /onPageChange/)
assert.match(search, /ed2TableState: state\.ed2TableState/)
assert.match(manual, /ed2-manual-barcode-save/)
assert.match(manual, /\/api\/catalog\/ed2\/manual-barcodes/)
assert.match(manual, /payload\.off_found/)
assert.match(manual, /payload\.photo_loaded/)
assert.match(manual, /payload\.off_unavailable/)
assert.match(manual, /useAppFeedback/)
assert.match(manual, /showFeedback\(\{/)
assert.match(manual, /testId: 'ed2-manual-barcode-error'/)
assert.match(manual, /variant: 'error'/)
assert.doesNotMatch(manual, /setError\(/)
assert.doesNotMatch(manual, /\{error \? <p role="alert"/)

console.log('ED2/Catalogus behoud tabelpositie en barcode-afbakening OK')
