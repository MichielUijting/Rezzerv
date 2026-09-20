import assert from 'node:assert/strict'
import fs from 'node:fs'
import path from 'node:path'
import { fileURLToPath } from 'node:url'

const here = path.dirname(fileURLToPath(import.meta.url))
const frontendRoot = path.resolve(here, '..')
const readFrontend = (relativePath) => fs.readFileSync(path.join(frontendRoot, relativePath), 'utf8')

const catalogSource = readFrontend('src/features/catalog/CatalogPage.jsx')
const catalogCss = readFrontend('src/features/catalog/catalog.css')
const tokensCss = readFrontend('src/ui/tokens.css')
const themeCss = readFrontend('src/ui/theme.css')

assert.match(catalogSource, /const PAGE_SIZE = 10/)
assert.match(catalogSource, /catalogKindLabel/)
assert.match(catalogSource, /'Exact product'/)
assert.match(catalogSource, /'Generiek'/)
assert.match(catalogSource, />Soort <span>/)
assert.match(catalogSource, /catalog_kind/)
assert.doesNotMatch(catalogSource, /updateSort\('source'\)/)
assert.doesNotMatch(catalogSource, /filters\.source/)
assert.match(catalogSource, /fillerRowCount = Math\.max\(0, PAGE_SIZE - occupiedBodyRows\)/)
assert.match(catalogSource, /data-testid="catalog-filler-row"/)
assert.match(catalogCss, /\.rz-catalog-col-kind\s*\{\s*width:/)
assert.match(catalogCss, /\.rz-catalog-filler-row\s*\{[\s\S]*pointer-events:\s*none/)
assert.match(tokensCss, /--color-ui-primary-text:\s*#FFFFFF/i)
assert.match(themeCss, /\.rz-header \.rz-header-title,[\s\S]*color:\s*var\(--color-ui-primary-text\)/)
assert.match(themeCss, /button\.rz-button-primary,[\s\S]*color:\s*var\(--color-ui-primary-text\)/)
assert.match(themeCss, /\.rz-table thead tr\.rz-table-header th,[\s\S]*color:\s*var\(--color-ui-primary-text\)/)

console.log('CATALOG_CLARITY_CONTRACT_GREEN')
