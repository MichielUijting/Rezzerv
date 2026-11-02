import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { gs1ProductTypeLabel } from '../src/features/catalog/gs1ProductTypeLabel.js'

const src = (relative) => readFileSync(new URL(relative, import.meta.url), 'utf8')
const desktop = src('../src/features/catalog/CatalogPage.jsx')
const mobile = src('../src/features/catalog/MobileCatalogPage.jsx')
const detail = src('../src/features/catalog/CatalogDetailPageV2.jsx')
const css = src('../src/features/catalog/catalog.css')

assert.equal(gs1ProductTypeLabel({ gpc_brick_code: '10000167', gpc_brick_name: 'Kaas — Smeerbaar' }), 'Kaas — Smeerbaar')
assert.equal(gs1ProductTypeLabel({ gpc_brick_code: '', gpc_brick_name: '' }), 'Niet geclassificeerd')
assert.equal(gs1ProductTypeLabel({ gpc_brick_code: '10000167' }), 'Omschrijving ontbreekt')
assert.equal(gs1ProductTypeLabel(null), 'Niet geclassificeerd')
assert.equal(desktop.split('>GS1-producttype <span>').length - 1, 1)
assert.equal(desktop.split('rz-catalog-col-gs1-type').length - 1, 1)
assert.match(desktop, /gs1ProductType: 'gpc_brick_name'/)
assert.match(desktop, /updateSort\('gpc_brick_name'\)/)
assert.match(desktop, /aria-label="Filter GS1-producttype"/)
assert.equal(desktop.split('colSpan="10"').length - 1, 2)
assert.match(desktop, /gs1ProductTypeLabel\(item\)/)
assert.match(desktop, /delete previous\[key\]/)
for (const legacy of ['gpcBrickCode', 'gpcBrickName', 'gpcClass', 'gpcFamily']) {
  assert.doesNotMatch(desktop, new RegExp('filters\\.' + legacy))
}
assert.doesNotMatch(desktop, />Brick-code <span>|>Brick-naam <span>|>GPC-groep <span>|>Productfamilie <span>/)
assert.match(desktop, /item\.gpc_brick_code,\s*item\.gpc_brick_name,\s*item\.gpc_class_name,\s*item\.gpc_family_name/)
assert.match(mobile, /GS1-producttype: \{gs1ProductTypeLabel\(item\)\}/)
assert.doesNotMatch(mobile, /<span>Brick-code:|<span>Brick-naam:|<span>GPC-groep:|<span>Productfamilie:/)
assert.match(css, /\.rz-catalog-col-gs1-type\s*\{\s*width:/)
for (const label of ['Brick-code', 'Brick-naam', 'GPC-groep', 'Productfamilie']) {
  assert.equal(detail.split('<dt>' + label + '</dt>').length - 1, 2)
}
console.log('CATALOG_GS1_SUMMARY_DETAIL_EXPORT_GREEN')
