import assert from 'node:assert/strict'
import fs from 'node:fs'

const frontend = fs.readFileSync(
  new URL('../src/features/stores/StoreBatchDetailPage.jsx', import.meta.url), 'utf8',
)
const backend = fs.readFileSync(
  new URL('../../backend/app/main.py', import.meta.url), 'utf8',
)

assert.match(frontend, /const selectedIds = \[\.\.\.new Set\(selectedLineIds\.map\(String\)\)\]/,
  'A bulk operation must freeze the user checkbox selection before refresh')
assert.match(frontend, /selected_line_ids: selectedIds\.map\(String\)/,
  'The browser must send the explicit checked line IDs')
assert.match(backend, /selected_line_ids: Optional\[List\[str\]\] = None/,
  'The API must support explicit selection without breaking legacy non-browser clients')
assert.match(backend, /if not explicit_line_ids\.issubset\(batch_line_ids\):/,
  'A request must not process a line belonging to another receipt')
assert.match(backend, /and \(explicit_line_ids is None or str\(line\["id"\]\) in explicit_line_ids\)/,
  'Only explicitly checked and approved receipt lines may be processed')
assert.match(backend, /Niet alle opgegeven bonregels zijn geselecteerd/,
  'The API must reject an explicit selection that was not approved')
assert.doesNotMatch(frontend, /review_decision: 'ignored'/,
  'Unchecked lines must never be silently marked ignored')

console.log('Uitpakken checkbox -> voorraad: exact-selection contract OK')
