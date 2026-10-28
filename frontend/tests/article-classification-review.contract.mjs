import assert from 'node:assert/strict'
import fs from 'node:fs'
import path from 'node:path'
import { fileURLToPath } from 'node:url'

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..')
const read = (filename) => fs.readFileSync(path.join(root, filename), 'utf8')

const page = read('src/features/catalog/ShopifyReviewPage.jsx')
const catalog = read('src/features/catalog/CatalogPage.jsx')
const mobile = read('src/features/catalog/MobileCatalogPage.jsx')
const detail = read('src/features/catalog/CatalogDetailPageV2.jsx')
const router = read('src/app/router/AppRouter.jsx')

assert.match(page, /AppShell title="Artikelclassificaties toekennen"/)
assert.match(page, /<h2>Artikelclassificaties toekennen<\/h2>/)
assert.match(page, /Via OFF kun je suggesties opvragen voor de artikelclassificatie\./)
assert.match(page, /<DataTable .*columns=\{columns\}/)
assert.match(page, /pageSize=\{8\}/)
assert.match(page, /key: 'select', label: '', width: 48/)
assert.match(page, /key: 'proposal'.*label: 'Voorgestelde artikelclassificatie'/)
assert.match(page, /onClick=\{fetchProposals\}/)
assert.match(page, /onClick=\{confirmProposals\}/)
assert.match(page, /disabled=\{busy \|\| !allHaveProposals\}/)
assert.match(page, /shopify_id: proposals\[item\.id\]\.shopify_id/)
assert.match(page, /barcode_confirmed: true/)
assert.match(page, /BATCH_SIZE = 100/)
assert.match(page, /OFF_INTERVAL_MS = 6200/)
assert.doesNotMatch(page, /categorySearch|searchCategories|Vorige 100|Volgende 100|Selecteer categorie|Haal OFF-voorstel op/)
assert.match(router, /path: '\/catalogus\/artikelclassificaties-toekennen'/)
assert.match(catalog, /Artikelclassificaties toekennen/)
assert.match(mobile, /Artikelclassificaties toekennen/)
assert.match(catalog, /catalog-article-classification-/)
assert.match(mobile, /Artikelclassificatie: \{text\(item\.article_classification/)
assert.match(detail, /Artikelclassificatie<\/dt>/)

console.log('ARTICLE_CLASSIFICATION_REVIEW_CONTRACT_GREEN')
