import assert from 'node:assert/strict'
import fs from 'node:fs'
import path from 'node:path'
import { fileURLToPath } from 'node:url'

const frontend = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..')
const src = path.join(frontend, 'src')
const read = (p) => fs.readFileSync(path.join(frontend, p), 'utf8')

for (const filename of [
  'ExternalDatabasesPage.jsx', 'ReceiptItemsOverview.jsx',
  'RecognitionConfirmationDetail.jsx', 'externalDatabasesRecovery.css',
]) {
  assert.equal(fs.existsSync(path.join(src, 'features/externalDatabases', filename)), false,
    `Oude Externe databases code mag niet bestaan: ${filename}`)
}

const router = read('src/app/router/AppRouter.jsx')
assert.doesNotMatch(router, /ExternalDatabasesPage/)
assert.doesNotMatch(router, /path:\s*['"]\/externe-databases['"]/)
assert.match(router, /path:\s*['"]\/externe-databases-2['"]/)
assert.match(router, /OffManualSearchPage/)
const navigation = read('src/features/home/homeNavigation.js')
assert.ok(!navigation.includes("key: 'externe-databases',"))
assert.ok(navigation.includes("key: 'externe-databases-2',"))
const home = read('src/features/home/HomePage.jsx')
assert.ok(!home.includes("'externe-databases': '/externe-databases'"))
assert.ok(home.includes("'externe-databases-2': '/externe-databases-2'"))
const chrome = read('src/app/MobileAppChrome.jsx')
assert.ok(!chrome.includes("['/externe-databases',"))
assert.ok(chrome.includes("['/externe-databases-2',"))

const flags = read('../backend/app/services/platform_feature_flag_service.py')
assert.ok(!flags.includes('ACTION_HOME_EXTERNE_DATABASES ='))
assert.ok(!flags.includes('_home_action("Externe databases", "externe-databases")'))
assert.ok(flags.includes('ACTION_HOME_EXTERNE_DATABASES_2'))

const ed2 = read('src/features/externalDatabases/ExternalDatabases2Page.jsx')
for(const marker of ['articles-overview', 'off/unlink-selected', 'OffCandidatePanel', 'Ed2GpcClassificationPanel'])
  assert.ok(ed2.includes(marker), `Vereiste ED2-functie verdwenen: ${marker}`)

console.log('GREEN: oude Externe databases pagina, menu, actie en componenten verwijderd; ED2 aanwezig')
