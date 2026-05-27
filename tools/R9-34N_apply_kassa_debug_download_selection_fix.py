from pathlib import Path

path = Path("frontend/src/features/receipts/KassaPage.jsx")
text = path.read_text(encoding="utf-8-sig")

replacements = [
    (
"""  const [openedReceiptId, setOpenedReceiptId] = useState('')
  const [openedReceipt, setOpenedReceipt] = useState(null)
  const [deletedReceiptIds, setDeletedReceiptIds] = useState(() => loadStoredReceiptIds(DELETED_RECEIPTS_STORAGE_KEY))
""",
"""  const [openedReceiptId, setOpenedReceiptId] = useState('')
  const [openedReceipt, setOpenedReceipt] = useState(null)
  const openedReceiptIdRef = useRef('')
  const [deletedReceiptIds, setDeletedReceiptIds] = useState(() => loadStoredReceiptIds(DELETED_RECEIPTS_STORAGE_KEY))
"""
    ),
    (
"""  useEffect(() => {
    return () => {
      if (transientReceiptPreview?.originalUrl) window.URL.revokeObjectURL(transientReceiptPreview.originalUrl)
      if (transientReceiptPreview?.processedUrl) window.URL.revokeObjectURL(transientReceiptPreview.processedUrl)
    }
  }, [transientReceiptPreview])

""",
"""  useEffect(() => {
    return () => {
      if (transientReceiptPreview?.originalUrl) window.URL.revokeObjectURL(transientReceiptPreview.originalUrl)
      if (transientReceiptPreview?.processedUrl) window.URL.revokeObjectURL(transientReceiptPreview.processedUrl)
    }
  }, [transientReceiptPreview])

  useEffect(() => {
    openedReceiptIdRef.current = String(openedReceiptId || '')
  }, [openedReceiptId])

"""
    ),
    (
"""      const activeReceiptId = String(options?.openReceiptId || openedReceiptId || '')""",
"""      const activeReceiptId = String(options?.openReceiptId || openedReceiptIdRef.current || openedReceiptId || '')"""
    ),
    (
"""  async function downloadParsingDebug() {
    if (!receipt?.id) return
    try {
      const token = localStorage.getItem('rezzerv_token') || ''
      const response = await fetch(`/api/receipts/${encodeURIComponent(receipt.id)}/debug-export`, {
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
      const json = JSON.stringify(payload, null, 2)
      window.__rezzervLastDownload = {
        filename: `rezzerv-kassa-debug-${receipt?.id || 'bon'}.json`,
        source: 'receipt-debug',
        receiptId: receipt?.id || null,
        json,
      }
      const blob = new Blob([json], { type: 'application/json;charset=utf-8;' })
      const url = window.URL.createObjectURL(blob)
      const link = document.createElement('a')
      link.href = url
      link.download = `rezzerv-kassa-debug-${receipt?.id || 'bon'}.json`
      document.body.appendChild(link)
      link.click()
      link.remove()
      window.URL.revokeObjectURL(url)
      onFeedback?.('success', 'Parsing-debug is gedownload.')
    } catch (err) {
      onFeedback?.('error', normalizeErrorMessage(err?.message) || 'Parsing-debug kon niet worden gedownload.')
    }
  }
""",
"""  async function downloadParsingDebug(event) {
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
"""
    ),
]

for old, new in replacements:
    if old not in text:
        raise SystemExit("R9-34N patch failed: expected block not found")
    text = text.replace(old, new, 1)

path.write_text(text, encoding="utf-8")
print("R9-34N patch applied to frontend/src/features/receipts/KassaPage.jsx")
