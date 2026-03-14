import { useEffect, useMemo, useRef, useState } from 'react'
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
  const [processWarning, setProcessWarning] = useState(null)
  const [processMode, setProcessMode] = useState('selected_only')
  const [lastProcessResult, setLastProcessResult] = useState(null)
  const [batchDiagnostics, setBatchDiagnostics] = useState(null)
  const processFeedbackTimer = useRef(null)

  const providersByCode = useMemo(
    () => Object.fromEntries(providers.map((provider) => [provider.code, provider])),
    [providers],
  )

  const activeProviderCode = batch?.store_provider_code || null
  const activeProvider = activeProviderCode ? providersByCode[activeProviderCode] || null : null
  const validArticleIds = useMemo(() => new Set(articleOptions.map((article) => String(article.id))), [articleOptions])
  const validLocationIds = useMemo(() => new Set(locationOptions.map((location) => String(location.id))), [locationOptions])

  const visibleLines = useMemo(
    () => batch?.lines?.filter((line) => (line.processing_status || 'pending') !== 'processed') || [],
    [batch],
  )

  const selectedLines = visibleLines.filter((line) => (line.review_decision || 'selected') === 'selected')
  const linesMissingArticle = selectedLines.filter((line) => !line.matched_household_article_id).length
  const linesMissingLocation = selectedLines.filter((line) => !line.target_location_id || !validLocationIds.has(String(line.target_location_id))).length
  const canProcessBatch = Boolean(batch && selectedLines.length > 0 && !busyLineId && !isLoading)
  const simplificationLevelLabel = getStoreImportSimplificationLabel(household?.store_import_simplification_level || 'gebalanceerd')

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

  async function handleMapLine(lineId, articleId) {
    setBusyLineId(lineId)
    setError('')
    setStatus('')
    try {
      await fetchJson(`/api/purchase-import-lines/${lineId}/map`, {
        method: 'POST',
        body: JSON.stringify({ household_article_id: articleId }),
      })
      await refreshBatch(batch.batch_id)
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

  async function handleTargetLocation(lineId, targetLocationId) {
    setBusyLineId(lineId)
    setError('')
    setStatus('')
    try {
      await fetchJson(`/api/purchase-import-lines/${lineId}/target-location`, {
        method: 'POST',
        body: JSON.stringify({ target_location_id: targetLocationId || null }),
      })
      await refreshBatch(batch.batch_id)
      await refreshLocationOptions(household?.id)
      setStatus('De voorkeurslocatie is opgeslagen.')
    } catch (err) {
      setError(normalizeErrorMessage(err?.message) || 'De voorkeurslocatie kon niet worden opgeslagen.')
    } finally {
      setBusyLineId('')
    }
  }

  async function processBatchNow(mode = processMode) {
    if (!batch) return
    setIsProcessingBatch(true)
    setError('')
    setStatus('')
    setLastProcessResult(null)
    try {
      const result = await fetchJson(`/api/purchase-import-batches/${batch.batch_id}/process`, {
        method: 'POST',
        body: JSON.stringify({ processed_by: 'ui', mode, auto_consume_article_ids: buildAutoConsumeArticleIds(selectedLines) }),
      })
      await refreshBatch(batch.batch_id)
      await refreshLocationOptions(household?.id)
      setLastProcessResult(result)
      setBatchDiagnostics(result?.diagnostics || null)
      setProcessWarning(null)
      showProcessFeedback('Verwerkt!')
      if (result.failed_count > 0) {
        setStatus(`Verwerking afgerond: ${result.processed_count} regel(s) verwerkt, ${result.failed_count} regel(s) mislukt. Controleer de overgebleven regels hieronder of open daarna Voorraad.`)
      } else {
        setStatus(`Verwerking afgerond: ${result.processed_count} regel(s) zijn naar voorraad verwerkt. Open Voorraad om het resultaat te controleren.`)
      }
    } catch (err) {
      setError(normalizeErrorMessage(err?.message) || 'De batch kon niet naar voorraad worden verwerkt.')
    } finally {
      setIsProcessingBatch(false)
    }
  }

  const processActionMode = batch?.import_status === 'reviewed' ? 'ready_only' : 'selected_only'

  async function handleProcessBatch() {
    if (!batch) return
    setProcessMode(processActionMode)
    if (processActionMode === 'selected_only' && (linesMissingLocation > 0 || linesMissingArticle > 0)) {
      setError('')
      setProcessWarning({
        missingLocations: linesMissingLocation,
        missingArticles: linesMissingArticle,
      })
      return
    }
    await processBatchNow(processActionMode)
  }

  return (
    <AppShell title={batch ? buildBatchTitle(batch) : 'Bondetail'} showExit={false}>
      <div style={{ display: 'grid', gap: '16px' }}>
        <Card>
          <div style={{ display: 'flex', justifyContent: 'space-between', gap: '12px', flexWrap: 'wrap', alignItems: 'center' }}>
            <div style={{ display: 'grid', gap: '6px' }}>
              <h2 style={{ margin: 0, fontSize: '20px' }}>{batch ? buildBatchTitle(batch) : 'Bondetail'}</h2>
              <div style={{ color: '#667085' }}>Werk deze bon af en ga daarna terug naar het overzicht of direct naar de startpagina.</div>
            </div>
            <div style={{ display: 'flex', gap: '8px', flexWrap: 'wrap' }}>
              <Button variant="secondary" onClick={() => navigate('/winkels')}>Terug naar overzicht</Button>
              <Button variant="secondary" onClick={() => navigate('/home')}>Terug naar start</Button>
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
          <Card>
            <div data-testid="batch-detail-page" className="rz-store-review">
              <div className="rz-store-review-summary">
                <div>
                  <h3 data-testid="active-batch-title" className="rz-store-review-title">{buildBatchTitle(batch)}</h3>
                  <div className="rz-store-review-meta">Aankoopdatum: {batch.purchase_date || 'Onbekend'}</div>
                  <div className="rz-store-review-meta">Winkel: {batch.store_label || batch.store_name || providerLabel(activeProvider)}</div>
                  <div className="rz-store-review-meta">Status: {batchStatusLabel(batch.import_status)}</div>
                </div>
                <div style={{ display: 'flex', gap: '12px', flexWrap: 'wrap', alignItems: 'center' }}>
                  <Button data-testid="process-active-batch" variant="primary" onClick={handleProcessBatch} disabled={isProcessingBatch || !canProcessBatch}>
                    {isProcessingBatch ? 'Bezig…' : 'Naar voorraad'}
                  </Button>
                  <Button variant="secondary" onClick={() => navigate('/voorraad')}>Bekijk voorraad</Button>
                  {processFeedback ? <span className="rz-store-inline-feedback">{processFeedback}</span> : null}
                </div>
              </div>

              <div className="rz-store-review-meta" style={{ marginBottom: '12px' }}>
                Vereenvoudigingsniveau actief: {simplificationLevelLabel}. Bekende regels worden volgens dit niveau voorgesteld of automatisch voorbereid.
              </div>

              <div className="rz-store-review-meta" style={{ display: 'flex', gap: '12px', flexWrap: 'wrap', marginBottom: '12px' }}>
                <span>Totaal: <strong>{batch.summary?.total || 0}</strong></span>
                <span>Open: <strong>{visibleLines.length}</strong></span>
                <span>Verwerkt: <strong>{batch.summary?.processed || 0}</strong></span>
                <span>Mislukt: <strong>{batch.summary?.failed || 0}</strong></span>
                {lastProcessResult?.processed_count ? <span>Laatst verwerkt: <strong>{lastProcessResult.processed_count}</strong></span> : null}
              </div>

              {lastProcessResult ? (
                <div className="rz-inline-feedback rz-inline-feedback--success" style={{ marginBottom: '12px' }}>
                  Laatste verwerking — verwerkt: <strong>{lastProcessResult.processed_count || 0}</strong>, overgeslagen: <strong>{lastProcessResult.skipped_count || 0}</strong>, mislukt: <strong>{lastProcessResult.failed_count || 0}</strong>.
                </div>
              ) : null}

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
                    ) : visibleLines.map((line) => {
                      const hasValidArticle = Boolean(line.matched_household_article_id) && validArticleIds.has(String(line.matched_household_article_id))
                      const isReadyForProcessing = (line.review_decision || 'selected') === 'selected' && hasValidArticle && line.target_location_id && validLocationIds.has(String(line.target_location_id))
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
                            {line.processing_status === 'failed' && line.processing_error ? (
                              <div className="rz-inline-feedback rz-inline-feedback--error" style={{ marginTop: '6px' }}>Verwerking mislukt: {line.processing_error}</div>
                            ) : null}
                          </td>
                          <td className="rz-num"><div className="rz-store-amount">{formatQuantity(line.quantity_raw, line.unit_raw)}</div></td>
                          <td>
                            <select
                              className="rz-input rz-store-select"
                              value={line.review_decision || 'selected'}
                              disabled={busyLineId === line.id || isProcessingBatch}
                              onChange={(event) => handleReviewDecision(line.id, event.target.value)}
                            >
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
                              disabled={busyLineId === line.id || isProcessingBatch}
                              onChange={(nextArticleId) => handleMapLine(line.id, nextArticleId)}
                              onCreateArticle={(articleName) => handleCreateArticleFromLine(line.id, articleName)}
                            />
                          </td>
                          <td>
                            <select
                              className="rz-input rz-store-select"
                              value={line.target_location_id || ''}
                              disabled={busyLineId === line.id || isProcessingBatch}
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
                      )
                    })}
                  </tbody>
                </table>
              </div>

              {lastProcessResult?.results?.length ? (
                <div style={{ display: 'grid', gap: '12px', marginTop: '16px' }}>
                  <div className="rz-store-review-meta" style={{ fontWeight: 700 }}>
                    Resultaat van Naar voorraad — per regel
                  </div>
                  {lastProcessResult.results.map((result) => {
                    const line = batch?.lines?.find((entry) => entry.id === result.line_id)
                    const label = line?.article_name_raw || result.line_id
                    const statusLabel = result.status === 'processed' ? 'Verwerkt' : result.status === 'skipped' ? 'Overgeslagen' : 'Mislukt'
                    const reason = result.reason || result.error || result.message || result.diagnostic?.failure_message || ''
                    return (
                      <div key={result.line_id} className="rz-inline-feedback" style={{ borderColor: result.status === 'failed' ? '#b42318' : '#1d2939' }}>
                        <strong>{label}</strong>: {statusLabel}{reason ? ` — ${reason}` : ''}
                      </div>
                    )
                  })}
                </div>
              ) : null}

              {batchDiagnostics?.line_diagnostics?.length ? (
                <div style={{ marginTop: '16px', display: 'grid', gap: '12px' }}>
                  <div className="rz-store-review-meta"><strong>Diagnose laatste verwerking</strong> — bewijs per kassabonregel waar verwerking, historie of automatisch afboeken wel of niet slaagt.</div>
                  {batchDiagnostics.line_diagnostics.map((diag) => (
                    <div key={diag.line_id} style={{ border: '1px solid #D0D5DD', borderRadius: '12px', padding: '12px', background: '#F8FAFC', display: 'grid', gap: '6px' }}>
                      <div><strong>Bonregel:</strong> {diag.receipt_line_text || 'Onbekend'}</div>
                      <div><strong>Status:</strong> {diag.processing_status === 'processed' ? 'verwerkt' : diag.processing_status === 'failed' ? 'mislukt' : 'nog niet verwerkt'}</div>
                      <div><strong>Gekoppeld artikel:</strong> {diag.resolved_article_name || '(geen)'} {diag.resolution_reason ? `· ${diag.resolution_reason}` : ''}</div>
                      <div><strong>Aankoop-event:</strong> {diag.purchase_event_created ? 'ja' : 'nee'} · <strong>Historie ziet aankoop:</strong> {diag.history_contains_purchase_event ? 'ja' : 'nee'}</div>
                      <div><strong>Voorraad:</strong> {diag.inventory_before_total} → {diag.inventory_after_purchase_total}{diag.auto_consume_event_created || diag.auto_consume_should_apply ? ` → ${diag.inventory_after_auto_consume_total}` : ''}</div>
                      <div><strong>Automatisch afboeken:</strong> {diag.auto_consume_event_created ? 'ja' : 'nee'} · <strong>Modus:</strong> {diag.auto_consume_effective_mode || 'none'}</div>
                      <div><strong>Gekocht:</strong> {diag.purchase_quantity} · <strong>Aangevraagd af te boeken:</strong> {diag.auto_consume_requested_deduction_quantity} · <strong>Werkelijk afgeboekt:</strong> {diag.auto_consume_applied_deduction_quantity}</div>
                      <div><strong>Beslisreden:</strong> {diag.auto_consume_decision_reason || 'Geen'}</div>
                      {diag.processing_status !== 'processed' && (!diag.failure_stage || diag.failure_stage === 'none') ? (
                        <div className="rz-store-review-meta">Deze regel is nog niet verwerkt. Koppel eerst een artikel en kies daarna verwerken.</div>
                      ) : null}
                      {diag.processing_status === 'failed' && diag.failure_stage && diag.failure_stage !== 'none' ? (
                        <div className="rz-inline-feedback rz-inline-feedback--error">Foutstap: {diag.failure_stage} — {diag.failure_message || 'Onbekende fout'}</div>
                      ) : null}
                    </div>
                  ))}
                </div>
              ) : null}

            </div>
          </Card>
        ) : (
          <Card><div>Deze bon kon niet worden gevonden.</div></Card>
        )}
      </div>

      {processWarning ? (
        <div className="rz-modal-backdrop" role="presentation">
          <div className="rz-modal-card" data-testid="process-warning-modal" role="dialog" aria-modal="true" aria-labelledby="process-warning-title">
            <h3 id="process-warning-title" className="rz-modal-title">Nog niet alle regels zijn klaar</h3>
            <p className="rz-modal-text">
              {processWarning.missingArticles > 0 ? `${processWarning.missingArticles} regel(s) missen nog een artikelkoppeling. ` : ''}
              {processWarning.missingLocations > 0 ? `${processWarning.missingLocations} regel(s) missen nog een locatie.` : ''}
            </p>
            <div className="rz-modal-actions">
              <Button variant="secondary" data-testid="process-warning-back" onClick={() => setProcessWarning(null)} disabled={isProcessingBatch}>Terug</Button>
              <Button variant="primary" data-testid="process-warning-ignore" onClick={handleProcessReadyOnly} disabled={isProcessingBatch}>
                {isProcessingBatch ? 'Bezig…' : 'Negeren'}
              </Button>
            </div>
          </div>
        </div>
      ) : null}
    </AppShell>
  )
}
