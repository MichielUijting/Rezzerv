import { useEffect, useMemo, useState } from 'react'
import { useLocation, useNavigate } from 'react-router-dom'
import AppShell from '../../app/AppShell'
import ScreenCard from '../../ui/ScreenCard'
import Button from '../../ui/Button'
import { StoreBatchDetailContent } from './StoreBatchDetailPage'
import {
  batchStatusLabel,
  deriveBatchUiState,
  fetchJson,
  normalizeErrorMessage,
  providerLabel,
} from './storeImportShared'

async function getLatestBatchMeta(connectionId) {
  try {
    const latest = await fetchJson(`/api/store-connections/${connectionId}/latest-batch`)
    return latest?.batch_id ? latest : null
  } catch {
    return null
  }
}

function formatDateTime(value) {
  if (!value) return '-'
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return String(value)
  return new Intl.DateTimeFormat('nl-NL', {
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
  }).format(date)
}

function formatMoney(value, currency = 'EUR') {
  if (value === null || value === undefined || value === '') return '-'
  const number = Number(value)
  if (Number.isNaN(number)) return String(value)
  try {
    return new Intl.NumberFormat('nl-NL', {
      style: 'currency',
      currency: currency || 'EUR',
      minimumFractionDigits: 2,
      maximumFractionDigits: 2,
    }).format(number)
  } catch {
    return `${number.toFixed(2)} ${currency || 'EUR'}`
  }
}

function parseReceiptStatusLabel(value) {
  if (value === 'parsed') return 'Geparsed'
  if (value === 'partial') return 'Gedeeltelijk herkend'
  if (value === 'review_needed') return 'Controle nodig'
  if (value === 'failed') return 'Niet herkend'
  return value || '-'
}

export default function ReceiptsPage() {
  const [providers, setProviders] = useState([])
  const [batches, setBatches] = useState([])
  const [filters, setFilters] = useState({ winkel: '', datum: '', regels: '', status: '' })
  const [isLoading, setIsLoading] = useState(true)
  const [error, setError] = useState('')
  const [selectedBatchIds, setSelectedBatchIds] = useState([])
  const [openedBatchId, setOpenedBatchId] = useState('')
  const location = useLocation()
  const navigate = useNavigate()
  const [receiptContext, setReceiptContext] = useState(() => location?.state?.receiptContext || null)
  const [receiptContextError, setReceiptContextError] = useState('')

  const providersByCode = useMemo(
    () => Object.fromEntries(providers.map((provider) => [provider.code, provider])),
    [providers],
  )

  useEffect(() => {
    let cancelled = false

    async function loadData() {
      setIsLoading(true)
      setError('')
      try {
        const token = localStorage.getItem('rezzerv_token')
        const householdData = await fetchJson('/api/household', {
          headers: token ? { Authorization: `Bearer ${token}` } : {},
        })
        if (cancelled) return

        const [providerData, connectionData] = await Promise.all([
          fetchJson('/api/store-providers'),
          fetchJson(`/api/store-connections?householdId=${encodeURIComponent(householdData.id)}`),
        ])
        if (cancelled) return
        setProviders(providerData || [])

        const latestCandidates = (await Promise.all((connectionData || []).map((connection) => getLatestBatchMeta(connection.id))))
          .filter((item) => item?.batch_id)

        const loadedBatches = (await Promise.all(
          latestCandidates.map((item) => fetchJson(`/api/purchase-import-batches/${item.batch_id}`).catch(() => null)),
        )).filter(Boolean)

        if (cancelled) return
        setBatches(loadedBatches)
      } catch (err) {
        if (!cancelled) {
          setError(normalizeErrorMessage(err?.message) || 'Uitpakken kon niet worden geladen.')
        }
      } finally {
        if (!cancelled) setIsLoading(false)
      }
    }

    loadData()
    return () => { cancelled = true }
  }, [location.search])

  useEffect(() => {
    const params = new URLSearchParams(location.search)
    const requestedReceiptId = String(params.get('receipt_table_id') || '').trim()
    const routeReceiptContext = location.state?.receiptContext || null

    if (routeReceiptContext && String(routeReceiptContext?.id || '') === requestedReceiptId) {
      setReceiptContext(routeReceiptContext)
      setReceiptContextError('')
      return
    }

    if (!requestedReceiptId) {
      setReceiptContext(routeReceiptContext)
      setReceiptContextError('')
      return
    }

    let cancelled = false
    setReceiptContextError('')
    fetchJson(`/api/receipts/${encodeURIComponent(requestedReceiptId)}`)
      .then((result) => {
        if (!cancelled) setReceiptContext(result || null)
      })
      .catch((err) => {
        if (!cancelled) {
          setReceiptContext(null)
          setReceiptContextError(normalizeErrorMessage(err?.message) || 'De bon uit Kassa kon niet worden geladen in Uitpakken.')
        }
      })

    return () => { cancelled = true }
  }, [location.search, location.state])

  const listItems = useMemo(() => {
    const enriched = (batches || []).map((batch) => ({
      ...batch,
      uiState: deriveBatchUiState(batch),
      providerName: providerLabel(providersByCode[batch?.store_provider_code] || batch),
      dateLabel: batch.purchase_date || batch.created_at?.slice(0, 10) || '-',
      totalLines: Number(batch.summary?.total || batch.lines?.length || 0),
      statusLabel: (() => {
        const summary = batch.summary || {}
        const openCount = Number(summary.open || 0)
        const readyCount = Number(summary.ready || 0)
        const processedCount = Number(summary.processed || 0)
        const totalCount = Number(summary.total || batch.lines?.length || 0)
        if (processedCount > 0 && processedCount >= totalCount && openCount === 0 && readyCount === 0) return 'Volledig verwerkt'
        if (processedCount > 0 || openCount > 0 || readyCount > 0) return 'Deels verwerkt'
        return 'Niet verwerkt'
      })(),
    }))

    return enriched
      .filter((item) => String(item.providerName || '').toLowerCase().includes(filters.winkel.trim().toLowerCase()))
      .filter((item) => String(item.dateLabel || '').toLowerCase().includes(filters.datum.trim().toLowerCase()))
      .filter((item) => String(item.totalLines).includes(filters.regels.trim()))
      .filter((item) => String(item.statusLabel || '').toLowerCase().includes(filters.status.trim().toLowerCase()))
      .sort((a, b) => String(b.created_at || '').localeCompare(String(a.created_at || '')))
  }, [batches, providersByCode, filters])

  useEffect(() => {
    if (!listItems.length) {
      setSelectedBatchIds([])
      setOpenedBatchId('')
      return
    }
    const visibleIds = new Set(listItems.map((item) => item.batch_id))
    setSelectedBatchIds((current) => current.filter((id) => visibleIds.has(id)))
    if (openedBatchId && !visibleIds.has(openedBatchId)) {
      setOpenedBatchId('')
    }
  }, [listItems, openedBatchId])

  function handleFilterChange(key, value) {
    setFilters((current) => ({ ...current, [key]: value }))
  }

  function toggleSelectedBatch(batchId) {
    setSelectedBatchIds((current) => (
      current.includes(batchId)
        ? current.filter((id) => id !== batchId)
        : [...current, batchId]
    ))
  }

  function toggleSelectAllVisible() {
    if (!listItems.length) return
    const visibleIds = listItems.map((item) => item.batch_id)
    const allVisibleSelected = visibleIds.every((id) => selectedBatchIds.includes(id))
    setSelectedBatchIds(allVisibleSelected ? [] : visibleIds)
  }

  function handleExport() {
    const selectedIds = selectedBatchIds.length ? new Set(selectedBatchIds) : null
    const rows = listItems.filter((item) => !selectedIds || selectedIds.has(item.batch_id))
    const header = ['Winkel', 'Datum', 'Regels', 'Status']
    const csvRows = rows.map((item) => [item.providerName, item.dateLabel, String(item.totalLines), item.statusLabel])
    const csv = [header, ...csvRows]
      .map((row) => row.map((value) => `"${String(value ?? '').replace(/"/g, '""')}"`).join(';'))
      .join('\n')
    const blob = new Blob([csv], { type: 'text/csv;charset=utf-8;' })
    const url = window.URL.createObjectURL(blob)
    const link = document.createElement('a')
    link.href = url
    link.download = 'rezzerv-uitpakken.csv'
    document.body.appendChild(link)
    link.click()
    link.remove()
    window.URL.revokeObjectURL(url)
  }

  function handleDeleteSelected() {
    if (selectedBatchIds.length === 0) return
    const selectedSet = new Set(selectedBatchIds)
    setBatches((current) => current.filter((batch) => !selectedSet.has(batch.batch_id)))
    if (openedBatchId && selectedSet.has(openedBatchId)) {
      setOpenedBatchId('')
    }
    setSelectedBatchIds([])
  }

  const allVisibleSelected = listItems.length > 0 && listItems.every((item) => selectedBatchIds.includes(item.batch_id))
  const receiptContextVisible = Boolean(receiptContext || receiptContextError)

  return (
    <AppShell title="Uitpakken" showExit={false}>
      <div style={{ display: 'grid', gap: '16px' }} data-testid="receipts-page">
        {receiptContextVisible ? (
          <ScreenCard>
            <div style={{ display: 'grid', gap: '12px' }} data-testid="uitpakken-receipt-context">
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', gap: '12px', flexWrap: 'wrap' }}>
                <div>
                  <div style={{ fontWeight: 700, fontSize: '24px' }}>Bon uit Kassa</div>
                  <div style={{ color: '#667085', marginTop: '4px' }}>
                    Deze bon is vanuit Kassa geopend en staat hier klaar als context voor het uitpakken.
                  </div>
                </div>
                <div className="rz-stock-table-actions" style={{ justifyContent: 'flex-start' }}>
                  <Button type="button" variant="secondary" onClick={() => navigate('/kassa')}>Terug naar Kassa</Button>
                </div>
              </div>

              {receiptContextError ? (
                <div className="rz-inline-feedback rz-inline-feedback--error">{receiptContextError}</div>
              ) : null}

              {receiptContext ? (
                <div style={{ display: 'grid', gap: '12px', gridTemplateColumns: 'repeat(auto-fit, minmax(180px, 1fr))' }}>
                  <div><strong>Winkel</strong><div>{receiptContext.store_name || 'Onbekende winkel'}</div></div>
                  <div><strong>Aankoopmoment</strong><div>{formatDateTime(receiptContext.purchase_at)}</div></div>
                  <div><strong>Totaal</strong><div>{formatMoney(receiptContext.total_amount, receiptContext.currency)}</div></div>
                  <div><strong>Bonregels</strong><div>{receiptContext.line_count ?? receiptContext.lines?.length ?? 0}</div></div>
                  <div><strong>Parse-status</strong><div>{parseReceiptStatusLabel(receiptContext.parse_status)}</div></div>
                  <div><strong>Receipt ID</strong><div>{receiptContext.id || '-'}</div></div>
                </div>
              ) : null}
            </div>
          </ScreenCard>
        ) : null}

        <ScreenCard>
        {error ? <div className="rz-inline-feedback rz-inline-feedback--error" style={{ marginBottom: '12px' }}>{error}</div> : null}
        <div className="rz-table-wrapper">
          <table className="rz-table" data-testid="receipts-table">
            <thead>
              <tr className="rz-table-header">
                <th style={{ width: '44px' }}>
                  <input
                    type="checkbox"
                    checked={allVisibleSelected}
                    onChange={toggleSelectAllVisible}
                    aria-label="Selecteer alle zichtbare bonnen in Uitpakken"
                  />
                </th>
                <th style={{ width: '26.6%' }}>Winkel</th>
                <th style={{ width: '22%' }}>Datum</th>
                <th className="rz-num" style={{ width: '12%' }}>Artikelen</th>
                <th style={{ width: '39.4%' }}>Status</th>
              </tr>
              <tr className="rz-table-filters">
                <th />
                <th>
                  <input
                    className="rz-input rz-inline-input"
                    value={filters.winkel}
                    onChange={(event) => handleFilterChange('winkel', event.target.value)}
                    placeholder="Filter"
                    aria-label="Filter op winkel"
                  />
                </th>
                <th>
                  <input
                    className="rz-input rz-inline-input"
                    value={filters.datum}
                    onChange={(event) => handleFilterChange('datum', event.target.value)}
                    placeholder="Filter"
                    aria-label="Filter op datum"
                  />
                </th>
                <th>
                  <input
                    className="rz-input rz-inline-input"
                    value={filters.regels}
                    onChange={(event) => handleFilterChange('regels', event.target.value)}
                    placeholder="Filter"
                    aria-label="Filter op artikelen"
                  />
                </th>
                <th>
                  <input
                    className="rz-input rz-inline-input"
                    value={filters.status}
                    onChange={(event) => handleFilterChange('status', event.target.value)}
                    placeholder="Filter"
                    aria-label="Filter op status"
                  />
                </th>
              </tr>
            </thead>
            <tbody>
              {isLoading ? (
                <tr><td colSpan={5}>Bonnen laden…</td></tr>
              ) : listItems.length === 0 ? (
                <tr><td colSpan={5}>Er zijn nog geen bonnen om uit te pakken.</td></tr>
              ) : listItems.map((item) => {
                const selected = selectedBatchIds.includes(item.batch_id)
                return (
                  <tr
                    key={item.batch_id}
                    data-testid={`receipt-batch-row-${item.batch_id}`}
                    className={selected ? 'rz-row-selected' : ''}
                    onClick={() => toggleSelectedBatch(item.batch_id)}
                    onDoubleClick={() => {
                      if (!selected) toggleSelectedBatch(item.batch_id)
                      setOpenedBatchId(item.batch_id)
                    }}
                    style={{ cursor: 'pointer' }}
                  >
                    <td onClick={(event) => event.stopPropagation()}>
                      <button
                        type="button"
                        data-testid={`receipt-batch-open-${item.batch_id}`}
                        onClick={(event) => { event.stopPropagation(); setOpenedBatchId(item.batch_id) }}
                        style={{ display: 'none' }}
                        aria-hidden="true"
                        tabIndex={-1}
                      />
                      <input
                        type="checkbox"
                        checked={selected}
                        onChange={() => toggleSelectedBatch(item.batch_id)}
                        aria-label={`Selecteer ${item.providerName} van ${item.dateLabel}`}
                      />
                    </td>
                    <td className="rz-receipts-cell">{item.providerName}</td>
                    <td className="rz-receipts-cell">{item.dateLabel}</td>
                    <td className="rz-num rz-receipts-cell">{item.totalLines}</td>
                    <td className="rz-receipts-cell">{item.statusLabel}</td>
                  </tr>
                )
              })}
            </tbody>
          </table>
        </div>
        <div className="rz-stock-table-actions">
          <Button type="button" variant="secondary" onClick={handleExport} disabled={isLoading || listItems.length === 0}>Exporteren</Button>
          <Button type="button" variant="secondary" onClick={handleDeleteSelected} disabled={selectedBatchIds.length === 0}>Verwijderen</Button>
          {openedBatchId ? <Button type="button" variant="secondary" onClick={() => setOpenedBatchId('')} data-testid="receipt-back-to-overview">Terug naar overzicht</Button> : null}
        </div>
        </ScreenCard>

        {openedBatchId ? <StoreBatchDetailContent batchIdOverride={openedBatchId} embedded /> : null}
      </div>
    </AppShell>
  )
}
