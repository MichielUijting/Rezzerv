import { useEffect, useState } from 'react'
import { fetchJsonWithAuth } from '../../lib/authSession'
import { useAppFeedback } from '../../ui/AppFeedbackProvider.jsx'
import ArticleBarcodeScanAction from '../barcodes/ArticleBarcodeScanAction.jsx'

/** One named Catalogus product. Desktop stays manual; mobile can scan directly. */
export default function CatalogBarcodeEntry({
  globalProductId, primaryGtin, productName = '', canEdit, canReplace = false,
  mobile, onSaved,
}) {
  const [gtin, setGtin] = useState('')
  const [saving, setSaving] = useState(false)
  const { showFeedback } = useAppFeedback()
  const known = String(primaryGtin || '').trim()

  useEffect(() => { setGtin('') }, [globalProductId, primaryGtin])

  if (!canEdit) {
    return known ? null : <p>Nog geen barcode bekend. Een bevoegd catalogusbeheerder kan deze toevoegen.</p>
  }

  async function persistBarcode(value, { replace = false, expectedOldBarcode = '' } = {}) {
    if (replace && !canReplace) {
      throw new Error('Alleen een bevoegd Catalogusbeheerder kan een bestaande barcode vervangen.')
    }
    const url = replace
      ? `/api/catalog/${encodeURIComponent(globalProductId)}/gtin/replace`
      : `/api/catalog/${encodeURIComponent(globalProductId)}/gtin`
    const response = await fetchJsonWithAuth(url, {
      method: 'PUT',
      body: JSON.stringify({
        gtin: String(value).trim(),
        ...(replace ? { expected_old_gtin: expectedOldBarcode } : {}),
      }),
    })
    const result = await response.json().catch(() => ({}))
    if (!response.ok) throw new Error(typeof result?.detail === 'string'
      ? result.detail : 'Deze barcode kon niet veilig aan dit Catalogusartikel worden gekoppeld.')
    onSaved?.(String(result.gtin))
    return result
  }

  async function saveManual(event) {
    event.preventDefault()
    if (!gtin.trim() || saving || known) return
    setSaving(true)
    try {
      await persistBarcode(gtin.trim())
      showFeedback({ variant: 'success', message: 'Barcode opgeslagen in de Catalogus.' })
    } catch (error) {
      showFeedback({ variant: 'error', message: error?.message || 'Barcode niet opgeslagen.' })
    } finally {
      setSaving(false)
    }
  }

  return (
    <section className={mobile ? 'rz-mobile-catalog-detail-card' : 'rz-catalog-detail-section'}
      data-testid="catalog-shared-gtin-entry">
      <h3>Barcode voor {productName || 'Catalogusartikel'}</h3>
      <p>Huidige barcode: <strong>{known || 'Geen barcode'}</strong></p>
      <p>Deze barcode geldt voor de centrale Catalogus. Scannen verandert geen voorraad.</p>
      {!known ? <form onSubmit={saveManual}>
        <label htmlFor="catalog-shared-gtin-input">Barcode (EAN/GTIN) handmatig invoeren</label>
        <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap', marginTop: 6 }}>
          <input id="catalog-shared-gtin-input" className="rz-input" inputMode="numeric"
            autoComplete="off" value={gtin} onChange={(event) => setGtin(event.target.value)}
            disabled={saving} placeholder="Barcode invoeren"
            data-testid="catalog-shared-gtin-input" />
          <button type="submit" className="rz-button-primary"
            disabled={saving || !gtin.trim()} data-testid="catalog-shared-gtin-save">
            {saving ? 'Opslaan…' : 'Opslaan'}
          </button>
        </div>
      </form> : null}
      {mobile && (known ? canReplace : canEdit) ? (
        <ArticleBarcodeScanAction articleName={productName || 'Catalogusartikel'}
          currentBarcode={known} disabled={saving} onConfirm={persistBarcode}
          testId="catalog-shared-gtin-scan" />
      ) : null}
    </section>
  )
}
