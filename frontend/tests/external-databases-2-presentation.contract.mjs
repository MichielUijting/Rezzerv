import assert from 'node:assert/strict'
import {
  displayRecognition,
  displayRetailerEvidenceMessage,
  displaySource,
} from '../src/features/externalDatabases/offCandidatePresentation.js'

assert.equal(displaySource('Open Food Facts'), 'OFF')
assert.equal(displaySource('Jumbo + Open Food Facts'), 'Jumbo + OFF')
assert.equal(displaySource('Albert Heijn + Open Food Facts'), 'Albert Heijn + OFF')
assert.equal(displaySource('Lidl'), 'Lidl')

assert.equal(displayRecognition('Suggestie op artikelnaam'), 'Alleen op artikelnaam')
assert.equal(displayRecognition('Winkelproduct; suggestie op naam'), 'Winkelproduct; alleen op naam')
assert.equal(displayRecognition('Artikelnummer en barcode bevestigd'), 'Artikelnummer en barcode bevestigd')

const jumboEvidence = {
  source: 'Jumbo', status: 'name_suggestions',
  message: 'Producten gevonden bij Jumbo. De koppeling met het bonartikel is alleen op naam; controleer de suggesties.',
}
assert.equal(displayRetailerEvidenceMessage(jumboEvidence), '')
assert.equal(displayRetailerEvidenceMessage({ ...jumboEvidence,
  message: `${jumboEvidence.message} OFF is tijdelijk niet bereikbaar; de winkelresultaten blijven beschikbaar.`,
}), 'OFF is tijdelijk niet bereikbaar; de winkelresultaten blijven beschikbaar.')
assert.equal(displayRetailerEvidenceMessage({ ...jumboEvidence, source: 'Albert Heijn' }), jumboEvidence.message)
assert.equal(displayRetailerEvidenceMessage(null), '')

console.log('Externe databases 2: weergaveteksten en bronwaarschuwingen OK')
