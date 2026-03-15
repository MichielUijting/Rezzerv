import { Fragment, useEffect, useMemo, useRef, useState } from 'react'
import { useNavigate, useParams } from 'react-router-dom'
import AppShell from '../../app/AppShell'
import ScreenCard from '../../ui/ScreenCard'
import Tabs from '../../ui/Tabs'
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
} from './storeImportShared'

const STATUS_FILTERS = [
  { key: 'all', label: 'Alles' },
  { key: 'ready', label: 'Klaar' },
  { key: 'action_needed', label: 'Actie nodig' },
  { key: 'ignored', label: 'Genegeerd' },
  { key: 'processed', label: 'Verwerkt' },
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

export function StoreBatchDetailContent({ batchIdOverride = '', embedded = false }) {
  const navigate = useNavigate()
  const params = useParams()
  const batchId = batchIdOverride || params.batchId || ''
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
  const [activeSummaryFilter, setActiveSummaryFilter] = useState('all')
  const [searchValue, setSearchValue] = useState('')
  const [statusFilter, setStatusFilter] = useState('all')
  const [mappingFilter, setMappingFilter] = useState('all')
  const [locationFilter, setLocationFilter] = useState('all')
  const [processConfirm, setProcessConfirm] = useState(null)
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
    const nextLineIds = []
    ;(batch?.lines || []).forEach((line) => {
      nextLineIds.push(line.id)
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
    setSelectedLineIds((current) => current.filter((id) => nextLineIds.includes(id)))
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

  async function syncSelectedReviewDecisions() {
    if (!batch) return
    const selectedSet = new Set(selectedLineIds)
    const lines = batch?.lines || []
    await Promise.all(lines.map((line) => {
      const nextDecision = selectedSet.has(line.id) ? 'selected' : 'ignored'
      if ((line.review_decision || 'pending') === nextDecision) return Promise.resolve()
      return fetchJson(`/api/purchase-import-lines/${line.id}/review`, {
        method: 'POST',
        body: JSON.stringify({ review_decision: nextDecision }),
      })
    }))
    await refreshBatch(batch.batch_id)
  }

  async function handleProcessSelected(mode = 'selected_only') {
    if (!batch) return
    if (selectedLineIds.length === 0) {
      setError('Selecteer eerst minstens één bonregel.')
      return
    }
    await syncSelectedReviewDecisions()
    await processBatchNow(mode)
    setProcessConfirm(null)
  }

  function handlePrimaryProcessClick() {
    if (!batch) return
    if (selectedLineIds.length === 0) {
      setError('Selecteer eerst minstens één bonregel.')
      return
    }
    const selectedSet = new Set(selectedLineIds)
    const selectedEntries = lineUiStates.filter((entry) => selectedSet.has(entry.line.id))
    const readyEntries = selectedEntries.filter((entry) => entry.hasValidArticle && entry.hasValidLocation)
    const incompleteEntries = selectedEntries.filter((entry) => !(entry.hasValidArticle && entry.hasValidLocation))
    if (incompleteEntries.length > 0) {
      setProcessConfirm({ readyCount: readyEntries.length, incompleteCount: incompleteEntries.length })
      return
    }
    handleProcessSelected('selected_only')
  }

  async function processBatchNow(mode = 'ready_only') {
    if (!batch) return
    setIsProcessingBatch(true)
    setError('')
    setStatus('')
    setLastProcessResult(null)
    try {
      const result = await fetchJson(`/api/purchase-import-batches/${batch.batch_id}/process`, {
        method: 'POST',
        body: JSON.stringify({ processed_by: 'ui', mode }),
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
        searchText: [line.article_name_raw, line.brand_raw, line.resolved_household_article_name]
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
      if (mappingFilter !== 'all' && entry.mappingState !== mappingFilter) return false
      if (locationFilter === 'filled' && !entry.hasValidLocation) return false
      if (locationFilter === 'missing' && entry.hasValidLocation) return false
      if (searchNeedle && !entry.searchText.includes(searchNeedle)) return false
      return true
    })
  }, [lineUiStates, activeSummaryFilter, statusFilter, mappingFilter, locationFilter, searchValue])
  const selectedLineStates = useMemo(() => {
    const selectedSet = new Set(selectedLineIds)
    return lineUiStates.filter((entry) => selectedSet.has(entry.line.id))
  }, [lineUiStates, selectedLineIds])


  const simplificationLevelLabel = getStoreImportSimplificationLabel(household?.store_import_simplification_level || 'gebalanceerd')

  function handleSummaryTileClick(nextKey) {
    setActiveSummaryFilter(nextKey)
    setStatusFilter(nextKey === 'new_mapping' ? 'all' : nextKey)
  }

  function resetFilters() {
    setActiveSummaryFilter('all')
    setStatusFilter('all')
    setMappingFilter('all')
    setLocationFilter('all')
    setSearchValue('')
  }

  function showExceptionsOnly() {
    setActiveSummaryFilter('all')
    setStatusFilter('action_needed')
    setLocationFilter('missing')
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





  const allVisibleSelected = filteredLineUiStates.length > 0 && filteredLineUiStates.every((entry) => selectedLineIds.includes(entry.line.id))

  const tabContent = {
    Bonregels: (
      <>
        <div style={{ display: 'grid', gap: '16px' }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', gap: '12px', flexWrap: 'wrap', alignItems: 'start' }}>
            <div style={{ display: 'grid', gap: '4px' }}>
              <div style={{ fontWeight: 700, fontSize: '24px' }}>{batch ? buildBatchTitle(batch) : 'Kassabon'}</div>
              <div style={{ color: '#2e7d4d' }}>{batch?.purchase_date || 'Onbekende datum'} · {batch?.store_label || batch?.store_name || providerLabel(activeProvider)}</div>
              <div style={{ color: '#2e7d4d' }}>Status: {batch ? batchStatusLabel(batch.import_status) : 'Laden'} · {summaryCounts.total} regels · Vereenvoudigingsniveau: {simplificationLevelLabel}</div>
            </div>
            <div style={{ display: 'flex', gap: '12px', flexWrap: 'wrap' }}>
              <Button variant="secondary" onClick={handlePrimaryProcessClick} disabled={isProcessingBatch}>Naar voorraad</Button>
            </div>
          </div>

          <div style={{ color: '#2e7d4d' }}>Totaal: {summaryCounts.total} · Klaar: {summaryCounts.ready} · Actie nodig: {summaryCounts.action_needed} · Verwerkt: {summaryCounts.processed}</div>

          {error ? <div className="rz-inline-feedback rz-inline-feedback--error">{error}</div> : null}
          {status ? <div className="rz-inline-feedback rz-inline-feedback--success">{status}</div> : null}
          {lastProcessResult ? (
            <div className="rz-inline-feedback rz-inline-feedback--success">
              Verwerkt: <strong>{lastProcessResult.processed_count || 0}</strong> · Overgeslagen: <strong>{lastProcessResult.skipped_count || 0}</strong> · Mislukt: <strong>{lastProcessResult.failed_count || 0}</strong>
            </div>
          ) : null}

          <div className="rz-table-wrapper">
            <table className="rz-table rz-store-workbench-table" style={{ minWidth: '980px' }}>
              <thead>
                <tr className="rz-table-header">
                  <th style={{ width: '44px' }}>
                    <input type="checkbox" checked={allVisibleSelected} onChange={toggleSelectAllVisible} aria-label="Selecteer alle zichtbare regels" />
                  </th>
                  <th>Bonartikel</th>
                  <th className="rz-num">Aantal</th>
                  <th>Gekoppeld artikel</th>
                  <th>Locatie</th>
                  <th className="rz-num">Prijs</th>
                </tr>
                <tr className="rz-table-filters">
                  <th />
                  <th>
                    <input className="rz-input rz-inline-input" type="text" placeholder="Filter" value={searchValue} onChange={(event) => setSearchValue(event.target.value)} aria-label="Filter op bonartikel of gekoppeld artikel" />
                  </th>
                  <th />
                  <th>
                    <select className="rz-input rz-inline-input" value={mappingFilter} onChange={(event) => setMappingFilter(event.target.value)}>
                      {MAPPING_FILTERS.map((filter) => <option key={filter.key} value={filter.key}>{filter.label}</option>)}
                    </select>
                  </th>
                  <th>
                    <select className="rz-input rz-inline-input" value={locationFilter} onChange={(event) => setLocationFilter(event.target.value)}>
                      {LOCATION_FILTERS.map((filter) => <option key={filter.key} value={filter.key}>{filter.label}</option>)}
                    </select>
                  </th>
                  <th />
                </tr>
              </thead>
              <tbody>
                {filteredLineUiStates.length === 0 ? (
                  <tr>
                    <td colSpan={6}>Geen regels in deze selectie.</td>
                  </tr>
                ) : filteredLineUiStates.map((entry) => {
                  const { line, draft, statusLabel: currentStatusLabel } = entry
                  const lineBusy = busyLineId === line.id || isProcessingBatch
                  const selected = selectedLineIds.includes(line.id)
                  return (
                    <tr key={line.id} className={`rz-store-workbench-row ${selected ? 'rz-row-selected' : ''} ${entry.statusKey === 'ready' ? 'is-ready' : ''} ${selected && entry.statusKey !== 'ready' ? 'is-selected-incomplete' : ''} ${entry.statusKey === 'ignored' ? 'is-ignored' : ''}`}>
                      <td>
                        <input type="checkbox" checked={selected} onChange={() => toggleLineSelection(line.id)} aria-label={`Selecteer ${line.article_name_raw}`} />
                      </td>
                      <td><div className="rz-store-primary">{line.article_name_raw}</div></td>
                      <td className="rz-num"><div className="rz-store-amount">{formatQuantity(line.quantity_raw, line.unit_raw)}</div></td>
                      <td>
                        <StoreArticleSelector
                          lineId={line.id}
                          lineName={line.article_name_raw}
                          selectedArticleId={draft.articleId || ''}
                          articleOptions={articleOptions}
                          disabled={lineBusy}
                          onChange={(nextArticleId) => persistLineDraft(line, { articleId: nextArticleId ?? '' })}
                          onClearArticle={() => persistLineDraft(line, { articleId: '' })}
                          onCreateArticle={(articleName) => handleCreateArticleFromLine(line.id, articleName)}
                          canCreateArticle={Boolean(household?.is_household_admin)}
                        />
                      </td>
                      <td>
                        <select
                          className="rz-input rz-store-select"
                          value={draft.locationId || ''}
                          disabled={lineBusy}
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
                      <td className="rz-num">{line.line_price_raw != null ? `€ ${line.line_price_raw.toFixed(2)}` : '-'}</td>
                    </tr>
                  )
                })}
              </tbody>
            </table>
          </div>

          {processConfirm ? (
            <div className="rz-modal-backdrop" role="presentation">
              <div className="rz-modal-card" role="dialog" aria-modal="true" aria-labelledby="process-selected-title">
                <h3 id="process-selected-title" className="rz-modal-title">Niet alle geselecteerde regels zijn compleet</h3>
                <p className="rz-modal-text">{processConfirm.readyCount} geselecteerde regel(s) zijn klaar voor verwerking en {processConfirm.incompleteCount} regel(s) missen nog artikel of locatie.</p>
                <div className="rz-modal-actions">
                  <Button variant="secondary" type="button" onClick={() => setProcessConfirm(null)} disabled={isProcessingBatch}>Annuleren</Button>
                  <Button variant="primary" type="button" onClick={() => handleProcessSelected('ready_only')} disabled={isProcessingBatch || processConfirm.readyCount === 0}>Verwerk alleen complete regels</Button>
                </div>
              </div>
            </div>
          ) : null}
        </div>
      </>
    ),
    Diagnose: (
      <div style={{ display: 'grid', gap: '12px' }}>
        <div><strong>Vereenvoudigingsniveau:</strong> {simplificationLevelLabel}</div>
        <div><strong>Huishoudinstelling:</strong> {detailValue(household?.default_consume_mode || household?.consume_mode || 'Uit')}</div>
        <div><strong>Batchstatus:</strong> {batch ? batchStatusLabel(batch.import_status) : '-'}</div>
        <div><strong>Laatst resultaat:</strong> {lastProcessResult ? `Verwerkt ${lastProcessResult.processed_count || 0} · Overgeslagen ${lastProcessResult.skipped_count || 0} · Mislukt ${lastProcessResult.failed_count || 0}` : 'Nog geen verwerking in deze sessie'}</div>
      </div>
    ),
  }

  const content = (
    <ScreenCard>
      {isLoading ? (
        <div>Bongegevens laden…</div>
      ) : batch ? (
        <Tabs tabs={['Bonregels', 'Diagnose']}>
          {(activeTab) => tabContent[activeTab]}
        </Tabs>
      ) : (
        <div>Geen kassabon beschikbaar.</div>
      )}
    </ScreenCard>
  )

  if (embedded) return content

  return (
    <AppShell title={batch ? buildBatchTitle(batch) : 'Kassabon'} showExit={false}>
      {content}
    </AppShell>
  )
}

export default function StoreBatchDetailPage() {
  return <StoreBatchDetailContent />
}
