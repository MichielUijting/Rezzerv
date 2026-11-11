import { useEffect, useState } from 'react'
import Button from '../../ui/Button'
import { fetchJsonWithAuth } from '../../lib/authSession'
import { useAppFeedback } from '../../ui/AppFeedbackProvider.jsx'

/** Manual ED2 barcode evidence is NOT a confirmed Catalogus / stock link. */
export default function Ed2ManualBarcodeEntry({ item, onSaved, scannedBarcode = null }) {
  const { showFeedback } = useAppFeedback()
  const [barcode, setBarcode] = useState('')
  const [confirm, setConfirm] = useState(false)
  const [saving, setSaving] = useState(false)
  const [checkingCatalog, setCheckingCatalog] = useState(false)
  const validLength = /^(?:[0-9]{8}|[0-9]{12,14})$/.test(barcode.trim())
  const canSave = !item.link_status || item.link_status === 'unlinked'
  const canConfirm = canSave || item.link_status === 'classification_pending'

  useEffect(() => {
    setBarcode('')
    setConfirm(false)
  }, [item.id])

  useEffect(() => {
    if (scannedBarcode?.receiptItemId !== item.id || !canConfirm) return
    setBarcode(String(scannedBarcode.value || '').trim())
    // A scan is not a write. Show the verified product before the user confirms.
    if (item.receipt_article_number && item.id?.startsWith('receipt-table-line:')) {
      void checkAndConfirmCatalog(String(scannedBarcode.value || '').trim())
    } else {
      setConfirm(true)
    }
  }, [scannedBarcode, item.id, canSave])

  async function checkAndConfirmCatalog(candidateBarcode = barcode.trim()) {
    if (checkingCatalog || saving || !canConfirm) return
    if (!item.receipt_article_number || !item.id?.startsWith('receipt-table-line:')) {
      showFeedback({ variant: 'warning', title: 'Artikelcode ontbreekt',
        message: 'Een bewezen kassabonartikelcode is nodig om de barcode centraal te koppelen. U kunt de barcode wel apart opslaan.' })
      return
    }
    if (!/^(?:[0-9]{8}|[0-9]{12,14})$/.test(candidateBarcode)) {
      showFeedback({ variant: 'error', message: 'Vul eerst een geldige GTIN van 8, 12, 13 of 14 cijfers in.' })
      return
    }
    setCheckingCatalog(true)
    try {
      const response = await fetchJsonWithAuth(`/api/barcodes/${encodeURIComponent(candidateBarcode)}`)
      const result = await response.json().catch(() => ({}))
      if (!response.ok) throw new Error(typeof result.detail === 'string' ? result.detail : 'Cataloguscontrole mislukt.')
      const product = result.product
      if (!result.valid || !product || !['matched', 'incomplete'].includes(result.match_status)
          || String(product.status || 'active').toLowerCase() !== 'active') {
        showFeedback({
          variant: 'warning', title: 'Nog geen bewezen Catalogusidentiteit',
          message: 'Deze barcode verwijst nog niet naar precies één actief Catalogusproduct. Bewaar de barcode als aanwijzing of koppel eerst een gecontroleerd product uit OFF.',
          testId: 'ed2-catalog-identity-not-found',
        })
        return
      }
      showFeedback({
        variant: 'warning', title: 'Catalogusidentiteit bevestigen',
        message: `Koppel winkelartikelcode ${item.receipt_article_number} van ${item.retailer || item.retailer_code} aan ${product.name || 'dit Catalogusproduct'}?`,
        detail: `Barcode: ${candidateBarcode}. Deze koppeling wordt centraal hergebruikt; GS1/CBS-classificatie is hiervoor niet vereist.`,
        primaryActionLabel: 'Koppelen', secondaryActionLabel: 'Annuleren',
        dismissMode: 'blocked',
        testId: 'ed2-catalog-identity-confirm',
        onPrimaryAction: async () => {
          const saved = await fetchJsonWithAuth('/api/barcodes/confirm-retailer-code', {
            method: 'POST', headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
              receipt_item_id: item.id, retailer_code: item.retailer_code,
              external_article_code: item.receipt_article_number,
              gtin: candidateBarcode,
            }),
          })
          const payload = await saved.json().catch(() => ({}))
          if (!saved.ok || !['confirmed', 'already_confirmed'].includes(payload.status)) {
            throw new Error(typeof payload.detail === 'string' ? payload.detail : 'De artikelidentiteit kon niet worden bevestigd.')
          }
          onSaved({
            status: 'success',
            message: payload.status === 'already_confirmed'
              ? 'Deze winkelartikelcode was al aan het juiste Catalogusproduct gekoppeld.'
              : 'Winkelartikelcode en barcode definitief gekoppeld aan de Catalogus.',
          })
          return false
        },
      })
    } catch (err) {
      if (err.status !== 401) showFeedback({ variant: 'error', title: 'Cataloguscontrole mislukt',
        message: err.message || 'De barcode kon niet worden gecontroleerd.' })
    } finally {
      setCheckingCatalog(false)
    }
  }

  async function save() {
    if (!validLength || !canSave || saving) return
    setConfirm(false)
    setSaving(true)
    const controller = new AbortController()
    const timeout = window.setTimeout(() => controller.abort(), 30000)
    try {
      const response = await fetchJsonWithAuth('/api/catalog/ed2/manual-barcodes', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        signal: controller.signal,
        body: JSON.stringify({ receipt_item_id: item.id, gtin: barcode.trim() }),
      })
      const payload = await response.json().catch(() => ({}))
      if (!response.ok || payload.saved !== true) {
        throw new Error(typeof payload.detail === 'string' ? payload.detail : 'Barcode opslaan is niet bevestigd.')
      }
      onSaved({
        status: 'success',
        message: payload.off_found
          ? 'Barcode en beschikbare productgegevens uit OFF opgeslagen in Catalogus'
            + (payload.photo_loaded ? ', inclusief foto.' : '.')
            + (payload.classification_pending ? ' Officiële GS1-classificatie ontbreekt nog.' : '')
          : payload.off_unavailable
            ? 'Barcode opgeslagen. OFF is tijdelijk niet bereikbaar; foto en productgegevens zijn nog niet opgehaald. Er is geen Cataloguskoppeling gemaakt.'
            : 'Barcode handmatig opgeslagen. Niet gevonden in OFF; geen OFF-product, GS1-classificatie of Cataloguskoppeling aangemaakt.',
      })
    } catch (err) {
      if (err.status !== 401) {
        const message = err.name === 'AbortError'
          ? 'Opslaan is niet bevestigd. Controleer eerst de artikellijst voordat u opnieuw probeert.'
          : (err.message || 'Barcode opslaan is niet gelukt.')
        showFeedback({
          variant: 'error',
          title: 'Barcode niet opgeslagen',
          message: message.includes('OFF-productgegevens passen niet veilig')
            ? 'De gegevens van deze barcode komen niet voldoende overeen met het bonartikel. Controleer het product en de barcode. Er is niets opgeslagen.'
            : message,
          testId: 'ed2-manual-barcode-error',
        })
      }
    } finally {
      window.clearTimeout(timeout)
      setSaving(false)
    }
  }

  if (!canConfirm) return null
  return (
    <section className="rz-external-manual-barcode" aria-label="Barcode handmatig opslaan" data-testid="ed2-manual-barcode-entry">
      <h4>Barcode handmatig opslaan</h4>
      <p>Controleer en bevestig de barcode bij het gevonden Catalogusproduct. Staat dat product nog niet in de Catalogus? Bewaar dan eerst de barcode als aanwijzing; voorraad wordt niet aangepast.</p>
      <div className="rz-external-off-manual-form">
        <label className="rz-input-field">
          <span className="rz-label">Barcode (EAN/GTIN)</span>
          <input className="rz-input" inputMode="numeric" autoComplete="off" value={barcode}
            onChange={(event) => setBarcode(event.target.value)}
            maxLength={14} aria-label="Barcode handmatig invoeren"
            data-testid="ed2-manual-barcode-input" />
        </label>
        {item.receipt_article_number && item.id?.startsWith('receipt-table-line:') ? <Button
          type="button" disabled={!validLength || saving || checkingCatalog}
          onClick={() => void checkAndConfirmCatalog()} data-testid="ed2-catalog-identity-check">
          {checkingCatalog ? 'Controleren...' : 'Koppelen aan Catalogus'}
        </Button> : null}
        {canSave ? <Button type="button" variant="secondary" disabled={!validLength || saving || checkingCatalog}
          onClick={() => setConfirm(true)} data-testid="ed2-manual-barcode-save">
          {saving ? 'Opslaan...' : 'Barcode bewaren'}
        </Button> : null}
      </div>
      {canSave && confirm ? <div className="rz-modal-backdrop">
        <div className="rz-modal-card" role="alertdialog" aria-modal="true"
          aria-labelledby="ed2-manual-barcode-confirm">
          <p id="ed2-manual-barcode-confirm" className="rz-modal-text">
            Barcode <strong>{barcode.trim()}</strong> voor <strong>{item.receipt_line_text}</strong> opslaan?
            Inhuis zoekt eerst bij OFF. Zonder OFF-match of bij tijdelijke OFF-storing blijft de barcode bewaard zonder productkoppeling.
          </p>
          <div className="rz-modal-actions">
            <Button type="button" variant="secondary" onClick={() => setConfirm(false)}>Annuleren</Button>
            <Button type="button" onClick={save}>OK</Button>
          </div>
        </div>
      </div> : null}
    </section>
  )
}
