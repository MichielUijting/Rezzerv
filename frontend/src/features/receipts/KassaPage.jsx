import { useEffect, useMemo, useRef, useState } from 'react'
import AppShell from '../../app/AppShell'
import ScreenCard from '../../ui/ScreenCard'
import Button from '../../ui/Button'
import Tabs from '../../ui/Tabs'
import { fetchJson, normalizeErrorMessage } from '../stores/storeImportShared'

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

function parseStatusLabel(value) {
  if (value === 'parsed') return 'Geparsed'
  if (value === 'partial') return 'Gedeeltelijk herkend'
  if (value === 'review_needed') return 'Controle nodig'
  if (value === 'failed') return 'Niet herkend'
  return value || '-'
}


const CHECKED_RECEIPTS_STORAGE_KEY = 'rezzerv_kassa_checked_receipts'

function loadCheckedReceiptIds() {
  try {
    const raw = window.localStorage.getItem(CHECKED_RECEIPTS_STORAGE_KEY)
    if (!raw) return []
    const parsed = JSON.parse(raw)
    return Array.isArray(parsed) ? parsed.map((value) => String(value)) : []
  } catch {
    return []
  }
}

function persistCheckedReceiptIds(ids) {
  try {
    window.localStorage.setItem(CHECKED_RECEIPTS_STORAGE_KEY, JSON.stringify([...new Set(ids.map((value) => String(value)))]))
  } catch {
    // ignore storage errors
  }
}

function deriveInboxStatus(receipt, checkedReceiptIds = []) {
  const receiptId = String(receipt?.receipt_table_id || receipt?.id || '')
  if (checkedReceiptIds.includes(receiptId)) return 'Gecontroleerd'
  if (receipt?.parse_status === 'review_needed' || receipt?.parse_status === 'failed') return 'Controle nodig'
  return 'Nieuw'
}

function inboxStatusStyle(value) {
  if (value === 'Gecontroleerd') {
    return {
      background: '#ECFDF3',
      color: '#027A48',
      border: '1px solid #ABEFC6',
    }
  }
  if (value === 'Controle nodig') {
    return {
      background: '#FFFAEB',
      color: '#B54708',
      border: '1px solid #FEDF89',
    }
  }
  return {
    background: '#EEF4FF',
    color: '#3538CD',
    border: '1px solid #C7D7FE',
  }
}

function ReceiptStatusBadge({ value }) {
  return (
    <span
      data-testid={`receipt-inbox-status-${String(value || '').toLowerCase().replace(/\s+/g, '-')}`}
      style={{
        display: 'inline-flex',
        alignItems: 'center',
        justifyContent: 'center',
        padding: '4px 10px',
        borderRadius: '999px',
        fontSize: '13px',
        fontWeight: 700,
        whiteSpace: 'nowrap',
        ...inboxStatusStyle(value),
      }}
    >
      {value || '-'}
    </span>
  )
}

async function uploadReceiptFile(householdId, file) {
  const token = localStorage.getItem('rezzerv_token') || ''
  const formData = new FormData()
  formData.append('household_id', String(householdId))
  formData.append('file', file)

  const response = await fetch('/api/receipts/import', {
    method: 'POST',
    headers: token ? { Authorization: `Bearer ${token}` } : {},
    body: formData,
  })
  const responseText = await response.text()
  let data = null
  if (responseText) {
    try {
      data = JSON.parse(responseText)
    } catch {
      data = responseText
    }
  }
  if (!response.ok) {
    throw new Error(normalizeErrorMessage(data?.detail || data || response.statusText))
  }
  return data
}

async function fetchReceiptSources(householdId) {
  return fetchJson(`/api/receipt-sources?householdId=${encodeURIComponent(householdId)}`)
}

async function createReceiptSource(payload) {
  return fetchJson('/api/receipt-sources', {
    method: 'POST',
    body: JSON.stringify(payload),
  })
}

async function fetchReceiptPreview(receiptTableId) {
  const token = localStorage.getItem('rezzerv_token') || ''
  const response = await fetch(`/api/receipts/${encodeURIComponent(receiptTableId)}/preview`, {
    method: 'GET',
    headers: token ? { Authorization: `Bearer ${token}` } : {},
  })
  if (!response.ok) {
    let detail = response.statusText
    try {
      const data = await response.json()
      detail = data?.detail || detail
    } catch {
      try {
        detail = await response.text()
      } catch {
        // ignore
      }
    }
    throw new Error(normalizeErrorMessage(detail) || 'Preview van de originele bon kon niet worden geladen.')
  }

  const blob = await response.blob()
  const contentType = response.headers.get('content-type') || blob.type || 'application/octet-stream'
  const blobUrl = window.URL.createObjectURL(blob)
  return {
    blobUrl,
    contentType,
    isPdf: contentType.includes('pdf'),
    isImage: contentType.startsWith('image/'),
  }
}

function DetailInfoRow({ label, value }) {
  return (
    <div style={{ display: 'grid', gap: '4px' }}>
      <div style={{ fontSize: '13px', fontWeight: 700, color: '#667085' }}>{label}</div>
      <div style={{ fontSize: '15px' }}>{value || '-'}</div>
    </div>
  )
}

function ReceiptPreviewCard({ receipt }) {
  const [previewState, setPreviewState] = useState({ status: 'idle', blobUrl: '', contentType: '', isPdf: false, isImage: false, error: '' })

  useEffect(() => {
    let cancelled = false
    let activeUrl = ''

    async function loadPreview() {
      if (!receipt?.id) {
        setPreviewState({ status: 'idle', blobUrl: '', contentType: '', isPdf: false, isImage: false, error: '' })
        return
      }
      setPreviewState({ status: 'loading', blobUrl: '', contentType: '', isPdf: false, isImage: false, error: '' })
      try {
        const result = await fetchReceiptPreview(receipt.id)
        if (cancelled) {
          window.URL.revokeObjectURL(result.blobUrl)
          return
        }
        activeUrl = result.blobUrl
        setPreviewState({ status: 'ready', error: '', ...result })
      } catch (err) {
        if (!cancelled) {
          setPreviewState({ status: 'error', blobUrl: '', contentType: '', isPdf: false, isImage: false, error: normalizeErrorMessage(err?.message) || 'Preview laden mislukt.' })
        }
      }
    }

    loadPreview()
    return () => {
      cancelled = true
      if (activeUrl) window.URL.revokeObjectURL(activeUrl)
    }
  }, [receipt?.id])

  const previewUrl = `/api/receipts/${encodeURIComponent(receipt?.id || '')}/preview`

  return (
    <ScreenCard>
      <div style={{ display: 'grid', gap: '16px' }} data-testid="receipt-preview-card">
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', gap: '12px', flexWrap: 'wrap' }}>
          <div>
            <div style={{ fontWeight: 700, fontSize: '22px' }}>Bon-preview</div>
            <div style={{ color: '#667085', marginTop: '4px' }}>
              Vergelijk de originele bon visueel met de herkende bongegevens.
            </div>
          </div>
          <div className="rz-stock-table-actions" style={{ justifyContent: 'flex-start' }}>
            <a href={previewUrl} target="_blank" rel="noreferrer" style={{ textDecoration: 'none' }}>
              <Button type="button" variant="secondary">Open origineel</Button>
            </a>
          </div>
        </div>

        <div
          style={{
            border: '1px solid #d0d5dd',
            borderRadius: '8px',
            minHeight: '420px',
            background: '#f8fafc',
            overflow: 'hidden',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            padding: previewState.isImage ? '16px' : '0',
          }}
        >
          {previewState.status === 'loading' ? (
            <div style={{ color: '#475467', fontWeight: 600 }}>Preview laden…</div>
          ) : null}

          {previewState.status === 'error' ? (
            <div className="rz-inline-feedback rz-inline-feedback--warning" data-testid="receipt-preview-fallback" style={{ maxWidth: '560px' }}>
              <div style={{ display: 'grid', gap: '12px' }}>
                <div>De preview van deze bon kon niet worden geladen.</div>
                <div style={{ color: '#667085' }}>{previewState.error || 'Gebruik Open origineel om de bon read-only te bekijken.'}</div>
                <div>
                  <a href={previewUrl} target="_blank" rel="noreferrer">Open origineel</a>
                </div>
              </div>
            </div>
          ) : null}

          {previewState.status === 'ready' && previewState.isPdf ? (
            <iframe
              src={previewState.blobUrl}
              title={`Preview van bon ${receipt?.id}`}
              style={{ width: '100%', minHeight: '560px', border: '0', background: '#fff' }}
              data-testid="receipt-preview-pdf"
            />
          ) : null}

          {previewState.status === 'ready' && previewState.isImage ? (
            <img
              src={previewState.blobUrl}
              alt={`Preview van bon ${receipt?.id}`}
              style={{ width: '100%', maxHeight: '720px', objectFit: 'contain', background: '#fff', borderRadius: '4px' }}
              data-testid="receipt-preview-image"
            />
          ) : null}

          {previewState.status === 'ready' && !previewState.isPdf && !previewState.isImage ? (
            <div className="rz-inline-feedback rz-inline-feedback--warning" data-testid="receipt-preview-unsupported" style={{ maxWidth: '560px' }}>
              Voor dit bestandstype is geen ingebedde preview beschikbaar. Gebruik Open origineel om het bestand read-only te bekijken.
            </div>
          ) : null}
        </div>
      </div>
    </ScreenCard>
  )
}

function ReceiptDetailInfoCard({ receipt, onBack }) {
  const [selectedLineIds, setSelectedLineIds] = useState([])

  useEffect(() => {
    setSelectedLineIds([])
  }, [receipt?.id])

  const lines = receipt?.lines || []
  const allSelected = lines.length > 0 && lines.every((line) => selectedLineIds.includes(line.id))

  function toggleLine(lineId) {
    setSelectedLineIds((current) => (
      current.includes(lineId)
        ? current.filter((id) => id !== lineId)
        : [...current, lineId]
    ))
  }

  function toggleAll() {
    setSelectedLineIds(allSelected ? [] : lines.map((line) => line.id))
  }

  function exportSelected() {
    const selectedSet = new Set(selectedLineIds)
    const exportLines = lines.filter((line) => selectedSet.has(line.id))
    const rows = exportLines.map((line) => [
      line.raw_label || '',
      line.normalized_label || '',
      line.quantity ?? '',
      line.unit || '',
      line.unit_price ?? '',
      line.line_total ?? '',
      line.discount_amount ?? '',
      line.barcode || '',
    ])
    const csv = [
      ['Ruwe regel', 'Genormaliseerd', 'Aantal', 'Eenheid', 'Stukprijs', 'Regelbedrag', 'Korting', 'Barcode'],
      ...rows,
    ]
      .map((row) => row.map((value) => `"${String(value ?? '').replace(/"/g, '""')}"`).join(';'))
      .join('\n')
    const blob = new Blob([csv], { type: 'text/csv;charset=utf-8;' })
    const url = window.URL.createObjectURL(blob)
    const link = document.createElement('a')
    link.href = url
    link.download = `rezzerv-kassa-${receipt?.id || 'bon'}.csv`
    document.body.appendChild(link)
    link.click()
    link.remove()
    window.URL.revokeObjectURL(url)
  }

  return (
    <ScreenCard>
      <div data-testid="receipt-detail-page" style={{ display: 'grid', gap: '16px' }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', gap: '12px', flexWrap: 'wrap' }}>
          <div>
            <div style={{ fontWeight: 700, fontSize: '24px' }} data-testid="receipt-detail-title">
              {receipt?.store_name || 'Kassabon'}
            </div>
            <div style={{ color: '#667085', marginTop: '4px' }}>
              {formatDateTime(receipt?.purchase_at)} · {parseStatusLabel(receipt?.parse_status)}
            </div>
          </div>
          <div className="rz-stock-table-actions" style={{ justifyContent: 'flex-start' }}>
            <Button type="button" variant="secondary" onClick={onBack} data-testid="receipt-back-to-overview">Terug naar overzicht</Button>
            <Button type="button" variant="secondary" onClick={exportSelected} disabled={selectedLineIds.length === 0} data-testid="receipt-export-button">Exporteren</Button>
          </div>
        </div>

        <Tabs tabs={['Bonregels', 'Bonkop', 'Bron']} defaultTab="Bonregels">
          {(activeTab) => {
            if (activeTab === 'Bonkop') {
              return (
                <div style={{ display: 'grid', gap: '12px', gridTemplateColumns: 'repeat(auto-fit, minmax(180px, 1fr))' }}>
                  <DetailInfoRow label="Winkel" value={receipt?.store_name} />
                  <DetailInfoRow label="Vestiging" value={receipt?.store_branch} />
                  <DetailInfoRow label="Aankoopmoment" value={formatDateTime(receipt?.purchase_at)} />
                  <DetailInfoRow label="Totaal" value={formatMoney(receipt?.total_amount, receipt?.currency)} />
                  <DetailInfoRow label="Valuta" value={receipt?.currency || 'EUR'} />
                  <DetailInfoRow label="Parse-status" value={parseStatusLabel(receipt?.parse_status)} />
                  <DetailInfoRow label="Confidence" value={receipt?.confidence_score ?? '-'} />
                  <DetailInfoRow label="Regels" value={String(lines.length)} />
                </div>
              )
            }
            if (activeTab === 'Bron') {
              return (
                <div style={{ display: 'grid', gap: '12px', gridTemplateColumns: 'repeat(auto-fit, minmax(220px, 1fr))' }}>
                  <DetailInfoRow label="Receipt table ID" value={receipt?.id} />
                  <DetailInfoRow label="Raw receipt ID" value={receipt?.raw_receipt_id} />
                  <DetailInfoRow label="Bron" value={receipt?.source_label || 'Handmatige upload'} />
                  <DetailInfoRow label="Oorspronkelijk bestand" value={receipt?.original_filename || 'Niet beschikbaar in deze release'} />
                  <DetailInfoRow label="Bestandstype" value={receipt?.mime_type || 'Niet beschikbaar in deze release'} />
                  <DetailInfoRow label="Imported at" value={formatDateTime(receipt?.imported_at || receipt?.created_at)} />
                  <DetailInfoRow label="Duplicate-status" value={receipt?.duplicate ? 'Dubbel bestand' : 'Geen duplicate gemeld'} />
                  <DetailInfoRow label="Aangemaakt" value={formatDateTime(receipt?.created_at)} />
                  <DetailInfoRow label="Bijgewerkt" value={formatDateTime(receipt?.updated_at)} />
                </div>
              )
            }
            return (
              <div style={{ display: 'grid', gap: '12px' }}>
                {lines.length === 0 ? (
                  <div className="rz-inline-feedback rz-inline-feedback--warning">
                    Deze bon heeft nog geen herkende artikelregels. Controleer later opnieuw of upload een beter leesbare bon.
                  </div>
                ) : null}
                <div className="rz-table-wrapper">
                  <table className="rz-table" data-testid="receipt-lines-table">
                    <thead>
                      <tr className="rz-table-header">
                        <th style={{ width: '44px' }}>
                          <input
                            type="checkbox"
                            checked={allSelected}
                            onChange={toggleAll}
                            aria-label="Selecteer alle bonregels"
                          />
                        </th>
                        <th>Artikel in bon</th>
                        <th>Genormaliseerd</th>
                        <th className="rz-num">Aantal</th>
                        <th>Eenheid</th>
                        <th className="rz-num">Stukprijs</th>
                        <th className="rz-num">Regelbedrag</th>
                        <th className="rz-num">Korting</th>
                      </tr>
                    </thead>
                    <tbody>
                      {lines.length === 0 ? (
                        <tr><td colSpan={8}>Geen artikelregels beschikbaar.</td></tr>
                      ) : lines.map((line) => {
                        const selected = selectedLineIds.includes(line.id)
                        return (
                          <tr key={line.id} data-testid={`receipt-line-row-${line.id}`} className={selected ? 'rz-row-selected' : ''}>
                            <td>
                              <input
                                type="checkbox"
                                data-testid={`receipt-line-select-${line.id}`}
                                checked={selected}
                                onChange={() => toggleLine(line.id)}
                                aria-label={`Selecteer regel ${line.raw_label || line.normalized_label || line.id}`}
                              />
                            </td>
                            <td data-testid={`receipt-line-status-${line.id}`}>{line.raw_label || '-'}</td>
                            <td>{line.normalized_label || '-'}</td>
                            <td className="rz-num">{line.quantity ?? '-'}</td>
                            <td>{line.unit || '-'}</td>
                            <td className="rz-num">{formatMoney(line.unit_price, receipt?.currency)}</td>
                            <td className="rz-num">{formatMoney(line.line_total, receipt?.currency)}</td>
                            <td className="rz-num">{formatMoney(line.discount_amount, receipt?.currency)}</td>
                          </tr>
                        )
                      })}
                    </tbody>
                  </table>
                </div>
              </div>
            )
          }}
        </Tabs>
      </div>
    </ScreenCard>
  )
}

function ReceiptDetailView({ receipt, onBack }) {
  return (
    <div
      style={{
        display: 'grid',
        gap: '16px',
        gridTemplateColumns: 'repeat(auto-fit, minmax(320px, 1fr))',
        alignItems: 'start',
      }}
    >
      <ReceiptPreviewCard receipt={receipt} />
      <ReceiptDetailInfoCard receipt={receipt} onBack={onBack} />
    </div>
  )
}

function ReceiptSourceHubModal({
  isOpen,
  onClose,
  onChooseFile,
}) {
  if (!isOpen) return null

  return (
    <div className="rz-modal-backdrop" role="presentation" style={{ inset: '56px 0 0 0', alignItems: 'start', justifyItems: 'center', overflowY: 'auto', padding: '16px 20px 20px' }}>
      <div
        className="rz-modal-card"
        role="dialog"
        aria-modal="true"
        aria-labelledby="kassa-bronhub-title"
        style={{ width: 'min(1100px, 100%)', maxHeight: 'calc(100vh - 88px)', overflow: 'auto', padding: '24px', gap: '20px', marginTop: '0' }}
      >
        <div style={{ display: 'flex', justifyContent: 'space-between', gap: '12px', alignItems: 'flex-start', flexWrap: 'wrap' }}>
          <div>
            <h2 id="kassa-bronhub-title" className="rz-modal-title" style={{ fontSize: '22px' }}>Bon toevoegen</h2>
            <p className="rz-modal-text">Kies één van de drie officiële routes om een kassabon in Rezzerv te krijgen.</p>
          </div>
          <Button type="button" variant="secondary" onClick={onClose}>Sluiten</Button>
        </div>

        <div style={{ display: 'grid', gap: '16px', gridTemplateColumns: 'repeat(auto-fit, minmax(240px, 1fr))' }}>
          <ScreenCard fullWidth>
            <div style={{ display: 'grid', gap: '12px' }}>
              <div style={{ fontSize: '20px', fontWeight: 700 }}>Delen naar Rezzerv</div>
              <div style={{ color: '#667085' }}>Gebruik de gewone deeloptie vanuit een app of website om een kassabon naar Rezzerv te sturen. Deze route wordt in een volgende release verder uitgewerkt.</div>
              <div className="rz-inline-feedback rz-inline-feedback--warning">Deelroute nog niet actief in deze versie.</div>
            </div>
          </ScreenCard>

          <ScreenCard fullWidth>
            <div style={{ display: 'grid', gap: '12px' }}>
              <div style={{ fontSize: '20px', fontWeight: 700 }}>Foto maken</div>
              <div style={{ color: '#667085' }}>Voeg een foto, screenshot of pdf van een kassabon toe via de bestaande importflow.</div>
              <Button type="button" variant="primary" onClick={onChooseFile}>Foto of bestand kiezen</Button>
            </div>
          </ScreenCard>

          <ScreenCard fullWidth>
            <div style={{ display: 'grid', gap: '12px' }}>
              <div style={{ fontSize: '20px', fontWeight: 700 }}>E-mail doorsturen</div>
              <div style={{ color: '#667085' }}>Stuur een e-mail met bonbijlage door naar jouw Rezzerv-route. Deze route wordt in een volgende release technisch aangesloten.</div>
              <div className="rz-inline-feedback rz-inline-feedback--warning">E-mailroute nog niet actief in deze versie.</div>
            </div>
          </ScreenCard>
        </div>
      </div>
    </div>
  )
}

export default function KassaPage() {
  const [householdId, setHouseholdId] = useState('1')
  const [receipts, setReceipts] = useState([])
  const [filters, setFilters] = useState({ winkel: '', datum: '', status: '' })
  const [isLoading, setIsLoading] = useState(true)
  const [isUploading, setIsUploading] = useState(false)
  const [isSourceHubOpen, setIsSourceHubOpen] = useState(false)
  const [error, setError] = useState('')
  const [status, setStatus] = useState('')
  const [selectedReceiptIds, setSelectedReceiptIds] = useState([])
  const [openedReceiptId, setOpenedReceiptId] = useState('')
  const [openedReceipt, setOpenedReceipt] = useState(null)
  const [checkedReceiptIds, setCheckedReceiptIds] = useState(() => loadCheckedReceiptIds())
  const fileInputRef = useRef(null)

  function markReceiptChecked(receiptTableId) {
    const normalizedId = String(receiptTableId || '')
    if (!normalizedId) return
    setCheckedReceiptIds((current) => {
      if (current.includes(normalizedId)) return current
      const next = [...current, normalizedId]
      persistCheckedReceiptIds(next)
      return next
    })
  }

  async function loadReceipts(nextHouseholdId = householdId) {
    setIsLoading(true)
    setError('')
    try {
      const list = await fetchJson(`/api/receipts?householdId=${encodeURIComponent(nextHouseholdId)}`)
      const items = Array.isArray(list?.items) ? list.items : []
      setReceipts(items)
      if (openedReceiptId) {
        const detail = await fetchJson(`/api/receipts/${encodeURIComponent(openedReceiptId)}`)
        const sourceItem = items.find((item) => String(item.receipt_table_id) === String(openedReceiptId)) || null
        setOpenedReceipt(sourceItem ? { ...sourceItem, ...detail } : detail)
      }
    } catch (err) {
      setError(normalizeErrorMessage(err?.message) || 'Kassabonnen konden niet worden geladen.')
    } finally {
      setIsLoading(false)
    }
  }

  useEffect(() => {
    let cancelled = false
    async function bootstrap() {
      try {
        const token = localStorage.getItem('rezzerv_token')
        const household = await fetchJson('/api/household', {
          headers: token ? { Authorization: `Bearer ${token}` } : {},
        })
        if (cancelled) return
        const resolvedHouseholdId = String(household?.id || '1')
        setHouseholdId(resolvedHouseholdId)
        await loadReceipts(resolvedHouseholdId)
      } catch (err) {
        if (!cancelled) {
          setError(normalizeErrorMessage(err?.message) || 'Huishouden kon niet worden geladen.')
          setIsLoading(false)
        }
      }
    }
    bootstrap()
    return () => { cancelled = true }
  }, [])

  useEffect(() => {
    const visibleIds = new Set(receipts.map((receipt) => receipt.receipt_table_id))
    setSelectedReceiptIds((current) => current.filter((id) => visibleIds.has(id)))
    if (openedReceiptId && !visibleIds.has(openedReceiptId)) {
      setOpenedReceiptId('')
      setOpenedReceipt(null)
    }
  }, [receipts, openedReceiptId])

  const inboxItems = useMemo(() => {
    return receipts
      .map((item) => ({ ...item, inbox_status: deriveInboxStatus(item, checkedReceiptIds) }))
      .sort((a, b) => String(b.created_at || '').localeCompare(String(a.created_at || '')))
  }, [receipts, checkedReceiptIds])

  const inboxSummary = useMemo(() => ({
    Nieuw: inboxItems.filter((item) => item.inbox_status === 'Nieuw').length,
    'Controle nodig': inboxItems.filter((item) => item.inbox_status === 'Controle nodig').length,
    Gecontroleerd: inboxItems.filter((item) => item.inbox_status === 'Gecontroleerd').length,
  }), [inboxItems])

  const listItems = useMemo(() => {
    return inboxItems
      .filter((item) => String(item.store_name || '').toLowerCase().includes(filters.winkel.trim().toLowerCase()))
      .filter((item) => formatDateTime(item.purchase_at).toLowerCase().includes(filters.datum.trim().toLowerCase()))
      .filter((item) => (filters.status ? item.inbox_status === filters.status : true))
  }, [inboxItems, filters])

  const allVisibleSelected = listItems.length > 0 && listItems.every((item) => selectedReceiptIds.includes(item.receipt_table_id))

  async function openReceiptDetail(receiptTableId) {
    setError('')
    try {
      const detail = await fetchJson(`/api/receipts/${encodeURIComponent(receiptTableId)}`)
      const sourceItem = receipts.find((item) => String(item.receipt_table_id) === String(receiptTableId)) || null
      setOpenedReceiptId(receiptTableId)
      setOpenedReceipt(sourceItem ? { ...sourceItem, ...detail } : detail)
      markReceiptChecked(receiptTableId)
    } catch (err) {
      setError(normalizeErrorMessage(err?.message) || 'De kassabon kon niet worden geladen.')
    }
  }

  function toggleSelectedReceipt(receiptTableId) {
    setSelectedReceiptIds((current) => (
      current.includes(receiptTableId)
        ? current.filter((id) => id !== receiptTableId)
        : [...current, receiptTableId]
    ))
  }

  function toggleSelectAllVisible() {
    const visibleIds = listItems.map((item) => item.receipt_table_id)
    setSelectedReceiptIds(allVisibleSelected ? [] : visibleIds)
  }

  function handleFilterChange(key, value) {
    setFilters((current) => ({ ...current, [key]: value }))
  }

  function applyStatusFilter(value) {
    setFilters((current) => ({ ...current, status: current.status === value ? '' : value }))
  }

  function openSourceHub() {
    setIsSourceHubOpen(true)
  }

  function handleChooseFileFromHub() {
    setTimeout(() => fileInputRef.current?.click(), 0)
  }

  async function handleUploadChange(event) {
    const file = event.target.files?.[0]
    event.target.value = ''
    if (!file) return
    setIsUploading(true)
    setError('')
    setStatus('')
    try {
      const result = await uploadReceiptFile(householdId, file)
      await loadReceipts(householdId)
      if (result?.receipt_table_id) {
        await openReceiptDetail(result.receipt_table_id)
      }
      setIsSourceHubOpen(false)
      if (result?.duplicate) {
        setStatus('Deze bon was al aanwezig en is niet opnieuw toegevoegd.')
      } else if (result?.receipt_table_id) {
        setStatus(`Bon toegevoegd met status: ${parseStatusLabel(result.parse_status)}`)
      } else {
        setStatus('Bestand opgeslagen, maar nog niet als bruikbare kassabon herkend.')
      }
    } catch (err) {
      setError(normalizeErrorMessage(err?.message) || 'Upload van de kassabon is mislukt.')
    } finally {
      setIsUploading(false)
    }
  }

  return (
    <AppShell title="Kassa" showExit={false}>
      <div style={{ display: 'grid', gap: '16px' }} data-testid="kassa-page">
        <ScreenCard>
          <div style={{ display: 'grid', gap: '16px' }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', gap: '12px', flexWrap: 'wrap' }}>
              <div>
                <div style={{ fontWeight: 700, fontSize: '24px' }}>Bon-inbox</div>
                <div style={{ color: '#667085', marginTop: '4px' }}>
                  Zie direct welke bonnen nieuw zijn, controle nodig hebben of al gecontroleerd zijn.
                </div>
              </div>
              <div className="rz-stock-table-actions" style={{ justifyContent: 'flex-start' }}>
                <input
                  ref={fileInputRef}
                  type="file"
                  accept=".pdf,.png,.jpg,.jpeg"
                  style={{ display: 'none' }}
                  onChange={handleUploadChange}
                />
                <Button type="button" variant="secondary" onClick={() => loadReceipts(householdId)} disabled={isLoading || isUploading}>Vernieuwen</Button>
                <Button type="button" variant="primary" onClick={openSourceHub} disabled={isUploading}>{isUploading ? 'Uploaden…' : 'Bon toevoegen'}</Button>
              </div>
            </div>

            {error ? <div className="rz-inline-feedback rz-inline-feedback--error">{error}</div> : null}
            {status ? <div className="rz-inline-feedback rz-inline-feedback--success">{status}</div> : null}

            <div style={{ display: 'grid', gap: '12px', gridTemplateColumns: 'repeat(auto-fit, minmax(180px, 1fr))' }}>
              {[
                { key: 'Nieuw', helper: 'Nog niet gecontroleerd' },
                { key: 'Controle nodig', helper: 'Vraagt extra aandacht' },
                { key: 'Gecontroleerd', helper: 'Al bekeken in Kassa' },
              ].map((entry) => {
                const isActive = filters.status === entry.key
                return (
                  <button
                    key={entry.key}
                    type="button"
                    onClick={() => applyStatusFilter(entry.key)}
                    data-testid={`kassa-status-card-${String(entry.key).toLowerCase().replace(/\s+/g, '-')}`}
                    style={{
                      textAlign: 'left',
                      borderRadius: '16px',
                      border: isActive ? '2px solid #3538CD' : '1px solid #D0D5DD',
                      background: '#FFFFFF',
                      padding: '16px',
                      display: 'grid',
                      gap: '8px',
                      cursor: 'pointer',
                      boxShadow: isActive ? '0 0 0 3px rgba(53,56,205,0.08)' : 'none',
                    }}
                  >
                    <div style={{ display: 'flex', justifyContent: 'space-between', gap: '8px', alignItems: 'center' }}>
                      <div style={{ fontSize: '15px', fontWeight: 700 }}>{entry.key}</div>
                      <ReceiptStatusBadge value={entry.key} />
                    </div>
                    <div style={{ fontSize: '28px', fontWeight: 800, lineHeight: 1 }}>{inboxSummary[entry.key] || 0}</div>
                    <div style={{ fontSize: '13px', color: '#667085' }}>{entry.helper}</div>
                  </button>
                )
              })}
            </div>

            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', gap: '12px', flexWrap: 'wrap' }}>
              <div style={{ display: 'flex', gap: '8px', flexWrap: 'wrap' }}>
                <Button type="button" variant={filters.status === '' ? 'primary' : 'secondary'} onClick={() => setFilters((current) => ({ ...current, status: '' }))}>Alle bonnen</Button>
                <Button type="button" variant={filters.status === 'Nieuw' ? 'primary' : 'secondary'} onClick={() => applyStatusFilter('Nieuw')}>Nieuw</Button>
                <Button type="button" variant={filters.status === 'Controle nodig' ? 'primary' : 'secondary'} onClick={() => applyStatusFilter('Controle nodig')}>Controle nodig</Button>
                <Button type="button" variant={filters.status === 'Gecontroleerd' ? 'primary' : 'secondary'} onClick={() => applyStatusFilter('Gecontroleerd')}>Gecontroleerd</Button>
              </div>
              <div style={{ color: '#667085', fontSize: '14px' }}>
                {listItems.length} bon{listItems.length === 1 ? '' : 'nen'} zichtbaar
              </div>
            </div>

            <div className="rz-table-wrapper">
              <table className="rz-table" data-testid="kassa-table">
                <thead>
                  <tr className="rz-table-header">
                    <th style={{ width: '44px' }}>
                      <input type="checkbox" checked={allVisibleSelected} onChange={toggleSelectAllVisible} aria-label="Selecteer alle zichtbare bonnen" />
                    </th>
                    <th>Winkel</th>
                    <th>Datum</th>
                    <th className="rz-num">Totaal</th>
                    <th className="rz-num">Artikelen</th>
                    <th>Status</th>
                  </tr>
                  <tr className="rz-table-filters">
                    <th />
                    <th>
                      <input className="rz-input rz-inline-input" value={filters.winkel} onChange={(event) => handleFilterChange('winkel', event.target.value)} placeholder="Filter" aria-label="Filter op winkel" />
                    </th>
                    <th>
                      <input className="rz-input rz-inline-input" value={filters.datum} onChange={(event) => handleFilterChange('datum', event.target.value)} placeholder="Filter" aria-label="Filter op datum" />
                    </th>
                    <th />
                    <th />
                    <th>
                      <span style={{ fontSize: '13px', color: '#667085' }}>{filters.status || 'Alle statussen'}</span>
                    </th>
                  </tr>
                </thead>
                <tbody>
                  {isLoading ? (
                    <tr><td colSpan={6}>Bonnen laden…</td></tr>
                  ) : listItems.length === 0 ? (
                    <tr><td colSpan={6}>Er zijn nog geen bonnen in de inbox beschikbaar.</td></tr>
                  ) : listItems.map((item) => {
                    const selected = selectedReceiptIds.includes(item.receipt_table_id)
                    return (
                      <tr
                        key={item.receipt_table_id}
                        className={selected ? 'rz-row-selected' : ''}
                        onClick={() => toggleSelectedReceipt(item.receipt_table_id)}
                        onDoubleClick={() => openReceiptDetail(item.receipt_table_id)}
                        data-testid={`kassa-row-${item.receipt_table_id}`}
                        style={{
                          cursor: 'pointer',
                          boxShadow: `inset 4px 0 0 ${item.inbox_status === 'Gecontroleerd' ? '#12B76A' : item.inbox_status === 'Controle nodig' ? '#F79009' : '#6172F3'}`,
                        }}
                      >
                        <td onClick={(event) => event.stopPropagation()}>
                          <button
                            type="button"
                            data-testid={`kassa-open-${item.receipt_table_id}`}
                            onClick={(event) => { event.stopPropagation(); openReceiptDetail(item.receipt_table_id) }}
                            style={{ display: 'none' }}
                            aria-hidden="true"
                            tabIndex={-1}
                          />
                          <input
                            type="checkbox"
                            checked={selected}
                            onChange={() => toggleSelectedReceipt(item.receipt_table_id)}
                            aria-label={`Selecteer bon ${item.store_name || 'onbekend'} van ${formatDateTime(item.purchase_at)}`}
                          />
                        </td>
                        <td className="rz-receipts-cell">{item.store_name || 'Onbekende winkel'}</td>
                        <td className="rz-receipts-cell">{formatDateTime(item.purchase_at)}</td>
                        <td className="rz-num rz-receipts-cell">{formatMoney(item.total_amount, item.currency)}</td>
                        <td className="rz-num rz-receipts-cell">{item.line_count ?? 0}</td>
                        <td className="rz-receipts-cell"><ReceiptStatusBadge value={item.inbox_status} /></td>
                      </tr>
                    )
                  })}
                </tbody>
              </table>
            </div>
          </div>
        </ScreenCard>

        {openedReceipt ? <ReceiptDetailView receipt={openedReceipt} onBack={() => { setOpenedReceiptId(''); setOpenedReceipt(null) }} /> : null}
      </div>

      <ReceiptSourceHubModal
        isOpen={isSourceHubOpen}
        onClose={() => setIsSourceHubOpen(false)}
        onChooseFile={handleChooseFileFromHub}
      />
    </AppShell>
  )
}
