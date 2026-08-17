import { useLayoutEffect, useRef, useState } from 'react'
import Tabs from '../../../ui/Tabs'
import { isHouseholdAdminFromContext, readStoredAuthContext } from '../../../lib/authSession'
import { ArticleIdentitySummary, ArticleProductSummary } from '../components/ArticleOverviewCuratedSummaries'
import ArticleOverviewTab from './ArticleOverviewTab'

const OVERVIEW_SUBTABS = ['Artikel', 'Huishouden', 'Identiteit', 'Productdata']
const OVERVIEW_SUBTAB_STORAGE_KEY = 'rezzerv.article-detail.overview-subtab'

const SUBTAB_KEY = {
  Artikel: 'article',
  Huishouden: 'household',
  Identiteit: 'identity',
  Productdata: 'productdata',
}

const SECTION_TO_KEY = {
  'Artikelgegevens voor dit huishouden': 'article',
  Basis: 'article',
  'Instellingen voor dit huishouden': 'household',
  Automatisering: 'household',
  Gebruiker: 'household',
  'Externe productkoppeling': 'legacy',
  Extern: 'legacy',
  Productverrijking: 'legacy',
  'Voeding & verpakking': 'legacy',
}

const CURATED_BASIS_DUPLICATE_LABELS = new Set([
  'Eigen naam:',
  'Categorie:',
  'Merk / maker / aanbieder:',
])

function readInitialSubtab() {
  if (typeof window === 'undefined') return 'Artikel'
  const stored = window.sessionStorage.getItem(OVERVIEW_SUBTAB_STORAGE_KEY)
  return OVERVIEW_SUBTABS.includes(stored) ? stored : 'Artikel'
}

function persistSubtab(value) {
  if (typeof window === 'undefined') return
  window.sessionStorage.setItem(OVERVIEW_SUBTAB_STORAGE_KEY, value)
}

function classifyOverviewSections(root, readOnly) {
  const overview = root?.querySelector('.rz-overview-tab')
  if (!overview) return

  overview.querySelectorAll(':scope > section.rz-article-section-accordion').forEach((section) => {
    const title = section.querySelector('.rz-article-section-title')?.textContent?.trim() || ''
    section.dataset.articleSubtab = SECTION_TO_KEY[title] || 'article'

    const summary = section.querySelector(':scope > .rz-article-section-header .rz-article-section-summary')
    if (summary?.getAttribute('aria-expanded') === 'false') summary.click()

    if (title === 'Basis') {
      section.querySelectorAll('.rz-field-row').forEach((row) => {
        const label = row.querySelector('.rz-field-row-label')?.textContent?.trim() || ''
        if (CURATED_BASIS_DUPLICATE_LABELS.has(label)) {
          row.dataset.curatedHidden = 'true'
        }
      })
    }
  })

  const householdNameInput = overview.querySelector('[data-testid="article-details-input-custom_name"]')
  const householdNameLabel = householdNameInput?.closest('.rz-field-row')?.querySelector('label')
  if (householdNameLabel) householdNameLabel.textContent = 'Naam in dit huishouden:'

  if (!readOnly) return

  overview.querySelectorAll('input, select, textarea').forEach((control) => {
    control.disabled = true
    control.setAttribute('aria-disabled', 'true')
  })
  overview.querySelectorAll('button:not(.rz-article-section-summary)').forEach((button) => {
    button.disabled = true
    button.setAttribute('aria-disabled', 'true')
  })
}

export default function ArticleOverviewSubtabs(props) {
  const [activeSubtab, setActiveSubtab] = useState(readInitialSubtab)
  const rootRef = useRef(null)
  const canMutate = isHouseholdAdminFromContext(readStoredAuthContext() || {})
  const readOnly = !canMutate
  const activeKey = SUBTAB_KEY[activeSubtab] || 'article'
  const articleData = props?.articleData

  useLayoutEffect(() => {
    classifyOverviewSections(rootRef.current, readOnly)
  }, [readOnly, articleData, activeSubtab])

  function handleSubtabChange(nextSubtab) {
    setActiveSubtab(nextSubtab)
    persistSubtab(nextSubtab)
  }

  return (
    <div
      ref={rootRef}
      className="rz-article-subtab-layout rz-article-overview-subtab-layout"
      data-testid="article-overview-subtab-layout"
      data-readonly={readOnly ? 'true' : 'false'}
      data-active-subtab={activeKey}
    >
      <Tabs
        tabs={OVERVIEW_SUBTABS}
        activeTab={activeSubtab}
        onTabChange={handleSubtabChange}
        className="rz-article-subtabs"
        ariaLabel="Overzicht subtabs"
        rootTestId="article-overview-subtabs"
        tablistTestId="article-overview-subtablist"
        tabTestIdMap={{
          Artikel: 'article-overview-subtab-article',
          Huishouden: 'article-overview-subtab-household',
          Identiteit: 'article-overview-subtab-identity',
          Productdata: 'article-overview-subtab-productdata',
        }}
      >
        {() => (
          <div
            className="rz-article-subtab-frame"
            data-testid={`article-overview-frame-${activeKey}`}
          >
            {readOnly ? <div className="rz-article-readonly-note" data-testid="article-detail-readonly-note">Alleen-lezen. Alleen een beheerder of eigenaar kan deze artikelgegevens wijzigen.</div> : null}
            {activeSubtab === 'Artikel' ? (
              <div className="rz-article-subtab-help" data-testid="article-household-name-help">
                Naam in dit huishouden is een optionele eigen benaming voor dit artikel. Laat het veld leeg om de gewone artikelnaam te gebruiken.
              </div>
            ) : null}
            {activeSubtab === 'Huishouden' ? (
              <div className="rz-article-subtab-help" data-testid="article-household-settings-help">
                Deze voorkeuren sturen voorraadniveaus, aanvuladvies, voorkeurswinkel, standaardopslag en verpakkingsgrootte voor dit huishouden.
              </div>
            ) : null}
            <ArticleOverviewTab {...props} />
            {activeSubtab === 'Identiteit' ? <ArticleIdentitySummary articleData={articleData} /> : null}
            {activeSubtab === 'Productdata' ? <ArticleProductSummary articleData={articleData} /> : null}
          </div>
        )}
      </Tabs>
    </div>
  )
}
