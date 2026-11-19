import assert from 'node:assert/strict'
import fs from 'node:fs'
const read = (path) => fs.readFileSync(new URL('../' + path, import.meta.url), 'utf8')
const source = read('src/features/articleSynonyms/SynonymAnalysisPage.jsx')
const router = read('src/app/router/AppRouter.jsx')
const synonyms = read('src/features/articleSynonyms/ArticleSynonymsPage.jsx')
const mobile = read('src/features/catalog/MobileCatalogPage.jsx')
const desktop = read('src/features/catalog/CatalogPage.jsx')
assert.match(router, /ProtectedFrontteam><SynonymAnalysisPage/)
assert.match(source, /synonym-analysis-items/)
assert.match(source, /synonym-analysis-candidate-table/)
assert.match(source, /synonym-count-/)
assert.match(source, /aria-pressed=\{bucket === key\}/)
assert.match(source, /setBucket\(\(current\) => current === value \? '' : value\)/)
assert.match(source, /onDoubleClick=\{\(\) => saveCandidate\(pair\)\}/)
assert.match(source, /Merk kandidaat aan als synoniem/)
assert.match(source, /\.slice\(0, 5\)/)
assert.match(source, /await refreshAnalysis\(\)/)
assert.match(source, /synonym_count/)
assert.match(source, /wrapperClassName="rz-synonym-analysis-table-wrapper"/)
assert.doesNotMatch(source, /rz-synonym-analysis-filters/)
assert.doesNotMatch(source, /<Select/)
assert.doesNotMatch(source, />Sluiten<\/Button>/)
assert.match(source, /renderRow=\{\(item\) => \(/)
assert.match(source, /onDoubleClick=\{\(\) => setSelectedId\(item.id\)\}/)
assert.match(source, /<span>\{item.name\}<\/span>/)
assert.doesNotMatch(source, /className="rz-button-secondary"/)
assert.doesNotMatch(source, /Bekijk hoeveel bevestigde synoniemen/)
assert.doesNotMatch(source, /Geselecteerd: \{productName\(selectedProduct\)\}/)
assert.doesNotMatch(source, /Een synoniem is één rechtstreeks bevestigd/)
assert.match(synonyms, /searchParams.get\('artikel'\)/)
// The legacy deep link stays functional, but Catalogus no longer duplicates
// the management buttons on desktop or mobile.
assert.doesNotMatch(mobile, /Synoniemenanalyse|Artikelclassificaties toekennen/)
assert.doesNotMatch(desktop, /Synoniemenanalyse|Artikelclassificaties toekennen/)
for (const marker of [
  'SYNONYM_BUCKETS', 'article-synonym-count-summary',
  'article-synonym-count-', 'synonymCounts', 'toggleSynonymBucket',
  "synonymBucket === '3+'", 'data={visibleArticles.map(',
]) assert.ok(synonyms.includes(marker), 'Artikelbeheer Synoniemen teller/filter: ' + marker)
assert.match(synonyms, /setSynonymBucket\(\(current\) => current === bucket \? '' : bucket\)/)
console.log('SYNONYM_ANALYSIS_CONTRACT_GREEN')
