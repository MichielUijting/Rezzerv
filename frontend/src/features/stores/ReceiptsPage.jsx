import { useEffect, useMemo, useState } from 'react'
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

export default function ReceiptsPage() {
  const [providers, setProviders] = useState([])
  const [batches, setBatches] = useState([])
  const [filters, setFilters] = useState({ winkel: '', datum: '', regels: '', status: '' })
  const [isLoading, setIsLoading] = useState(true)
  const [error, setError] = useState('')
  const [selectedBatchIds, setSelectedBatchIds] = useState([])
  const [openedBatchId, setOpenedBatchId] = useState('')

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
          setError(normalizeErrorMessage(err?.message) || 'Kassabonnen konden niet worden geladen.')
        }
      } finally {
        if (!cancelled) setIsLoading(false)
      }
    }

    loadData()
    return () => { cancelled = true }
  }, [])

  const listItems = useMemo(() => {
    const enriched = (batches || []).map((batch) => ({
      ...batch,
      uiState: deriveBatchUiState(batch),
      providerName: providerLabel(providersByCode[batch?.store_provider_code] || batch),
      dateLabel: batch.purchase_date || batch.created_at?.slice(0, 10) || '-',
      totalLines: Number(batch.summary?.total || batch.lines?.length || 0),
      statusLabel: batch.import_status === 'processed' ? 'Verwerkt' : batchStatusLabel(batch.import_status),
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
    link.download = 'rezzerv-kassabonnen.csv'
    document.body.appendChild(link)
    link.click()
    link.remove()
    window.URL.revokeObjectURL(url)
  }

  const allVisibleSelected = listItems.length > 0 && listItems.every((item) => selectedBatchIds.includes(item.batch_id))

  return (
    <AppShell title="Kassabonnen" showExit={false}>
      <ScreenCard>
        {error ? <div className="rz-inline-feedback rz-inline-feedback--error" style={{ marginBottom: '12px' }}>{error}</div> : null}
        <div className="rz-table-wrapper">
          <table className="rz-table">
            <thead>
              <tr className="rz-table-header">
                <th style={{ width: '44px' }}>
                  <input
                    type="checkbox"
                    checked={allVisibleSelected}
                    onChange={toggleSelectAllVisible}
                    aria-label="Selecteer alle zichtbare kassabonnen"
                  />
                </th>
                <th style={{ width: '38%' }}>Winkel</th>
                <th style={{ width: '22%' }}>Datum</th>
                <th className="rz-num" style={{ width: '12%' }}>Artikelen</th>
                <th style={{ width: '20%' }}>Status</th>
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
                <tr><td colSpan={5}>Er zijn nog geen kassabonnen.</td></tr>
              ) : listItems.map((item) => {
                const selected = selectedBatchIds.includes(item.batch_id)
                return (
                  <tr
                    key={item.batch_id}
                    className={selected ? 'rz-row-selected' : ''}
                    onClick={() => toggleSelectedBatch(item.batch_id)}
                    onDoubleClick={() => {
                      if (!selected) toggleSelectedBatch(item.batch_id)
                      setOpenedBatchId(item.batch_id)
                    }}
                    style={{ cursor: 'pointer' }}
                  >
                    <td onClick={(event) => event.stopPropagation()}>
                      <input
                        type="checkbox"
                        checked={selected}
                        onChange={() => toggleSelectedBatch(item.batch_id)}
                        aria-label={`Selecteer ${item.providerName} van ${item.dateLabel}`}
                      />
                    </td>
                    <td>
                      <div style={{ fontWeight: 700 }}>{item.providerName}</div>
                    </td>
                    <td>{item.dateLabel}</td>
                    <td className="rz-num">{item.totalLines}</td>
                    <td>
                      <span className={`rz-store-status-badge rz-store-status-badge--${item.uiState?.statusKey || 'new'}`}>
                        {item.statusLabel}
                      </span>
                      <div style={{ color: '#667085', marginTop: '4px' }}>
                        {(() => {
                          const summary = item?.summary || {}
                          const klaar = Number(summary.ready || item.uiState?.readyCount || 0)
                          const actie = Number(summary.open || item.uiState?.openCount || 0)
                          const verwerkt = Number(summary.processed || 0)
                          if (verwerkt > 0 && actie === 0 && klaar === 0) return 'Volledig verwerkt'
                          if (actie > 0 || klaar > 0) return `${klaar} klaar · ${actie} actie nodig`
                          return 'Nog niet beoordeeld'
                        })()}
                      </div>
                    </td>
                  </tr>
                )
              })}
            </tbody>
          </table>
        </div>
        <div className="rz-stock-table-actions">
          <Button type="button" variant="secondary" onClick={handleExport} disabled={isLoading || listItems.length === 0}>Exporteren</Button>
        </div>
      </ScreenCard>

      {openedBatchId ? <StoreBatchDetailContent batchIdOverride={openedBatchId} embedded /> : null}
    </AppShell>
  )
}
