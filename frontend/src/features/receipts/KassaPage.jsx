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

function dispatchKassaMelding(type, message, title = '') {
  const text = String(message || '').trim()
  if (!text || typeof window === 'undefined') return
  window.dispatchEvent(new CustomEvent('rezzerv:melding', {
    detail: {
      type,
      title,
      message: text,
    },
  }))
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

  const response = await fetch('/api/receipts/share/upload', {
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


async function readSharedFileFromLaunchQueue() {
  if (!('launchQueue' in window) || !('files' in LaunchParams.prototype)) return null
  return new Promise((resolve) => {
    let settled = false
    window.launchQueue.setConsumer(async (launchParams) => {
      if (settled) return
      settled = true
      const fileHandle = launchParams.files?.[0]
      if (!fileHandle) return resolve(null)
      try {
        const file = await fileHandle.getFile()
        resolve(file)
      } catch {
        resolve(null)
      }
    })
    window.setTimeout(() => {
      if (!settled) resolve(null)
    }, 1000)
  })
}


function readShareQueryParams() {
  try {
    const params = new URLSearchParams(window.location.search)
    const shareStatus = params.get('share')
    if (!shareStatus) return null
    return {
      shareStatus,
      duplicate: params.get('duplicate') === '1',
      message: params.get('message') || '',
      receiptTableId: params.get('receiptTableId') || '',
      parseStatus: params.get('parseStatus') || '',
    }
  } catch {
    return null
  }
}


function clearShareQueryParams() {
  try {
    const url = new URL(window.location.href)
    for (const key of ['share', 'duplicate', 'message', 'receiptTableId', 'parseStatus']) url.searchParams.delete(key)
    window.history.replaceState({}, document.title, url.pathname + (url.search || '') + (url.hash || ''))
  } catch {
    // ignore cleanup errors
  }
}


function getReceiptLandingFileFromClipboardEvent(event) {
  const items = Array.from(event.clipboardData?.items || [])
  for (const item of items) {
    if (item.kind === 'file') {
      const file = item.getAsFile()
      if (file && isSupportedReceiptLandingFile(file)) return file
    }
  }
  return null
}

function isSupportedReceiptLandingFile(file) {
  if (!file) return false
  const name = String(file.name || '').toLowerCase()
  const type = String(file.type || '').toLowerCase()
  return (
    name.endsWith('.eml') ||
    name.endsWith('.pdf') ||
    name.endsWith('.zip') ||
    name.endsWith('.png') ||
    name.endsWith('.jpg') ||
    name.endsWith('.jpeg') ||
    name.endsWith('.webp') ||
    type === 'message/rfc822' ||
    type === 'application/pdf' ||
    type === 'application/zip' ||
    type === 'application/x-zip-compressed' ||
    type === 'image/png' ||
    type === 'image/jpeg' ||
    type === 'image/webp'
  )
}

function findSupportedReceiptLandingFile(fileList) {
  const files = Array.from(fileList || [])
  return files.find((file) => isSupportedReceiptLandingFile(file)) || null
}


async function fetchEmailRoute(householdId) {
  return fetchJson(`/api/receipts/email-route?householdId=${encodeURIComponent(householdId)}`)
}

async function copyTextToClipboard(text) {
  if (!text) return false
  try {
    await navigator.clipboard.writeText(text)
    return true
  } catch {
    return false
  }
}


async function uploadReceiptEmailFile(householdId, file) {
  const token = localStorage.getItem('rezzerv_token') || ''
  const formData = new FormData()
  formData.append('household_id', String(householdId))
  formData.append('file', file)

  const response = await fetch('/api/receipts/email/upload', {
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

function formatReceiptLineItemLabel(line) {
  const rawName = String(line.article_name || '').trim()
  if (!rawName) return '-'
  const name = rawName.replace(/\s+/g, ' ')
  const lowerName = name.toLowerCase()
  const quantity = Number(line.quantity ?? 1)
  const unit = String(line.unit || '').trim()
  const unitPrice = Number(line.unit_price ?? 0)
  const lineTotal = Number(line.line_total ?? 0)
  const firstValue = Number(line.value_1 ?? 0)
  const secondValue = Number(line.value_2 ?? 0)
  const source = String(line.source_text || '').trim()
  const piecesMatch = source.match(/\b(\d+(?:[,.]\d+)?)\s*[xX]\b/)
  const kiloMatch = source.match(/(\d+(?:[,.]\d+)?)\s*(kg|kilo)\b/i)
  const gramMatch = source.match(/(\d+(?:[,.]\d+)?)\s*g\b/i)
  const literMatch = source.match(/(\d+(?:[,.]\d+)?)\s*(l|ltr|liter)\b/i)
  const unitWeightMatch = source.match(/\b(\d+(?:[,.]\d+)?)\s*[xX]\s*(\d+(?:[,.]\d+)?)\s*(g|kg|ml|l)\b/i)
  const unitCountMatch = name.match(/\b(\d+)\s*[xX]\b/)
  const normalizedUnit = unit.toLowerCase()
  const formatCount = (value) => new Intl.NumberFormat('nl-NL', { maximumFractionDigits: 2 }).format(value)
  const formatWeight = (value, suffix) => `${new Intl.NumberFormat('nl-NL', { maximumFractionDigits: 3 }).format(value)} ${suffix}`

  if (unitWeightMatch) {
    const count = Number(unitWeightMatch[1].replace(',', '.'))
    const amount = Number(unitWeightMatch[2].replace(',', '.'))
    const suffix = unitWeightMatch[3].toLowerCase()
    if (Number.isFinite(count) && Number.isFinite(amount)) return `${formatCount(count)} × ${formatWeight(amount, suffix)}`
  }
  if (quantity > 1 && unit && normalizedUnit !== 'stuk' && normalizedUnit !== 'stuks') {
    if (normalizedUnit === 'kg' || normalizedUnit === 'g' || normalizedUnit === 'l' || normalizedUnit === 'ml') return `${formatCount(quantity)} ${unit}`
    return `${formatCount(quantity)} ${unit}`
  }
  if (piecesMatch) {
    const count = Number(piecesMatch[1].replace(',', '.'))
    if (Number.isFinite(count) && count > 1) return `${formatCount(count)} stuks`
  }
  if (unitCountMatch) {
    const count = Number(unitCountMatch[1])
    if (Number.isFinite(count) && count > 1) return `${formatCount(count)} stuks`
  }
  if (kiloMatch && !lowerName.includes('kilo')) {
    const amount = Number(kiloMatch[1].replace(',', '.'))
    if (Number.isFinite(amount)) return formatWeight(amount, 'kg')
  }
  if (gramMatch && !lowerName.includes('gram')) {
    const amount = Number(gramMatch[1].replace(',', '.'))
    if (Number.isFinite(amount)) return formatWeight(amount, 'g')
  }
  if (literMatch && !lowerName.includes('liter')) {
    const amount = Number(literMatch[1].replace(',', '.'))
    if (Number.isFinite(amount)) return formatWeight(amount, literMatch[2].toLowerCase().startsWith('l') ? 'l' : literMatch[2])
  }
  if (quantity > 1 && Math.abs(quantity - Math.round(quantity)) < 0.0001 && unitPrice && lineTotal && Math.abs(unitPrice * quantity - lineTotal) < 0.05) {
    return `${formatCount(quantity)} stuks`
  }
  if (firstValue > 0 && secondValue > 0 && Math.abs(firstValue * secondValue - lineTotal) < 0.05) {
    return `${formatCount(firstValue)} × ${formatMoney(secondValue)}`
  }
  return '1 stuk'
}

function ReceiptPreviewPanel({ preview }) {
  if (!preview) return null
  const previewState = preview?.preview || {}
  const kind = previewState.kind || preview.kind || ''
  const sourcePart = previewState.sourcePart || preview.sourcePart || ''
  const extractedText = previewState.text || ''
  const html = previewState.html || ''
  const originalUrl = preview.originalUrl || ''
  const processedUrl = preview.processedUrl || ''
  const isImage = kind === 'image'
  const isPdf = kind === 'pdf'
  const isEml = kind === 'eml'
  const isHtml = kind === 'html'
  const isText = kind === 'text'
  const viewerTitle = isPdf ? 'PDF-preview' : isImage ? 'Bonfoto' : isHtml ? 'HTML-weergave' : isText ? 'Tekstweergave' : 'Bestand'

  return (
    <ScreenCard fullWidth>
      <div style={{ display: 'grid', gap: '12px' }} data-testid="receipt-preview-panel">
        <div style={{ display: 'flex', justifyContent: 'space-between', gap: '12px', alignItems: 'flex-start', flexWrap: 'wrap' }}>
          <div>
            <h2 className="rz-modal-title" style={{ fontSize: '22px' }}>Ontvangen bestand</h2>
            <p className="rz-modal-text">Controleer de originele bron en de preprocessing voordat Rezzerv de bon definitief opslaat.</p>
          </div>
          <div style={{ display: 'grid', gap: '4px', justifyItems: 'end', color: '#667085', fontSize: '13px' }}>
            <div>{normalizeReceiptSourceLabel(preview.sourceLabel || preview.sourceContext)}</div>
            {sourcePart ? <div>{emailPartLabel(sourcePart)}</div> : null}
          </div>
        </div>

        <Tabs
          tabs={[
            {
              key: 'original',
              label: 'Origineel',
              content: (
                <div style={{ border: '1px solid #D0D5DD', borderRadius: '12px', background: '#F8FAFC', minHeight: '360px', overflow: 'auto' }}>
                  {isImage && originalUrl ? <img src={originalUrl} alt="Origineel ontvangen kassabonbestand" style={{ display: 'block', maxWidth: '100%', margin: '0 auto' }} /> : null}
                  {isPdf && originalUrl ? <iframe title="PDF-preview" src={originalUrl} style={{ width: '100%', height: '70vh', border: 0 }} /> : null}
                  {isHtml ? <iframe title="HTML-preview" srcDoc={html} sandbox="" style={{ width: '100%', height: '70vh', border: 0, background: '#fff' }} /> : null}
                  {isText ? <pre style={{ margin: 0, padding: '16px', whiteSpace: 'pre-wrap', wordBreak: 'break-word', fontFamily: 'inherit' }}>{extractedText}</pre> : null}
                  {!isImage && !isPdf && !isHtml && !isText ? <div style={{ padding: '16px', color: '#667085' }}>{viewerTitle} kan niet inline worden getoond.</div> : null}
                </div>
              ),
            },
            {
              key: 'processed',
              label: 'Voorbewerkt',
              content: (
                <div style={{ border: '1px solid #D0D5DD', borderRadius: '12px', background: '#F8FAFC', minHeight: '360px', overflow: 'auto' }}>
                  {isImage && processedUrl ? <img src={processedUrl} alt="Voorbewerkte kassabon" style={{ display: 'block', maxWidth: '100%', margin: '0 auto' }} /> : null}
                  {isPdf && processedUrl ? <iframe title="Voorbewerkte PDF" src={processedUrl} style={{ width: '100%', height: '70vh', border: 0 }} /> : null}
                  {isHtml ? <iframe title="Voorbewerkte HTML" srcDoc={html} sandbox="" style={{ width: '100%', height: '70vh', border: 0, background: '#fff' }} /> : null}
                  {isText ? <pre style={{ margin: 0, padding: '16px', whiteSpace: 'pre-wrap', wordBreak: 'break-word', fontFamily: 'inherit' }}>{extractedText}</pre> : null}
                  {!isImage && !isPdf && !isHtml && !isText ? <div style={{ padding: '16px', color: '#667085' }}>Voor dit bestandstype is geen voorbewerkte weergave beschikbaar.</div> : null}
                </div>
              ),
            },
          ]}
        />
      </div>
    </ScreenCard>
  )
}
