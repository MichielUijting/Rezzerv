import fs from 'node:fs'
import path from 'node:path'
import { fileURLToPath } from 'node:url'

const here = path.dirname(fileURLToPath(import.meta.url))
const root = path.resolve(here, '..')

const authSession = fs.readFileSync(path.join(root, 'src/lib/authSession.js'), 'utf8')
const dayHandling = fs.readFileSync(path.join(root, 'src/features/receipts/dayArticleHandling.js'), 'utf8')

function requireSource(condition, message) {
  if (!condition) throw new Error(message)
}

requireSource(
  authSession.includes("const REFERENCE_READ_CACHE_TTL_MS = 60_000"),
  'Locatie-referentiereads moeten een begrensde cache hebben.',
)
requireSource(
  authSession.includes("['/api/spaces', '/api/sublocations'].includes(normalizedUrl)"),
  'Alleen stabiele locatie-referentielijsten mogen via deze read-cache lopen.',
)
requireSource(
  authSession.includes("const householdId = String(currentSessionContext?.active_household_id || '').trim()")
    && authSession.includes('return householdId ? `${normalizedUrl}::${householdId}` :'),
  'Locatiecache moet expliciet aan het actieve huishouden zijn gebonden.',
)
requireSource(
  authSession.includes('if (previousHouseholdId !== nextHouseholdId) referenceReadCache.clear()'),
  'Een huishoudwissel moet de locatiecache direct wissen.',
)
requireSource(
  authSession.includes('if (changesLocations) referenceReadCache.clear()'),
  'Locatiecache moet bij locatie-/sublocatiemutaties fail-safe worden geïnvalideerd.',
)
requireSource(
  authSession.includes('return cached.response.clone()'),
  'Gecachete responses moeten clonebaar blijven voor bestaande response-consumers.',
)

requireSource(
  dayHandling.includes('const articleHandlingCache = new Map()')
    && dayHandling.includes('const lineOverrideCache = new Map()'),
  'Dagartikeldefaults en regeloverrides moeten los worden gecachet.',
)
requireSource(
  dayHandling.includes('missingArticleIds') && dayHandling.includes('missingLineIds'),
  'Batchreads mogen alleen ontbrekende handling-waarden opnieuw ophalen.',
)
requireSource(
  dayHandling.includes('writeHandlingCache(lineOverrideCache, cacheKey(normalizedHouseholdId, normalizedLineId), normalizedOverride)'),
  'Een opgeslagen regeloverride moet direct de lokale cache bijwerken.',
)

console.log('UITPAKKEN_PERFORMANCE_HOT_PATH_CONTRACT_GREEN')
