import { useEffect, useMemo, useRef, useState } from 'react'
import { useLocation, useNavigate } from 'react-router-dom'
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

function emailPartLabel(value) {
  if (value === 'attachment') return 'Bijlage uit e-mail'
  if (value === 'html_body') return 'HTML-body van e-mail'
  if (value === 'text_body') return 'Tekst-body van e-mail'
  return value || '-'
}

function inboundImportStatusLabel(value) {
  if (value === 'imported') return 'Automatisch ontvangen'
  if (value === 'duplicate') return 'Al eerder ontvangen'
  if (value === 'failed') return 'Ontvangen, controle nodig'
  if (value === 'received') return 'Webhook ontvangen'
  return value || '-'
}

function formatDuplicateImportMessage(result) {
  return normalizeErrorMessage(result?.duplicate_message || result?.message) || 'Deze kassabon is al eerder toegevoegd en is niet opnieuw geladen.'
}

const DELETED_RECEIPTS_STORAGE_KEY = 'rezzerv_kassa_deleted_receipts'
const DEFAULT_RECEIPT_FILTERS = { winkel: '', datum: '', totaal: '', artikelen: '', status: '' }
const MAX_CAMERA_UPLOAD_BYTES = 4 * 1024 * 1024
const MAX_CAMERA_DIMENSION = 1800

function renameFileToJpeg(name = 'receipt.jpg') {
  const baseName = String(name || 'receipt').replace(/\.[^.]+$/, '') || 'receipt'
  return `${baseName}.jpg`
}

async function loadImageForCompression(file) {
  const objectUrl = window.URL.createObjectURL(file)
  try {
    const image = await new Promise((resolve, reject) => {
      const nextImage = new Image()
      nextImage.onload = () => resolve(nextImage)
      nextImage.onerror = () => reject(new Error('Afbeelding kon niet worden geladen voor compressie.'))
      nextImage.src = objectUrl
    })
    return image
  } finally {
    window.URL.revokeObjectURL(objectUrl)
  }
}

async function canvasToJpegFile(canvas, originalName, quality) {
  const blob = await new Promise((resolve, reject) => {
    canvas.toBlob((nextBlob) => {
      if (nextBlob) resolve(nextBlob)
      else reject(new Error('Afbeelding kon niet worden voorbereid voor upload.'))
    }, 'image/jpeg', quality)
  })
  return new File([blob], renameFileToJpeg(originalName), { type: 'image/jpeg', lastModified: Date.now() })
}

async function prepareCameraUploadFile(file) {
  if (!file || !file.type?.startsWith('image/')) return file
  if (file.size <= MAX_CAMERA_UPLOAD_BYTES) return file

  const image = await loadImageForCompression(file)
  let width = Number(image.naturalWidth || image.width || 0)
  let height = Number(image.naturalHeight || image.height || 0)
  if (!width || !height) return file

  const maxDimension = Math.max(width, height)
  if (maxDimension > MAX_CAMERA_DIMENSION) {
    const scale = MAX_CAMERA_DIMENSION / maxDimension
    width = Math.max(1, Math.round(width * scale))
    height = Math.max(1, Math.round(height * scale))
  }

  const canvas = document.createElement('canvas')
  const context = canvas.getContext('2d', { alpha: false })
  if (!context) return file

  let bestFile = file
  let currentWidth = width
  let currentHeight = height

  for (let dimensionAttempt = 0; dimensionAttempt < 4; dimensionAttempt += 1) {
    canvas.width = currentWidth
    canvas.height = currentHeight
    context.fillStyle = '#ffffff'
    context.fillRect(0, 0, currentWidth, currentHeight)
    context.drawImage(image, 0, 0, currentWidth, currentHeight)

    for (const quality of [0.9, 0.82, 0.74, 0.66, 0.58]) {
      const candidateFile = await canvasToJpegFile(canvas, file.name, quality)
      if (!bestFile || candidateFile.size < bestFile.size) bestFile = candidateFile
      if (candidateFile.size <= MAX_CAMERA_UPLOAD_BYTES) return candidateFile
    }

    currentWidth = Math.max(1, Math.round(currentWidth * 0.85))
    currentHeight = Math.max(1, Math.round(currentHeight * 0.85))
  }

  return bestFile
}

function loadStoredReceiptIds(storageKey) {
  try {
    const raw = window.localStorage.getItem(storageKey)
    if (!raw) return []
    const parsed = JSON.parse(raw)
    return Array.isArray(parsed) ? parsed.map((value) => String(value)) : []
  } catch {
    return []
  }
}

function persistStoredReceiptIds(storageKey, ids) {
  try {
    window.localStorage.setItem(storageKey, JSON.stringify([...new Set(ids.map((value) => String(value)))]))
  } catch {
    // ignore storage errors
  }
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
  const confidence = Number(receipt?.confidence_score)
  if (receipt?.parse_status === 'parsed' && amountsMatch(receipt) && lineCount >= 2 && Number.isFinite(confidence) && confidence >= 0.95) {
    return 'Gecontroleerd'
  }
  if (receipt?.line_total_sum !== null && receipt?.line_total_sum !== undefined && receipt?.total_amount !== null && receipt?.total_amount !== undefined) {
    return 'Controle nodig'
  }
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
      color: '#166534',
      border: '1px solid #FEDF89',
    }
  }
  return {
    background: '#FFF7ED',
    color: '#166534',
    border: '1px solid #F9DBAF',
  }
}

function inboxStatusAccentColor(value) {
  if (value === 'Gecontroleerd') return '#12B76A'
  if (value === 'Controle nodig') return '#F79009'
  return '#B54708'
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



async function uploadSharedReceiptFile(householdId, file, sourceContext = 'shared_file', sourceLabel = '') {
  const token = localStorage.getItem('rezzerv_token') || ''
  const formData = new FormData()
  formData.append('household_id', String(householdId))
  formData.append('file', file)
  formData.append('source_context', sourceContext)
  if (sourceLabel) formData.append('source_label', sourceLabel)

  const response = await fetch('/api/receipts/share-import', {
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

async function uploadEmailReceiptFile(householdId, emailFile) {
  const token = localStorage.getItem('rezzerv_token') || ''
  const formData = new FormData()
  formData.append('household_id', String(householdId))
  formData.append('email_file', emailFile)

  const response = await fetch('/api/receipts/email-import', {
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

function isSupportedEmailImportFile(file) {
  if (!file) return false
  const fileName = String(file.name || '').toLowerCase()
  const fileType = String(file.type || '').toLowerCase()
  return fileName.endsWith('.eml') || fileType === 'message/rfc822'
}

function isSupportedReceiptDocumentFile(file) {
  if (!file) return false
  const fileName = String(file.name || '').toLowerCase()
  const fileType = String(file.type || '').toLowerCase()
  return fileName.endsWith('.pdf') || fileType === 'application/pdf' || fileType.includes('pdf')
}

function isSupportedReceiptImageFile(file) {
  if (!file) return false
  const fileName = String(file.name || '').toLowerCase()
  const fileType = String(file.type || '').toLowerCase()
  return fileName.endsWith('.png') || fileName.endsWith('.jpg') || fileName.endsWith('.jpeg') || fileType === 'image/png' || fileType === 'image/jpeg'
}

function isSupportedReceiptLandingFile(file) {
  return isSupportedEmailImportFile(file) || isSupportedReceiptDocumentFile(file) || isSupportedReceiptImageFile(file)
}

function getReceiptLandingFileKind(file) {
  if (isSupportedEmailImportFile(file)) return 'email'
  if (isSupportedReceiptDocumentFile(file)) return 'pdf'
  if (isSupportedReceiptImageFile(file)) return 'image'
  return 'unsupported'
}

function findSupportedReceiptLandingFile(files) {
  return Array.from(files || []).find(isSupportedReceiptLandingFile) || null
}

function getReceiptLandingFileFromClipboardEvent(event) {
  const clipboardFiles = Array.from(event?.clipboardData?.files || [])
  const directFile = findSupportedReceiptLandingFile(clipboardFiles)
  if (directFile) return directFile

  const clipboardItems = Array.from(event?.clipboardData?.items || [])
  for (const item of clipboardItems) {
    if (!item) continue
    if (item.kind !== 'file') continue
    const file = item.getAsFile?.()
    if (file && isSupportedReceiptLandingFile(file)) return file
  }
  return null
}

async function fetchReceiptSources(householdId) {
  return fetchJson(`/api/receipt-sources?householdId=${encodeURIComponent(householdId)}`)
}

async function fetchGmailConnectionStatus(householdId) {
  return fetchJson(`/api/receipt-sources/gmail-status?householdId=${encodeURIComponent(householdId)}`)
}

async function fetchGmailConnectUrl(householdId, frontendOrigin) {
  return fetchJson(`/api/receipts/gmail/connect-url?householdId=${encodeURIComponent(householdId)}&frontendOrigin=${encodeURIComponent(frontendOrigin || window.location.origin)}`)
}

async function syncGmailMailbox(householdId) {
  return fetchJson(`/api/receipts/gmail/sync?householdId=${encodeURIComponent(householdId)}`, {
    method: 'POST',
  })
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
  const isPdf = contentType.includes('pdf')
  const isImage = contentType.startsWith('image/')
  const isHtml = contentType.startsWith('text/html')
  const isText = contentType.startsWith('text/plain') || contentType.startsWith('message/rfc822')
  const blobUrl = (isPdf || isImage) ? window.URL.createObjectURL(blob) : ''
  const textContent = (isHtml || isText) ? await blob.text() : ''
  return {
    blobUrl,
    contentType,
    isPdf,
    isImage,
    isHtml,
    isText,
    textContent,
  }
}


function clearShareQueryParams() {
  try {
    const url = new URL(window.location.href)
    if (!url.searchParams.has('share_status')) return
    url.searchParams.delete('share_status')
    url.searchParams.delete('receipt_table_id')
    url.searchParams.delete('duplicate')
    url.searchParams.delete('parse_status')
    url.searchParams.delete('message')
    window.history.replaceState({}, '', `${url.pathname}${url.search}${url.hash}`)
  } catch {
    // ignore history errors
  }
}

function readShareQueryParams() {
  try {
    const params = new URLSearchParams(window.location.search)
    const shareStatus = params.get('share_status') || ''
    if (!shareStatus) return null
    return {
      shareStatus,
      receiptTableId: params.get('receipt_table_id') || '',
      duplicate: params.get('duplicate') === '1',
      parseStatus: params.get('parse_status') || '',
      message: params.get('message') || '',
    }
  } catch {
    return null
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

function ReceiptPreviewCard({ receipt, isCollapsed, onToggleCollapse }) {
  const [previewState, setPreviewState] = useState({ status: 'idle', blobUrl: '', contentType: '', isPdf: false, isImage: false, isHtml: false, isText: false, textContent: '', error: '' })

  useEffect(() => {
    let cancelled = false
    let activeUrl = ''

    async function loadPreview() {
      if (!receipt?.id) {
        setPreviewState({ status: 'idle', blobUrl: '', contentType: '', isPdf: false, isImage: false, isHtml: false, isText: false, textContent: '', error: '' })
        return
      }
      setPreviewState({ status: 'loading', blobUrl: '', contentType: '', isPdf: false, isImage: false, isHtml: false, isText: false, textContent: '', error: '' })
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
          setPreviewState({ status: 'error', blobUrl: '', contentType: '', isPdf: false, isImage: false, isHtml: false, isText: false, textContent: '', error: normalizeErrorMessage(err?.message) || 'Preview laden mislukt.' })
        }
      }
    }

    loadPreview()
    return () => {
      cancelled = true
      if (activeUrl) window.URL.revokeObjectURL(activeUrl)
    }
  }, [receipt?.id])


  return (
    <ScreenCard>
      {isCollapsed ? (
        <div
          style={{
            display: 'grid',
            alignContent: 'start',
            justifyItems: 'center',
            minHeight: '100%',
          }}
          data-testid="receipt-preview-card"
        >
          <button
            type="button"
            onClick={onToggleCollapse}
            data-testid="receipt-preview-toggle"
            aria-label="Originele kassabon uitklappen"
            title="Uitklappen"
            style={{
              width: '32px',
              height: '32px',
              borderRadius: '999px',
              border: '1px solid #D0D5DD',
              background: '#FFFFFF',
              color: '#166534',
              fontSize: '18px',
              fontWeight: 700,
              cursor: 'pointer',
              display: 'inline-flex',
              alignItems: 'center',
              justifyContent: 'center',
              padding: 0,
            }}
          >
            ▶
          </button>
        </div>
      ) : (
        <div style={{ display: 'grid', gap: '16px' }} data-testid="receipt-preview-card">
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', gap: '12px', flexWrap: 'wrap' }}>
            <div>
              <div style={{ fontWeight: 700, fontSize: '22px' }}>Originele kassabon</div>
            </div>
            <div className="rz-stock-table-actions" style={{ justifyContent: 'flex-start' }}>
              <button
                type="button"
                onClick={onToggleCollapse}
                data-testid="receipt-preview-toggle"
                aria-label="Originele kassabon inklappen"
                title="Inklappen"
                style={{
                  width: '32px',
                  height: '32px',
                  borderRadius: '999px',
                  border: '1px solid #D0D5DD',
                  background: '#FFFFFF',
                  color: '#166534',
                  fontSize: '18px',
                  fontWeight: 700,
                  cursor: 'pointer',
                  display: 'inline-flex',
                  alignItems: 'center',
                  justifyContent: 'center',
                  padding: 0,
                }}
              >
                ◀
              </button>
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
                  <div style={{ color: '#667085' }}>{previewState.error || 'De bonpreview is momenteel niet beschikbaar.'}</div>
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

            {previewState.status === 'ready' && previewState.isHtml ? (
              <iframe
                srcDoc={previewState.textContent || '<p>Geen HTML-preview beschikbaar.</p>'}
                title={`HTML-preview van bon ${receipt?.id}`}
                style={{ width: '100%', minHeight: '560px', border: '0', background: '#fff' }}
                sandbox=""
                data-testid="receipt-preview-html"
              />
            ) : null}

            {previewState.status === 'ready' && previewState.isText ? (
              <pre
                style={{ width: '100%', minHeight: '560px', margin: 0, padding: '16px', whiteSpace: 'pre-wrap', wordBreak: 'break-word', background: '#fff', fontFamily: 'inherit', fontSize: '14px', lineHeight: 1.5 }}
                data-testid="receipt-preview-text"
              >
                {previewState.textContent || 'Geen tekstpreview beschikbaar.'}
              </pre>
            ) : null}

            {previewState.status === 'ready' && !previewState.isPdf && !previewState.isImage && !previewState.isHtml && !previewState.isText ? (
              <div className="rz-inline-feedback rz-inline-feedback--warning" data-testid="receipt-preview-unsupported" style={{ maxWidth: '560px' }}>
                Voor dit bestandstype is geen ingebedde preview beschikbaar.
              </div>
            ) : null}
          </div>
        </div>
      )}
    </ScreenCard>
  )
}

function ReceiptDetailInfoCard({ receipt }) {
  const [selectedLineIds, setSelectedLineIds] = useState([])
  const [hiddenLineIds, setHiddenLineIds] = useState([])

  useEffect(() => {
    setSelectedLineIds([])
    setHiddenLineIds([])
  }, [receipt?.id])

  const baseLines = receipt?.lines || []
  const lines = baseLines.filter((line) => !hiddenLineIds.includes(line.id))
  const allSelected = lines.length > 0 && lines.every((line) => selectedLineIds.includes(line.id))
  const visibleLineTotalSum = lines.reduce((sum, line) => {
    const value = Number(line?.line_total)
    return Number.isFinite(value) ? sum + value : sum
  }, 0)
  const visibleDiscountSum = lines.reduce((sum, line) => {
    const value = Number(line?.discount_amount)
    return Number.isFinite(value) ? sum + value : sum
  }, 0)
  const receiptLevelDiscount = Number(receipt?.discount_total_effective ?? receipt?.discount_total)
  const visibleNetTotalSum = visibleLineTotalSum + (Number.isFinite(receiptLevelDiscount) ? receiptLevelDiscount : visibleDiscountSum)
  const detailAmountsMatch = Number.isFinite(Number(receipt?.total_amount)) && lines.length > 0 && Math.abs(Number(receipt?.total_amount) - visibleNetTotalSum) < 0.01

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

  function deleteSelectedLines() {
    if (selectedLineIds.length === 0) return
    setHiddenLineIds((current) => [...new Set([...current, ...selectedLineIds])])
    setSelectedLineIds([])
  }

  return (
    <ScreenCard>
      <div data-testid="receipt-detail-page" style={{ display: 'grid', gap: '16px' }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', gap: '12px', flexWrap: 'wrap' }}>
          <div>
            <div style={{ fontWeight: 700, fontSize: '24px' }} data-testid="receipt-detail-title">
              {receipt?.store_name || 'Kassabon'}
            </div>
          </div>
        </div>

        <Tabs tabs={['Bonregels', 'Bonkop', 'Bron']} defaultTab="Bonregels" activeColor={detailAmountsMatch ? '#166534' : '#B54708'}>
          {(activeTab) => {
            if (activeTab === 'Bonkop') {
              return (
                <div style={{ display: 'grid', gap: '12px', gridTemplateColumns: 'repeat(auto-fit, minmax(180px, 1fr))' }}>
                  <DetailInfoRow label="Winkel" value={receipt?.store_name} />
                  <DetailInfoRow label="Vestiging" value={receipt?.store_branch} />
                  <DetailInfoRow label="Aankoopmoment" value={formatDateTime(receipt?.purchase_at)} />
                  <DetailInfoRow label="Totaal" value={formatMoney(receipt?.total_amount, receipt?.currency)} />
                  <DetailInfoRow label="Som bonregels" value={formatMoney(visibleLineTotalSum, receipt?.currency)} />
                  <DetailInfoRow label="Korting" value={formatMoney(receipt?.discount_total_effective ?? receipt?.discount_total ?? visibleDiscountSum, receipt?.currency)} />
                  <DetailInfoRow label="Netto bonregels" value={formatMoney(visibleNetTotalSum, receipt?.currency)} />
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
                  <DetailInfoRow label="Afzender" value={receipt?.sender_name || receipt?.sender_email || '-'} />
                  <DetailInfoRow label="Afzender e-mail" value={receipt?.sender_email || '-'} />
                  <DetailInfoRow label="E-mail onderwerp" value={receipt?.email_subject || '-'} />
                  <DetailInfoRow label="Ontvangen op" value={formatDateTime(receipt?.email_received_at)} />
                  <DetailInfoRow label="Gekozen e-mailonderdeel" value={emailPartLabel(receipt?.selected_part_type)} />
                  <DetailInfoRow label="Bestand uit e-mail" value={receipt?.email_selected_filename || '-'} />
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
                <div className="rz-table-wrapper" style={{ paddingBottom: '12px', maxWidth: '100%' }}>
                  <table className="rz-table" data-testid="receipt-lines-table" style={{ tableLayout: 'auto', width: 'max-content', minWidth: '100%' }}>
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
                <div className="rz-stock-table-actions" style={{ justifyContent: 'flex-start' }}>
                  <Button type="button" variant="secondary" onClick={deleteSelectedLines} disabled={selectedLineIds.length === 0}>Verwijderen</Button>
                  <Button type="button" variant="secondary" onClick={exportSelected} disabled={selectedLineIds.length === 0} data-testid="receipt-export-button">Exporteren</Button>
                </div>
              </div>
            )
          }}
        </Tabs>
      </div>
    </ScreenCard>
  )
}

function ReceiptDetailView({ receipt }) {
  const [isPreviewCollapsed, setIsPreviewCollapsed] = useState(false)

  useEffect(() => {
    setIsPreviewCollapsed(false)
  }, [receipt?.id])

  return (
    <div
      style={{
        display: 'grid',
        gap: '16px',
        gridTemplateColumns: isPreviewCollapsed ? '44px minmax(0, 1fr)' : 'minmax(0, 1fr) minmax(0, 1fr)',
        alignItems: 'start',
        width: '100%',
        maxWidth: '900px',
        margin: '0 auto',
      }}
    >
      <div style={{ minWidth: 0, width: '100%' }}>
        <ReceiptPreviewCard
          receipt={receipt}
          isCollapsed={isPreviewCollapsed}
          onToggleCollapse={() => setIsPreviewCollapsed((current) => !current)}
        />
      </div>
      <div style={{ minWidth: 0, width: '100%' }}>
        <ReceiptDetailInfoCard receipt={receipt} />
      </div>
    </div>
  )
}

function ReceiptSourceHubContent({
  onChooseReceiptFile,
  onChooseCamera,
  onChooseEmail,
  onDropLandingFile,
  onCopyEmailRoute,
  emailRoute,
  isEmailRouteLoading,
  emailRouteError,
  feedbackMessage,
  feedbackVariant = 'success',
  isUploading,
  uploadProgress,
  showHeading = true,
  showSupportPanels = true,
}) {
  const [isLandingDropActive, setIsLandingDropActive] = useState(false)

  useEffect(() => {

    function handleWindowPaste(event) {
      if (isUploading) return
      const file = getReceiptLandingFileFromClipboardEvent(event)
      if (!file) return
      event.preventDefault()
      onDropLandingFile?.(file)
    }

    window.addEventListener('paste', handleWindowPaste)
    return () => window.removeEventListener('paste', handleWindowPaste)
  }, [isUploading, onDropLandingFile])

  function handleLandingDragEnter(event) {
    event.preventDefault()
    event.stopPropagation()
    if (isUploading) return
    setIsLandingDropActive(true)
  }

  function handleLandingDragOver(event) {
    event.preventDefault()
    event.stopPropagation()
    if (event.dataTransfer) event.dataTransfer.dropEffect = 'copy'
    if (isUploading) return
    if (!isLandingDropActive) setIsLandingDropActive(true)
  }

  function handleLandingDragLeave(event) {
    event.preventDefault()
    event.stopPropagation()
    const nextTarget = event.relatedTarget
    if (nextTarget && event.currentTarget?.contains?.(nextTarget)) return
    setIsLandingDropActive(false)
  }

  async function handleLandingDrop(event) {
    event.preventDefault()
    event.stopPropagation()
    setIsLandingDropActive(false)
    if (isUploading) return
    const landingFile = findSupportedReceiptLandingFile(event.dataTransfer?.files || []) || Array.from(event.dataTransfer?.files || [])[0] || null
    if (!landingFile) {
      onDropLandingFile?.(null)
      return
    }
    await onDropLandingFile?.(landingFile)
  }

  const routeAddress = emailRoute?.route_address || '-'
  const routeIsPublic = Boolean(emailRoute?.route_is_public)
  const routeDomain = emailRoute?.route_domain || ''
  const resendConfigured = Boolean(emailRoute?.resend_configured)
  const latestInbound = emailRoute?.latest || null
  const webhookEndpointPath = emailRoute?.webhook_endpoint_path || '/api/receipts/inbound'
  const forwardingStatusLabel = isEmailRouteLoading
    ? 'Doorstuuradres laden…'
    : routeIsPublic && resendConfigured
      ? 'Automatische ontvangst mogelijk'
      : routeIsPublic
        ? 'Adres klaar, inbound nog niet actief'
        : 'Lokale demo-opstelling'
  const feedbackClassName = feedbackVariant === 'error'
    ? 'rz-inline-feedback rz-inline-feedback--error'
    : feedbackVariant === 'warning'
      ? 'rz-inline-feedback rz-inline-feedback--warning'
      : 'rz-inline-feedback rz-inline-feedback--success'

  return (
    <div style={{ display: 'grid', gap: '20px' }} data-testid="kassa-add-screen">
      {showHeading ? (
        <div>
          <h2 id="kassa-bronhub-title" className="rz-modal-title" style={{ fontSize: '22px' }}>Bon toevoegen</h2>
        </div>
      ) : null}

      <ScreenCard fullWidth>
          <div style={{ display: 'grid', gap: '18px' }}>
            {feedbackMessage ? (
              <div className={feedbackClassName} style={{ fontWeight: 700 }} data-testid="receipt-landing-feedback">{feedbackMessage}</div>
            ) : null}
            <div
              role="button"
              tabIndex={0}
              onClick={() => { if (!isUploading) onChooseReceiptFile?.() }}
              onKeyDown={(event) => {
                if (event.key === 'Enter' || event.key === ' ') {
                  event.preventDefault()
                  if (!isUploading) onChooseReceiptFile?.()
                }
              }}
              onDragEnter={handleLandingDragEnter}
              onDragOver={handleLandingDragOver}
              onDragLeave={handleLandingDragLeave}
              onDrop={handleLandingDrop}
              style={{
                borderRadius: '18px',
                border: isLandingDropActive ? '2px dashed #12B76A' : '2px dashed #D0D5DD',
                background: isLandingDropActive ? 'rgba(18, 183, 106, 0.06)' : '#F8FAFC',
                padding: '28px 24px',
                display: 'grid',
                gap: '10px',
                justifyItems: 'center',
                textAlign: 'center',
                cursor: isUploading ? 'progress' : 'copy',
                outline: 'none',
                boxShadow: isLandingDropActive ? '0 0 0 4px rgba(18,183,106,0.12)' : 'none',
              }}
              aria-label="Sleep een .eml, .pdf of bonfoto naar Rezzerv, klik om een bestand te kiezen of plak vanuit het klembord"
              data-testid="kassa-email-dropzone"
            >
              <div style={{ fontSize: '22px', fontWeight: 700, color: '#166534' }}>Sleep hier je kassabon of e-mail</div>
              <div style={{ color: '#344054', fontSize: '15px', maxWidth: '640px' }}>
                Ondersteund in deze landingsplaats: <strong>.eml</strong>, <strong>.pdf</strong>, <strong>.png</strong>, <strong>.jpg</strong> en <strong>.jpeg</strong>.
              </div>
            </div>

            <div style={{ display: 'grid', gap: '10px', gridTemplateColumns: 'repeat(3, minmax(0, 1fr))', alignItems: 'stretch' }}>
              <Button type="button" variant="primary" onClick={onChooseReceiptFile} disabled={isUploading} style={{ width: '100%', fontSize: '14px', padding: '10px 12px', whiteSpace: 'nowrap' }}>Bestanden kiezen</Button>
              <Button type="button" variant="secondary" onClick={onChooseCamera} disabled={isUploading} style={{ width: '100%', fontSize: '14px', padding: '10px 12px', whiteSpace: 'nowrap' }}>Camera openen</Button>
              <Button type="button" variant="secondary" onClick={onChooseEmail} disabled={isUploading} style={{ width: '100%', fontSize: '14px', padding: '10px 12px', whiteSpace: 'nowrap' }}>Email inlezen</Button>
            </div>

            {uploadProgress?.active ? (
              <div
                className="rz-inline-feedback rz-inline-feedback--success"
                data-testid="receipt-upload-progress"
                aria-live="polite"
                style={{ display: 'grid', gap: '8px' }}
              >
                <div style={{ display: 'flex', justifyContent: 'space-between', gap: '12px', alignItems: 'center', flexWrap: 'wrap' }}>
                  <div style={{ fontWeight: 700 }}>{uploadProgress.label || 'Kassabon verwerken…'}</div>
                  <div style={{ fontSize: '13px', color: '#667085' }}>{Math.max(5, Math.min(100, Math.round(uploadProgress.percent || 0)))}%</div>
                </div>
                <div style={{ height: '10px', borderRadius: '999px', background: '#D1FADF', overflow: 'hidden' }}>
                  <div
                    style={{
                      height: '100%',
                      width: `${Math.max(5, Math.min(100, Math.round(uploadProgress.percent || 0)))}%`,
                      background: '#166534',
                      borderRadius: '999px',
                      transition: 'width 240ms ease',
                    }}
                  />
                </div>
                <div style={{ fontSize: '13px', color: '#344054' }}>{uploadProgress.detail || 'Even geduld, Rezzerv verwerkt de bon en laadt daarna Kassa.'}</div>
              </div>
            ) : null}

            {emailRouteError ? <div className="rz-inline-feedback rz-inline-feedback--error">{emailRouteError}</div> : null}
          </div>
        </ScreenCard>

        {showSupportPanels ? (
        <>
        <div style={{ display: 'grid', gap: '16px', gridTemplateColumns: 'repeat(auto-fit, minmax(280px, 1fr))' }}>
          <ScreenCard fullWidth>
            <div style={{ display: 'grid', gap: '10px' }}>
              <div style={{ fontSize: '18px', fontWeight: 700 }}>Persoonlijk Rezzerv-adres</div>
              <div style={{ border: '1px solid #D0D5DD', borderRadius: '12px', background: '#F8FAFC', padding: '12px 14px', display: 'grid', gap: '6px' }}>
                <div style={{ fontSize: '13px', color: '#667085', fontWeight: 700 }}>Status</div>
                <div style={{ fontSize: '15px', fontWeight: 700 }}>{forwardingStatusLabel}</div>
                <div style={{ fontSize: '13px', color: '#667085' }}>
                  {routeIsPublic && resendConfigured
                    ? 'Dit adres kan automatisch bonmails ontvangen zodra Resend naar jouw publieke Rezzerv-webhook post.'
                    : routeIsPublic
                      ? 'Het doorstuuradres is publiek, maar de Resend-inbound API-sleutel ontbreekt nog in Rezzerv. Gebruik voorlopig de centrale landingsplaats of .eml als fallback.'
                      : `Deze lokale build gebruikt nu ${routeDomain || 'een lokaal domein'}. Daardoor werkt automatisch ontvangen nog niet rechtstreeks vanaf internetmail.`}
                </div>
              </div>
              <div style={{ border: '1px solid #D0D5DD', borderRadius: '12px', background: '#F8FAFC', padding: '12px 14px', display: 'grid', gap: '6px' }}>
                <div style={{ fontSize: '13px', color: '#667085', fontWeight: 700 }}>Adres</div>
                <div style={{ fontSize: '15px', fontWeight: 700, wordBreak: 'break-all' }}>
                  {isEmailRouteLoading ? 'E-mailroute laden…' : routeAddress}
                </div>
              </div>
            </div>
          </ScreenCard>

          <ScreenCard fullWidth>
            <div style={{ display: 'grid', gap: '10px' }}>
              <div style={{ fontSize: '18px', fontWeight: 700 }}>Automatische ontvangst</div>
              <div style={{ border: '1px solid #D0D5DD', borderRadius: '12px', background: '#F8FAFC', padding: '12px 14px', display: 'grid', gap: '6px' }}>
                <div style={{ fontSize: '13px', color: '#667085', fontWeight: 700 }}>Laatste status</div>
                <div style={{ fontSize: '15px', fontWeight: 700 }}>
                  {latestInbound ? inboundImportStatusLabel(latestInbound.import_status) : 'Nog geen automatische mail ontvangen'}
                </div>
                <div style={{ fontSize: '13px', color: '#667085' }}>
                  {latestInbound
                    ? `Laatst ontvangen: ${formatDateTime(latestInbound.received_at || latestInbound.webhook_received_at)}`
                    : 'Zodra Resend een mail aan Rezzerv doorstuurt, zie je dat hier terug.'}
                </div>
                {latestInbound?.sender_email ? (
                  <div style={{ fontSize: '13px', color: '#667085' }}>Afzender: {latestInbound.sender_name ? `${latestInbound.sender_name} <${latestInbound.sender_email}>` : latestInbound.sender_email}</div>
                ) : null}
                <div style={{ fontSize: '13px', color: '#667085' }}>Webhook-pad in Rezzerv: <strong>{webhookEndpointPath}</strong></div>
              </div>
            </div>
          </ScreenCard>
        </div>

        <div style={{ display: 'grid', gap: '16px', gridTemplateColumns: 'repeat(auto-fit, minmax(280px, 1fr))' }}>
          <ScreenCard fullWidth>
            <div style={{ display: 'grid', gap: '12px' }}>
              <div style={{ fontSize: '18px', fontWeight: 700 }}>Importuitleg</div>
              <div style={{ color: '#667085' }}>De schermopbouw is nu gericht op één centrale actie. De extra uitleg blijft zichtbaar, maar staat bewust lager op het scherm.</div>
              <div style={{ color: '#344054', fontSize: '14px', display: 'grid', gap: '6px' }}>
                <div><strong>.eml</strong> blijft via de bestaande e-mailimport lopen.</div>
                <div><strong>.pdf</strong> en ondersteunde afbeeldingsbestanden lopen via de bestaande bonbestand-import.</div>
                <div><strong>Slepen, plakken en kiezen via Verkenner</strong> komen hiermee samen in één centrale landingsroute.</div>
              </div>
            </div>
          </ScreenCard>

          <ScreenCard fullWidth>
            <div style={{ display: 'grid', gap: '12px' }}>
              <div style={{ fontSize: '18px', fontWeight: 700 }}>Zo stel je forwarding in</div>
              <div style={{ display: 'grid', gap: '10px', color: '#344054', fontSize: '14px' }}>
                <div>
                  <div style={{ fontWeight: 700, marginBottom: '4px' }}>Gmail</div>
                  <ol style={{ margin: 0, paddingLeft: '20px', display: 'grid', gap: '4px' }}>
                    <li>Open Gmail instellingen en voeg dit Rezzerv-adres toe als doorstuuradres.</li>
                    <li>Bevestig het adres wanneer Gmail daar om vraagt.</li>
                    <li>Maak daarna een filter voor kassabonmails en kies als actie: doorsturen naar Rezzerv.</li>
                  </ol>
                </div>
                <div>
                  <div style={{ fontWeight: 700, marginBottom: '4px' }}>Outlook</div>
                  <ol style={{ margin: 0, paddingLeft: '20px', display: 'grid', gap: '4px' }}>
                    <li>Open regels in Outlook.</li>
                    <li>Maak een regel voor kassabonmails of bekende winkels.</li>
                    <li>Kies als actie: doorsturen of redirecten naar dit Rezzerv-adres.</li>
                  </ol>
                </div>
              </div>
              <Button
                type="button"
                variant="secondary"
                onClick={onCopyEmailRoute}
                disabled
                aria-disabled="true"
                title="Adres kopiëren wordt later weer geactiveerd."
                style={{ width: 'fit-content', minWidth: '180px', opacity: 0.55, cursor: 'not-allowed' }}
              >
                Adres kopiëren
              </Button>
            </div>
          </ScreenCard>
        </div>
        </>
        ) : null}
    </div>
  )
}


function CameraCaptureModal({
  isOpen,
  draftUrl,
  onConfirm,
  onRetake,
  onCancel,
  isUploading,
  error,
  duplicateNotice,
}) {
  if (!isOpen) return null

  return (
    <div className="rz-modal-backdrop" role="presentation" style={{ inset: '56px 0 0 0', alignItems: 'start', justifyItems: 'center', overflowY: 'auto', padding: '16px 20px 20px' }}>
      <div
        className="rz-modal-card"
        role="dialog"
        aria-modal="true"
        aria-labelledby="kassa-camera-title"
        style={{ width: 'min(900px, 100%)', maxHeight: 'calc(100vh - 88px)', overflow: 'auto', padding: '24px', gap: '20px', marginTop: '0' }}
      >
        <div style={{ display: 'flex', justifyContent: 'space-between', gap: '12px', alignItems: 'flex-start', flexWrap: 'wrap' }}>
          <div>
            <h2 id="kassa-camera-title" className="rz-modal-title" style={{ fontSize: '22px' }}>Foto controleren</h2>
            <p className="rz-modal-text">Controleer of de kassabon volledig zichtbaar is voordat je hem opslaat in Kassa.</p>
          </div>
          <Button type="button" variant="secondary" onClick={onCancel} disabled={isUploading}>Annuleren</Button>
        </div>

        {duplicateNotice ? <div className="rz-inline-feedback rz-inline-feedback--warning" data-testid="receipt-camera-duplicate-feedback">{duplicateNotice}</div> : null}
        {error ? <div className="rz-inline-feedback rz-inline-feedback--error">{error}</div> : null}

        <div style={{ border: '1px solid #D0D5DD', borderRadius: '12px', background: '#F8FAFC', minHeight: '360px', display: 'flex', alignItems: 'center', justifyContent: 'center', padding: '16px' }}>
          {draftUrl ? (
            <img src={draftUrl} alt="Voorbeeld van gefotografeerde kassabon" style={{ maxWidth: '100%', maxHeight: '70vh', objectFit: 'contain', borderRadius: '8px', background: '#fff' }} />
          ) : (
            <div style={{ color: '#667085' }}>Geen voorbeeld beschikbaar.</div>
          )}
        </div>

        <div className="rz-stock-table-actions" style={{ justifyContent: 'flex-start' }}>
          <Button type="button" variant="secondary" onClick={onRetake} disabled={isUploading}>Opnieuw</Button>
          <Button type="button" variant="primary" onClick={onConfirm} disabled={isUploading}>{isUploading ? 'Opslaan…' : 'Bevestigen'}</Button>
        </div>
      </div>
    </div>
  )
}


function ReceiptUploadInputs({ fileInputRef, cameraInputRef, emailInputRef, onLandingUploadChange, onCameraCaptureChange, onEmailUploadChange }) {
  return (
    <>
      <input
        ref={fileInputRef}
        type="file"
        accept=".eml,message/rfc822,.pdf,.png,.jpg,.jpeg,application/pdf,image/png,image/jpeg"
        style={{ display: 'none' }}
        onChange={onLandingUploadChange}
      />
      <input
        ref={cameraInputRef}
        type="file"
        accept="image/*"
        capture="environment"
        style={{ display: 'none' }}
        onChange={onCameraCaptureChange}
      />
      <input
        ref={emailInputRef}
        type="file"
        accept=".eml,message/rfc822"
        style={{ display: 'none' }}
        onChange={onEmailUploadChange}
      />
    </>
  )
}

export default function KassaPage() {
  const navigate = useNavigate()
  const location = useLocation()
  const isAddReceiptRoute = location.pathname === '/kassa/nieuw'
  const [householdId, setHouseholdId] = useState('1')
  const [receipts, setReceipts] = useState([])
  const [filters, setFilters] = useState(DEFAULT_RECEIPT_FILTERS)
  const [isLoading, setIsLoading] = useState(true)
  const [isUploading, setIsUploading] = useState(false)
  const [uploadProgress, setUploadProgress] = useState({ active: false, label: '', detail: '', percent: 0 })
  const [error, setError] = useState('')
  const [status, setStatus] = useState('')
  const [duplicateNotice, setDuplicateNotice] = useState('')
  const [selectedReceiptIds, setSelectedReceiptIds] = useState([])
  const [openedReceiptId, setOpenedReceiptId] = useState('')
  const [openedReceipt, setOpenedReceipt] = useState(null)
  const [deletedReceiptIds, setDeletedReceiptIds] = useState(() => loadStoredReceiptIds(DELETED_RECEIPTS_STORAGE_KEY))
  const [uploadMode, setUploadMode] = useState('manual')
  const [cameraDraft, setCameraDraft] = useState(null)
  const [cameraError, setCameraError] = useState('')
  const [emailRoute, setEmailRoute] = useState(null)
  const [isEmailRouteLoading, setIsEmailRouteLoading] = useState(false)
  const [emailRouteError, setEmailRouteError] = useState('')
  const [receiptInboxFocusId, setReceiptInboxFocusId] = useState('')
  const fileInputRef = useRef(null)
  const cameraInputRef = useRef(null)
  const emailInputRef = useRef(null)


  useEffect(() => {
    return () => {
      if (cameraDraft?.previewUrl) {
        window.URL.revokeObjectURL(cameraDraft.previewUrl)
      }
    }
  }, [cameraDraft])

  useEffect(() => {
    if (!isAddReceiptRoute) return
    setCameraError('')
    setEmailRouteError('')
    setDuplicateNotice('')
    setStatus('')
    setError('')
    resetUploadProgress()
    ensureEmailRouteLoaded().catch(() => {})
  }, [isAddReceiptRoute])

  async function deleteSelectedReceipts() {
    if (selectedReceiptIds.length === 0) return
    const deletedIds = selectedReceiptIds.map((value) => String(value))
    setError('')
    setDuplicateNotice('')
    try {
      await fetchJson('/api/receipts/delete', {
        method: 'POST',
        body: JSON.stringify({ receipt_table_ids: deletedIds }),
      })
      persistStoredReceiptIds(DELETED_RECEIPTS_STORAGE_KEY, [])
      setDeletedReceiptIds([])
      if (openedReceiptId && deletedIds.includes(String(openedReceiptId))) {
        setOpenedReceiptId('')
        setOpenedReceipt(null)
      }
      setSelectedReceiptIds([])
      await loadReceipts(householdId)
      setStatus(`${deletedIds.length} bon${deletedIds.length === 1 ? '' : 'nen'} verwijderd uit de inbox.`)
    } catch (err) {
      setError(normalizeErrorMessage(err?.message) || 'De geselecteerde bonnen konden niet worden verwijderd.')
    }
  }

  async function loadReceipts(nextHouseholdId = householdId) {
    setIsLoading(true)
    setError('')
    let items = []
    try {
      const list = await fetchJson(`/api/receipts?householdId=${encodeURIComponent(nextHouseholdId)}`)
      items = Array.isArray(list?.items) ? list.items : []
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
    return items
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
        const storedDeletedIds = loadStoredReceiptIds(DELETED_RECEIPTS_STORAGE_KEY)
        if (storedDeletedIds.length) {
          try {
            await fetchJson('/api/receipts/delete', {
              method: 'POST',
              body: JSON.stringify({ receipt_table_ids: storedDeletedIds }),
            })
            persistStoredReceiptIds(DELETED_RECEIPTS_STORAGE_KEY, [])
            if (!cancelled) setDeletedReceiptIds([])
          } catch {
            // keep local fallback when backend sync fails
          }
        }
        const items = await loadReceipts(resolvedHouseholdId)
        if (cancelled) return
        const sharedResult = readShareQueryParams()
        if (sharedResult?.shareStatus === 'error') {
          setError(sharedResult.message || 'Gedeelde inhoud kon niet worden verwerkt.')
          clearShareQueryParams()
          return
        }
        if (sharedResult?.shareStatus === 'success') {
          if (sharedResult.duplicate) {
            announceDuplicate(sharedResult)
          } else {
            setDuplicateNotice('')
            setStatus(`Gedeelde bon ontvangen met status: ${parseStatusLabel(sharedResult.parseStatus || 'partial')}`)
          }
          if (sharedResult.receiptTableId) {
            try {
              const detail = await fetchJson(`/api/receipts/${encodeURIComponent(sharedResult.receiptTableId)}`)
              const sourceItem = (items || []).find((item) => String(item.receipt_table_id) === String(sharedResult.receiptTableId)) || null
              setOpenedReceiptId(sharedResult.receiptTableId)
              setOpenedReceipt(sourceItem ? { ...sourceItem, ...detail } : detail)
            } catch {
              // ignore detail preload errors after share redirect
            }
          }
          clearShareQueryParams()
        }
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
    if (!receiptInboxFocusId) return undefined
    const timeoutId = window.setTimeout(() => {
      setReceiptInboxFocusId('')
    }, 6000)
    return () => window.clearTimeout(timeoutId)
  }, [receiptInboxFocusId])

  function announceDuplicate(result) {
    setError('')
    setStatus('')
    setDuplicateNotice(formatDuplicateImportMessage(result))
    try {
      window.requestAnimationFrame(() => {
        const feedback = document.querySelector('[data-testid="receipt-duplicate-feedback"]')
        feedback?.scrollIntoView({ behavior: 'smooth', block: 'center' })
      })
    } catch {
      // ignore scroll issues
    }
  }

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
      .filter((item) => !deletedReceiptIds.includes(String(item?.receipt_table_id || '')))
      .map((item) => ({ ...item, inbox_status: deriveInboxStatus(item) }))
      .sort((a, b) => String(b.created_at || '').localeCompare(String(a.created_at || '')))
  }, [receipts, deletedReceiptIds])

  const inboxSummary = useMemo(() => ({
    Nieuw: inboxItems.filter((item) => item.inbox_status === 'Nieuw').length,
    'Controle nodig': inboxItems.filter((item) => item.inbox_status === 'Controle nodig').length,
    Gecontroleerd: inboxItems.filter((item) => item.inbox_status === 'Gecontroleerd').length,
  }), [inboxItems])


  const landingFeedback = useMemo(() => {
    if (error) return { message: error, variant: 'error' }
    if (duplicateNotice) return { message: duplicateNotice, variant: 'warning' }
    if (status) return { message: status, variant: 'success' }
    return null
  }, [error, duplicateNotice, status])

  const listItems = useMemo(() => {
    return inboxItems
      .filter((item) => String(item.store_name || '').toLowerCase().includes(filters.winkel.trim().toLowerCase()))
      .filter((item) => formatDateTime(item.purchase_at).toLowerCase().includes(filters.datum.trim().toLowerCase()))
      .filter((item) => formatMoney(item.total_amount, item.currency).toLowerCase().includes(filters.totaal.trim().toLowerCase()))
      .filter((item) => String(item.line_count ?? 0).includes(filters.artikelen.trim()))
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

  async function ensureEmailRouteLoaded(forceReload = false) {
    if (emailRoute?.route_address && !forceReload) return emailRoute
    setIsEmailRouteLoading(true)
    setEmailRouteError('')
    try {
      const route = await fetchJson(`/api/receipt-sources/email-route?householdId=${encodeURIComponent(householdId)}`)
      setEmailRoute(route)
      return route
    } catch (err) {
      const message = normalizeErrorMessage(err?.message) || 'De e-mailroute kon niet worden geladen.'
      setEmailRouteError(message)
      throw err
    } finally {
      setIsEmailRouteLoading(false)
    }
  }


  function setUploadProgressState(active, label = '', detail = '', percent = 0) {
    setUploadProgress({ active, label, detail, percent })
  }

  function resetUploadProgress() {
    setUploadProgress({ active: false, label: '', detail: '', percent: 0 })
  }

  function buildPostImportProgressMessage(kindLabel) {
    return `${kindLabel} wordt gecontroleerd en daarna wordt Kassa opnieuw geladen.`
  }

  function openSourceHub() {
    setCameraError('')
    setEmailRouteError('')
    setDuplicateNotice('')
    resetUploadProgress()
    navigate('/kassa/nieuw')
  }

  function handleChooseReceiptFileFromHub() {
    setUploadMode('manual')
    setStatus('')
    setError('')
    setDuplicateNotice('')
    setEmailRouteError('')
    setReceiptInboxFocusId('')
    setTimeout(() => fileInputRef.current?.click(), 0)
  }

  function clearCameraDraft() {
    setCameraDraft((current) => {
      if (current?.previewUrl) window.URL.revokeObjectURL(current.previewUrl)
      return null
    })
  }

  function handleChooseCameraFromHub() {
    setUploadMode('camera_capture')
    setStatus('')
    setError('')
    setDuplicateNotice('')
    setCameraError('')
    setReceiptInboxFocusId('')
    setTimeout(() => cameraInputRef.current?.click(), 0)
  }

  function handleChooseEmailFromHub() {
    setUploadMode('email_import')
    setStatus('')
    setError('')
    setDuplicateNotice('')
    setEmailRouteError('')
    setReceiptInboxFocusId('')
    setTimeout(() => emailInputRef.current?.click(), 0)
  }

  async function copyEmailRouteToClipboard() {
    try {
      const route = await ensureEmailRouteLoaded()
      if (!route?.route_address) {
        setEmailRouteError('Er is nog geen e-mailroute beschikbaar voor dit huishouden.')
        return
      }
      await navigator.clipboard.writeText(route.route_address)
      setStatus('Het Rezzerv e-mailadres is gekopieerd.')
      setError('')
      setDuplicateNotice('')
    } catch (err) {
      setEmailRouteError(normalizeErrorMessage(err?.message) || 'Het e-mailadres kon niet worden gekopieerd.')
    }
  }

  function handleCameraCaptureChange(event) {
    const file = event.target.files?.[0]
    event.target.value = ''
    setCameraError('')
    if (!file) {
      setUploadMode('manual')
      return
    }
    clearCameraDraft()
    const previewUrl = window.URL.createObjectURL(file)
    setCameraDraft({ file, previewUrl })
  }

  async function confirmCameraDraft() {
    if (!cameraDraft?.file) return
    setIsUploading(true)
    setUploadProgressState(true, 'Kassabon verwerken…', 'Rezzerv bereidt de foto voor en verwerkt daarna de bon.', 15)
    setError('')
    setCameraError('')
    setStatus('')
    setDuplicateNotice('')
    try {
      const preparedFile = await prepareCameraUploadFile(cameraDraft.file)
      setUploadProgressState(true, 'Kassabon verwerken…', 'De gefotografeerde kassabon wordt nu geanalyseerd.', 45)
      const result = await uploadSharedReceiptFile(householdId, preparedFile, 'camera_capture', 'Foto gemaakt in Rezzerv')
      const uploadedReceiptId = String(result?.receipt_table_id || '')

      if (result?.duplicate) {
        announceDuplicate(result)
      } else {
        clearCameraDraft()
            setOpenedReceiptId('')
        setOpenedReceipt(null)
        setFilters(DEFAULT_RECEIPT_FILTERS)
        setReceiptInboxFocusId(uploadedReceiptId)

        setUploadProgressState(true, 'Kassa laden…', buildPostImportProgressMessage('De foto'), 85)
        const refreshedItems = await loadReceipts(householdId)
        const receiptExistsInInbox = uploadedReceiptId
          ? refreshedItems.some((item) => String(item?.receipt_table_id || '') === uploadedReceiptId)
          : false

        if (uploadedReceiptId && receiptExistsInInbox) {
          setSelectedReceiptIds([uploadedReceiptId])
        } else {
          setSelectedReceiptIds([])
        }

        if (result?.receipt_table_id) {
          setDuplicateNotice('')
          setStatus(`Foto verwerkt met status: ${parseStatusLabel(result.parse_status)}. De bon staat nu in de Bon-inbox.`)
        } else {
          setStatus('Foto opgeslagen, maar nog niet als bruikbare kassabon herkend.')
        }

        if (uploadedReceiptId && !receiptExistsInInbox) {
          setError('De kassabon is opgeslagen, maar kon nog niet direct als nieuwe rij in de Bon-inbox worden geladen.')
        }

        setUploadProgressState(true, 'Kassa openen…', 'De nieuwe bon staat klaar in Kassa.', 100)
        if (isAddReceiptRoute) navigate('/kassa')

        try {
          window.requestAnimationFrame(() => {
            const targetRow = uploadedReceiptId
              ? document.querySelector(`[data-testid="kassa-row-${uploadedReceiptId}"]`)
              : null
            const inbox = targetRow || document.querySelector('[data-testid="kassa-table"]')
            inbox?.scrollIntoView({ behavior: 'smooth', block: 'start' })
          })
        } catch {
          // ignore scroll issues
        }
      }
    } catch (err) {
      const message = normalizeErrorMessage(err?.message) || 'Foto van kassabon kon niet worden verwerkt.'
      setCameraError(message)
      setError('')
    } finally {
      setIsUploading(false)
      resetUploadProgress()
      setUploadMode('manual')
    }
  }

  function cancelCameraDraft() {
    setCameraError('')
    clearCameraDraft()
    setUploadMode('manual')
  }

  function retakeCameraDraft() {
    setCameraError('')
    clearCameraDraft()
    setUploadMode('camera_capture')
    setTimeout(() => cameraInputRef.current?.click(), 0)
  }

  async function processEmailImportFile(file) {
    if (!file) {
      setEmailRouteError('Sleep een .eml-bestand naar het landingsgebied of kies handmatig een e-mailbestand.')
      setError('')
      return
    }
    if (!isSupportedEmailImportFile(file)) {
      setEmailRouteError('Dit bestandstype wordt nog niet ondersteund. Gebruik in deze versie een .eml-bestand.')
      setError('')
      return
    }
    setIsUploading(true)
    setUploadProgressState(true, 'E-mail verwerken…', 'Rezzerv leest de e-mailbon en zet die klaar voor Kassa.', 20)
    setError('')
    setStatus('')
    setDuplicateNotice('')
    setEmailRouteError('')
    try {
      const result = await uploadEmailReceiptFile(householdId, file)
      const uploadedReceiptId = String(result?.receipt_table_id || '')
      if (result?.duplicate) {
        announceDuplicate(result)
      } else {
            setOpenedReceiptId('')
        setOpenedReceipt(null)
        setFilters(DEFAULT_RECEIPT_FILTERS)
        setReceiptInboxFocusId(uploadedReceiptId)
        setUploadProgressState(true, 'Kassa laden…', buildPostImportProgressMessage('De e-mailbon'), 85)
        const refreshedItems = await loadReceipts(householdId)
        const receiptExistsInInbox = uploadedReceiptId
          ? refreshedItems.some((item) => String(item?.receipt_table_id || '') === uploadedReceiptId)
          : false

        if (uploadedReceiptId && receiptExistsInInbox) {
          setSelectedReceiptIds([uploadedReceiptId])
        } else {
          setSelectedReceiptIds([])
        }

        if (result?.receipt_table_id) {
          setDuplicateNotice('')
          setStatus(`E-mailbon ontvangen met status: ${parseStatusLabel(result.parse_status)}. De bon staat nu in de Bon-inbox.`)
        } else {
          setStatus('E-mail verwerkt, maar nog niet als bruikbare kassabon herkend.')
        }

        if (uploadedReceiptId && !receiptExistsInInbox) {
          setError('De e-mailbon is opgeslagen, maar kon nog niet direct als nieuwe rij in de Bon-inbox worden geladen.')
        }

        setUploadProgressState(true, 'Kassa openen…', 'De nieuwe e-mailbon staat klaar in Kassa.', 100)
        if (isAddReceiptRoute) navigate('/kassa')

        try {
          window.requestAnimationFrame(() => {
            const targetRow = uploadedReceiptId
              ? document.querySelector(`[data-testid="kassa-row-${uploadedReceiptId}"]`)
              : null
            const inbox = targetRow || document.querySelector('[data-testid="kassa-table"]')
            inbox?.scrollIntoView({ behavior: 'smooth', block: 'start' })
          })
        } catch {
          // ignore scroll issues
        }
      }
    } catch (err) {
      const message = normalizeErrorMessage(err?.message) || 'De e-mailbon kon niet worden verwerkt.'
      setEmailRouteError(message)
      setError('')
    } finally {
      setIsUploading(false)
      resetUploadProgress()
      setUploadMode('manual')
    }
  }

  async function processReceiptFileImport(file) {
    if (!file) {
      setEmailRouteError('Kies een .pdf of ondersteunde bonafbeelding, of gebruik .eml voor een e-mailbestand.')
      setError('')
      return
    }
    if (!isSupportedReceiptDocumentFile(file) && !isSupportedReceiptImageFile(file)) {
      setEmailRouteError('Dit bestandstype wordt in deze versie nog niet als bonbestand ondersteund.')
      setError('')
      return
    }

    setIsUploading(true)
    setUploadProgressState(true, 'Kassabon verwerken…', 'Rezzerv verwerkt het bestand en bereidt Kassa voor.', 20)
    setError('')
    setStatus('')
    setDuplicateNotice('')
    setEmailRouteError('')
    try {
      const result = await uploadReceiptFile(householdId, file)
      const uploadedReceiptId = String(result?.receipt_table_id || '')
      if (result?.duplicate) {
        announceDuplicate(result)
      } else {
            setOpenedReceiptId('')
        setOpenedReceipt(null)
        setFilters(DEFAULT_RECEIPT_FILTERS)
        setReceiptInboxFocusId(uploadedReceiptId)
        setUploadProgressState(true, 'Kassa laden…', buildPostImportProgressMessage('De kassabon'), 85)
        const refreshedItems = await loadReceipts(householdId)
        const receiptExistsInInbox = uploadedReceiptId
          ? refreshedItems.some((item) => String(item?.receipt_table_id || '') === uploadedReceiptId)
          : false

        if (uploadedReceiptId && receiptExistsInInbox) {
          setSelectedReceiptIds([uploadedReceiptId])
        } else {
          setSelectedReceiptIds([])
        }

        if (result?.receipt_table_id) {
          setDuplicateNotice('')
          setStatus(`Bon toegevoegd met status: ${parseStatusLabel(result.parse_status)}. De bon staat nu in de Bon-inbox.`)
        } else {
          setStatus('Bestand opgeslagen, maar nog niet als bruikbare kassabon herkend.')
        }

        if (uploadedReceiptId && !receiptExistsInInbox) {
          setError('De kassabon is opgeslagen, maar kon nog niet direct als nieuwe rij in de Bon-inbox worden geladen.')
        }

        setUploadProgressState(true, 'Kassa openen…', 'De nieuwe kassabon staat klaar in Kassa.', 100)
        if (isAddReceiptRoute) navigate('/kassa')

        try {
          window.requestAnimationFrame(() => {
            const targetRow = uploadedReceiptId
              ? document.querySelector(`[data-testid="kassa-row-${uploadedReceiptId}"]`)
              : null
            const inbox = targetRow || document.querySelector('[data-testid="kassa-table"]')
            inbox?.scrollIntoView({ behavior: 'smooth', block: 'start' })
          })
        } catch {
          // ignore scroll issues
        }
      }
    } catch (err) {
      setEmailRouteError(normalizeErrorMessage(err?.message) || 'Upload van het bonbestand is mislukt.')
      setError('')
    } finally {
      setIsUploading(false)
      resetUploadProgress()
      setUploadMode('manual')
    }
  }

  async function processLandingReceiptFile(file) {
    if (!file) {
      setEmailRouteError('Sleep of kies een .eml, .pdf of ondersteunde bonafbeelding.')
      setError('')
      return
    }
    const fileKind = getReceiptLandingFileKind(file)
    if (fileKind === 'email') {
      await processEmailImportFile(file)
      return
    }
    if (fileKind === 'pdf' || fileKind === 'image') {
      await processReceiptFileImport(file)
      return
    }
    setEmailRouteError('Dit bestandstype wordt niet ondersteund in de centrale landingsplaats.')
    setError('')
  }

  async function handleEmailUploadChange(event) {
    const file = event.target.files?.[0]
    event.target.value = ''
    if (!file) return
    await processEmailImportFile(file)
  }

  async function handleDroppedLandingFile(file) {
    await processLandingReceiptFile(file)
  }

  async function handleLandingUploadChange(event) {
    const file = event.target.files?.[0]
    event.target.value = ''
    if (!file) return
    await processLandingReceiptFile(file)
  }

  return (
    <AppShell title={isAddReceiptRoute ? 'Bon toevoegen' : 'Kassa'} showExit={false}>
      <ReceiptUploadInputs
        fileInputRef={fileInputRef}
        cameraInputRef={cameraInputRef}
        emailInputRef={emailInputRef}
        onLandingUploadChange={handleLandingUploadChange}
        onCameraCaptureChange={handleCameraCaptureChange}
        onEmailUploadChange={handleEmailUploadChange}
      />

      {isAddReceiptRoute ? (
        <div data-testid="kassa-add-page" style={{ display: 'grid', gap: '16px' }}>
          <ReceiptSourceHubContent
            onChooseReceiptFile={handleChooseReceiptFileFromHub}
            onChooseCamera={handleChooseCameraFromHub}
            onChooseEmail={handleChooseEmailFromHub}
            onDropLandingFile={handleDroppedLandingFile}
            onCopyEmailRoute={copyEmailRouteToClipboard}
            emailRoute={emailRoute}
            isEmailRouteLoading={isEmailRouteLoading}
            emailRouteError={emailRouteError}
            feedbackMessage={landingFeedback?.message || ''}
            feedbackVariant={landingFeedback?.variant || 'success'}
            isUploading={isUploading}
            uploadProgress={uploadProgress}
          />
        </div>
      ) : (
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
                  <Button type="button" variant="primary" onClick={openSourceHub} disabled={isUploading} data-testid="kassa-add-receipt-button">{isUploading ? 'Uploaden…' : 'Bon toevoegen'}</Button>
                </div>
              </div>

              <ReceiptSourceHubContent
                onChooseReceiptFile={handleChooseReceiptFileFromHub}
                onChooseCamera={handleChooseCameraFromHub}
                onChooseEmail={handleChooseEmailFromHub}
                onDropLandingFile={handleDroppedLandingFile}
                onCopyEmailRoute={copyEmailRouteToClipboard}
                emailRoute={emailRoute}
                isEmailRouteLoading={isEmailRouteLoading}
                emailRouteError={emailRouteError}
                feedbackMessage={landingFeedback?.message || ''}
                feedbackVariant={landingFeedback?.variant || 'success'}
                isUploading={isUploading}
                uploadProgress={uploadProgress}
                showHeading={false}
                showSupportPanels={false}
              />

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
                        textAlign: 'center',
                        borderRadius: '16px',
                        border: isActive ? `2px solid ${inboxStatusAccentColor(entry.key)}` : '1px solid #D0D5DD',
                        background: '#FFFFFF',
                        padding: '16px',
                        display: 'grid',
                        gap: '8px',
                        cursor: 'pointer',
                        boxShadow: isActive ? `0 0 0 3px ${entry.key === 'Gecontroleerd' ? 'rgba(18,183,106,0.12)' : entry.key === 'Controle nodig' ? 'rgba(247,144,9,0.12)' : 'rgba(181,71,8,0.12)'}` : 'none',
                        position: 'relative',
                        overflow: 'hidden',
                      }}
                    >
                      <div style={{ position: 'absolute', left: 0, top: 0, bottom: 0, width: '8px', background: inboxStatusAccentColor(entry.key) }} />
                      <div style={{ fontSize: '15px', fontWeight: 700, justifySelf: 'center' }}>{entry.key}</div>
                      <div style={{ fontSize: '28px', fontWeight: 800, lineHeight: 1 }}>{inboxSummary[entry.key] || 0}</div>
                      <div style={{ fontSize: '13px', color: '#667085' }}>{entry.helper}</div>
                    </button>
                  )
                })}
              </div>

              <div style={{ display: 'flex', justifyContent: 'flex-end', alignItems: 'center', gap: '12px', flexWrap: 'wrap' }}>
                <Button type="button" variant="secondary" onClick={deleteSelectedReceipts} disabled={selectedReceiptIds.length === 0} data-testid="kassa-delete-selected-button">Verwijderen</Button>
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
                    </tr>
                    <tr className="rz-table-filters">
                      <th />
                      <th>
                        <input className="rz-input rz-inline-input" value={filters.winkel} onChange={(event) => handleFilterChange('winkel', event.target.value)} placeholder="Filter" aria-label="Filter op winkel" />
                      </th>
                      <th>
                        <input className="rz-input rz-inline-input" value={filters.datum} onChange={(event) => handleFilterChange('datum', event.target.value)} placeholder="Filter" aria-label="Filter op datum" />
                      </th>
                      <th>
                        <input className="rz-input rz-inline-input" value={filters.totaal} onChange={(event) => handleFilterChange('totaal', event.target.value)} placeholder="Filter" aria-label="Filter op totaal" />
                      </th>
                      <th>
                        <input className="rz-input rz-inline-input" value={filters.artikelen} onChange={(event) => handleFilterChange('artikelen', event.target.value)} placeholder="Filter" aria-label="Filter op artikelen" />
                      </th>
                    </tr>
                  </thead>
                  <tbody>
                    {isLoading ? (
                      <tr><td colSpan={5}>Bonnen laden…</td></tr>
                    ) : listItems.length === 0 ? (
                      <tr><td colSpan={5}>Er zijn nog geen bonnen in de inbox beschikbaar.</td></tr>
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
                            boxShadow: `inset 4px 0 0 ${item.inbox_status === 'Gecontroleerd' ? '#12B76A' : item.inbox_status === 'Controle nodig' ? '#F79009' : '#B54708'}`,
                            background: String(item.receipt_table_id) === receiptInboxFocusId ? '#ECFDF3' : undefined,
                            outline: String(item.receipt_table_id) === receiptInboxFocusId ? '2px solid #12B76A' : undefined,
                            outlineOffset: String(item.receipt_table_id) === receiptInboxFocusId ? '-2px' : undefined,
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
                          <td className="rz-receipts-cell">
                            <div style={{ display: 'grid', gap: '4px' }}>
                              <div>{item.store_name || 'Onbekende winkel'}</div>
                              <div style={{ fontSize: '12px', color: '#667085', fontWeight: 700 }}>{item.source_label || 'Handmatige upload'}</div>
                            </div>
                          </td>
                          <td className="rz-receipts-cell">{formatDateTime(item.purchase_at)}</td>
                          <td className="rz-num rz-receipts-cell">{formatMoney(item.total_amount, item.currency)}</td>
                          <td className="rz-num rz-receipts-cell">{item.line_count ?? 0}</td>
                        </tr>
                      )
                    })}
                  </tbody>
                </table>
              </div>
            </div>
          </ScreenCard>

          {openedReceipt ? <ReceiptDetailView receipt={openedReceipt} /> : null}
        </div>
      )}

      <CameraCaptureModal
        isOpen={Boolean(cameraDraft)}
        draftUrl={cameraDraft?.previewUrl || ''}
        onConfirm={confirmCameraDraft}
        onRetake={retakeCameraDraft}
        onCancel={cancelCameraDraft}
        isUploading={isUploading}
        error={cameraError}
        duplicateNotice={duplicateNotice}
      />
    </AppShell>
  )
}
