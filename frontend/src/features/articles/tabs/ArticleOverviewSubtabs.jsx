import { useLayoutEffect, useRef, useState } from 'react'
import Tabs from '../../../ui/Tabs'
import { isHouseholdAdminFromContext, readStoredAuthContext } from '../../../lib/authSession'
import ArticleOverviewTab from './ArticleOverviewTab'

const OVERVIEW_SUBTABS = ['Artikel', 'Huishouden', 'Identiteit', 'Productdata']

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
  'Externe productkoppeling': 'identity',
  Extern: 'identity',
  Productverrijking: 'productdata',
  'Voeding & verpakking': 'productdata',
}

function classifyOverviewSections(root, readOnly) {
  const overview = root?.querySelector('.rz-overview-tab')
  if (!overview) return

  overview.querySelectorAll(':scope > section.rz-article-section-accordion').forEach((section) => {
    const title = section.querySelector('.rz-article-section-title')?.textContent?.trim() || ''
    const targetKey = SECTION_TO_KEY[title] || 'article'
    if (section.dataset.articleSubtab !== targetKey) {
      section.dataset.articleSubtab = targetKey
    }
  })

  if (!readOnly) return

  overview.querySelectorAll('input, select, textarea').forEach((control) => {
    if (!control.disabled) control.disabled = true
    if (control.getAttribute('aria-disabled') !== 'true') control.setAttribute('aria-disabled', 'true')
  })
  overview.querySelectorAll('button:not(.rz-article-section-summary)').forEach((button) => {
    if (!button.disabled) button.disabled = true
    if (button.getAttribute('aria-disabled') !== 'true') button.setAttribute('aria-disabled', 'true')
  })
}

export default function ArticleOverviewSubtabs(props) {
  const [activeSubtab, setActiveSubtab] = useState('Artikel')
  const rootRef = useRef(null)
  const canMutate = isHouseholdAdminFromContext(readStoredAuthContext() || {})
  const readOnly = !canMutate
  const activeKey = SUBTAB_KEY[activeSubtab] || 'article'

  useLayoutEffect(() => {
    const root = rootRef.current
    if (!root) return undefined

    const classify = () => classifyOverviewSections(root, readOnly)
    classify()

    const observer = new MutationObserver(classify)
    observer.observe(root, { childList: true, subtree: true })
    return () => observer.disconnect()
  }, [readOnly])

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
