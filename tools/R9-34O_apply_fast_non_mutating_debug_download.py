from pathlib import Path

path = Path("frontend/src/features/receipts/KassaPage.jsx")
text = path.read_text(encoding="utf-8-sig")

old = """  async function downloadParsingDebug() {
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
"""

new = """  async function downloadParsingDebug(event) {
    event?.preventDefault?.()
    event?.stopPropagation?.()
    const receiptId = String(receipt?.id || '')
    if (!receiptId) return
    try {
      const payload = {
        receipt,
        stored_lines_raw: Array.isArray(receipt?.lines) ? receipt.lines : [],
        export_mode: 'stored_snapshot_frontend',
        scope: {
          read_only: true,
          non_mutating: true,
          backend_reparse_executed: false,
          ocr_executed: false,
          photo_normalization_executed: false,
          parser_changed: false,
          status_classification_changed: false,
          po_norm_status_label_touched: false,
        },
        exported_at: new Date().toISOString(),
      }
      const json = JSON.stringify(payload, null, 2)
      const filename = `rezzerv-kassa-debug-${receiptId}.json`
      window.__rezzervLastDownload = {
        filename,
        source: 'receipt-debug-stored-snapshot',
        receiptId,
        json,
      }
      const blob = new Blob([json], { type: 'application/json;charset=utf-8;' })
      const url = window.URL.createObjectURL(blob)
      const link = document.createElement('a')
      link.href = url
      link.download = filename
      document.body.appendChild(link)
      link.click()
      link.remove()
      window.URL.revokeObjectURL(url)
      onFeedback?.('success', 'Parsing-debug is gedownload zonder heranalyse.')
    } catch (err) {
      onFeedback?.('error', normalizeErrorMessage(err?.message) || 'Parsing-debug kon niet worden gedownload.')
    }
  }
"""

if old not in text:
    raise SystemExit("R9-34O patch failed: downloadParsingDebug block not found")

text = text.replace(old, new, 1)
path.write_text(text, encoding="utf-8")
print("R9-34O patch applied to frontend/src/features/receipts/KassaPage.jsx")
