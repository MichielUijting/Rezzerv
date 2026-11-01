import { useState } from 'react'
import Button from '../../ui/Button'
import { fetchJsonWithAuth } from '../../lib/authSession'

/** Manual ED2 barcode evidence is NOT a confirmed Catalogus / stock link. */
export default function Ed2ManualBarcodeEntry({ item, onSaved }) {
  const [barcode, setBarcode] = useState('')
  const [confirm, setConfirm] = useState(false)
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState('')
  const validLength = /^(?:[0-9]{8}|[0-9]{12,14})$/.test(barcode.trim())
  const canSave = !item.link_status || item.link_status === 'unlinked'

  async function save() {
    if (!validLength || !canSave || saving) return
    setConfirm(false)
    setError('')
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
        setError(message)
      }
    } finally {
      window.clearTimeout(timeout)
      setSaving(false)
    }
  }

  if (!canSave) return null
  return (
    <section className="rz-external-manual-barcode" aria-label="Barcode handmatig opslaan" data-testid="ed2-manual-barcode-entry">
      <h4>Barcode handmatig opslaan</h4>
      <p>Inhuis zoekt de barcode eerst exact in Open Food Facts. Als OFF het product niet kent of tijdelijk niet bereikbaar is, wordt de ingevoerde barcode toch bewaard. Er ontstaat geen automatische voorraadkoppeling.</p>
      <div className="rz-external-off-manual-form">
        <label className="rz-input-field">
          <span className="rz-label">Barcode (EAN/GTIN)</span>
          <input className="rz-input" inputMode="numeric" autoComplete="off" value={barcode}
            onChange={(event) => { setBarcode(event.target.value); setError('') }}
            maxLength={14} aria-label="Barcode handmatig invoeren"
            data-testid="ed2-manual-barcode-input" />
        </label>
        <Button type="button" disabled={!validLength || saving}
          onClick={() => setConfirm(true)} data-testid="ed2-manual-barcode-save">
          {saving ? 'Opslaan...' : 'Barcode opslaan'}
        </Button>
      </div>
      {error ? <p role="alert">{error}</p> : null}
      {confirm ? <div className="rz-modal-backdrop">
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
