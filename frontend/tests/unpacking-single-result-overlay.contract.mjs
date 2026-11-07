import assert from 'node:assert/strict'
import fs from 'node:fs'

const detail = fs.readFileSync(
  new URL('../src/features/stores/StoreBatchDetailPage.jsx', import.meta.url),
  'utf8',
)
const feedback = fs.readFileSync(
  new URL('../src/ui/AppFeedbackProvider.jsx', import.meta.url),
  'utf8',
)

assert.doesNotMatch(detail, /processResultOverlay|setProcessResultOverlay/, 'Verwijder de tweede, zelfgebouwde verwerkingsoverlay')
assert.doesNotMatch(detail, /showProcessFeedback\('Verwerkt!'\)/, 'Geen tweede succesmelding voor dezelfde actie')
assert.match(detail, /title: unresolved === 0 \? 'Verwerking afgerond' : 'Geselecteerde artikelen verwerkt'/)
assert.match(detail, /dismissMode: 'ok-only'/, 'Resultaat blijft zichtbaar tot gebruiker het sluit')
assert.match(detail, /Nog \$\{unresolved\} bonregel\(s\) niet verwerkt/, 'Gedeeltelijke verwerking mag geen voltooiing melden')
assert.match(feedback, /const interactiveDialog = !mobileTransient \|\| variant === 'error'/,
  'Centrale desktopmelding moet een dekkende achtergrond hebben')

console.log('Uitpakken single-result-overlay contract: OK')
