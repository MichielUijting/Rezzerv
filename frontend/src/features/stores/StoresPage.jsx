import { useEffect, useMemo, useRef, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import AppShell from '../../app/AppShell'
import Card from '../../ui/Card'
import Button from '../../ui/Button'
import { getStoreImportSimplificationLabel } from '../settings/services/storeImportSimplificationService'
import {
  batchStatusPillStyle,
  batchStatusToneStyles,
  deriveBatchUiState,
  fetchJson,
  formatBatchLastChange,
  normalizeErrorMessage,
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

function sourceTypeLabel(item) {
  if (!item) return 'Onbekend'
  if (item.staticType) return item.staticType
  if (item.connection) return 'Klantkaart'
  return 'Nog niet gekoppeld'
}

function sourceStatusLabel(item) {
  if (!item) return 'Onbekend'
  if (item.staticStatus) return item.staticStatus
  return item.connection ? 'Actief' : 'Aandacht nodig'
}

function sourceActionLabel(item) {
  if (!item) return 'Open'
  if (item.staticAction) return item.staticAction
  return item.connection ? 'Inlezen' : 'Koppelen'
}

export default function StoresPage() {
  const navigate = useNavigate()
  const [household, setHousehold] = useState(null)
  const [providers, setProviders] = useState([])
  const [connections, setConnections] = useState([])
  const [openBatches, setOpenBatches] = useState([])
  const [latestImports, setLatestImports] = useState([])
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

  const importLevelLabel = getStoreImportSimplificationLabel(household?.store_import_simplification_level || 'gebalanceerd')

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

  const sourceItems = useMemo(() => {
    const base = connectedStoreItems.map((item) => ({
      ...item,
      staticType: null,
      staticStatus: null,
      staticAction: null,
    }))
    return [
      ...base,
      { code: 'photo-import', name: 'Foto-import', staticType: 'Foto', staticStatus: 'Beschikbaar', staticAction: 'Foto toevoegen' },
      { code: 'barcode-import', name: 'Barcode-import', staticType: 'Barcode', staticStatus: 'Beschikbaar', staticAction: 'Scan product' },
    ]
  }, [connectedStoreItems])

  const newPurchaseItems = useMemo(() => {
    const merged = latestImports.map((item) => {
      const openBatch = batchItems.find((batch) => batch.batch_id === item.batch_id) || null
      const typeLabel = openBatch ? 'Kassabon' : 'Import'
      const contentLabel = openBatch
        ? `${openBatch.summary?.total || openBatch.lines?.length || 0} regels`
        : (item.item_count ? `${item.item_count} regels` : 'Nieuwe aankoop')
      const statusLabel = openBatch ? 'Open werkblad beschikbaar' : 'Recent ingelezen'
      return {
        key: item.batch_id || `${item.connection_id}-${item.created_at || ''}`,
        sourceName: item.store_provider_name || item.store_name || 'Bron',
        dateLabel: item.purchase_date || item.created_at || 'Onbekend',
        typeLabel,
        contentLabel,
        statusLabel,
        batchId: item.batch_id || null,
      }
    })
    return merged.sort((a, b) => String(b.dateLabel || '').localeCompare(String(a.dateLabel || ''))).slice(0, 5)
  }, [latestImports, batchItems])

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

  async function loadLatestImports(connectionsToCheck) {
    const latestCandidates = (await Promise.all((connectionsToCheck || []).map(async (connection) => {
      const latest = await getLatestBatchMeta(connection.id)
      if (!latest) return null
      return {
        ...latest,
        connection_id: connection.id,
        store_provider_name: connection.store_provider_name || latest.store_provider_name || connection.store_provider_code,
      }
    }))).filter(Boolean)
    setLatestImports(latestCandidates)
    return latestCandidates
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
      await Promise.all([
        loadOpenBatches(connectionData),
        loadLatestImports(connectionData),
      ])
    } catch (err) {
      setError(normalizeErrorMessage(err?.message) || 'Aankoopgegevens konden niet worden geladen.')
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
      await Promise.all([loadOpenBatches(nextConnections), loadLatestImports(nextConnections)])
      showStatus(`${providerName || providerCode} is gekoppeld als bron voor aankopen.`)
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
        await Promise.all([loadOpenBatches(connections), loadLatestImports(connections)])
        showStatus(`De laatste open aankoop van ${providerName || 'de bron'} is opnieuw geladen.`)
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
        showStatus(`Nieuwe aankopen van ${providerName || 'de bron'} zijn binnen. ${fullyPrefilled} regel(s) staan al klaar; ${articlePrefills} regel(s) hebben een voorstel.`)
      } else {
        showStatus(`Nieuwe aankopen van ${providerName || 'de bron'} zijn binnengekomen.`)
      }
      const refreshedConnections = await fetchJson(`/api/store-connections?householdId=${encodeURIComponent(household.id)}`)
      setConnections(refreshedConnections)
      await Promise.all([loadOpenBatches(refreshedConnections), loadLatestImports(refreshedConnections)])
    } catch (err) {
      setError(normalizeErrorMessage(err?.message) || 'Aankopen konden niet worden opgehaald.')
    } finally {
      setIsPulling(false)
    }
  }

  function handleSourceAction(item) {
    if (item.code === 'photo-import') {
      showStatus('Foto-import is voorzien in de module Aankopen, maar nog niet actief in deze ontwikkelstap.')
      return
    }
    if (item.code === 'barcode-import') {
      showStatus('Barcode-import is voorzien in de module Aankopen, maar nog niet actief in deze ontwikkelstap.')
      return
    }
    if (!item.connection && item.provider) {
      handleConnect(item.code, item.name)
      return
    }
    if (item.connection) {
      handlePullPurchases(item.connection, item.name)
    }
  }

  function handlePrimaryBatchAction(batch) {
    if (!batch) return
    navigate(`/winkels/batch/${batch.batch_id}`)
  }

  return (
    <AppShell title="Aankopen" showExit={false}>
      <div style={{ display: 'grid', gap: '16px' }}>
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
          <div style={{ display: 'grid', gap: '12px' }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', gap: '12px', flexWrap: 'wrap', alignItems: 'center' }}>
              <div style={{ display: 'grid', gap: '6px' }}>
                <h2 style={{ margin: 0, fontSize: '20px' }}>Bronnen</h2>
                <div style={{ color: '#667085', fontSize: '14px' }}>Beheer hier hoe aankopen in Rezzerv binnenkomen.</div>
              </div>
              <div style={{ display: 'flex', gap: '10px', flexWrap: 'wrap' }}>
                <Button variant="secondary" onClick={() => navigate('/home')}>Terug naar start</Button>
                <Button variant="secondary" onClick={() => navigate('/instellingen/winkelimport')}>Instellingen</Button>
              </div>
            </div>
            <div style={{ display: 'grid', gridTemplateColumns: 'minmax(220px, 280px) 1fr', gap: '12px', alignItems: 'center' }}>
              <div style={{ fontWeight: 700 }}>Importniveau aankopen</div>
              <div className="rz-inline-feedback rz-inline-feedback--warning" style={{ padding: '10px 12px' }}>
                <strong>{importLevelLabel}</strong>
              </div>
            </div>
            {isLoading ? (
              <div>Bronnen laden…</div>
            ) : (
              <div style={{ overflowX: 'auto' }}>
                <table style={{ width: '100%', borderCollapse: 'collapse' }}>
                  <thead>
                    <tr style={{ textAlign: 'left', borderBottom: '1px solid #d0d5dd' }}>
                      <th style={{ padding: '10px 8px' }}>Bron</th>
                      <th style={{ padding: '10px 8px' }}>Type</th>
                      <th style={{ padding: '10px 8px' }}>Status</th>
                      <th style={{ padding: '10px 8px' }}>Laatste synchronisatie</th>
                      <th style={{ padding: '10px 8px' }}>Importstand</th>
                      <th style={{ padding: '10px 8px' }}>Actie</th>
                    </tr>
                  </thead>
                  <tbody>
                    {sourceItems.map((item) => {
                      const providerOpenBatch = batchItems.find((batch) => batch.store_provider_code === item.code) || null
                      const syncLabel = item.staticType ? '-' : (providerOpenBatch ? formatBatchLastChange(providerOpenBatch) : 'Nog nooit')
                      const importLabel = item.staticType ? 'Handmatig' : (item.connection ? importLevelLabel : 'Handmatig')
                      return (
                        <tr key={item.code} style={{ borderBottom: '1px solid #eaecf0' }}>
                          <td style={{ padding: '12px 8px', fontWeight: 700 }}>{item.name}</td>
                          <td style={{ padding: '12px 8px' }}>{sourceTypeLabel(item)}</td>
                          <td style={{ padding: '12px 8px' }}>{sourceStatusLabel(item)}</td>
                          <td style={{ padding: '12px 8px' }}>{syncLabel}</td>
                          <td style={{ padding: '12px 8px' }}>{importLabel}</td>
                          <td style={{ padding: '12px 8px' }}>
                            <div style={{ display: 'flex', gap: '8px', flexWrap: 'wrap' }}>
                              <Button variant={item.connection || item.staticType ? 'secondary' : 'primary'} onClick={() => handleSourceAction(item)} disabled={isConnecting || isPulling}>
                                {isConnecting || isPulling ? 'Bezig…' : sourceActionLabel(item)}
                              </Button>
                              {!item.staticType ? <Button variant="secondary" onClick={() => navigate('/instellingen/winkelimport')}>Instellingen</Button> : null}
                            </div>
                          </td>
                        </tr>
                      )
                    })}
                  </tbody>
                </table>
              </div>
            )}
          </div>
        </Card>

        <Card>
          <div style={{ display: 'grid', gap: '12px' }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', gap: '12px', flexWrap: 'wrap', alignItems: 'center' }}>
              <div>
                <h3 style={{ margin: '0 0 4px 0', fontSize: '18px' }}>Nieuwe aankopen</h3>
                <div style={{ color: '#667085', fontSize: '14px' }}>Nieuwe imports en aankopen die net zijn binnengekomen.</div>
              </div>
              <Button variant="secondary" onClick={loadPageData} disabled={isLoading}>Vernieuwen</Button>
            </div>
            {isLoading ? (
              <div>Nieuwe aankopen laden…</div>
            ) : newPurchaseItems.length === 0 ? (
              <div style={{ display: 'grid', gap: '12px', color: '#667085' }}>
                <div>Er zijn nu geen nieuwe aankopen.</div>
                <div>Kies hieronder een bron en lees nieuwe aankopen in.</div>
              </div>
            ) : (
              <div style={{ overflowX: 'auto' }}>
                <table style={{ width: '100%', borderCollapse: 'collapse' }}>
                  <thead>
                    <tr style={{ textAlign: 'left', borderBottom: '1px solid #d0d5dd' }}>
                      <th style={{ padding: '10px 8px' }}>Bron</th>
                      <th style={{ padding: '10px 8px' }}>Datum</th>
                      <th style={{ padding: '10px 8px' }}>Type</th>
                      <th style={{ padding: '10px 8px' }}>Inhoud</th>
                      <th style={{ padding: '10px 8px' }}>Status</th>
                      <th style={{ padding: '10px 8px' }}>Actie</th>
                    </tr>
                  </thead>
                  <tbody>
                    {newPurchaseItems.map((item) => (
                      <tr key={item.key} style={{ borderBottom: '1px solid #eaecf0' }}>
                        <td style={{ padding: '12px 8px', fontWeight: 700 }}>{item.sourceName}</td>
                        <td style={{ padding: '12px 8px' }}>{item.dateLabel}</td>
                        <td style={{ padding: '12px 8px' }}>{item.typeLabel}</td>
                        <td style={{ padding: '12px 8px' }}>{item.contentLabel}</td>
                        <td style={{ padding: '12px 8px' }}>{item.statusLabel}</td>
                        <td style={{ padding: '12px 8px' }}>
                          {item.batchId ? (
                            <Button variant="secondary" onClick={() => navigate(`/winkels/batch/${item.batchId}`)}>Open</Button>
                          ) : (
                            <Button variant="secondary" disabled>Beoordeel</Button>
                          )}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </div>
        </Card>

        <Card>
          <div data-testid="open-batches-section" style={{ display: 'grid', gap: '12px' }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', gap: '12px', flexWrap: 'wrap', alignItems: 'center' }}>
              <div>
                <h3 style={{ margin: '0 0 4px 0', fontSize: '18px' }}>Open en verwerk</h3>
                <div style={{ color: '#667085', fontSize: '14px' }}>Werkbladen die nog naar voorraad moeten worden verwerkt.</div>
              </div>
              <Button variant="secondary" onClick={loadPageData} disabled={isLoading}>Vernieuwen</Button>
            </div>

            {isLoading ? (
              <div>Werkbladen laden…</div>
            ) : batchItems.length === 0 ? (
              <div data-testid="open-batches-empty" style={{ display: 'grid', gap: '12px', color: '#667085' }}>
                <div>Er zijn nu geen open werkbladen.</div>
                <div>Lees eerst aankopen in bij een bron of bekijk nieuwe aankopen hierboven.</div>
              </div>
            ) : (
              <div style={{ overflowX: 'auto' }}>
                <table style={{ width: '100%', borderCollapse: 'collapse' }}>
                  <thead>
                    <tr style={{ textAlign: 'left', borderBottom: '1px solid #d0d5dd' }}>
                      <th style={{ padding: '10px 8px' }}>Bron</th>
                      <th style={{ padding: '10px 8px' }}>Datum</th>
                      <th style={{ padding: '10px 8px' }}>Regels</th>
                      <th style={{ padding: '10px 8px' }}>Klaar</th>
                      <th style={{ padding: '10px 8px' }}>Actie nodig</th>
                      <th style={{ padding: '10px 8px' }}>Status</th>
                      <th style={{ padding: '10px 8px' }}>Actie</th>
                    </tr>
                  </thead>
                  <tbody>
                    {batchItems.map((batch) => {
                      const totalLines = batch.summary?.total || batch.lines?.length || 0
                      const readyCount = batch.summary?.ready || batch.summary?.ready_to_process || 0
                      const actionNeeded = batch.summary?.action_needed || Math.max(0, totalLines - readyCount - (batch.summary?.ignored || 0) - (batch.summary?.processed || 0))
                      return (
                        <tr key={batch.batch_id} data-testid={`open-batch-${batch.batch_id}`} style={{ borderBottom: '1px solid #eaecf0' }}>
                          <td style={{ padding: '12px 8px', fontWeight: 700 }}>{batch.store_provider_name || batch.store_name}</td>
                          <td style={{ padding: '12px 8px' }}>{batch.purchase_date || 'Onbekend'}</td>
                          <td style={{ padding: '12px 8px' }}>{totalLines}</td>
                          <td style={{ padding: '12px 8px' }}>{readyCount}</td>
                          <td style={{ padding: '12px 8px' }}>{actionNeeded}</td>
                          <td style={{ padding: '12px 8px' }}>
                            <span style={{ ...batchStatusPillStyle, ...(batchStatusToneStyles[batch.uiState.statusKey] || batchStatusToneStyles.open) }}>{batch.uiState.label}</span>
                          </td>
                          <td style={{ padding: '12px 8px' }}>
                            <Button
                              data-testid={`batch-primary-action-${batch.batch_id}`}
                              variant={batch.uiState.actionType === 'process' ? 'primary' : 'secondary'}
                              onClick={() => handlePrimaryBatchAction(batch)}
                              disabled={busyBatchId === batch.batch_id || isProcessingBatch}
                            >
                              {busyBatchId === batch.batch_id ? 'Bezig…' : 'Open werkblad'}
                            </Button>
                          </td>
                        </tr>
                      )
                    })}
                  </tbody>
                </table>
              </div>
            )}
          </div>
        </Card>
      </div>
    </AppShell>
  )
}
