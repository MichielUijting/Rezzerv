import { useEffect, useRef, useState } from 'react'
import MobileModuleHeader from '../../ui/MobileModuleHeader.jsx'
import Button from '../../ui/Button'
import Tabs from '../../ui/Tabs'
import { useAppFeedback } from '../../ui/AppFeedbackProvider.jsx'
import { fetchJson, normalizeErrorMessage } from '../stores/storeImportShared'
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

function mobileScanErrorMessage(detail) {
  const raw = typeof detail === 'string' ? detail : JSON.stringify(detail || '')
  if (/ReceiptBodyV1|receipt\.lines|at least one visible receipt line/i.test(raw)) {
    return 'Geen kassabon herkend. Zorg dat de volledige bon duidelijk binnen het kader staat en probeer opnieuw.'
  }
  return normalizeErrorMessage(raw) || 'Bon kon niet worden verwerkt. Probeer opnieuw.'
}

export default function MobileKassa() {
  const { showFeedback } = useAppFeedback()
  const videoRef = useRef(null)
  const streamRef = useRef(null)
  const fileRef = useRef(null)
  const uploadRef = useRef(null)
  const [mode, setMode] = useState('camera')
  const [householdId, setHouseholdId] = useState('')
  const [receipts, setReceipts] = useState([])
  const [receiptsLoading, setReceiptsLoading] = useState(false)
  const [receiptsLoadError, setReceiptsLoadError] = useState('')
  const receiptRequestRef = useRef(0)
  const [receipt, setReceipt] = useState(null)
  const [selectedLineIds, setSelectedLineIds] = useState([])
  const [selectedReceiptIds, setSelectedReceiptIds] = useState([])
  const [addingLine, setAddingLine] = useState(false)
  const [newLine, setNewLine] = useState({ article_name: '', quantity: 1, unit: '', unit_price: '', line_total: '' })
  const [receiptFilter, setReceiptFilter] = useState('')
  const [cameraError, setCameraError] = useState('')
  const [busy, setBusy] = useState(false)
  const [message, setMessage] = useState('')

  useEffect(() => {
    if (mode !== 'detail') return undefined
    const handleBack = (event) => {
      event.preventDefault()
      showReceiptList()
    }
    window.addEventListener('inhuis:mobile-kassa-back', handleBack)
    return () => window.removeEventListener('inhuis:mobile-kassa-back', handleBack)
  }, [mode, householdId])

  useEffect(() => {
    if (!message || message === 'Bon wordt herkend en gestructureerd…') return
    showFeedback({
      variant: /bevestigd|doorgezet/i.test(message) ? 'success' : 'warning',
      title: /bevestigd|doorgezet/i.test(message) ? 'Gelukt' : 'Melding',
      message,
      testId: 'mobile-kassa-feedback',
    })
  }, [message, showFeedback])

  async function loadReceipts(id = householdId) {
    const requestId = ++receiptRequestRef.current
    setReceiptsLoading(true)
    setReceiptsLoadError('')
    try {
      if (!id) throw new Error('Het actieve huishouden is nog niet geladen.')
      const result = await fetchJson(`/api/receipts?householdId=${encodeURIComponent(id)}`)
      if (!Array.isArray(result?.items)) throw new Error('De kassabonlijst heeft een onverwacht antwoord ontvangen.')
      if (requestId === receiptRequestRef.current) setReceipts(result.items)
      return result.items
    } catch (error) {
      if (requestId === receiptRequestRef.current) {
        setReceiptsLoadError(normalizeErrorMessage(error?.message) || 'Kassabonnen konden niet worden geladen.')
      }
      throw error
    } finally {
      if (requestId === receiptRequestRef.current) setReceiptsLoading(false)
    }
  }

  function showReceiptList() {
    streamRef.current?.getTracks?.().forEach((track) => track.stop())
    streamRef.current = null
    setReceipt(null)
    setSelectedLineIds([])
    setMode('list')
    loadReceipts().catch(() => {})
  }

  async function openCamera() {
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
    } catch (error) {
      const denied = error?.name === 'NotAllowedError' || error?.name === 'PermissionDeniedError'
      setCameraError(denied ? 'Cameratoegang is geweigerd.' : 'De camera kon niet worden geopend.')
      showFeedback({ variant: 'warning', title: 'Cameratoegang', message: denied ? 'Geef Inhuis cameratoegang in de browserinstellingen en probeer opnieuw.' : 'Controleer of je camera beschikbaar is en probeer opnieuw.', primaryActionLabel: 'Opnieuw proberen', onPrimaryAction: () => openCamera(), secondaryActionLabel: 'Sluiten', testId: 'mobile-kassa-camera-permission' })
      return false
    }
  }

  async function startCamera() {
    setMode('camera')
    setReceipt(null)
    setCameraError('')
    let granted = false
    try {
      const permission = await navigator.permissions?.query?.({ name: 'camera' })
      granted = permission?.state === 'granted'
    } catch { /* Niet iedere browser ondersteunt de camera-permissionquery. */ }
    if (granted) return openCamera()
    showFeedback({
      variant: 'info',
      title: 'Cameratoegang',
      message: 'Inhuis heeft toegang tot je camera nodig om een kassabon te fotograferen.',
      detail: 'Kies Toestaan en bevestig daarna de eventuele toestemmingsvraag van je browser.',
      primaryActionLabel: 'Toestaan',
      secondaryActionLabel: 'Annuleren',
      onPrimaryAction: () => openCamera(),
      testId: 'mobile-kassa-camera-permission',
    })
  }

  useEffect(() => {
    let cancelled = false
    const searchParams = new URLSearchParams(window.location.search)
    const requestedView = searchParams.get('view') || ''
    const requestedReceiptId = searchParams.get('receipt') || ''
    fetchJson('/api/household').then(async (household) => {
      if (cancelled) return
      const id = String(household?.active_household_id ?? household?.id ?? '')
      setHouseholdId(id)
      await loadReceipts(id)
      if (cancelled) return
      if (requestedReceiptId) {
        await openReceipt(requestedReceiptId)
        return
      }
      if (requestedView === 'bonnen') {
        setMode('list')
        return
      }
      await startCamera()
    }).catch(() => { if (!cancelled) setCameraError('Kassa kon niet worden gestart.') })
    return () => {
      cancelled = true
      streamRef.current?.getTracks?.().forEach((track) => track.stop())
    }
  }, [])

  async function uploadImage(file, source = 'camera') {
    if (!file || !householdId) {
      showFeedback({ variant: 'warning', message: 'Er is nog geen actief huishouden geladen.' })
      return
    }
    setBusy(true)
    setMessage('Bon wordt herkend en gestructureerd…')
    try {
      const form = new FormData()
      form.append('household_id', householdId)
      form.append('file', file)
      form.append('source_context', source === 'upload' ? 'manual_upload' : 'camera_capture')
      form.append('source_label', source === 'upload' ? 'Bestand gekozen in Inhuis' : 'Foto gemaakt in Inhuis')
      const response = await fetch('/api/receipts/share-import', { method: 'POST', credentials: 'include', body: form })
      const result = await response.json().catch(() => ({}))
      if (!response.ok) throw new Error(mobileScanErrorMessage(result?.detail))
      const id = String(result?.receipt_table_id || result?.existing_receipt?.receipt_table_id || '')
      if (!id) throw new Error('Inhuis herkent geen bruikbare kassabon.')
      const detail = await fetchJson(`/api/receipts/${encodeURIComponent(id)}`)
      streamRef.current?.getTracks?.().forEach((track) => track.stop())
      streamRef.current = null
      setReceipt(detail)
      setMode('review')
      setMessage('')
    } catch (error) {
      setMessage(mobileScanErrorMessage(error?.message))
    } finally {
      setBusy(false)
    }
  }

  async function takePhoto() {
    const video = videoRef.current
    if (!streamRef.current?.active) {
      await startCamera()
      return
    }
    if (!video?.videoWidth || !video?.videoHeight) {
      showFeedback({ variant: 'warning', title: 'Camera nog niet gereed', message: 'Wacht tot de camera beeld geeft en probeer opnieuw.', testId: 'mobile-kassa-camera-not-ready' })
      return
    }
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
    showReceiptList()
  }

  async function openReceipt(id) {
    setBusy(true)
    try {
      setReceipt(await fetchJson(`/api/receipts/${encodeURIComponent(id)}`))
      setSelectedLineIds([])
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

  function feedbackError(error, fallback) {
    showFeedback({ variant: 'error', title: 'Kassa', message: normalizeErrorMessage(error?.message) || fallback })
  }

  async function addReceiptLine() {
    if (!String(newLine.article_name || '').trim()) {
      showFeedback({ variant: 'warning', message: 'Vul eerst een artikelnaam in.' })
      return
    }
    setBusy(true)
    try {
      const updated = await fetchJson(`/api/receipts/${encodeURIComponent(receiptId(receipt))}/lines`, {
        method: 'POST',
        body: JSON.stringify({
          article_name: newLine.article_name,
          quantity: Number(newLine.quantity || 1),
          unit: newLine.unit,
          unit_price: newLine.unit_price === '' ? null : Number(newLine.unit_price),
          line_total: newLine.line_total === '' ? null : Number(newLine.line_total),
          is_validated: true,
        }),
      })
      setReceipt(updated)
      setNewLine({ article_name: '', quantity: 1, unit: '', unit_price: '', line_total: '' })
      setAddingLine(true)
      showFeedback({ variant: 'success', message: 'Artikel toegevoegd. Je kunt nog een artikel toevoegen.' })
    } catch (error) { feedbackError(error, 'Bonregel kon niet worden toegevoegd.') }
    finally { setBusy(false) }
  }

  async function changeSelectedLines(deleteLines = false) {
    if (!selectedLineIds.length) return
    setBusy(true)
    try {
      let updated = receipt
      for (const id of selectedLineIds) {
        const line = receiptLines(updated).find((item) => String(item.id || item.receipt_line_id) === id)
        updated = await fetchJson(`/api/receipts/${encodeURIComponent(receiptId(updated))}/lines/${encodeURIComponent(id)}`, {
          method: 'PATCH',
          body: JSON.stringify({
            article_name: line?.normalized_label || line?.display_label || line?.article_name || line?.raw_label || '',
            quantity: Number(line?.quantity ?? 1),
            unit: line?.unit || '',
            unit_price: line?.unit_price ?? null,
            line_total: line?.line_total ?? null,
            is_validated: true,
            is_deleted: deleteLines,
          }),
        })
      }
      setReceipt(updated)
      setSelectedLineIds([])
      showFeedback({ variant: 'success', message: deleteLines ? 'Bonregels verwijderd.' : 'Bonregels gecontroleerd.' })
    } catch (error) { feedbackError(error, 'Bonregels konden niet worden bijgewerkt.') }
    finally { setBusy(false) }
  }

  function confirmDeleteLines() {
    showFeedback({
      variant: 'warning', title: 'Bonregels verwijderen?',
      message: `Wil je ${selectedLineIds.length} geselecteerde bonregels verwijderen?`,
      dismissMode: 'action-only', primaryActionLabel: 'Verwijderen', secondaryActionLabel: 'Annuleren',
      onPrimaryAction: () => changeSelectedLines(true),
    })
  }

  function confirmDeleteReceipts(ids) {
    if (!ids.length) return
    showFeedback({
      variant: 'warning', title: 'Kassabonnen verwijderen?',
      message: `Wil je ${ids.length} geselecteerde kassabonnen definitief verwijderen?`,
      dismissMode: 'action-only', primaryActionLabel: 'Verwijderen', secondaryActionLabel: 'Annuleren',
      onPrimaryAction: async () => {
        setBusy(true)
        try {
          await fetchJson('/api/receipts/delete', { method: 'POST', body: JSON.stringify({ receipt_table_ids: ids }) })
          setSelectedReceiptIds([])
          showReceiptList()
          showFeedback({ variant: 'success', message: 'Kassabonnen verwijderd.' })
        } catch (error) { feedbackError(error, 'Kassabonnen konden niet worden verwijderd.') }
        finally { setBusy(false) }
      },
    })
  }

  function exportLines() {
    const rows = receiptLines(receipt).filter((line) => selectedLineIds.includes(String(line.id || line.receipt_line_id)))
    const csv = [['Artikel', 'Aantal', 'Eenheid', 'Stukprijs', 'Bedrag'], ...rows.map((line) => [
      line.normalized_label || line.display_label || line.article_name || line.raw_label || '',
      line.quantity ?? '', line.unit ?? '', line.unit_price ?? '', line.line_total ?? '',
    ])].map((row) => row.map((cell) => `"${String(cell).replace(/"/g, '""')}"`).join(';')).join('\\n')
    const url = URL.createObjectURL(new Blob([csv], { type: 'text/csv;charset=utf-8' }))
    const link = document.createElement('a')
    link.href = url
    link.download = `inhuis-kassa-${receiptId(receipt)}.csv`
    link.click()
    URL.revokeObjectURL(url)
  }

  async function approve() {
    if (!receiptId(receipt) || busy) return
    if (!String(receipt.store_name || '').trim()) {
      showFeedback({ variant: 'warning', message: 'Vul eerst de winkel in bij Bonkop.' })
      return
    }
    if (!String(receipt.purchase_at || '').trim()) {
      showFeedback({ variant: 'warning', message: 'Vul eerst de aankoopdatum in bij Bonkop.' })
      return
    }
    setBusy(true)
    try {
      await fetchJson(`/api/receipts/${encodeURIComponent(receiptId(receipt))}/approve`, { method: 'POST' })
      showReceiptList()
      showFeedback({ variant: 'success', message: 'Bon is goedgekeurd voor Uitpakken.' })
    } catch (error) {
      feedbackError(error, 'Bon kon niet worden goedgekeurd.')
    } finally { setBusy(false) }
  }

  const lines = receiptLines(receipt)
  const activeLines = lines.filter((line) => !line.is_deleted)
  const lineSum = activeLines.reduce((sum, line) => sum + (Number(line.display_line_total ?? line.line_total) || 0), 0)
  const lineDiscount = activeLines.reduce((sum, line) => sum + (Number(line.discount_amount) || 0), 0)
  const receiptDiscount = Number(receipt?.discount_total_effective ?? receipt?.discount_total ?? 0) || 0
  const netTotal = lineSum + lineDiscount + receiptDiscount
  const headerTotal = receipt?.total_amount === null || receipt?.total_amount === undefined || receipt?.total_amount === '' ? null : Number(receipt.total_amount)
  const totalsMatch = headerTotal !== null && Number.isFinite(headerTotal) && activeLines.length > 0 && Math.abs(headerTotal - netTotal) < 0.01
  const alreadyControlled = String(receipt?.po_norm_status_label || '').trim().toLowerCase() === 'gecontroleerd'

  return (
    <div className="rz-mobile-kassa" data-testid="mobile-kassa-page">
      <MobileModuleHeader title={mode === 'list' ? 'Bonnen' : mode === 'detail' ? 'Kassabon' : mode === 'review' ? 'Bon controleren' : 'Kassa'} testId="mobile-kassa-header" />

      {mode === 'camera' ? (
        <main className="rz-mobile-kassa-camera" data-testid="mobile-kassa-camera">
          <video ref={videoRef} playsInline muted className="rz-mobile-kassa-video" />
          <div className="rz-mobile-kassa-guide">Plaats de kassabon binnen het vlak</div>
          <input ref={fileRef} type="file" accept="image/*" capture="environment" hidden onChange={(event) => { const file = event.target.files?.[0]; event.target.value=''; if (file) uploadImage(file) }} />
          <input ref={uploadRef} type="file" accept="image/*,application/pdf" hidden aria-label="Bonbestand kiezen" onChange={(event) => { const file = event.target.files?.[0]; event.target.value = ''; if (file) uploadImage(file, 'upload') }} />
          <div className="rz-mobile-kassa-camera-actions">
            <Button type="button" onClick={showReceiptList}>Bonnen</Button>
            <Button type="button" onClick={takePhoto} disabled={busy} aria-label="Maak foto van kassabon">Foto nemen</Button>
          </div>
          <Button type="button" variant="secondary" disabled={busy} onClick={() => uploadRef.current?.click()}>Bonbestand uploaden</Button>
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
          <div className="rz-mobile-kassa-list-actions"><input type="file" accept="image/*,application/pdf" hidden ref={uploadRef} aria-label="Bonbestand kiezen" onChange={(event) => { const file = event.target.files?.[0]; event.target.value = ''; if (file) uploadImage(file, 'upload') }} /><Button type="button" variant="secondary" disabled={busy} onClick={() => uploadRef.current?.click()}>Bonbestand uploaden</Button><Button type="button" onClick={startCamera}>Nieuwe scan</Button></div>
          <input className="rz-mobile-kassa-search" aria-label="Zoek kassabonnen" placeholder="Zoek winkel of status" value={receiptFilter} onChange={(event) => setReceiptFilter(event.target.value)} />
          <div className="rz-mobile-kassa-bulk">
            <label><input type="checkbox" aria-label="Selecteer alle zichtbare bonnen" checked={receipts.length > 0 && receipts.filter((item) => `${item.store_name || ''} ${item.po_norm_status_label || item.inbox_status || ''}`.toLowerCase().includes(receiptFilter.toLowerCase())).every((item) => selectedReceiptIds.includes(receiptId(item)))} onChange={(event) => setSelectedReceiptIds(event.target.checked ? receipts.filter((item) => `${item.store_name || ''} ${item.po_norm_status_label || item.inbox_status || ''}`.toLowerCase().includes(receiptFilter.toLowerCase())).map(receiptId) : [])} /> Alles</label>
            <Button type="button" variant="secondary" disabled={!selectedReceiptIds.length || busy} onClick={() => confirmDeleteReceipts(selectedReceiptIds)}>Verwijderen</Button>
          </div>
          {receiptsLoading ? <div className="rz-mobile-kassa-empty" role="status">Kassabonnen laden…</div> : null}
          {receiptsLoadError ? <div className="rz-mobile-kassa-empty" role="alert">Kassabonnen konden niet worden geladen. <Button type="button" onClick={() => loadReceipts().catch(() => {})}>Opnieuw proberen</Button></div> : null}
          {!receiptsLoading && !receiptsLoadError && receipts.length === 0 ? <div className="rz-mobile-kassa-empty">Nog geen opgeslagen kassabonnen voor dit huishouden.</div> : receipts.filter((item) => `${item.store_name || ''} ${item.po_norm_status_label || item.inbox_status || ''}`.toLowerCase().includes(receiptFilter.toLowerCase())).map((item) => (
            <div key={receiptId(item)} className="rz-mobile-kassa-receipt-card">
              <label className="rz-mobile-kassa-select"><input type="checkbox" checked={selectedReceiptIds.includes(receiptId(item))} onChange={(event) => setSelectedReceiptIds((current) => event.target.checked ? [...current, receiptId(item)] : current.filter((id) => id !== receiptId(item)))} /> Selecteer bon</label>
              <button type="button" className="rz-mobile-kassa-open" onClick={() => openReceipt(receiptId(item))}>
                <strong>{item.store_name || 'Onbekende winkel'}</strong>
                <span>{dateLabel(item.purchase_at)} · {money(item.total_amount, item.currency)} · {item.line_count ?? 0} regels</span>
                <span>{item.po_norm_status_label || item.inbox_status || 'Controle nodig'} ›</span>
              </button>
            </div>
          ))}
        </main>
      ) : null}

      {mode === 'detail' && receipt ? (
        <main className="rz-mobile-kassa-content" data-testid="mobile-kassa-detail">
          <div className={totalsMatch || alreadyControlled ? 'rz-mobile-kassa-totals rz-mobile-kassa-totals--ok' : 'rz-mobile-kassa-totals rz-mobile-kassa-totals--warning'} data-testid="mobile-kassa-totals">
            <strong>{totalsMatch || alreadyControlled ? 'Bonbedragen sluiten aan' : 'Totaalbedrag wijkt af van de bonregels'}</strong>
            <div>Bonregels: {money(lineSum, receipt.currency)} · Regelkortingen: {money(lineDiscount, receipt.currency)} · Boncorrectie: {money(receiptDiscount, receipt.currency)}</div>
            <div>Netto bonregels: {money(netTotal, receipt.currency)} · Bonkop: {money(headerTotal, receipt.currency)}</div>
            {!totalsMatch && !alreadyControlled ? <div>Controleer de bedragen. Je kunt de afwijking bij Goedkeuren overrulen.</div> : null}
          </div>
          <Tabs tabs={['Bonregels', 'Bonkop']} defaultTab="Bonregels" ariaLabel="Kassabondetails" rootTestId="mobile-kassa-detail-tabs">
            {(tab) => tab === 'Bonkop' ? (
              <section className="rz-mobile-kassa-summary rz-mobile-kassa-fields">
                {[
                  ['Winkel', 'store_name', 'text'],
                  ['Aankoopdatum', 'purchase_at', 'date'],
                  ['Totaalbedrag', 'total_amount', 'number'],
                  ['Referentie / bonnummer', 'reference', 'text'],
                  ['Notitie', 'notes', 'text'],
                ].map(([label, field, type]) => (
                  <label key={field}>{label}<input key={`${receiptId(receipt)}-${field}-${String(receipt[field])}`} type={type} step={type === 'number' ? '0.01' : undefined} defaultValue={field === 'purchase_at' ? String(receipt[field] || '').slice(0, 10) : receipt[field] ?? ''} onBlur={(event) => { if (String(event.target.value) !== String(field === 'purchase_at' ? String(receipt[field] || '').slice(0, 10) : receipt[field] ?? '')) updateHeader(field, type === 'number' ? Number(event.target.value) : event.target.value).catch((error) => feedbackError(error, 'Bonkop kon niet worden opgeslagen.')) }} /></label>
                ))}
                <div>Valuta: {receipt.currency || 'EUR'} · {lines.length} regels</div>
              </section>
            ) : (
              <section className="rz-mobile-kassa-summary rz-mobile-kassa-fields">
                <div className="rz-mobile-kassa-bulk">
                  <label><input type="checkbox" checked={lines.length > 0 && lines.filter((line) => !line.is_deleted).every((line) => selectedLineIds.includes(String(line.id || line.receipt_line_id)))} onChange={(event) => setSelectedLineIds(event.target.checked ? lines.filter((line) => !line.is_deleted).map((line) => String(line.id || line.receipt_line_id)) : [])} /> Alles</label>
                  <Button type="button" variant="secondary" onClick={() => setAddingLine((value) => !value)}>Artikel toevoegen</Button>
                </div>
                {addingLine ? (
                  <div className="rz-mobile-kassa-fields">
                    {['article_name', 'quantity', 'unit', 'unit_price', 'line_total'].map((field) => (
                      <label key={field}>{({ article_name: 'Artikel', quantity: 'Aantal', unit: 'Eenheid', unit_price: 'Stukprijs', line_total: 'Bedrag' })[field]}<input type={['quantity', 'unit_price', 'line_total'].includes(field) ? 'number' : 'text'} step="any" value={newLine[field]} onChange={(event) => setNewLine((current) => ({ ...current, [field]: event.target.value }))} /></label>
                    ))}
                    <Button type="button" disabled={busy} onClick={addReceiptLine}>Artikel opslaan</Button>
                  </div>
                ) : null}
                {lines.filter((line) => !line.is_deleted).map((line, index) => (
                  <div key={String(line.id || line.receipt_line_id || index)} className="rz-mobile-kassa-edit-line">
                    <label className="rz-mobile-kassa-select"><input type="checkbox" checked={selectedLineIds.includes(String(line.id || line.receipt_line_id))} onChange={(event) => setSelectedLineIds((current) => event.target.checked ? [...current, String(line.id || line.receipt_line_id)] : current.filter((id) => id !== String(line.id || line.receipt_line_id)))} /> Regel {index + 1}</label>
                    {[
                      ['Artikel', 'article_name', line.normalized_label || line.display_label || line.article_name || line.raw_label || ''],
                      ['Aantal', 'quantity', line.quantity ?? 1],
                      ['Eenheid', 'unit', line.unit ?? ''],
                      ['Stukprijs', 'unit_price', line.unit_price ?? ''],
                      ['Bedrag', 'line_total', line.line_total ?? ''],
                    ].map(([label, field, value]) => (
                      <label key={field}>{label}<input key={`${line.id}-${field}-${value}`} type={['quantity', 'unit_price', 'line_total'].includes(field) ? 'number' : 'text'} step="any" defaultValue={value} onBlur={(event) => { if (String(event.target.value) !== String(value)) updateLine(line, field, event.target.value).catch((error) => feedbackError(error, 'Bonregel kon niet worden opgeslagen.')) }} /></label>
                    ))}
                  </div>
                ))}
                <div className="rz-mobile-kassa-bulk">
                  <Button type="button" variant="secondary" disabled={!selectedLineIds.length || busy} onClick={exportLines}>Exporteren</Button>
                  <Button type="button" variant="secondary" disabled={!selectedLineIds.length || busy} onClick={confirmDeleteLines}>Verwijderen</Button>
                </div>
              </section>
            )}
          </Tabs>
          <div className="rz-mobile-kassa-primary-actions">
            <Button type="button" onClick={approve} disabled={busy}>{busy ? 'Goedkeuren…' : 'Bon goedkeuren'}</Button>
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
