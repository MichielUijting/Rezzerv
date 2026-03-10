import { useParams, useSearchParams } from 'react-router-dom'
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

function mapLiveHistoryRows(rows = []) {
  return rows.map((row) => ({
    id: row?.id || '',
    datetime: row?.created_at || '',
    type: row?.event_type === 'purchase' ? 'Aankoop' : (row?.event_type || 'Gebeurtenis'),
    old_value: '—',
    new_value: row?.quantity != null ? `+${row.quantity}` : '—',
    location: row?.location_label || '',
    source: row?.source || '',
    note: row?.note || '',
    quantity_change: Number(row?.quantity) || 0,
  }))
}

async function fetchArticleHistory(articleName) {
  const response = await fetch(`/api/dev/article-history?article_name=${encodeURIComponent(articleName)}`)
  if (!response.ok) throw new Error('Live artikelhistorie kon niet worden geladen')
  const data = await response.json()
  return Array.isArray(data?.rows) ? data.rows : []
}

function buildLiveOnlyArticle(articleName, liveRows) {
  const normalizedTarget = normalizeName(articleName)
  const matchingRows = Array.isArray(liveRows) ? liveRows.filter((row) => normalizeName(row?.artikel) === normalizedTarget) : []
  const liveLocations = matchingRows.map((row) => ({
    locatie: row?.locatie || '',
    sublocatie: row?.sublocatie || '',
    aantal: Number(row?.aantal) || 0,
  }))
  const firstLocation = liveLocations[0] || {}
  const totalQuantity = liveLocations.reduce((sum, entry) => sum + (Number(entry.aantal) || 0), 0)
  return {
    id: `live-${normalizedTarget || 'unknown'}`,
    name: articleName || 'Onbekend artikel',
    type: '',
    article_type: '',
    weight: '',
    size_value: '',
    notes: '',
    calories: '',
    fat_total: '',
    emballage: false,
    emballage_amount: '',
    history: [],
    locations: liveLocations,
    total_quantity: totalQuantity,
    main_location: firstLocation.locatie || '',
    sub_location: firstLocation.sublocatie || '',
  }
}

export default function ArticlePage() {
  const { articleId } = useParams()
  const [searchParams] = useSearchParams()
  const { visibilityMap, isLoading: visibilityLoading, error: visibilityError } = useArticleFieldVisibility()
  const [automationVersion, setAutomationVersion] = useState(0)
  const [liveInventoryRows, setLiveInventoryRows] = useState([])
  const [liveHistoryRows, setLiveHistoryRows] = useState([])
  const [inventoryLoadError, setInventoryLoadError] = useState('')
  const [historyLoadError, setHistoryLoadError] = useState('')

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

  const requestedArticleName = useMemo(() => searchParams.get('artikel') || '', [searchParams])

  const activeArticle = useMemo(() => {
    const directMatch = demoData.articles.find((a) => String(a.id) === String(articleId))
    if (directMatch) return directMatch

    if (requestedArticleName) {
      const nameMatch = demoData.articles.find((a) => normalizeName(a.name) === normalizeName(requestedArticleName))
      if (nameMatch) return nameMatch
      return buildLiveOnlyArticle(requestedArticleName, liveInventoryRows)
    }

    const liveRowMatch = Array.isArray(liveInventoryRows)
      ? liveInventoryRows.find((row) => String(row?.id) === String(articleId))
      : null
    if (liveRowMatch?.artikel) {
      const nameMatch = demoData.articles.find((a) => normalizeName(a.name) === normalizeName(liveRowMatch.artikel))
      if (nameMatch) return nameMatch
      return buildLiveOnlyArticle(liveRowMatch.artikel, liveInventoryRows)
    }

    return demoData.articles[0]
  }, [articleId, requestedArticleName, liveInventoryRows])

  useEffect(() => {
    let cancelled = false
    setInventoryLoadError('')
    setHistoryLoadError('')

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

    fetchArticleHistory(activeArticle?.name || '')
      .then((rows) => {
        if (!cancelled) {
          setLiveHistoryRows(rows)
        }
      })
      .catch(() => {
        if (!cancelled) {
          setLiveHistoryRows([])
          setHistoryLoadError('Live artikelhistorie kon niet worden geladen. Demo-historie wordt getoond.')
        }
      })

    return () => {
      cancelled = true
    }
  }, [articleId, activeArticle?.name])

  const articleData = useMemo(() => {
    const merged = mergeLiveLocations(activeArticle, liveInventoryRows)
    const liveHistory = mapLiveHistoryRows(liveHistoryRows)
    return liveHistory.length ? { ...merged, history: liveHistory } : merged
  }, [activeArticle, automationVersion, liveInventoryRows, liveHistoryRows])

  const pageTitle = `Artikel details: ${articleData.name || 'Onbekend artikel'}`

  return (
    <AppShell title={pageTitle} showExit={false}>
      <Card className="rz-card-home">
        <div style={{ display: 'grid', gap: '18px', width: '100%' }}>
          {visibilityError ? <div className="rz-inline-feedback rz-inline-feedback--warning">Standaardweergave actief.</div> : null}
          {inventoryLoadError ? <div className="rz-inline-feedback rz-inline-feedback--warning">{inventoryLoadError}</div> : null}
          {historyLoadError ? <div className="rz-inline-feedback rz-inline-feedback--warning">{historyLoadError}</div> : null}
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
