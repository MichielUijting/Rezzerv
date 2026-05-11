const DEBUG_BUTTON_ID = 'rezzerv-download-debug-json-button'
const DEBUG_PATCH_MARKER = '__rezzervReceiptDebugExportPatchInstalled'
const ACTIVE_RECEIPT_KEY = 'rezzerv_active_receipt_table_id'

function getToken() {
  try {
    return window.localStorage.getItem('rezzerv_token') || ''
  } catch {
    return ''
  }
}

function rememberReceiptIdFromUrl(input) {
  const url = typeof input === 'string' ? input : String(input?.url || '')
  const match = url.match(/\/api\/receipts\/([^/?#]+)(?:\/preview|\/debug-export|\b)/)
  if (!match?.[1]) return
  try {
    window.sessionStorage.setItem(ACTIVE_RECEIPT_KEY, decodeURIComponent(match[1]))
  } catch {
    // ignore storage errors
  }
}

function installFetchObserver() {
  if (window[DEBUG_PATCH_MARKER]) return
  window[DEBUG_PATCH_MARKER] = true
  const originalFetch = window.fetch.bind(window)
  window.fetch = async (input, init) => {
    rememberReceiptIdFromUrl(input)
    return originalFetch(input, init)
  }
}

function findActiveReceiptId() {
  try {
    const stored = window.sessionStorage.getItem(ACTIVE_RECEIPT_KEY)
    if (stored) return stored
  } catch {
    // ignore storage errors
  }
  const candidates = Array.from(document.querySelectorAll('[data-receipt-id], [data-receipt-table-id]'))
  for (const candidate of candidates) {
    const receiptId = candidate.getAttribute('data-receipt-id') || candidate.getAttribute('data-receipt-table-id')
    if (receiptId) return receiptId
  }
  return ''
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

async function downloadDebugJson(button) {
  const receiptId = findActiveReceiptId()
  if (!receiptId) {
    window.alert('Selecteer eerst een kassabon. Open daarna opnieuw Download debug JSON.')
    return
  }
  const token = getToken()
  const previousText = button.textContent
  button.disabled = true
  button.textContent = 'Debug downloaden…'
  try {
    const response = await fetch(`/api/receipts/${encodeURIComponent(receiptId)}/debug-export`, {
      method: 'GET',
      headers: token ? { Authorization: `Bearer ${token}`, Accept: 'application/json' } : { Accept: 'application/json' },
    })
    const bodyText = await response.text()
    if (!response.ok) {
      let message = bodyText || response.statusText
      try {
        const parsed = JSON.parse(bodyText)
        message = parsed?.detail || message
      } catch {
        // keep raw message
      }
      throw new Error(message || 'Debugexport downloaden mislukt.')
    }
    const blob = new Blob([bodyText], { type: 'application/json;charset=utf-8' })
    downloadBlob(blob, `rezzerv-kassa-debug-${receiptId}.json`)
  } catch (error) {
    window.alert(`Debugexport downloaden mislukt: ${error?.message || error}`)
  } finally {
    button.disabled = false
    button.textContent = previousText || 'Download debug JSON'
  }
}

function createDebugButton() {
  const button = document.createElement('button')
  button.id = DEBUG_BUTTON_ID
  button.type = 'button'
  button.textContent = 'Download debug JSON'
  button.className = 'rz-button rz-button--secondary'
  button.style.marginLeft = '8px'
  button.style.whiteSpace = 'nowrap'
  button.addEventListener('click', () => downloadDebugJson(button))
  return button
}

function mountDebugButton() {
  if (!window.location.pathname.startsWith('/kassa')) return
  if (document.getElementById(DEBUG_BUTTON_ID)) return

  const buttons = Array.from(document.querySelectorAll('button, a'))
  const parsingButton = buttons.find((button) => /download\s+parsing/i.test(String(button.textContent || '')))
  if (!parsingButton || !parsingButton.parentElement) return

  parsingButton.insertAdjacentElement('afterend', createDebugButton())
}

export function installReceiptDebugExportPatch() {
  if (typeof window === 'undefined' || typeof document === 'undefined') return
  installFetchObserver()
  const observer = new MutationObserver(() => mountDebugButton())
  observer.observe(document.documentElement, { childList: true, subtree: true })
  window.addEventListener('focus', mountDebugButton)
  window.addEventListener('hashchange', mountDebugButton)
  window.addEventListener('popstate', mountDebugButton)
  window.setTimeout(mountDebugButton, 250)
}
