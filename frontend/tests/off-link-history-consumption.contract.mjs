import assert from 'node:assert/strict'
import fs from 'node:fs'

const overview = fs.readFileSync(
  new URL('../src/features/externalDatabases/ExternalDatabases2Page.jsx', import.meta.url),
  'utf8',
)
const manualSearch = fs.readFileSync(
  new URL('../src/features/externalDatabases/OffManualSearchPage.jsx', import.meta.url),
  'utf8',
)

const arrival = overview.split('const result = location.state?.offLinkOutcome')[1]
  ?.split('\n  }, [location.key, location.state?.offLinkOutcome])')[0]
assert.ok(arrival, 'OFF-koppelresultaat moet bij aankomst in het artikeloverzicht worden verwerkt')
assert.match(arrival, /setOffLinkOutcome\(result\)/, 'Resultaat blijft als eenmalige melding zichtbaar')
assert.match(arrival, /delete nextState\.offLinkOutcome/, 'Verbruikte melding moet uit browsergeschiedenis verdwijnen')
assert.match(arrival, /replace: true/, 'Geschiedenis mag geen extra navigatiestap krijgen')
assert.match(arrival, /state: nextState/, 'Tabel- en filterstatus moeten behouden blijven')
assert.match(manualSearch, /replace: linkOutcome !== null/, 'Terugkeer na een koppeling vervangt de OFF-zoekpagina')

console.log('OFF terugnavigatie: eenmalige koppelmelding zonder geschiedenisreplay OK')
