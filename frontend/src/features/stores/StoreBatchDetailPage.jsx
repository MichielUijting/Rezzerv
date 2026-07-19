import { Fragment, useEffect, useMemo, useRef, useState } from 'react'
import { useNavigate, useParams } from 'react-router-dom'
import AppShell from '../../app/AppShell'
import ScreenCard from '../../ui/ScreenCard'
import Table from '../../ui/Table'
import Tabs from '../../ui/Tabs'
import Button from '../../ui/Button'
import { getStoreImportSimplificationLabel } from '../settings/services/storeImportSimplificationService'
import { nextSortState, sortItems, sortOptionObjects } from '../../ui/sorting'
import { buildTableWidth, ResizableHeaderCell, useResizableColumnWidths } from '../../ui/resizableTable.jsx'
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
import useDismissOnComponentClick from '../../lib/useDismissOnComponentClick.js'
import { useAppFeedback } from '../../ui/AppFeedbackProvider'

const STATUS_FILTERS = [
  { key: 'all', label: 'Alles' },
  { key: 'ready', label: 'Klaar' },
  { key: 'action_needed', label: 'Actie nodig' },
  { key: 'ignored', label: 'Genegeerd' },
  { key: 'processed', label: 'Verwerkt' },
]


const MAPPING_FILTERS = sortOptionObjects([
  { key: 'all', label: 'Alles' },
  { key: 'known', label: 'Bekende mapping' },
  { key: 'new', label: 'Nieuwe mapping' },
  { key: 'unknown', label: 'Onbekend artikel' },
])

const LOCATION_FILTERS = sortOptionObjects([
  { key: 'all', label: 'Alles' },
  { key: 'filled', label: 'Locatie ingevuld' },
  { key: 'missing', label: 'Locatie ontbreekt' },
])

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

function formatReceiptLineLabel(value) {
  const normalized = String(value || '').trim()
  if (!normalized) return '-'
  return normalized
    .toLocaleLowerCase('nl-NL')
    .replace(/(^|[\s\-/])(\p{L})/gu, (match, prefix, letter) => `${prefix}${letter.toLocaleUpperCase('nl-NL')}`)
}




function standardProductLabel(line) {
  return String(
    line?.matched_global_product_name ||
    line?.global_product_name ||
    line?.standard_product_name ||
    line?.standardized_article_name ||
    ''
  ).trim()
}

function standardProductDetail(line) {
  return standardProductLabel(line)
}


function firstTextValue(...values) {
  for (const value of values) {
    if (value == null) continue
    if (typeof value === 'object') {
      const nested = firstTextValue(value.name, value.label, value.title)
      if (nested) return nested
      continue
    }
    const text = String(value).trim()
    if (text) return text
  }
  return ''
}


function buildActiveLocationOptions(spacesData, sublocationsData) {
  const activeSpaces = Array.isArray(spacesData?.items) ? spacesData.items.filter((item) => Boolean(item?.active)) : []
  const activeSublocations = Array.isArray(sublocationsData?.items) ? sublocationsData.items.filter((item) => Boolean(item?.active)) : []
  const sublocationsBySpaceId = new Map()

  activeSublocations.forEach((item) => {
    const key = String(item?.space_id || '')
    if (!key) return
    const current = sublocationsBySpaceId.get(key) || []
    current.push(item)
    sublocationsBySpaceId.set(key, current)
  })

  const rows = []
  activeSpaces.forEach((space) => {
    const spaceId = String(space?.id || '')
    const spaceName = String(space?.naam || '').trim()
    if (!spaceId || !spaceName) return

    const linked = sortOptionObjects(sublocationsBySpaceId.get(spaceId) || [], (item) => item?.naam || '')

    rows.push({
      id: spaceId,
      label: spaceName,
      type: 'space',
      space_id: spaceId,
      sublocation_id: '',
      has_sublocations: linked.length > 0,
    })

    linked.forEach((sublocation) => {
      const sublocationId = String(sublocation?.id || '')
      const sublocationName = String(sublocation?.naam || '').trim()
      if (!sublocationId || !sublocationName) return

      rows.push({
        id: sublocationId,
        label: `${spaceName} / ${sublocationName}`,
        type: 'sublocation',
        space_id: spaceId,
        sublocation_id: sublocationId,
        parent_label: spaceName,
        sublocation_label: sublocationName,
        has_sublocations: false,
      })
    })
  })

  return sortOptionObjects(rows, (location) => location?.label || '')
}

function spaceLocationOptions(locationOptions) {
  const bySpace = new Map()
  ;(locationOptions || []).forEach((location) => {
    if (location?.type !== 'space') return
    bySpace.set(String(location.space_id || location.id), location)
  })
  return sortOptionObjects([...bySpace.values()], (location) => location?.label || '')
}

function sublocationOptionsForSpace(locationOptions, spaceId) {
  const key = String(spaceId || '')
  return sortOptionObjects(
    (locationOptions || []).filter((location) => location?.type === 'sublocation' && String(location.space_id || '') === key),
    (location) => location?.sublocation_label || location?.label || ''
  )
}

function deriveLineSelectionState({ draft, validLocationIds, processingStatus }) {
  const effectiveArticleId = String(draft?.articleId || '')
  const effectiveLocationId = String(draft?.locationId || '')
  const hasValidArticle = Boolean(effectiveArticleId)
  const hasValidLocation = Boolean(effectiveLocationId) && validLocationIds.has(effectiveLocationId)
  const isProcessable = hasValidArticle && hasValidLocation && processingStatus !== 'processed'
  return {
    effectiveArticleId,
    effectiveLocationId,
    hasValidArticle,
    hasValidLocation,
    isProcessable,
  }
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
  const [processResultOverlay, setProcessResultOverlay] = useState('')
  const [lastProcessResult, setLastProcessResult] = useState(null)
  const [batchDiagnostics, setBatchDiagnostics] = useState(null)
  const [lineDrafts, setLineDrafts] = useState({})
  const [lineSaveState, setLineSaveState] = useState({})
  const [selectedLineIds, setSelectedLineIds] = useState([])
  const [activeSummaryFilter, setActiveSummaryFilter] = useState('all')
  const [searchValue, setSearchValue] = useState('')
  const [locationPickerLineId, setLocationPickerLineId] = useState('')
  const [locationPickerSearch, setLocationPickerSearch] = useState('')
  const [locationPickerMode, setLocationPickerMode] = useState('single')
  const [activeLocationSpaceId, setActiveLocationSpaceId] = useState('')
  const [pendingDefaultLocationChoice, setPendingDefaultLocationChoice] = useState(null)
  const locationHoverTimerRef = useRef(null)

  useDismissOnComponentClick([() => setStatus(''), () => setError(''), () => setProcessFeedback('')], Boolean(status || error || processFeedback))
  const [statusFilter, setStatusFilter] = useState('all')
  const [mappingFilter, setMappingFilter] = useState('all')
  const [locationFilter, setLocationFilter] = useState('all')
  const [tableSort, setTableSort] = useState({ key: 'bonartikel', direction: 'asc' })
  const [processConfirm, setProcessConfirm] = useState(null)
  const processFeedbackTimer = useRef(null)
  const storeBatchTableColumns = useMemo(() => ([
    { key: 'select', width: 44 },
    { key: 'bonartikel', width: 240 },
    { key: 'locatie', width: 260 },
    { key: 'aantal', width: 100 },
    { key: 'gekoppeld', width: 280 },
    { key: 'standaardartikel', width: 260 },
  ]), [])
  const lineColumnDefaults = useMemo(() => Object.fromEntries(storeBatchTableColumns.map(({ key, width }) => [key, width])), [storeBatchTableColumns])
  const { widths: lineColumnWidths, startResize: startLineResize } = useResizableColumnWidths(lineColumnDefaults)

  const providersByCode = useMemo(
    () => Object.fromEntries(providers.map((provider) => [provider.code, provider])),
    [providers],
  )

  const activeProviderCode = batch?.store_provider_code || null
  const activeProvider = activeProviderCode ? providersByCode[activeProviderCode] || null : null
  const validLocationIds = useMemo(() => new Set(locationOptions.map((location) => String(location.id))), [locationOptions])
  const isViewer = Boolean(household?.is_viewer)


  const { showFeedback } = useAppFeedback()

  function showUitpakkenFeedback(variant, message, options = {}) {
    const normalizedVariant = String(variant || 'info').trim().toLowerCase() || 'info'
    const normalizedMessage = String(message || '').trim()
    if (!normalizedMessage) return

    showFeedback({
      variant: normalizedVariant,
      title: normalizedVariant === 'error'
        ? 'Fout'
        : normalizedVariant === 'warning'
          ? 'Let op'
          : normalizedVariant === 'success'
            ? 'Gelukt'
            : 'Melding',
      message: normalizedMessage,
      dedupeKey: options.key || `uitpakken-${normalizedVariant}-${normalizedMessage}`,
      dedupeMs: options.dedupeMs ?? 1200,
    })
  }

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
      if ((line.processing_status || 'pending') !== 'processed') nextLineIds.push(line.id)
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
    setBatchDiagnostics(null)
    return null
  }

  async function refreshLocationOptions() {
    const [spacesData, sublocationsData] = await Promise.all([
      fetchJson('/api/spaces?_ts=' + Date.now()).catch(() => ({ items: [] })),
      fetchJson('/api/sublocations?_ts=' + Date.now()).catch(() => ({ items: [] })),
    ])
    const nextLocations = buildActiveLocationOptions(spacesData, sublocationsData)
    setLocationOptions(nextLocations)
    return nextLocations
  }

  function closeLocationPicker() {
    if (locationHoverTimerRef.current) {
      window.clearTimeout(locationHoverTimerRef.current)
      locationHoverTimerRef.current = null
    }
    setLocationPickerLineId('')
    setLocationPickerSearch('')
    setLocationPickerMode('single')
    setActiveLocationSpaceId('')
  }

  function activateLocationSpaceDelayed(spaceId) {
    const nextSpaceId = String(spaceId || '')
    if (locationHoverTimerRef.current) {
      window.clearTimeout(locationHoverTimerRef.current)
    }
    locationHoverTimerRef.current = window.setTimeout(() => {
      setActiveLocationSpaceId(nextSpaceId)
    }, 500)
  }

  function activateLocationSpaceNow(spaceId) {
    if (locationHoverTimerRef.current) {
      window.clearTimeout(locationHoverTimerRef.current)
      locationHoverTimerRef.current = null
    }
    setActiveLocationSpaceId(String(spaceId || ''))
  }

  async function openLocationPicker(lineId) {
    setLocationPickerMode('single')
    setLocationPickerLineId(String(lineId))
    setLocationPickerSearch('')
    if (household?.id) {
      await refreshLocationOptions()
    }
  }

  async function openBulkLocationPicker() {
    if (selectedLineIds.length === 0) {
      setError('Selecteer eerst minstens één bonregel.')
      return
    }
    const selectedSet = new Set(selectedLineIds)
    const targetEntries = lineUiStates.filter((entry) => selectedSet.has(entry.line.id) && entry.processingStatus !== 'processed')
    if (targetEntries.length === 0) {
      setError('Er zijn geen geselecteerde open bonregels om een locatie op toe te passen.')
      return
    }
    setLocationPickerMode('bulk')
    setLocationPickerLineId('bulk')
    setLocationPickerSearch('')
    if (household?.id) {
      await refreshLocationOptions()
    }
  }

  function locationLabelForDraft(draft) {
    return locationOptions.find((location) => String(location.id) === String(draft.locationId || ''))?.label || ''
  }

  function filteredLocationOptions() {
    const needle = locationPickerSearch.trim().toLowerCase()
    const spaces = spaceLocationOptions(locationOptions)
    if (!needle) return spaces.slice(0, 12)
    return spaces
      .filter((location) => String(location.label || '').toLowerCase().includes(needle))
      .slice(0, 12)
  }

  function activeSublocationOptions() {
    return sublocationOptionsForSpace(locationOptions, activeLocationSpaceId)
  }

  const canManageLocations = !isViewer

  function openLocationManagement() {
    window.location.href = '/instellingen/locaties'
  }

  async function applyPickedLocation(locationId) {
    const nextLocationId = String(locationId ?? '')

    if (locationPickerMode === 'bulk') {
      const selectedSet = new Set(selectedLineIds)
      const targetEntries = lineUiStates.filter((entry) => selectedSet.has(entry.line.id) && entry.processingStatus !== 'processed')
      if (targetEntries.length === 0) {
        setError('Er zijn geen geselecteerde open bonregels om bij te werken.')
        closeLocationPicker()
        return
      }

      for (const entry of targetEntries) {
        await persistLineDraft(entry.line, { locationId: nextLocationId }, { suppressSuccessFeedback: true })
      }

      setStatus(nextLocationId
        ? `Locatie toegepast op ${targetEntries.length} geselecteerde regel(s).`
        : `Locatie verwijderd bij ${targetEntries.length} geselecteerde regel(s).`
      )
      closeLocationPicker()
      return
    }

    const pickerEntry = lineUiStates.find((entry) => String(entry.line.id) === String(locationPickerLineId))
    if (!pickerEntry) {
      closeLocationPicker()
      return
    }

    const hasArticle = Boolean(String(pickerEntry.draft?.articleId || pickerEntry.line?.matched_household_article_id || '').trim())

    if (hasArticle && nextLocationId) {
      setPendingDefaultLocationChoice({
        lineId: pickerEntry.line.id,
        locationId: nextLocationId,
      })
      closeLocationPicker()
      return
    }

    await persistLineDraft(
      pickerEntry.line,
      { locationId: nextLocationId },
      { defaultLocationPolicy: 'line_only' }
    )
    closeLocationPicker()
  }

  async function confirmDefaultLocationChoice(defaultLocationPolicy) {
    const pendingChoice = pendingDefaultLocationChoice
    if (!pendingChoice) return

    const pendingEntry = lineUiStates.find(
      (entry) => String(entry.line.id) === String(pendingChoice.lineId)
    )

    setPendingDefaultLocationChoice(null)

    if (!pendingEntry) return

    await persistLineDraft(
      pendingEntry.line,
      { locationId: pendingChoice.locationId },
      { defaultLocationPolicy }
    )
  }

  function cancelDefaultLocationChoice() {
    setPendingDefaultLocationChoice(null)
  }

  async function persistLineDraft(line, patch = {}, options = {}) {
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
          status: 'idle',
          message: '',
          error: '',
          currentArticleId: originalArticleId,
          currentLocationId: originalLocationId,
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
          body: JSON.stringify({
            target_location_id: nextLocationId || null,
            default_location_policy: options.defaultLocationPolicy || 'line_only',
          }),
        })
      }
      await refreshBatch(batch.batch_id)
      await refreshLocationOptions()
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
      if (!options.suppressSuccessFeedback) {
        showUitpakkenFeedback(
          'success',
          articleChanged && locationChanged
            ? 'Artikel en locatie bijgewerkt.'
            : articleChanged
              ? 'Artikelkoppeling bijgewerkt.'
              : 'Locatie bijgewerkt.',
          { key: `uitpakken-line-saved-${String(line.id)}-${Date.now()}` }
        )
      }
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

      const [providerData, backendArticles, spacesData, sublocationsData, loadedBatch] = await Promise.all([
        fetchJson('/api/store-providers'),
        fetchJson('/api/store-review-articles').catch(() => articleFallbackOptions),
        fetchJson('/api/spaces?_ts=' + Date.now()).catch(() => ({ items: [] })),
        fetchJson('/api/sublocations?_ts=' + Date.now()).catch(() => ({ items: [] })),
        fetchJson(`/api/purchase-import-batches/${batchId}`),
      ])

      setProviders(providerData)
      setArticleOptions(Array.isArray(backendArticles) && backendArticles.length ? sortOptionObjects(backendArticles, (article) => articleLabel(article)) : articleFallbackOptions)
      setLocationOptions(buildActiveLocationOptions(spacesData, sublocationsData))
      setBatch(loadedBatch)
      setBatchDiagnostics(null)
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
    const readyEntries = selectedEntries.filter((entry) => entry.isReadyForProcessing)
    const incompleteEntries = selectedEntries.filter((entry) => !entry.isReadyForProcessing)
    if (incompleteEntries.length > 0) {
      setProcessConfirm({ readyCount: readyEntries.length, incompleteCount: incompleteEntries.length })
      return
    }
    handleProcessSelected('selected_only')
  }


  function handleExportSelected() {
    if (!batch || selectedLineIds.length === 0) return
    const selectedSet = new Set(selectedLineIds.map((id) => String(id)))
    const rows = lineUiStates.filter((entry) => selectedSet.has(String(entry.line.id)))
    const header = ['Bonartikel', 'Artikelgroep', 'Locatie', 'Aantal', 'Universeel artikel', 'Status']
    const csvRows = rows.map((entry) => {
      const articleName = entry.line.resolved_household_article_name || articleLabel(articleOptions.find((option) => String(option.id) === String(entry.draft.articleId))) || ''
      const locationLabel = locationOptions.find((location) => String(location.id) === String(entry.draft.locationId))?.label || ''
      return [
        entry.line.article_name_raw || '',
        articleName,
        locationLabel,
        formatQuantity(entry.line.quantity_raw, entry.line.unit_raw),
        standardProductLabel(entry.line),
        entry.statusLabel || '',
      ]
    })
    const csv = [header, ...csvRows]
      .map((row) => row.map((value) => `"${String(value ?? '').replace(/"/g, '""')}"`).join(';'))
      .join('\n')
    window.__rezzervLastDownload = {
      filename: 'rezzerv-kassabondetail.csv',
      csv,
      rowCount: rows.length,
      source: 'receipt-detail',
    }
    const blob = new Blob([csv], { type: 'text/csv;charset=utf-8;' })
    const url = window.URL.createObjectURL(blob)
    const link = document.createElement('a')
    link.href = url
    link.download = 'rezzerv-kassabondetail.csv'
    document.body.appendChild(link)
    link.click()
    link.remove()
    window.URL.revokeObjectURL(url)
  }

  async function processBatchNow(mode = 'ready_only') {
    if (!batch) return
    if (isViewer) {
      setError('Kijkers mogen kassabonnen wel opvoeren, maar niet naar voorraad verwerken.')
      return
    }
    setIsProcessingBatch(true)
    setError('')
    setStatus('')
    setLastProcessResult(null)
    try {
      const lineNameById = Object.fromEntries((batch.lines || []).map((line) => [line.id, line.article_name_raw]))
      const result = await fetchJson(`/api/purchase-import-batches/${batch.batch_id}/process`, {
        method: 'POST',
        body: JSON.stringify({ processed_by: 'ui', mode }),
      })
      await refreshBatch(batch.batch_id)
      await refreshLocationOptions()
      setLastProcessResult(result)
      setBatchDiagnostics(result?.diagnostics || null)
      showProcessFeedback('Verwerkt!')
      const processed = (result.results || []).filter((item) => item.status === 'processed').map((item) => lineNameById[item.line_id]).filter(Boolean)
      const skipped = (result.results || []).filter((item) => item.status === 'skipped').map((item) => lineNameById[item.line_id]).filter(Boolean)
      const failed = (result.results || []).filter((item) => item.status === 'failed').map((item) => lineNameById[item.line_id]).filter(Boolean)
      const parts = []
      if (processed.length) parts.push(`Verwerkt: ${processed.join(', ')}`)
      if (skipped.length) parts.push(`Overgeslagen: ${skipped.join(', ')}`)
      if (failed.length) parts.push(`Mislukt: ${failed.join(', ')}`)
      if (!parts.length) {
        const processedCount = result.processed_count || 0
        const skippedCount = result.skipped_count || 0
        const failedCount = result.failed_count || 0
        parts.push(`Verwerkt: ${processedCount}`)
        parts.push(`Overgeslagen: ${skippedCount}`)
        parts.push(`Mislukt: ${failedCount}`)
      }
      setProcessResultOverlay(parts.join(' · '))
      setSelectedLineIds((current) => current.filter((id) => {
        const outcome = (result.results || []).find((item) => item.line_id === id)
        return !(outcome && outcome.status === 'processed')
      }))
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
    const selectedSet = new Set(selectedLineIds)
    return lines.map((line) => {
      const draft = getDraftValues(line)
      const saveState = lineSaveState[line.id] || { dirty: false, status: 'idle', message: '', error: '' }
      const processingStatus = line.processing_status || 'pending'
      const reviewDecision = line.review_decision || 'pending'
      const isSelected = selectedSet.has(line.id)
      const selectionState = deriveLineSelectionState({ draft, validLocationIds, processingStatus })
      const { effectiveArticleId, hasValidArticle, hasValidLocation, isProcessable } = selectionState

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
      } else if (reviewDecision === 'ignored' && !isSelected) {
        statusKey = 'ignored'
        statusLabel = 'Genegeerd'
        statusReason = 'Door gebruiker overgeslagen.'
      } else if (reviewDecision === 'selected' || isSelected) {
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
        isSelected,
        hasValidArticle,
        hasValidLocation,
        statusKey,
        statusLabel,
        statusReason,
        mappingState,
        isReadyForProcessing: isProcessable,
        isSelectionIncomplete: isSelected && !isProcessable && processingStatus !== 'processed',
        searchText: [line.article_name_raw, line.brand_raw, standardProductLabel(line), standardProductDetail(line), line.resolved_household_article_name]
          .filter(Boolean)
          .join(' ')
          .toLowerCase(),
      }
    })
  }, [batch?.lines, lineSaveState, lineDrafts, selectedLineIds, validLocationIds])

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

  const visibleLineUiStates = useMemo(() => {
    const visible = filteredLineUiStates.filter((entry) => entry.processingStatus !== 'processed')
    return sortItems(visible, tableSort, {
      bonartikel: (entry) => entry.line.article_name_raw || '',
      aantal: (entry) => Number(entry.line.quantity_raw ?? 0),
      standaardartikel: (entry) => standardProductLabel(entry.line),
      gekoppeld: (entry) => entry.line.resolved_household_article_name || '',
      locatie: (entry) => (locationOptions.find((location) => String(location.id) === String(entry.draft.locationId || ''))?.label || ''),
    })
  }, [filteredLineUiStates, tableSort, locationOptions])

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
    closeLocationPicker()
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
    const visibleIds = visibleLineUiStates.map((entry) => entry.line.id)
    const visibleIdSet = new Set(visibleIds)
    const allSelected = visibleIds.length > 0 && visibleIds.every((id) => selectedLineIds.includes(id))
    setSelectedLineIds((current) => {
      const retained = current.filter((id) => !visibleIdSet.has(id))
      return allSelected ? retained : [...retained, ...visibleIds]
    })
  }





  const allVisibleSelected = visibleLineUiStates.length > 0 && visibleLineUiStates.every((entry) => selectedLineIds.includes(entry.line.id))

  const tabContent = {
    Bonregels: (
      <>
        <div style={{ display: 'grid', gap: '16px' }} data-testid="receipt-detail-page">
          <div style={{ display: 'flex', justifyContent: 'space-between', gap: '12px', flexWrap: 'wrap', alignItems: 'start' }}>
            <div style={{ display: 'grid', gap: '4px' }}>
                            <div style={{ color: '#2e7d4d' }}>{batch?.purchase_date || 'Onbekende datum'} · {batch?.store_label || batch?.store_name || providerLabel(activeProvider)}</div>
              <div style={{ color: '#2e7d4d' }}>Status: {batch ? batchStatusLabel(batch.import_status) : 'Laden'} · {summaryCounts.total} regels · Vereenvoudigingsniveau: {simplificationLevelLabel}</div>
            </div>
            <div style={{ display: 'flex', gap: '12px', flexWrap: 'wrap' }}>
              <Button variant="secondary" type="button" onClick={handleExportSelected} disabled={selectedLineIds.length === 0} data-testid="receipt-export-button">Exporteren</Button>
              <Button variant="secondary" type="button" onClick={openBulkLocationPicker} disabled={selectedLineIds.length === 0 || isProcessingBatch || isViewer} data-testid="receipt-bulk-location-button">Locatie toepassen</Button>
              <Button variant="secondary" onClick={handlePrimaryProcessClick} disabled={isProcessingBatch || isViewer} data-testid="receipt-process-button">Naar voorraad</Button>
            </div>
          </div>

          <div style={{ color: '#2e7d4d' }}>Totaal: {summaryCounts.total} · Klaar: {summaryCounts.ready} · Actie nodig: {summaryCounts.action_needed} · Verwerkt: {summaryCounts.processed}</div>

          <Table wrapperClassName="rz-store-batch-table-wrapper" tableClassName="rz-store-workbench-table rz-data-table--sticky-header rz-data-table--sticky-filters" dataTestId="receipt-lines-table" tableStyle={{ tableLayout: 'fixed', width: buildTableWidth(lineColumnWidths), minWidth: buildTableWidth(lineColumnWidths), '--rz-sticky-header-offset': '36px' }}>
              <colgroup>
                <col style={{ width: `${lineColumnWidths.select}px` }} />
                <col style={{ width: `${lineColumnWidths.bonartikel}px` }} />
                <col style={{ width: `${lineColumnWidths.locatie}px` }} />
                <col style={{ width: `${lineColumnWidths.aantal}px` }} />
                <col style={{ width: `${lineColumnWidths.gekoppeld}px` }} />
                <col style={{ width: `${lineColumnWidths.standaardartikel}px` }} />
              </colgroup>
              <thead>
                <tr className="rz-table-header">
                  <ResizableHeaderCell columnKey="select" widths={lineColumnWidths} onStartResize={startLineResize} style={{ width: '44px' }}>
                    <input type="checkbox" checked={allVisibleSelected} onChange={toggleSelectAllVisible} aria-label="Selecteer alle zichtbare regels" />
                  </ResizableHeaderCell>
                  <ResizableHeaderCell columnKey="bonartikel" widths={lineColumnWidths} onStartResize={startLineResize} className="rz-store-batch-col-item" sortable isSorted={tableSort.key === 'bonartikel'} sortDirection={tableSort.direction} onSort={(key) => setTableSort((current) => nextSortState(current, key, { bonartikel: 'asc', locatie: 'asc', aantal: 'desc', gekoppeld: 'asc', standaardartikel: 'asc' }))}>Bonartikel</ResizableHeaderCell>
                  <ResizableHeaderCell columnKey="locatie" widths={lineColumnWidths} onStartResize={startLineResize} className="rz-store-batch-col-location" sortable isSorted={tableSort.key === 'locatie'} sortDirection={tableSort.direction} onSort={(key) => setTableSort((current) => nextSortState(current, key, { bonartikel: 'asc', locatie: 'asc', aantal: 'desc', gekoppeld: 'asc', standaardartikel: 'asc' }))}>Locatie / sublocatie</ResizableHeaderCell>
                  <ResizableHeaderCell columnKey="aantal" widths={lineColumnWidths} onStartResize={startLineResize} className="rz-num rz-store-batch-col-quantity" sortable isSorted={tableSort.key === 'aantal'} sortDirection={tableSort.direction} onSort={(key) => setTableSort((current) => nextSortState(current, key, { bonartikel: 'asc', locatie: 'asc', aantal: 'desc', gekoppeld: 'asc', standaardartikel: 'asc' }))}>Aantal</ResizableHeaderCell>
                  <ResizableHeaderCell columnKey="gekoppeld" widths={lineColumnWidths} onStartResize={startLineResize} className="rz-store-batch-col-linked" sortable isSorted={tableSort.key === 'gekoppeld'} sortDirection={tableSort.direction} onSort={(key) => setTableSort((current) => nextSortState(current, key, { bonartikel: 'asc', locatie: 'asc', aantal: 'desc', gekoppeld: 'asc', standaardartikel: 'asc' }))}>Artikelgroep</ResizableHeaderCell>
                  <ResizableHeaderCell columnKey="standaardartikel" widths={lineColumnWidths} onStartResize={startLineResize} className="rz-store-batch-col-standard" sortable isSorted={tableSort.key === 'standaardartikel'} sortDirection={tableSort.direction} onSort={(key) => setTableSort((current) => nextSortState(current, key, { bonartikel: 'asc', locatie: 'asc', aantal: 'desc', gekoppeld: 'asc', standaardartikel: 'asc' }))}>Universeel artikel</ResizableHeaderCell>
                </tr>
                <tr className="rz-table-filters">
                  <th />
                  <th>
                    <input className="rz-input rz-inline-input" type="text" placeholder="Filter" value={searchValue} onChange={(event) => setSearchValue(event.target.value)} aria-label="Filter op bonartikel of artikelgroep" />
                  </th>
                  <th>
                    <select className="rz-input rz-inline-input" value={locationFilter} onChange={(event) => setLocationFilter(event.target.value)}>
                      {LOCATION_FILTERS.map((filter) => <option key={filter.key} value={filter.key}>{filter.label}</option>)}
                    </select>
                  </th>
                  <th />
                  <th>
                    <select className="rz-input rz-inline-input" value={mappingFilter} onChange={(event) => setMappingFilter(event.target.value)}>
                      {MAPPING_FILTERS.map((filter) => <option key={filter.key} value={filter.key}>{filter.label}</option>)}
                    </select>
                  </th>
                  <th />
                </tr>
              </thead>
              <tbody>
                {visibleLineUiStates.length === 0 ? (
                  <tr>
                    <td colSpan={6}>Geen open bonregels in deze selectie.</td>
                  </tr>
                ) : visibleLineUiStates.map((entry) => {
                  const { line, draft, statusLabel: currentStatusLabel } = entry
                  const lineBusy = busyLineId === line.id || isProcessingBatch
                  const selected = entry.isSelected
                  const selectedLocationLabel = locationLabelForDraft(draft)
                  const rowClassName = [
                    'rz-store-workbench-row',
                    entry.statusKey === 'ready' && !selected ? 'is-ready' : '',
                    entry.statusKey === 'ignored' && !selected ? 'is-ignored' : '',
                    selected && entry.isReadyForProcessing ? 'rz-row-selected' : '',
                    entry.isSelectionIncomplete ? 'is-selected-incomplete' : '',
                  ].filter(Boolean).join(' ')
                  return (
                    <tr key={line.id} className={rowClassName} data-testid={`receipt-line-${line.id}`}>
                      <td>
                        <input type="checkbox" checked={selected} onChange={() => toggleLineSelection(line.id)} aria-label={`Selecteer ${line.article_name_raw}`} data-testid={`receipt-line-select-${line.id}`} />
                      </td>
                      <td className="rz-store-batch-col-item"><div className="rz-store-primary" style={{ fontWeight: 400 }}>{formatReceiptLineLabel(line.article_name_raw)}</div><span data-testid={`receipt-line-status-${line.id}`} style={{ display: 'none' }}>{entry.statusKey}</span></td>
                      <td className="rz-store-batch-col-location">
                        <button
                          type="button"
                          className="rz-input rz-store-select"
                          data-testid={`receipt-line-location-select-${line.id}`}
                          disabled={lineBusy}
                          onClick={() => openLocationPicker(line.id)}
                          style={{ width: '100%', textAlign: 'left', cursor: lineBusy ? 'not-allowed' : 'pointer' }}
                        >
                          {selectedLocationLabel || 'Kies locatie'}
                        </button>
                      </td>
                      <td className="rz-num rz-store-batch-col-quantity"><div className="rz-store-amount">{formatQuantity(line.quantity_raw, line.unit_raw)}</div></td>
                      <td className="rz-store-batch-col-linked">
                        <div data-testid={`receipt-line-article-select-${line.id}`}><StoreArticleSelector
                          lineId={line.id}
                          lineName={line.article_name_raw}
                          selectedArticleId={draft.articleId || ''}
                          articleOptions={articleOptions}
                          disabled={lineBusy}
                          onChange={(nextArticleId) => persistLineDraft(line, { articleId: nextArticleId ?? '' })}
                          onClearArticle={() => persistLineDraft(line, { articleId: '' })}
                          onCreateArticle={(articleName) => handleCreateArticleFromLine(line.id, articleName)}
                          canCreateArticle={Boolean(household?.permissions?.['article.create'])}
                        /></div>
                      </td>
                      <td className="rz-store-batch-col-standard" title={standardProductDetail(line) || standardProductLabel(line)}>
                         <div className="rz-store-primary" data-testid={`receipt-line-standard-product-${line.id}`}>{standardProductLabel(line)}</div>
                       </td>
                    </tr>
                  )
                })}
              </tbody>
            </Table>

          {pendingDefaultLocationChoice ? (
            <div
              className="rz-modal-backdrop"
              role="presentation"
              onClick={cancelDefaultLocationChoice}
            >
              <div
                className="rz-modal-card"
                role="dialog"
                aria-modal="true"
                aria-labelledby="default-location-choice-title"
                onClick={(event) => event.stopPropagation()}
              >
                <h3 id="default-location-choice-title" className="rz-modal-title">
                  Standaardlocatie instellen
                </h3>
                <p className="rz-modal-text">
                  Wil je deze locatie voortaan als standaardlocatie voor dit artikel gebruiken?
                </p>
                <div className="rz-modal-actions">
                  <Button
                    variant="secondary"
                    type="button"
                    onClick={cancelDefaultLocationChoice}
                  >
                    Annuleren
                  </Button>
                  <Button
                    variant="secondary"
                    type="button"
                    onClick={() => confirmDefaultLocationChoice('line_only')}
                  >
                    Alleen voor deze bonregel
                  </Button>
                  <Button
                    variant="primary"
                    type="button"
                    onClick={() => confirmDefaultLocationChoice('article_default')}
                  >
                    Als standaardlocatie gebruiken
                  </Button>
                </div>
              </div>
            </div>
          ) : null}
          {processResultOverlay ? (
            <div className="rz-modal-backdrop" role="presentation" onClick={() => setProcessResultOverlay('')}>
              <div
                className="rz-modal-card"
                role="dialog"
                aria-modal="true"
                aria-labelledby="process-result-title"
                onClick={(event) => event.stopPropagation()}
                style={{ width: 'min(560px, calc(100vw - 48px))' }}
              >
                <h3 id="process-result-title" className="rz-modal-title">Verwerking afgerond</h3>
                <p className="rz-modal-text">{processResultOverlay}</p>
                <div className="rz-modal-actions">
                  <Button variant="primary" type="button" onClick={() => setProcessResultOverlay('')}>
                    Sluiten
                  </Button>
                </div>
              </div>
            </div>
          ) : null}

          {locationPickerLineId ? (() => {
            const pickerIsBulk = locationPickerMode === 'bulk'
            const pickerEntry = pickerIsBulk ? null : lineUiStates.find((entry) => String(entry.line.id) === String(locationPickerLineId))
            if (!pickerIsBulk && !pickerEntry) return null

            const pickerOptions = filteredLocationOptions()
            const selectedSet = new Set(selectedLineIds)
            const pickerTargetCount = pickerIsBulk
              ? lineUiStates.filter((entry) => selectedSet.has(entry.line.id) && entry.processingStatus !== 'processed').length
              : 1
            const pickerLineBusy = isProcessingBatch || (!pickerIsBulk && busyLineId === pickerEntry.line.id)

            return (
              <div className="rz-modal-backdrop" role="presentation" onClick={closeLocationPicker}>
                <div
                  className="rz-modal-card"
                  role="dialog"
                  aria-modal="true"
                  aria-labelledby="location-picker-title"
                  onClick={(event) => event.stopPropagation()}
                  style={{ width: 'min(600px, calc(100vw - 48px))', maxHeight: '90vh', overflow: 'auto' }}
                >
                  <h3 id="location-picker-title" className="rz-modal-title">
                    {pickerIsBulk ? 'Locatie toepassen op geselecteerde regels' : 'Locatie / sublocatie kiezen'}
                  </h3>
                  <p className="rz-modal-text">
                    {pickerIsBulk
                      ? `${pickerTargetCount} geselecteerde open regel(s)`
                      : formatReceiptLineLabel(pickerEntry.line.article_name_raw)}
                  </p>
                  <input
                    className="rz-input"
                    type="text"
                    autoFocus
                    placeholder="Zoek locatie..."
                    value={locationPickerSearch}
                    onChange={(event) => setLocationPickerSearch(event.target.value)}
                    data-testid={pickerIsBulk ? 'receipt-bulk-location-search' : `receipt-line-location-search-${pickerEntry.line.id}`}
                  />
                  <div style={{ display: 'grid', gridTemplateColumns: 'minmax(0, 1fr) minmax(0, 1fr)', gap: '14px', overflow: 'hidden', marginTop: '12px' }}>
                    <div style={{ display: 'grid', gap: '8px', minWidth: 0 }}>
                      <div style={{ color: '#2e7d4d', fontSize: 14, fontWeight: 400, letterSpacing: '0' }}>Stap 1: locatie</div>
                      <div style={{ display: 'grid', gap: '6px', height: '246px', overflowY: 'auto', padding: '6px', border: '1px solid #d8e8de', borderRadius: '12px', background: '#f8fbf9', alignContent: 'start', gridAutoRows: '42px' }}>
                        {pickerOptions.length ? pickerOptions.map((location) => {
                          const sublocations = sublocationOptionsForSpace(locationOptions, location.space_id || location.id)
                          const hasSublocations = sublocations.length > 0
                          const active = String(activeLocationSpaceId || '') === String(location.space_id || location.id)
                          return (
                            <button
                              key={location.id}
                              type="button"
                              disabled={pickerLineBusy}
                              onMouseEnter={() => hasSublocations ? activateLocationSpaceDelayed(location.space_id || location.id) : null}
                              onFocus={() => hasSublocations ? activateLocationSpaceDelayed(location.space_id || location.id) : null}
                              onClick={() => {
                                if (hasSublocations) {
                                  activateLocationSpaceNow(location.space_id || location.id)
                                  return
                                }
                                applyPickedLocation(String(location.id))
                              }}
                              title={hasSublocations ? 'Kies een sublocatie binnen deze locatie' : 'Kies deze locatie'}
                              style={{
                                appearance: 'none',
                                width: '100%',
                                border: active ? '1px solid #2e7d4d' : '1px solid #d8e8de',
                                background: active ? '#e8f4ec' : '#ffffff',
                                color: '#163020',
                                borderRadius: '10px',
                                height: '42px',
                                padding: '0 12px',
                                display: 'flex',
                                alignItems: 'center',
                                justifyContent: 'space-between',
                                gap: '12px',
                                fontSize: 14,
                                fontWeight: 500,
                                lineHeight: 1.3,
                                textAlign: 'left',
                                cursor: pickerLineBusy ? 'not-allowed' : 'pointer',
                                boxShadow: active ? '0 0 0 1px rgba(46, 125, 77, 0.08)' : 'none',
                              }}
                            >
                              <span>{location.label}</span>
                              <span style={{ color: hasSublocations ? '#2e7d4d' : '#9aa8a0', fontSize: 14, fontWeight: 700 }}>
                                {hasSublocations ? '›' : ''}
                              </span>
                            </button>
                          )
                        }) : (
                          <div style={{ color: '#5f7a68', fontSize: 13, padding: '10px 12px' }}>Geen locatie gevonden.</div>
                        )}
                      </div>
                    </div>

                    <div style={{ display: 'grid', gap: '8px', minWidth: 0 }}>
                      <div style={{ color: '#2e7d4d', fontSize: 14, fontWeight: 400, letterSpacing: '0' }}>Stap 2: sublocatie</div>
                      <div style={{ display: 'grid', gap: '6px', height: '246px', overflowY: 'auto', padding: '6px', border: '1px solid #d8e8de', borderRadius: '12px', background: '#f8fbf9', alignContent: 'start', gridAutoRows: '42px' }}>
                        {activeSublocationOptions().length ? activeSublocationOptions().map((location) => (
                          <button
                            key={location.id}
                            type="button"
                            disabled={pickerLineBusy}
                            onClick={() => applyPickedLocation(String(location.id))}
                            style={{
                              appearance: 'none',
                              width: '100%',
                              border: '1px solid #d8e8de',
                              background: '#ffffff',
                              color: '#163020',
                              borderRadius: '10px',
                              height: '42px',
                              padding: '0 12px',
                              display: 'flex',
                              alignItems: 'center',
                              justifyContent: 'space-between',
                              gap: '12px',
                              fontSize: 14,
                              fontWeight: 500,
                              lineHeight: 1.3,
                              textAlign: 'left',
                              cursor: pickerLineBusy ? 'not-allowed' : 'pointer',
                            }}
                          >
                            <span>{location.sublocation_label || location.label}</span>
                            <span style={{ color: '#2e7d4d', fontSize: 14, fontWeight: 700 }}>✓</span>
                          </button>
                        )) : null}
                      </div>
                    </div>
                  </div>
                  <div className="rz-modal-actions">
                    {canManageLocations ? (
                      <Button variant="secondary" type="button" disabled={pickerLineBusy} onClick={openLocationManagement}>
                        Beheer locaties
                      </Button>
                    ) : null}
                    <Button
                      variant="secondary"
                      type="button"
                      disabled={pickerLineBusy}
                      onClick={() => applyPickedLocation('')}
                    >
                      Verwijderen
                    </Button>
                    <Button variant="secondary" type="button" onClick={closeLocationPicker}>
                      Sluiten
                    </Button>
                  </div>
                </div>
              </div>
            )
          })() : null}

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
      <div data-testid="receipt-detail-title" style={{ display: 'none' }}>
        {batch ? buildBatchTitle(batch) : 'Kassabon'}
      </div>
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
