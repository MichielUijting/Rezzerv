import { useEffect, useMemo, useRef, useState } from 'react'
import { useNavigate, useParams } from 'react-router-dom'
import AppShell from '../../app/AppShell'
import Card from '../../ui/Card'
import Button from '../../ui/Button'
import demoData from '../../demo-articles.json'
import { getStoreImportSimplificationLabel } from '../settings/services/storeImportSimplificationService'

function normalizeErrorMessage(value) {
  if (!value) return 'Verzoek mislukt'
  if (typeof value === 'string') return value
  if (Array.isArray(value)) {
    const first = value[0]
    if (typeof first === 'string') return first
    if (first && typeof first === 'object') {
      const message = first.msg || first.message || null
      if (message) return message
    }
    return 'Verzoek mislukt'
  }
  if (typeof value === 'object') {
    return value.detail || value.message || value.msg || 'Verzoek mislukt'
  }
  return 'Verzoek mislukt'
}

async function fetchJson(url, options = {}) {
  const response = await fetch(url, {
    headers: {
      'Content-Type': 'application/json',
      ...(options.headers || {}),
    },
    ...options,
  })

  const responseText = await response.text()
  const contentType = (response.headers.get('content-type') || '').toLowerCase()
  const looksLikeJson = contentType.includes('application/json') || /^\s*[\[{]/.test(responseText)

  let data = null
  if (responseText) {
    if (looksLikeJson) {
      try {
        data = JSON.parse(responseText)
      } catch (error) {
        if (!response.ok) {
          throw new Error('Winkelgegevens konden niet volledig worden geladen')
        }
        throw new Error('De server gaf ongeldige gegevens terug')
      }
    } else if (!response.ok) {
      throw new Error(normalizeErrorMessage(responseText) || 'Winkelgegevens konden niet volledig worden geladen')
    }
  }

  if (!response.ok) {
    throw new Error(normalizeErrorMessage(data?.detail || data || responseText))
  }

  return data
}

const articleFallbackOptions = demoData.articles.map((article) => ({
  id: String(article.id),
  name: article.name,
  brand: article.brand || '',
}))

function articleLabel(article) {
  return article.brand ? `${article.name} — ${article.brand}` : article.name
}

function StoreArticleSelector({
  lineId,
  lineName,
  selectedArticleId,
  articleOptions,
  disabled,
  onChange,
  onCreateArticle,
}) {
  const datalistId = `store-article-options-${lineId}`
  const optionsByLabel = useMemo(() => {
    const entries = articleOptions.map((article) => [articleLabel(article), String(article.id)])
    return new Map(entries)
  }, [articleOptions])
  const labelById = useMemo(() => {
    const entries = articleOptions.map((article) => [String(article.id), articleLabel(article)])
    return new Map(entries)
  }, [articleOptions])
  const [query, setQuery] = useState(selectedArticleId ? (labelById.get(String(selectedArticleId)) || '') : '')

  useEffect(() => {
    const nextValue = selectedArticleId ? (labelById.get(String(selectedArticleId)) || '') : ''
    setQuery(nextValue)
  }, [selectedArticleId, labelById])

  const normalizedQuery = query.trim().toLowerCase()
  const hasExactMatch = Boolean(normalizedQuery && Array.from(optionsByLabel.keys()).some((label) => label.trim().toLowerCase() === normalizedQuery))
  const canCreateArticle = Boolean(normalizedQuery) && !hasExactMatch && !selectedArticleId

  async function handleCreateArticle() {
    const baseName = query.trim() || lineName || ''
    const nextName = window.prompt('Nieuw artikel aanmaken', baseName)
    if (!nextName) return
    const created = await onCreateArticle(nextName)
    if (created?.name) {
      setQuery(articleLabel(created))
    }
  }

  function handleInputChange(event) {
    const nextQuery = event.target.value
    setQuery(nextQuery)
    if (!nextQuery) {
      onChange('')
      return
    }
    const matchedId = optionsByLabel.get(nextQuery)
    if (matchedId) {
      onChange(matchedId)
    }
  }

  function handleSelectChange(event) {
    const nextId = String(event.target.value || '')
    const nextLabel = nextId ? (labelById.get(nextId) || '') : ''
    setQuery(nextLabel)
    onChange(nextId)
  }

  return (
    <div className="rz-store-article-search" style={articleSearchStyle}>
      <input
        className="rz-input rz-store-article-search-input" style={articleSearchInputStyle}
        type="text"
        list={datalistId}
        value={query}
        placeholder="Kies artikel"
        disabled={disabled}
        onChange={handleInputChange}
      />
      <datalist id={datalistId}>
        {articleOptions.map((article) => (
          <option key={article.id} value={articleLabel(article)} />
        ))}
      </datalist>
      <select
        className="rz-input rz-store-select rz-store-select--hidden"
        style={{ display: 'none' }}
        data-store-article-select="true"
        value={selectedArticleId || ''}
        disabled={disabled}
        onChange={handleSelectChange}
        aria-hidden="true"
        tabIndex={-1}
      >
        <option value="">Kies artikel</option>
        {articleOptions.map((article) => (
          <option key={article.id} value={article.id}>{articleLabel(article)}</option>
        ))}
      </select>
      {canCreateArticle ? (
        <button
          type="button"
          className="rz-link-button"
          style={createArticleButtonStyle}
          disabled={disabled}
          onClick={handleCreateArticle}
        >
          Nieuw artikel aanmaken
        </button>
      ) : null}
    </div>
  )
}

function providerLabel(providerOrConnection) {
  return providerOrConnection?.store_provider_name || providerOrConnection?.name || providerOrConnection?.store_provider_code || providerOrConnection?.code || 'Winkel'
}

function providerStatusLabel(provider) {
  if (!provider) return 'niet beschikbaar'
  return `${provider.status} / ${provider.import_mode}`
}

function buildBatchTitle(batch) {
  const providerName = batch?.store_provider_name || batch?.store_name || 'Winkel'
  return `Kassabon ${providerName}`
}

function batchStatusLabel(value) {
  if (value === 'processed') return 'Verwerkt naar voorraad'
  if (value === 'partially_processed') return 'Gedeeltelijk verwerkt'
  if (value === 'failed') return 'Verwerking mislukt'
  if (value === 'reviewed') return 'Beoordeling afgerond'
  if (value === 'in_review') return 'In bewerking'
  return 'Nog te beoordelen'
}

function suggestionLabel(line) {
  if (line?.preparation_explanation) return line.preparation_explanation
  if (line?.suggestion_reason) return line.suggestion_reason
  if (line.is_auto_prefilled && (line.review_decision || 'pending') === 'selected' && line.matched_household_article_id && line.target_location_id) {
    return 'Automatisch voorbereid'
  }
  if (line.suggested_household_article_id || line.suggested_location_id) {
    return 'Controleer voorstel'
  }
  return 'Geen eerdere mapping gevonden'
}

function formatQuantity(value, unit) {
  return [value, unit].filter(Boolean).join(' ')
}

function deriveBatchUiState(batch) {
  const lines = Array.isArray(batch?.lines) ? batch.lines : []
  const visibleLines = lines.filter((line) => (line.processing_status || 'pending') !== 'processed')
  const selectedLines = visibleLines.filter((line) => (line.review_decision || 'pending') === 'selected')
  const readyLines = selectedLines.filter((line) => line.matched_household_article_id && line.target_location_id)
  const blockedLines = selectedLines.length - readyLines.length
  const pendingReviewCount = visibleLines.filter((line) => (line.review_decision || 'pending') === 'pending').length
  const summary = batch?.summary || {}
  const totalLines = summary.total || lines.length

  if ((batch?.import_status || '') === 'processed') {
    return {
      statusKey: 'processed',
      label: 'Verwerkt',
      actionLabel: 'Openen',
      actionType: 'open',
      rank: 99,
      progressText: totalLines > 0 ? `${summary.processed || 0} verwerkt` : 'Afgerond',
    }
  }

  if (blockedLines > 0) {
    return {
      statusKey: 'action_needed',
      label: 'Actie nodig',
      actionLabel: 'Hervatten',
      actionType: 'resume',
      rank: 0,
      progressText: `${readyLines.length} klaar / ${blockedLines} geblokkeerd`,
    }
  }

  if (selectedLines.length > 0 && pendingReviewCount === 0) {
    return {
      statusKey: 'ready',
      label: 'Klaar voor verwerking',
      actionLabel: 'Naar voorraad',
      actionType: 'process',
      rank: 1,
      progressText: `${readyLines.length} klaar om te verwerken`,
    }
  }

  if ((batch?.import_status || '') === 'in_review' || (batch?.import_status || '') === 'reviewed' || selectedLines.length > 0 || pendingReviewCount < visibleLines.length) {
    return {
      statusKey: 'in_progress',
      label: 'In bewerking',
      actionLabel: 'Hervatten',
      actionType: 'resume',
      rank: 2,
      progressText: visibleLines.length > 0 ? `${readyLines.length} klaar / ${Math.max(visibleLines.length - readyLines.length, 0)} open` : 'Beoordeling loopt',
    }
  }

  return {
    statusKey: 'open',
    label: 'Open',
    actionLabel: 'Openen',
    actionType: 'open',
    rank: 3,
    progressText: totalLines > 0 ? `${totalLines} regel(s) wachten op beoordeling` : 'Nog te beoordelen',
  }
}

function formatBatchLastChange(batch) {
  const rawValue = batch?.created_at || ''
  if (!rawValue) return 'Onbekend'
  const date = new Date(rawValue)
  if (Number.isNaN(date.getTime())) return rawValue
  return new Intl.DateTimeFormat('nl-NL', {
    day: '2-digit',
    month: '2-digit',
    year: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
  }).format(date)
}

export default function StoresPage() {
  const navigate = useNavigate()
  const { batchId: batchIdParam } = useParams()
  const detailBatchId = batchIdParam || ''
  const isBatchDetailRoute = Boolean(detailBatchId)
  const [household, setHousehold] = useState(null)
  const [providers, setProviders] = useState([])
  const [connections, setConnections] = useState([])
  const [openBatches, setOpenBatches] = useState([])
  const [activeBatch, setActiveBatch] = useState(null)
  const [articleOptions, setArticleOptions] = useState(articleFallbackOptions)
  const [locationOptions, setLocationOptions] = useState([])
  const [status, setStatus] = useState('')
  const [error, setError] = useState('')
  const [isLoading, setIsLoading] = useState(true)
  const [isConnecting, setIsConnecting] = useState(false)
  const [isPulling, setIsPulling] = useState(false)
  const [busyLineId, setBusyLineId] = useState('')
  const [isProcessingBatch, setIsProcessingBatch] = useState(false)
  const [busyBatchId, setBusyBatchId] = useState('')
  const [processFeedback, setProcessFeedback] = useState('')
  const [processWarning, setProcessWarning] = useState(null)
  const processFeedbackTimer = useRef(null)

  const providersByCode = useMemo(
    () => Object.fromEntries(providers.map((provider) => [provider.code, provider])),
    [providers],
  )

  const connectionsByProviderCode = useMemo(
    () => Object.fromEntries(connections.map((connection) => [connection.store_provider_code, connection])),
    [connections],
  )

  const primaryProvider = useMemo(
    () => providers[0] || null,
    [providers],
  )

  const activeProviderCode = activeBatch?.store_provider_code || primaryProvider?.code || null
  const activeProvider = activeProviderCode ? providersByCode[activeProviderCode] || null : null

  const validArticleIds = useMemo(() => new Set(articleOptions.map((article) => String(article.id))), [articleOptions])
  const validLocationIds = useMemo(() => new Set(locationOptions.map((location) => String(location.id))), [locationOptions])

  const visibleLines = useMemo(
    () => activeBatch?.lines?.filter((line) => (line.processing_status || 'pending') !== 'processed') || [],
    [activeBatch],
  )

  const selectedLines = visibleLines.filter((line) => (line.review_decision || 'selected') === 'selected')
  const linesMissingArticle = selectedLines.filter((line) => !line.matched_household_article_id).length
  const linesMissingLocation = selectedLines.filter((line) => !line.target_location_id || !validLocationIds.has(String(line.target_location_id))).length
  const canProcessBatch = Boolean(activeBatch && selectedLines.length > 0)
  const simplificationLevelLabel = getStoreImportSimplificationLabel(household?.store_import_simplification_level || 'gebalanceerd')
  const overviewBatchCount = batchItems.length
  const detailBatchUiState = activeBatch ? deriveBatchUiState(activeBatch) : null

  const batchItems = useMemo(() => {
    return (openBatches || []).map((batch) => ({
      ...batch,
      uiState: deriveBatchUiState(batch),
    })).sort((a, b) => {
      if (a.uiState.rank !== b.uiState.rank) return a.uiState.rank - b.uiState.rank
      return String(b.created_at || '').localeCompare(String(a.created_at || ''))
    })
  }, [openBatches])

  const connectedStoreItems = useMemo(() => {
    const itemsByCode = new Map()

    providers.forEach((provider) => {
      const code = provider?.code || ''
      if (!code) return
      itemsByCode.set(code, {
        code,
        provider,
        connection: connectionsByProviderCode[code] || null,
        name: provider.name || provider.code || 'Winkel',
      })
    })

    connections.forEach((connection) => {
      const code = connection?.store_provider_code || ''
      if (!code) return
      const existing = itemsByCode.get(code)
      const provider = existing?.provider || providersByCode[code] || null
      itemsByCode.set(code, {
        code,
        provider,
        connection,
        name: provider?.name || connection?.store_provider_name || code,
      })
    })

    return Array.from(itemsByCode.values()).sort((a, b) => a.name.localeCompare(b.name, 'nl'))
  }, [connections, connectionsByProviderCode, providers, providersByCode])

  async function refreshBatch(batchId) {
    const batch = await fetchJson(`/api/purchase-import-batches/${batchId}`)
    setActiveBatch(batch)
    setOpenBatches((current) => {
      const others = (current || []).filter((item) => item.batch_id !== batch.batch_id)
      return [...others, batch]
    })
    return batch
  }

  async function refreshLocationOptions(householdId) {
    if (!householdId) return []
    const backendLocations = await fetchJson(`/api/store-location-options?householdId=${encodeURIComponent(householdId)}&_ts=${Date.now()}`, { cache: 'no-store' }).catch(() => [])
    const nextLocations = Array.isArray(backendLocations) ? backendLocations : []
    setLocationOptions(nextLocations)
    return nextLocations
  }

  function showProcessFeedback(message) {
    if (processFeedbackTimer.current) window.clearTimeout(processFeedbackTimer.current)
    setProcessFeedback(message)
    processFeedbackTimer.current = window.setTimeout(() => setProcessFeedback(''), 2200)
  }

  async function getLatestBatchMeta(connectionId) {
    try {
      const latest = await fetchJson(`/api/store-connections/${connectionId}/latest-batch`)
      return latest?.batch_id ? latest : null
    } catch (err) {
      return null
    }
  }

  async function loadOpenBatches(connectionsToCheck, preferredBatchId = null) {
    const latestCandidates = (await Promise.all((connectionsToCheck || []).map((connection) => getLatestBatchMeta(connection.id))))
      .filter((item) => item?.batch_id && item.import_status !== 'processed')

    if (!latestCandidates.length) {
      setOpenBatches([])
      setActiveBatch(null)
      return []
    }

    const loadedBatches = (await Promise.all(latestCandidates.map((item) => fetchJson(`/api/purchase-import-batches/${item.batch_id}`).catch(() => null))))
      .filter(Boolean)

    setOpenBatches(loadedBatches)

    const sortedBatches = [...loadedBatches].sort((a, b) => {
      const aState = deriveBatchUiState(a)
      const bState = deriveBatchUiState(b)
      if (aState.rank !== bState.rank) return aState.rank - bState.rank
      return String(b.created_at || '').localeCompare(String(a.created_at || ''))
    })

    const nextBatchId = preferredBatchId && loadedBatches.some((batch) => batch.batch_id === preferredBatchId)
      ? preferredBatchId
      : (activeBatch?.batch_id && loadedBatches.some((batch) => batch.batch_id === activeBatch.batch_id)
        ? activeBatch.batch_id
        : null)

    const selectedBatch = nextBatchId
      ? loadedBatches.find((batch) => batch.batch_id === nextBatchId) || null
      : isBatchDetailRoute
        ? null
        : sortedBatches[0] || null

    setActiveBatch(selectedBatch)
    return loadedBatches
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

      const [providerData, connectionData, backendArticles, backendLocations] = await Promise.all([
        fetchJson('/api/store-providers'),
        fetchJson(`/api/store-connections?householdId=${encodeURIComponent(householdData.id)}`),
        fetchJson('/api/store-review-articles').catch(() => articleFallbackOptions),
        fetchJson(`/api/store-location-options?householdId=${encodeURIComponent(householdData.id)}&_ts=${Date.now()}`, { cache: 'no-store' }).catch(() => []),
      ])

      setProviders(providerData)
      setConnections(connectionData)
      setArticleOptions(Array.isArray(backendArticles) && backendArticles.length ? backendArticles : articleFallbackOptions)
      setLocationOptions(Array.isArray(backendLocations) ? backendLocations : [])

      await loadOpenBatches(connectionData, detailBatchId || null)
      if (detailBatchId) {
        try {
          await refreshBatch(detailBatchId)
        } catch (detailError) {
          setError(normalizeErrorMessage(detailError?.message) || 'De geselecteerde bon kon niet worden geladen.')
        }
      }
    } catch (err) {
      setError(normalizeErrorMessage(err?.message) || 'Winkelgegevens konden niet worden geladen.')
    } finally {
      setIsLoading(false)
    }
  }

  useEffect(() => {
    loadPageData()
    return () => {
      if (processFeedbackTimer.current) window.clearTimeout(processFeedbackTimer.current)
    }
  }, [detailBatchId])

  useEffect(() => {
    function handleRefresh() {
      if (household?.id) {
        refreshLocationOptions(household.id)
      }
    }

    window.addEventListener('focus', handleRefresh)
    document.addEventListener('visibilitychange', handleRefresh)
    return () => {
      window.removeEventListener('focus', handleRefresh)
      document.removeEventListener('visibilitychange', handleRefresh)
    }
  }, [household?.id])

  useEffect(() => {
    if (household?.id && activeBatch?.batch_id) {
      refreshLocationOptions(household.id)
    }
  }, [household?.id, activeBatch?.batch_id])

  async function handleConnect(providerCode, providerName) {
    if (!household || !providerCode) return
    setIsConnecting(true)
    setError('')
    setStatus('')
    try {
      const connection = await fetchJson('/api/store-connections', {
        method: 'POST',
        body: JSON.stringify({ household_id: household.id, store_provider_code: providerCode }),
      })
      const nextConnections = [...connections.filter((item) => item.id !== connection.id), connection]
      setConnections(nextConnections)
      await refreshLocationOptions(household.id)
      await loadOpenBatches(nextConnections)
      setStatus(`${providerName || providerCode} is gekoppeld aan dit huishouden.`)
    } catch (err) {
      setError(normalizeErrorMessage(err?.message) || `${providerName || providerCode} kon niet worden gekoppeld.`)
    } finally {
      setIsConnecting(false)
    }
  }

  async function handlePullPurchases(connection, providerName) {
    if (!connection) return
    setIsPulling(true)
    setError('')
    setStatus('')
    try {
      const existingBatchMeta = await getLatestBatchMeta(connection.id)
      if (existingBatchMeta?.batch_id && existingBatchMeta.import_status !== 'processed') {
        await refreshBatch(existingBatchMeta.batch_id)
        await loadOpenBatches(connections, existingBatchMeta.batch_id)
        setStatus(`De laatste open bon van ${providerName || 'de winkel'} is opnieuw geladen met het actuele gemaksniveau.`)
        await refreshLocationOptions(household.id)
        return
      }

      const pullResult = await fetchJson(`/api/store-connections/${connection.id}/pull-purchases`, {
        method: 'POST',
        body: JSON.stringify({ mock_profile: 'default' }),
      })
      await refreshBatch(pullResult.batch_id)
      const p = pullResult.prefill_summary || {}
      const fullyPrefilled = p.fully_prefilled || 0
      const articlePrefills = p.article_prefills || 0
      if (fullyPrefilled > 0 || articlePrefills > 0) {
        setStatus(`Nieuwe mockaankopen van ${providerName || 'de winkel'} zijn opgehaald. ${fullyPrefilled} regel(s) staan al klaar; ${articlePrefills} regel(s) hebben een artikelvoorstel.`)
      } else {
        setStatus(`Nieuwe mockaankopen van ${providerName || 'de winkel'} zijn opgehaald. Kies per regel wat naar voorraad mag.`)
      }
      const refreshedConnections = await fetchJson(`/api/store-connections?householdId=${encodeURIComponent(household.id)}`)
      setConnections(refreshedConnections)
      await loadOpenBatches(refreshedConnections, pullResult.batch_id)
      await refreshLocationOptions(household.id)
    } catch (err) {
      setError(normalizeErrorMessage(err?.message) || 'Aankopen konden niet worden opgehaald.')
    } finally {
      setIsPulling(false)
    }
  }

  async function handleReviewDecision(lineId, reviewDecision) {
    setBusyLineId(lineId)
    setError('')
    setStatus('')
    try {
      await fetchJson(`/api/purchase-import-lines/${lineId}/review`, {
        method: 'POST',
        body: JSON.stringify({ review_decision: reviewDecision }),
      })
      await refreshBatch(activeBatch.batch_id)
      await loadOpenBatches(connections, activeBatch.batch_id)
      setStatus('De beoordeling is opgeslagen.')
    } catch (err) {
      setError(normalizeErrorMessage(err?.message) || 'De beoordeling kon niet worden opgeslagen.')
    } finally {
      setBusyLineId('')
    }
  }

  async function handleMapLine(lineId, articleId) {
    setBusyLineId(lineId)
    setError('')
    setStatus('')
    try {
      await fetchJson(`/api/purchase-import-lines/${lineId}/map`, {
        method: 'POST',
        body: JSON.stringify({ household_article_id: articleId }),
      })
      await refreshBatch(activeBatch.batch_id)
      await loadOpenBatches(connections, activeBatch.batch_id)
      setStatus('De artikelkoppeling is opgeslagen.')
    } catch (err) {
      setError(normalizeErrorMessage(err?.message) || 'De artikelkoppeling kon niet worden opgeslagen.')
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
      await refreshBatch(activeBatch.batch_id)
      await loadOpenBatches(connections, activeBatch.batch_id)
      setStatus('Nieuw artikel aangemaakt en gekoppeld aan de bonregel.')
      return result?.article_option || null
    } catch (err) {
      setError(normalizeErrorMessage(err?.message) || 'Het nieuwe artikel kon niet worden aangemaakt.')
      return null
    } finally {
      setBusyLineId('')
    }
  }

  async function handleTargetLocation(lineId, targetLocationId) {
    setBusyLineId(lineId)
    setError('')
    setStatus('')
    try {
      await fetchJson(`/api/purchase-import-lines/${lineId}/target-location`, {
        method: 'POST',
        body: JSON.stringify({ target_location_id: targetLocationId || null }),
      })
      await refreshBatch(activeBatch.batch_id)
      await loadOpenBatches(connections, activeBatch.batch_id)
      await refreshLocationOptions(household?.id)
      setStatus('De voorkeurslocatie is opgeslagen.')
    } catch (err) {
      setError(normalizeErrorMessage(err?.message) || 'De voorkeurslocatie kon niet worden opgeslagen.')
    } finally {
      setBusyLineId('')
    }
  }

  async function processBatchNow(batchToProcess = activeBatch) {
    if (!batchToProcess) return
    setIsProcessingBatch(true)
    setBusyBatchId(batchToProcess.batch_id)
    setError('')
    setStatus('')
    try {
      const result = await fetchJson(`/api/purchase-import-batches/${batchToProcess.batch_id}/process`, {
        method: 'POST',
        body: JSON.stringify({ processed_by: 'ui', mode: 'selected_only' }),
      })
      showProcessFeedback('Verwerkt!')
      if (result.failed_count > 0) {
        setStatus(`Verwerking afgerond: ${result.processed_count} regel(s) verwerkt, ${result.failed_count} regel(s) mislukt.`)
      } else {
        setStatus(`Verwerking afgerond: ${result.processed_count} regel(s) zijn naar voorraad verwerkt.`)
      }
      const refreshedConnections = household?.id
        ? await fetchJson(`/api/store-connections?householdId=${encodeURIComponent(household.id)}`).catch(() => connections)
        : connections
      setConnections(refreshedConnections)
      await loadOpenBatches(refreshedConnections)
      if (isBatchDetailRoute) {
        navigate('/winkels')
      }
    } catch (err) {
      setError(normalizeErrorMessage(err?.message) || 'De batch kon niet naar voorraad worden verwerkt.')
    } finally {
      setIsProcessingBatch(false)
      setBusyBatchId('')
    }
  }

  async function handleSelectBatch(batchId) {
    setError('')
    setStatus('')
    navigate(`/winkels/batch/${batchId}`)
  }

  async function handlePrimaryBatchAction(batch) {
    if (!batch) return
    const uiState = deriveBatchUiState(batch)
    if (uiState.actionType === 'process') {
      await processBatchNow(batch)
      return
    }
    await handleSelectBatch(batch.batch_id)
  }

  async function handleProcessBatch() {
    if (!activeBatch) return
    if (linesMissingLocation > 0 || linesMissingArticle > 0) {
      setError('')
      setProcessWarning({
        missingLocations: linesMissingLocation,
        missingArticles: linesMissingArticle,
      })
      return
    }
    await processBatchNow(activeBatch)
  }

  return (
    <AppShell title="Winkelimport" showExit={false}>
      <div style={{ display: 'grid', gap: '18px' }}>
        <Card>
          <div data-testid="stores-page-intro" style={{ display: 'grid', gap: '10px' }}>
            <div>
              <h2 style={{ margin: '0 0 8px 0', fontSize: '20px' }}>Winkelimport</h2>
              <p style={{ margin: 0, color: '#667085' }}>
                Werk eerst je open bonnen af. Verbonden winkels blijven beschikbaar om nieuwe aankopen op te halen.
              </p>
            </div>
          </div>
        </Card>

        <Card>
          <div data-testid="store-import-simplification-banner" className="rz-inline-feedback rz-inline-feedback--warning" style={{ display: 'flex', justifyContent: 'space-between', gap: '12px', flexWrap: 'wrap' }}>
            <span>Vereenvoudigingsniveau winkelimport: <strong>{simplificationLevelLabel}</strong></span>
            <span>{overviewBatchCount > 0 ? `${overviewBatchCount} open bon(nen)` : 'Geen open bonnen'} in deze huishoudcontext.</span>
          </div>
        </Card>

        {error && (
          <Card>
            <div style={{ color: '#b42318', fontWeight: 700 }}>{error}</div>
          </Card>
        )}

        {status && (
          <Card>
            <div style={{ color: '#0f5132', fontWeight: 700 }}>{status}</div>
          </Card>
        )}

        {!isBatchDetailRoute ? (
          <Card>
            <div data-testid="open-batches-section" style={{ display: 'grid', gap: '14px' }}>
              <div>
                <h3 style={{ margin: '0 0 6px 0', fontSize: '18px' }}>Open bonnen</h3>
                <div style={{ color: '#667085', fontSize: '14px' }}>Open, hervat en verwerk hier je bonnen.</div>
              </div>

              {isLoading ? (
                <div>Winkelgegevens laden…</div>
              ) : batchItems.length === 0 ? (
                <div data-testid="open-batches-empty" style={{ color: '#667085' }}>Geen open bonnen</div>
              ) : (
                <div style={{ display: 'grid', gap: '12px' }}>
                  {batchItems.map((batch) => (
                    <div
                      key={batch.batch_id}
                      data-testid={`open-batch-${batch.batch_id}`}
                      style={{
                        border: '1px solid #d0d5dd',
                        borderRadius: '12px',
                        padding: '14px 16px',
                        display: 'grid',
                        gap: '10px',
                        background: '#ffffff',
                      }}
                    >
                      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', gap: '12px', flexWrap: 'wrap' }}>
                        <div style={{ display: 'grid', gap: '6px' }}>
                          <div style={{ fontWeight: 700, fontSize: '18px' }}>{batch.store_provider_name || batch.store_name}</div>
                          <div style={{ color: '#667085', fontSize: '14px' }}>
                            {batch.purchase_date || 'Onbekend'} · {batch.store_label || batch.store_name || providerLabel(providersByCode[batch.store_provider_code])}
                          </div>
                        </div>
                        <div style={{ display: 'flex', gap: '8px', alignItems: 'center', flexWrap: 'wrap' }}>
                          <span style={{ ...batchStatusPillStyle, ...(batchStatusToneStyles[batch.uiState.statusKey] || batchStatusToneStyles.open) }}>{batch.uiState.label}</span>
                          <Button
                            data-testid={`batch-primary-action-${batch.batch_id}`}
                            variant={batch.uiState.actionType === 'process' ? 'primary' : 'secondary'}
                            onClick={() => handlePrimaryBatchAction(batch)}
                            disabled={busyBatchId === batch.batch_id || isProcessingBatch}
                          >
                            {busyBatchId === batch.batch_id ? 'Bezig…' : batch.uiState.actionLabel}
                          </Button>
                        </div>
                      </div>

                      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(160px, 1fr))', gap: '10px', color: '#667085', fontSize: '14px' }}>
                        <div>Aantal regels: <strong>{batch.summary?.total || batch.lines?.length || 0}</strong></div>
                        <div>{batch.uiState.progressText}</div>
                        <div>Laatste wijziging: {formatBatchLastChange(batch)}</div>
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </div>
          </Card>
        ) : null}

        {isBatchDetailRoute && activeBatch ? (
          <Card fullWidth>
            <div data-testid="active-batch-card" className="rz-store-review">
              <div className="rz-store-review-summary">
                <div>
                  <div style={{ marginBottom: '10px' }}>
                    <Button variant="secondary" onClick={() => navigate('/winkels')}>Terug naar overzicht</Button>
                  </div>
                  <h3 data-testid="active-batch-title" className="rz-store-review-title">{buildBatchTitle(activeBatch)}</h3>
                  <div className="rz-store-review-meta">Aankoopdatum: {activeBatch.purchase_date || 'Onbekend'}</div>
                  <div className="rz-store-review-meta">Winkel: {activeBatch.store_label || activeBatch.store_name || providerLabel(activeProvider)}</div>
                </div>
                <div style={{ display: 'flex', gap: '12px', flexWrap: 'wrap', alignItems: 'center' }}>
                  {detailBatchUiState ? <span style={{ ...batchStatusPillStyle, ...(batchStatusToneStyles[detailBatchUiState.statusKey] || batchStatusToneStyles.open) }}>{detailBatchUiState.label}</span> : null}
                  <Button data-testid="process-active-batch" variant="primary" onClick={handleProcessBatch} disabled={isProcessingBatch || !canProcessBatch}>
                    {isProcessingBatch ? 'Bezig…' : 'Naar voorraad'}
                  </Button>
                  {processFeedback ? <span className="rz-store-inline-feedback">{processFeedback}</span> : null}
                </div>
              </div>

              <div className="rz-store-review-meta" style={{ marginBottom: '12px' }}>
                Vereenvoudigingsniveau actief: {simplificationLevelLabel}. Bekende regels worden volgens dit niveau voorgesteld of automatisch voorbereid.
              </div>

              <div className="rz-store-table-wrap">
                <table className="rz-table rz-store-table" data-testid="store-review-table">
                  <colgroup>
                    <col style={{ width: '34%' }} />
                    <col style={{ width: '12%' }} />
                    <col style={{ width: '18%' }} />
                    <col style={{ width: '20%' }} />
                    <col style={{ width: '18%' }} />
                  </colgroup>
                  <thead>
                    <tr className="rz-table-header">
                      <th>Artikel</th>
                      <th className="rz-num">Aantal</th>
                      <th>Beoordeling</th>
                      <th>Koppelen aan</th>
                      <th>Locatie</th>
                    </tr>
                  </thead>
                  <tbody>
                    {visibleLines.length === 0 ? (
                      <tr><td colSpan={5}>Er staan geen open regels meer in deze kassabon.</td></tr>
                    ) : visibleLines.map((line) => {
                      const hasValidArticle = Boolean(line.matched_household_article_id) && validArticleIds.has(String(line.matched_household_article_id))
                      const hasValidLocation = Boolean(line.target_location_id) && validLocationIds.has(String(line.target_location_id))
                      const isReadyForProcessing = (line.review_decision || 'selected') === 'selected' && hasValidArticle && hasValidLocation
                      return (
                        <tr key={line.id} className={isReadyForProcessing ? 'rz-store-row--linked' : ''}>
                          <td>
                            <div className="rz-store-primary">{line.article_name_raw}</div>
                            <div className="rz-store-secondary">{line.brand_raw || 'Geen merk'} · {line.line_price_raw != null ? `€ ${line.line_price_raw.toFixed(2)}` : 'Geen prijs'}</div>
                            {suggestionLabel(line) ? <div className={`rz-store-suggestion ${line.is_auto_prefilled ? 'rz-store-suggestion--auto' : 'rz-store-suggestion--check'}`}>{suggestionLabel(line)}</div> : null}
                            {line?.preparation_mode ? (
                              <div className="rz-store-secondary">
                                Status voorbereiding: {line.preparation_mode === 'auto_ready' ? 'Automatisch klaargezet' : line.preparation_mode === 'suggest_only' ? 'Alleen voorstel' : 'Geen voorbereiding'}
                              </div>
                            ) : null}
                          </td>
                          <td className="rz-num"><div className="rz-store-amount">{formatQuantity(line.quantity_raw, line.unit_raw)}</div></td>
                          <td>
                            <select className="rz-input rz-store-select" value={line.review_decision || 'selected'} disabled={busyLineId === line.id} onChange={(event) => handleReviewDecision(line.id, event.target.value)}>
                              <option value="pending">Nog te beoordelen</option>
                              <option value="selected">Verwerken</option>
                              <option value="ignored">Negeren</option>
                            </select>
                          </td>
                          <td>
                            <StoreArticleSelector
                              lineId={line.id}
                              lineName={line.article_name_raw}
                              selectedArticleId={line.matched_household_article_id || ''}
                              articleOptions={articleOptions}
                              disabled={busyLineId === line.id}
                              onChange={(nextArticleId) => handleMapLine(line.id, nextArticleId)}
                              onCreateArticle={(articleName) => handleCreateArticleFromLine(line.id, articleName)}
                            />
                          </td>
                          <td>
                            <select className="rz-input rz-store-select" value={line.target_location_id || ''} disabled={busyLineId === line.id} onFocus={() => household?.id && refreshLocationOptions(household.id)} onMouseDown={() => household?.id && refreshLocationOptions(household.id)} onChange={(event) => handleTargetLocation(line.id, event.target.value)}>
                              <option value="">Geen voorkeurslocatie</option>
                              {locationOptions.map((location) => (
                                <option key={location.id} value={location.id}>{location.label}</option>
                              ))}
                            </select>
                          </td>
                        </tr>
                      )
                    })}
                  </tbody>
                </table>
              </div>
            </div>
          </Card>
        ) : null}
        <Card>
          <div data-testid="connected-stores-section">
            {isLoading ? (
              <div>Winkelgegevens laden…</div>
            ) : (
              <div style={{ display: 'grid', gap: '14px' }}>
                <div>
                  <h3 style={{ margin: '0 0 6px 0', fontSize: '18px' }}>Verbonden winkels</h3>
                  <div style={{ color: '#667085', fontSize: '14px' }}>Beheer hier je gekoppelde winkels en haal nieuwe aankopen op.</div>
                </div>
                {connectedStoreItems.map((item) => {
                  const provider = item.provider
                  const connection = item.connection
                  const providerOpenBatch = batchItems.find((batch) => batch.store_provider_code === item.code) || null
                  const providerName = item.name
                  return (
                    <div key={item.code} data-testid={`store-provider-${item.code}`} style={connectedStoreRowStyle}>
                      <div style={{ display: 'grid', gap: '2px' }}>
                        <div style={{ fontWeight: 700 }}>{providerName}</div>
                        <div style={{ color: '#667085', fontSize: '14px' }}>Status: {connection ? 'gekoppeld / actief' : 'nog niet gekoppeld'}</div>
                        <div style={{ color: '#667085', fontSize: '14px' }}>Laatste activiteit: {providerOpenBatch ? formatBatchLastChange(providerOpenBatch) : 'Nog geen open bon'}</div>
                      </div>
                      <div style={{ display: 'flex', gap: '10px', alignItems: 'center', flexWrap: 'wrap', justifyContent: 'flex-end' }}>
                        {providerOpenBatch ? (
                          <span style={{ ...batchStatusPillStyle, ...(batchStatusToneStyles[providerOpenBatch.uiState.statusKey] || batchStatusToneStyles.open) }}>{providerOpenBatch.uiState.label}</span>
                        ) : null}
                        {!connection && provider ? (
                          <Button data-testid={`connect-store-${item.code}`} variant="primary" onClick={() => handleConnect(item.code, providerName)} disabled={isConnecting}>
                            {isConnecting ? 'Koppelen…' : `${providerName} koppelen`}
                          </Button>
                        ) : connection ? (
                          <Button data-testid={`pull-purchases-${item.code}`} variant="secondary" onClick={() => handlePullPurchases(connection, providerName)} disabled={isPulling}>
                            {isPulling ? 'Ophalen…' : 'Aankopen ophalen'}
                          </Button>
                        ) : null}
                      </div>
                    </div>
                  )
                })}
              </div>
            )}
          </div>
        </Card>
      </div>

      {processWarning && (
        <div className="rz-modal-backdrop" role="presentation">
          <div className="rz-modal-card" role="dialog" aria-modal="true" aria-labelledby="process-warning-title">
            <h3 id="process-warning-title" className="rz-modal-title">Nog niet alle regels zijn klaar</h3>
            <p className="rz-modal-text">
              {processWarning.missingLocations > 0 && processWarning.missingArticles > 0
                ? `Nog ${processWarning.missingLocations} artikel(en) zonder geldige locatie en ${processWarning.missingArticles} artikel(en) zonder geldig artikel.`
                : processWarning.missingLocations > 0
                  ? `Nog ${processWarning.missingLocations} artikel(en) zonder geldige locatie.`
                  : `Nog ${processWarning.missingArticles} artikel(en) zonder geldig artikel.`}
            </p>
            <div className="rz-modal-actions">
              <Button variant="secondary" onClick={() => setProcessWarning(null)}>Terug naar Winkel</Button>
              <Button onClick={async () => { setProcessWarning(null); await processBatchNow(activeBatch); }} disabled={isProcessingBatch}>Negeren</Button>
            </div>
          </div>
        </div>
      )}
    </AppShell>
  )
}

const articleSearchStyle = {
  display: 'flex',
  flexDirection: 'column',
  gap: '6px',
}

const articleSearchInputStyle = {
  width: '100%',
  padding: '8px 10px',
  borderRadius: '8px',
  border: '1px solid #d0d5dd',
  fontSize: '14px',
  background: '#ffffff',
}

const createArticleButtonStyle = {
  alignSelf: 'flex-start',
  background: 'none',
  border: 'none',
  padding: 0,
  marginTop: '4px',
  color: '#0f766e',
  fontWeight: 700,
  cursor: 'pointer',
  textDecoration: 'underline',
}

const batchStatusPillStyle = {
  display: 'inline-flex',
  alignItems: 'center',
  borderRadius: '999px',
  padding: '4px 10px',
  fontSize: '12px',
  fontWeight: 700,
}

const batchStatusToneStyles = {
  action_needed: {
    background: '#fef3f2',
    color: '#b42318',
  },
  ready: {
    background: '#ecfdf3',
    color: '#027a48',
  },
  in_progress: {
    background: '#eff8ff',
    color: '#175cd3',
  },
  open: {
    background: '#f2f4f7',
    color: '#344054',
  },
  processed: {
    background: '#ecfdf3',
    color: '#027a48',
  },
}

const connectedStoreRowStyle = {
  display: 'flex',
  justifyContent: 'space-between',
  alignItems: 'center',
  gap: '16px',
  flexWrap: 'wrap',
  borderTop: '1px solid #e4e7ec',
  paddingTop: '14px',
}
