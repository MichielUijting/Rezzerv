import assert from 'node:assert/strict'
import fs from 'node:fs'
import path from 'node:path'
import { fileURLToPath } from 'node:url'

const here = path.dirname(fileURLToPath(import.meta.url))
const frontendRoot = path.resolve(here, '..')

const read = (relativePath) => fs.readFileSync(path.join(frontendRoot, relativePath), 'utf8')

const page = read('src/features/catalog/CatalogPage.jsx')
const detail = read('src/features/catalog/CatalogDetailPageV2.jsx')
const image = read('src/features/catalog/CatalogProductImage.jsx')
const css = read('src/features/catalog/catalog.css')

assert.match(page, /CatalogProductImage/)
assert.match(page, /imageUrl=\{item\.image_url\}/)
assert.match(page, /compact/)
assert.match(detail, /imageUrl=\{product\.image_url\}/)
assert.match(image, /data-testid="catalog-product-image-fallback"/)
assert.match(image, /Geen foto/)
assert.match(image, /object-fit|onError=\{\(\) => setFailed\(true\)\}/)
assert.match(css, /\.rz-catalog-product-image--compact/)
assert.match(css, /object-fit:\s*contain/)
assert.match(css, /\.rz-catalog-product-summary/)

console.log('CATALOG_PRODUCT_IMAGE_CONTRACT_GREEN')
