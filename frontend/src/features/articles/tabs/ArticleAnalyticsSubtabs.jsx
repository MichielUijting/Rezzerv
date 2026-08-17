import { useState } from 'react'
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

function readInitialSubtab() {
  if (typeof window === 'undefined') return 'Trends'
  const stored = window.sessionStorage.getItem(ANALYSIS_SUBTAB_STORAGE_KEY)
  return ANALYSIS_SUBTABS.includes(stored) ? stored : 'Trends'
}

function persistSubtab(value) {
  if (typeof window === 'undefined') return
  window.sessionStorage.setItem(ANALYSIS_SUBTAB_STORAGE_KEY, value)
}

export default function ArticleAnalyticsSubtabs(props) {
  const [activeSubtab, setActiveSubtab] = useState(readInitialSubtab)
  const activeKey = SUBTAB_KEY[activeSubtab] || 'trends'

  function handleSubtabChange(nextSubtab) {
    setActiveSubtab(nextSubtab)
    persistSubtab(nextSubtab)
  }

  return (
    <div
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
