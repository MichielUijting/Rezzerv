import { useEffect, useState } from 'react'
import Button from '../../ui/Button'
import { normalizeErrorMessage } from '../stores/storeImportShared'
import './receiptDebugExportButton.css'

const ACTIVE_RECEIPT_KEY = 'rezzerv_active_receipt_table_id'
const FETCH_PATCH_MARKER = '__rezzervReceiptDebugFetchObserverInstalled'
const RECEIPT_URL_PATTERN = /\/api\/receipts\/([^/?#]+)(?:\/preview|\/debug-export|\b)/

function getToken() {
  try {
    return window.localStorage.getItem('rezzerv_token') || ''
  } catch {
    return ''
  }
}

function rememberReceiptIdFromFetchInput(input) {
  const url = typeof input === 'string' ? input : String(input?.url || '')
  const match = url.match(RECEIPT_URL_PATTERN)
  if (!match?.[1]) return ''
  const receiptId = decodeURIComponent(match[1])
  try {
    window.sessionStorage.setItem(ACTIVE_RECEIPT_KEY, receiptId)
    window.dispatchEvent(new CustomEvent('rezzerv-active-receipt-ready', { detail: { receiptId } }))
  } catch {
    // ignore browser storage/event edge cases
  }
  return receiptId
}

function installFetchObserver() {
  if (typeof window === 'undefined') return
  if (window[FETCH_PATCH_MARKER]) return
  window[FETCH_PATCH_MARKER] = true
  const originalFetch = window.fetch.bind(window)
  window.fetch = async (input, init) => {
    rememberReceiptIdFromFetchInput(input)
    return originalFetch(input, init)
  }
}

function readStoredReceiptId() {
  try {
    return window.sessionStorage.getItem(ACTIVE_RECEIPT_KEY) || ''
  } catch {
    return ''
  }
}

function downloadBlob(blob, filename) {
  const url = window.URL.createObjectURL(blob)
  const anchor = document.createElement('a')
  anchor.href = url
  anchor.download = filename
  document.body.appendChild(anchor)
  anchor.click()
  anchor.remove()
  window.setTimeout(() => window.URL.revokeObjectURL(url), 1000)
}

export default function ReceiptDebugExportButton() {
  const [receiptId, setReceiptId] = useState('')
  const [message, setMessage] = useState('')
  const [isDownloading, setIsDownloading] = useState(false)
  const [isKassaRoute, setIsKassaRoute] = useState(() => window.location.pathname.startsWith('/kassa'))

  useEffect(() => {
    installFetchObserver()
    setReceiptId(readStoredReceiptId())

    const updateRoute = () => setIsKassaRoute(window.location.pathname.startsWith('/kassa'))
    const updateReceipt = (event) => setReceiptId(event?.detail?.receiptId || readStoredReceiptId())

    window.addEventListener('popstate', updateRoute)
    window.addEventListener('hashchange', updateRoute)
    window.addEventListener('rezzerv-active-receipt-ready', updateReceipt)
    window.addEventListener('focus', updateReceipt)
    const timer = window.setInterval(() => {
      updateRoute()
      const storedReceiptId = readStoredReceiptId()
      if (storedReceiptId && storedReceiptId !== receiptId) setReceiptId(storedReceiptId)
    }, 1000)

    return () => {
      window.removeEventListener('popstate', updateRoute)
      window.removeEventListener('hashchange', updateRoute)
      window.removeEventListener('rezzerv-active-receipt-ready', updateReceipt)
      window.removeEventListener('focus', updateReceipt)
      window.clearInterval(timer)
    }
  }, [receiptId])

  if (!isKassaRoute || !receiptId) return null

  async function handleDownloadDebugJson() {
    setIsDownloading(true)
    setMessage('')
    try {
      const token = getToken()
      const response = await fetch(`/api/receipts/${encodeURIComponent(receiptId)}/debug-export`, {
        method: 'GET',
        headers: token ? { Authorization: `Bearer ${token}`, Accept: 'application/json' } : { Accept: 'application/json' },
      })
      const bodyText = await response.text()
      if (!response.ok) {
        let errorMessage = bodyText || response.statusText
        try {
          const parsed = JSON.parse(bodyText)
          errorMessage = parsed?.detail || errorMessage
        } catch {
          // keep raw backend response
        }
        throw new Error(errorMessage || 'Debugexport downloaden mislukt.')
      }
      downloadBlob(new Blob([bodyText], { type: 'application/json;charset=utf-8' }), `rezzerv-kassa-debug-${receiptId}.json`)
      setMessage('Debug JSON is gedownload.')
    } catch (error) {
      setMessage(normalizeErrorMessage(error?.message) || 'Debugexport downloaden mislukt.')
    } finally {
      setIsDownloading(false)
    }
  }

  return (
    <div className="rz-receipt-debug-export" data-testid="receipt-debug-export-panel">
      <Button
        type="button"
        variant="secondary"
        onClick={handleDownloadDebugJson}
        disabled={isDownloading}
        data-testid="receipt-debug-download-button"
      >
        {isDownloading ? 'Debug downloaden…' : 'Download debug JSON'}
      </Button>
      {message ? <div className="rz-receipt-debug-export__message">{message}</div> : null}
    </div>
  )
}
