import { useLayoutEffect, useRef, useState } from 'react'
import Tabs from '../../../ui/Tabs'
import ArticleAnalyticsTab from './ArticleAnalyticsTab'

const ANALYSIS_SUBTABS = ['Trends', 'Prijs', 'Prognose', 'Onderbouwing']
const ANALYSIS_SUBTAB_STORAGE_KEY = 'rezzerv.article-detail.analysis-subtab'

const SUBTAB_KEY = {
  Trends: 'trends',
  Prijs: 'price',
  Prognose: 'forecast',
  Onderbouwing: 'evidence',
}

const SECTION_TO_KEY = {
  'Aankoop en verbruik in de tijd': 'trends',
  Verbruiksbeeld: 'trends',
  Prijsinzichten: 'price',
  Voorraadprognose: 'forecast',
  Aanbeveling: 'forecast',
  Automatisering: 'evidence',
  Onderbouwing: 'evidence',
}

function readInitialSubtab() {
  if (typeof window === 'undefined') return 'Trends'
  const stored = window.sessionStorage.getItem(ANALYSIS_SUBTAB_STORAGE_KEY)
  return ANALYSIS_SUBTABS.includes(stored) ? stored : 'Trends'
}

function persistSubtab(value) {
  if (typeof window === 'undefined') return
  window.sessionStorage.setItem(ANALYSIS_SUBTAB_STORAGE_KEY, value)
}

function classifyAnalysisSections(root) {
  const analysis = root?.querySelector('.rz-analytics-tab')
  if (!analysis) return

  analysis.querySelectorAll('.rz-article-section-accordion').forEach((section) => {
    const title = section.querySelector('.rz-article-section-title')?.textContent?.trim() || ''
    const targetKey = SECTION_TO_KEY[title] || 'trends'
    const wrapper = section.parentElement?.matches('[data-testid^="analysis-row-"]') ? section.parentElement : section
    wrapper.dataset.analysisSubtab = targetKey
  })
}

export default function ArticleAnalyticsSubtabs(props) {
  const [activeSubtab, setActiveSubtab] = useState(readInitialSubtab)
  const rootRef = useRef(null)
  const activeKey = SUBTAB_KEY[activeSubtab] || 'trends'
  const articleData = props?.articleData
  const automationVersion = props?.automationVersion

  useLayoutEffect(() => {
    classifyAnalysisSections(rootRef.current)
  }, [articleData, automationVersion])

  function handleSubtabChange(nextSubtab) {
    setActiveSubtab(nextSubtab)
    persistSubtab(nextSubtab)
  }

  return (
    <div
      ref={rootRef}
      className="rz-article-subtab-layout rz-article-analysis-subtab-layout"
      data-testid="article-analysis-subtab-layout"
      data-active-subtab={activeKey}
    >
      <Tabs
        tabs={ANALYSIS_SUBTABS}
        activeTab={activeSubtab}
        onTabChange={handleSubtabChange}
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
