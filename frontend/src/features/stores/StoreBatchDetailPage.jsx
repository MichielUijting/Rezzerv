import { Fragment, useEffect, useMemo, useRef, useState } from 'react'
import { useNavigate, useParams } from 'react-router-dom'
import AppShell from '../../app/AppShell'
import Card from '../../ui/Card'
import Button from '../../ui/Button'
import { getStoreImportSimplificationLabel } from '../settings/services/storeImportSimplificationService'
import {
  articleFallbackOptions,
  articleLabel,
  batchStatusLabel,
  buildBatchTitle,
  fetchJson,
  formatQuantity,
  normalizeErrorMessage,
  providerLabel,
  StoreArticleSelector,
  suggestionLabel,
} from './storeImportShared'
import { buildAutoConsumeArticleIds } from './autoConsumeContext'

const STATUS_FILTERS = [
  { key: 'all', label: 'Alles' },
  { key: 'ready', label: 'Klaar' },
  { key: 'action_needed', label: 'Actie nodig' },
  { key: 'ignored', label: 'Genegeerd' },
  { key: 'processed', label: 'Verwerkt' },
]

const REVIEW_FILTERS = [
  { key: 'all', label: 'Alles' },
  { key: 'selected', label: 'Verwerken' },
  { key: 'ignored', label: 'Negeren' },
  { key: 'pending', label: 'Nog te beoordelen' },
]

const MAPPING_FILTERS = [
  { key: 'all', label: 'Alles' },
  { key: 'known', label: 'Bekende mapping' },
  { key: 'new', label: 'Nieuwe mapping' },
  { key: 'unknown', label: 'Onbekend artikel' },
]

const LOCATION_FILTERS = [
  { key: 'all', label: 'Alles' },
  { key: 'filled', label: 'Locatie ingevuld' },
  { key: 'missing', label: 'Locatie ontbreekt' },
]

function countUniqueNewMappings(lines) {
  const ids = new Set()
  lines.forEach((line) => {
    if (line?.matched_household_article_id && !line?.suggested_household_article_id) {
      ids.add(String(line.id))
    }
  })
  return ids.size
}

function detailValue(value, fallback = 'Niet van toepassing') {
  if (value === undefined || value === null || value === '') return fallback
  return String(value)
}

export default function StoreBatchDetailPage() {
  const navigate = useNavigate()
  const { batchId } = useParams()
  const [household, setHousehold] = useState(null)
  const [providers, setProviders] = useState([])
  const [batch, setBatch] = useState(null)
  const [articleOptions, setArticleOptions] = useState(articleFallbackOptions)
  const [locationOptions, setLocationOptions] = useState([])
  const [status, setStatus] = useState('')
  const [error, setError] = useState('')
  const [isLoading, setIsLoading] = useState(true)
  const [busyLineId, setBusyLineId] = useState('')
  const [isProcessingBatch, setIsProcessingBatch] = useState(false)
  const [processFeedback, setProcessFeedback] = useState('')
  const [lastProcessResult, setLastProcessResult] = useState(null)
  const [batchDiagnostics, setBatchDiagnostics] = useState(null)
  const [lineDrafts, setLineDrafts] = useState({})
  const [lineSaveState, setLineSaveState] = useState({})
  const [selectedLineIds, setSelectedLineIds] = useState([])
  const [expandedLineIds, setExpandedLineIds] = useState([])
  const [activeSummaryFilter, setActiveSummaryFilter] = useState('all')
  const [searchValue, setSearchValue] = useState('')
  const [statusFilter, setStatusFilter] = useState('all')
  const [reviewFilter, setReviewFilter] = useState('all')
  const [mappingFilter, setMappingFilter] = useState('all')
  const [locationFilter, setLocationFilter] = useState('all')
  const [bulkLocationId, setBulkLocationId] = useState('')
  const [bulkArticleId, setBulkArticleId] = useState('')
  const processFeedbackTimer = useRef(null)

  const providersByCode = useMemo(
    () => Object.fromEntries(providers.map((provider) => [provider.code, provider])),
    [providers],
  )

  const activeProviderCode = batch?.store_provider_code || null
  const activeProvider = activeProviderCode ? providersByCode[activeProviderCode] || null : null
  const validLocationIds = useMemo(() => new Set(locationOptions.map((location) => String(location.id))), [locationOptions])

  function getDraftValues(line) {
    const draft = Object.prototype.hasOwnProperty.call(lineDrafts, line.id)
      ? lineDrafts[line.id]
      : {
          articleId: line.matched_household_article_id || '',
          locationId: line.target_location_id || '',
        }
    return {
      articleId: String((draft?.articleId ?? line.matched_household_article_id) ?? ''),
      locationId: String((draft?.locationId ?? line.target_location_id) ?? ''),
    }
  }

  useEffect(() => {
    const nextDrafts = {}
    const nextSaveState = {}
    ;(batch?.lines || []).forEach((line) => {
      nextDrafts[line.id] = {
        articleId: line.matched_household_article_id || '',
        locationId: line.target_location_id || '',
      }
      const existing = lineSaveState[line.id] || {}
      nextSaveState[line.id] = {
        ...existing,
        dirty: false,
        status: existing.status === 'error' ? 'error' : existing.status === 'saved' ? 'saved' : 'idle',
        currentArticleId: String(line.matched_household_article_id || ''),
        currentLocationId: String(line.target_location_id || ''),
      }
    })
    setLineDrafts(nextDrafts)
    setLineSaveState(nextSaveState)
    setSelectedLineIds([])
  }, [batch?.batch_id, batch?.lines])

  function setLineDraftValue(lineId, patch) {
    setLineDrafts((current) => ({
      ...current,
      [lineId]: {
        ...(current[lineId] || { articleId: '', locationId: '' }),
        ...patch,
      },
    }))
  }

  async function refreshBatch(nextBatchId = batchId) {
    const nextBatch = await fetchJson(`/api/purchase-import-batches/${nextBatchId}`)
    setBatch(nextBatch)
    return nextBatch
  }

  async function refreshBatchDiagnostics(nextBatchId = batchId) {
    if (!nextBatchId) return null
    const diagnostics = await fetchJson(`/api/dev/purchase-import-batches/${nextBatchId}/diagnostics`).catch(() => null)
    setBatchDiagnostics(diagnostics)
    return diagnostics
  }

  async function refreshLocationOptions(householdId) {
    if (!householdId) return []
    const backendLocations = await fetchJson(`/api/store-location-options?householdId=${encodeURIComponent(householdId)}&_ts=${Date.now()}`, { cache: 'no-store' }).catch(() => [])
    const nextLocations = Array.isArray(backendLocations) ? backendLocations : []
    setLocationOptions(nextLocations)
    return nextLocations
  }

  async function persistLineDraft(line, patch = {}) {
    if (!batch) return
    const draftValues = getDraftValues(line)
    const nextArticleId = String(patch.articleId !== undefined ? (patch.articleId ?? '') : draftValues.articleId)
    const nextLocationId = String(patch.locationId !== undefined ? (patch.locationId ?? '') : draftValues.locationId)
    const originalArticleId = String(line.matched_household_article_id || '')
    const originalLocationId = String(line.target_location_id || '')
    const articleChanged = nextArticleId !== originalArticleId
    const locationChanged = nextLocationId !== originalLocationId

    setLineDraftValue(line.id, { articleId: nextArticleId, locationId: nextLocationId })

    if (!articleChanged && !locationChanged) {
      setLineSaveState((current) => ({
        ...current,
        [line.id]: {
          ...(current[line.id] || {}),
          dirty: false,
          status: 'saved',
          message: 'Opgeslagen',
          savedAt: new Date().toISOString(),
          error: '',
        },
      }))
      return
    }

    setBusyLineId(line.id)
    setError('')
    setStatus('')
    setLineSaveState((current) => ({
      ...current,
      [line.id]: {
        ...(current[line.id] || {}),
        dirty: true,
        status: 'saving',
        message: 'Opslaan…',
        error: '',
      },
    }))
    try {
      if (articleChanged) {
        await fetchJson(`/api/purchase-import-lines/${line.id}/map`, {
          method: 'POST',
          body: JSON.stringify({ household_article_id: nextArticleId || null }),
        })
      }
      if (locationChanged) {
        await fetchJson(`/api/purchase-import-lines/${line.id}/target-location`, {
          method: 'POST',
          body: JSON.stringify({ target_location_id: nextLocationId || null }),
        })
      }
      await refreshBatch(batch.batch_id)
      await refreshLocationOptions(household?.id)
      setLineSaveState((current) => ({
        ...current,
        [line.id]: {
          ...(current[line.id] || {}),
          dirty: false,
          status: 'saved',
          message: 'Opgeslagen',
          savedAt: new Date().toISOString(),
          error: '',
          currentArticleId: nextArticleId,
          currentLocationId: nextLocationId,
        },
      }))
    } catch (err) {
      const message = normalizeErrorMessage(err?.message) || 'Opslaan mislukt'
      setError(message)
      setLineSaveState((current) => ({
        ...current,
        [line.id]: {
          ...(current[line.id] || {}),
          dirty: true,
          status: 'error',
          message: 'Opslaan mislukt',
          error: message,
        },
      }))
    } finally {
      setBusyLineId('')
    }
  }

  function clearTransientFeedback() {
    if (processFeedbackTimer.current) {
      window.clearTimeout(processFeedbackTimer.current)
      processFeedbackTimer.current = null
    }
  }

  function showProcessFeedback(message) {
    clearTransientFeedback()
    setProcessFeedback(message)
    processFeedbackTimer.current = window.setTimeout(() => setProcessFeedback(''), 2200)
  }

  async function loadPageData() {
    setIsLoading(true)
    setError('')
    try {
      const token = localStorage.getItem('rezzerv_token')
      const householdData = await fetchJson('/api/household', {
        headers: token ? { Authorization: `Bearer ${token}` } : {},
      })
      setHousehold(householdData)

      const [providerData, backendArticles, backendLocations, loadedBatch] = await Promise.all([
        fetchJson('/api/store-providers'),
        fetchJson('/api/store-review-articles').catch(() => articleFallbackOptions),
        fetchJson(`/api/store-location-options?householdId=${encodeURIComponent(householdData.id)}&_ts=${Date.now()}`, { cache: 'no-store' }).catch(() => []),
        fetchJson(`/api/purchase-import-batches/${batchId}`),
      ])

      setProviders(providerData)
      setArticleOptions(Array.isArray(backendArticles) && backendArticles.length ? backendArticles : articleFallbackOptions)
      setLocationOptions(Array.isArray(backendLocations) ? backendLocations : [])
      setBatch(loadedBatch)
      const diagnostics = await fetchJson(`/api/dev/purchase-import-batches/${batchId}/diagnostics`).catch(() => null)
      setBatchDiagnostics(diagnostics)
    } catch (err) {
      setError(normalizeErrorMessage(err?.message) || 'De kassabon kon niet worden geladen.')
    } finally {
      setIsLoading(false)
    }
  }

  useEffect(() => {
    loadPageData()
    return () => clearTransientFeedback()
  }, [batchId])

  useEffect(() => {
    if (household?.id && batch?.batch_id) {
      refreshLocationOptions(household.id)
    }
  }, [household?.id, batch?.batch_id])

  async function handleReviewDecision(lineId, reviewDecision) {
    setBusyLineId(lineId)
    setError('')
    setStatus('')
    try {
      await fetchJson(`/api/purchase-import-lines/${lineId}/review`, {
        method: 'POST',
        body: JSON.stringify({ review_decision: reviewDecision }),
      })
      await refreshBatch(batch.batch_id)
      setStatus('De beoordeling is opgeslagen.')
    } catch (err) {
      setError(normalizeErrorMessage(err?.message) || 'De beoordeling kon niet worden opgeslagen.')
    } finally {
      setBusyLineId('')
    }
  }

  async function handleCreateArticleFromLine(lineId, articleName) {
    setBusyLineId(lineId)
    setError('')
    setStatus('')
    try {
      const result = await fetchJson(`/api/purchase-import-lines/${lineId}/create-article`, {
        method: 'POST',
        body: JSON.stringify({ article_name: articleName }),
      })
      if (result?.article_option) {
        setArticleOptions((current) => {
          const next = Array.isArray(current) ? [...current] : []
          const exists = next.some((item) => String(item.id) === String(result.article_option.id))
          if (!exists) {
            next.push(result.article_option)
            next.sort((a, b) => articleLabel(a).localeCompare(articleLabel(b), 'nl'))
          }
          return next
        })
      }
      await refreshBatch(batch.batch_id)
      setStatus('Nieuw artikel aangemaakt en gekoppeld aan de bonregel.')
      return result?.article_option || null
    } catch (err) {
      setError(normalizeErrorMessage(err?.message) || 'Het nieuwe artikel kon niet worden aangemaakt.')
      return null
    } finally {
      setBusyLineId('')
    }
  }

  async function processBatchNow(mode = 'ready_only') {
    if (!batch) return
    const lineStateMap = new Map(lineUiStates.map((entry) => [entry.line.id, entry]))
    const autoConsumeLines = Array.from(lineStateMap.values())
      .filter((entry) => entry.isReadyForProcessing)
      .map((entry) => entry.line)

    setIsProcessingBatch(true)
    setError('')
    setStatus('')
    setLastProcessResult(null)
    try {
      const result = await fetchJson(`/api/purchase-import-batches/${batch.batch_id}/process`, {
        method: 'POST',
        body: JSON.stringify({ processed_by: 'ui', mode, auto_consume_article_ids: buildAutoConsumeArticleIds(autoConsumeLines) }),
      })
      await refreshBatch(batch.batch_id)
      await refreshLocationOptions(household?.id)
      setLastProcessResult(result)
      setBatchDiagnostics(result?.diagnostics || null)
      showProcessFeedback('Verwerkt!')
      if (result.failed_count > 0) {
        setStatus(`Verwerking afgerond: ${result.processed_count} regel(s) verwerkt, ${result.failed_count} regel(s) mislukt.`)
      } else {
        setStatus(`Verwerking afgerond: ${result.processed_count} regel(s) verwerkt, ${result.skipped_count || 0} regel(s) overgeslagen.`)
      }
      setActiveSummaryFilter('action_needed')
      setStatusFilter('action_needed')
    } catch (err) {
      setError(normalizeErrorMessage(err?.message) || 'De batch kon niet naar voorraad worden verwerkt.')
    } finally {
      setIsProcessingBatch(false)
    }
  }

  function toggleExpanded(lineId) {
    setExpandedLineIds((current) => current.includes(lineId) ? current.filter((value) => value !== lineId) : [...current, lineId])
  }

  const diagByLineId = useMemo(() => {
    const entries = batchDiagnostics?.line_diagnostics || []
    return Object.fromEntries(entries.map((entry) => [entry.line_id, entry]))
  }, [batchDiagnostics])

  const lineUiStates = useMemo(() => {
    const lines = batch?.lines || []
    return lines.map((line) => {
      const draft = getDraftValues(line)
      const saveState = lineSaveState[line.id] || { dirty: false, status: 'idle', message: '', error: '' }
      const effectiveArticleId = String(draft.articleId || '')
      const effectiveLocationId = String(draft.locationId || '')
      const hasValidArticle = Boolean(effectiveArticleId)
      const hasValidLocation = Boolean(effectiveLocationId) && validLocationIds.has(effectiveLocationId)
      const reviewDecision = line.review_decision || 'pending'
      const processingStatus = line.processing_status || 'pending'

      let statusKey = 'new'
      let statusLabel = 'Nieuw'
      let statusReason = 'Regel wacht nog op beoordeling.'

      if (processingStatus === 'processed') {
        statusKey = 'processed'
        statusLabel = 'Verwerkt'
        statusReason = 'Regel is al naar voorraad verwerkt.'
      } else if (processingStatus === 'failed') {
        statusKey = 'action_needed'
        statusLabel = 'Actie nodig'
        statusReason = line.processing_error || 'Vorige verwerking mislukte; controleer deze regel.'
      } else if (reviewDecision === 'ignored') {
        statusKey = 'ignored'
        statusLabel = 'Genegeerd'
        statusReason = 'Door gebruiker overgeslagen.'
      } else if (reviewDecision === 'selected') {
        if (saveState.dirty) {
          statusKey = 'action_needed'
          statusLabel = 'Actie nodig'
          statusReason = 'Wijzigingen zijn nog niet opgeslagen.'
        } else if (!hasValidArticle) {
          statusKey = 'action_needed'
          statusLabel = 'Actie nodig'
          statusReason = 'Artikel onbekend of nog niet gekoppeld.'
        } else if (!hasValidLocation) {
          statusKey = 'action_needed'
          statusLabel = 'Actie nodig'
          statusReason = 'Locatie ontbreekt.'
        } else {
          statusKey = 'ready'
          statusLabel = 'Klaar'
          statusReason = 'Regel is compleet en klaar voor verwerking.'
        }
      }

      let mappingState = 'unknown'
      if (hasValidArticle && line.suggested_household_article_id && String(line.suggested_household_article_id) === effectiveArticleId) {
        mappingState = 'known'
      } else if (hasValidArticle) {
        mappingState = 'new'
      }

      return {
        line,
        draft,
        saveState,
        reviewDecision,
        processingStatus,
        hasValidArticle,
        hasValidLocation,
        statusKey,
        statusLabel,
        statusReason,
        mappingState,
        isReadyForProcessing: statusKey === 'ready',
        searchText: [line.article_name_raw, line.brand_raw, line.resolved_household_article_name, suggestionLabel(line)]
          .filter(Boolean)
          .join(' ')
          .toLowerCase(),
      }
    })
  }, [batch?.lines, lineSaveState, lineDrafts, validLocationIds])

  const summaryCounts = useMemo(() => {
    const counts = {
      total: lineUiStates.length,
      ready: lineUiStates.filter((entry) => entry.statusKey === 'ready').length,
      action_needed: lineUiStates.filter((entry) => entry.statusKey === 'action_needed').length,
      ignored: lineUiStates.filter((entry) => entry.statusKey === 'ignored').length,
      processed: lineUiStates.filter((entry) => entry.statusKey === 'processed').length,
      new_mapping: countUniqueNewMappings(lineUiStates.map((entry) => entry.line)),
    }
    return counts
  }, [lineUiStates])

  const filteredLineUiStates = useMemo(() => {
    const searchNeedle = searchValue.trim().toLowerCase()
    return lineUiStates.filter((entry) => {
      if (activeSummaryFilter !== 'all') {
        if (activeSummaryFilter === 'new_mapping' && entry.mappingState !== 'new') return false
        if (activeSummaryFilter !== 'new_mapping' && entry.statusKey !== activeSummaryFilter) return false
      }
      if (statusFilter !== 'all' && entry.statusKey !== statusFilter) return false
      if (reviewFilter !== 'all' && entry.reviewDecision !== reviewFilter) return false
      if (mappingFilter !== 'all' && entry.mappingState !== mappingFilter) return false
      if (locationFilter === 'filled' && !entry.hasValidLocation) return false
      if (locationFilter === 'missing' && entry.hasValidLocation) return false
      if (searchNeedle && !entry.searchText.includes(searchNeedle)) return false
      return true
    })
  }, [lineUiStates, activeSummaryFilter, statusFilter, reviewFilter, mappingFilter, locationFilter, searchValue])
  const selectedLineStates = useMemo(() => {
    const selectedSet = new Set(selectedLineIds)
    return lineUiStates.filter((entry) => selectedSet.has(entry.line.id))
  }, [lineUiStates, selectedLineIds])

  const canProcessBatch = useMemo(() => {
    return !isLoading && !busyLineId && lineUiStates.some((entry) => entry.isReadyForProcessing)
  }, [isLoading, busyLineId, lineUiStates])

  const simplificationLevelLabel = getStoreImportSimplificationLabel(household?.store_import_simplification_level || 'gebalanceerd')

  function handleSummaryTileClick(nextKey) {
    setActiveSummaryFilter(nextKey)
    setStatusFilter(nextKey === 'new_mapping' ? 'all' : nextKey)
  }

  function resetFilters() {
    setActiveSummaryFilter('all')
    setStatusFilter('all')
    setReviewFilter('all')
    setMappingFilter('all')
    setLocationFilter('all')
    setSearchValue('')
  }

  function showExceptionsOnly() {
    setActiveSummaryFilter('all')
    setStatusFilter('action_needed')
    setLocationFilter('missing')
    setReviewFilter('all')
    setMappingFilter('all')
  }

  function toggleLineSelection(lineId) {
    setSelectedLineIds((current) => current.includes(lineId) ? current.filter((value) => value !== lineId) : [...current, lineId])
  }

  function toggleSelectAllVisible() {
    const visibleIds = filteredLineUiStates.map((entry) => entry.line.id)
    const visibleIdSet = new Set(visibleIds)
    const allSelected = visibleIds.length > 0 && visibleIds.every((id) => selectedLineIds.includes(id))
    setSelectedLineIds((current) => {
      const retained = current.filter((id) => !visibleIdSet.has(id))
      return allSelected ? retained : [...retained, ...visibleIds]
    })
  }

  function selectEverythingInFilter() {
    const visibleIds = filteredLineUiStates.map((entry) => entry.line.id)
    setSelectedLineIds((current) => Array.from(new Set([...current, ...visibleIds])))
  }

  async function handleBulkReviewDecision(nextDecision) {
    const targets = selectedLineStates.filter((entry) => entry.reviewDecision !== nextDecision)
    if (!targets.length) return
    setBusyLineId('bulk-review')
    setError('')
    setStatus('')
    try {
      for (const entry of targets) {
        await fetchJson(`/api/purchase-import-lines/${entry.line.id}/review`, {
          method: 'POST',
          body: JSON.stringify({ review_decision: nextDecision }),
        })
      }
      await refreshBatch(batch.batch_id)
      setStatus(`${targets.length} regel(s) zijn bijgewerkt naar ${nextDecision === 'selected' ? 'Verwerken' : 'Negeren'}.`)
    } catch (err) {
      setError(normalizeErrorMessage(err?.message) || 'De bulkactie kon niet worden opgeslagen.')
    } finally {
      setBusyLineId('')
    }
  }

  async function handleBulkLocationApply() {
    if (!bulkLocationId) {
      setError('Kies eerst een locatie voor de geselecteerde regels.')
      return
    }
    const targets = selectedLineStates.filter((entry) => String(entry.draft.locationId || '') !== String(bulkLocationId))
    if (!targets.length) return
    for (const entry of targets) {
      // eslint-disable-next-line no-await-in-loop
      await persistLineDraft(entry.line, { locationId: bulkLocationId })
    }
    setStatus(`${targets.length} regel(s) hebben een nieuwe locatie gekregen.`)
  }

  async function handleBulkArticleApply() {
    if (!bulkArticleId) {
      setError('Kies eerst een artikel voor de geselecteerde regels.')
      return
    }
    const targets = selectedLineStates.filter((entry) => String(entry.draft.articleId || '') !== String(bulkArticleId))
    if (!targets.length) return
    for (const entry of targets) {
      // eslint-disable-next-line no-await-in-loop
      await persistLineDraft(entry.line, { articleId: bulkArticleId })
    }
    setStatus(`${targets.length} regel(s) zijn gekoppeld aan hetzelfde artikel.`)
  }

  const allVisibleSelected = filteredLineUiStates.length > 0 && filteredLineUiStates.every((entry) => selectedLineIds.includes(entry.line.id))

  return (
    <AppShell title="Kassabon werkblad" showExit={false}>
      <div style={{ display: 'grid', gap: '16px', width: '100%' }}>
        <Card>
          <div className="rz-store-workbench-header">
            <div className="rz-store-workbench-heading">
              <div className="rz-store-workbench-eyebrow">Kassabon werkblad</div>
              <h2 style={{ margin: 0, fontSize: '24px' }}>{batch ? buildBatchTitle(batch) : 'Kassabon werkblad'}</h2>
              <div className="rz-store-workbench-meta">{batch?.purchase_date || 'Onbekende datum'} · {batch?.store_label || batch?.store_name || providerLabel(activeProvider)}</div>
              <div className="rz-store-workbench-meta">Status: {batch ? batchStatusLabel(batch.import_status) : 'Laden'} · {summaryCounts.total} regels · Vereenvoudigingsniveau: {simplificationLevelLabel}</div>
            </div>
            <div className="rz-store-workbench-actions">
              <Button variant="secondary" onClick={() => navigate('/winkels')}>Terug naar bonnen</Button>
              <Button variant="secondary" onClick={() => navigate('/voorraad')}>Bekijk voorraad</Button>
              <Button variant="primary" onClick={() => processBatchNow('ready_only')} disabled={isProcessingBatch || !canProcessBatch}>
                {isProcessingBatch ? 'Bezig…' : 'Verwerk alles wat klaar is'}
              </Button>
              {processFeedback ? <span className="rz-store-inline-feedback">{processFeedback}</span> : null}
            </div>
          </div>
        </Card>

        {error ? (
          <Card><div className="rz-inline-feedback rz-inline-feedback--error">{error}</div></Card>
        ) : null}
        {status ? (
          <Card><div className="rz-inline-feedback rz-inline-feedback--success">{status}</div></Card>
        ) : null}

        {isLoading ? (
          <Card><div>Bongegevens laden…</div></Card>
        ) : batch ? (
          <>
            <Card>
              <div className="rz-store-summary-grid">
                <button type="button" className={`rz-store-summary-tile ${activeSummaryFilter === 'all' ? 'is-active' : ''}`} onClick={() => handleSummaryTileClick('all')}>
                  <span className="rz-store-summary-label">Totaal</span>
                  <strong>{summaryCounts.total}</strong>
                </button>
                <button type="button" className={`rz-store-summary-tile ${activeSummaryFilter === 'ready' ? 'is-active' : ''}`} onClick={() => handleSummaryTileClick('ready')}>
                  <span className="rz-store-summary-label">Klaar</span>
                  <strong>{summaryCounts.ready}</strong>
                </button>
                <button type="button" className={`rz-store-summary-tile ${activeSummaryFilter === 'action_needed' ? 'is-active' : ''}`} onClick={() => handleSummaryTileClick('action_needed')}>
                  <span className="rz-store-summary-label">Actie nodig</span>
                  <strong>{summaryCounts.action_needed}</strong>
                </button>
                <button type="button" className={`rz-store-summary-tile ${activeSummaryFilter === 'ignored' ? 'is-active' : ''}`} onClick={() => handleSummaryTileClick('ignored')}>
                  <span className="rz-store-summary-label">Genegeerd</span>
                  <strong>{summaryCounts.ignored}</strong>
                </button>
                <button type="button" className={`rz-store-summary-tile ${activeSummaryFilter === 'processed' ? 'is-active' : ''}`} onClick={() => handleSummaryTileClick('processed')}>
                  <span className="rz-store-summary-label">Verwerkt</span>
                  <strong>{summaryCounts.processed}</strong>
                </button>
                <button type="button" className={`rz-store-summary-tile ${activeSummaryFilter === 'new_mapping' ? 'is-active' : ''}`} onClick={() => handleSummaryTileClick('new_mapping')}>
                  <span className="rz-store-summary-label">Nieuw gekoppeld</span>
                  <strong>{summaryCounts.new_mapping}</strong>
                </button>
              </div>
            </Card>

            <Card>
              <div className="rz-store-filters-grid">
                <input
                  className="rz-input"
                  type="text"
                  placeholder="Zoek op bonartikel of gekoppeld artikel"
                  value={searchValue}
                  onChange={(event) => setSearchValue(event.target.value)}
                />
                <select className="rz-input" value={statusFilter} onChange={(event) => setStatusFilter(event.target.value)}>
                  {STATUS_FILTERS.map((filter) => <option key={filter.key} value={filter.key}>{filter.label}</option>)}
                </select>
                <select className="rz-input" value={reviewFilter} onChange={(event) => setReviewFilter(event.target.value)}>
                  {REVIEW_FILTERS.map((filter) => <option key={filter.key} value={filter.key}>{filter.label}</option>)}
                </select>
                <select className="rz-input" value={mappingFilter} onChange={(event) => setMappingFilter(event.target.value)}>
                  {MAPPING_FILTERS.map((filter) => <option key={filter.key} value={filter.key}>{filter.label}</option>)}
                </select>
                <select className="rz-input" value={locationFilter} onChange={(event) => setLocationFilter(event.target.value)}>
                  {LOCATION_FILTERS.map((filter) => <option key={filter.key} value={filter.key}>{filter.label}</option>)}
                </select>
                <div className="rz-store-filter-actions">
                  <Button variant="secondary" onClick={resetFilters}>Filters wissen</Button>
                  <Button variant="secondary" onClick={showExceptionsOnly}>Toon alleen uitzonderingen</Button>
                </div>
              </div>
            </Card>

            {selectedLineIds.length ? (
              <Card>
                <div className="rz-store-bulkbar">
                  <div><strong>{selectedLineIds.length}</strong> regel(s) geselecteerd</div>
                  <div className="rz-store-bulk-actions">
                    <Button variant="secondary" onClick={selectEverythingInFilter}>Selecteer alles in filter</Button>
                    <Button variant="secondary" onClick={() => handleBulkReviewDecision('selected')} disabled={Boolean(busyLineId)}>Zet op Verwerken</Button>
                    <Button variant="secondary" onClick={() => handleBulkReviewDecision('ignored')} disabled={Boolean(busyLineId)}>Zet op Negeren</Button>
                    <select className="rz-input" value={bulkArticleId} onChange={(event) => setBulkArticleId(event.target.value)}>
                      <option value="">Koppel geselecteerde regels</option>
                      {articleOptions.map((article) => <option key={article.id} value={article.id}>{articleLabel(article)}</option>)}
                    </select>
                    <Button variant="secondary" onClick={handleBulkArticleApply} disabled={Boolean(busyLineId)}>Koppel geselecteerde regels</Button>
                    <select className="rz-input" value={bulkLocationId} onChange={(event) => setBulkLocationId(event.target.value)}>
                      <option value="">Kies locatie</option>
                      {locationOptions.map((location) => <option key={location.id} value={location.id}>{location.label}</option>)}
                    </select>
                    <Button variant="secondary" onClick={handleBulkLocationApply} disabled={Boolean(busyLineId)}>Kies locatie</Button>
                    <Button variant="secondary" onClick={() => setStatus('Werkblad is bijgewerkt. De wijzigingen zijn direct opgeslagen per regel.')}>Opslaan</Button>
                  </div>
                </div>
              </Card>
            ) : null}

            {lastProcessResult ? (
              <Card>
                <div className="rz-store-result-card">
                  <div>
                    <div className="rz-store-workbench-eyebrow">Verwerking afgerond</div>
                    <div>Verwerkt: <strong>{lastProcessResult.processed_count || 0}</strong> · Overgeslagen: <strong>{lastProcessResult.skipped_count || 0}</strong> · Mislukt: <strong>{lastProcessResult.failed_count || 0}</strong></div>
                  </div>
                  <div className="rz-store-result-actions">
                    <Button variant="secondary" onClick={() => setStatusFilter('processed')}>Toon verwerkte regels</Button>
                    <Button variant="secondary" onClick={() => setStatusFilter('action_needed')}>Toon overgeslagen regels</Button>
                    <Button variant="secondary" onClick={() => navigate('/voorraad')}>Ga naar voorraad</Button>
                  </div>
                </div>
              </Card>
            ) : null}

            <Card>
              <div className="rz-table-wrapper">
                <table className="rz-table rz-store-workbench-table">
                  <thead>
                    <tr className="rz-table-header">
                      <th style={{ width: '44px' }}>
                        <input type="checkbox" checked={allVisibleSelected} onChange={toggleSelectAllVisible} aria-label="Selecteer alle zichtbare regels" />
                      </th>
                      <th>Bonartikel</th>
                      <th className="rz-num">Aantal</th>
                      <th>Gekoppeld artikel</th>
                      <th>Beoordeling</th>
                      <th>Locatie</th>
                      <th>Status</th>
                      <th>Reden</th>
                      <th>Details</th>
                    </tr>
                  </thead>
                  <tbody>
                    {filteredLineUiStates.length === 0 ? (
                      <tr>
                        <td colSpan={9}>Geen regels in deze selectie.</td>
                      </tr>
                    ) : filteredLineUiStates.map((entry) => {
                      const { line, draft, saveState, statusLabel: currentStatusLabel, statusReason } = entry
                      const lineBusy = busyLineId === line.id || busyLineId === 'bulk-review'
                      const isExpanded = expandedLineIds.includes(line.id)
                      const diag = diagByLineId[line.id] || null
                      return (
                        <Fragment key={line.id}>
                          <tr key={line.id} className={`rz-store-workbench-row ${entry.statusKey === 'ready' ? 'is-ready' : entry.statusKey === 'action_needed' ? 'is-action-needed' : entry.statusKey === 'ignored' ? 'is-ignored' : ''}`}>
                            <td>
                              <input type="checkbox" checked={selectedLineIds.includes(line.id)} onChange={() => toggleLineSelection(line.id)} aria-label={`Selecteer ${line.article_name_raw}`} />
                            </td>
                            <td>
                              <div className="rz-store-primary">{line.article_name_raw}</div>
                              <div className="rz-store-secondary">{providerLabel(activeProvider)} · {line.brand_raw || 'Geen merk'} · {line.line_price_raw != null ? `€ ${line.line_price_raw.toFixed(2)}` : 'Geen prijs'}</div>
                              {suggestionLabel(line) ? <div className={`rz-store-suggestion ${line.is_auto_prefilled ? 'rz-store-suggestion--auto' : 'rz-store-suggestion--check'}`}>{suggestionLabel(line)}</div> : null}
                              {entry.mappingState === 'new' ? <div className="rz-store-badge rz-store-badge--new">Nieuwe mapping</div> : null}
                              {entry.mappingState === 'known' ? <div className="rz-store-badge rz-store-badge--known">Bekende mapping</div> : null}
                            </td>
                            <td className="rz-num"><div className="rz-store-amount">{formatQuantity(line.quantity_raw, line.unit_raw)}</div></td>
                            <td>
                              <StoreArticleSelector
                                lineId={line.id}
                                lineName={line.article_name_raw}
                                selectedArticleId={draft.articleId || ''}
                                articleOptions={articleOptions}
                                disabled={lineBusy || isProcessingBatch}
                                onChange={(nextArticleId) => persistLineDraft(line, { articleId: nextArticleId ?? '' })}
                                onClearArticle={() => persistLineDraft(line, { articleId: '' })}
                                onCreateArticle={(articleName) => handleCreateArticleFromLine(line.id, articleName)}
                              />
                            </td>
                            <td>
                              <select
                                className="rz-input rz-store-select"
                                value={line.review_decision || 'pending'}
                                disabled={lineBusy || isProcessingBatch}
                                onChange={(event) => handleReviewDecision(line.id, event.target.value)}
                              >
                                <option value="pending">Nog te beoordelen</option>
                                <option value="selected">Verwerken</option>
                                <option value="ignored">Negeren</option>
                              </select>
                            </td>
                            <td>
                              <select
                                className="rz-input rz-store-select"
                                value={draft.locationId || ''}
                                disabled={lineBusy || isProcessingBatch}
                                onFocus={() => household?.id && refreshLocationOptions(household.id)}
                                onMouseDown={() => household?.id && refreshLocationOptions(household.id)}
                                onChange={(event) => persistLineDraft(line, { locationId: event.target.value || '' })}
                              >
                                <option value="">Kies locatie</option>
                                {locationOptions.map((location) => (
                                  <option key={location.id} value={location.id}>{location.label}</option>
                                ))}
                              </select>
                            </td>
                            <td><span className={`rz-store-status-badge rz-store-status-badge--${entry.statusKey}`}>{currentStatusLabel}</span></td>
                            <td>
                              <div>{statusReason}</div>
                              {saveState?.message ? <div className="rz-store-secondary">{saveState.message}</div> : null}
                              {saveState?.error ? <div className="rz-inline-feedback rz-inline-feedback--error" style={{ marginTop: '6px' }}>{saveState.error}</div> : null}
                            </td>
                            <td>
                              <Button variant="secondary" onClick={() => toggleExpanded(line.id)}>{isExpanded ? 'Sluit' : 'Details'}</Button>
                            </td>
                          </tr>
                          {isExpanded ? (
                            <tr key={`${line.id}-details`}>
                              <td colSpan={9}>
                                <div className="rz-store-detail-grid">
                                  <div className="rz-store-detail-panel">
                                    <div className="rz-store-detail-title">Automatische afboeking</div>
                                    <div><strong>Huishoudinstelling:</strong> {detailValue(diag?.household_consume_mode || diag?.household_mode || household?.default_consume_mode || household?.consume_mode || 'Uit')}</div>
                                    <div><strong>Artikeloverride:</strong> {detailValue(diag?.article_consume_override || diag?.article_override || 'Huishoudinstelling volgen')}</div>
                                    <div><strong>Effectieve automatische afboeking:</strong> {detailValue(diag?.auto_consume_effective_mode || diag?.effective_mode || 'Niet van toepassing')}</div>
                                    <div><strong>Beslisreden:</strong> {detailValue(diag?.auto_consume_decision_reason || diag?.decision_reason || statusReason)}</div>
                                  </div>
                                  <div className="rz-store-detail-panel">
                                    <div className="rz-store-detail-title">Verwerkingsuitkomst</div>
                                    <div><strong>Aangevraagd af te boeken:</strong> {detailValue(diag?.auto_consume_requested_deduction_quantity, '0')}</div>
                                    <div><strong>Werkelijk afgeboekt:</strong> {detailValue(diag?.auto_consume_applied_deduction_quantity, '0')}</div>
                                    <div><strong>Laatste verwerking:</strong> {detailValue(line.processed_at || diag?.processed_at || 'Nog niet verwerkt')}</div>
                                    <div><strong>Laatste resultaat:</strong> {detailValue(diag?.processing_status || line.processing_status || 'Nog niet verwerkt')}</div>
                                  </div>
                                </div>
                              </td>
                            </tr>
                          ) : null}
                        </Fragment>
                      )
                    })}
                  </tbody>
                </table>
              </div>
            </Card>
          </>
        ) : (
          <Card><div>Deze bon kon niet worden gevonden.</div></Card>
        )}
      </div>
    </AppShell>
  )
}
