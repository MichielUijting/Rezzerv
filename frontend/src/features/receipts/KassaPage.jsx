import { useEffect, useLayoutEffect, useMemo, useRef, useState } from 'react'
import { useLocation, useNavigate } from 'react-router-dom'
import AppShell from '../../app/AppShell'
import ScreenCard from '../../ui/ScreenCard'
import Table from '../../ui/Table'
import DataTable from '../../ui/DataTable'
import Button from '../../ui/Button'
import Input from '../../ui/Input'
import Tabs from '../../ui/Tabs'
import { nextSortState, sortItems } from '../../ui/sorting'
import { buildTableWidth, ResizableHeaderCell, useResizableColumnWidths } from '../../ui/resizableTable.jsx'
import { fetchJson, normalizeErrorMessage } from '../stores/storeImportShared'
import useDismissOnComponentClick from '../../lib/useDismissOnComponentClick.js'
import ReceiptStatusBadge from '../kassa/components/ReceiptStatusBadge.jsx'
import { useAppFeedback } from '../../ui/AppFeedbackProvider.jsx'
import DetailInfoRow from '../kassa/components/DetailInfoRow.jsx'

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


function getDuplicateReceiptTableId(result) {
  return String(result?.existing_receipt?.receipt_table_id || result?.receipt_table_id || result?.receiptTableId || '')
}

function formatDuplicateImportMessageV2(result) {
  const existing = result?.existing_receipt || {}
  if (result?.duplicate_message) return String(result.duplicate_message)
  const filename = String(existing.original_filename || '').trim()
  const purchaseAt = existing.purchase_at ? formatDateTime(existing.purchase_at) : ''
  const total = existing.total_amount !== undefined && existing.total_amount !== null ? formatMoney(existing.total_amount, existing.currency || 'EUR') : ''
  const statusLabel = String(existing.po_norm_status_label || '').trim()
  const parts = ['Deze bon is al ingelezen']
  if (filename) parts.push(`als ${filename}`)
  if (purchaseAt) parts.push(`op ${purchaseAt}`)
  if (total && total !== '-') parts.push(`totaal ${total}`)
  if (statusLabel) parts.push(`status ${statusLabel}`)
  return `${parts.join(' ')}.`
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

// Kassa-inbox: de hoogte wordt in de browser gemeten op kop/filter plus exact tien bonregels.
// Daardoor blijft het aantal zichtbare regels stabiel, ook wanneer de werkelijke rijhoogte door de styleguide verandert.
const KASSA_INBOX_VISIBLE_ROW_COUNT = 10
const KASSA_INBOX_FALLBACK_SCROLL_HEIGHT_PX = 350
const RECEIPT_INBOX_AUTO_REFRESH_MS = 60000
const RECEIPT_DETAIL_PANEL_HEIGHT = 560
const RECEIPT_PREVIEW_ZOOM_MIN = 0.5
const RECEIPT_PREVIEW_ZOOM_MAX = 3
const RECEIPT_PREVIEW_ZOOM_STEP = 0.25

const RECEIPT_IMPORT_STEPS = [
  { key: 'preparing', label: 'Bestand voorbereiden' },
  { key: 'uploading', label: 'Bon versturen' },
  { key: 'processing', label: 'Bon verwerken' },
  { key: 'refreshing', label: 'Kassa bijwerken' },
  { key: 'ready', label: 'Gereed' },
]

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

function requirePoNormStatusLabel(item) {
  const label = String(item?.po_norm_status_label || '').trim()
  if (!label) return 'API-contractfout: po_norm_status_label ontbreekt'
  return label
}


function inboxStatusAccentColor(value) {
  if (value === 'Gecontroleerd') return '#12B76A'
  if (value === 'Controle nodig') return '#F79009'
  return '#B54708'
}


function createUploadTechnicalError(response, responseText, endpoint) {
  const contentType = response?.headers?.get?.('content-type') || ''
  const body = String(responseText || '').trim()
  const isHtml = /^<html[\s>]/i.test(body) || /^<!doctype\s+html/i.test(body)
  const detail = [
    `Endpoint: ${endpoint}`,
    `HTTP-status: ${response?.status || '-'}`,
    `StatusText: ${response?.statusText || '-'}`,
    `Content-Type: ${contentType || '-'}`,
    `Response-type: ${isHtml ? 'HTML in plaats van JSON' : 'niet-JSON of foutresponse'}`,
    '',
    body.slice(0, 4000) || '(lege response-body)',
  ].join('\n')
  return {
    userMessage: 'Upload mislukt. De server gaf een technische fout terug.',
    detail,
  }
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
    const error = new Error(normalizeErrorMessage(data?.detail || data || response.statusText))
    error.technicalUploadError = createUploadTechnicalError(response, responseText, '/api/receipts/import')
    throw error
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
    const error = new Error(normalizeErrorMessage(data?.detail || data || response.statusText))
    error.technicalUploadError = createUploadTechnicalError(response, responseText, '/api/receipts/import')
    throw error
  }
  return data
}



async function uploadPicnicEmailReceiptFile(householdId, emailFile) {
  const token = localStorage.getItem('rezzerv_token') || ''
  const formData = new FormData()
  formData.append('household_id', String(householdId))
  formData.append('email_file', emailFile)

  const response = await fetch('/api/receipts/picnic-email-import', {
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
    const error = new Error(normalizeErrorMessage(data?.detail || data || response.statusText))
    error.technicalUploadError = createUploadTechnicalError(response, responseText, '/api/receipts/picnic-email-import')
    throw error
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

async function fetchReceiptPreview(receiptTableId, variant = 'original') {
  const token = localStorage.getItem('rezzerv_token') || ''
  const params = new URLSearchParams()
  if (variant && variant !== 'original') params.set('variant', variant)
  const querySuffix = params.toString() ? `?${params.toString()}` : ''
  const response = await fetch(`/api/receipts/${encodeURIComponent(receiptTableId)}/preview${querySuffix}`, {
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
    throw new Error(normalizeErrorMessage(detail) || (variant === 'processed' ? 'Bewerkte bonpreview kon niet worden geladen.' : 'Preview van de originele bon kon niet worden geladen.'))
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

function buildTransientProcessedPreview(file) {
  return new Promise((resolve, reject) => {
    const reader = new FileReader()
    reader.onerror = () => reject(new Error('Preview van bewerkte bon kon niet worden opgebouwd.'))
    reader.onload = () => {
      const image = new Image()
      image.onload = () => {
        try {
          let width = Number(image.naturalWidth || image.width || 0)
          let height = Number(image.naturalHeight || image.height || 0)
          if (!width || !height) throw new Error('Afbeeldingsafmetingen ontbreken.')
          const canvas = document.createElement('canvas')
          const context = canvas.getContext('2d', { alpha: false })
          if (!context) throw new Error('Canvas context ontbreekt.')

          const shouldRotate = width > height
          canvas.width = shouldRotate ? height : width
          canvas.height = shouldRotate ? width : height
          context.fillStyle = '#ffffff'
          context.fillRect(0, 0, canvas.width, canvas.height)
          if (shouldRotate) {
            context.translate(canvas.width, 0)
            context.rotate(Math.PI / 2)
          }
          context.drawImage(image, 0, 0, width, height)
          if (shouldRotate) {
            context.setTransform(1, 0, 0, 1, 0, 0)
          }

          const frame = context.getImageData(0, 0, canvas.width, canvas.height)
          const pixels = frame.data
          for (let index = 0; index < pixels.length; index += 4) {
            const gray = Math.round((pixels[index] * 0.299) + (pixels[index + 1] * 0.587) + (pixels[index + 2] * 0.114))
            const threshold = gray > 168 ? 255 : 0
            pixels[index] = threshold
            pixels[index + 1] = threshold
            pixels[index + 2] = threshold
            pixels[index + 3] = 255
          }
          context.putImageData(frame, 0, 0)
          canvas.toBlob((blob) => {
            if (!blob) {
              reject(new Error('Preview van bewerkte bon kon niet worden opgebouwd.'))
              return
            }
            resolve(window.URL.createObjectURL(blob))
          }, 'image/png')
        } catch (error) {
          reject(error)
        }
      }
      image.onerror = () => reject(new Error('Afbeelding kon niet worden geladen voor preview.'))
      image.src = String(reader.result || '')
    }
    reader.readAsDataURL(file)
  })
}

async function createTransientReceiptPreview(file) {
  if (!file || !isSupportedReceiptImageFile(file)) return null
  const originalUrl = window.URL.createObjectURL(file)
  const processedUrl = await buildTransientProcessedPreview(file)
  return {
    originalUrl,
    processedUrl,
    filename: String(file.name || 'Kassabon'),
    isImage: true,
  }
}

function clearShareQueryParams() {
  try {
    const url = new URL(window.location.href)
    if (!url.searchParams.has('share_status')) return
    url.searchParams.delete('share_status')
    url.searchParams.delete('receipt_table_id')
    url.searchParams.delete('duplicate')
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
      message: params.get('message') || '',
    }
  } catch {
    return null
  }
}


function ReceiptPreviewCard({ receipt, transientPreview = null, isCollapsed, onToggleCollapse }) {
  const [selectedVariant, setSelectedVariant] = useState('original')
  const [previewState, setPreviewState] = useState({ status: 'idle', blobUrl: '', contentType: '', isPdf: false, isImage: false, isHtml: false, isText: false, textContent: '', error: '' })
  const [imageZoom, setImageZoom] = useState(1)
  const hasTransientPreview = Boolean(transientPreview?.originalUrl)
  const supportsProcessedPreview = hasTransientPreview || (receipt?.mime_type ? String(receipt.mime_type).toLowerCase().startsWith('image/') : false)
  const previewTitle = selectedVariant === 'processed' ? 'Bewerkte kassabon' : 'Originele kassabon'

  useEffect(() => {
    setSelectedVariant('original')
    setImageZoom(1)
  }, [receipt?.id, transientPreview?.originalUrl, transientPreview?.processedUrl])

  useEffect(() => {
    let cancelled = false
    let activeUrl = ''

    async function loadPreview() {
      if (hasTransientPreview) {
        const transientUrl = selectedVariant === 'processed' ? transientPreview?.processedUrl : transientPreview?.originalUrl
        if (!transientUrl) {
          setPreviewState({ status: 'error', blobUrl: '', contentType: '', isPdf: false, isImage: false, isHtml: false, isText: false, textContent: '', error: 'Bewerkte bonpreview is nog niet beschikbaar.' })
          return
        }
        setPreviewState({ status: 'ready', blobUrl: transientUrl, contentType: 'image/png', isPdf: false, isImage: true, isHtml: false, isText: false, textContent: '', error: '' })
        return
      }
      if (!receipt?.id) {
        setPreviewState({ status: 'idle', blobUrl: '', contentType: '', isPdf: false, isImage: false, isHtml: false, isText: false, textContent: '', error: '' })
        return
      }
      setPreviewState({ status: 'loading', blobUrl: '', contentType: '', isPdf: false, isImage: false, isHtml: false, isText: false, textContent: '', error: '' })
      try {
        const result = await fetchReceiptPreview(receipt.id, selectedVariant === 'processed' ? 'processed' : 'original')
        if (cancelled) {
          if (result.blobUrl) window.URL.revokeObjectURL(result.blobUrl)
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
      if (!hasTransientPreview && activeUrl) window.URL.revokeObjectURL(activeUrl)
    }
  }, [receipt?.id, receipt?.mime_type, selectedVariant, transientPreview?.originalUrl, transientPreview?.processedUrl, hasTransientPreview])

  function zoomReceiptImage(delta) {
    setImageZoom((current) => {
      const next = Math.round((Number(current || 1) + delta) * 100) / 100
      return Math.min(RECEIPT_PREVIEW_ZOOM_MAX, Math.max(RECEIPT_PREVIEW_ZOOM_MIN, next))
    })
  }

  const imageZoomPercent = Math.round(imageZoom * 100)

  return (
        <ScreenCard style={{
      height: 'calc(var(--rz-kassa-review-panel-height) + var(--rz-kassa-preview-card-overhead))',
      minHeight: 'calc(var(--rz-kassa-review-panel-height) + var(--rz-kassa-preview-card-overhead))',
    }}>
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
            aria-label="Kassabon uitklappen"
            title="Uitklappen"
            className="rz-expand-chip"
            style={{ width: '32px', height: '32px' }}
          >
            +
          </button>
        </div>
      ) : (
        <div style={{ display: 'grid', gap: '16px', height: '100%', gridTemplateRows: 'auto 1fr' }} data-testid="receipt-preview-card">
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', gap: '12px', flexWrap: 'wrap' }}>
            <div style={{ display: 'grid', gap: '8px' }}>
              <div style={{ fontWeight: 700, fontSize: '22px' }}>{previewTitle}</div>
              <div className="rz-stock-table-actions" style={{ justifyContent: 'flex-start', gap: '8px' }}>
                {previewState.status === 'ready' && previewState.isImage ? (
                  <div className="rz-kassa-preview-zoom-controls" aria-label="Zoom kassabonfoto">
                    <Button type="button" variant="secondary" onClick={() => zoomReceiptImage(-RECEIPT_PREVIEW_ZOOM_STEP)} disabled={imageZoom <= RECEIPT_PREVIEW_ZOOM_MIN} data-testid="receipt-preview-zoom-out">âˆ’</Button>
                    <span className="rz-kassa-preview-zoom-label" data-testid="receipt-preview-zoom-level">{imageZoomPercent}%</span>
                    <Button type="button" variant="secondary" onClick={() => zoomReceiptImage(RECEIPT_PREVIEW_ZOOM_STEP)} disabled={imageZoom >= RECEIPT_PREVIEW_ZOOM_MAX} data-testid="receipt-preview-zoom-in">+</Button>
                  </div>
                ) : null}
              </div>
            </div>
            <div className="rz-stock-table-actions" style={{ justifyContent: 'flex-start' }}>
              <button
                type="button"
                onClick={onToggleCollapse}
                data-testid="receipt-preview-toggle"
                aria-label="Kassabon inklappen"
                title="Inklappen"
                className="rz-expand-chip"
                style={{ width: '32px', height: '32px' }}
              >
                -
              </button>
            </div>
          </div>

          <div
            className={`rz-kassa-preview-viewport${previewState.isImage ? '' : ' rz-kassa-preview-viewport--plain'}`}
            data-testid="receipt-preview-viewport"
          >
            {previewState.status === 'loading' ? (
              <div style={{ color: '#475467', fontWeight: 600, padding: '16px' }}>Preview laden...</div>
            ) : null}

            {previewState.status === 'error' ? (
              <div style={{ maxWidth: '560px', margin: '16px' }}>
</div>
            ) : null}

            {previewState.status === 'ready' && previewState.isPdf ? (
              <object
                data={`${previewState.blobUrl}#toolbar=1&navpanes=0&scrollbar=1&zoom=page-width`}
                type="application/pdf"
                title={`Preview van bon ${receipt?.id || transientPreview?.filename || ''}`}
                style={{ display: 'block', width: '100%', height: '100%', minHeight: '100%', border: '0', background: '#fff' }}
                data-testid="receipt-preview-pdf"
              >
                <iframe
                  src={`${previewState.blobUrl}#toolbar=1&navpanes=0&scrollbar=1&zoom=page-width`}
                  title={`Preview van bon ${receipt?.id || transientPreview?.filename || ''}`}
                  style={{ display: 'block', width: '100%', height: '100%', minHeight: '100%', border: '0', background: '#fff' }}
                />
              </object>
            ) : null}

            {previewState.status === 'ready' && previewState.isImage ? (
              <img
                src={previewState.blobUrl}
                alt={selectedVariant === 'processed' ? 'Bewerkte kassabon' : 'Originele kassabon'}
                className="rz-kassa-preview-image"
                style={{ width: `${imageZoomPercent}%` }}
                data-testid="receipt-preview-image"
              />
            ) : null}

            {previewState.status === 'ready' && previewState.isHtml ? (
              <iframe
                srcDoc={previewState.textContent || '<p>Geen HTML-preview beschikbaar.</p>'}
                title={`HTML-preview van bon ${receipt?.id}`}
                style={{ display: 'block', width: '100%', height: '100%', minHeight: '100%', border: '0', background: '#fff' }}
                sandbox=""
                data-testid="receipt-preview-html"
              />
            ) : null}

            {previewState.status === 'ready' && previewState.isText ? (
              <pre
                style={{ width: '100%', minHeight: '100%', margin: 0, padding: '16px', whiteSpace: 'pre-wrap', wordBreak: 'break-word', background: '#fff', fontFamily: 'inherit', fontSize: '14px', lineHeight: 1.5 }}
                data-testid="receipt-preview-text"
              >
                {previewState.textContent || 'Geen tekstpreview beschikbaar.'}
              </pre>
            ) : null}

            {previewState.status === 'ready' && !previewState.isPdf && !previewState.isImage && !previewState.isHtml && !previewState.isText ? (
              <div style={{ maxWidth: '560px', margin: '16px' }}>
</div>
            ) : null}
          </div>
        </div>
      )}
    </ScreenCard>
  )
}

function ReceiptUploadProgressOverlay({ uploadProgress }) {
  if (!uploadProgress?.active) return null

  const percent = Math.max(5, Math.min(100, Math.round(Number(uploadProgress?.percent || 0))))
  const label = String(uploadProgress?.label || 'Kassabon verwerken...')
  const detail = String(uploadProgress?.detail || 'Rezzerv verwerkt je bestand.')
  const currentStepKey = String(uploadProgress?.stepKey || 'processing')
  const currentStepIndex = Math.max(0, RECEIPT_IMPORT_STEPS.findIndex((step) => step.key === currentStepKey))

  return (
    <div
      className="rz-modal-backdrop"
      role="dialog"
      aria-modal="true"
      aria-labelledby="kassa-upload-progress-title"
      aria-describedby="kassa-upload-progress-detail"
      data-testid="kassa-upload-progress-overlay"
      style={{ zIndex: 1200, padding: '20px' }}
    >
      <div className="rz-modal-card" style={{ width: 'min(560px, 100%)', display: 'grid', gap: '18px', padding: '24px' }}>
        <div style={{ display: 'grid', gap: '6px' }}>
          <h2 id="kassa-upload-progress-title" className="rz-modal-title" style={{ fontSize: '22px' }}>Bon verwerken</h2>
          <div style={{ color: '#344054', fontSize: '15px', fontWeight: 700 }}>{label}</div>
          <p id="kassa-upload-progress-detail" className="rz-modal-text">{detail}</p>
        </div>

        <div
          role="progressbar"
          aria-label="Voortgang kassabon verwerken"
          aria-valuemin={0}
          aria-valuemax={100}
          aria-valuenow={percent}
          data-testid="kassa-upload-progress"
          style={{ display: 'grid', gap: '8px' }}
        >
          <div style={{ height: '14px', borderRadius: '999px', overflow: 'hidden', background: '#EAECF0' }}>
            <div style={{ width: `${percent}%`, height: '100%', background: '#166534', transition: 'width 220ms ease' }} />
          </div>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', color: '#166534', fontSize: '14px', fontWeight: 700 }}>
            <span>Voortgang</span>
            <span data-testid="kassa-upload-progress-percent">{percent}%</span>
          </div>
        </div>

        <ol style={{ display: 'grid', gap: '10px', margin: 0, padding: 0, listStyle: 'none' }} aria-label="Stappen bij het verwerken van de kassabon">
          {RECEIPT_IMPORT_STEPS.map((step, index) => {
            const isComplete = index < currentStepIndex || (step.key === 'ready' && percent >= 100)
            const isCurrent = index === currentStepIndex && !isComplete
            return (
              <li key={step.key} style={{ display: 'flex', alignItems: 'center', gap: '10px', color: isComplete || isCurrent ? '#166534' : '#667085', fontWeight: isCurrent ? 700 : 400 }}>
                <span
                  aria-hidden="true"
                  style={{
                    width: '22px',
                    height: '22px',
                    borderRadius: '50%',
                    display: 'inline-flex',
                    alignItems: 'center',
                    justifyContent: 'center',
                    flex: '0 0 22px',
                    border: isComplete || isCurrent ? '1px solid #166534' : '1px solid #D0D5DD',
                    background: isComplete ? '#166534' : isCurrent ? '#FFFFFF' : '#FFFFFF',
                    color: isComplete ? '#FFFFFF' : '#667085',
                    fontSize: '13px',
                    fontWeight: 800,
                  }}
                >
                  {isComplete ? 'âœ“' : index + 1}
                </span>
                <span>{step.label}</span>
                {isCurrent ? <span style={{ marginLeft: 'auto', fontSize: '13px', color: '#166534' }}>Bezig</span> : null}
              </li>
            )
          })}
        </ol>
      </div>
    </div>
  )
}

function ReceiptProcessingInfoCard({ transientPreview }) {
  return (
    <ScreenCard fullWidth>
      <div style={{ display: 'grid', gap: '18px' }}>
        <div>
          <div style={{ fontWeight: 700, fontSize: '24px' }}>OCR-voorbereiding</div>
          <div style={{ color: '#667085', marginTop: '4px' }}>
            Rezzerv verwerkt deze bon nu en zet daarna de detailweergave klaar.
          </div>
        </div>

        <div style={{ display: 'grid', gap: '12px', gridTemplateColumns: 'repeat(auto-fit, minmax(220px, 1fr))' }}>
          <DetailInfoRow label="Bestand" value={transientPreview?.filename || '-'} />
          <DetailInfoRow label="Weergaven" value="Origineel / Bewerkt" />
        </div>
</div>
    </ScreenCard>
  )
}

function ReceiptDetailInfoCard({ receipt, canEdit = false, onReceiptUpdated, onFeedback }) {
  const [selectedLineIds, setSelectedLineIds] = useState([])
  const [lineSort, setLineSort] = useState({ key: 'lineIndex', direction: 'asc' })
  const [lineFilters, setLineFilters] = useState({ article: '', quantity: '', unit: '', unitPrice: '', lineTotal: '', discount: '' })
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
  const lineFieldInitialValueRef = useRef(new Map())
  const lineFieldDirtyRef = useRef(new Set())
  const [isAddingLine, setIsAddingLine] = useState(false)
  const [newLineDraft, setNewLineDraft] = useState({ article_name: '', quantity: 1, unit: '', unit_price: '', line_total: '' })

  useEffect(() => {
    setSelectedLineIds([])
    setLineFilters({ article: '', quantity: '', unit: '', unitPrice: '', lineTotal: '', discount: '' })
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
        article_name: line?.normalized_label ?? line?.display_label ?? line?.corrected_raw_label ?? line?.raw_label ?? '',
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
    lineIndex: (line) => Number(line?.line_index ?? 0),
    article: (line) => lineDrafts[line.id]?.article_name || line?.normalized_label || line?.display_label || line?.raw_label || '',
    quantity: (line) => Number(lineDrafts[line.id]?.quantity ?? line?.display_quantity ?? line?.quantity ?? 0),
    unit: (line) => lineDrafts[line.id]?.unit || line?.display_unit || line?.unit || '',
    unitPrice: (line) => Number(lineDrafts[line.id]?.unit_price ?? line?.display_unit_price ?? line?.unit_price ?? 0),
    lineTotal: (line) => Number(lineDrafts[line.id]?.line_total ?? line?.display_line_total ?? line?.line_total ?? 0),
    discount: (line) => Number(line?.discount_amount ?? 0),
  }), [lines, lineSort, lineDrafts])

  const allSelected = lines.length > 0 && lines.every((line) => selectedLineIds.includes(line.id))
  const visibleLineTotalSum = lines.reduce((sum, line) => {
    const value = Number(lineDrafts[line.id]?.line_total ?? line?.display_line_total ?? line?.line_total)
    return Number.isFinite(value) ? sum + value : sum
  }, 0)
  const visibleDiscountSum = lines.reduce((sum, line) => {
    const value = Number(line?.discount_amount)
    return Number.isFinite(value) ? sum + value : sum
  }, 0)
  const receiptLevelDiscount = Number(receipt?.discount_total_effective ?? receipt?.discount_total ?? 0)
  const effectiveLineDiscountTotal = Number.isFinite(visibleDiscountSum) ? visibleDiscountSum : 0
  const effectiveReceiptLevelDiscount = Number.isFinite(receiptLevelDiscount) ? receiptLevelDiscount : 0
  const effectiveDiscountTotal = effectiveLineDiscountTotal + effectiveReceiptLevelDiscount
  const visibleNetTotalSum = visibleLineTotalSum + effectiveDiscountTotal
  const poNormStatusLabel = String(receipt?.po_norm_status_label ?? receipt?.status_label ?? receipt?.norm_status_label ?? '').trim().toLowerCase()
  const isPoNormControlled = poNormStatusLabel === 'gecontroleerd'
  const detailAmountsMatch = Number.isFinite(Number(headerDraft.total_amount)) && lines.length > 0 && Math.abs(Number(headerDraft.total_amount) - visibleNetTotalSum) < 0.01
  const detailAmountsAccepted = detailAmountsMatch || isPoNormControlled
  const totalsMismatchWarningVisible = !detailAmountsAccepted && Number.isFinite(Number(headerDraft.total_amount)) && lines.length > 0
  const branchParts = deriveBranchAddressPlace(receipt)
  const receiptLineDataTableColumns = useMemo(() => receiptLineTableColumns.map((column) => {
    if (column.key === 'select') {
      return {
        ...column,
        header: <input type="checkbox" checked={allSelected} onChange={toggleAll} aria-label="Selecteer alle bonregels" />,
      }
    }

    const labels = {
      article: 'Artikel in bon',
      quantity: 'Aantal',
      unit: 'Eenheid',
      unitPrice: 'Stukprijs',
      lineTotal: 'Regelbedrag',
      discount: 'Korting',
    }

    const filterLabels = {
      article: 'Filter op artikel in bon',
      quantity: 'Filter op aantal',
      unit: 'Filter op eenheid',
      unitPrice: 'Filter op stukprijs',
      lineTotal: 'Filter op regelbedrag',
      discount: 'Filter op korting',
    }

    return {
      ...column,
      label: labels[column.key] || column.label || column.key,
      align: ['quantity', 'unitPrice', 'lineTotal', 'discount'].includes(column.key) ? 'right' : undefined,
      sortable: true,
      filterable: true,
      filterLabel: filterLabels[column.key],
      getSortValue: (line) => {
        if (column.key === 'article') return lineDrafts[line.id]?.article_name || line?.normalized_label || line?.display_label || line?.raw_label || ''
        if (column.key === 'quantity') return Number(lineDrafts[line.id]?.quantity ?? line?.display_quantity ?? line?.quantity ?? 0)
        if (column.key === 'unit') return lineDrafts[line.id]?.unit || line?.display_unit || line?.unit || ''
        if (column.key === 'unitPrice') return Number(lineDrafts[line.id]?.unit_price ?? line?.display_unit_price ?? line?.unit_price ?? 0)
        if (column.key === 'lineTotal') return Number(lineDrafts[line.id]?.line_total ?? line?.display_line_total ?? line?.line_total ?? 0)
        if (column.key === 'discount') return Number(line?.discount_amount ?? 0)
        return ''
      },
      getFilterValue: (line) => {
        if (column.key === 'article') return lineDrafts[line.id]?.article_name || line?.normalized_label || line?.display_label || line?.raw_label || ''
        if (column.key === 'quantity') return lineDrafts[line.id]?.quantity ?? line?.display_quantity ?? line?.quantity ?? ''
        if (column.key === 'unit') return lineDrafts[line.id]?.unit || line?.display_unit || line?.unit || ''
        if (column.key === 'unitPrice') return lineDrafts[line.id]?.unit_price ?? line?.display_unit_price ?? line?.unit_price ?? ''
        if (column.key === 'lineTotal') return lineDrafts[line.id]?.line_total ?? line?.display_line_total ?? line?.line_total ?? ''
        if (column.key === 'discount') return line?.discount_amount ?? ''
        return ''
      },
    }
  }), [allSelected, lineDrafts])

  function handleLineFilterChange(key, value) {
    setLineFilters((current) => ({ ...current, [key]: value }))
  }

  function toggleLine(lineId) {
    setSelectedLineIds((current) => (current.includes(lineId) ? current.filter((id) => id !== lineId) : [...current, lineId]))
  }

  function toggleAll() {
    setSelectedLineIds(allSelected ? [] : lines.map((line) => line.id))
  }

  function lineFieldKey(lineId, fieldName) {
    return `${String(lineId)}::${String(fieldName)}`
  }

  function normalizeLineInputValue(fieldName, value) {
    if (fieldName === 'quantity' || fieldName === 'unit_price' || fieldName === 'line_total') {
      const rawValue = String(value ?? '').trim()
      if (!rawValue) return ''
      const numberValue = Number(rawValue)
      return Number.isFinite(numberValue) ? String(numberValue) : rawValue
    }
    return String(value ?? '')
  }

  function rememberLineFieldValue(lineId, fieldName, value) {
    const key = lineFieldKey(lineId, fieldName)
    lineFieldInitialValueRef.current.set(key, normalizeLineInputValue(fieldName, value))
    lineFieldDirtyRef.current.delete(key)
  }

  function updateLineDraft(lineId, field, value) {
    const key = lineFieldKey(lineId, field)
    const nextValue = normalizeLineInputValue(field, value)

    if (!lineFieldInitialValueRef.current.has(key)) {
      lineFieldInitialValueRef.current.set(key, nextValue)
    }

    const initialValue = lineFieldInitialValueRef.current.get(key)
    if (initialValue === nextValue) {
      lineFieldDirtyRef.current.delete(key)
    } else {
      lineFieldDirtyRef.current.add(key)
    }

    setLineDrafts((current) => ({ ...current, [lineId]: { ...(current[lineId] || {}), [field]: value } }))
  }

  function saveLineFieldOnBlur(lineId, fieldName, value) {
    const key = lineFieldKey(lineId, fieldName)
    const isDirty = lineFieldDirtyRef.current.has(key)

    lineFieldDirtyRef.current.delete(key)
    lineFieldInitialValueRef.current.delete(key)

    if (!isDirty) return

    saveLine(lineId, { [fieldName]: value })
  }

  function normalizePurchaseDateInput(value) {
    const rawValue = String(value || '').trim()
    if (!rawValue) return ''
    return rawValue.slice(0, 10)
  }

  async function persistHeaderDraft({ suppressSuccessFeedback = false } = {}) {
    const normalizedStoreName = String(headerDraft.store_name || '').trim()
    const normalizedPurchaseAt = normalizePurchaseDateInput(headerDraft.purchase_at)
    const payload = {
      store_name: normalizedStoreName,
      purchase_at: normalizedPurchaseAt,
      total_amount: headerDraft.total_amount === '' ? null : Number(headerDraft.total_amount),
      reference: headerDraft.reference,
      notes: headerDraft.notes,
    }
    const updated = await fetchJson(`/api/receipts/${encodeURIComponent(receipt.id)}`, {
      method: 'PATCH',
      body: JSON.stringify(payload),
    })
    onReceiptUpdated?.(updated)
    if (!suppressSuccessFeedback) onFeedback?.('success', 'Bonkop opgeslagen.')
    return updated
  }

  async function saveHeaderFieldOnBlur(fieldName) {
    if (!canEdit || isSavingHeader) return

    const currentValue = fieldName === 'purchase_at'
      ? normalizePurchaseDateInput(receipt?.purchase_at)
      : String(receipt?.[fieldName] || '').trim()

    const nextValue = fieldName === 'purchase_at'
      ? normalizePurchaseDateInput(headerDraft.purchase_at)
      : String(headerDraft[fieldName] || '').trim()

    if (currentValue === nextValue) return

    setIsSavingHeader(true)

    try {
      await persistHeaderDraft({ suppressSuccessFeedback: true })

      const fieldLabel = fieldName === 'purchase_at'
        ? 'Aankoopdatum'
        : 'Winkel'

      onFeedback?.(
        'success',
        `${fieldLabel} is opgeslagen en bijgewerkt in de hoofdtabel.`,
        { key: `receipt-header-${fieldName}-saved-${String(receipt?.id || '')}` },
      )
    } catch (err) {
      onFeedback?.(
        'error',
        normalizeErrorMessage(err?.message)
          || `${fieldName === 'purchase_at' ? 'Aankoopdatum' : 'Winkel'} kon niet worden opgeslagen.`,
      )
    } finally {
      setIsSavingHeader(false)
    }
  }

async function saveLine(lineId, overrides = null) {
    if (!canEdit) return
    const draft = { ...(lineDrafts[lineId] || {}), ...(overrides || {}) }
    try {
      const updated = await fetchJson(`/api/receipts/${encodeURIComponent(receipt.id)}/lines/${encodeURIComponent(lineId)}`, {
        method: 'PATCH',
        body: JSON.stringify({
          article_name: draft.article_name,
          quantity: draft.quantity === '' ? null : Number(draft.quantity),
          unit: draft.unit,
          unit_price: draft.unit_price === '' ? null : Number(draft.unit_price),
          line_total: draft.line_total === '' ? null : Number(draft.line_total),
          is_validated: Boolean(draft.is_validated),
          is_deleted: Boolean(draft.is_deleted),
        }),
      })
      onReceiptUpdated?.(updated)
      if (updated?.mutation_status !== 'unchanged') {
        onFeedback?.('success', updated?.mutation_message || 'Wijziging verwerkt.', { key: `receipt-line-saved-${String(lineId)}` })
      }
    } catch (err) {
      onFeedback?.('error', normalizeErrorMessage(err?.message) || 'Bonregel kon niet worden opgeslagen.')
    }
  }


  async function deleteSelectedLines() {
    if (!canEdit || selectedLineIds.length === 0) return
    try {
      let updated = null
      for (const lineId of selectedLineIds) {
        updated = await fetchJson(`/api/receipts/${encodeURIComponent(receipt.id)}/lines/${encodeURIComponent(lineId)}`, {
          method: 'PATCH',
          body: JSON.stringify({ ...(lineDrafts[lineId] || {}), is_deleted: true }),
        })
      }
      if (updated) onReceiptUpdated?.(updated)
      setSelectedLineIds([])
      onFeedback?.('success', 'Geselecteerde bonregels verwijderd.')
    } catch (err) {
      onFeedback?.('error', normalizeErrorMessage(err?.message) || 'Bonregels konden niet worden verwijderd.')
    }
  }

  async function addLine() {
    if (!canEdit) return
    if (!isAddingLine) {
      setIsAddingLine(true)
      return
    }
    if (!String(newLineDraft.article_name || '').trim()) {
      onFeedback?.('warning', 'Vul eerst een artikelnaam in voor de nieuwe bonregel.')
      return
    }
    try {
      const updated = await fetchJson(`/api/receipts/${encodeURIComponent(receipt.id)}/lines`, {
        method: 'POST',
        body: JSON.stringify({
          article_name: newLineDraft.article_name,
          quantity: newLineDraft.quantity === '' ? 1 : Number(newLineDraft.quantity),
          unit: newLineDraft.unit,
          unit_price: newLineDraft.unit_price === '' ? null : Number(newLineDraft.unit_price),
          line_total: newLineDraft.line_total === '' ? null : Number(newLineDraft.line_total),
          is_validated: true,
        }),
      })
      onReceiptUpdated?.(updated)
      setIsAddingLine(true)
      setNewLineDraft({ article_name: '', quantity: 1, unit: '', unit_price: '', line_total: '' })
      onFeedback?.('success', 'Bonregel toegevoegd.')
    } catch (err) {
      onFeedback?.('error', normalizeErrorMessage(err?.message) || 'Bonregel kon niet worden toegevoegd.')
    }
  }

  async function approveReceipt() {
    if (!canEdit) return
    const normalizedStoreName = String(headerDraft.store_name || '').trim()
    const normalizedPurchaseAt = String(headerDraft.purchase_at || '').trim()
    if (!normalizedStoreName) {
      onFeedback?.('error', 'Vul eerst de winkel in voordat je de bon goedkeurt.')
      return
    }
    if (!normalizedPurchaseAt) {
      onFeedback?.('error', 'Vul eerst de aankoopdatum in voordat je de bon goedkeurt.')
      return
    }
    setIsApproving(true)
    try {
      const receiptStoreName = String(receipt?.store_name || '').trim()
      const receiptPurchaseAt = String(receipt?.purchase_at || '').trim()
      const receiptReference = String(receipt?.reference || '')
      const receiptNotes = String(receipt?.notes || '')
      const receiptTotalAmount = receipt?.total_amount === null || receipt?.total_amount === undefined || receipt?.total_amount === ''
        ? ''
        : String(receipt.total_amount)
      const draftTotalAmount = headerDraft.total_amount === null || headerDraft.total_amount === undefined ? '' : String(headerDraft.total_amount)
      const headerChanged = (
        normalizedStoreName !== receiptStoreName
        || normalizedPurchaseAt !== receiptPurchaseAt
        || draftTotalAmount !== receiptTotalAmount
        || String(headerDraft.reference || '') !== receiptReference
        || String(headerDraft.notes || '') !== receiptNotes
      )
      if (headerChanged) {
        await persistHeaderDraft({ suppressSuccessFeedback: true })
      }
      const updated = await fetchJson(`/api/receipts/${encodeURIComponent(receipt.id)}/approve`, { method: 'POST' })
      onReceiptUpdated?.(updated)
      onFeedback?.('success', 'Bon is goedgekeurd voor Uitpakken.')
    } catch (err) {
      onFeedback?.('error', normalizeErrorMessage(err?.message) || 'Bon kon niet worden goedgekeurd.')
    } finally {
      setIsApproving(false)
    }
  }

  function exportSelected() {
    const selectedSet = new Set(selectedLineIds)
    const exportLines = lines.filter((line) => selectedSet.has(line.id))
    const rows = exportLines.map((line) => {
      const draft = lineDrafts[line.id] || {}
      return [draft.article_name || line.normalized_label || line.display_label || line.raw_label || '', draft.quantity ?? '', draft.unit || '', draft.unit_price ?? '', draft.line_total ?? '', line.discount_amount ?? '', line.barcode || '']
    })
    const csv = [['Artikel in bon', 'Aantal', 'Eenheid', 'Stukprijs', 'Regelbedrag', 'Korting', 'Barcode'], ...rows].map((row) => row.map((value) => `"${String(value ?? '').replace(/"/g, '""')}"`).join(';')).join('\n')
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

  async function downloadParsingDebug(event) {
    event?.preventDefault?.()
    event?.stopPropagation?.()
    const receiptId = String(receipt?.id || '')
    if (!receiptId) return
    try {
      const token = localStorage.getItem('rezzerv_token') || ''
      const response = await fetch(`/api/receipts/${encodeURIComponent(receiptId)}/debug-export`, {
        headers: token ? { Authorization: `Bearer ${token}` } : {},
        credentials: 'include',
      })
      if (!response.ok) {
        let message = 'Parsing-debug kon niet worden gedownload.'
        try {
          const payload = await response.json()
          if (payload?.detail) message = String(payload.detail)
        } catch {}
        throw new Error(message)
      }
      const payload = await response.json()
      const debugReceiptId = String(payload?.receipt?.id || receiptId)
      const json = JSON.stringify(payload, null, 2)
      const downloadFilename = `rezzerv-kassa-debug-${debugReceiptId}.json`
      window.__rezzervLastDownload = {
        filename: downloadFilename,
        source: 'receipt-debug',
        receiptId: debugReceiptId,
        requestedReceiptId: receiptId,
        json,
      }
      const blob = new Blob([json], { type: 'application/json;charset=utf-8;' })
      const url = window.URL.createObjectURL(blob)
      const link = document.createElement('a')
      link.href = url
      link.download = downloadFilename
      document.body.appendChild(link)
      link.click()
      link.remove()
      window.URL.revokeObjectURL(url)
      onFeedback?.('success', 'Parsing-debug is gedownload.')
    } catch (err) {
      onFeedback?.('error', normalizeErrorMessage(err?.message) || 'Parsing-debug kon niet worden gedownload.')
    }
  }

  return (
    <ScreenCard style={{ minHeight: `${RECEIPT_DETAIL_PANEL_HEIGHT}px`, overflow: 'visible' }}>
      <div data-testid="receipt-detail-page" style={{ display: 'grid', gap: '16px', minHeight: 0, overflow: 'visible' }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', gap: '12px', flexWrap: 'wrap' }}>
          <div>
            <div style={{ fontWeight: 700, fontSize: '24px' }} data-testid="receipt-detail-title">{receipt?.store_name || 'Kassabon'}</div>
            <div style={{ color: detailAmountsAccepted ? '#027A48' : '#B54708', fontWeight: 600 }}>{detailAmountsAccepted ? 'Bonbedragen sluiten aan' : 'Totaalbedrag wijkt af van de bonregels'}</div>
            {totalsMismatchWarningVisible ? <div style={{ color: '#B54708', fontSize: 13 }}>Je kunt deze afwijking overrulen via 'Goedkeuren'. De bon gaat dan naar Gecontroleerd.</div> : null}
          </div>
          {canEdit ? (
            <div style={{ display: 'flex', gap: '8px', flexWrap: 'wrap' }}>
              
              
              
            </div>
          ) : null}
        </div>

        <Tabs tabs={['Bonregels', 'Bonkop', 'Bron']} defaultTab="Bonregels" activeColor={detailAmountsAccepted ? '#166534' : '#B54708'}>
          {(activeTab) => {
            if (activeTab === 'Bonkop') {
              return (
                <div style={{ display: 'grid', gap: '12px', gridTemplateColumns: 'repeat(auto-fit, minmax(220px, 1fr))' }}>
                  {canEdit ? (
                    <>
                      <Input
                        label="Winkel"
                        value={headerDraft.store_name}
                        disabled={isSavingHeader}
                        onChange={(event) => setHeaderDraft((current) => ({ ...current, store_name: event.target.value }))}
                        onBlur={() => saveHeaderFieldOnBlur('store_name')}
                      />
                      <Input
                        label="Aankoopdatum"
                        type="date"
                        value={normalizePurchaseDateInput(headerDraft.purchase_at)}
                        disabled={isSavingHeader}
                        onChange={(event) => setHeaderDraft((current) => ({ ...current, purchase_at: event.target.value }))}
                        onBlur={() => saveHeaderFieldOnBlur('purchase_at')}
                      />
                      <Input label="Totaalbedrag" type="number" step="0.01" value={headerDraft.total_amount} onChange={(event) => setHeaderDraft((current) => ({ ...current, total_amount: event.target.value }))} />
                      <Input label="Referentie / bonnummer" value={headerDraft.reference} onChange={(event) => setHeaderDraft((current) => ({ ...current, reference: event.target.value }))} />
                      <Input label="Notitie" value={headerDraft.notes} onChange={(event) => setHeaderDraft((current) => ({ ...current, notes: event.target.value }))} />
                    </>
                  ) : (
                    <>
                      <DetailInfoRow label="Winkel" value={receipt?.store_name} />
                      <DetailInfoRow label="Aankoopdatum" value={formatDateTime(receipt?.purchase_at)} />
                      <DetailInfoRow label="Totaal" value={formatMoney(receipt?.total_amount, receipt?.currency)} />
                      <DetailInfoRow label="Referentie / bonnummer" value={receipt?.reference} />
                      <DetailInfoRow label="Notitie" value={receipt?.notes} />
                    </>
                  )}
                  <DetailInfoRow label="Adres" value={branchParts.address} />
                  <DetailInfoRow label="Plaats" value={branchParts.city} />
                  <DetailInfoRow label="Som bonregels" value={formatMoney(visibleLineTotalSum, receipt?.currency)} />
                  <DetailInfoRow label="Regelkortingen" value={formatMoney(effectiveLineDiscountTotal, receipt?.currency)} />
                  <DetailInfoRow label="Boncorrectie" value={formatMoney(effectiveReceiptLevelDiscount, receipt?.currency)} />
                  <DetailInfoRow label="Netto bonregels" value={formatMoney(visibleNetTotalSum, receipt?.currency)} />
                  <DetailInfoRow label="Valuta" value={receipt?.currency || 'EUR'} />
                  <DetailInfoRow label="Regels" value={String(lines.length)} />
                </div>
              )
            }
            if (activeTab === 'Bron') {
              return (
                <div style={{ display: 'grid', gap: '12px', gridTemplateColumns: 'repeat(auto-fit, minmax(220px, 1fr))' }}>
                  <DetailInfoRow label="Bron" value={normalizeReceiptSourceLabel(receipt?.source_label)} />
                  <DetailInfoRow label="Adres" value={branchParts.address} />
                  <DetailInfoRow label="Plaats" value={branchParts.city} />
                  <DetailInfoRow label="Oorspronkelijk bestand" value={receipt?.original_filename || 'Niet beschikbaar in deze release'} />
                  <DetailInfoRow label="Bestandstype" value={receipt?.mime_type || 'Niet beschikbaar in deze release'} />
                  <DetailInfoRow label="GeÃ¯mporteerd op" value={formatDateTime(receipt?.imported_at || receipt?.created_at)} />
                  <DetailInfoRow label="Aangemaakt op" value={formatDateTime(receipt?.created_at)} />
                  <DetailInfoRow label="Bijgewerkt op" value={formatDateTime(receipt?.updated_at)} />
                  <DetailInfoRow label="Goedgekeurd op" value={formatDateTime(receipt?.approved_at)} />
                  <DetailInfoRow label="Goedgekeurd door" value={receipt?.approved_by_user_email} />
                  {receipt?.totals_overridden ? <DetailInfoRow label="Override totaalafwijking" value={`Ja${receipt?.totals_override_by_user_email ? ` Â· ${receipt.totals_override_by_user_email}` : ''}${receipt?.totals_override_at ? ` Â· ${formatDateTime(receipt.totals_override_at)}` : ''}`} /> : null}
                </div>
              )
            }
            return (
              <div style={{ display: 'grid', gap: '12px' }}>
                <DataTable
                  columns={receiptLineDataTableColumns}
                  data={lines}
                  getRowKey={(line) => line.id}
                  wrapperClassName="rz-receipt-lines-table-wrapper"
                  tableClassName="rz-receipt-lines-table"
                  dataTestId="receipt-lines-table"
                  defaultSort={{ key: 'lineIndex', direction: 'asc' }}
                  sortState={lineSort}
                  onSortChange={setLineSort}
                  filterState={lineFilters}
                  onFilterChange={handleLineFilterChange}
                  emptyMessage="Geen bonregels gevonden."
                  renderRow={(line) => {
                    const selected = selectedLineIds.includes(line.id)
                    const draft = lineDrafts[line.id] || {}
                    return (
                      <tr key={line.id} data-testid={`receipt-line-row-${line.id}`} className={selected ? 'rz-row-selected' : ''}>
                        <td><input type="checkbox" data-testid={`receipt-line-select-${line.id}`} checked={selected} onChange={() => toggleLine(line.id)} aria-label={`Selecteer regel ${draft.article_name || line.normalized_label || line.display_label || line.id}`} /></td>
                        <td>{canEdit ? <input className="rz-input" value={draft.article_name ?? ''} onFocus={(event) => rememberLineFieldValue(line.id, 'article_name', event.target.value)} onChange={(event) => updateLineDraft(line.id, 'article_name', event.target.value)} onBlur={(event) => saveLineFieldOnBlur(line.id, 'article_name', event.target.value)} /> : <span data-testid={`receipt-line-status-${line.id}`}>{draft.article_name || line.normalized_label || line.display_label || '-'}</span>}</td>
                        <td className="rz-num">{canEdit ? <input className="rz-input" type="number" step="0.001" value={draft.quantity ?? ''} onFocus={(event) => rememberLineFieldValue(line.id, 'quantity', event.target.value)} onChange={(event) => updateLineDraft(line.id, 'quantity', event.target.value)} onBlur={(event) => saveLineFieldOnBlur(line.id, 'quantity', event.target.value)} /> : formatQuantity(draft.quantity ?? line.display_quantity ?? line.quantity)}</td>
                        <td>{canEdit ? <input className="rz-input" value={draft.unit ?? ''} onFocus={(event) => rememberLineFieldValue(line.id, 'unit', event.target.value)} onChange={(event) => updateLineDraft(line.id, 'unit', event.target.value)} onBlur={(event) => saveLineFieldOnBlur(line.id, 'unit', event.target.value)} /> : (draft.unit || line.display_unit || '-')}</td>
                        <td className="rz-num">{canEdit ? <input className="rz-input" type="number" step="0.01" value={draft.unit_price ?? ''} onFocus={(event) => rememberLineFieldValue(line.id, 'unit_price', event.target.value)} onChange={(event) => updateLineDraft(line.id, 'unit_price', event.target.value)} onBlur={(event) => saveLineFieldOnBlur(line.id, 'unit_price', event.target.value)} /> : formatMoney(draft.unit_price ?? line.display_unit_price ?? line.unit_price, receipt?.currency)}</td>
                        <td className="rz-num">{canEdit ? <input className="rz-input" type="number" step="0.01" value={draft.line_total ?? ''} onFocus={(event) => rememberLineFieldValue(line.id, 'line_total', event.target.value)} onChange={(event) => updateLineDraft(line.id, 'line_total', event.target.value)} onBlur={(event) => saveLineFieldOnBlur(line.id, 'line_total', event.target.value)} /> : formatMoney(draft.line_total ?? line.display_line_total ?? line.line_total, receipt?.currency)}</td>
                        <td className="rz-num">{formatMoney(line.discount_amount, receipt?.currency)}</td>
                      </tr>
                    )
                  }}
                  renderBodyAppend={() => (
                    canEdit && isAddingLine ? (
                      <tr data-testid="receipt-line-row-new">
                        <td />
                        <td><input className="rz-input" value={newLineDraft.article_name} onChange={(event) => setNewLineDraft((current) => ({ ...current, article_name: event.target.value }))} placeholder="Nieuw artikel" /></td>
                        <td className="rz-num"><input className="rz-input" type="number" step="0.001" value={newLineDraft.quantity} onChange={(event) => setNewLineDraft((current) => ({ ...current, quantity: event.target.value }))} /></td>
                        <td><input className="rz-input" value={newLineDraft.unit} onChange={(event) => setNewLineDraft((current) => ({ ...current, unit: event.target.value }))} placeholder="st / kg / l" /></td>
                        <td className="rz-num"><input className="rz-input" type="number" step="0.01" value={newLineDraft.unit_price} onChange={(event) => setNewLineDraft((current) => ({ ...current, unit_price: event.target.value }))} /></td>
                        <td className="rz-num"><input className="rz-input" type="number" step="0.01" value={newLineDraft.line_total} onChange={(event) => setNewLineDraft((current) => ({ ...current, line_total: event.target.value }))} /></td>
                        <td />
                      </tr>
                    ) : null
                  )}
                  renderFooter={() => (
                    <tfoot>
                      <tr><td colSpan={5} style={{ fontWeight: 700 }}>Totaal bonregels</td><td className="rz-num" style={{ fontWeight: 700 }}>{formatMoney(visibleLineTotalSum, receipt?.currency)}</td><td className="rz-num" style={{ fontWeight: 700 }}>{formatMoney(effectiveLineDiscountTotal, receipt?.currency)}</td></tr>
                      <tr><td colSpan={5} style={{ fontWeight: 700 }}>Boncorrectie</td><td className="rz-num" style={{ fontWeight: 700 }}>-</td><td className="rz-num" style={{ fontWeight: 700 }}>{formatMoney(effectiveReceiptLevelDiscount, receipt?.currency)}</td></tr>
                      <tr><td colSpan={5} style={{ fontWeight: 700 }}>Netto bonregels</td><td className="rz-num" style={{ fontWeight: 700 }}>{formatMoney(visibleNetTotalSum, receipt?.currency)}</td><td className="rz-num" style={{ fontWeight: 700 }}>{formatMoney(headerDraft.total_amount, receipt?.currency)}</td></tr>
                    </tfoot>
                  )}
                />
                <div className="rz-stock-table-actions" style={{ justifyContent: 'flex-start', alignItems: 'center', gap: 12, flexWrap: 'wrap' }}>
                  {canEdit ? <Button type="button" variant="secondary" onClick={addLine}>{isAddingLine ? 'Nieuwe regel opslaan' : 'Toevoegen'}</Button> : null}
                  {canEdit ? <Button type="button" variant="secondary" onClick={deleteSelectedLines} disabled={selectedLineIds.length === 0}>Verwijderen</Button> : null}
                  <Button type="button" variant="secondary" onClick={exportSelected} disabled={selectedLineIds.length === 0} data-testid="receipt-export-button">Exporteren</Button>
                </div>
              <div className="rz-kassa-secondary-actions">
                <Button type="button" onClick={approveReceipt} disabled={isApproving}>{isApproving ? 'Goedkeuren...' : 'Goedkeuren'}</Button>
                <Button type="button" variant="secondary" onClick={downloadParsingDebug} data-testid="receipt-debug-download-button">JSON</Button>
              </div>
              </div>
            )
          }}
        </Tabs>
      </div>
    </ScreenCard>
  )
}

function ReceiptDetailView({ receipt = null, transientPreview = null, canEdit = false, onReceiptUpdated, onFeedback }) {
  const [isPreviewCollapsed, setIsPreviewCollapsed] = useState(false)

  useEffect(() => {
    setIsPreviewCollapsed(false)
  }, [receipt?.id, transientPreview?.originalUrl])

  return (
    <div
      style={{
        display: 'grid',
        gap: '16px',
        gridTemplateColumns: isPreviewCollapsed ? '44px minmax(0, 1fr)' : 'minmax(0, 1fr) minmax(0, 1fr)',
        alignItems: 'stretch',
        width: '100%',
        maxWidth: '900px',
        margin: '0 auto',
        minWidth: 0,
        overflow: 'visible',
      }}
    >
      <div style={{ minWidth: 0, width: '100%', overflow: 'visible', minHeight: `${RECEIPT_DETAIL_PANEL_HEIGHT}px` }}>
        <ReceiptPreviewCard
          receipt={receipt}
          transientPreview={transientPreview}
          isCollapsed={isPreviewCollapsed}
          onToggleCollapse={() => setIsPreviewCollapsed((current) => !current)}
        />
      </div>
      <div style={{ minWidth: 0, width: '100%', overflow: 'visible', minHeight: `${RECEIPT_DETAIL_PANEL_HEIGHT}px` }}>
        {receipt ? (
          <ReceiptDetailInfoCard receipt={receipt} canEdit={canEdit} onReceiptUpdated={onReceiptUpdated} onFeedback={onFeedback} />
        ) : (
          <ReceiptProcessingInfoCard transientPreview={transientPreview} />
        )}
      </div>
    </div>
  )
}

function ReceiptSourceHubContent({
  onChooseReceiptFile,
  onChooseCamera,
  onDropLandingFile,
  onCopyEmailRoute,
  emailRoute,
  isEmailRouteLoading,
  emailRouteError,
  feedbackMessage,
  feedbackVariant = 'success',
  isUploading,
  technicalUploadError,
  isTechnicalUploadErrorOpen = false,
  onToggleTechnicalUploadError,
  currentUserDisplayRole = 'viewer',
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
    ? 'Doorstuuradres laden...'
    : routeIsPublic && resendConfigured
      ? 'Automatische ontvangst mogelijk'
      : routeIsPublic
        ? 'Adres klaar, inbound nog niet actief'
        : 'Lokale demo-opstelling'
  return (
    <div style={{ display: 'grid', gap: '20px' }} data-testid="kassa-add-screen">
      {showHeading ? (
        <div>
          <h2 id="kassa-bronhub-title" className="rz-modal-title" style={{ fontSize: '22px' }}>Bon toevoegen</h2>
        </div>
      ) : null}

      <ScreenCard fullWidth>
          <div style={{ display: 'grid', gap: '18px' }}>
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
                Ondersteund in deze landingsplaats: <strong>.eml</strong>, <strong>.pdf</strong>, <strong>.zip</strong>, <strong>.png</strong>, <strong>.jpg</strong>, <strong>.jpeg</strong> en <strong>.webp</strong>.
              </div>
            </div>

            <div style={{ display: 'grid', gap: '10px', gridTemplateColumns: 'repeat(2, minmax(0, 1fr))', alignItems: 'stretch' }}>
              <Button type="button" variant="primary" onClick={onChooseReceiptFile} disabled={isUploading} data-testid="kassa-choose-file-button" style={{ width: '100%', fontSize: '14px', padding: '10px 12px', whiteSpace: 'nowrap' }}>Bestanden kiezen</Button>
              <Button type="button" variant="secondary" onClick={onChooseCamera} disabled={isUploading} data-testid="kassa-open-camera-button" style={{ width: '100%', fontSize: '14px', padding: '10px 12px', whiteSpace: 'nowrap' }}>Camera openen</Button>
            </div>
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
                  {isEmailRouteLoading ? 'E-mailroute laden...' : routeAddress}
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
              <div style={{ color: '#667085' }}>De schermopbouw is nu gericht op Ã©Ã©n centrale actie. De extra uitleg blijft zichtbaar, maar staat bewust lager op het scherm.</div>
              <div style={{ color: '#344054', fontSize: '14px', display: 'grid', gap: '6px' }}>
                <div><strong>.eml</strong> blijft via de bestaande e-mailimport lopen.</div>
                <div><strong>.pdf</strong>, <strong>.zip</strong> en ondersteunde afbeeldingsbestanden lopen via de bestaande bonbestand-import.</div>
                <div><strong>Slepen, plakken en kiezen via Verkenner</strong> komen hiermee samen in Ã©Ã©n centrale landingsroute.</div>
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
                title="Adres kopiÃƒÂ«ren wordt later weer geactiveerd."
                style={{ width: 'fit-content', minWidth: '180px', opacity: 0.55, cursor: 'not-allowed' }}
              >
                Adres kopiÃƒÂ«ren
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
        data-testid="kassa-camera-modal"
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
          <Button type="button" variant="secondary" onClick={onCancel} disabled={isUploading} data-testid="kassa-camera-cancel">Annuleren</Button>
        </div>
        <div style={{ border: '1px solid #D0D5DD', borderRadius: '12px', background: '#F8FAFC', minHeight: '360px', display: 'flex', alignItems: 'center', justifyContent: 'center', padding: '16px' }}>
          {draftUrl ? (
            <img src={draftUrl} alt="Voorbeeld van gefotografeerde kassabon" style={{ maxWidth: '100%', maxHeight: '70vh', objectFit: 'contain', borderRadius: '8px', background: '#fff' }} />
          ) : (
            <div style={{ color: '#667085' }}>Geen voorbeeld beschikbaar.</div>
          )}
        </div>


        <div className="rz-stock-table-actions" style={{ justifyContent: 'flex-start' }}>
          <Button type="button" variant="secondary" onClick={onRetake} disabled={isUploading} data-testid="kassa-camera-retake">Opnieuw</Button>
          <Button type="button" variant="primary" onClick={onConfirm} disabled={isUploading} data-testid="kassa-camera-confirm">{isUploading ? 'Opslaan...' : 'Bevestigen'}</Button>
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
        accept=".eml,message/rfc822,.pdf,.zip,.png,.jpg,.jpeg,.webp,application/pdf,application/zip,application/x-zip-compressed,image/png,image/jpeg,image/webp"
        style={{ display: 'none' }}
        data-testid="kassa-manual-file-input"
        onChange={onLandingUploadChange}
      />
      <input
        ref={cameraInputRef}
        type="file"
        accept="image/*"
        capture="environment"
        style={{ display: 'none' }}
        data-testid="kassa-camera-file-input"
        onChange={onCameraCaptureChange}
      />
      <input
        ref={emailInputRef}
        type="file"
        accept=".eml,message/rfc822"
        style={{ display: 'none' }}
        data-testid="kassa-email-file-input"
        onChange={onEmailUploadChange}
      />
    </>
  )
}

export default function KassaPage() {
  const navigate = useNavigate()
  const location = useLocation()
  const { showFeedback } = useAppFeedback()
  const isAddReceiptRoute = location.pathname === '/kassa/nieuw'
  const [householdId, setHouseholdId] = useState('')
  const [currentUserDisplayRole, setCurrentUserDisplayRole] = useState('viewer')
  const [receipts, setReceipts] = useState([])
  const [filters, setFilters] = useState(DEFAULT_RECEIPT_FILTERS)
  const [isLoading, setIsLoading] = useState(true)
  const [isUploading, setIsUploading] = useState(false)
  const [uploadProgress, setUploadProgress] = useState({ active: false, label: '', detail: '', percent: 0, stepKey: 'preparing' })
  const [error, setError] = useState('')
  const [status, setStatus] = useState('')
  const [duplicateNotice, setDuplicateNotice] = useState('')
  const [selectedReceiptIds, setSelectedReceiptIds] = useState([])
  const [openedReceiptId, setOpenedReceiptId] = useState('')
  const [openedReceipt, setOpenedReceipt] = useState(null)
  const openedReceiptIdRef = useRef('')
  const [deletedReceiptIds, setDeletedReceiptIds] = useState(() => loadStoredReceiptIds(DELETED_RECEIPTS_STORAGE_KEY))
  const [uploadMode, setUploadMode] = useState('manual')
  const [cameraDraft, setCameraDraft] = useState(null)
  const [cameraError, setCameraError] = useState('')
  const [emailRoute, setEmailRoute] = useState(null)
  const [isEmailRouteLoading, setIsEmailRouteLoading] = useState(false)
  const [emailRouteError, setEmailRouteError] = useState('')
  const [receiptInboxFocusId, setReceiptInboxFocusId] = useState('')
  const [transientReceiptPreview, setTransientReceiptPreview] = useState(null)
  const [technicalUploadError, setTechnicalUploadError] = useState(null)
  const [isTechnicalUploadErrorOpen, setIsTechnicalUploadErrorOpen] = useState(false)
  const fileInputRef = useRef(null)
  const cameraInputRef = useRef(null)
  const uploadBatchPollerRef = useRef(null)
  const uploadBatchLastProcessedRef = useRef(-1)
  const uploadProgressTimersRef = useRef([])
  const receiptInboxRefreshInFlightRef = useRef(false)
  const inboxScrollFrameRef = useRef(null)
  const [inboxScrollHeightPx, setInboxScrollHeightPx] = useState(KASSA_INBOX_FALLBACK_SCROLL_HEIGHT_PX)
  const [inboxSort, setInboxSort] = useState({ key: 'date', direction: 'desc' })

  useDismissOnComponentClick([() => setError(''), () => setStatus(''), () => setDuplicateNotice(''), () => setCameraError(''), () => setEmailRouteError('')], Boolean(error || status || duplicateNotice || cameraError || emailRouteError))

  useEffect(() => {
    return () => {
      if (cameraDraft?.previewUrl) {
        window.URL.revokeObjectURL(cameraDraft.previewUrl)
      }
    }
  }, [cameraDraft])

  useEffect(() => {
    return () => {
      if (transientReceiptPreview?.originalUrl) window.URL.revokeObjectURL(transientReceiptPreview.originalUrl)
      if (transientReceiptPreview?.processedUrl) window.URL.revokeObjectURL(transientReceiptPreview.processedUrl)
    }
  }, [transientReceiptPreview])

  useEffect(() => {
    openedReceiptIdRef.current = String(openedReceiptId || '')
  }, [openedReceiptId])

  useEffect(() => {
    return () => {
      if (uploadBatchPollerRef.current) {
        window.clearInterval(uploadBatchPollerRef.current)
        uploadBatchPollerRef.current = null
      }
      uploadProgressTimersRef.current.forEach((timerId) => window.clearTimeout(timerId))
      uploadProgressTimersRef.current = []
    }
  }, [])

  function showKassaFeedback(variant, message, options = {}) {
    const normalizedVariant = String(variant || 'info').trim().toLowerCase() || 'info'
    const normalizedMessage = String(message || '').trim()
    if (!normalizedMessage) return

    showFeedback({
      variant: normalizedVariant,
      title: options.title || (normalizedVariant === 'success' ? 'Gelukt' : normalizedVariant === 'error' ? 'Melding' : undefined),
      message: normalizedMessage,
      detail: options.detail || '',
      technicalDetail: options.technicalDetail || '',
      showTechnicalToggle: Boolean(options.showTechnicalToggle),
      key: options.key || `kassa-${normalizedVariant}-${normalizedMessage}`,
      dedupeMs: Number.isFinite(Number(options.dedupeMs)) ? Number(options.dedupeMs) : 3000,
      dismissMode: options.dismissMode || undefined,
      testId: options.testId || `kassa-feedback-${normalizedVariant}`,
    })
  }

  function clearTransientReceiptPreview() {
    setTransientReceiptPreview((current) => {
      if (current?.originalUrl) window.URL.revokeObjectURL(current.originalUrl)
      if (current?.processedUrl) window.URL.revokeObjectURL(current.processedUrl)
      return null
    })
  }

  function stopReceiptImportBatchPolling() {
    if (uploadBatchPollerRef.current) {
      window.clearInterval(uploadBatchPollerRef.current)
      uploadBatchPollerRef.current = null
    }
    uploadBatchLastProcessedRef.current = -1
  }

  function buildBatchUploadProgress(statusPayload) {
    const total = Number(statusPayload?.total_files || 0)
    const processed = Number(statusPayload?.processed_files || 0)
    const percentage = Number(statusPayload?.percentage || 0)
    return {
      label: 'Zip-batch verwerken...',
      detail: `${processed} van ${total} kassabonnen verwerkt (${percentage}%).`,
      percent: Math.max(10, percentage),
      stepKey: percentage >= 100 ? 'ready' : processed > 0 ? 'processing' : 'uploading',
    }
  }

  async function startReceiptImportBatchMonitoring(batchPayload) {
    const batchId = String(batchPayload?.batch_id || '')
    if (!batchId) return
    stopReceiptImportBatchPolling()
    const initial = buildBatchUploadProgress(batchPayload)
    setUploadProgressState(true, initial.label, initial.detail, initial.percent, initial.stepKey)
    if (isAddReceiptRoute) navigate('/kassa')
    setIsUploading(true)
    const pollOnce = async () => {
      try {
        const batch = await fetchReceiptImportBatchStatus(householdId, batchId)
        const nextProgress = buildBatchUploadProgress(batch)
        setUploadProgressState(true, nextProgress.label, nextProgress.detail, nextProgress.percent, nextProgress.stepKey)
        const processed = Number(batch?.processed_files || 0)
        if (processed !== uploadBatchLastProcessedRef.current) {
          uploadBatchLastProcessedRef.current = processed
          await loadReceipts(householdId)
        }
        const statusValue = String(batch?.status || '').toLowerCase()
        if (['completed', 'completed_with_errors', 'failed'].includes(statusValue)) {
          stopReceiptImportBatchPolling()
          await loadReceipts(householdId)
          await completeUploadProgress('Het zipbestand')
          setIsUploading(false)
          setUploadMode('manual')
          resetUploadProgress()
          setDuplicateNotice('')
          if (statusValue === 'failed') {
            setError(normalizeErrorMessage(batch?.error_message) || 'Het zipbestand kon niet volledig worden verwerkt.')
            setStatus('')
          } else {
            setError('')
            setStatus(`Zipbestand verwerkt: ${Number(batch?.imported_files || 0)} toegevoegd, ${Number(batch?.duplicate_files || 0)} dubbel, ${Number(batch?.failed_files || 0)} mislukt.`)
          }
          return true
        }
        return false
      } catch (err) {
        stopReceiptImportBatchPolling()
        setIsUploading(false)
        setUploadMode('manual')
        resetUploadProgress()
        setError(normalizeErrorMessage(err?.message) || 'De voortgang van het zipbestand kon niet worden bijgewerkt.')
        return true
      }
    }
    const finishedImmediately = await pollOnce()
    if (!finishedImmediately) {
      uploadBatchPollerRef.current = window.setInterval(() => {
        pollOnce().catch(() => {})
      }, 1000)
    }
  }

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
      const deletedCount = deletedIds.length
      const message = `${deletedCount} bon${deletedCount === 1 ? '' : 'nen'} verwijderd uit de inbox.`
      setStatus('')
      showKassaFeedback('success', message, {
        title: deletedCount === 1 ? 'Bon verwijderd' : 'Bonnen verwijderd',
        detail: 'De verwijderde bon is niet langer zichtbaar in de Kassa-inbox.',
        key: 'kassa-receipt-delete-success',
        dedupeMs: 0,
        testId: 'kassa-delete-overlay',
      })
    } catch (err) {
      setError(normalizeErrorMessage(err?.message) || 'De geselecteerde bonnen konden niet worden verwijderd.')
    }
  }


  function pruneReceiptUiState(apiItems = []) {
    const apiItemIds = new Set((apiItems || []).map((item) => String(item?.receipt_table_id || '')).filter(Boolean))
    setDeletedReceiptIds((current) => {
      const next = current.filter((id) => apiItemIds.has(String(id)))
      if (next.length !== current.length) persistStoredReceiptIds(DELETED_RECEIPTS_STORAGE_KEY, next)
      return next
    })
    setSelectedReceiptIds((current) => current.filter((id) => apiItemIds.has(String(id))))
    setReceiptInboxFocusId((current) => (current && !apiItemIds.has(String(current)) ? '' : current))
  }
  function mergeUploadedReceiptIntoItems(apiItems = [], result = null) {
    const uploadedReceiptId = String(result?.receipt_table_id || '')
    if (!uploadedReceiptId) return apiItems
    if ((apiItems || []).some((item) => String(item?.receipt_table_id || '') === uploadedReceiptId)) return apiItems
    return [
      {
        receipt_table_id: uploadedReceiptId,
        store_name: result?.store_name || result?.parsed?.store_name || result?.receipt?.store_name || 'Onbekende winkel',
        purchase_at: result?.purchase_at || result?.parsed?.purchase_at || result?.receipt?.purchase_at || null,
        total_amount: result?.total_amount ?? result?.parsed?.total_amount ?? result?.receipt?.total_amount ?? null,
        currency: result?.currency || result?.parsed?.currency || result?.receipt?.currency || 'EUR',
        line_count: Number(result?.line_count ?? result?.parsed?.line_count ?? result?.receipt?.line_count ?? 0),
        inbox_status: result?.inbox_status || result?.po_norm_status_label || 'Controle nodig',
        po_norm_status_label: result?.po_norm_status_label || 'Controle nodig',
        _optimistic_after_upload: true,
      },
      ...(apiItems || []),
    ]
  }

  async function loadReceiptsWithUploadedFallback(result, options = {}) {
    const uploadedReceiptId = String(result?.receipt_table_id || '')
    const items = await loadReceipts(householdId, options)
    if (!uploadedReceiptId || items.some((item) => String(item?.receipt_table_id || '') === uploadedReceiptId)) return items
    const mergedItems = mergeUploadedReceiptIntoItems(items, result)
    setReceipts([...mergedItems])
    pruneReceiptUiState(mergedItems)
    return mergedItems
  }
  async function loadReceipts(nextHouseholdId = householdId, options = {}) {
    if (!options?.silent) setIsLoading(true)
    if (!options?.silent) setError('')
    let items = []
    try {
      const list = await fetchJson(`/api/receipts?householdId=${encodeURIComponent(nextHouseholdId)}`)
      items = Array.isArray(list?.items) ? list.items : []
      setReceipts([...items])
      pruneReceiptUiState(items)
      setError('')
      if (!options?.preserveDuplicateNotice) setDuplicateNotice('')
      const activeReceiptId = String(options?.openReceiptId || openedReceiptIdRef.current || openedReceiptId || '')
      if (activeReceiptId) {
        const sourceItem = items.find((item) => String(item.receipt_table_id) === activeReceiptId) || null
        if (!sourceItem && !options?.prefetchedDetail) {
          setOpenedReceiptId('')
          setOpenedReceipt(null)
        } else {
          const detail = options?.prefetchedDetail || await fetchJson(`/api/receipts/${encodeURIComponent(activeReceiptId)}`)
          setOpenedReceiptId(activeReceiptId)
          setOpenedReceipt(sourceItem ? { ...sourceItem, ...detail } : detail)
        }
      }
    } catch (err) {
      setError(normalizeErrorMessage(err?.message) || 'Kassabonnen konden niet worden geladen.')
    } finally {
      if (!options?.silent) setIsLoading(false)
    }
    return items
  }

  useEffect(() => {
    if (!householdId || isAddReceiptRoute || isUploading) return undefined
    let cancelled = false
    const refreshKassaInbox = async () => {
      if (cancelled || receiptInboxRefreshInFlightRef.current) return
      receiptInboxRefreshInFlightRef.current = true
      try {
        await loadReceipts(householdId, { silent: true })
      } finally {
        receiptInboxRefreshInFlightRef.current = false
      }
    }
    const intervalId = window.setInterval(refreshKassaInbox, RECEIPT_INBOX_AUTO_REFRESH_MS)
    window.addEventListener('focus', refreshKassaInbox)
    return () => {
      cancelled = true
      window.clearInterval(intervalId)
      window.removeEventListener('focus', refreshKassaInbox)
      receiptInboxRefreshInFlightRef.current = false
    }
  }, [householdId, isAddReceiptRoute, isUploading])

  useEffect(() => {
    let cancelled = false
    async function bootstrap() {
      try {
        const token = localStorage.getItem('rezzerv_token')
        const household = await fetchJson('/api/household', {
          headers: token ? { Authorization: `Bearer ${token}` } : {},
        })
        if (cancelled) return
        const resolvedHouseholdId = String(
          household?.active_household_id
            || household?.id
            || household?.household_id
            || ''
        )

        if (!resolvedHouseholdId) {
          throw new Error('Er kon geen actief huishouden worden vastgesteld.')
        }

        setCurrentUserDisplayRole(String(household?.display_role || household?.current_user_display_role || 'viewer').toLowerCase())
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
          setError(sharedResult.message || 'De gedeelde bon kon niet worden verwerkt.')
          clearShareQueryParams()
          return
        }
        if (sharedResult?.shareStatus === 'success') {
          if (sharedResult.duplicate) {
            await announceDuplicate(sharedResult, items)
          } else {
            setDuplicateNotice('')
            setStatus('Gedeelde bon ontvangen. De bon staat nu in de Kassa.')
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
          setError(normalizeErrorMessage(err?.message) || 'Je gegevens konden niet worden geladen.')
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

  async function announceDuplicate(result, sourceItems = receipts) {
    const message = formatDuplicateImportMessageV2(result)
    const existingReceiptId = getDuplicateReceiptTableId(result)
    setError('')
    setStatus('')
    setDuplicateNotice(message)
    showKassaFeedback('warning', message, {
      title: 'Bon al ingelezen',
      detail: existingReceiptId ? 'De bestaande kassabon is geopend in Kassa.' : 'Deze upload is niet opnieuw toegevoegd. De bestaande kassabon blijft ongewijzigd in Kassa.',
      key: `kassa-duplicate-receipt-${existingReceiptId || 'unknown'}`,
      dedupeMs: 0,
      testId: 'kassa-duplicate-overlay',
    })

    if (existingReceiptId) {
      setFilters(DEFAULT_RECEIPT_FILTERS)
      setReceiptInboxFocusId(existingReceiptId)
      setSelectedReceiptIds([existingReceiptId])
      const refreshedItems = await loadReceipts(householdId, {
        preserveDuplicateNotice: true,
        openReceiptId: existingReceiptId,
      })
      const itemsForOpen = Array.isArray(refreshedItems) && refreshedItems.length ? refreshedItems : sourceItems
      await openReceiptDetail(existingReceiptId, itemsForOpen)
      if (isAddReceiptRoute) navigate('/kassa')
    }

    try {
      window.requestAnimationFrame(() => {
        const targetRow = existingReceiptId
          ? document.querySelector(`[data-testid="kassa-row-${existingReceiptId}"]`)
          : null
        const feedback = document.querySelector('[data-testid="receipt-duplicate-feedback"]')
        ;(targetRow || feedback)?.scrollIntoView({ behavior: 'smooth', block: 'center' })
      })
    } catch {
      // ignore scroll issues
    }
  }

  useEffect(() => {
    const visibleIds = new Set(receipts.map((receipt) => String(receipt?.receipt_table_id || '')).filter(Boolean))
    setSelectedReceiptIds((current) => current.filter((id) => visibleIds.has(String(id))))
    if (openedReceiptId && !visibleIds.has(String(openedReceiptId))) {
      setOpenedReceiptId('')
      setOpenedReceipt(null)
    }
  }, [receipts, openedReceiptId])

  useEffect(() => {
    if (receipts.length === 0) {
      setOpenedReceiptId('')
      setOpenedReceipt(null)
    }
  }, [receipts])

  const inboxItems = useMemo(() => {
    return receipts
      .filter((item) => !deletedReceiptIds.includes(String(item?.receipt_table_id || '')))
      .map((item) => ({ ...item, inbox_status: requirePoNormStatusLabel(item) }))
      .sort((a, b) => String(b.created_at || '').localeCompare(String(a.created_at || '')))
  }, [receipts, deletedReceiptIds])

  const inboxSummary = useMemo(() => ({
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
    const filteredItems = inboxItems
      .filter((item) => String(item.store_name || '').toLowerCase().includes(filters.winkel.trim().toLowerCase()))
      .filter((item) => formatDateTime(item.purchase_at).toLowerCase().includes(filters.datum.trim().toLowerCase()))
      .filter((item) => formatMoney(item.total_amount, item.currency).toLowerCase().includes(filters.totaal.trim().toLowerCase()))
      .filter((item) => String(item.line_count ?? 0).includes(filters.artikelen.trim()))
      .filter((item) => (filters.status ? item.inbox_status === filters.status : true))
    return sortItems(filteredItems, inboxSort, {
      store: (item) => item.store_name || '',
      date: (item) => item.purchase_at || '',
      total: (item) => Number(item.total_amount ?? 0),
      items: (item) => Number(item.line_count ?? 0),
    })
  }, [inboxItems, filters, inboxSort])

  const allVisibleSelected = listItems.length > 0 && listItems.every((item) => selectedReceiptIds.includes(String(item.receipt_table_id || '')))

  const inboxTableFilters = useMemo(() => ({
    store: filters.winkel,
    date: filters.datum,
    total: filters.totaal,
    items: filters.artikelen,
  }), [filters.winkel, filters.datum, filters.totaal, filters.artikelen])

  const inboxColumnDefaults = useMemo(
    () => Object.fromEntries(inboxTableColumns.map(({ key, width }) => [key, width])),
    [],
  )
  const { widths: inboxTableWidths, startResize: startInboxTableResize } = useResizableColumnWidths(inboxColumnDefaults)

  useLayoutEffect(() => {
    const frame = inboxScrollFrameRef.current
    if (!frame) return undefined

    let animationFrame = 0

    const measureInboxHeight = () => {
      const table = frame.querySelector('.rz-kassa-inbox-table')
      const header = table?.querySelector('thead')
      const dataRows = Array.from(table?.querySelectorAll('tbody > tr') || [])
        .filter((row) => row.querySelector('td'))

      if (!header || dataRows.length === 0) {
        setInboxScrollHeightPx(KASSA_INBOX_FALLBACK_SCROLL_HEIGHT_PX)
        return
      }

      const visibleRows = dataRows.slice(0, KASSA_INBOX_VISIBLE_ROW_COUNT)
      const headerHeight = header.getBoundingClientRect().height
      const rowsHeight = visibleRows.reduce(
        (total, row) => total + row.getBoundingClientRect().height,
        0,
      )

      // EÃ©n pixel marge voorkomt dat de elfde rij deels zichtbaar wordt door afronding of tabelranden.
      const nextHeight = Math.max(
        1,
        Math.floor(headerHeight + rowsHeight) - 1,
      )

      setInboxScrollHeightPx((current) => (
        current === nextHeight ? current : nextHeight
      ))
    }

    const scheduleMeasure = () => {
      window.cancelAnimationFrame(animationFrame)
      animationFrame = window.requestAnimationFrame(measureInboxHeight)
    }

    scheduleMeasure()

    const resizeObserver = typeof ResizeObserver !== 'undefined'
      ? new ResizeObserver(scheduleMeasure)
      : null

    resizeObserver?.observe(frame)
    window.addEventListener('resize', scheduleMeasure)

    return () => {
      window.cancelAnimationFrame(animationFrame)
      resizeObserver?.disconnect()
      window.removeEventListener('resize', scheduleMeasure)
    }
  }, [
    isLoading,
    listItems.length,
    inboxSort,
    inboxTableFilters.store,
    inboxTableFilters.date,
    inboxTableFilters.total,
    inboxTableFilters.items,
  ])

  function applyReceiptUpdate(updated) {
    if (!updated) return
    setOpenedReceipt(updated)
    setReceipts((current) => current.map((item) => {
      const itemId = String(item?.receipt_table_id || item?.id || '')
      const updatedId = String(updated?.receipt_table_id || updated?.id || '')
      if (!itemId || itemId !== updatedId) return item
      return {
        ...item,
        ...updated,
        receipt_table_id: item.receipt_table_id || updated.receipt_table_id || updated.id,
      }
    }))
  }

  function normalizeReceiptCorrectionDate(value) {
    const rawValue = String(value || '').trim()
    return rawValue ? rawValue.slice(0, 10) : ''
  }

  function openReceiptImportConfirmation(receipt) {
    const receiptId = String(receipt?.receipt_table_id || receipt?.id || '')
    if (!receiptId) return

    const needsStore = String(receipt?.store_name_source || '') === 'user_required'
    const needsPurchaseDate = String(receipt?.purchase_at_source || '') === 'import_default'

    if (!needsStore && !needsPurchaseDate) return

    const inputFields = []

    if (needsStore) {
      inputFields.push({
        name: 'store_name',
        label: 'Winkel(keten)',
        type: 'text',
        value: '',
        placeholder: 'Vul de naam van de winkel of winkelketen in',
        required: true,
        autoFocus: true,
      })
    }

    if (needsPurchaseDate) {
      inputFields.push({
        name: 'purchase_at',
        label: 'Aankoopdatum',
        type: 'date',
        value: normalizeReceiptCorrectionDate(receipt?.purchase_at),
        required: true,
        autoFocus: !needsStore,
      })
    }

    const title = needsStore && needsPurchaseDate
      ? 'Controleer winkel en aankoopdatum'
      : needsStore
        ? 'Winkel niet herkend'
        : 'Aankoopdatum niet herkend'

    const message = needsStore && needsPurchaseDate
      ? 'De winkel kon niet worden gelezen en voor de aankoopdatum is de inleesdatum ingevuld.'
      : needsStore
        ? 'Vul de naam van de winkel of winkelketen in.'
        : 'Als aankoopdatum is de datum van inlezen ingevuld.'

    const detail = needsPurchaseDate
      ? 'Controleer de aankoopdatum. Je kunt de voorgestelde datum wijzigen voordat je opslaat.'
      : 'Deze naam wordt bij de kassabon opgeslagen en helpt bij latere ondersteuning van deze winkel.'

    showFeedback({
      variant: 'warning',
      title,
      message,
      detail,
      inputFields,
      primaryActionLabel: 'Opslaan',
      dismissMode: 'blocked',
      key: `kassa-import-confirmation-${receiptId}`,
      dedupeMs: 0,
      testId: 'kassa-import-confirmation',
      onPrimaryAction: async (values) => {
        const payload = {}

        if (needsStore) {
          payload.store_name = String(values?.store_name || '').trim()
          if (!payload.store_name) {
            throw new Error('Vul de naam van de winkel of winkelketen in.')
          }
        }

        if (needsPurchaseDate) {
          payload.purchase_at = normalizeReceiptCorrectionDate(values?.purchase_at)
          if (!payload.purchase_at) {
            throw new Error('Vul een geldige aankoopdatum in.')
          }
        }

        const updated = await fetchJson(
          `/api/receipts/${encodeURIComponent(receiptId)}`,
          {
            method: 'PATCH',
            body: JSON.stringify(payload),
          },
        )

        applyReceiptUpdate(updated)

        showKassaFeedback(
          'success',
          needsStore && needsPurchaseDate
            ? 'Winkel en aankoopdatum zijn opgeslagen.'
            : needsStore
              ? 'Winkel is opgeslagen.'
              : 'Aankoopdatum is opgeslagen.',
          {
            key: `kassa-import-confirmation-saved-${receiptId}`,
            dedupeMs: 0,
          },
        )

        return true
      },
    })
  }

  async function openReceiptDetail(
    receiptTableId,
    sourceItems = receipts,
    prefetchedDetail = null,
    showImportConfirmation = false,
  ) {
    setError('')
    try {
      const detail = prefetchedDetail || await fetchJson(`/api/receipts/${encodeURIComponent(receiptTableId)}`)
      const sourceItem = sourceItems.find((item) => String(item.receipt_table_id) === String(receiptTableId)) || null
      const mergedDetail = sourceItem ? { ...sourceItem, ...detail } : detail
      setOpenedReceiptId(receiptTableId)
      setOpenedReceipt(mergedDetail)

      if (showImportConfirmation) {
        openReceiptImportConfirmation(mergedDetail)
      }

      return mergedDetail
    } catch (err) {
      setError(normalizeErrorMessage(err?.message) || 'De kassabon kon niet worden geladen.')
      return null
    }
  }

  function toggleSelectedReceipt(receiptTableId) {
    const receiptId = String(receiptTableId || '')
    if (!receiptId) return
    setSelectedReceiptIds((current) => (
      current.includes(receiptId)
        ? current.filter((id) => id !== receiptId)
        : [...current, receiptId]
    ))
  }

  function toggleSelectAllVisible() {
    const visibleIds = listItems.map((item) => String(item.receipt_table_id || '')).filter(Boolean)
    if (!visibleIds.length) return
    const allSelected = visibleIds.every((id) => selectedReceiptIds.includes(id))
    setSelectedReceiptIds(allSelected ? [] : visibleIds)
  }

  function handleFilterChange(key, value) {
    const mappedKey = {
      store: 'winkel',
      date: 'datum',
      total: 'totaal',
      items: 'artikelen',
    }[key] || key

    setFilters((current) => ({ ...current, [mappedKey]: value }))
  }

  function applyStatusFilter(value) {
    setFilters((current) => ({ ...current, status: current.status === value ? '' : value }))
  }

  async function ensureEmailRouteLoaded(forceReload = false) {
    if (!householdId) return null
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


  function clearUploadProgressTimers() {
    uploadProgressTimersRef.current.forEach((timerId) => window.clearTimeout(timerId))
    uploadProgressTimersRef.current = []
  }

  function setUploadProgressState(active, label = '', detail = '', percent = 0, stepKey = 'processing') {
    setUploadProgress({ active, label, detail, percent, stepKey })
  }

  function scheduleUploadProgressStep(delayMs, label, detail, percent, stepKey) {
    const timerId = window.setTimeout(() => {
      setUploadProgress((current) => {
        if (!current?.active) return current
        return { active: true, label, detail, percent, stepKey }
      })
    }, delayMs)
    uploadProgressTimersRef.current.push(timerId)
  }

  function beginUploadProgress(kindLabel = 'de kassabon') {
    clearUploadProgressTimers()
    setUploadProgressState(true, 'Bestand voorbereiden...', `Rezzerv bereidt ${kindLabel} voor.`, 10, 'preparing')
    scheduleUploadProgressStep(180, 'Bon versturen...', 'Het bestand wordt veilig naar Rezzerv verstuurd.', 25, 'uploading')
    scheduleUploadProgressStep(700, 'Bon verwerken...', 'Rezzerv leest winkel, aankoopmoment, bedragen en bonregels uit.', 50, 'processing')
  }

  async function completeUploadProgress(kindLabel = 'De kassabon') {
    clearUploadProgressTimers()
    setUploadProgressState(true, 'Kassa bijwerken...', `${kindLabel} is verwerkt. Rezzerv werkt nu de inbox bij.`, 80, 'refreshing')
    await new Promise((resolve) => window.setTimeout(resolve, 160))
    setUploadProgressState(true, 'Gereed...', `${kindLabel} staat klaar in Kassa.`, 100, 'ready')
    await new Promise((resolve) => window.setTimeout(resolve, 420))
  }

  function resetUploadProgress() {
    clearUploadProgressTimers()
    setUploadProgress({ active: false, label: '', detail: '', percent: 0, stepKey: 'preparing' })
  }

  function clearTechnicalUploadError() {
    setTechnicalUploadError(null)
    setIsTechnicalUploadErrorOpen(false)
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
    beginUploadProgress('de foto')
    setError('')
    setCameraError('')
    setStatus('')
    setDuplicateNotice('')
    try {
      const preparedFile = await prepareCameraUploadFile(cameraDraft.file)
      setUploadProgressState(true, 'Bon verwerken...', 'Rezzerv analyseert de gefotografeerde kassabon.', 55, 'processing')
      const result = await uploadSharedReceiptFile(householdId, preparedFile, 'camera_capture', 'Foto gemaakt in Rezzerv')
      const uploadedReceiptId = String(result?.receipt_table_id || '')

      if (result?.duplicate) {
        await announceDuplicate(result)
      } else {
        clearCameraDraft()
            setOpenedReceiptId('')
        setOpenedReceipt(null)
        setFilters(DEFAULT_RECEIPT_FILTERS)
        setReceiptInboxFocusId(uploadedReceiptId)

        setUploadProgressState(true, 'Kassa bijwerken...', buildPostImportProgressMessage('De foto'), 80, 'refreshing')
        const refreshedItems = await loadReceiptsWithUploadedFallback(result, { openReceiptId: uploadedReceiptId })
        const receiptExistsInInbox = uploadedReceiptId
          ? refreshedItems.some((item) => String(item?.receipt_table_id || '') === uploadedReceiptId)
          : false

        if (uploadedReceiptId) {
          setSelectedReceiptIds([uploadedReceiptId])
          await openReceiptDetail(
            uploadedReceiptId,
            refreshedItems,
            null,
            true,
          )
          clearTransientReceiptPreview()
        } else {
          setSelectedReceiptIds([])
        }

        if (result?.receipt_table_id) {
          setDuplicateNotice('')
          setStatus('Foto verwerkt. De bon staat nu in de Kassa.')
        } else {
          setStatus('Foto opgeslagen, maar Rezzerv herkent nog geen bruikbare kassabon. Controleer de foto of probeer opnieuw.')
        }

        if (uploadedReceiptId && !receiptExistsInInbox) {
          setStatus('Bon toegevoegd. De lijst is bijgewerkt.')
        }

        await completeUploadProgress('De foto')
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



  async function processPicnicEmailLandingFile(file) {
    if (!file) {
      setEmailRouteError('Sleep hier een opgeslagen Picnic e-mailbestand (.eml) naartoe.')
      setError('')
      return
    }

    if (!isSupportedEmailImportFile(file)) {
      setEmailRouteError('Gebruik voor Picnic een opgeslagen e-mailbestand (.eml).')
      setError('')
      return
    }

    setIsUploading(true)
    beginUploadProgress('de Picnic e-mailbon')
    setError('')
    setStatus('Picnic e-mailbestand wordt verwerkt.')
    setDuplicateNotice('')
    setEmailRouteError('')
    clearTechnicalUploadError()

    try {
      const result = await uploadPicnicEmailReceiptFile(householdId, file)
      const uploadedReceiptId = String(result?.receipt_table_id || '')

      if (result?.duplicate) {
        await announceDuplicate(result)
      } else {
        setOpenedReceiptId('')
        setOpenedReceipt(null)
        setFilters(DEFAULT_RECEIPT_FILTERS)
        setReceiptInboxFocusId(uploadedReceiptId)
        setUploadProgressState(true, 'Kassa bijwerken...', buildPostImportProgressMessage('De Picnic e-mailbon'), 80, 'refreshing')

        const refreshedItems = await loadReceiptsWithUploadedFallback(result, { openReceiptId: uploadedReceiptId })
        const receiptExistsInInbox = uploadedReceiptId
          ? refreshedItems.some((item) => String(item?.receipt_table_id || '') === uploadedReceiptId)
          : false

        if (uploadedReceiptId) {
          setSelectedReceiptIds([uploadedReceiptId])
          await openReceiptDetail(
            uploadedReceiptId,
            refreshedItems,
            null,
            true,
          )
          clearTransientReceiptPreview()
        } else {
          setSelectedReceiptIds([])
        }

        setDuplicateNotice('')
        setEmailRouteError('')
        clearTechnicalUploadError()
        setStatus(result?.receipt_table_id ? 'Picnic e-mailbon ontvangen. De bon staat nu in de Kassa.' : 'Picnic e-mail verwerkt, maar Rezzerv herkent nog geen bruikbare kassabon. Controleer het e-mailbestand.')
        await completeUploadProgress('De Picnic e-mailbon')

        if (isAddReceiptRoute) navigate('/kassa')
      }
    } catch (err) {
      const technical = err?.technicalUploadError || null
      if (technical) setTechnicalUploadError(technical)
      setEmailRouteError(technical?.userMessage || normalizeErrorMessage(err?.message) || 'Picnic e-mailbestand kon niet worden verwerkt.')
      setError('')
    } finally {
      setIsUploading(false)
      resetUploadProgress()
      setUploadMode('manual')
    }
  }

  async function processReceiptFileImport(file) {
    if (isSupportedReceiptImageFile(file)) {
      try {
        const nextTransientPreview = await createTransientReceiptPreview(file)
        setTransientReceiptPreview((current) => {
          if (current?.originalUrl) window.URL.revokeObjectURL(current.originalUrl)
          if (current?.processedUrl) window.URL.revokeObjectURL(current.processedUrl)
          return nextTransientPreview
        })
      } catch {
        clearTransientReceiptPreview()
      }
    } else {
      clearTransientReceiptPreview()
    }
    if (!file) {
      setEmailRouteError('Kies een bonbestand: pdf, zip, afbeelding of e-mailbestand (.eml).')
      setError('')
      return
    }
    if (!isSupportedReceiptDocumentFile(file) && !isSupportedReceiptImageFile(file)) {
      setEmailRouteError('Dit bestandstype wordt nog niet ondersteund. Gebruik pdf, zip, png, jpg, jpeg, webp of eml.')
      setError('')
      return
    }

    setIsUploading(true)
    beginUploadProgress('de kassabon')
    setError('')
    setStatus('')
    setDuplicateNotice('')
    setEmailRouteError('')
    try {
      const result = await uploadReceiptFile(householdId, file)
      const uploadedReceiptId = String(result?.receipt_table_id || '')
      const isBatchImport = Boolean(result?.batch)
      let keepUploading = false
      if (result?.duplicate && !isBatchImport) {
        await announceDuplicate(result)
      } else if (isBatchImport && result?.async && result?.batch_id) {
        setOpenedReceiptId('')
        setOpenedReceipt(null)
        setFilters(DEFAULT_RECEIPT_FILTERS)
        setSelectedReceiptIds([])
        setDuplicateNotice('')
        setError('')
        keepUploading = true
        await startReceiptImportBatchMonitoring(result)
      } else {
        setOpenedReceiptId('')
        setOpenedReceipt(null)
        setFilters(DEFAULT_RECEIPT_FILTERS)
        setReceiptInboxFocusId(uploadedReceiptId)
        setUploadProgressState(true, 'Kassa bijwerken...', buildPostImportProgressMessage('De kassabon'), 80, 'refreshing')
        const refreshedItems = await loadReceiptsWithUploadedFallback(result, { openReceiptId: uploadedReceiptId })
        const receiptExistsInInbox = uploadedReceiptId
          ? refreshedItems.some((item) => String(item?.receipt_table_id || '') === uploadedReceiptId)
          : false

        if (uploadedReceiptId) {
          setSelectedReceiptIds([uploadedReceiptId])
          await openReceiptDetail(
            uploadedReceiptId,
            refreshedItems,
            null,
            true,
          )
          clearTransientReceiptPreview()
        } else {
          setSelectedReceiptIds([])
        }

        if (result?.receipt_table_id) {
          setDuplicateNotice('')
          setStatus('Bon toegevoegd. De bon staat nu in de Kassa.')
        } else {
          setStatus('Bestand opgeslagen, maar Rezzerv herkent nog geen bruikbare kassabon. Controleer het bestand of probeer opnieuw.')
        }

        if (uploadedReceiptId && !receiptExistsInInbox) {
          setStatus('Bon toegevoegd. De lijst is bijgewerkt.')
        }

        await completeUploadProgress('De kassabon')
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
      if (!keepUploading) {
        setIsUploading(false)
        resetUploadProgress()
      }
    } catch (err) {
      const technical = err?.technicalUploadError || null
      if (technical) setTechnicalUploadError(technical)

      let refreshedItems = []
      try {
        refreshedItems = await loadReceipts(householdId, { preserveDuplicateNotice: true })
      } catch {
        refreshedItems = []
      }

      const visibleReceiptCount = Array.isArray(refreshedItems) ? refreshedItems.length : 0
      if (visibleReceiptCount > 0) {
        setEmailRouteError('')
        setError('')
        setDuplicateNotice('')
        setStatus(`Kassa is geladen met ${visibleReceiptCount} bon${visibleReceiptCount === 1 ? '' : 'nen'}. Er was wel een technische uploadmelding; details zijn alleen voor de admin beschikbaar.`)
      } else {
        setEmailRouteError(technical?.userMessage || normalizeErrorMessage(err?.message) || 'Upload van het bonbestand is mislukt.')
        setError('')
      }
      setIsUploading(false)
      resetUploadProgress()
    } finally {
      setUploadMode('manual')
    }
  }

  async function processLandingReceiptFile(file) {
    if (!file) {
      setEmailRouteError('Sleep of kies een eml-, pdf- of afbeeldingsbestand.')
      setError('')
      return
    }
    const fileKind = getReceiptLandingFileKind(file)
    if (fileKind === 'email') {
      await processPicnicEmailLandingFile(file)
      return
    }
    if (fileKind === 'pdf' || fileKind === 'image') {
      await processReceiptFileImport(file)
      return
    }
    setEmailRouteError('Dit bestandstype wordt hier niet ondersteund.')
    setError('')
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
        onLandingUploadChange={handleLandingUploadChange}
        onCameraCaptureChange={handleCameraCaptureChange}
      />

      {isAddReceiptRoute ? (
        <div data-testid="kassa-add-page" style={{ display: 'grid', gap: '16px' }}>
          <ReceiptSourceHubContent
            onChooseReceiptFile={handleChooseReceiptFileFromHub}
            onChooseCamera={handleChooseCameraFromHub}
            onDropLandingFile={handleDroppedLandingFile}
            onCopyEmailRoute={copyEmailRouteToClipboard}
            emailRoute={emailRoute}
            isEmailRouteLoading={isEmailRouteLoading}
            emailRouteError={emailRouteError}
            isUploading={isUploading}
            technicalUploadError={technicalUploadError}
            isTechnicalUploadErrorOpen={isTechnicalUploadErrorOpen}
            onToggleTechnicalUploadError={() => setIsTechnicalUploadErrorOpen((current) => !current)}
            currentUserDisplayRole={currentUserDisplayRole}
          />
        </div>
      ) : (
        <div className="rz-kassa-page" style={{ display: 'grid', gap: '16px' }} data-testid="kassa-page">
          <ScreenCard>
            <div style={{ display: 'grid', gap: '16px' }}>
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', gap: '12px', flexWrap: 'wrap' }}>
                <div>
                  <div style={{ fontWeight: 700, fontSize: '24px' }}>Kassa</div>
                  <div style={{ color: '#667085', marginTop: '4px' }}>
                    Zie direct welke bonnen nieuw zijn, controle nodig hebben of al gecontroleerd zijn.
                  </div>
                </div>
                <div className="rz-stock-table-actions" style={{ justifyContent: 'flex-start' }}>
                  <Button type="button" variant="primary" onClick={openSourceHub} disabled={isUploading} data-testid="kassa-add-receipt-button">{isUploading ? 'Uploaden...' : 'Bon toevoegen'}</Button>
                </div>
              </div>

              <ReceiptSourceHubContent
                onChooseReceiptFile={handleChooseReceiptFileFromHub}
                onChooseCamera={handleChooseCameraFromHub}
                onDropLandingFile={handleDroppedLandingFile}
                onCopyEmailRoute={copyEmailRouteToClipboard}
                emailRoute={emailRoute}
                isEmailRouteLoading={isEmailRouteLoading}
                emailRouteError={emailRouteError}
                isUploading={isUploading}
            technicalUploadError={technicalUploadError}
            isTechnicalUploadErrorOpen={isTechnicalUploadErrorOpen}
            onToggleTechnicalUploadError={() => setIsTechnicalUploadErrorOpen((current) => !current)}
            currentUserDisplayRole={currentUserDisplayRole}
                showHeading={false}
                showSupportPanels={false}
              />

              <div style={{ display: 'grid', gap: '12px', gridTemplateColumns: 'repeat(auto-fit, minmax(180px, 1fr))' }}>
                {[
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

              <style>{`
                .rz-kassa-inbox-scroll-frame > .rz-kassa-inbox-table-wrapper {
                  max-height: none !important;
                  overflow: visible !important;
                }

                .rz-kassa-inbox-scroll-frame .rz-kassa-inbox-table tbody > tr > td {
                  padding-top: 4px;
                  padding-bottom: 4px;
                  vertical-align: middle;
                  white-space: nowrap;
                  overflow: hidden;
                  text-overflow: ellipsis;
                }
              `}</style>

              <div
                ref={inboxScrollFrameRef}
                className="rz-kassa-inbox-scroll-frame"
                style={{
                  // Gemeten hoogte: kop/filter plus exact tien volledige bonregels.
                  height: `${inboxScrollHeightPx}px`,
                  maxHeight: `${inboxScrollHeightPx}px`,
                  overflowY: 'auto',
                  overflowX: 'auto',
                  scrollbarGutter: 'stable',
                }}
                aria-label="Kassaboninbox met maximaal tien zichtbare bonnen"
                data-testid="kassa-inbox-scroll-container"
              >
              <Table
                wrapperClassName="rz-kassa-inbox-table-wrapper"
                tableClassName="rz-kassa-inbox-table rz-table--compact"
                dataTestId="kassa-table"
                tableStyle={{
                  tableLayout: 'fixed',
                  width: buildTableWidth(inboxTableWidths),
                  minWidth: buildTableWidth(inboxTableWidths),
                }}
              >
                <colgroup>
                  <col style={{ width: `${inboxTableWidths.select}px` }} />
                  <col style={{ width: `${inboxTableWidths.store}px` }} />
                  <col style={{ width: `${inboxTableWidths.date}px` }} />
                  <col style={{ width: `${inboxTableWidths.total}px` }} />
                  <col style={{ width: `${inboxTableWidths.items}px` }} />
                </colgroup>
                <thead>
                  <tr className="rz-table-header">
                    <ResizableHeaderCell columnKey="select" widths={inboxTableWidths} onStartResize={startInboxTableResize} style={{ width: '44px' }}>
                      <input
                        type="checkbox"
                        checked={allVisibleSelected}
                        onChange={toggleSelectAllVisible}
                        aria-label="Selecteer alle zichtbare bonnen"
                      />
                    </ResizableHeaderCell>
                    <ResizableHeaderCell columnKey="store" widths={inboxTableWidths} onStartResize={startInboxTableResize} sortable isSorted={inboxSort.key === 'store'} sortDirection={inboxSort.direction} onSort={(key) => setInboxSort((current) => nextSortState(current, key, { store: 'asc', date: 'desc', total: 'desc', items: 'desc' }))}>Winkel</ResizableHeaderCell>
                    <ResizableHeaderCell columnKey="date" widths={inboxTableWidths} onStartResize={startInboxTableResize} sortable isSorted={inboxSort.key === 'date'} sortDirection={inboxSort.direction} onSort={(key) => setInboxSort((current) => nextSortState(current, key, { store: 'asc', date: 'desc', total: 'desc', items: 'desc' }))}>Datum</ResizableHeaderCell>
                    <ResizableHeaderCell columnKey="total" widths={inboxTableWidths} onStartResize={startInboxTableResize} className="rz-num" sortable isSorted={inboxSort.key === 'total'} sortDirection={inboxSort.direction} onSort={(key) => setInboxSort((current) => nextSortState(current, key, { store: 'asc', date: 'desc', total: 'desc', items: 'desc' }))}>Totaal</ResizableHeaderCell>
                    <ResizableHeaderCell columnKey="items" widths={inboxTableWidths} onStartResize={startInboxTableResize} className="rz-num" sortable isSorted={inboxSort.key === 'items'} sortDirection={inboxSort.direction} onSort={(key) => setInboxSort((current) => nextSortState(current, key, { store: 'asc', date: 'desc', total: 'desc', items: 'desc' }))}>Artikelen</ResizableHeaderCell>
                  </tr>
                  <tr className="rz-table-filters">
                    <th />
                    <th>
                      <input
                        className="rz-input rz-inline-input"
                        value={inboxTableFilters.store}
                        onChange={(event) => handleFilterChange('store', event.target.value)}
                        placeholder="Filter"
                        aria-label="Filter op winkel"
                      />
                    </th>
                    <th>
                      <input
                        className="rz-input rz-inline-input"
                        value={inboxTableFilters.date}
                        onChange={(event) => handleFilterChange('date', event.target.value)}
                        placeholder="Filter"
                        aria-label="Filter op datum"
                      />
                    </th>
                    <th>
                      <input
                        className="rz-input rz-inline-input"
                        value={inboxTableFilters.total}
                        onChange={(event) => handleFilterChange('total', event.target.value)}
                        placeholder="Filter"
                        aria-label="Filter op totaal"
                      />
                    </th>
                    <th>
                      <input
                        className="rz-input rz-inline-input"
                        value={inboxTableFilters.items}
                        onChange={(event) => handleFilterChange('items', event.target.value)}
                        placeholder="Filter"
                        aria-label="Filter op artikelen"
                      />
                    </th>
                  </tr>
                </thead>
                <tbody>
                  {isLoading ? (
                    <tr><td colSpan={5}>Bonnen laden...</td></tr>
                  ) : listItems.length === 0 ? (
                    <tr><td colSpan={5}>Er zijn nog geen bonnen in de inbox beschikbaar.</td></tr>
                  ) : listItems.map((item) => {
                    const receiptId = String(item.receipt_table_id || '')
                    const selected = selectedReceiptIds.includes(receiptId)
                    return (
                      <tr
                        key={receiptId}
                        className={selected ? 'rz-row-selected' : ''}
                        onClick={() => toggleSelectedReceipt(receiptId)}
                        onDoubleClick={() => openReceiptDetail(receiptId)}
                        data-testid={`kassa-row-${receiptId}`}
                        style={{
                          cursor: 'pointer',
                          boxShadow: `inset 4px 0 0 ${item.inbox_status === 'Gecontroleerd' ? '#12B76A' : item.inbox_status === 'Controle nodig' ? '#F79009' : '#B54708'}`,
                          background: receiptId === receiptInboxFocusId ? '#ECFDF3' : undefined,
                          outline: receiptId === receiptInboxFocusId ? '2px solid #12B76A' : undefined,
                          outlineOffset: receiptId === receiptInboxFocusId ? '-2px' : undefined,
                        }}
                      >
                        <td onClick={(event) => event.stopPropagation()}>
                          <button
                            type="button"
                            data-testid={`kassa-open-${receiptId}`}
                            onClick={(event) => { event.stopPropagation(); openReceiptDetail(receiptId) }}
                            style={{ display: 'none' }}
                            aria-hidden="true"
                            tabIndex={-1}
                          />
                          <input
                            type="checkbox"
                            checked={selected}
                            onChange={() => toggleSelectedReceipt(receiptId)}
                            aria-label={`Selecteer bon ${item.store_name || 'onbekend'} van ${formatDateTime(item.purchase_at)}`}
                          />
                        </td>
                        <td>{item.store_name || 'Onbekende winkel'}</td>
                        <td>{formatDateTime(item.purchase_at)}</td>
                        <td className="rz-num">{formatMoney(item.total_amount, item.currency)}</td>
                        <td className="rz-num">{item.line_count ?? 0}</td>
                      </tr>
                    )
                  })}
                </tbody>
              </Table>
              </div>

            </div>
          </ScreenCard>

          {(openedReceipt || transientReceiptPreview) ? <ReceiptDetailView receipt={openedReceipt} transientPreview={openedReceipt ? null : transientReceiptPreview} canEdit={['admin','lid'].includes(currentUserDisplayRole)} onReceiptUpdated={applyReceiptUpdate} onFeedback={showKassaFeedback} /> : null}
        </div>
      )}

      <ReceiptUploadProgressOverlay uploadProgress={uploadProgress} />

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
