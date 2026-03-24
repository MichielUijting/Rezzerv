import { useEffect, useMemo, useState } from 'react'
import { useLocation, useNavigate } from 'react-router-dom'
import AppShell from '../../app/AppShell'
import ScreenCard from '../../ui/ScreenCard'
import Button from '../../ui/Button'
import {
  StoreArticleSelector,
  articleFallbackOptions,
  fetchJson,
  formatQuantity,
  normalizeErrorMessage,
} from './storeImportShared'

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

function unpackStatusLabel(value) {
  if (value === 'new') return 'Nieuw'
  if (value === 'review_needed') return 'Controle nodig'
  if (value === 'ready_for_unpack') return 'Klaar voor uitpakken'
  if (value === 'unpack_in_progress') return 'Bezig met uitpakken'
  if (value === 'unpacked') return 'Uitgepakt'
  return value || '-'
}

function lineStatusLabel(value) {
  if (value === 'unlinked') return 'Nog niet gekoppeld'
  if (value === 'article_linked') return 'Artikel gekoppeld'
  if (value === 'location_linked') return 'Locatie gekoppeld'
  if (value === 'ready_to_book') return 'Klaar om op te boeken'
  if (value === 'booked') return 'Opgeboekt'
  return value || '-'
}

const RECEIPT_STATUS_OPTIONS = [
  { value: 'new', label: 'Nieuw' },
  { value: 'review_needed', label: 'Controle nodig' },
  { value: 'ready_for_unpack', label: 'Klaar voor uitpakken' },
  { value: 'unpack_in_progress', label: 'Bezig met uitpakken' },
  { value: 'unpacked', label: 'Uitgepakt' },
]

function ReceiptQueueTable({ items, isLoading, filters, onFilterChange, onOpenReceipt, openedReceiptId }) {
  const filteredItems = useMemo(() => {
    return (items || [])
      .filter((item) => String(item.store_name || '').toLowerCase().includes(filters.winkel.trim().toLowerCase()))
      .filter((item) => String(item.purchase_at || item.created_at || '').toLowerCase().includes(filters.datum.trim().toLowerCase()))
      .filter((item) => !filters.status || String(item.unpack_status || '') === filters.status)
  }, [items, filters])

  return (
    <ScreenCard>
      <div className="rz-table-wrapper">
        <table className="rz-table" data-testid="unpack-queue-table">
          <thead>
            <tr className="rz-table-header">
              <th style={{ width: '30%' }}>Winkel</th>
              <th style={{ width: '22%' }}>Datum</th>
              <th className="rz-num" style={{ width: '10%' }}>Regels</th>
              <th style={{ width: '23%' }}>Uitpakstatus</th>
              <th style={{ width: '15%' }}>Actie</th>
            </tr>
            <tr className="rz-table-filters">
              <th>
                <input
                  className="rz-input rz-inline-input"
                  value={filters.winkel}
                  onChange={(event) => onFilterChange('winkel', event.target.value)}
                  placeholder="Filter"
                  aria-label="Filter op winkel"
                />
              </th>
              <th>
                <input
                  className="rz-input rz-inline-input"
                  value={filters.datum}
                  onChange={(event) => onFilterChange('datum', event.target.value)}
                  placeholder="Filter"
                  aria-label="Filter op datum"
                />
              </th>
              <th />
              <th>
                <select
                  className="rz-input rz-inline-input"
                  value={filters.status}
                  onChange={(event) => onFilterChange('status', event.target.value)}
                  aria-label="Filter op uitpakstatus"
                >
                  <option value="">Alle statussen</option>
                  {RECEIPT_STATUS_OPTIONS.map((option) => (
                    <option key={option.value} value={option.value}>{option.label}</option>
                  ))}
                </select>
              </th>
              <th />
            </tr>
          </thead>
          <tbody>
            {isLoading ? (
              <tr><td colSpan={5}>Bonnen laden…</td></tr>
            ) : filteredItems.length === 0 ? (
              <tr><td colSpan={5}>Er zijn nog geen bonnen met verwerkingscontext.</td></tr>
            ) : filteredItems.map((item) => {
              const isOpened = String(openedReceiptId || '') === String(item.id || '')
              return (
                <tr key={item.id} className={isOpened ? 'rz-row-selected' : ''}>
                  <td>{item.store_name || 'Onbekende winkel'}</td>
                  <td>{formatDateTime(item.purchase_at || item.created_at)}</td>
                  <td className="rz-num">{item.line_count ?? 0}</td>
                  <td>{unpackStatusLabel(item.unpack_status)}</td>
                  <td>
                    <Button type="button" variant="secondary" onClick={() => onOpenReceipt(item.id)}>
                      Openen
                    </Button>
                  </td>
                </tr>
              )
            })}
          </tbody>
        </table>
      </div>
    </ScreenCard>
  )
}

function ReceiptDetailPane({
  receipt,
  receiptContextError,
  articleOptions,
  locationOptions,
  busyLineId,
  busyReceiptStatus,
  lineFeedback,
  onBackToKassa,
  onReceiptStatusChange,
  onLineChange,
}) {
  if (!receipt && !receiptContextError) return null

  return (
    <ScreenCard>
      <div style={{ display: 'grid', gap: '16px' }} data-testid="uitpakken-processing-context">
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', gap: '12px', flexWrap: 'wrap' }}>
          <div>
            <div style={{ fontWeight: 700, fontSize: '24px' }}>{receipt?.store_name || 'Bon in Uitpakken'}</div>
            <div style={{ color: '#667085', marginTop: '4px' }}>
              Kassa en Uitpakken gebruiken nu dezelfde persistente boncontext.
            </div>
          </div>
          <div className="rz-stock-table-actions" style={{ justifyContent: 'flex-start' }}>
            <Button type="button" variant="secondary" onClick={onBackToKassa}>Terug naar Kassa</Button>
          </div>
        </div>

        {receiptContextError ? (
          <div className="rz-inline-feedback rz-inline-feedback--error">{receiptContextError}</div>
        ) : null}

        {receipt ? (
          <>
            <div style={{ display: 'grid', gap: '12px', gridTemplateColumns: 'repeat(auto-fit, minmax(180px, 1fr))' }}>
              <div><strong>Winkel</strong><div>{receipt.store_name || 'Onbekende winkel'}</div></div>
              <div><strong>Aankoopmoment</strong><div>{formatDateTime(receipt.purchase_at)}</div></div>
              <div><strong>Totaal</strong><div>{formatMoney(receipt.total_amount, receipt.currency)}</div></div>
              <div><strong>Bonregels</strong><div>{receipt.line_count ?? receipt.lines?.length ?? 0}</div></div>
              <div><strong>Parse-status</strong><div>{parseReceiptStatusLabel(receipt.parse_status)}</div></div>
              <div><strong>Uitpakstatus</strong><div>{unpackStatusLabel(receipt.unpack_status)}</div></div>
            </div>

            <div style={{ display: 'grid', gap: '8px', gridTemplateColumns: 'repeat(auto-fit, minmax(220px, 1fr))', alignItems: 'end' }}>
              <div>
                <label htmlFor="receipt-status-select" style={{ display: 'block', fontWeight: 700, marginBottom: '6px' }}>Bonstatus</label>
                <select
                  id="receipt-status-select"
                  className="rz-input"
                  value={receipt.unpack_status || 'new'}
                  onChange={(event) => onReceiptStatusChange(event.target.value)}
                  disabled={busyReceiptStatus}
                >
                  {RECEIPT_STATUS_OPTIONS.map((option) => (
                    <option key={option.value} value={option.value}>{option.label}</option>
                  ))}
                </select>
              </div>
              <div>
                <strong>Koppelingen</strong>
                <div>{receipt.processing_summary?.linked_articles || 0} artikel(en) · {receipt.processing_summary?.linked_locations || 0} locatie(s)</div>
              </div>
              <div>
                <strong>Klaar voor opboeken</strong>
                <div>{receipt.processing_summary?.ready_to_book || 0} regel(s)</div>
              </div>
            </div>

            {lineFeedback ? <div className="rz-inline-feedback">{lineFeedback}</div> : null}

            <div className="rz-table-wrapper">
              <table className="rz-table" data-testid="receipt-processing-lines-table">
                <thead>
                  <tr className="rz-table-header">
                    <th style={{ width: '28%' }}>Artikel in bon</th>
                    <th style={{ width: '10%' }}>Aantal</th>
                    <th style={{ width: '11%' }}>Bedrag</th>
                    <th style={{ width: '24%' }}>Gekoppeld artikel</th>
                    <th style={{ width: '17%' }}>Locatie</th>
                    <th style={{ width: '10%' }}>Status</th>
                  </tr>
                </thead>
                <tbody>
                  {(receipt.lines || []).map((line) => {
                    const disabled = busyLineId === line.id
                    return (
                      <tr key={line.id}>
                        <td style={{ whiteSpace: 'normal', wordBreak: 'break-word' }}>{line.raw_label || '-'}</td>
                        <td>{formatQuantity(line.quantity, line.unit)}</td>
                        <td>{formatMoney(line.line_total, receipt.currency)}</td>
                        <td>
                          <StoreArticleSelector
                            lineId={line.id}
                            lineName={line.normalized_label || line.raw_label || ''}
                            selectedArticleId={String(line.matched_household_article_id || '')}
                            articleOptions={articleOptions}
                            disabled={disabled}
                            onChange={(nextArticleId) => onLineChange(line, { matched_article_id: nextArticleId || null, target_location_id: line.target_location_id || null })}
                            onClearArticle={() => onLineChange(line, { matched_article_id: null, target_location_id: line.target_location_id || null })}
                            canCreateArticle={false}
                          />
                        </td>
                        <td>
                          <select
                            className="rz-input"
                            value={String(line.target_location_id || '')}
                            disabled={disabled}
                            onChange={(event) => onLineChange(line, { matched_article_id: line.matched_household_article_id || null, target_location_id: event.target.value || null })}
                          >
                            <option value="">Kies locatie</option>
                            {locationOptions.map((location) => (
                              <option key={location.id} value={location.id}>{location.label}</option>
                            ))}
                          </select>
                        </td>
                        <td>{lineStatusLabel(line.unpack_status)}</td>
                      </tr>
                    )
                  })}
                </tbody>
              </table>
            </div>
          </>
        ) : null}
      </div>
    </ScreenCard>
  )
}

export default function ReceiptsPage() {
  const [queueItems, setQueueItems] = useState([])
  const [filters, setFilters] = useState({ winkel: '', datum: '', status: '' })
  const [isLoading, setIsLoading] = useState(true)
  const [error, setError] = useState('')
  const [articleOptions, setArticleOptions] = useState(articleFallbackOptions)
  const [locationOptions, setLocationOptions] = useState([])
  const [openedReceiptId, setOpenedReceiptId] = useState('')
  const [activeReceipt, setActiveReceipt] = useState(() => null)
  const [busyLineId, setBusyLineId] = useState('')
  const [busyReceiptStatus, setBusyReceiptStatus] = useState(false)
  const [lineFeedback, setLineFeedback] = useState('')
  const [receiptContextError, setReceiptContextError] = useState('')
  const location = useLocation()
  const navigate = useNavigate()

  async function loadQueueData() {
    setIsLoading(true)
    setError('')
    try {
      const token = localStorage.getItem('rezzerv_token')
      const householdData = await fetchJson('/api/household', {
        headers: token ? { Authorization: `Bearer ${token}` } : {},
      })
      const householdId = householdData?.id
      const [queueResult, backendArticles, backendLocations] = await Promise.all([
        fetchJson(`/api/unpack/queue?householdId=${encodeURIComponent(householdId)}&status=all`),
        fetchJson('/api/store-review-articles').catch(() => articleFallbackOptions),
        fetchJson(`/api/store-location-options?householdId=${encodeURIComponent(householdId)}&_ts=${Date.now()}`, { cache: 'no-store' }).catch(() => []),
      ])
      setQueueItems(Array.isArray(queueResult?.items) ? queueResult.items : [])
      setArticleOptions(Array.isArray(backendArticles) && backendArticles.length ? backendArticles : articleFallbackOptions)
      setLocationOptions(Array.isArray(backendLocations) ? backendLocations : [])
      return householdId
    } catch (err) {
      setError(normalizeErrorMessage(err?.message) || 'Uitpakken kon niet worden geladen.')
      return null
    } finally {
      setIsLoading(false)
    }
  }

  function syncReceiptInQueue(receipt) {
    if (!receipt?.id) return
    setQueueItems((current) => {
      const nextItems = Array.isArray(current) ? [...current] : []
      const nextItem = {
        ...nextItems.find((item) => String(item.id) === String(receipt.id)),
        ...receipt,
        line_count: receipt.line_count ?? receipt.lines?.length ?? 0,
      }
      const existingIndex = nextItems.findIndex((item) => String(item.id) === String(receipt.id))
      if (existingIndex >= 0) nextItems[existingIndex] = nextItem
      else nextItems.unshift(nextItem)
      return nextItems
    })
  }

  async function openReceipt(receiptId, fallbackReceipt = null) {
    if (!receiptId) return
    setReceiptContextError('')
    setOpenedReceiptId(String(receiptId))
    if (fallbackReceipt && String(fallbackReceipt.id || '') === String(receiptId) && Array.isArray(fallbackReceipt.lines)) {
      setActiveReceipt(fallbackReceipt)
      syncReceiptInQueue(fallbackReceipt)
      return
    }
    try {
      const nextReceipt = await fetchJson(`/api/receipts/${encodeURIComponent(receiptId)}/processing-context`)
      setActiveReceipt(nextReceipt)
      syncReceiptInQueue(nextReceipt)
    } catch (err) {
      setActiveReceipt(null)
      setReceiptContextError(normalizeErrorMessage(err?.message) || 'De bon uit Kassa kon niet worden geladen in Uitpakken.')
    }
  }

  useEffect(() => {
    let cancelled = false

    async function initializePage() {
      await loadQueueData()
      if (cancelled) return
      const params = new URLSearchParams(location.search)
      const requestedReceiptId = String(params.get('receipt_table_id') || '').trim()
      const routeReceiptContext = location.state?.receiptContext || null
      if (requestedReceiptId) {
        await openReceipt(requestedReceiptId, routeReceiptContext)
        return
      }
      if (routeReceiptContext?.id) {
        await openReceipt(routeReceiptContext.id, routeReceiptContext)
      }
    }

    initializePage()
    return () => { cancelled = true }
  }, [location.search, location.state])

  function handleFilterChange(key, value) {
    setFilters((current) => ({ ...current, [key]: value }))
  }

  async function handleReceiptStatusChange(nextStatus) {
    if (!activeReceipt?.id) return
    setBusyReceiptStatus(true)
    setError('')
    try {
      const result = await fetchJson(`/api/receipts/${encodeURIComponent(activeReceipt.id)}/status`, {
        method: 'PATCH',
        body: JSON.stringify({ unpack_status: nextStatus }),
      })
      const updatedReceipt = result?.receipt || activeReceipt
      setActiveReceipt(updatedReceipt)
      syncReceiptInQueue(updatedReceipt)
      setLineFeedback('Bonstatus opgeslagen.')
    } catch (err) {
      setError(normalizeErrorMessage(err?.message) || 'Bonstatus opslaan mislukt.')
    } finally {
      setBusyReceiptStatus(false)
    }
  }

  async function handleLineChange(line, patch) {
    if (!line?.id) return
    setBusyLineId(String(line.id))
    setError('')
    setLineFeedback('')
    try {
      const result = await fetchJson(`/api/receipt-lines/${encodeURIComponent(line.id)}/processing`, {
        method: 'PATCH',
        body: JSON.stringify(patch),
      })
      const updatedReceipt = result?.receipt || null
      if (updatedReceipt) {
        setActiveReceipt(updatedReceipt)
        syncReceiptInQueue(updatedReceipt)
      }
      setLineFeedback('Bonregel opgeslagen.')
    } catch (err) {
      setError(normalizeErrorMessage(err?.message) || 'Bonregel opslaan mislukt.')
    } finally {
      setBusyLineId('')
    }
  }

  return (
    <AppShell title="Uitpakken" showExit={false}>
      <div style={{ display: 'grid', gap: '16px' }} data-testid="receipts-page">
        {error ? <div className="rz-inline-feedback rz-inline-feedback--error">{error}</div> : null}

        <ReceiptQueueTable
          items={queueItems}
          isLoading={isLoading}
          filters={filters}
          onFilterChange={handleFilterChange}
          onOpenReceipt={openReceipt}
          openedReceiptId={openedReceiptId}
        />

        <ReceiptDetailPane
          receipt={activeReceipt}
          receiptContextError={receiptContextError}
          articleOptions={articleOptions}
          locationOptions={locationOptions}
          busyLineId={busyLineId}
          busyReceiptStatus={busyReceiptStatus}
          lineFeedback={lineFeedback}
          onBackToKassa={() => navigate('/kassa')}
          onReceiptStatusChange={handleReceiptStatusChange}
          onLineChange={handleLineChange}
        />
      </div>
    </AppShell>
  )
}
