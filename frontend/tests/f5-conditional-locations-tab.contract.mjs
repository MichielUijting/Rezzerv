import assert from 'node:assert/strict'
import { readFile } from 'node:fs/promises'

const articlePageUrl = new URL('../src/features/articles/ArticlePage.jsx', import.meta.url)
const source = await readFile(articlePageUrl, 'utf8')

assert.match(source, /TABS_WITH_LOCATIONS\s*=\s*\['Overzicht', 'Voorraad', 'Locaties', 'Historie', 'Analyse'\]/)
assert.match(source, /TABS_WITHOUT_LOCATIONS\s*=\s*\['Overzicht', 'Voorraad', 'Historie', 'Analyse'\]/)

assert.match(
  source,
  /product_configuration/,
  'ArticlePage moet de gezaghebbende product_configuration uit /api/onboarding gebruiken',
)
assert.match(
  source,
  /location_tracking_level/,
  'De zichtbaarheid van de Locaties-tab moet afhangen van location_tracking_level',
)
assert.doesNotMatch(
  source,
  /primaryUseCase\s*===\s*['"]waar_inhuis['"]\s*\?\s*TABS_WITH_LOCATIONS/,
  'primary_use_case mag de Locaties-tab niet meer autoriseren',
)
assert.match(
  source,
  /locationTrackingLevel\s*===\s*['"]none['"]\s*\?\s*TABS_WITHOUT_LOCATIONS\s*:\s*TABS_WITH_LOCATIONS/,
  'location_tracking_level=none moet de Locaties-tab fail-closed verbergen',
)
assert.match(
  source,
  /else if \(!tabs\.includes\(activeTab\)\)\s*\{\s*setActiveTab\(['"]Overzicht['"]\)/s,
  'Een reeds actieve Locaties-tab moet veilig terugvallen op Overzicht zodra locaties uitgaan',
)

console.log('PASS article_locations_tab_uses_product_configuration')
console.log('PASS location_tracking_none_hides_locations_tab')
console.log('PASS primary_use_case_no_longer_authorizes_locations_tab')
console.log('PASS stale_locations_tab_falls_back_to_overview')
console.log('F5_13_CONDITIONAL_LOCATIONS_TAB_GREEN')
