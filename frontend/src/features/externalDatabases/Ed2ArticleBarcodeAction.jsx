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
  async function prepare(barcode, { replace, expectedOldBarcode }) {
    if (!replace) return null
    if (previous !== expectedOldBarcode) {
      throw new Error('De bestaande barcode is gewijzigd. Open het artikel opnieuw.')
    }
    const lidl = isLidl(item) && Boolean(item.manual_barcode)
    const data = lidl
      ? { receipt_item_id: item.id, new_gtin: barcode }
      : { receipt_item_id: item.id, mode: 'use_other', new_gtin: barcode }
    const route = lidl
      ? '/api/catalog/ed2/manual-barcodes/lidl/preview-correction'
      : '/api/catalog/ed2/manual-barcodes/conflicts/preview'
    const preview = await request(route, data)
    if (!preview.can_confirm || !preview.preview_fingerprint) {
      throw new Error((preview.blocked_reasons || []).join(' ')
        || 'Deze barcode heeft bestaande koppelingen en kan niet veilig worden vervangen.')
    }
    return {
      lidl, data, preview,
      detail: 'De bestaande winkel- en Cataloguskoppelingen zijn gecontroleerd. Alleen de correctie voor dit exacte bonartikel wordt toegepast. Bestaande kassabonnen, huishoudartikelen en voorraad blijven behouden.',
    }
  }

  async function confirm(barcode, { replace, expectedOldBarcode, prepared }) {
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

    // The user saw this exact server-side impact preview in the same
    // Save/Replace/Cancel overlay, before authorizing the correction.
    if (!prepared?.preview?.can_confirm || !prepared.preview.preview_fingerprint
        || prepared.data?.new_gtin !== barcode || prepared.data.receipt_item_id !== item.id) {
      throw new Error('De verplichte gevolgencontrole ontbreekt. Scan opnieuw.')
    }
    const route = prepared.lidl
      ? '/api/catalog/ed2/manual-barcodes/lidl/confirm-correction'
      : '/api/catalog/ed2/manual-barcodes/conflicts/confirm'
    const response = await request(route, {
      ...prepared.data,
      ...(prepared.lidl ? { expected_old_gtin: expectedOldBarcode } : {}),
      preview_fingerprint: prepared.preview.preview_fingerprint,
    })
    if (response.corrected !== true) {
      throw new Error('De barcodevervanging is niet bevestigd. De vorige barcode blijft behouden.')
    }
    onSaved?.({ status: 'success', message: 'Barcode vervangen voor ' + item.receipt_line_text })
  }
  return <ArticleBarcodeScanAction articleName={item.receipt_line_text}
    currentBarcode={previous} prepareConfirmation={prepare} onConfirm={confirm}
    showSuccessOnConfirm={false}
    testId="ed2-article-barcode-scan" />
}
