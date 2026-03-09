import { useParams } from 'react-router-dom'
import { useEffect, useMemo, useState } from 'react'
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

function normalizeName(value) {
  return String(value || '').trim().toLowerCase()
}

function buildFallbackArticle(article) {
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
}

function mergeLiveLocations(baseArticle, liveRows) {
  const fallbackArticle = buildFallbackArticle(baseArticle)
  if (!Array.isArray(liveRows) || !liveRows.length) return fallbackArticle

  const nameKey = normalizeName(baseArticle?.name)
  const matchingRows = liveRows.filter((row) => normalizeName(row?.artikel) === nameKey)
  if (!matchingRows.length) return fallbackArticle

  const liveLocations = matchingRows.map((row) => ({
    locatie: row?.locatie || '',
    sublocatie: row?.sublocatie || '',
    aantal: Number(row?.aantal) || 0,
  }))

  const firstLocation = liveLocations[0] || {}
  const totalQuantity = liveLocations.reduce((sum, entry) => sum + (Number(entry.aantal) || 0), 0)

  return {
    ...fallbackArticle,
    locations: liveLocations,
    total_quantity: totalQuantity,
    main_location: firstLocation.locatie || '',
    sub_location: firstLocation.sublocatie || '',
  }
}

async function fetchInventoryPreview() {
  const response = await fetch('/api/dev/inventory-preview')
  if (!response.ok) throw new Error('Live artikelvoorraad kon niet worden geladen')
  const data = await response.json()
  return Array.isArray(data?.rows) ? data.rows : []
}

export default function ArticlePage() {
  const { articleId } = useParams()
  const { visibilityMap, isLoading: visibilityLoading, error: visibilityError } = useArticleFieldVisibility()
  const [automationVersion, setAutomationVersion] = useState(0)
  const [liveInventoryRows, setLiveInventoryRows] = useState([])
  const [inventoryLoadError, setInventoryLoadError] = useState('')

  useEffect(() => {
    function handleAutomationChange() {
      setAutomationVersion((value) => value + 1)
    }

    window.addEventListener('rezzerv-household-automation-updated', handleAutomationChange)
    window.addEventListener('rezzerv-article-auto-consume-overrides-updated', handleAutomationChange)

    return () => {
      window.removeEventListener('rezzerv-household-automation-updated', handleAutomationChange)
      window.removeEventListener('rezzerv-article-auto-consume-overrides-updated', handleAutomationChange)
    }
  }, [])

  useEffect(() => {
    let cancelled = false
    setInventoryLoadError('')

    fetchInventoryPreview()
      .then((rows) => {
        if (!cancelled) {
          setLiveInventoryRows(rows)
        }
      })
      .catch(() => {
        if (!cancelled) {
          setLiveInventoryRows([])
          setInventoryLoadError('Live artikelvoorraad kon niet worden geladen. Demo-locaties worden getoond.')
        }
      })

    return () => {
      cancelled = true
    }
  }, [articleId])

  const articleData = useMemo(() => {
    const article = demoData.articles.find((a) => String(a.id) === String(articleId)) || demoData.articles[0]
    return mergeLiveLocations(article, liveInventoryRows)
  }, [articleId, automationVersion, liveInventoryRows])

  const pageTitle = `Artikel details: ${articleData.name || 'Onbekend artikel'}`

  return (
    <AppShell title={pageTitle} showExit={false}>
      <Card className="rz-card-home">
        <div style={{ display: 'grid', gap: '18px', width: '100%' }}>
          {visibilityError ? <div className="rz-inline-feedback rz-inline-feedback--warning">Standaardweergave actief.</div> : null}
          {inventoryLoadError ? <div className="rz-inline-feedback rz-inline-feedback--warning">{inventoryLoadError}</div> : null}
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
