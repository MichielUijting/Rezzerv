import { useEffect, useMemo, useRef, useState } from 'react'
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
  if (value === 'in_review') return 'In beoordeling'
  return 'Nog te beoordelen'
}

function suggestionLabel(line) {
  if (line?.suggestion_reason) return line.suggestion_reason
  if (line.is_auto_prefilled && (line.review_decision || 'pending') === 'selected' && line.matched_household_article_id && line.target_location_id) {
    return 'Automatisch voorbereid'
  }
  if (line.suggested_household_article_id || line.suggested_location_id) {
    return 'Controleer voorstel'
  }
  return ''
}

function formatQuantity(value, unit) {
  return [value, unit].filter(Boolean).join(' ')
}

function getLineBlockerReason(line, validArticleIds, validLocationIds) {
  if ((line.processing_status || 'pending') === 'processed') return ''
  if ((line.review_decision || 'pending') !== 'selected') return 'Zet beoordeling op Verwerken'
  if (!line.matched_household_article_id) return 'Kies eerst een artikel'
  if (validArticleIds && !validArticleIds.has(String(line.matched_household_article_id))) return 'Kies een geldig artikel'
  if (!line.target_location_id) return 'Kies eerst een locatie'
  if (validLocationIds && !validLocationIds.has(String(line.target_location_id))) return 'Kies een geldige locatie'
  return ''
}

export default function StoresPage() {
  const [household, setHousehold] = useState(null)
  const [providers, setProviders] = useState([])
  const [connections, setConnections] = useState([])
  const [activeBatch, setActiveBatch] = useState(null)
  const [articleOptions, setArticleOptions] = useState(articleFallbackOptions)
  const [locationOptions, setLocationOptions] = useState([])
  const [status, setStatus] = useState('')
  const [error, setError] = useState('')
  const [isLoading, setIsLoading] = useState(true)
  const [isConnecting, setIsConnecting] = useState(false)
  const [isPulling, setIsPulling] = useState(false)
  const [busyLineId, setBusyLineId] = useState('')
  const [isCompletingReview, setIsCompletingReview] = useState(false)
  const [isProcessingBatch, setIsProcessingBatch] = useState(false)
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
  const activeConnection = activeProviderCode ? connectionsByProviderCode[activeProviderCode] || null : null

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

  async function refreshBatch(batchId) {
    const batch = await fetchJson(`/api/purchase-import-batches/${batchId}`)
    setActiveBatch(batch)
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

  async function restoreLatestBatch(connectionId) {
    try {
      const latest = await fetchJson(`/api/store-connections/${connectionId}/latest-batch`)
      if (!latest?.batch_id) return
      if (latest.import_status === 'processed') {
        setActiveBatch(null)
        return
      }
      await refreshBatch(latest.batch_id)
    } catch (err) {
      // Geen eerdere batch is toegestaan; negeren.
    }
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

      const existingPrimaryConnection = connectionData.find((connection) => providerData.some((provider) => provider.code === connection.store_provider_code))
      if (existingPrimaryConnection?.id) {
        await restoreLatestBatch(existingPrimaryConnection.id)
      } else {
        setActiveBatch(null)
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
  }, [])

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
      setConnections((current) => {
        const filtered = current.filter((item) => item.id !== connection.id)
        return [...filtered, connection]
      })
      await refreshLocationOptions(household.id)
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
      setStatus('De artikelkoppeling is opgeslagen.')
    } catch (err) {
      setError(normalizeErrorMessage(err?.message) || 'De artikelkoppeling kon niet worden opgeslagen.')
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
      await refreshLocationOptions(household?.id)
      setStatus('De voorkeurslocatie is opgeslagen.')
    } catch (err) {
      setError(normalizeErrorMessage(err?.message) || 'De voorkeurslocatie kon niet worden opgeslagen.')
    } finally {
      setBusyLineId('')
    }
  }

  async function handleCompleteReview() {
    if (!activeBatch) return
    setIsCompletingReview(true)
    setError('')
    setStatus('')
    try {
      await fetchJson(`/api/purchase-import-batches/${activeBatch.batch_id}/complete-review`, {
        method: 'POST',
      })
      await refreshBatch(activeBatch.batch_id)
      setStatus('De batch is als beoordeeld opgeslagen. Er is nog niets naar voorraad verwerkt.')
    } catch (err) {
      setError(normalizeErrorMessage(err?.message) || 'De batch kon niet worden afgerond.')
    } finally {
      setIsCompletingReview(false)
    }
  }


  async function processBatchNow() {
    if (!activeBatch) return
    setIsProcessingBatch(true)
    setError('')
    setStatus('')
    try {
      const result = await fetchJson(`/api/purchase-import-batches/${activeBatch.batch_id}/process`, {
        method: 'POST',
        body: JSON.stringify({ processed_by: 'ui', mode: 'selected_only' }),
      })
      const refreshedBatch = await refreshBatch(activeBatch.batch_id)
      showProcessFeedback('Verwerkt!')
      if (result.failed_count > 0) {
        setStatus(`Verwerking afgerond: ${result.processed_count} regel(s) verwerkt, ${result.failed_count} regel(s) mislukt.`)
      } else {
        setStatus(`Verwerking afgerond: ${result.processed_count} regel(s) zijn naar voorraad verwerkt.`)
      }
      if (refreshedBatch?.import_status === 'processed') {
        window.setTimeout(() => setActiveBatch(null), 1200)
      }
    } catch (err) {
      setError(normalizeErrorMessage(err?.message) || 'De batch kon niet naar voorraad worden verwerkt.')
    } finally {
      setIsProcessingBatch(false)
    }
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
    await processBatchNow()
  }

  return (
    <AppShell title="Winkels" showExit={false}>
      <div style={{ display: 'grid', gap: '18px' }}>
        <Card>
          <div style={{ display: 'grid', gap: '10px' }}>
            <div>
              <h2 style={{ margin: '0 0 8px 0', fontSize: '20px' }}>Winkelkoppelingen</h2>
              <p style={{ margin: 0, color: '#667085' }}>
                Koppel hier winkels, haal voorbeeld-aankopen op en beoordeel per regel wat later verwerkt mag worden.
              </p>
            </div>
          </div>
        </Card>

        <Card>
          <div className="rz-inline-feedback rz-inline-feedback--warning" style={{ display: 'flex', justifyContent: 'space-between', gap: '12px', flexWrap: 'wrap' }}>
            <span>Vereenvoudigingsniveau winkelimport: <strong>{simplificationLevelLabel}</strong></span>
            <span>Deze instelling geldt voor het hele huishouden.</span>
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

        <Card>
          {isLoading ? (
            <div>Winkelgegevens laden…</div>
          ) : (
            <div style={{ display: 'grid', gap: '16px' }}>
              {providers.map((provider) => {
                const connection = connectionsByProviderCode[provider.code] || null
                return (
                  <div key={provider.code} style={{ display: 'grid', gap: '16px' }}>
                    <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', gap: '16px', flexWrap: 'wrap' }}>
                      <div>
                        <div style={{ fontWeight: 700, fontSize: '18px' }}>{provider.name}</div>
                        <div style={{ color: '#667085', fontSize: '14px' }}>
                          Status provider: {providerStatusLabel(provider)}
                        </div>
                        <div style={{ color: '#667085', fontSize: '14px' }}>
                          Koppeling: {connection ? 'gekoppeld' : 'nog niet gekoppeld'}
                        </div>
                      </div>
                      <div style={{ display: 'flex', gap: '12px', flexWrap: 'wrap' }}>
                        {!connection ? (
                          <Button variant="primary" onClick={() => handleConnect(provider.code, provider.name)} disabled={isConnecting}>
                            {isConnecting ? 'Koppelen…' : `${provider.name} koppelen`}
                          </Button>
                        ) : (
                          <Button variant="secondary" onClick={() => handlePullPurchases(connection, provider.name)} disabled={isPulling}>
                            {isPulling ? 'Ophalen…' : 'Aankopen ophalen'}
                          </Button>
                        )}
                      </div>
                    </div>

                    <div style={{ borderTop: '1px solid #e4e7ec', paddingTop: '14px', color: '#667085', fontSize: '14px' }}>
                      Deze release laat je regels beoordelen, koppelen en geselecteerde regels expliciet naar voorraad verwerken.
                    </div>
                  </div>
                )
              })}
            </div>
          )}
        </Card>

        {activeBatch && (
          <Card>
            <div className="rz-store-review">
              <div className="rz-store-review-summary">
                <div>
                  <h3 className="rz-store-review-title">{buildBatchTitle(activeBatch)}</h3>
                  <div className="rz-store-review-meta">
                    Aankoopdatum: {activeBatch.purchase_date || 'Onbekend'}
                  </div>
                  <div className="rz-store-review-meta">
                    Winkel: {activeBatch.store_label || activeBatch.store_name || providerLabel(activeProvider)}
                  </div>
                </div>
                <div style={{ display: 'flex', gap: '12px', flexWrap: 'wrap', alignItems: 'center' }}>
                  <Button variant="primary" onClick={handleProcessBatch} disabled={isProcessingBatch || !canProcessBatch}>
                    {isProcessingBatch ? 'Bezig…' : 'Naar voorraad'}
                  </Button>
                  {processFeedback ? <span className="rz-store-inline-feedback">{processFeedback}</span> : null}
                </div>
              </div>

              <div className="rz-store-review-meta" style={{ marginBottom: '12px' }}>
                Vereenvoudigingsniveau actief: {simplificationLevelLabel}. Bekende regels worden volgens dit niveau voorgesteld of automatisch voorbereid.
              </div>

              <div className="rz-table-wrapper">
                <table className="rz-table rz-store-review-table">
                  <colgroup>
                    <col style={{ width: '27%' }} />
                    <col style={{ width: '11%' }} />
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
                    ) : visibleLines.map((line) => (
                      <tr key={line.id} className={line.target_location_id && validLocationIds.has(String(line.target_location_id)) ? 'rz-store-row--linked' : ''}>
                        <td>
                          <div className="rz-store-primary">{line.article_name_raw}</div>
                          <div className="rz-store-secondary">{line.brand_raw || 'Geen merk'} · {line.line_price_raw != null ? `€ ${line.line_price_raw.toFixed(2)}` : 'Geen prijs'}</div>
                          {suggestionLabel(line) ? <div className={`rz-store-suggestion ${line.is_auto_prefilled ? 'rz-store-suggestion--auto' : 'rz-store-suggestion--check'}`}>{suggestionLabel(line)}</div> : null}
                        </td>
                        <td className="rz-num">
                          <div className="rz-store-amount">{formatQuantity(line.quantity_raw, line.unit_raw)}</div>
                        </td>
                        <td>
                          <select
                            className="rz-input rz-store-select"
                            value={line.review_decision || 'selected'}
                            disabled={busyLineId === line.id}
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
                            value={line.matched_household_article_id || ''}
                            disabled={busyLineId === line.id}
                            onChange={(event) => handleMapLine(line.id, event.target.value)}
                          >
                            <option value="">Kies artikel</option>
                            {articleOptions.map((article) => (
                              <option key={article.id} value={article.id}>{articleLabel(article)}</option>
                            ))}
                          </select>
                        </td>
                        <td>
                          <select
                            className="rz-input rz-store-select"
                            value={line.target_location_id || ''}
                            disabled={busyLineId === line.id}
                            onFocus={() => household?.id && refreshLocationOptions(household.id)}
                            onMouseDown={() => household?.id && refreshLocationOptions(household.id)}
                            onChange={(event) => handleTargetLocation(line.id, event.target.value)}
                          >
                            <option value="">Geen voorkeurslocatie</option>
                            {locationOptions.map((location) => (
                              <option key={location.id} value={location.id}>{location.label}</option>
                            ))}
                          </select>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          </Card>
        )}
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
                <Button onClick={async () => { setProcessWarning(null); await processBatchNow(); }} disabled={isProcessingBatch}>Negeren</Button>
              </div>
            </div>
          </div>
        )}
    </AppShell>
  )
}

const tableHeadStyle = {
  textAlign: 'left',
  padding: '10px 8px',
  borderBottom: '1px solid #d0d5dd',
  fontSize: '14px',
}

const tableCellStyle = {
  padding: '10px 8px',
  borderBottom: '1px solid #eaecf0',
  fontSize: '14px',
  verticalAlign: 'top',
}

const selectStyle = {
  width: '100%',
  padding: '8px 10px',
  borderRadius: '8px',
  border: '1px solid #d0d5dd',
  fontSize: '14px',
  background: '#ffffff',
}
