import assert from 'node:assert/strict'
import fs from 'node:fs'
import path from 'node:path'
import { fileURLToPath } from 'node:url'

const here = path.dirname(fileURLToPath(import.meta.url))
const root = path.resolve(here, '..')
const source = fs.readFileSync(
  path.join(root, 'src', 'features', 'externalDatabases', 'ExternalDatabasesPage.jsx'),
  'utf8',
)

assert.match(source, /Product zoeken op barcode/)
assert.match(source, /\/api\/external-databases\/gtin\/lookup/)
assert.match(source, /Barcode \/ GTIN/)
assert.match(source, /gtinLookupResult\.product\?\.product_name/)
assert.match(source, /gtinLookupResult\.matched_source/)
assert.match(source, /Deze zoekactie wijzigt de Catalogus niet/)

console.log('external-databases-gtin-source contract passed')
