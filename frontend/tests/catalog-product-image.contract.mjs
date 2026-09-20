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
const sharedThumbnail = read('src/ui/CatalogArticleThumbnail.jsx')
const sharedThumbnailCss = read('src/ui/catalogArticleThumbnail.css')
const inventory = read('src/pages/Voorraad.jsx')
const almostOut = read('src/features/almostOut/AlmostOutPage.jsx')
const shopping = read('src/features/shopping/ShoppingPage.jsx')

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

assert.match(sharedThumbnail, /onError=\{\(\) => setFailed\(true\)\}/)
assert.match(sharedThumbnail, /referrerPolicy="no-referrer"/)
assert.match(sharedThumbnail, /catalog-article-thumbnail-empty/)
assert.match(sharedThumbnailCss, /width:\s*52px/)
assert.match(sharedThumbnailCss, /object-fit:\s*contain/)
assert.match(inventory, /CatalogArticleThumbnail/)
assert.match(almostOut, /CatalogArticleThumbnail/)
assert.match(shopping, /CatalogArticleThumbnail/)
assert.match(inventory, /imageUrl=\{row\?\.imageUrl\}/)
assert.match(almostOut, /imageUrl=\{row\.imageUrl\}/)
assert.match(shopping, /imageUrl=\{item\.image_url\}/)

console.log('CATALOG_PRODUCT_IMAGE_CONTRACT_GREEN')
