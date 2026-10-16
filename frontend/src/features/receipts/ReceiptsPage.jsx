import { useEffect, useMemo, useRef, useState } from 'react'
import { useLocation, useNavigate } from 'react-router-dom'
import AppShell from '../../app/AppShell'
import ScreenCard from '../../ui/ScreenCard'
import Table from '../../ui/Table'
import Button from '../../ui/Button'
import { StoreBatchDetailContent } from '../purchaseImport/StoreBatchDetailPage'
import { fetchJson, normalizeErrorMessage, providerLabel } from '../stores/storeImportShared'
import { useAppFeedback } from '../../ui/AppFeedbackProvider.jsx'
import { nextSortState, sortItems } from '../../ui/sorting'
import { buildTableWidth, ResizableHeaderCell, useResizableColumnWidths } from '../../ui/resizableTable.jsx'
import { useMobileAppViewport } from '../../app/mobileViewport.js'
import MobileModuleHeader from '../../ui/MobileModuleHeader.jsx'
import { MobilePaginationControls } from '../../ui/MobilePagination.jsx'
import './mobileReceipts.css'

export default function ReceiptsPage() {
  const [batches, setBatches] = useState([])
  const [page, setPage] = useState(1)
  const [total, setTotal] = useState(0)
  const [refreshVersion, setRefreshVersion] = useState(0)
  const [filters, setFilters] = useState({ winkel: '', datum: '', regels: '', status: '' })
  const [isLoading, setIsLoading] = useState(true)
  const [hasLoadError, setHasLoadError] = useState(false)
  const { showFeedback } = useAppFeedback()
  const [selectedBatchIds, setSelectedBatchIds] = useState([])
  const [selectedBatchesById, setSelectedBatchesById] = useState({})
  const lastHouseholdId = useRef(null)
  const [openedBatchId, setOpenedBatchId] = useState(() => (
    new URLSearchParams(window.location.search).get('batch') || ''
  ))
  const [deleteChoiceOpen, setDeleteChoiceOpen] = useState(false)
  const [isApplyingDeleteChoice, setIsApplyingDeleteChoice] = useState(false)
  const [isBulkApproving, setIsBulkApproving] = useState(false)
  const [tableSort, setTableSort] = useState({ key: 'datum', direction: 'desc' })
  const location = useLocation()
  const navigate = useNavigate()
  const isMobileViewport = useMobileAppViewport()

  useEffect(() => {
    const requestedBatchId = new URLSearchParams(location.search).get('batch') || ''
    setOpenedBatchId(requestedBatchId)
  }, [location.search])
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
      setHasLoadError(false)
      try {
        const householdData = await fetchJson('/api/household')
        if (cancelled) return

        const unpackData = await fetchJson(`/api/unpack-start-batches?${new URLSearchParams({ householdId: householdData.id, page: String(page), page_size: '10', ...filters, sort_key: tableSort.key, sort_direction: tableSort.direction })}`)
        if (cancelled) return
        const householdId = String(householdData.id)
        if (lastHouseholdId.current !== null && lastHouseholdId.current !== householdId) {
          setSelectedBatchIds([])
          setSelectedBatchesById({})
          setOpenedBatchId('')
        }
        lastHouseholdId.current = householdId
        setBatches(Array.isArray(unpackData?.items) ? unpackData.items : [])
        setTotal(Number(unpackData?.total || 0))
      } catch (err) {
        if (!cancelled) {
          setHasLoadError(true)
          showFeedback({
            variant: 'error',
            message: normalizeErrorMessage(err?.message) || 'Kassabonnen konden niet worden geladen.',
            key: 'receipts-load-error',
          })
        }
      } finally {
        if (!cancelled) setIsLoading(false)
      }
    }

    loadData()
    return () => { cancelled = true }
  }, [location.search, showFeedback, page, filters, tableSort, refreshVersion])

  const listItems = useMemo(() => {
    // Uitpakken is een werkvoorraad, geen bonarchief. Zodra de volledige bon
    // naar Voorraad is verwerkt, verdwijnt hij uit dit overzicht.
    const enriched = (batches || [])
      .map((batch) => ({
        ...batch,
        providerName: providerLabel(batch),
        dateLabel: batch.purchase_date || batch.created_at?.slice(0, 10) || '-',
        totalLines: Number(batch.summary?.total ?? batch.lines?.length ?? 0),
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

  // Selection must outlive server-side page changes.
  const selectedBatches = selectedBatchIds
    .map((id) => selectedBatchesById[id])
    .filter(Boolean)

  function handleFilterChange(key, value) {
    setPage(1)
    setFilters((current) => ({ ...current, [key]: value }))
  }

  function toggleSelectedBatch(batchId) {
    const row = listItems.find((item) => item.batch_id === batchId)
    if (!row) return
    const wasSelected = selectedBatchIds.includes(batchId)
    setSelectedBatchIds((current) => wasSelected
      ? current.filter((id) => id !== batchId)
      : [...current, batchId])
    setSelectedBatchesById((current) => {
      const next = { ...current }
      if (wasSelected) delete next[batchId]
      else next[batchId] = row
      return next
    })
  }

  function toggleSelectAllVisible() {
    if (!mobileVisibleItems.length) return
    const visibleIds = mobileVisibleItems.map((item) => item.batch_id)
    const allVisibleSelected = visibleIds.every((id) => selectedBatchIds.includes(id))
    setSelectedBatchIds((current) => allVisibleSelected
      ? current.filter((id) => !visibleIds.includes(id))
      : [...new Set([...current, ...visibleIds])])
    setSelectedBatchesById((current) => {
      const next = { ...current }
      if (allVisibleSelected) visibleIds.forEach((id) => { delete next[id] })
      else mobileVisibleItems.forEach((item) => { next[item.batch_id] = item })
      return next
    })
  }

  function handleExport() {
    const rows = selectedBatches
    const header = ['Winkel', 'Datum', 'Regels', 'Status']
    const csvRows = rows.map((item) => [item.providerName, item.dateLabel, String(item.totalLines), item.statusLabel])
    const csv = [header, ...csvRows]
      .map((row) => row.map((value) => `"${String(value ?? '').replace(/"/g, '""')}"`).join(';'))
      .join('\n')
    const blob = new Blob([csv], { type: 'text/csv;charset=utf-8;' })
    const url = window.URL.createObjectURL(blob)
    const link = document.createElement('a')
    link.href = url
    link.download = 'inhuis-kassabonnen.csv'
    document.body.appendChild(link)
    link.click()
    link.remove()
    window.URL.revokeObjectURL(url)
  }

  async function handleBulkApprove() {
    if (!selectedBatchIds.length || isBulkApproving) return
    setIsBulkApproving(true)
    const selected = selectedBatches
    const eligible = selected.filter((item) => String(item.statusLabel || '').trim().toLowerCase() === 'gecontroleerd')
    const ineligible = selected.length - eligible.length
    let processed = 0
    let skipped = 0
    let failed = 0
    const errors = []
    try {
      for (const item of eligible) {
        try {
          // De bestaande backend beslist per bonregel over geschiktheid, locaties
          // en idempotentie. 'ready_only' verwerkt ook bij een deels onvolledige bon.
          const result = await fetchJson(`/api/purchase-import-batches/${encodeURIComponent(item.batch_id)}/process`, {
            method: 'POST',
            body: JSON.stringify({ processed_by: 'ui', mode: 'ready_only' }),
          })
          processed += Number(result?.processed_count || 0)
          skipped += Number(result?.skipped_count || 0)
          failed += Number(result?.failed_count || 0)
        } catch (error) {
          failed += 1
          errors.push(normalizeErrorMessage(error?.message) || 'Verwerking mislukt')
        }
      }
      setRefreshVersion((current) => current + 1)
      setSelectedBatchIds([])
      setSelectedBatchesById({})
      showFeedback({
        variant: failed ? 'warning' : 'info',
        message: `Voorraadcontrole toegepast: bij actieve voorraadlocaties is een geldige standaardlocatie per artikel vereist. Verwerkt: ${processed} regel(s). Overgeslagen: ${skipped} regel(s). Mislukt: ${failed}. ${ineligible} bon(nen) niet Gecontroleerd en daarom niet aangeboden. Onvolledige bonnen blijven in Uitpakken. ${errors.slice(0, 2).join(' · ')}`,
        key: 'uitpakken-bulk-approve-result',
      })
    } catch (error) {
      showFeedback({
        variant: 'error',
        message: normalizeErrorMessage(error?.message) || 'De Uitpakken-lijst kon niet worden vernieuwd.',
        key: 'uitpakken-bulk-approve-error',
      })
    } finally {
      setIsBulkApproving(false)
    }
  }

  function handleDeleteSelected() {
    if (selectedBatchIds.length === 0) return
    setDeleteChoiceOpen(true)
  }

  async function applyDeleteChoice(action) {
    if (selectedBatchIds.length === 0 || isApplyingDeleteChoice) return
    const selectedSet = new Set(selectedBatchIds)
    if (selectedBatches.length !== selectedBatchIds.length) return

    setIsApplyingDeleteChoice(true)
    try {
      if (action === 'remove') {
        const receiptTableIds = selectedBatches
          .map((item) => String(item.receipt_table_id || '').trim())
          .filter(Boolean)
        if (receiptTableIds.length !== selectedBatches.length) {
          throw new Error('Niet alle geselecteerde kassabonnen hebben een geldige receipt-identiteit.')
        }
        await fetchJson('/api/receipts/delete', {
          method: 'POST',
          body: JSON.stringify({ receipt_table_ids: receiptTableIds }),
        })
      } else {
        await Promise.all(selectedBatches.map((item) => fetchJson(
          `/api/purchase-import-batches/${encodeURIComponent(item.batch_id)}/receipt-lifecycle`,
          {
            method: 'POST',
            body: JSON.stringify({ action }),
          },
        )))
      }

      setBatches((current) => current.filter((batch) => !selectedSet.has(batch.batch_id)))
      setRefreshVersion((current) => current + 1)
      if (openedBatchId && selectedSet.has(openedBatchId)) {
        setOpenedBatchId('')
      }
      setSelectedBatchIds([])
      setSelectedBatchesById({})
      setDeleteChoiceOpen(false)
    } catch (err) {
      showFeedback({
        variant: 'error',
        message: normalizeErrorMessage(err?.message) || 'De gekozen kassabonactie is mislukt.',
        key: 'receipts-delete-error',
      })
    } finally {
      setIsApplyingDeleteChoice(false)
    }
  }

  const mobileReceiptPagination = {
    page,
    pageCount: Math.max(1, Math.ceil(total / 10)),
    setPage,
  }
  const mobileVisibleItems = listItems
  const allVisibleSelected = mobileVisibleItems.length > 0 && mobileVisibleItems.every((item) => selectedBatchIds.includes(item.batch_id))

  if (isMobileViewport) {
    return (
      <div className="rz-mobile-inventory-screen rz-mobile-unpack-screen" data-testid="mobile-unpack-page">
        <MobileModuleHeader title="Uitpakken" testId="mobile-unpack-header" />
        <main className="rz-mobile-inventory-content rz-mobile-unpack-content">
          <div className="rz-mobile-inventory-toolbar">
            <div className="rz-mobile-inventory-search">
              <input className="rz-input" value={filters.winkel} onChange={(event) => handleFilterChange('winkel', event.target.value)} placeholder="Zoek winkel" aria-label="Zoek winkel" />
            </div>
            <div className="rz-mobile-unpack-filter-strip">
              <input className="rz-input" value={filters.datum} onChange={(event) => handleFilterChange('datum', event.target.value)} placeholder="Datum" aria-label="Filter op datum" />
              <input className="rz-input" value={filters.status} onChange={(event) => handleFilterChange('status', event.target.value)} placeholder="Status" aria-label="Filter op status" />
            </div>
          </div>

          <div className="rz-mobile-inventory-summary-row">
            <span className="rz-mobile-inventory-summary">{total} kassabon{total === 1 ? '' : 'nen'}</span>
            {listItems.length > 0 ? (
              <label className="rz-mobile-unpack-select-all">
                <input type="checkbox" checked={allVisibleSelected} onChange={toggleSelectAllVisible} />
                <span>Alles</span>
              </label>
            ) : null}
          </div>

          {isLoading ? <div className="rz-mobile-inventory-state" role="status">Nieuwe pagina laden… Vorige resultaten blijven zichtbaar.</div> : null}
          {!isLoading && hasLoadError ? <div className="rz-mobile-inventory-state rz-mobile-inventory-state--error">Kassabonnen konden niet worden geladen.</div> : null}
          {!isLoading && !hasLoadError && listItems.length === 0 ? <div className="rz-mobile-inventory-state">Er zijn nog geen kassabonnen.</div> : null}

          {!hasLoadError && listItems.length > 0 ? (
            <div className="rz-mobile-inventory-list rz-mobile-unpack-list" aria-busy={isLoading} style={{ pointerEvents: isLoading ? 'none' : undefined }}>
              {mobileVisibleItems.map((item) => {
                const selected = selectedBatchIds.includes(item.batch_id)
                return (
                  <div key={item.batch_id} className={`rz-mobile-inventory-card rz-mobile-unpack-card${selected ? ' rz-mobile-unpack-card--selected' : ''}`} data-testid={`mobile-receipt-batch-${item.batch_id}`} onClick={() => navigate(`/kassabonnen/batch/${encodeURIComponent(item.batch_id)}`)}>
                    <label className="rz-mobile-article-row-leading" onClick={(event) => event.stopPropagation()}>
                      <input type="checkbox" checked={selected} onChange={() => toggleSelectedBatch(item.batch_id)} aria-label={`Selecteer ${item.providerName} van ${item.dateLabel}`} />
                    </label>
                    <button type="button" className="rz-mobile-unpack-main" onClick={(event) => { event.stopPropagation(); navigate(`/kassabonnen/batch/${encodeURIComponent(item.batch_id)}`) }} data-testid={`mobile-receipt-open-${item.batch_id}`}>
                      <span className="rz-mobile-inventory-card-title">{item.providerName}</span>
                      <span className="rz-mobile-inventory-card-meta"><span>{item.dateLabel}</span><span>{item.totalLines} artikelen</span><span>{item.statusLabel}</span></span>
                    </button>

                  </div>
                )
              })}
            </div>
          ) : null}
          <div style={{ pointerEvents: isLoading ? 'none' : undefined }}><MobilePaginationControls {...mobileReceiptPagination} ariaLabel="Paginering Uitpakken" /></div>

          <div className="rz-mobile-unpack-actions" data-testid="mobile-unpack-bulk-actions">
            <Button
              type="button"
              variant="secondary"
              onClick={handleExport}
              disabled={selectedBatchIds.length === 0}
              data-testid="mobile-unpack-export"
            >
              Exporteren
            </Button>
            <Button type="button" onClick={handleBulkApprove} disabled={selectedBatchIds.length === 0 || isBulkApproving} data-testid="mobile-unpack-approve">{isBulkApproving ? "Goedkeuren…" : "Goedkeuren"}</Button>
            <Button
              type="button"
              variant="secondary"
              onClick={handleDeleteSelected}
              disabled={selectedBatchIds.length === 0}
              data-testid="mobile-unpack-delete"
            >
              Verwijderen
            </Button>
          </div>

        </main>

        {deleteChoiceOpen ? (
          <div className="rz-modal-backdrop" role="presentation">
            <div className="rz-modal-card rz-mobile-unpack-dialog" role="dialog" aria-modal="true" aria-labelledby="unpack-delete-choice-title" data-testid="unpack-delete-choice-dialog">
              <h2 id="unpack-delete-choice-title" className="rz-modal-title">Wat wil je met de kassabon doen?</h2>
              <p className="rz-modal-text">Reeds naar Voorraad verwerkte artikelen blijven ongewijzigd. Kies wat er met de kassabon en de resterende artikelen moet gebeuren.</p>
              <div className="rz-mobile-unpack-dialog-actions">
                <Button type="button" onClick={() => applyDeleteChoice('return_to_kassa')} disabled={isApplyingDeleteChoice}>Terugzetten naar Kassa</Button>
                <Button type="button" variant="secondary" onClick={() => applyDeleteChoice('archive')} disabled={isApplyingDeleteChoice}>Archiveren</Button>
                <Button type="button" variant="secondary" onClick={() => applyDeleteChoice('remove')} disabled={isApplyingDeleteChoice}>Volledig verwijderen</Button>
                <Button type="button" variant="secondary" onClick={() => setDeleteChoiceOpen(false)} disabled={isApplyingDeleteChoice}>Annuleren</Button>
              </div>
            </div>
          </div>
        ) : null}
      </div>
    )
  }

  return (
    <AppShell title="Uitpakken" showExit={false}>
      <div style={{ display: 'grid', gap: '16px' }} data-testid="receipts-page">
        <ScreenCard>
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
                <ResizableHeaderCell columnKey="winkel" widths={tableWidths} onStartResize={startTableResize} sortable isSorted={tableSort.key === 'winkel'} sortDirection={tableSort.direction} onSort={(key) => { setPage(1); setTableSort((current) => nextSortState(current, key, { winkel: 'asc', datum: 'desc', regels: 'desc', status: 'asc' })) }}>Winkel</ResizableHeaderCell>
                <ResizableHeaderCell columnKey="datum" widths={tableWidths} onStartResize={startTableResize} sortable isSorted={tableSort.key === 'datum'} sortDirection={tableSort.direction} onSort={(key) => { setPage(1); setTableSort((current) => nextSortState(current, key, { winkel: 'asc', datum: 'desc', regels: 'desc', status: 'asc' })) }}>Datum</ResizableHeaderCell>
                <ResizableHeaderCell columnKey="regels" widths={tableWidths} onStartResize={startTableResize} className="rz-num" sortable isSorted={tableSort.key === 'regels'} sortDirection={tableSort.direction} onSort={(key) => { setPage(1); setTableSort((current) => nextSortState(current, key, { winkel: 'asc', datum: 'desc', regels: 'desc', status: 'asc' })) }}>Artikelen</ResizableHeaderCell>
                <ResizableHeaderCell columnKey="status" widths={tableWidths} onStartResize={startTableResize} sortable isSorted={tableSort.key === 'status'} sortDirection={tableSort.direction} onSort={(key) => { setPage(1); setTableSort((current) => nextSortState(current, key, { winkel: 'asc', datum: 'desc', regels: 'desc', status: 'asc' })) }}>Status</ResizableHeaderCell>
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
            <tbody aria-busy={isLoading} style={{ pointerEvents: isLoading ? 'none' : undefined }}>
              {hasLoadError ? null : listItems.length === 0 ? (
                <tr><td colSpan={5}>{isLoading ? 'Bonnen laden…' : 'Er zijn nog geen kassabonnen.'}</td></tr>
              ) : mobileVisibleItems.map((item) => {
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
          <MobilePaginationControls {...mobileReceiptPagination} ariaLabel="Paginering Uitpakken" />
        <div className="rz-stock-table-actions">
          <Button type="button" variant="secondary" onClick={handleExport} disabled={isLoading || selectedBatchIds.length === 0}>Exporteren</Button>
          <Button type="button" onClick={handleBulkApprove} disabled={selectedBatchIds.length === 0 || isBulkApproving} data-testid="unpack-approve-selected-button">{isBulkApproving ? "Goedkeuren…" : "Goedkeuren"}</Button>
          <Button type="button" variant="secondary" onClick={handleDeleteSelected} disabled={selectedBatchIds.length === 0 || isBulkApproving}>Verwijderen</Button>
          {openedBatchId ? <Button type="button" variant="secondary" onClick={() => setOpenedBatchId('')} data-testid="receipt-back-to-overview">Terug naar overzicht</Button> : null}
        </div>
        </ScreenCard>

        {openedBatchId ? <StoreBatchDetailContent batchIdOverride={openedBatchId} embedded /> : null}
      </div>

      {deleteChoiceOpen ? (
        <div className="rz-modal-backdrop" role="presentation">
          <div
            className="rz-modal-card"
            role="dialog"
            aria-modal="true"
            aria-labelledby="unpack-delete-choice-title"
            data-testid="unpack-delete-choice-dialog"
            style={{ width: 'min(620px, calc(100vw - 32px))' }}
          >
            <h2 id="unpack-delete-choice-title" className="rz-modal-title">Wat wil je met de kassabon doen?</h2>
            <p className="rz-modal-text">
              Reeds naar Voorraad verwerkte artikelen blijven ongewijzigd. Kies wat er met de kassabon en de resterende artikelen moet gebeuren.
            </p>
            <div className="rz-stock-table-actions" style={{ justifyContent: 'flex-start', flexWrap: 'wrap' }}>
              <Button
                type="button"
                onClick={() => applyDeleteChoice('return_to_kassa')}
                disabled={isApplyingDeleteChoice}
                data-testid="unpack-delete-return-to-kassa"
              >
                Terugzetten naar Kassa
              </Button>
              <Button
                type="button"
                variant="secondary"
                onClick={() => applyDeleteChoice('archive')}
                disabled={isApplyingDeleteChoice}
                data-testid="unpack-delete-archive"
              >
                Archiveren
              </Button>
              <Button
                type="button"
                variant="secondary"
                onClick={() => applyDeleteChoice('remove')}
                disabled={isApplyingDeleteChoice}
                data-testid="unpack-delete-remove"
              >
                Volledig verwijderen
              </Button>
              <Button
                type="button"
                variant="secondary"
                onClick={() => setDeleteChoiceOpen(false)}
                disabled={isApplyingDeleteChoice}
                data-testid="unpack-delete-cancel"
              >
                Annuleren
              </Button>
            </div>
          </div>
        </div>
      ) : null}
    </AppShell>
  )
}
