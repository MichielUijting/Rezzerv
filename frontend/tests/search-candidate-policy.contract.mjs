import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'

const policy = readFileSync(new URL('../src/ui/searchCandidatePolicy.js', import.meta.url), 'utf8')
const list = readFileSync(new URL('../src/ui/SearchCandidateList.jsx', import.meta.url), 'utf8')
const desktopShopping = readFileSync(new URL('../src/features/shopping/ShoppingPage.jsx', import.meta.url), 'utf8')
const mobileShopping = readFileSync(new URL('../src/features/shopping/MobileShopping.jsx', import.meta.url), 'utf8')
const inventory = readFileSync(new URL('../src/pages/Voorraad.jsx', import.meta.url), 'utf8')
const gpc = readFileSync(new URL('../src/features/catalog/CatalogGpcActionPage.jsx', import.meta.url), 'utf8')

assert.match(policy, /MAX_VISIBLE_SEARCH_CANDIDATES = 5/)
assert.match(list, /limitSearchCandidates\(items\)/)
assert.match(list, /role="listbox"/)
assert.match(list, /role="option"/)

for (const source of [desktopShopping, mobileShopping]) {
  assert.match(source, /SearchCandidateList/)
  assert.match(source, /shoppingSearchScopes\(searchMode\)/)
  assert.match(source, /catalog-search\?scope=\$\{scope\}&query=.*limit=5/)
  assert.match(source, /value=\{catalogQuery\}[\s\S]{0,120}disabled=\{saving\}/)
  assert.doesNotMatch(source, /Zoekresultaat/)
}

assert.match(inventory, /limitSearchCandidates\(filteredOptions\)/)
assert.match(gpc, /limitSearchCandidates/)
assert.match(gpc, /gpc\/bricks\?query=.*limit=5/)

// ED2 product candidates have their own bounded table and separate OFF search flow.
// The obsolete receipt overview does not participate in the global five-option search policy.
console.log('SEARCH_CANDIDATE_POLICY_CONTRACT_GREEN')
