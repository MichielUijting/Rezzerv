import { useEffect, useRef, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import MobileModuleHeader from '../../ui/MobileModuleHeader.jsx'
import Button from '../../ui/Button'
import { fetchJson } from '../stores/storeImportShared'
import './mobileKassa.css'

function money(value, currency = 'EUR') {
  const number = Number(value)
  if (!Number.isFinite(number)) return '—'
  return new Intl.NumberFormat('nl-NL', { style: 'currency', currency: currency || 'EUR' }).format(number)
}
function dateLabel(value) {
  if (!value) return 'Datum onbekend'
  const date = new Date(value)
  return Number.isNaN(date.getTime()) ? String(value) : new Intl.DateTimeFormat('nl-NL').format(date)
}
function receiptId(receipt) { return String(receipt?.receipt_table_id || receipt?.id || '') }
function receiptLines(receipt) { return Array.isArray(receipt?.lines) ? receipt.lines : Array.isArray(receipt?.receipt_lines) ? receipt.receipt_lines : [] }

export default function MobileKassa() {
  const navigate = useNavigate()
  const videoRef = useRef(null)
  const streamRef = useRef(null)
  const fileRef = useRef(null)
  const [mode, setMode] = useState('camera')
  const [householdId, setHouseholdId] = useState('')
  const [receipts, setReceipts] = useState([])
  const [receipt, setReceipt] = useState(null)
  const [cameraError, setCameraError] = useState('')
  const [busy, setBusy] = useState(false)
  const [message, setMessage] = useState('')

  async function loadReceipts(id = householdId) {
    if (!id) return []
    const result = await fetchJson(`/api/receipts?householdId=${encodeURIComponent(id)}`)
    const items = Array.isArray(result?.items) ? result.items : []
    setReceipts(items)
    return items
  }

  async function startCamera() {
    setMode('camera')
    setReceipt(null)
    setMessage('')
    setCameraError('')
    streamRef.current?.getTracks?.().forEach((track) => track.stop())
    streamRef.current = null
    try {
      if (!navigator.mediaDevices?.getUserMedia) throw new Error('Camera is niet rechtstreeks beschikbaar.')
      const stream = await navigator.mediaDevices.getUserMedia({ video: { facingMode: { ideal: 'environment' } }, audio: false })
      streamRef.current = stream
      if (videoRef.current) {
        videoRef.current.srcObject = stream
        await videoRef.current.play().catch(() => {})
      }
    } catch {
      setCameraError('De camera kon niet automatisch worden geopend. Gebruik Camera openen.')
    }
  }

  useEffect(() => {
    let cancelled = false
    fetchJson('/api/household').then(async (household) => {
      if (cancelled) return
      const id = String(household?.active_household_id ?? household?.id ?? '')
      setHouseholdId(id)
      await loadReceipts(id)
      if (!cancelled) await startCamera()
    }).catch(() => setCameraError('Kassa kon niet worden gestart.'))
    return () => {
      cancelled = true
      streamRef.current?.getTracks?.().forEach((track) => track.stop())
    }
  }, [])

  async function uploadImage(file) {
    if (!file || !householdId) return
    setBusy(true)
    setMessage('Bon wordt herkend en gestructureerd…')
    try {
      const form = new FormData()
      form.append('household_id', householdId)
      form.append('file', file)
      form.append('source_context', 'camera_capture')
      form.append('source_label', 'Foto gemaakt in Inhuis')
      const response = await fetch('/api/receipts/share-import', { method: 'POST', credentials: 'include', body: form })
      const result = await response.json().catch(() => ({}))
      if (!response.ok) throw new Error(result?.detail || 'Bon kon niet worden verwerkt.')
      const id = String(result?.receipt_table_id || result?.existing_receipt?.receipt_table_id || '')
      if (!id) throw new Error('Inhuis herkent geen bruikbare kassabon.')
      const detail = await fetchJson(`/api/receipts/${encodeURIComponent(id)}`)
      streamRef.current?.getTracks?.().forEach((track) => track.stop())
      streamRef.current = null
      setReceipt(detail)
      setMode('review')
      setMessage('')
    } catch (error) {
      setMessage(String(error?.message || 'Bon kon niet worden verwerkt.'))
    } finally {
      setBusy(false)
    }
  }

  async function takePhoto() {
    const video = videoRef.current
    if (!video?.videoWidth || !video?.videoHeight) return fileRef.current?.click()
    const canvas = document.createElement('canvas')
    canvas.width = video.videoWidth
    canvas.height = video.videoHeight
    canvas.getContext('2d')?.drawImage(video, 0, 0)
    const blob = await new Promise((resolve) => canvas.toBlob(resolve, 'image/jpeg', 0.86))
    if (blob) await uploadImage(new File([blob], `kassabon-${Date.now()}.jpg`, { type: 'image/jpeg' }))
  }

  async function cancelReview() {
    const id = receiptId(receipt)
    if (id) {
      try {
        await fetchJson('/api/receipts/delete', { method: 'POST', body: JSON.stringify({ receipt_table_ids: [id] }) })
      } catch {
        setMessage('De scan kon niet worden geannuleerd.')
        return
      }
    }
    await loadReceipts()
    await startCamera()
  }

  async function saveReview() {
    await loadReceipts()
    setReceipt(null)
    setMode('list')
  }

  async function openReceipt(id) {
    setBusy(true)
    try {
      setReceipt(await fetchJson(`/api/receipts/${encodeURIComponent(id)}`))
      setMode('detail')
    } finally { setBusy(false) }
  }

  async function updateHeader(field, value) {
    const id = receiptId(receipt)
    const updated = await fetchJson(`/api/receipts/${encodeURIComponent(id)}`, {
      method: 'PATCH', body: JSON.stringify({ [field]: value }),
    })
    setReceipt(updated)
  }

  async function updateLine(line, field, value) {
    const id = receiptId(receipt)
    const lineId = String(line?.id || line?.receipt_line_id || '')
    if (!id || !lineId) return
    const payload = { [field]: field === 'quantity' || field === 'line_total' ? Number(value) : value, is_validated: true }
    const updated = await fetchJson(`/api/receipts/${encodeURIComponent(id)}/lines/${encodeURIComponent(lineId)}`, {
      method: 'PATCH', body: JSON.stringify(payload),
    })
    setReceipt(updated)
  }

  async function approve() {
    const id = receiptId(receipt)
    setBusy(true)
    try {
      await fetchJson(`/api/receipts/${encodeURIComponent(id)}/approve`, { method: 'POST' })
      await loadReceipts()
      setReceipt(null)
      setMode('list')
      setMessage('Bon bevestigd en doorgezet volgens de ingestelde Inhuis-route.')
    } catch (error) {
      setMessage(String(error?.message || 'Bon kon niet worden bevestigd.'))
    } finally { setBusy(false) }
  }

  const lines = receiptLines(receipt)

  return (
    <div className="rz-mobile-kassa" data-testid="mobile-kassa-page">
      <MobileModuleHeader title={mode === 'list' ? 'Bonnen' : mode === 'detail' ? 'Kassabon' : mode === 'review' ? 'Bon controleren' : 'Kassa'} testId="mobile-kassa-header" />
      {message ? <div className="rz-mobile-kassa-message" role="status">{message}</div> : null}

      {mode === 'camera' ? (
        <main className="rz-mobile-kassa-camera" data-testid="mobile-kassa-camera">
          <video ref={videoRef} playsInline muted className="rz-mobile-kassa-video" />
          <div className="rz-mobile-kassa-guide">Plaats de kassabon binnen het vlak</div>
          {cameraError ? <div className="rz-mobile-kassa-camera-error">{cameraError}</div> : null}
          <input ref={fileRef} type="file" accept="image/*" capture="environment" hidden onChange={(event) => { const file = event.target.files?.[0]; event.target.value=''; if (file) uploadImage(file) }} />
          <div className="rz-mobile-kassa-camera-actions">
            <Button type="button" variant="secondary" onClick={() => { streamRef.current?.getTracks?.().forEach((track) => track.stop()); setMode('list'); loadReceipts() }}>Bonnen</Button>
            <button type="button" className="rz-mobile-kassa-shutter" aria-label="Maak foto van kassabon" onClick={takePhoto} disabled={busy} />
            <Button type="button" variant="secondary" onClick={() => fileRef.current?.click()}>Camera openen</Button>
          </div>
        </main>
      ) : null}

      {mode === 'review' && receipt ? (
        <main className="rz-mobile-kassa-content" data-testid="mobile-kassa-review">
          <ReceiptSummary receipt={receipt} lines={lines} editable={false} />
          <div className="rz-mobile-kassa-primary-actions">
            <Button type="button" variant="secondary" onClick={cancelReview} disabled={busy}>Annuleren</Button>
            <Button type="button" onClick={saveReview} disabled={busy}>Opslaan</Button>
          </div>
        </main>
      ) : null}

      {mode === 'list' ? (
        <main className="rz-mobile-kassa-content" data-testid="mobile-kassa-list">
          <div className="rz-mobile-kassa-list-actions"><Button type="button" onClick={startCamera}>Nieuwe scan</Button></div>
          {receipts.length === 0 ? <div className="rz-mobile-kassa-empty">Nog geen opgeslagen kassabonnen.</div> : receipts.map((item) => (
            <button key={receiptId(item)} type="button" className="rz-mobile-kassa-receipt-card" onClick={() => openReceipt(receiptId(item))}>
              <strong>{item.store_name || 'Onbekende winkel'}</strong>
              <span>{dateLabel(item.purchase_at)} · {money(item.total_amount, item.currency)} · {item.line_count ?? 0} regels</span>
              <span>{item.po_norm_status_label || item.inbox_status || 'Controle nodig'} ›</span>
            </button>
          ))}
        </main>
      ) : null}

      {mode === 'detail' && receipt ? (
        <main className="rz-mobile-kassa-content" data-testid="mobile-kassa-detail">
          <ReceiptSummary receipt={receipt} lines={lines} editable onHeaderChange={updateHeader} onLineChange={updateLine} />
          <div className="rz-mobile-kassa-primary-actions">
            <Button type="button" variant="secondary" onClick={() => { setReceipt(null); setMode('list') }}>Terug naar bonnen</Button>
            <Button type="button" onClick={approve} disabled={busy}>{busy ? 'Bevestigen…' : 'Bon bevestigen'}</Button>
          </div>
        </main>
      ) : null}
    </div>
  )
}

function ReceiptSummary({ receipt, lines, editable, onHeaderChange, onLineChange }) {
  return (
    <section className="rz-mobile-kassa-summary">
      <div className="rz-mobile-kassa-receipt-head">
        {editable ? <input aria-label="Winkel" defaultValue={receipt.store_name || ''} onBlur={(e) => onHeaderChange?.('store_name', e.target.value)} /> : <strong>{receipt.store_name || 'Onbekende winkel'}</strong>}
        <span>{dateLabel(receipt.purchase_at)} · {money(receipt.total_amount, receipt.currency)}</span>
      </div>
      <div className="rz-mobile-kassa-lines">
        {lines.length === 0 ? <div>Geen artikelregels herkend.</div> : lines.map((line, index) => {
          const id = String(line?.id || line?.receipt_line_id || index)
          const name = line.normalized_label || line.display_label || line.article_name || line.raw_label || 'Onbekend artikel'
          return (
            <div className="rz-mobile-kassa-line" key={id}>
              {editable ? <input aria-label={`Artikel ${index + 1}`} defaultValue={name} onBlur={(e) => onLineChange?.(line, 'article_name', e.target.value)} /> : <span>{name}</span>}
              {editable ? <input aria-label={`Aantal ${index + 1}`} type="number" step="any" defaultValue={line.quantity ?? 1} onBlur={(e) => onLineChange?.(line, 'quantity', e.target.value)} /> : <span>{line.quantity ?? 1}×</span>}
              <span>{money(line.line_total ?? line.total_amount, receipt.currency)}</span>
            </div>
          )
        })}
      </div>
    </section>
  )
}
