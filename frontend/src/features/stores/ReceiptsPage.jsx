import { useEffect, useMemo, useState } from 'react'
import { useLocation } from 'react-router-dom'
import AppShell from '../../app/AppShell'
import ScreenCard from '../../ui/ScreenCard'
import Button from '../../ui/Button'
import { fetchJson, normalizeErrorMessage } from './storeImportShared'

const DEFAULT_FILTERS = { winkel: '', datum: '', regels: '', status: '' }
const VISIBLE_STATUSES = new Set(['Gecontroleerd', 'Controle nodig'])

function formatDateTime(value) {
  if (!value) return '-'
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return String(value)
  return new Intl.DateTimeFormat('nl-NL', {
    day: '2-digit',
    month: '2-digit',
    year: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
  }).format(date)
}

function formatMoney(value, currency = 'EUR') {
  const amount = Number(value)
  if (!Number.isFinite(amount)) return '-'
  try {
    return new Intl.NumberFormat('nl-NL', {
      style: 'currency',
      currency,
      minimumFractionDigits: 2,
      maximumFractionDigits: 2,
    }).format(amount)
  } catch {
    return `${amount.toFixed(2)} ${currency || 'EUR'}`
  }
}

function formatQuantity(value) {
  if (value === null || value === undefined || value === '') return '-'
  const number = Number(value)
  if (!Number.isFinite(number)) return String(value)
  const hasDecimals = Math.abs(number - Math.round(number)) > 0.0009
  return new Intl.NumberFormat('nl-NL', {
    minimumFractionDigits: hasDecimals ? 3 : 0,
    maximumFractionDigits: hasDecimals ? 3 : 2,
  }).format(number)
}

function amountsMatch(receipt) {
  const totalAmount = Number(receipt?.total_amount)
  const netLineTotalSum = Number(
    receipt?.net_line_total_sum
      ?? ((Number(receipt?.line_total_sum) || 0) + (Number(receipt?.discount_total_effective ?? receipt?.discount_total) || 0))
  )
  const lineCount = Number(receipt?.line_count ?? receipt?.lines?.length ?? 0)
  if (!Number.isFinite(totalAmount) || !Number.isFinite(netLineTotalSum)) return false
  if (!Number.isFinite(lineCount) || lineCount <= 0) return false
  return Math.abs(totalAmount - netLineTotalSum) < 0.01
}

function deriveInboxStatus(receipt) {
  if (receipt?.parse_status === 'review_needed' || receipt?.parse_status === 'failed') return 'Controle nodig'
  const lineCount = Number(receipt?.line_count ?? receipt?.lines?.length ?? 0)
  if (receipt?.parse_status === 'parsed' && amountsMatch(receipt) && lineCount >= 1) return 'Gecontroleerd'
  if (receipt?.line_total_sum !== null && receipt?.line_total_sum !== undefined && receipt?.total_amount !== null && receipt?.total_amount !== undefined) return 'Controle nodig'
  return 'Nieuw'
}

function inboxStatusAccentColor(value) {
  if (value === 'Gecontroleerd') return '#12B76A'
  if (value === 'Controle nodig') return '#F79009'
  return '#B54708'
}

function ReceiptStatusBadge({ value }) {
  const style = value === 'Gecontroleerd'
    ? { background: '#ECFDF3', color: '#027A48', border: '1px solid #ABEFC6' }
    : value === 'Controle nodig'
      ? { background: '#FFFAEB', color: '#166534', border: '1px solid #FEDF89' }
      : { background: '#FFF7ED', color: '#166534', border: '1px solid #F9DBAF' }

  return (
    <span
      style={{
        display: 'inline-flex',
        alignItems: 'center',
        justifyContent: 'center',
        padding: '4px 10px',
        borderRadius: '999px',
        fontSize: '13px',
        fontWeight: 700,
        whiteSpace: 'nowrap',
        ...style,
      }}
    >
      {value || '-'}
    </span>
  )
}

function DetailField({ label, value }) {
  return (
    <div style={{ display: 'grid', gap: '4px' }}>
      <div style={{ fontSize: '13px', fontWeight: 700, color: '#667085' }}>{label}</div>
      <div style={{ fontSize: '15px' }}>{value || '-'}</div>
    </div>
  )
}

function ReceiptDetailCard({ receipt, onClose }) {
  if (!receipt) return null
  return (
    <ScreenCard>
      <div style={{ display: 'grid', gap: '16px' }} data-testid="unpack-receipt-detail">
        <div style={{ display: 'flex', justifyContent: 'space-between', gap: '12px', alignItems: 'flex-start', flexWrap: 'wrap' }}>
          <div style={{ display: 'grid', gap: '6px' }}>
            <div style={{ fontSize: '24px', fontWeight: 700 }}>{receipt.store_name || 'Kassabon'}</div>
            <div style={{ color: '#667085' }}>Overgenomen uit Kassa voor verdere verwerking in Uitpakken.</div>
          </div>
          <div style={{ display: 'flex', gap: '12px', alignItems: 'center', flexWrap: 'wrap' }}>
            <ReceiptStatusBadge value={receipt.inbox_status} />
            <Button type="button" variant="secondary" onClick={onClose}>Terug naar overzicht</Button>
          </div>
        </div>

        <div style={{ display: 'grid', gap: '16px', gridTemplateColumns: 'repeat(auto-fit, minmax(180px, 1fr))' }}>
          <DetailField label="Winkel" value={receipt.store_name || '-'} />
          <DetailField label="Datum" value={formatDateTime(receipt.purchase_at)} />
          <DetailField label="Totaal" value={formatMoney(receipt.total_amount, receipt.currency)} />
          <DetailField label="Artikelen" value={String(receipt.line_count ?? receipt.lines?.length ?? 0)} />
        </div>

        <div className="rz-table-wrapper" style={{ overflowX: 'auto' }}>
          <table className="rz-table" data-testid="unpack-receipt-lines-table">
            <thead>
              <tr className="rz-table-header">
                <th style={{ width: '48%' }}>Artikel</th>
                <th className="rz-num" style={{ width: '13%' }}>Aantal</th>
                <th style={{ width: '12%' }}>Eenheid</th>
                <th className="rz-num" style={{ width: '13%' }}>Prijs</th>
                <th className="rz-num" style={{ width: '14%' }}>Totaal</th>
              </tr>
            </thead>
            <tbody>
              {(receipt.lines || []).length === 0 ? (
                <tr><td colSpan={5}>Er zijn nog geen bonregels beschikbaar.</td></tr>
              ) : (receipt.lines || []).map((line) => (
                <tr key={line.id || `${line.line_index}-${line.raw_label}`}>
                  <td>{line.raw_label || line.normalized_label || '-'}</td>
                  <td className="rz-num">{formatQuantity(line.quantity)}</td>
                  <td>{line.unit || '-'}</td>
                  <td className="rz-num">{formatMoney(line.unit_price, receipt.currency)}</td>
                  <td className="rz-num">{formatMoney(line.line_total, receipt.currency)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </ScreenCard>
  )
}

export default function ReceiptsPage() {
  const [receipts, setReceipts] = useState([])
  const [filters, setFilters] = useState(DEFAULT_FILTERS)
  const [isLoading, setIsLoading] = useState(true)
  const [error, setError] = useState('')
  const [selectedReceiptIds, setSelectedReceiptIds] = useState([])
  const [openedReceiptId, setOpenedReceiptId] = useState('')
  const [openedReceipt, setOpenedReceipt] = useState(null)
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

        const response = await fetchJson(`/api/receipts?householdId=${encodeURIComponent(householdData.id)}`)
        if (cancelled) return
        setReceipts(Array.isArray(response?.items) ? response.items : [])
      } catch (err) {
        if (!cancelled) setError(normalizeErrorMessage(err?.message) || 'Kassabonnen konden niet worden geladen.')
      } finally {
        if (!cancelled) setIsLoading(false)
      }
    }

    loadData()
    return () => { cancelled = true }
  }, [location.search])

  const sourceItems = useMemo(() => (
    (receipts || [])
      .map((item) => ({ ...item, inbox_status: deriveInboxStatus(item) }))
      .filter((item) => VISIBLE_STATUSES.has(item.inbox_status))
  ), [receipts])

  const listItems = useMemo(() => (
    sourceItems
      .filter((item) => String(item.store_name || '').toLowerCase().includes(filters.winkel.trim().toLowerCase()))
      .filter((item) => formatDateTime(item.purchase_at).toLowerCase().includes(filters.datum.trim().toLowerCase()))
      .filter((item) => String(item.line_count ?? 0).includes(filters.regels.trim()))
      .filter((item) => String(item.inbox_status || '').toLowerCase().includes(filters.status.trim().toLowerCase()))
      .sort((a, b) => String(b.created_at || '').localeCompare(String(a.created_at || '')))
  ), [filters, sourceItems])

  useEffect(() => {
    if (!listItems.length) {
      setSelectedReceiptIds([])
      setOpenedReceiptId('')
      setOpenedReceipt(null)
      return
    }
    const visibleIds = new Set(listItems.map((item) => String(item.receipt_table_id)))
    setSelectedReceiptIds((current) => current.filter((id) => visibleIds.has(String(id))))
    if (openedReceiptId && !visibleIds.has(String(openedReceiptId))) {
      setOpenedReceiptId('')
      setOpenedReceipt(null)
    }
  }, [listItems, openedReceiptId])

  function handleFilterChange(key, value) {
    setFilters((current) => ({ ...current, [key]: value }))
  }

  function toggleSelectedReceipt(receiptTableId) {
    setSelectedReceiptIds((current) => (
      current.includes(receiptTableId)
        ? current.filter((id) => id !== receiptTableId)
        : [...current, receiptTableId]
    ))
  }

  function toggleSelectAllVisible() {
    if (!listItems.length) return
    const visibleIds = listItems.map((item) => item.receipt_table_id)
    const allVisibleSelected = visibleIds.every((id) => selectedReceiptIds.includes(id))
    setSelectedReceiptIds(allVisibleSelected ? [] : visibleIds)
  }

  async function openReceiptDetail(receiptTableId) {
    setError('')
    try {
      const detail = await fetchJson(`/api/receipts/${encodeURIComponent(receiptTableId)}`)
      const sourceItem = sourceItems.find((item) => String(item.receipt_table_id) === String(receiptTableId)) || null
      setOpenedReceiptId(String(receiptTableId))
      setOpenedReceipt(sourceItem ? { ...sourceItem, ...detail } : detail)
    } catch (err) {
      setError(normalizeErrorMessage(err?.message) || 'De kassabon kon niet worden geladen.')
    }
  }

  function handleExport() {
    const selectedIds = selectedReceiptIds.length ? new Set(selectedReceiptIds) : null
    const rows = listItems.filter((item) => !selectedIds || selectedIds.has(item.receipt_table_id))
    const header = ['Winkel', 'Datum', 'Artikelen', 'Status']
    const csvRows = rows.map((item) => [
      item.store_name || '-',
      formatDateTime(item.purchase_at),
      String(item.line_count ?? 0),
      item.inbox_status,
    ])
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
    if (selectedReceiptIds.length === 0) return
    const selectedSet = new Set(selectedReceiptIds.map((value) => String(value)))
    setReceipts((current) => current.filter((receipt) => !selectedSet.has(String(receipt.receipt_table_id))))
    if (openedReceiptId && selectedSet.has(String(openedReceiptId))) {
      setOpenedReceiptId('')
      setOpenedReceipt(null)
    }
    setSelectedReceiptIds([])
  }

  const allVisibleSelected = listItems.length > 0 && listItems.every((item) => selectedReceiptIds.includes(item.receipt_table_id))

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
                  <tr><td colSpan={5}>Er zijn nog geen kassabonnen om uit te pakken.</td></tr>
                ) : listItems.map((item) => {
                  const selected = selectedReceiptIds.includes(item.receipt_table_id)
                  const accentColor = inboxStatusAccentColor(item.inbox_status)
                  return (
                    <tr
                      key={item.receipt_table_id}
                      data-testid={`receipt-batch-row-${item.receipt_table_id}`}
                      className={selected ? 'rz-row-selected' : ''}
                      onClick={() => toggleSelectedReceipt(item.receipt_table_id)}
                      onDoubleClick={() => {
                        if (!selected) toggleSelectedReceipt(item.receipt_table_id)
                        openReceiptDetail(item.receipt_table_id)
                      }}
                      style={{ cursor: 'pointer' }}
                    >
                      <td onClick={(event) => event.stopPropagation()} style={{ borderLeft: `8px solid ${accentColor}` }}>
                        <button
                          type="button"
                          data-testid={`receipt-batch-open-${item.receipt_table_id}`}
                          onClick={(event) => { event.stopPropagation(); openReceiptDetail(item.receipt_table_id) }}
                          style={{ display: 'none' }}
                          aria-hidden="true"
                          tabIndex={-1}
                        />
                        <input
                          type="checkbox"
                          checked={selected}
                          onChange={() => toggleSelectedReceipt(item.receipt_table_id)}
                          aria-label={`Selecteer ${item.store_name || 'kassabon'} van ${formatDateTime(item.purchase_at)}`}
                        />
                      </td>
                      <td className="rz-receipts-cell">{item.store_name || '-'}</td>
                      <td className="rz-receipts-cell">{formatDateTime(item.purchase_at)}</td>
                      <td className="rz-num rz-receipts-cell">{item.line_count ?? 0}</td>
                      <td className="rz-receipts-cell"><ReceiptStatusBadge value={item.inbox_status} /></td>
                    </tr>
                  )
                })}
              </tbody>
            </table>
          </div>
          <div className="rz-stock-table-actions">
            <Button type="button" variant="secondary" onClick={handleExport} disabled={isLoading || listItems.length === 0}>Exporteren</Button>
            <Button type="button" variant="secondary" onClick={handleDeleteSelected} disabled={selectedReceiptIds.length === 0}>Verwijderen</Button>
            {openedReceiptId ? <Button type="button" variant="secondary" onClick={() => { setOpenedReceiptId(''); setOpenedReceipt(null) }} data-testid="receipt-back-to-overview">Terug naar overzicht</Button> : null}
          </div>
        </ScreenCard>

        {openedReceiptId ? <ReceiptDetailCard receipt={openedReceipt} onClose={() => { setOpenedReceiptId(''); setOpenedReceipt(null) }} /> : null}
      </div>
    </AppShell>
  )
}
