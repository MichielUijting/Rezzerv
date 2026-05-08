const RECEIPT_UPLOAD_ENDPOINTS = new Set([
  '/api/receipts/import',
  '/api/receipts/share-import',
  '/api/receipts/email-import',
])

let isInstalled = false
let originalFetch = null

function isReceiptUploadRequest(resource) {
  const url = typeof resource === 'string' ? resource : resource?.url
  if (!url) return false
  try {
    const parsed = new URL(url, window.location.origin)
    return RECEIPT_UPLOAD_ENDPOINTS.has(parsed.pathname)
  } catch {
    return RECEIPT_UPLOAD_ENDPOINTS.has(String(url))
  }
}

function extractDetailFromBody(responseBody, statusText) {
  if (!responseBody) return statusText || 'Geen backend-detail ontvangen.'
  try {
    const parsedJson = JSON.parse(responseBody)
    return parsedJson?.detail || parsedJson?.message || responseBody
  } catch {
    return responseBody
  }
}

export function buildReceiptUploadErrorDetail(status, detail) {
  const normalizedDetail = String(detail || 'Geen backend-detail ontvangen.').trim()
  return `Upload mislukt (HTTP ${status}): ${normalizedDetail}`
}

export function installReceiptUploadErrorHandling() {
  if (isInstalled || typeof window === 'undefined' || typeof window.fetch !== 'function') return false
  originalFetch = window.fetch.bind(window)

  window.fetch = async function receiptUploadFetch(resource, init) {
    const response = await originalFetch(resource, init)
    if (!isReceiptUploadRequest(resource) || response.ok) return response

    const responseBody = await response.clone().text()
    const parsedDetail = extractDetailFromBody(responseBody, response.statusText)
    const detail = buildReceiptUploadErrorDetail(response.status, parsedDetail)

    console.error('Rezzerv receipt upload failed', {
      endpoint: typeof resource === 'string' ? resource : resource?.url,
      status: response.status,
      statusText: response.statusText,
      responseBody,
      parsedDetail,
    })

    return new Response(JSON.stringify({ detail }), {
      status: response.status,
      statusText: response.statusText,
      headers: { 'content-type': 'application/json' },
    })
  }

  isInstalled = true
  return true
}
