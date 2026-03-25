import { useEffect, useMemo, useState } from 'react'
import { useLocation } from 'react-router-dom'
import AppShell from '../../app/AppShell'
import ScreenCard from '../../ui/ScreenCard'
import Button from '../../ui/Button'
import { StoreBatchDetailContent } from './StoreBatchDetailPage'
import { fetchJson, normalizeErrorMessage, providerLabel } from './storeImportShared'
import { nextSortState, sortItems } from '../../ui/sorting'

export default function ReceiptsPage() {
  const [batches, setBatches] = useState([])
  const [filters, setFilters] = useState({ winkel: '', datum: '', regels: '', status: '' })
  const [isLoading, setIsLoading] = useState(true)
  const [error, setError] = useState('')
  const [selectedBatchIds, setSelectedBatchIds] = useState([])
  const [openedBatchId, setOpenedBatchId] = useState('')
  const [tableSort, setTableSort] = useState({ key: 'datum', direction: 'desc' })
  const location = useLocation()


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

        const unpackData = await fetchJson(`/api/unpack-start-batches?householdId=${encodeURIComponent(householdData.id)}`)
        if (cancelled) return
        setBatches(Array.isArray(unpackData?.items) ? unpackData.items : [])
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
  }, [location.search])

  const listItems = useMemo(() => {
    const enriched = (batches || []).map((batch) => ({
      ...batch,
      providerName: providerLabel(batch),
      dateLabel: batch.purchase_date || batch.created_at?.slice(0, 10) || '-',
      totalLines: Number(batch.summary?.total || batch.lines?.length || 0),
      statusLabel: batch.inbox_status || 'Nieuw',
    }))

    const filtered = enriched
      .filter((item) => String(item.providerName || '').toLowerCase().includes(filters.winkel.trim().toLowerCase()))
      .filter((item) => String(item.dateLabel || '').toLowerCase().includes(filters.datum.trim().toLowerCase()))
      .filter((item) => String(item.totalLines).includes(filters.regels.trim()))
      .filter((item) => String(item.statusLabel || '').toLowerCase().includes(filters.status.trim().toLowerCase()))

    return sortItems(filtered, tableSort, {
      winkel: (item) => item.providerName || '',
      datum: (item) => item.purchase_date || item.created_at || '',
      regels: (item) => Number(item.totalLines ?? 0),
      status: (item) => item.statusLabel || '',
    })
  }, [batches, filters, tableSort])

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

  return (
    <AppShell title="Uitpakken" showExit={false}>
      <div style={{ display: 'grid', gap: '16px' }} data-testid="receipts-page">
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
                    aria-label="Selecteer alle zichtbare kassabonnen"
                  />
                </th>
                <th style={{ width: '26.6%' }}><button type="button" className="rz-sort-button" onClick={() => setTableSort((current) => nextSortState(current, 'winkel', { winkel: 'asc', datum: 'desc', regels: 'desc', status: 'asc' }))}><span>Winkel</span><span className={`rz-sort-indicator${tableSort.key === 'winkel' ? ' is-active' : ''}`} aria-hidden="true">{tableSort.key === 'winkel' ? (tableSort.direction === 'asc' ? '▲' : '▼') : '↕'}</span></button></th>
                <th style={{ width: '22%' }}><button type="button" className="rz-sort-button" onClick={() => setTableSort((current) => nextSortState(current, 'datum', { winkel: 'asc', datum: 'desc', regels: 'desc', status: 'asc' }))}><span>Datum</span><span className={`rz-sort-indicator${tableSort.key === 'datum' ? ' is-active' : ''}`} aria-hidden="true">{tableSort.key === 'datum' ? (tableSort.direction === 'asc' ? '▲' : '▼') : '↕'}</span></button></th>
                <th className="rz-num" style={{ width: '12%' }}><button type="button" className="rz-sort-button rz-sort-button--numeric" onClick={() => setTableSort((current) => nextSortState(current, 'regels', { winkel: 'asc', datum: 'desc', regels: 'desc', status: 'asc' }))}><span>Artikelen</span><span className={`rz-sort-indicator${tableSort.key === 'regels' ? ' is-active' : ''}`} aria-hidden="true">{tableSort.key === 'regels' ? (tableSort.direction === 'asc' ? '▲' : '▼') : '↕'}</span></button></th>
                <th style={{ width: '39.4%' }}><button type="button" className="rz-sort-button" onClick={() => setTableSort((current) => nextSortState(current, 'status', { winkel: 'asc', datum: 'desc', regels: 'desc', status: 'asc' }))}><span>Status</span><span className={`rz-sort-indicator${tableSort.key === 'status' ? ' is-active' : ''}`} aria-hidden="true">{tableSort.key === 'status' ? (tableSort.direction === 'asc' ? '▲' : '▼') : '↕'}</span></button></th>
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
