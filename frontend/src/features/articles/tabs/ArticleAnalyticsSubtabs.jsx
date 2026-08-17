import { useEffect, useRef, useState } from 'react'
import Tabs from '../../../ui/Tabs'
import ArticleAnalyticsTab from './ArticleAnalyticsTab'

const ANALYSIS_SUBTABS = ['Trends', 'Prijs', 'Prognose', 'Onderbouwing']

const SECTION_TO_SUBTAB = {
  'Aankoop en verbruik in de tijd': 'Trends',
  Verbruiksbeeld: 'Trends',
  Prijsinzichten: 'Prijs',
  Voorraadprognose: 'Prognose',
  Aanbeveling: 'Prognose',
  Automatisering: 'Onderbouwing',
  Onderbouwing: 'Onderbouwing',
}

function applyAnalysisSubtab(root, activeSubtab) {
  const analysis = root?.querySelector('.rz-analytics-tab')
  if (!analysis) return

  const globalToggle = analysis.querySelector(':scope > .rz-article-global-toggle')
  if (globalToggle) globalToggle.hidden = true

  analysis.querySelectorAll('.rz-article-section-accordion').forEach((section) => {
    const title = section.querySelector('.rz-article-section-title')?.textContent?.trim() || ''
    const targetSubtab = SECTION_TO_SUBTAB[title] || 'Trends'
    const wrapper = section.parentElement?.matches('[data-testid^="analysis-row-"]') ? section.parentElement : section
    wrapper.hidden = targetSubtab !== activeSubtab
  })
}

export default function ArticleAnalyticsSubtabs(props) {
  const [activeSubtab, setActiveSubtab] = useState('Trends')
  const rootRef = useRef(null)

  useEffect(() => {
    const root = rootRef.current
    if (!root) return undefined

    const apply = () => applyAnalysisSubtab(root, activeSubtab)
    apply()

    const observer = new MutationObserver(apply)
    observer.observe(root, { childList: true, subtree: true })
    return () => observer.disconnect()
  }, [activeSubtab])

  return (
    <div ref={rootRef} className="rz-article-subtab-layout" data-testid="article-analysis-subtab-layout">
      <Tabs
        tabs={ANALYSIS_SUBTABS}
        activeTab={activeSubtab}
        onTabChange={setActiveSubtab}
        className="rz-article-subtabs"
        ariaLabel="Analyse subtabs"
        rootTestId="article-analysis-subtabs"
        tablistTestId="article-analysis-subtablist"
        tabTestIdMap={{
          Trends: 'article-analysis-subtab-trends',
          Prijs: 'article-analysis-subtab-price',
          Prognose: 'article-analysis-subtab-forecast',
          Onderbouwing: 'article-analysis-subtab-evidence',
        }}
      >
        {() => <ArticleAnalyticsTab {...props} />}
      </Tabs>
    </div>
  )
}
