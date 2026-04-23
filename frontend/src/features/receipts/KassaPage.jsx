import { useEffect, useMemo, useRef, useState } from 'react'
import { useLocation, useNavigate } from 'react-router-dom'
import AppShell from '../../app/AppShell'
import ScreenCard from '../../ui/ScreenCard'
import Table from '../../ui/Table'
import Button from '../../ui/Button'
import Input from '../../ui/Input'
import Tabs from '../../ui/Tabs'
import { nextSortState, sortItems } from '../../ui/sorting'
import { buildTableWidth, ResizableHeaderCell, useResizableColumnWidths } from '../../ui/resizableTable.jsx'
import { fetchJson, normalizeErrorMessage } from '../stores/storeImportShared'
import useDismissOnComponentClick from '../../lib/useDismissOnComponentClick.js'

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
  if (value === 'approved') return 'Goedgekeurd'
  if (value === 'approved_override') return 'Goedgekeurd met override'
  if (value === 'failed') return 'Niet herkend'
  return value || '-'
}

function emailPartLabel(value) {
  if (value === 'attachment') return 'Bijlage uit e-mail'
  if (value === 'html_body') return 'HTML-body van e-mail'
  if (value === 'text_body') return 'Tekst-body van e-mail'
  return value || '-'
}

function normalizeReceiptSourceLabel(value) {
  if (!value) return 'Handmatige upload'
  if (String(value).toLowerCase() === 'manual upload') return 'Handmatige upload'
  return String(value)
}

const AH_BRANCH_MAP = {
  '8770': { address: 'Valburgseweg 20', city: 'Elst Gld' },
  '8521': { address: 'Polenplein 24 A', city: 'Driel' },
}

const ALDI_RECEIPT_HINTS = [
  {
    match: /aldi-kassabon-nl-voorbeeld|prins[_ -]?frederiklaan|c8st010\s*003|aldi_top/i,
    address: 'Prins Frederiklaan 203',
    city: 'Leidschendam',
  },
]

function extractAhBranchCode(receipt) {
  const candidates = [
    receipt?.store_branch,
    receipt?.original_filename,
    receipt?.source_label,
    receipt?.id,
  ]
  const matches = []
  for (const candidate of candidates) {
    const normalized = String(candidate || '').trim()
    if (!normalized) continue
    const directMatch = normalized.match(/^\s*(\d{4})\s*$/)
    if (directMatch) matches.push(directMatch[1])
    const allMatches = Array.from(normalized.matchAll(/(\d{4})/g)).map((match) => match[1]).filter(Boolean)
    matches.push(...allMatches)
  }
  const knownMatches = matches.filter((code) => AH_BRANCH_MAP[code])
  if (knownMatches.length) return knownMatches[knownMatches.length - 1]
  return matches.length ? matches[matches.length - 1] : ''
}

function splitBranchAddressPlace(value) {
  const normalized = String(value || '').trim()
  if (!normalized) return { address: '-', city: '-' }
  const parts = normalized.split(',').map((part) => part.trim()).filter(Boolean)
  const postcodePattern = /^\d{4}\s?[A-Z]{2}\s+(.+)$/i
  if (parts.length >= 2) {
    const trailing = parts[parts.length - 1] || ''
    const postcodeMatch = trailing.match(postcodePattern)
    return {
      address: parts.slice(0, -1).join(', ') || '-',
      city: (postcodeMatch?.[1] || trailing || '-').trim(),
    }
  }
  const standalonePostcodeMatch = normalized.match(/^(.*?),(?:\s*)?(\d{4}\s?[A-Z]{2})\s+(.+)$/i)
  if (standalonePostcodeMatch) {
    return {
      address: standalonePostcodeMatch[1].trim() || '-',
      city: standalonePostcodeMatch[3].trim() || '-',
    }
  }
  return { address: normalized, city: '-' }
}

function deriveBranchAddressPlace(receipt) {
  const storeName = String(receipt?.store_name || '').trim().toLowerCase()
  if (storeName === 'albert heijn') {
    const branchCode = extractAhBranchCode(receipt)
    if (branchCode && AH_BRANCH_MAP[branchCode]) return AH_BRANCH_MAP[branchCode]
  }
  if (storeName === 'aldi') {
    const combined = `${String(receipt?.store_branch || '')} ${String(receipt?.original_filename || '')}`.trim()
    const matchedHint = ALDI_RECEIPT_HINTS.find((entry) => entry.match.test(combined))
    if (matchedHint) return { address: matchedHint.address, city: matchedHint.city }
  }
  return splitBranchAddressPlace(receipt?.store_branch)
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


const receiptLineTableColumns = [
  { key: 'select', width: 44 },
  { key: 'article', width: 320 },
  { key: 'quantity', width: 92 },
  { key: 'unit', width: 92 },
  { key: 'unitPrice', width: 118 },
  { key: 'lineTotal', width: 128 },
  { key: 'discount', width: 118 },
]

const inboxTableColumns = [
  { key: 'select', width: 44 },
  { key: 'store', width: 300 },
  { key: 'date', width: 170 },
  { key: 'total', width: 150 },
  { key: 'items', width: 120 },
]

const DELETED_RECEIPTS_STORAGE_KEY = 'rezzerv_kassa_deleted_receipts'
const DEFAULT_RECEIPT_FILTERS = { winkel: '', datum: '', totaal: '', artikelen: '', status: '' }
const MAX_CAMERA_UPLOAD_BYTES = 4 * 1024 * 1024
const MAX_CAMERA_DIMENSION = 1800

function formatQuantity(value) {
  if (value === null || value === undefined || value === '') return '-'
  const number = Number(value)
  if (Number.isNaN(number)) return String(value)
  const hasThousandths = Math.abs(number - Math.round(number)) > 0.0009
  return new Intl.NumberFormat('nl-NL', {
    minimumFractionDigits: hasThousandths ? 3 : 0,
    maximumFractionDigits: hasThousandths ? 3 : 2,
  }).format(number)
}

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

function normalizeInboxStatus(value) {
  const normalized = String(value || '').trim()
  if (normalized === 'Gecontroleerd' || normalized === 'Controle nodig' || normalized === 'Handmatig') {
    return normalized
  }
  if (normalized === 'Nieuw' || normalized.toLowerCase() === 'manual') {
    return 'Handmatig'
  }
  return 'Handmatig'
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

async function fetchReceiptImportBatchStatus(householdId, batchId) {
  return fetchJson(`/api/receipts/import-batches/${encodeURIComponent(batchId)}?householdId=${encodeURIComponent(householdId)}`)
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
  return fileName.endsWith('.pdf') || fileName.endsWith('.zip') || fileType === 'application/pdf' || fileType.includes('pdf') || fileType === 'application/zip' || fileType === 'application/x-zip-compressed'
}

function isSupportedReceiptImageFile(file) {
  if (!file) return false
  const fileName = String(file.name || '').toLowerCase()
  const fileType = String(file.type || '').toLowerCase()
  return fileName.endsWith('.png') || fileName.endsWith('.jpg') || fileName.endsWith('.jpeg') || fileName.endsWith('.webp') || fileType === 'image/png' || fileType === 'image/jpeg' || fileType === 'image/webp'
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
            className="rz-expand-chip"
            style={{ width: '32px', height: '32px' }}
          >
            +
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
                className="rz-expand-chip"
                style={{ width: '32px', height: '32px' }}
              >
                −
              </button>
            </div>
          </div>

          <div
            style={{
              border: '1px solid #d0d5dd',
              borderRadius: '8px',
              minHeight: '420px',
              background: '#f8fafc',
              overflow: 'auto',
              display: 'block',
              padding: previewState.isImage ? '16px' : '0',
              height: '72vh',
              maxHeight: '72vh',
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
              <object
                data={`${previewState.blobUrl}#toolbar=1&navpanes=0&scrollbar=1&zoom=page-width`}
                type="application/pdf"
                title={`Preview van bon ${receipt?.id}`}
                style={{ display: 'block', width: '100%', height: '100%', minHeight: '900px', border: '0', background: '#fff' }}
                data-testid="receipt-preview-pdf"
              >
                <iframe
                  src={`${previewState.blobUrl}#toolbar=1&navpanes=0&scrollbar=1&zoom=page-width`}
                  title={`Preview van bon ${receipt?.id}`}
                  style={{ display: 'block', width: '100%', height: '100%', minHeight: '900px', border: '0', background: '#fff' }}
                />
              </object>
            ) : null}

            {previewState.status === 'ready' && previewState.isImage ? (
              <img
                src={previewState.blobUrl}
                alt={`Preview van bon ${receipt?.id}`}
                style={{ display: 'block', width: '100%', maxWidth: '100%', height: 'auto', background: '#fff', borderRadius: '4px' }}
                data-testid="receipt-preview-image"
              />
            ) : null}

            {previewState.status === 'ready' && previewState.isHtml ? (
              <iframe
                srcDoc={previewState.textContent || '<p>Geen HTML-preview beschikbaar.</p>'}
                title={`HTML-preview van bon ${receipt?.id}`}
                style={{ display: 'block', width: '100%', height: '100%', minHeight: '560px', border: '0', background: '#fff' }}
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

function ReceiptDetailInfoCard({ receipt, canEdit = false, onReceiptUpdated, onFeedback }) {
  const [selectedLineIds, setSelectedLineIds] = useState([])
  const [lineSort, setLineSort] = useState({ key: 'lineIndex', direction: 'asc' })
  const [isSavingHeader, setIsSavingHeader] = useState(false)
  const [isApproving, setIsApproving] = useState(false)
  const [headerDraft, setHeaderDraft] = useState({
    store_name: receipt?.store_name || '',
    purchase_at: receipt?.purchase_at || '',
    total_amount: receipt?.total_amount ?? '',
    reference: receipt?.reference || '',
    notes: receipt?.notes || '',
  })
  const [lineDrafts, setLineDrafts] = useState({})
  const [isAddingLine, setIsAddingLine] = useState(false)
  const [newLineDraft, setNewLineDraft] = useState({ article_name: '', quantity: 1, unit: '', unit_price: '', line_total: '' })

  useEffect(() => {
    setSelectedLineIds([])
    setHeaderDraft({
      store_name: receipt?.store_name || '',
      purchase_at: receipt?.purchase_at || '',
      total_amount: receipt?.total_amount ?? '',
      reference: receipt?.reference || '',
      notes: receipt?.notes || '',
    })
    const nextDrafts = {}
    ;(receipt?.lines || []).forEach((line) => {
      nextDrafts[line.id] = {
        article_name: line?.display_label ?? line?.corrected_raw_label ?? line?.raw_label ?? '',
        quantity: line?.display_quantity ?? line?.corrected_quantity ?? line?.quantity ?? '',
        unit: line?.display_unit ?? line?.corrected_unit ?? line?.unit ?? '',
        unit_price: line?.display_unit_price ?? line?.corrected_unit_price ?? line?.unit_price ?? '',
        line_total: line?.display_line_total ?? line?.corrected_line_total ?? line?.line_total ?? '',
        is_validated: Boolean(line?.is_validated),
        is_deleted: Boolean(line?.is_deleted),
      }
    })
    setLineDrafts(nextDrafts)
    setIsAddingLine(false)
    setNewLineDraft({ article_name: '', quantity: 1, unit: '', unit_price: '', line_total: '' })
  }, [receipt?.id, receipt?.updated_at])

  const baseLines = receipt?.lines || []
  const lines = baseLines.filter((line) => !Boolean(lineDrafts[line.id]?.is_deleted ?? line?.is_deleted))
  const sortedLines = useMemo(() => sortItems(lines, lineSort, {
    lineIndex: (line) => Number(line?.line_index || 0),
    article: (line) => String(line?.display_label || '').toLowerCase(),
    quantity: (line) => Number(line?.display_quantity || 0),
    unit: (line) => String(line?.display_unit || '').toLowerCase(),
    unitPrice: (line) => Number(line?.display_unit_price || 0),
    lineTotal: (line) => Number(line?.display_line_total || 0),
    discount: (line) => Number(line?.discount_amount || 0),
  }), [lines, lineSort])

  const selectedVisibleLineIds = useMemo(() => sortedLines.map((line) => String(line.id)), [sortedLines])
  const allVisibleSelected = selectedVisibleLineIds.length > 0 && selectedVisibleLineIds.every((id) => selectedLineIds.includes(id))
  const someVisibleSelected = selectedVisibleLineIds.some((id) => selectedLineIds.includes(id))

  useEffect(() => {
    const checkbox = document.getElementById('receipt-line-select-all')
    if (checkbox) checkbox.indeterminate = !allVisibleSelected && someVisibleSelected
  }, [allVisibleSelected, someVisibleSelected, sortedLines.length])

  function updateHeaderField(field, value) {
    setHeaderDraft((current) => ({ ...current, [field]: value }))
  }

  function updateLineDraft(lineId, field, value) {
    setLineDrafts((current) => ({
      ...current,
      [lineId]: {
        ...(current[lineId] || {}),
        [field]: value,
      },
    }))
  }

  function toggleLineSelection(lineId) {
    const normalizedId = String(lineId)
    setSelectedLineIds((current) => current.includes(normalizedId)
      ? current.filter((value) => value !== normalizedId)
      : [...current, normalizedId])
  }

  function toggleSelectAllVisible() {
    if (allVisibleSelected) {
      setSelectedLineIds((current) => current.filter((id) => !selectedVisibleLineIds.includes(id)))
      return
    }
    setSelectedLineIds((current) => [...new Set([...current, ...selectedVisibleLineIds])])
  }

  function markSelectedValidated(nextValue) {
    const nextSelected = [...selectedLineIds]
    if (!nextSelected.length) return
    setLineDrafts((current) => {
      const nextDrafts = { ...current }
      nextSelected.forEach((id) => {
        nextDrafts[id] = {
          ...(nextDrafts[id] || {}),
          is_validated: nextValue,
        }
      })
      return nextDrafts
    })
  }

  function deleteSelectedLines() {
    if (!selectedLineIds.length) return
    setLineDrafts((current) => {
      const nextDrafts = { ...current }
      selectedLineIds.forEach((id) => {
        nextDrafts[id] = {
          ...(nextDrafts[id] || {}),
          is_deleted: true,
        }
      })
      return nextDrafts
    })
    setSelectedLineIds([])
  }

  async function saveHeader() {
    if (!receipt?.id) return
    setIsSavingHeader(true)
    try {
      const updated = await fetchJson(`/api/receipt-tables/${encodeURIComponent(receipt.id)}`, {
        method: 'PATCH',
        body: JSON.stringify({
          store_name: headerDraft.store_name,
          purchase_at: headerDraft.purchase_at,
          total_amount: headerDraft.total_amount === '' ? null : Number(headerDraft.total_amount),
          reference: headerDraft.reference,
          notes: headerDraft.notes,
        }),
      })
      onReceiptUpdated?.(updated)
      onFeedback?.('success', 'Bonkop is opgeslagen.')
    } catch (err) {
      onFeedback?.('error', normalizeErrorMessage(err?.message) || 'Opslaan van de bonkop is mislukt.')
    } finally {
      setIsSavingHeader(false)
    }
  }

  async function saveLines() {
    if (!receipt?.id) return
    setIsSavingHeader(true)
    try {
      const payload = {
        lines: (receipt.lines || []).map((line) => {
          const draft = lineDrafts[line.id] || {}
          return {
            id: line.id,
            corrected_raw_label: draft.article_name,
            corrected_quantity: draft.quantity === '' ? null : Number(draft.quantity),
            corrected_unit: draft.unit || null,
            corrected_unit_price: draft.unit_price === '' ? null : Number(draft.unit_price),
            corrected_line_total: draft.line_total === '' ? null : Number(draft.line_total),
            is_validated: Boolean(draft.is_validated),
            is_deleted: Boolean(draft.is_deleted),
          }
        }),
      }
      const updated = await fetchJson(`/api/receipt-tables/${encodeURIComponent(receipt.id)}/lines`, {
        method: 'PATCH',
        body: JSON.stringify(payload),
      })
      onReceiptUpdated?.(updated)
      onFeedback?.('success', 'Bonregels zijn opgeslagen.')
      setSelectedLineIds([])
    } catch (err) {
      onFeedback?.('error', normalizeErrorMessage(err?.message) || 'Opslaan van de bonregels is mislukt.')
    } finally {
      setIsSavingHeader(false)
    }
  }

  async function addLine() {
    if (!receipt?.id) return
    setIsAddingLine(true)
    try {
      const updated = await fetchJson(`/api/receipt-tables/${encodeURIComponent(receipt.id)}/lines`, {
        method: 'POST',
        body: JSON.stringify({
          raw_label: newLineDraft.article_name,
          quantity: newLineDraft.quantity === '' ? null : Number(newLineDraft.quantity),
          unit: newLineDraft.unit || null,
          unit_price: newLineDraft.unit_price === '' ? null : Number(newLineDraft.unit_price),
          line_total: newLineDraft.line_total === '' ? null : Number(newLineDraft.line_total),
        }),
      })
      onReceiptUpdated?.(updated)
      onFeedback?.('success', 'Bonregel is toegevoegd.')
      setNewLineDraft({ article_name: '', quantity: 1, unit: '', unit_price: '', line_total: '' })
    } catch (err) {
      onFeedback?.('error', normalizeErrorMessage(err?.message) || 'Toevoegen van de bonregel is mislukt.')
    } finally {
      setIsAddingLine(false)
    }
  }

  async function approveReceipt() {
    if (!receipt?.id) return
    setIsApproving(true)
    try {
      const updated = await fetchJson(`/api/receipt-tables/${encodeURIComponent(receipt.id)}/approve`, {
        method: 'POST',
      })
      onReceiptUpdated?.(updated)
      onFeedback?.('success', 'Kassabon is goedgekeurd.')
    } catch (err) {
      onFeedback?.('error', normalizeErrorMessage(err?.message) || 'Goedkeuren van de bon is mislukt.')
    } finally {
      setIsApproving(false)
    }
  }

  const canSave = canEdit
  const receiptAddress = deriveBranchAddressPlace(receipt)
  const verifiedLineCount = lines.filter((line) => Boolean(lineDrafts[line.id]?.is_validated ?? line?.is_validated)).length
  const totalLineCount = lines.length

  return (
    <ScreenCard fullWidth>
      <div style={{ display: 'grid', gap: '24px' }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', gap: '16px', flexWrap: 'wrap' }}>
          <div>
            <div style={{ fontWeight: 700, fontSize: '24px' }}>Bongegevens</div>
            <div style={{ color: '#667085', marginTop: '4px' }}>
              Werk de bonkop en bonregels bij voordat je de kassabon goedkeurt.
            </div>
          </div>
          <div className="rz-stock-table-actions" style={{ justifyContent: 'flex-start' }}>
            <Button type="button" variant="secondary" onClick={saveHeader} disabled={!canSave || isSavingHeader} data-testid="receipt-save-header-button">{isSavingHeader ? 'Opslaan…' : 'Bonkop opslaan'}</Button>
            <Button type="button" variant="secondary" onClick={saveLines} disabled={!canSave || isSavingHeader} data-testid="receipt-save-lines-button">{isSavingHeader ? 'Opslaan…' : 'Bonregels opslaan'}</Button>
            <Button type="button" variant="primary" onClick={approveReceipt} disabled={!canSave || isApproving || totalLineCount === 0 || verifiedLineCount < totalLineCount} data-testid="receipt-approve-button">{isApproving ? 'Goedkeuren…' : 'Kassabon goedkeuren'}</Button>
          </div>
        </div>

        <div style={{ display: 'grid', gap: '16px', gridTemplateColumns: 'repeat(auto-fit, minmax(220px, 1fr))' }}>
          <DetailInfoRow label="Status" value={parseStatusLabel(receipt.status)} />
          <DetailInfoRow label="Bron" value={normalizeReceiptSourceLabel(receipt.source_label || receipt.source_type)} />
          <DetailInfoRow label="Winkeladres" value={receiptAddress.address} />
          <DetailInfoRow label="Plaats" value={receiptAddress.city} />
        </div>

        <div style={{ display: 'grid', gap: '16px', gridTemplateColumns: 'repeat(auto-fit, minmax(220px, 1fr))' }}>
          <div style={{ display: 'grid', gap: '6px' }}>
            <div style={{ fontSize: '13px', fontWeight: 700, color: '#667085' }}>Winkelnaam</div>
            <Input value={headerDraft.store_name} onChange={(event) => updateHeaderField('store_name', event.target.value)} disabled={!canEdit} data-testid="receipt-store-name-input" />
          </div>
          <div style={{ display: 'grid', gap: '6px' }}>
            <div style={{ fontSize: '13px', fontWeight: 700, color: '#667085' }}>Aankoopdatum</div>
            <Input type="datetime-local" value={headerDraft.purchase_at ? String(headerDraft.purchase_at).slice(0, 16) : ''} onChange={(event) => updateHeaderField('purchase_at', event.target.value)} disabled={!canEdit} data-testid="receipt-purchase-at-input" />
          </div>
          <div style={{ display: 'grid', gap: '6px' }}>
            <div style={{ fontSize: '13px', fontWeight: 700, color: '#667085' }}>Totaalbedrag</div>
            <Input type="number" step="0.01" value={headerDraft.total_amount ?? ''} onChange={(event) => updateHeaderField('total_amount', event.target.value)} disabled={!canEdit} data-testid="receipt-total-amount-input" />
          </div>
          <div style={{ display: 'grid', gap: '6px' }}>
            <div style={{ fontSize: '13px', fontWeight: 700, color: '#667085' }}>Referentie</div>
            <Input value={headerDraft.reference} onChange={(event) => updateHeaderField('reference', event.target.value)} disabled={!canEdit} data-testid="receipt-reference-input" />
          </div>
        </div>

        <div style={{ display: 'grid', gap: '6px' }}>
          <div style={{ fontSize: '13px', fontWeight: 700, color: '#667085' }}>Notities</div>
          <textarea
            value={headerDraft.notes}
            onChange={(event) => updateHeaderField('notes', event.target.value)}
            disabled={!canEdit}
            rows={3}
            data-testid="receipt-notes-input"
            style={{ width: '100%', borderRadius: '12px', border: '1px solid #D0D5DD', padding: '12px 14px', fontSize: '14px', resize: 'vertical' }}
          />
        </div>

        <div style={{ display: 'grid', gap: '16px' }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', gap: '12px', flexWrap: 'wrap' }}>
            <div>
              <div style={{ fontWeight: 700, fontSize: '20px' }}>Bonregels</div>
              <div style={{ color: '#667085', marginTop: '4px' }}>
                {verifiedLineCount} van {totalLineCount} regels gecontroleerd.
              </div>
            </div>
            <div className="rz-stock-table-actions" style={{ justifyContent: 'flex-start' }}>
              <Button type="button" variant="secondary" onClick={() => markSelectedValidated(true)} disabled={!canEdit || !selectedLineIds.length} data-testid="receipt-validate-selected-button">Markeer geselecteerd als gecontroleerd</Button>
              <Button type="button" variant="secondary" onClick={() => markSelectedValidated(false)} disabled={!canEdit || !selectedLineIds.length} data-testid="receipt-unvalidate-selected-button">Hef controle geselecteerd op</Button>
              <Button type="button" variant="secondary" onClick={deleteSelectedLines} disabled={!canEdit || !selectedLineIds.length} data-testid="receipt-delete-selected-button">Verwijder geselecteerde regels</Button>
            </div>
          </div>

          <div className="rz-table-wrap">
            <table className="rz-table" data-testid="receipt-detail-lines-table" style={{ tableLayout: 'fixed', width: buildTableWidth(receiptLineTableColumns, null) }}>
              <colgroup>
                {receiptLineTableColumns.map((column) => <col key={column.key} style={{ width: `${column.width}px` }} />)}
              </colgroup>
              <thead>
                <tr>
                  <th style={{ textAlign: 'center' }}>
                    <input id="receipt-line-select-all" type="checkbox" checked={allVisibleSelected} onChange={toggleSelectAllVisible} data-testid="receipt-line-select-all" />
                  </th>
                  <th>Artikel</th>
                  <th>Aantal</th>
                  <th>Eenheid</th>
                  <th>Prijs per stuk</th>
                  <th>Regeltotaal</th>
                  <th>Korting</th>
                </tr>
              </thead>
              <tbody>
                {sortedLines.map((line) => {
                  const draft = lineDrafts[line.id] || {}
                  const isSelected = selectedLineIds.includes(String(line.id))
                  return (
                    <tr key={line.id} data-testid={`receipt-line-row-${line.id}`}>
                      <td style={{ textAlign: 'center' }}>
                        <input type="checkbox" checked={isSelected} onChange={() => toggleLineSelection(line.id)} data-testid={`receipt-line-select-${line.id}`} />
                      </td>
                      <td>
                        <Input value={draft.article_name ?? ''} onChange={(event) => updateLineDraft(line.id, 'article_name', event.target.value)} disabled={!canEdit} data-testid={`receipt-line-article-${line.id}`} />
                      </td>
                      <td>
                        <Input type="number" step="0.001" value={draft.quantity ?? ''} onChange={(event) => updateLineDraft(line.id, 'quantity', event.target.value)} disabled={!canEdit} data-testid={`receipt-line-quantity-${line.id}`} />
                      </td>
                      <td>
                        <Input value={draft.unit ?? ''} onChange={(event) => updateLineDraft(line.id, 'unit', event.target.value)} disabled={!canEdit} data-testid={`receipt-line-unit-${line.id}`} />
                      </td>
                      <td>
                        <Input type="number" step="0.01" value={draft.unit_price ?? ''} onChange={(event) => updateLineDraft(line.id, 'unit_price', event.target.value)} disabled={!canEdit} data-testid={`receipt-line-unit-price-${line.id}`} />
                      </td>
                      <td>
                        <Input type="number" step="0.01" value={draft.line_total ?? ''} onChange={(event) => updateLineDraft(line.id, 'line_total', event.target.value)} disabled={!canEdit} data-testid={`receipt-line-total-${line.id}`} />
                      </td>
                      <td>{formatMoney(line.discount_amount)}</td>
                    </tr>
                  )
                })}
                {!sortedLines.length ? (
                  <tr>
                    <td colSpan={7} style={{ textAlign: 'center', color: '#667085' }}>Geen bonregels beschikbaar.</td>
                  </tr>
                ) : null}
              </tbody>
            </table>
          </div>

          <div style={{ display: 'grid', gap: '12px', gridTemplateColumns: '2fr repeat(4, minmax(120px, 1fr))' }}>
            <Input placeholder="Nieuw artikel" value={newLineDraft.article_name} onChange={(event) => setNewLineDraft((current) => ({ ...current, article_name: event.target.value }))} disabled={!canEdit || isAddingLine} data-testid="receipt-new-line-article" />
            <Input type="number" step="0.001" placeholder="Aantal" value={newLineDraft.quantity} onChange={(event) => setNewLineDraft((current) => ({ ...current, quantity: event.target.value }))} disabled={!canEdit || isAddingLine} data-testid="receipt-new-line-quantity" />
            <Input placeholder="Eenheid" value={newLineDraft.unit} onChange={(event) => setNewLineDraft((current) => ({ ...current, unit: event.target.value }))} disabled={!canEdit || isAddingLine} data-testid="receipt-new-line-unit" />
            <Input type="number" step="0.01" placeholder="Prijs/stuk" value={newLineDraft.unit_price} onChange={(event) => setNewLineDraft((current) => ({ ...current, unit_price: event.target.value }))} disabled={!canEdit || isAddingLine} data-testid="receipt-new-line-unit-price" />
            <Input type="number" step="0.01" placeholder="Regeltotaal" value={newLineDraft.line_total} onChange={(event) => setNewLineDraft((current) => ({ ...current, line_total: event.target.value }))} disabled={!canEdit || isAddingLine} data-testid="receipt-new-line-total" />
          </div>

          <div className="rz-stock-table-actions" style={{ justifyContent: 'flex-start' }}>
            <Button type="button" variant="secondary" onClick={addLine} disabled={!canEdit || !newLineDraft.article_name || isAddingLine} data-testid="receipt-add-line-button">{isAddingLine ? 'Toevoegen…' : 'Regel toevoegen'}</Button>
          </div>
        </div>
      </div>
    </ScreenCard>
  )
}

function ReceiptDetailView({ receipt, canEdit = false, onReceiptUpdated, onFeedback }) {
  const [isPreviewCollapsed, setIsPreviewCollapsed] = useState(false)

  useEffect(() => {
    setIsPreviewCollapsed(false)
  }, [receipt?.id])

  return (
    <div
      style={{
        display: 'grid',
        gap: '16px',
        alignItems: 'start',
        gridTemplateColumns: isPreviewCollapsed
          ? 'minmax(44px, 44px) minmax(0, 1fr)'
          : 'minmax(280px, 0.95fr) minmax(0, 2.35fr)',
      }}
    >
      <div style={{ minWidth: 0, width: '100%', overflow: 'visible' }}>
        <ReceiptPreviewCard
          receipt={receipt}
          isCollapsed={isPreviewCollapsed}
          onToggleCollapse={() => setIsPreviewCollapsed((current) => !current)}
        />
      </div>
      <div style={{ minWidth: 0, width: '100%', overflow: 'visible' }}>
        <ReceiptDetailInfoCard receipt={receipt} canEdit={canEdit} onReceiptUpdated={onReceiptUpdated} onFeedback={onFeedback} />
      </div>
    </div>
  )
}

function formatReceiptDateForInbox(value) {
  if (!value) return '-'
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return String(value)
  return new Intl.DateTimeFormat('nl-NL', { dateStyle: 'short', timeStyle: 'short' }).format(date)
}

function defaultReceiptSelection(receipts) {
  if (!Array.isArray(receipts) || !receipts.length) return []
  return [String(receipts[0]?.receipt_table_id || '')].filter(Boolean)
}

function selectReceiptById(receipts, receiptId) {
  if (!receiptId) return defaultReceiptSelection(receipts)
  const normalizedId = String(receiptId)
  const match = receipts.find((receipt) => String(receipt?.receipt_table_id || '') === normalizedId)
  if (!match) return defaultReceiptSelection(receipts)
  return [normalizedId]
}

function resolveReceiptById(receipts, receiptId) {
  if (!receiptId) return null
  return receipts.find((receipt) => String(receipt?.receipt_table_id || '') === String(receiptId)) || null
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
  const [isDragging, setIsDragging] = useState(false)

  const handleDragOver = (event) => {
    event.preventDefault()
    event.dataTransfer.dropEffect = 'copy'
    setIsDragging(true)
  }

  const handleDragLeave = (event) => {
    event.preventDefault()
    if (event.currentTarget.contains(event.relatedTarget)) return
    setIsDragging(false)
  }

  const handleDrop = async (event) => {
    event.preventDefault()
    setIsDragging(false)
    const file = findSupportedReceiptLandingFile(event.dataTransfer?.files)
    if (file) {
      await onDropLandingFile?.(file)
    }
  }

  const copyButtonLabel = emailRoute ? 'Kopieer e-mailadres' : 'E-mailroute laden'

  return (
    <div style={{ display: 'grid', gap: '16px' }}>
      {showHeading ? (
        <div>
          <div style={{ fontWeight: 700, fontSize: '22px' }}>Bon toevoegen</div>
          <div style={{ color: '#667085', marginTop: '4px' }}>
            Kies hoe je een kassabon wilt aanleveren voor Kassa.
          </div>
        </div>
      ) : null}

      <div
        onDragOver={handleDragOver}
        onDragLeave={handleDragLeave}
        onDrop={handleDrop}
        style={{
          border: isDragging ? '2px dashed #12B76A' : '1px dashed #98A2B3',
          borderRadius: '16px',
          padding: '20px',
          background: isDragging ? '#ECFDF3' : '#FFFFFF',
          display: 'grid',
          gap: '16px',
        }}
        data-testid="receipt-source-hub"
      >
        <div style={{ display: 'grid', gap: '8px' }}>
          <div style={{ fontWeight: 700, fontSize: '18px' }}>Landingsplaats</div>
          <div style={{ color: '#667085' }}>
            Sleep een kassabon naar dit vak of kies een van de routes hieronder. Ondersteund: .pdf, .zip, .png, .jpg, .jpeg, .webp of .eml.
          </div>
        </div>

        <div className="rz-stock-table-actions" style={{ justifyContent: 'flex-start', gap: '12px', flexWrap: 'wrap' }}>
          <Button type="button" variant="primary" onClick={onChooseReceiptFile} disabled={isUploading} data-testid="receipt-source-hub-upload-button">{isUploading ? 'Uploaden…' : 'Bestand kiezen'}</Button>
          <Button type="button" variant="secondary" onClick={onChooseCamera} disabled={isUploading} data-testid="receipt-source-hub-camera-button">Foto maken</Button>
          <Button type="button" variant="secondary" onClick={onChooseEmail} disabled={isUploading} data-testid="receipt-source-hub-email-button">E-mailbestand (.eml)</Button>
          <Button type="button" variant="secondary" onClick={onCopyEmailRoute} disabled={isEmailRouteLoading} data-testid="receipt-source-hub-email-route-button">
            {isEmailRouteLoading ? 'Laden…' : copyButtonLabel}
          </Button>
        </div>

        {uploadProgress?.active ? (
          <div className="rz-inline-feedback rz-inline-feedback--success" data-testid="receipt-upload-progress">
            <div style={{ display: 'grid', gap: '10px' }}>
              <div style={{ fontWeight: 700 }}>{uploadProgress.label || 'Upload bezig…'}</div>
              {uploadProgress.detail ? <div style={{ color: '#475467' }}>{uploadProgress.detail}</div> : null}
              <div style={{ height: '10px', borderRadius: '999px', background: '#d1fadf', overflow: 'hidden' }}>
                <div
                  style={{
                    height: '100%',
                    width: `${Math.max(0, Math.min(100, Number(uploadProgress.percent) || 0))}%`,
                    background: '#12B76A',
                    transition: 'width 180ms ease',
                  }}
                />
              </div>
              <div style={{ fontSize: '13px', color: '#344054' }}>{Math.round(Math.max(0, Math.min(100, Number(uploadProgress.percent) || 0)))}%</div>
            </div>
          </div>
        ) : null}

        {!uploadProgress?.active && feedbackMessage ? (
          <div
            className={feedbackVariant === 'warning' ? 'rz-inline-feedback rz-inline-feedback--warning' : 'rz-inline-feedback rz-inline-feedback--success'}
            data-testid="receipt-hub-feedback"
          >
            {feedbackMessage}
          </div>
        ) : null}

        {emailRoute ? (
          <div className="rz-inline-feedback rz-inline-feedback--success" data-testid="receipt-email-route-preview">
            Gebruik dit Rezzerv-adres om kassabonnen automatisch door te sturen:<br />
            <strong>{emailRoute}</strong>
          </div>
        ) : null}

        {emailRouteError ? (
          <div className="rz-inline-feedback rz-inline-feedback--warning" data-testid="receipt-email-route-error">
            {emailRouteError}
          </div>
        ) : null}

        {showSupportPanels ? (
          <div style={{ display: 'grid', gap: '12px', gridTemplateColumns: 'repeat(auto-fit, minmax(220px, 1fr))' }}>
            <ScreenCard>
              <div style={{ display: 'grid', gap: '8px' }}>
                <div style={{ fontWeight: 700 }}>Foto vanaf je telefoon</div>
                <div style={{ color: '#667085' }}>
                  Gebruik <strong>Foto maken</strong> om direct een kassabon met de camera vast te leggen. De foto wordt vóór upload automatisch gecomprimeerd als dat nodig is.
                </div>
              </div>
            </ScreenCard>
            <ScreenCard>
              <div style={{ display: 'grid', gap: '8px' }}>
                <div style={{ fontWeight: 700 }}>E-mail route</div>
                <div style={{ color: '#667085' }}>
                  Kopieer het Rezzerv e-mailadres en stel in je mailbox een regel in om kassabonmails automatisch door te sturen.
                </div>
              </div>
            </ScreenCard>
          </div>
        ) : null}
      </div>
    </div>
  )
}

function CameraDraftCard({ draft, isUploading, onRetake, onConfirm, onDiscard }) {
  if (!draft?.previewUrl) return null
  return (
    <div className="rz-camera-review" data-testid="kassa-camera-review" style={{ display: 'grid', gap: '16px' }}>
      <div style={{ display: 'grid', gap: '8px' }}>
        <div style={{ fontWeight: 700, fontSize: '20px' }}>Controleer de foto</div>
        <div style={{ color: '#667085' }}>Deze foto wordt bij bevestigen als kassabon geüpload.</div>
      </div>
      <div style={{ border: '1px solid #d0d5dd', borderRadius: '16px', padding: '16px', background: '#fff' }}>
        <img
          src={draft.previewUrl}
          alt="Concept kassabon"
          style={{ display: 'block', width: '100%', maxHeight: '70vh', objectFit: 'contain', borderRadius: '8px', background: '#f8fafc' }}
        />
      </div>
      <div className="rz-stock-table-actions" style={{ justifyContent: 'flex-start', gap: '12px', flexWrap: 'wrap' }}>
        <Button type="button" variant="secondary" onClick={onDiscard} disabled={isUploading} data-testid="kassa-camera-discard">Annuleren</Button>
        <Button type="button" variant="secondary" onClick={onRetake} disabled={isUploading} data-testid="kassa-camera-retake">Opnieuw</Button>
        <Button type="button" variant="primary" onClick={onConfirm} disabled={isUploading} data-testid="kassa-camera-confirm">{isUploading ? 'Opslaan…' : 'Bevestigen'}</Button>
      </div>
    </div>
  )
}


function ReceiptUploadInputs {