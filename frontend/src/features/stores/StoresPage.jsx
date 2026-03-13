import { useEffect, useMemo, useRef, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import AppShell from '../../app/AppShell'
import Card from '../../ui/Card'
import Button from '../../ui/Button'
import { getStoreImportSimplificationLabel } from '../settings/services/storeImportSimplificationService'
import {
  batchStatusPillStyle,
  batchStatusToneStyles,
  connectedStoreRowStyle,
  deriveBatchUiState,
  fetchJson,
  formatBatchLastChange,
  normalizeErrorMessage,
  providerLabel,
  providerStatusLabel,
} from './storeImportShared'
import { buildAutoConsumeArticleIds } from './autoConsumeContext'

async function getLatestBatchMeta(connectionId) {
  try {
    const latest = await fetchJson(`/api/store-connections/${connectionId}/latest-batch`)
    return latest?.batch_id ? latest : null
  } catch (err) {
    return null
  }
}

export default function StoresPage() {
  const navigate = useNavigate()
  const [household, setHousehold] = useState(null)
  const [providers, setProviders] = useState([])
  const [connections, setConnections] = useState([])
  const [openBatches, setOpenBatches] = useState([])
  const [status, setStatus] = useState('')
  const [error, setError] = useState('')
  const [isLoading, setIsLoading] = useState(true)
  const [isConnecting, setIsConnecting] = useState(false)
  const [isPulling, setIsPulling] = useState(false)
  const [isProcessingBatch, setIsProcessingBatch] = useState(false)
  const [busyBatchId, setBusyBatchId] = useState('')
  const processFeedbackTimer = useRef(null)

  const providersByCode = useMemo(
    () => Object.fromEntries(providers.map((provider) => [provider.code, provider])),
    [providers],
  )

  const connectionsByProviderCode = useMemo(
    () => Object.fromEntries(connections.map((connection) => [connection.store_provider_code, connection])),
    [connections],
  )

  const simplificationLevelLabel = getStoreImportSimplificationLabel(household?.store_import_simplification_level || 'gebalanceerd')

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

  function clearTransientFeedback() {
    if (processFeedbackTimer.current) {
      window.clearTimeout(processFeedbackTimer.current)
      processFeedbackTimer.current = null
    }
  }

  function showStatus(message) {
    clearTransientFeedback()
    setStatus(message)
  }

  async function loadOpenBatches(connectionsToCheck) {
    const latestCandidates = (await Promise.all((connectionsToCheck || []).map((connection) => getLatestBatchMeta(connection.id))))
      .filter((item) => item?.batch_id && item.import_status !== 'processed')

    if (!latestCandidates.length) {
      setOpenBatches([])
      return []
    }

    const loadedBatches = (await Promise.all(latestCandidates.map((item) => fetchJson(`/api/purchase-import-batches/${item.batch_id}`).catch(() => null))))
      .filter(Boolean)

    setOpenBatches(loadedBatches)
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

      const [providerData, connectionData] = await Promise.all([
        fetchJson('/api/store-providers'),
        fetchJson(`/api/store-connections?householdId=${encodeURIComponent(householdData.id)}`),
      ])

      setProviders(providerData)
      setConnections(connectionData)
      await loadOpenBatches(connectionData)
    } catch (err) {
      setError(normalizeErrorMessage(err?.message) || 'Winkelgegevens konden niet worden geladen.')
    } finally {
      setIsLoading(false)
    }
  }

  useEffect(() => {
    loadPageData()
    return () => clearTransientFeedback()
  }, [])

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
      await loadOpenBatches(nextConnections)
      showStatus(`${providerName || providerCode} is gekoppeld aan dit huishouden.`)
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
        await loadOpenBatches(connections)
        showStatus(`De laatste open bon van ${providerName || 'de winkel'} is opnieuw geladen.`)
        return
      }

      const pullResult = await fetchJson(`/api/store-connections/${connection.id}/pull-purchases`, {
        method: 'POST',
        body: JSON.stringify({ mock_profile: 'default' }),
      })
      const p = pullResult.prefill_summary || {}
      const fullyPrefilled = p.fully_prefilled || 0
      const articlePrefills = p.article_prefills || 0
      if (fullyPrefilled > 0 || articlePrefills > 0) {
        showStatus(`Nieuwe mockaankopen van ${providerName || 'de winkel'} zijn opgehaald. ${fullyPrefilled} regel(s) staan al klaar; ${articlePrefills} regel(s) hebben een voorstel.`)
      } else {
        showStatus(`Nieuwe mockaankopen van ${providerName || 'de winkel'} zijn opgehaald.`)
      }
      const refreshedConnections = await fetchJson(`/api/store-connections?householdId=${encodeURIComponent(household.id)}`)
      setConnections(refreshedConnections)
      await loadOpenBatches(refreshedConnections)
    } catch (err) {
      setError(normalizeErrorMessage(err?.message) || 'Aankopen konden niet worden opgehaald.')
    } finally {
      setIsPulling(false)
    }
  }

  async function processBatchNow(batchToProcess) {
    if (!batchToProcess) return
    setIsProcessingBatch(true)
    setBusyBatchId(batchToProcess.batch_id)
    setError('')
    setStatus('')
    try {
      const result = await fetchJson(`/api/purchase-import-batches/${batchToProcess.batch_id}/process`, {
        method: 'POST',
        body: JSON.stringify({ processed_by: 'ui', mode: 'selected_only', auto_consume_article_ids: buildAutoConsumeArticleIds((batchToProcess?.lines || []).filter((line) => (line.processing_status || 'pending') !== 'processed' && (line.review_decision || 'selected') === 'selected')) }),
      })
      if (result.failed_count > 0) {
        showStatus(`Verwerking afgerond: ${result.processed_count} regel(s) verwerkt, ${result.failed_count} regel(s) mislukt.`)
      } else {
        showStatus(`Verwerking afgerond: ${result.processed_count} regel(s) zijn naar voorraad verwerkt.`)
      }
      const refreshedConnections = household?.id
        ? await fetchJson(`/api/store-connections?householdId=${encodeURIComponent(household.id)}`).catch(() => connections)
        : connections
      setConnections(refreshedConnections)
      await loadOpenBatches(refreshedConnections)
    } catch (err) {
      setError(normalizeErrorMessage(err?.message) || 'De batch kon niet naar voorraad worden verwerkt.')
    } finally {
      setIsProcessingBatch(false)
      setBusyBatchId('')
    }
  }

  async function handlePrimaryBatchAction(batch) {
    if (!batch) return
    const uiState = deriveBatchUiState(batch)
    if (uiState.actionType === 'process') {
      await processBatchNow(batch)
      return
    }
    navigate(`/winkels/batch/${batch.batch_id}`)
  }

  return (
    <AppShell title="Winkelimport" showExit={false}>
      <div style={{ display: 'grid', gap: '16px' }}>
        <Card>
          <div data-testid="stores-page-intro" style={{ display: 'flex', justifyContent: 'space-between', gap: '12px', flexWrap: 'wrap', alignItems: 'center' }}>
            <div style={{ display: 'grid', gap: '8px' }}>
              <h2 style={{ margin: 0, fontSize: '20px' }}>Winkelimport</h2>
              <p style={{ margin: 0, color: '#667085' }}>
                Werk eerst je open bonnen af. Verbonden winkels beheer je hieronder.
              </p>
            </div>
            <Button variant="secondary" onClick={() => navigate('/home')}>Terug naar start</Button>
          </div>
        </Card>

        <Card>
          <div data-testid="store-import-simplification-banner" className="rz-inline-feedback rz-inline-feedback--warning" style={{ display: 'flex', justifyContent: 'space-between', gap: '12px', flexWrap: 'wrap', padding: '4px 0' }}>
            <span>Vereenvoudigingsniveau winkelimport: <strong>{simplificationLevelLabel}</strong></span>
            <span>{batchItems.length > 0 ? `${batchItems.length} open bon(nen)` : 'Geen open bonnen'} in deze huishoudcontext.</span>
          </div>
        </Card>

        {error ? (
          <Card>
            <div style={{ color: '#b42318', fontWeight: 700 }}>{error}</div>
          </Card>
        ) : null}

        {status ? (
          <Card>
            <div style={{ color: '#0f5132', fontWeight: 700 }}>{status}</div>
          </Card>
        ) : null}

        <Card>
          <div data-testid="open-batches-section" style={{ display: 'grid', gap: '12px' }}>
            <div>
              <h3 style={{ margin: '0 0 4px 0', fontSize: '18px' }}>Open bonnen</h3>
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

                    <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(180px, 1fr))', gap: '10px', color: '#667085', fontSize: '14px' }}>
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

        <Card>
          <div data-testid="connected-stores-section">
            {isLoading ? (
              <div>Winkelgegevens laden…</div>
            ) : (
              <div style={{ display: 'grid', gap: '14px' }}>
                <div>
                  <h3 style={{ margin: '0 0 4px 0', fontSize: '18px' }}>Verbonden winkels</h3>
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
                        <div style={{ color: '#667085', fontSize: '14px' }}>Status: {connection ? 'gekoppeld / actief' : providerStatusLabel(provider)}</div>
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
    </AppShell>
  )
}
