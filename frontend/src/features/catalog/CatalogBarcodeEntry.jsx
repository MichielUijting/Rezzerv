import { useEffect, useState } from 'react'
import { fetchJsonWithAuth } from '../../lib/authSession'
import useBarcodeScanner from '../../lib/useBarcodeScanner'
import BarcodeScannerModal from '../barcodes/BarcodeScannerModal'

/** One shared Catalogus editor for the desktop and mobile article detail. */
export default function CatalogBarcodeEntry({ globalProductId, primaryGtin, canEdit, mobile, onSaved }) {
  const [gtin, setGtin] = useState('')
  const [saving, setSaving] = useState(false)
  const [message, setMessage] = useState('')
  const [error, setError] = useState('')
  const {
    videoRef, isOpen, cameraState, cameraMeta, availableCameras,
    startScanner, stopScanner, switchCamera,
  } = useBarcodeScanner({
    screenContext: 'Catalogus gedeelde barcode',
    onDetected: (detected) => {
      setGtin(String(detected || '').trim())
      setError('')
      setMessage('Barcode gevonden. Controleer de code en bevestig met Opslaan.')
      stopScanner(true)
    },
  })

  useEffect(() => {
    setGtin('')
    setMessage('')
    setError('')
    stopScanner()
  }, [globalProductId, primaryGtin, stopScanner])

  if (String(primaryGtin || '').trim()) return null
  if (!canEdit) {
    return <p className="rz-inline-feedback">Nog geen barcode bekend. Een bevoegd catalogusbeheerder kan deze toevoegen.</p>
  }

  async function saveBarcode(event) {
    event.preventDefault()
    if (!gtin.trim() || saving) return
    setSaving(true)
    setMessage('')
    setError('')
    try {
      const response = await fetchJsonWithAuth(
        `/api/catalog/${encodeURIComponent(globalProductId)}/gtin`,
        { method: 'PUT', body: JSON.stringify({ gtin: gtin.trim() }) },
      )
      const result = await response.json().catch(() => ({}))
      if (!response.ok) throw new Error(result?.detail || 'De barcode kon niet worden opgeslagen.')
      onSaved(String(result.gtin))
      setMessage('De barcode is centraal in de Catalogus opgeslagen.')
    } catch (saveError) {
      setError(saveError?.message || 'De barcode kon niet worden opgeslagen.')
    } finally {
      setSaving(false)
    }
  }

  return (
    <section className={mobile ? 'rz-mobile-catalog-detail-card' : 'rz-catalog-detail-section'} data-testid="catalog-shared-gtin-entry">
      <h3>Barcode toevoegen aan Catalogus</h3>
      <p>Deze barcode geldt voor alle huishoudens. Er wordt geen voorraad aangepast.</p>
      <form onSubmit={saveBarcode}>
        <label htmlFor="catalog-shared-gtin-input">Barcode (EAN/GTIN)</label>
        <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap', marginTop: 6 }}>
          <input
            id="catalog-shared-gtin-input"
            className="rz-input"
            inputMode="numeric"
            autoComplete="off"
            value={gtin}
            onChange={(event) => setGtin(event.target.value)}
            disabled={saving}
            placeholder="Barcode invoeren"
            data-testid="catalog-shared-gtin-input"
          />
          <button type="submit" className="rz-button-primary" disabled={saving || !gtin.trim()} data-testid="catalog-shared-gtin-save">
            {saving ? 'Opslaan…' : 'Opslaan'}
          </button>
          {mobile ? (
            <button type="button" className="rz-button-secondary" onClick={() => startScanner()} disabled={saving} data-testid="catalog-shared-gtin-scan">
              Barcode scannen
            </button>
          ) : null}
        </div>
      </form>
      {error ? <p role="alert" className="rz-inline-feedback rz-inline-feedback--error">{error}</p> : null}
      {message ? <p role="status" className="rz-inline-feedback rz-inline-feedback--success">{message}</p> : null}
      <BarcodeScannerModal
        open={isOpen}
        title="Barcode scannen voor Catalogus"
        videoRef={videoRef}
        cameraState={cameraState}
        cameraMeta={cameraMeta}
        availableCameras={availableCameras}
        onSwitchCamera={switchCamera}
        onClose={() => stopScanner()}
      />
    </section>
  )
}
