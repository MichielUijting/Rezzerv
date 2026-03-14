import { useParams, useSearchParams } from 'react-router-dom'
import { useEffect, useMemo, useState } from 'react'
import AppShell from '../../app/AppShell'
import ScreenCard from '../../ui/ScreenCard'
import Tabs from '../../ui/Tabs'
import demoData from '../../demo-articles.json'
import { useArticleFieldVisibility } from './hooks/useArticleFieldVisibility'
import ArticleOverviewTab from './tabs/ArticleOverviewTab'
import ArticleStockTab from './tabs/ArticleStockTab'
import ArticleLocationsTab from './tabs/ArticleLocationsTab'
import ArticleHistoryTab from './tabs/ArticleHistoryTab'
import ArticleAnalyticsTab from './tabs/ArticleAnalyticsTab'

const TABS = ['Overzicht', 'Voorraad', 'Locaties', 'Historie', 'Analyse']

function PlaceholderTab({ text }) {
  return <div style={{ color: '#667085' }}>{text}</div>
}

function normalizeName(value) {
  return String(value || '').trim().toLowerCase()
}

function buildFallbackArticle(article) {
  const safeArticle = article || {}
  const firstLocation = safeArticle.locations?.[0] || {}
  const totalQuantity = (safeArticle.locations || []).reduce((sum, entry) => sum + (Number(entry.aantal) || 0), 0)
  const history = Array.isArray(safeArticle.history) ? safeArticle.history : []
  return {
    ...safeArticle,
    history,
    article_type: safeArticle.article_type || safeArticle.type || '',
    size_value: safeArticle.size_value || safeArticle.weight || '',
    notes: safeArticle.notes || '',
    calories: safeArticle.calories ?? '',
    fat_total: safeArticle.fat_total ?? '',
    emballage: safeArticle.emballage ?? false,
    emballage_amount: safeArticle.emballage_amount ?? '',
    total_quantity: totalQuantity,
    main_location: firstLocation.locatie || '',
    sub_location: firstLocation.sublocatie || '',
  }
}

function mergeLiveLocations(baseArticle, liveRows) {
  const fallbackArticle = buildFallbackArticle(baseArticle)
  if (!Array.isArray(liveRows) || !liveRows.length) return fallbackArticle

  const articleName = fallbackArticle?.name || ''
  const nameKey = normalizeName(articleName)
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
    name: articleName || fallbackArticle.name,
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

function mapEventTypeLabel(eventType) {
  if (eventType === 'purchase') return 'Aankoop'
  if (eventType === 'manual_adjustment') return 'Handmatige voorraadcorrectie'
  if (eventType === 'auto_repurchase') return 'Automatisch (herhaalaankoop)'
  return eventType || 'Gebeurtenis'
}

function formatQuantityDelta(value) {
  if (value == null || value === '') return '—'
  const number = Number(value)
  if (!Number.isFinite(number)) return String(value)
  if (number > 0) return `+${number}`
  return String(number)
}

function mapLiveHistoryRows(rows = []) {
  return rows.map((row) => {
    const usesInventoryDelta = ['manual_adjustment', 'purchase', 'auto_repurchase'].includes(row?.event_type)
    return {
      id: row?.id || '',
      datetime: row?.created_at || '',
      type: mapEventTypeLabel(row?.event_type),
      old_value: usesInventoryDelta ? String(row?.old_quantity ?? '—') : '—',
      new_value: usesInventoryDelta ? String(row?.new_quantity ?? '—') : formatQuantityDelta(row?.quantity),
      location: row?.location_label || '',
      source: row?.source || '',
      note: row?.note || '',
      quantity_change: Number(row?.quantity) || 0,
      event_type: row?.event_type || '',
      old_quantity: row?.old_quantity,
      new_quantity: row?.new_quantity,
    }
  })
}

async function fetchArticleHistory(articleName) {
  const response = await fetch(`/api/dev/article-history?article_name=${encodeURIComponent(articleName)}`)
  if (!response.ok) throw new Error('Live artikelhistorie kon niet worden geladen')
  const data = await response.json()
  return Array.isArray(data?.rows) ? data.rows : []
}

function buildLiveOnlyArticle(articleName, liveRows, articleId = '') {
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
    id: articleId || `live-${normalizedTarget || 'unknown'}`,
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

function buildLiveFirstArticle(articleName, liveRows, fallbackArticle = null, articleId = '') {
  const liveArticle = buildLiveOnlyArticle(articleName, liveRows, articleId)
  if (!fallbackArticle) return liveArticle

  const fallback = buildFallbackArticle(fallbackArticle)
  return {
    ...fallback,
    id: fallback.id || liveArticle.id,
    name: liveArticle.name || fallback.name,
    locations: liveArticle.locations,
    total_quantity: liveArticle.total_quantity,
    main_location: liveArticle.main_location,
    sub_location: liveArticle.sub_location,
  }
}

function hasLiveInventoryRowsForArticle(articleName, liveRows) {
  const normalizedTarget = normalizeName(articleName)
  if (!normalizedTarget) return false
  return Array.isArray(liveRows) && liveRows.some((row) => normalizeName(row?.artikel) === normalizedTarget)
}

function buildArticleResolution({ articleId, requestedArticleName, liveInventoryRows }) {
  const trimmedArticleId = String(articleId || '').trim()
  const trimmedRequestedName = String(requestedArticleName || '').trim()
  const liveRows = Array.isArray(liveInventoryRows) ? liveInventoryRows : []

  const liveRowById = trimmedArticleId ? liveRows.find((row) => String(row?.id) === trimmedArticleId) : null
  const preferredName = trimmedRequestedName || liveRowById?.artikel || ''
  const liveNameMatch = preferredName ? demoData.articles.find((article) => normalizeName(article.name) === normalizeName(preferredName)) : null
  const directDemoMatch = trimmedArticleId ? demoData.articles.find((article) => String(article.id) === trimmedArticleId) : null

  if (preferredName) {
    const hasLiveMatch = hasLiveInventoryRowsForArticle(preferredName, liveRows)
    return {
      status: 'resolved',
      article: hasLiveMatch
        ? buildLiveFirstArticle(preferredName, liveRows, liveNameMatch || null, trimmedArticleId)
        : liveNameMatch
          ? buildFallbackArticle(liveNameMatch)
          : buildLiveFirstArticle(preferredName, liveRows, null, trimmedArticleId),
      articleName: preferredName,
      hasLiveInventoryMatch: hasLiveMatch,
      isPureDemoArticle: Boolean(liveNameMatch) && !hasLiveMatch,
    }
  }

  if (directDemoMatch) {
    return {
      status: 'resolved',
      article: mergeLiveLocations(directDemoMatch, liveRows),
      articleName: directDemoMatch.name || '',
      hasLiveInventoryMatch: hasLiveInventoryRowsForArticle(directDemoMatch.name, liveRows),
      isPureDemoArticle: !hasLiveInventoryRowsForArticle(directDemoMatch.name, liveRows),
    }
  }

  if (!trimmedArticleId && !trimmedRequestedName) {
    return {
      status: 'missing-identifier',
      article: null,
      articleName: '',
      hasLiveInventoryMatch: false,
      isPureDemoArticle: false,
    }
  }

  return {
    status: 'not-found',
    article: null,
    articleName: preferredName || '',
    hasLiveInventoryMatch: false,
    isPureDemoArticle: false,
  }
}

function ArticleDetailState({ title, message }) {
  return (
    <section className="rz-article-detail-section">
      <h3 className="rz-article-detail-section-title">{title}</h3>
      <div className="rz-empty-state rz-article-detail-section-body">{message}</div>
    </section>
  )
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
  const [inventoryLoading, setInventoryLoading] = useState(true)
  const [historyLoading, setHistoryLoading] = useState(false)

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

  useEffect(() => {
    let cancelled = false
    setInventoryLoading(true)
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
          setInventoryLoadError('Live artikelvoorraad kon niet worden geladen. Demo-locaties worden getoond waar beschikbaar.')
        }
      })
      .finally(() => {
        if (!cancelled) {
          setInventoryLoading(false)
        }
      })

    return () => {
      cancelled = true
    }
  }, [])

  const resolution = useMemo(() => {
    return buildArticleResolution({ articleId, requestedArticleName, liveInventoryRows })
  }, [articleId, requestedArticleName, liveInventoryRows, automationVersion])

  const activeArticle = resolution.article
  const hasLiveInventoryMatch = resolution.hasLiveInventoryMatch
  const isPureDemoArticle = resolution.isPureDemoArticle
  const resolvedArticleName = resolution.articleName

  useEffect(() => {
    let cancelled = false
    setHistoryLoadError('')

    if (!resolvedArticleName) {
      setLiveHistoryRows([])
      setHistoryLoading(false)
      return () => {
        cancelled = true
      }
    }

    setHistoryLoading(true)
    fetchArticleHistory(resolvedArticleName)
      .then((rows) => {
        if (!cancelled) {
          setLiveHistoryRows(rows)
        }
      })
      .catch(() => {
        if (!cancelled) {
          setLiveHistoryRows([])
          setHistoryLoadError(
            hasLiveInventoryMatch
              ? 'Live artikelhistorie kon niet worden geladen.'
              : 'Live artikelhistorie kon niet worden geladen. Demo-historie wordt getoond waar beschikbaar.',
          )
        }
      })
      .finally(() => {
        if (!cancelled) {
          setHistoryLoading(false)
        }
      })

    return () => {
      cancelled = true
    }
  }, [resolvedArticleName, hasLiveInventoryMatch])

  const articleData = useMemo(() => {
    if (!activeArticle) return null
    const merged = activeArticle
    const liveHistory = mapLiveHistoryRows(liveHistoryRows)

    if (hasLiveInventoryMatch) {
      return { ...merged, history: liveHistory }
    }

    if (isPureDemoArticle) {
      return merged
    }

    return liveHistory.length ? { ...merged, history: liveHistory } : merged
  }, [activeArticle, automationVersion, liveHistoryRows, hasLiveInventoryMatch, isPureDemoArticle])

  const pageTitle = `Artikel details: ${articleData?.name || resolvedArticleName || 'Onbekend artikel'}`

  const tabContent = {
    Overzicht: articleData ? <ArticleOverviewTab articleData={articleData} visibilityMap={visibilityMap} visibilityLoading={visibilityLoading} visibilityError={visibilityError} /> : null,
    Voorraad: articleData ? <ArticleStockTab articleData={articleData} /> : null,
    Locaties: articleData ? <ArticleLocationsTab articleData={articleData} /> : null,
    Historie: articleData ? <ArticleHistoryTab articleData={articleData} isLoading={historyLoading} loadError={historyLoadError} /> : null,
    Analyse: articleData ? <ArticleAnalyticsTab articleData={articleData} automationVersion={automationVersion} /> : null,
  }

  const hasBlockingState = resolution.status === 'missing-identifier' || resolution.status === 'not-found'

  return (
    <AppShell title={pageTitle} showExit={false}>
      <ScreenCard fullWidth>
        <div className="rz-article-detail-page">
          {inventoryLoadError ? <div className="rz-article-detail-alert">{inventoryLoadError}</div> : null}
          {historyLoadError && !historyLoading && articleData ? <div className="rz-article-detail-alert">{historyLoadError}</div> : null}

          {inventoryLoading ? (
            <ArticleDetailState title="Artikeldetail laden" message="De live artikelgegevens worden geladen. Als live data niet beschikbaar is, wordt beschikbare demo-informatie gebruikt." />
          ) : hasBlockingState ? (
            <ArticleDetailState
              title={resolution.status === 'missing-identifier' ? 'Artikel niet geselecteerd' : 'Artikel niet gevonden'}
              message={
                resolution.status === 'missing-identifier'
                  ? 'Er is geen geldig artikel opgegeven voor deze detailpagina.'
                  : 'Voor dit artikel konden geen detailgegevens worden gevonden. Controleer de route of open het artikel opnieuw vanuit Voorraad.'
              }
            />
          ) : articleData ? (
            <Tabs tabs={TABS}>
              {(activeTab) => {
                const content = tabContent[activeTab]
                return content || <PlaceholderTab text="Deze tab volgt later." />
              }}
            </Tabs>
          ) : (
            <ArticleDetailState title="Artikel niet beschikbaar" message="Er zijn op dit moment geen stabiele read-gegevens beschikbaar voor deze detailpagina." />
          )}
        </div>
      </ScreenCard>
    </AppShell>
  )
}
