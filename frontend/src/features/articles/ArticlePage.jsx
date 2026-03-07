import { Link, useParams } from 'react-router-dom'
import { useMemo } from 'react'
import AppShell from '../../app/AppShell'
import Card from '../../ui/Card'
import Tabs from '../../ui/Tabs'
import demoData from '../../demo-articles.json'
import { useArticleFieldVisibility } from './hooks/useArticleFieldVisibility'
import ArticleOverviewTab from './tabs/ArticleOverviewTab'

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
    return {
      ...article,
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
          <div style={{ display: 'flex', justifyContent: 'space-between', gap: '12px', alignItems: 'center', flexWrap: 'wrap' }}>
            <Link to="/voorraad" style={{ color: '#2e7d4d', textDecoration: 'none', fontWeight: 600 }}>← Voorraad</Link>
            {visibilityError ? <div style={{ color: '#9c4221', fontSize: '14px' }}>Standaardweergave actief.</div> : null}
          </div>
          {visibilityLoading ? <div>Gegevens laden…</div> : (
            <Tabs tabs={TABS} defaultTab="Overzicht">
              {(tab) => {
                if (tab === 'Overzicht') return <ArticleOverviewTab articleData={articleData} visibilityMap={visibilityMap} />
                if (tab === 'Voorraad') return <PlaceholderTab text="Voorraad-tab volgt in de volgende stap." />
                if (tab === 'Locaties') return <PlaceholderTab text="Locaties-tab volgt in de volgende stap." />
                if (tab === 'Historie') return <PlaceholderTab text="Historie-tab volgt in de volgende stap." />
                return <PlaceholderTab text="Analyse-tab volgt in de volgende stap." />
              }}
            </Tabs>
          )}
        </div>
      </Card>
    </AppShell>
  )
}
