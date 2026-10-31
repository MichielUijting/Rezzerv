import assert from 'node:assert/strict'
import fs from 'node:fs'
import path from 'node:path'
import { fileURLToPath } from 'node:url'

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..')
const ed2 = fs.readFileSync(path.join(root, 'src/features/externalDatabases/ExternalDatabases2Page.jsx'), 'utf8')

assert.match(ed2, /isPlatformSuperuser \? <Button/)
assert.match(ed2, /onClick=\{confirmDeleteSelected\}/)
assert.match(ed2, /'\/api\/external-databases\/articles\/delete-selected'/)
assert.match(ed2, /testId: 'ed2-delete-confirmation'/)
assert.match(ed2, /primaryActionLabel: 'Verwijderen'/)
assert.match(ed2, /secondaryActionLabel: 'Annuleren'/)
assert.match(ed2, /useAppFeedback/)
assert.match(ed2, /setRefreshVersion\(\(value\) => value \+ 1\)/)
assert.match(ed2, /status: 'success'|variant: 'success'/)
assert.match(ed2, /variant: 'error'/)
assert.doesNotMatch(ed2, /onClick=\{\(\) => setConfirmDelete/)
console.log('ED2 verwijderen: alleen Superuser, centrale bevestiging en foutfeedback OK')
