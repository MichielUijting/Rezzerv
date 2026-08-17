import { useEffect, useRef, useState } from 'react'
import Tabs from '../../../ui/Tabs'
import { isHouseholdAdminFromContext, readStoredAuthContext } from '../../../lib/authSession'
import ArticleOverviewTab from './ArticleOverviewTab'

const OVERVIEW_SUBTABS = ['Artikel', 'Huishouden', 'Identiteit', 'Productdata']

const SECTION_TO_SUBTAB = {
  'Artikelgegevens voor dit huishouden': 'Artikel',
  Basis: 'Artikel',
  'Instellingen voor dit huishouden': 'Huishouden',
  Automatisering: 'Huishouden',
  Gebruiker: 'Huishouden',
  'Externe productkoppeling': 'Identiteit',
  Extern: 'Identiteit',
  Productverrijking: 'Productdata',
  'Voeding & verpakking': 'Productdata',
}

function applyOverviewSubtab(root, activeSubtab, readOnly) {
  const overview = root?.querySelector('.rz-overview-tab')
  if (!overview) return

  const globalToggle = overview.querySelector(':scope > .rz-article-global-toggle')
  if (globalToggle) globalToggle.hidden = true

  overview.querySelectorAll(':scope > section.rz-article-section-accordion').forEach((section) => {
    const title = section.querySelector('.rz-article-section-title')?.textContent?.trim() || ''
    const targetSubtab = SECTION_TO_SUBTAB[title] || 'Artikel'
    section.hidden = targetSubtab !== activeSubtab
  })

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
  const [activeSubtab, setActiveSubtab] = useState('Artikel')
  const rootRef = useRef(null)
  const canMutate = isHouseholdAdminFromContext(readStoredAuthContext() || {})
  const readOnly = !canMutate

  useEffect(() => {
    const root = rootRef.current
    if (!root) return undefined

    const apply = () => applyOverviewSubtab(root, activeSubtab, readOnly)
    apply()

    const observer = new MutationObserver(apply)
    observer.observe(root, { childList: true, subtree: true })
    return () => observer.disconnect()
  }, [activeSubtab, readOnly])

  return (
    <div ref={rootRef} className="rz-article-subtab-layout" data-testid="article-overview-subtab-layout" data-readonly={readOnly ? 'true' : 'false'}>
      <Tabs
        tabs={OVERVIEW_SUBTABS}
        activeTab={activeSubtab}
        onTabChange={setActiveSubtab}
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
          <>
            {readOnly ? <div className="rz-article-readonly-note" data-testid="article-detail-readonly-note">Alleen-lezen. Alleen een beheerder of eigenaar kan deze artikelgegevens wijzigen.</div> : null}
            <ArticleOverviewTab {...props} />
          </>
        )}
      </Tabs>
    </div>
  )
}
