import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'

const page = readFileSync(new URL('../src/pages/Voorraad.jsx', import.meta.url), 'utf8')
const endpoint = readFileSync(new URL('../../backend/app/api/inventory_desktop_pagination_routes.py', import.meta.url), 'utf8')
const router = readFileSync(new URL('../../backend/app/api/router.py', import.meta.url), 'utf8')

// The first screen must not block on the legacy full-stock/GPC projection.
assert.match(page, /fetchDesktopInventoryPage\(paginationPage\)/)
assert.match(page, /\/api\/voorraad\/desktop-page\?/)
assert.match(page, /page_size: '10'/)
assert.doesNotMatch(page, /const inventoryPromise = fetchInventoryRows\(\)/)
assert.match(page, /setServerTotal\(total\)/)
assert.match(page, /serverPaged \? serverTotal : filteredRows\.length/)
assert.match(page, /fetchDesktopPageClassifications\(sourceRows\)/)
assert.match(page, /setServerLoading\(false\)/)
assert.match(page, /const \[firstPageSettled, setFirstPageSettled\] = useState\(false\)/)
assert.match(page, /if \(!firstPageSettled\) return undefined/)
assert.match(page, /setFirstPageSettled\(true\)/)
assert.match(page, /\[firstPageSettled, showFeedback\]/)

// Sorting and filtering by Brick, family, quantity and location still require
// global rows rather than accidentally filtering just the visible ten.
assert.match(page, /const needsFullInventory =/)
assert.match(page, /if \(!serverPaged \|\| !needsFullInventory\) return undefined/)
assert.match(page, /fetchInventoryRows\(\)/)
assert.match(page, /setServerPaged\(false\)/)
assert.match(page, /handleFilterChange\("brick", e\.target\.value\)/)
assert.match(page, /handleFilterChange\("productfamilie", e\.target\.value\)/)
assert.match(page, /reloadInventoryRows = async/)

// The SQL pages before loading the physical positions. Count and both queries
// must remain scoped to the authenticated household, with positive stock.
assert.match(endpoint, /@router\.get\("\/api\/voorraad\/desktop-page"\)/)
assert.match(endpoint, /@router\.post\("\/api\/voorraad\/desktop-page-classifications"\)/)
assert.match(endpoint, /require_household_context\(authorization\)/)
assert.match(endpoint, /active_household_id/)
assert.match(endpoint, /i\.household_id = :household_id/)
assert.match(endpoint, /COALESCE\(i\.aantal, 0\) > 0/)
assert.match(endpoint, /GROUP BY \{_DESKTOP_GROUP_KEY\}/)
assert.match(endpoint, /LIMIT :page_size OFFSET :offset/)
assert.match(endpoint, /bindparam\("group_keys", expanding=True\)/)
assert.match(endpoint, /dutch_gpc_by_household_article\(conn, household_id, ids\)/)
assert.match(router, /include_router\(inventory_desktop_pagination_router\)/)

console.log('DESKTOP_VOORRAAD_FIRST_PAGE_CONTRACT_GREEN')
