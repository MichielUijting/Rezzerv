import { useParams } from 'react-router-dom'
import { useMemo } from 'react'
import AppShell from '../../app/AppShell'
import Card from '../../ui/Card'
import Tabs from '../../ui/Tabs'
import demoData from '../../demo-articles.json'
import { useArticleFieldVisibility } from './hooks/useArticleFieldVisibility'
import ArticleOverviewTab from './tabs/ArticleOverviewTab'
import ArticleStockTab from './tabs/ArticleStockTab'
import ArticleLocationsTab from './tabs/ArticleLocationsTab'
import ArticleHistoryTab from './tabs/ArticleHistoryTab'
import ArticleAnalyticsTab from './tabs/ArticleAnalyticsTab'
import { applyAutoRepurchaseHistory } from './lib/autoRepurchaseHistory'

const TABS = ['Overzicht', 'Voorraad', 'Locaties', 'Historie', 'Analyse']

function PlaceholderTab({ text }) {
  return <div style={{ color: '#667085' }}>{text}</div>
}

export default function ArticlePage() {
  const { articleId } = useParams()
  const { visibilityMap, isLoading: visibilityLoading, error: visibilityError } = useArticleFieldVisibility()
  const articleData = useMemo(() => {
    const article = demoData.articles.find((a) => String(a.id) === String(articleId)) || demoData.articles[0]
    const firstLocation = article.locations?.[0] || {}
    const totalQuantity = (article.locations || []).reduce((sum, entry) => sum + (Number(entry.aantal) || 0), 0)
    const history = applyAutoRepurchaseHistory(article)
    return {
      ...article,
      history,
      article_type: article.type,
      size_value: article.weight,
      notes: article.notes || '',
      calories: article.calories ?? '',
      fat_total: article.fat_total ?? '',
      emballage: article.emballage ?? false,
      emballage_amount: article.emballage_amount ?? '',
      total_quantity: totalQuantity,
      main_location: firstLocation.locatie || '',
      sub_location: firstLocation.sublocatie || '',
    }
  }, [articleId])

  const pageTitle = `Artikel details: ${articleData.name || 'Onbekend artikel'}`

  return (
    <AppShell title={pageTitle} showExit={false}>
      <Card className="rz-card-home">
        <div style={{ display: 'grid', gap: '18px', width: '100%' }}>
          {visibilityError ? <div className="rz-inline-feedback rz-inline-feedback--warning">Standaardweergave actief.</div> : null}
          {visibilityLoading ? <div>Gegevens laden…</div> : (
            <Tabs tabs={TABS} defaultTab="Overzicht">
              {(tab) => {
                if (tab === 'Overzicht') return <ArticleOverviewTab articleData={articleData} visibilityMap={visibilityMap} />
                if (tab === 'Voorraad') return <ArticleStockTab articleData={articleData} />
                if (tab === 'Locaties') return <ArticleLocationsTab articleData={articleData} />
                if (tab === 'Historie') return <ArticleHistoryTab articleData={articleData} />
                if (tab === 'Analyse') return <ArticleAnalyticsTab articleData={articleData} />
                return <PlaceholderTab text="Onbekende tab." />
              }}
            </Tabs>
          )}
        </div>
      </Card>
    </AppShell>
  )
}
