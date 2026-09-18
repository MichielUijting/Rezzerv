import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'

const selectSource = readFileSync(new URL('../src/ui/Select.jsx', import.meta.url), 'utf8')
const selectCss = readFileSync(new URL('../src/ui/components/select.css', import.meta.url), 'utf8')
const voorraadSource = readFileSync(new URL('../src/pages/MobileVoorraad.jsx', import.meta.url), 'utf8')
const almostOutSource = readFileSync(new URL('../src/features/almostOut/MobileAlmostOut.jsx', import.meta.url), 'utf8')
const articleSource = readFileSync(new URL('../src/features/articles/MobileArticlePage.jsx', import.meta.url), 'utf8')

assert.match(selectSource, /role="listbox"/)
assert.match(selectSource, /role="option"/)
assert.match(selectSource, /aria-haspopup="listbox"/)
assert.match(selectSource, /onKeyDown=\{handleKeyDown\}/)
assert.match(selectCss, /\.rz-select-trigger[\s\S]*font-size: var\(--font-size-ui-body\) !important;/)
assert.match(selectCss, /\.rz-select-listbox[\s\S]*font-size: var\(--font-size-ui-body\) !important;/)
assert.match(selectCss, /\.rz-select-option[\s\S]*font-size: var\(--font-size-ui-body\) !important;/)

for (const source of [voorraadSource, almostOutSource, articleSource]) {
  assert.match(source, /import Select from/)
  assert.doesNotMatch(source, /<select\b/)
}

assert.match(voorraadSource, /ariaLabelledby="mobile-inventory-sort-label"/)
assert.match(almostOutSource, /ariaLabelledby="mobile-almost-out-sort-label"/)
assert.match(articleSource, /dataTestId="mobile-article-location-select"/)

console.log('INHUIS_SELECT_CONTRACT_GREEN')
