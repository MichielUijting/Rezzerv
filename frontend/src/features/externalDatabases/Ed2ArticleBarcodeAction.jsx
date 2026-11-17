import ArticleBarcodeScanAction from '../barcodes/ArticleBarcodeScanAction.jsx'
import { fetchJsonWithAuth } from '../../lib/authSession.js'

function gtinFromItem(item) {
  return String(item?.manual_barcode || item?.article_code || '').trim()
}
function isLidl(item) {
  return ['lidl', 'lidl-nederland', 'lidl-nederland-gmbh'].includes(
    String(item?.retailer_code || '').trim().toLowerCase().replaceAll('_', '-'))
}
async function request(url, payload) {
  const response = await fetchJsonWithAuth(url, {
    method: 'POST',
    body: JSON.stringify(payload),
  })
  const body = await response.json().catch(() => ({}))
  if (!response.ok) throw new Error(typeof body.detail === 'string'
    ? body.detail : body.detail?.message || 'De barcode kon niet veilig worden verwerkt.')
  return body
}

/** Scan button belongs to the exact ED2 receipt item, never to the worklist. */
export default function Ed2ArticleBarcodeAction({ item, onSaved }) {
  if (!item?.id) return null
  const previous = gtinFromItem(item)
  async function confirm(barcode, { replace, expectedOldBarcode }) {
    if (!replace) {
      const data = await request('/api/catalog/ed2/manual-barcodes', {
        receipt_item_id: item.id, gtin: barcode,
      })
      if (data.saved !== true || data.catalog_linked !== true) {
        throw new Error('Opslag is niet bevestigd. De bestaande koppeling is behouden.')
      }
      onSaved?.({ status: 'success', message: 'Barcode bevestigd voor ' + item.receipt_line_text })
      return
    }
    if (gtinFromItem(item) !== expectedOldBarcode) {
      throw new Error('De bestaande barcode is gewijzigd. Open het artikel opnieuw.')
    }

    // Old retailer claims can affect other data. Always use the repository's
    // immutable preview fingerprint and authorized correction endpoint.
    if (isLidl(item) && item.manual_barcode) {
      const preview = await request('/api/catalog/ed2/manual-barcodes/lidl/preview-correction', {
        receipt_item_id: item.id, new_gtin: barcode,
      })
      if (!preview.can_confirm) throw new Error(
        (preview.blocked_reasons || []).join(' ') || 'Deze Lidl-correctie is niet veilig.'
      )
      const result = await request('/api/catalog/ed2/manual-barcodes/lidl/confirm-correction', {
        receipt_item_id: item.id,
        new_gtin: barcode,
        expected_old_gtin: expectedOldBarcode,
        preview_fingerprint: preview.preview_fingerprint,
      })
      if (result.corrected !== true) throw new Error('Barcodevervanging is niet bevestigd.')
    } else {
      const data = { receipt_item_id: item.id, mode: 'use_other', new_gtin: barcode }
      const preview = await request('/api/catalog/ed2/manual-barcodes/conflicts/preview', data)
      if (!preview.can_confirm) throw new Error(
        (preview.blocked_reasons || []).join(' ') ||
        'Deze barcode kan niet automatisch worden vervangen. Gebruik de bestaande conflictcontrole.'
      )
      const result = await request('/api/catalog/ed2/manual-barcodes/conflicts/confirm', {
        ...data, preview_fingerprint: preview.preview_fingerprint,
      })
      if (result.corrected !== true) throw new Error('Barcodevervanging is niet bevestigd.')
    }
    onSaved?.({ status: 'success', message: 'Barcode vervangen voor ' + item.receipt_line_text })
  }
  return <ArticleBarcodeScanAction articleName={item.receipt_line_text}
    currentBarcode={previous} onConfirm={confirm}
    testId="ed2-article-barcode-scan" />
}
