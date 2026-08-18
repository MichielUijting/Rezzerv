import { readFileSync } from 'node:fs'

const overview = readFileSync(new URL('../src/features/articles/tabs/ArticleOverviewSubtabs.jsx', import.meta.url), 'utf8')
const analysis = readFileSync(new URL('../src/features/articles/tabs/ArticleAnalyticsSubtabs.jsx', import.meta.url), 'utf8')
const policy = readFileSync(new URL('../src/features/articles/articleDetailMutationPolicy.css', import.meta.url), 'utf8')

function expectIncludes(source, needle, label) {
  if (!source.includes(needle)) {
    throw new Error(`${label}: ontbreekt: ${needle}`)
  }
}

function expectNotIncludes(source, needle, label) {
  if (source.includes(needle)) {
    throw new Error(`${label}: onverwacht aanwezig: ${needle}`)
  }
}

expectIncludes(overview, 'className="rz-article-subtab-frame"', 'Overzicht heeft geen enkel subtabframe')
expectIncludes(overview, 'article-overview-frame-${activeKey}', 'Overzichtframe heeft geen stabiele testidentiteit')
expectIncludes(overview, '.rz-article-section-summary', 'Overzicht houdt legacy-secties niet expliciet open')
expectIncludes(overview, 'summary.click()', 'Overzicht forceert legacy-secties niet open')

expectIncludes(analysis, 'className="rz-article-subtab-frame"', 'Analyse heeft geen enkel subtabframe')
expectIncludes(analysis, 'article-analysis-frame-${activeKey}', 'Analyseframe heeft geen stabiele testidentiteit')
expectIncludes(analysis, '.rz-article-section-summary[aria-expanded="false"]', 'Analyse houdt legacy-secties niet expliciet open')
expectIncludes(analysis, 'summary.click()', 'Analyse forceert legacy-secties niet open')

expectIncludes(policy, '.rz-article-subtab-frame .rz-article-global-toggle', 'Globale in-/uitklapbediening wordt niet verwijderd')
expectIncludes(policy, '.rz-article-subtab-frame .rz-article-section-header', 'Interne framekoppen worden niet verwijderd')
expectIncludes(policy, '.rz-article-subtab-frame .rz-article-section-accordion', 'Legacy accordionframes worden niet afgevlakt')
expectIncludes(policy, '.rz-article-subtab-frame .rz-article-automation-card', 'Automatiseringsframe wordt niet afgevlakt')
expectIncludes(policy, 'display: none !important;', 'Verborgen accordionbediening heeft geen harde UI-regel')
expectIncludes(policy, 'border: 0 !important;', 'Interne frames houden nog eigen randen')
expectIncludes(policy, 'box-shadow: none !important;', 'Interne frames houden nog eigen schaduw')

expectNotIncludes(policy, '.rz-article-subtab-frame .rz-article-section-summary::before', 'Een +/- pseudo-element wordt opnieuw toegevoegd')
expectNotIncludes(policy, '.rz-article-subtab-frame .rz-article-section-summary::after', 'Een +/- pseudo-element wordt opnieuw toegevoegd')

console.log('ARTICLE_DETAIL_FLAT_SUBTABS_CONTRACT_GREEN')
