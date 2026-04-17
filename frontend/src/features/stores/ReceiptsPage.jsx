import { useEffect, useMemo, useState } from 'react'
import { useLocation } from 'react-router-dom'
import AppShell from '../../app/AppShell'
import ScreenCard from '../../ui/ScreenCard'
import Table from '../../ui/Table'
import Button from '../../ui/Button'
import { StoreBatchDetailContent } from './StoreBatchDetailPage'
import { fetchJson, normalizeErrorMessage, providerLabel } from './storeImportShared'
import useDismissOnComponentClick from '../../lib/useDismissOnComponentClick.js'
import { nextSortState, sortItems } from '../../ui/sorting'
import { buildTableWidth, ResizableHeaderCell, useResizableColumnWidths } from '../../ui/resizableTable.jsx'

export default function ReceiptsPage() {
  const [batches, setBatches] = useState([])
  const [filters, setFilters] = useState({ winkel: '', datum: '', regels: '', status: '' })
  const [isLoading, setIsLoading] = useState(true)
  const [error, setError] = useState('')

  useDismissOnComponentClick([() => setError('')], Boolean(error))
  const [selectedBatchIds, setSelectedBatchIds] = useState([])
  const [openedBatchId, setOpenedBatchId] = useState('')
  const [tableSort, setTableSort] = useState({ key: 'datum', direction: 'desc' })
  const location = useLocation()
  const receiptsTableColumns = useMemo(() => ([
    { key: 'select', width: 44 },
    { key: 'winkel', width: 260 },
    { key: 'datum', width: 200 },
    { key: 'regels', width: 120 },
    { key: 'status', width: 300 },
  ]), [])
  const columnDefaults = useMemo(() => Object.fromEntries(receiptsTableColumns.map(({ key, width }) => [key, width])), [receiptsTableColumns])
  const { widths: tableWidths, startResize: startTableResize } = useResizableColumnWidths(columnDefaults)


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
        <Table dataTestId="receipts-table" tableStyle={{ tableLayout: 'fixed', width: buildTableWidth(tableWidths), minWidth: buildTableWidth(tableWidths) }}>
            <colgroup>
              <col style={{ width: `${tableWidths.select}px` }} />
              <col style={{ width: `${tableWidths.winkel}px` }} />
              <col style={{ width: `${tableWidths.datum}px` }} />
              <col style={{ width: `${tableWidths.regels}px` }} />
              <col style={{ width: `${tableWidths.status}px` }} />
            </colgroup>
            <thead>
              <tr className="rz-table-header">
                <ResizableHeaderCell columnKey="select" widths={tableWidths} onStartResize={startTableResize} style={{ width: '44px' }}>
                  <input
                    type="checkbox"
                    checked={allVisibleSelected}
                    onChange={toggleSelectAllVisible}
                    aria-label="Selecteer alle zichtbare kassabonnen"
                  />
                </ResizableHeaderCell>
                <ResizableHeaderCell columnKey="winkel" widths={tableWidths} onStartResize={startTableResize} sortable isSorted={tableSort.key === 'winkel'} sortDirection={tableSort.direction} onSort={(key) => setTableSort((current) => nextSortState(current, key, { winkel: 'asc', datum: 'desc', regels: 'desc', status: 'asc' }))}>Winkel</ResizableHeaderCell>
                <ResizableHeaderCell columnKey="datum" widths={tableWidths} onStartResize={startTableResize} sortable isSorted={tableSort.key === 'datum'} sortDirection={tableSort.direction} onSort={(key) => setTableSort((current) => nextSortState(current, key, { winkel: 'asc', datum: 'desc', regels: 'desc', status: 'asc' }))}>Datum</ResizableHeaderCell>
                <ResizableHeaderCell columnKey="regels" widths={tableWidths} onStartResize={startTableResize} className="rz-num" sortable isSorted={tableSort.key === 'regels'} sortDirection={tableSort.direction} onSort={(key) => setTableSort((current) => nextSortState(current, key, { winkel: 'asc', datum: 'desc', regels: 'desc', status: 'asc' }))}>Artikelen</ResizableHeaderCell>
                <ResizableHeaderCell columnKey="status" widths={tableWidths} onStartResize={startTableResize} sortable isSorted={tableSort.key === 'status'} sortDirection={tableSort.direction} onSort={(key) => setTableSort((current) => nextSortState(current, key, { winkel: 'asc', datum: 'desc', regels: 'desc', status: 'asc' }))}>Status</ResizableHeaderCell>
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
          </Table>
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
