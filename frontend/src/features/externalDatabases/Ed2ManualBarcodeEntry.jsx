import { useEffect, useRef, useState } from 'react'
import Button from '../../ui/Button'
import { fetchJsonWithAuth, readStoredAuthContext } from '../../lib/authSession'
import { useAppFeedback } from '../../ui/AppFeedbackProvider.jsx'
import { ed2BarcodeIdentityState } from './ed2BarcodeIdentity.js'

/** Saving the barcode is confirmed Catalogus identification; OFF is optional. */
export default function Ed2ManualBarcodeEntry({ item, onSaved, scannedBarcode = null }) {
  const { showFeedback } = useAppFeedback()
  const lastConflictPrompted = useRef('')
  const identity = ed2BarcodeIdentityState(item)
  const hasBarcodeConflict = identity.barcodeConflict
  const mayResolveConflict = hasBarcodeConflict
    && Boolean(readStoredAuthContext()?.is_platform_superuser)
  const [barcode, setBarcode] = useState('')
  const [confirm, setConfirm] = useState(false)
  const [saving, setSaving] = useState(false)
  const [checkingCatalog, setCheckingCatalog] = useState(false)
  const [correctionBarcode, setCorrectionBarcode] = useState('')
  const [correcting, setCorrecting] = useState(false)
  const isLidl = ['lidl', 'lidl-nederland', 'lidl-nederland-gmbh'].includes(
    String(item.retailer_code || '').trim().toLowerCase().replaceAll('_', '-'))
  const mayCorrectLidl = isLidl && Boolean(item.manual_barcode)
  const correctionValid = /^(?:[0-9]{8}|[0-9]{12,14})$/.test(correctionBarcode.trim())
    && correctionBarcode.trim() !== String(item.manual_barcode || '').trim()
  const validLength = /^(?:[0-9]{8}|[0-9]{12,14})$/.test(barcode.trim())
  const canSave = (!item.link_status || item.link_status === 'unlinked') && !item.manual_barcode
  const canConfirm = canSave || item.link_status === 'classification_pending' || mayCorrectLidl

  useEffect(() => {
    setBarcode('')
    setCorrectionBarcode('')
    setConfirm(false)
  }, [item.id, item.manual_barcode])

  useEffect(() => {
    if (scannedBarcode?.receiptItemId !== item.id || !canConfirm) return
    if (mayCorrectLidl) {
      // An existing Lidl barcode is corrected only via the impact-preview flow.
      setCorrectionBarcode(String(scannedBarcode.value || '').trim())
      return
    }
    setBarcode(String(scannedBarcode.value || '').trim())
    // A scan is not a write. Show the verified product before the user confirms.
    // A scan is only input: storing the barcode itself proves identity.
    // The older "confirm existing Catalogus link" route remains an explicit
    // alternative, never the default scanner outcome for an unlinked item.
    if (canSave) {
      setConfirm(true)
    } else if (item.receipt_article_number && item.id?.startsWith('receipt-table-line:')) {
      void checkAndConfirmCatalog(String(scannedBarcode.value || '').trim())
    } else {
      showFeedback({ variant: 'warning', title: 'Winkelartikelcode ontbreekt',
        message: 'Een winkelartikelcode is nodig om de gescande GTIN centraal te bevestigen.' })
    }
  }, [scannedBarcode, item.id, canConfirm, mayCorrectLidl])

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
          message: canSave
            ? 'Deze barcode is nog niet bekend in de Catalogus. Via Barcode opslaan in Catalogus bevestig je de identificatie; Inhuis maakt zo nodig een nieuw product aan.'
            : 'Deze bestaande artikelkoppeling vraagt eerst om beoordeling. Er is niets gewijzigd.',
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
          const repaired = Number(payload.historical_repair?.updated || 0)
          const deferred = payload.historical_repair?.status === 'deferred'
          onSaved({
            status: deferred ? 'warning' : 'success',
            message: (payload.status === 'already_confirmed'
              ? 'Deze winkelartikelcode was al aan het juiste Catalogusproduct gekoppeld.'
              : 'Winkelartikelcode en barcode definitief gekoppeld aan de Catalogus.')
              + (repaired ? ` ${repaired} bestaand huishoudartikel automatisch bijgewerkt.` : '')
              + (deferred ? ' Historische koppelingen zijn nog niet bijgewerkt; controle vereist.' : ''),
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


  async function previewCorrection() {
    if (!mayCorrectLidl || !correctionValid || saving || correcting || checkingCatalog) return
    const intended = correctionBarcode.trim()
    setCorrecting(true)
    try {
      const response = await fetchJsonWithAuth('/api/catalog/ed2/manual-barcodes/lidl/preview-correction', {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ receipt_item_id: item.id, new_gtin: intended }),
      })
      const preview = await response.json().catch(() => ({}))
      if (!response.ok) throw new Error(
        typeof preview.detail === 'string' ? preview.detail : 'De gevolgen konden niet worden opgehaald.')
      if (!preview.can_confirm) {
        showFeedback({
          variant: 'warning', title: 'Correctie nog niet veilig',
          message: (preview.blocked_reasons || []).join(' ') || 'Een bestaande koppeling moet eerst gecontroleerd worden.',
          detail: 'De oude barcode en alle Catalogus- en huishoudgegevens zijn ongewijzigd.',
          testId: 'ed2-lidl-correction-blocked',
        })
        return
      }
      const productLabel = preview.new_product_will_be_created
        ? 'een nieuw Catalogusproduct'
        : 'het bestaande Catalogusproduct'
      const oldProduct = preview.old_product_id
        ? 'Oud Catalogusproduct: ' + (preview.old_product_name || 'Naam onbekend')
          + ' (' + (preview.old_product_status === 'deleted' ? 'verwijderd' : 'bestaand') + '). '
        : 'Er was nog geen oude Catalogusverwijzing. '
      showFeedback({
        variant: 'warning', title: 'Lidl-barcode corrigeren',
        message: 'Barcode ' + preview.old_gtin + ' vervangen door ' + preview.new_gtin + '?',
        detail: 'Voor ' + item.receipt_line_text + ' (' + (item.receipt_article_number || 'zonder bonartikelnummer')
          + '). ' + oldProduct + 'De nieuwe code koppelt aan ' + productLabel
          + '. Bestaande externe koppelingen: ' + preview.legacy_link_count
          + '; huishoudartikelen op oud product: ' + preview.household_article_count
          + '. De oorspronkelijke bonnen, oude Catalogusproducten en voorraad blijven behouden. '
          + 'Alleen aantoonbaar eigen ED2-identiteitsclaims worden aangepast.',
        primaryActionLabel: 'Correctie bevestigen',
        secondaryActionLabel: 'Annuleren',
        dismissMode: 'blocked',
        testId: 'ed2-lidl-correction-confirm',
        onPrimaryAction: async () => {
          setCorrecting(true)
          try {
            const saved = await fetchJsonWithAuth('/api/catalog/ed2/manual-barcodes/lidl/confirm-correction', {
              method: 'POST', headers: { 'Content-Type': 'application/json' },
              body: JSON.stringify({
                receipt_item_id: item.id, new_gtin: preview.new_gtin,
                expected_old_gtin: preview.old_gtin,
                preview_fingerprint: preview.preview_fingerprint,
              }),
            })
            const result = await saved.json().catch(() => ({}))
            if (!saved.ok || result.corrected !== true) throw new Error(
              typeof result.detail === 'string' ? result.detail : 'Barcodecorrectie is niet bevestigd.')
            onSaved({
              status: 'success',
              message: 'Lidl-barcode gecorrigeerd van ' + result.old_gtin + ' naar '
                + result.gtin + ' en met registratie aan de Catalogus gekoppeld.',
            })
            return false
          } catch (error) {
            showFeedback({ variant: 'error', title: 'Barcode niet gecorrigeerd',
              message: error.message || 'Controleer de gegevens opnieuw; niets is bevestigd.' })
            return false
          } finally {
            setCorrecting(false)
          }
        },
      })
    } catch (error) {
      showFeedback({ variant: 'error', title: 'Gevolgencontrole mislukt',
        message: error.message || 'De correctie kan niet worden voorbereid.' })
    } finally {
      setCorrecting(false)
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
      if (!response.ok || payload.saved !== true || payload.catalog_linked !== true) {
        throw new Error(typeof payload.detail === 'string' ? payload.detail : 'Barcode opslaan is niet bevestigd.')
      }
      onSaved({
        status: 'success',
        message: 'Barcode opgeslagen en gekoppeld aan '
          + (payload.catalog_product_created ? 'een nieuw' : 'het bestaande')
          + ' Catalogusproduct.',
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

  function showBarcodeConflictOptions() {
    if (!mayResolveConflict) return
    showFeedback({
      variant: 'warning',
      title: 'Barcodeconflict: ' + item.receipt_line_text,
      message: 'Inhuis heeft twee afwijkende barcodes voor dit bonartikel. Welke is correct?',
      detail: 'Winkel: ' + (item.retailer || item.retailer_code)
        + '; bonartikelnummer: ' + (item.receipt_article_number || 'ontbreekt')
        + '. Er wordt nog niets gewijzigd. Een nieuwe barcode moet echt bij het product horen.',
      dismissMode: 'blocked',
      testId: 'ed2-barcode-conflict-options',
      inputFields: [
        {
          name: 'mode', label: 'Kies de juiste barcode', type: 'select', required: true,
          placeholder: 'Kies een barcodecorrectie',
          options: [
            { value: 'keep_catalog', label: 'Catalogusbarcode behouden: ' + item.article_code },
            { value: 'keep_manual', label: 'Handmatig opgeslagen barcode behouden: ' + item.manual_barcode },
            { value: 'use_other', label: 'Een andere barcode invoeren' },
          ],
        },
        {
          name: 'new_gtin', label: 'Andere EAN/GTIN (alleen bij de derde keuze)',
          type: 'text', value: '', placeholder: 'Vul een echte barcode in',
        },
      ],
      primaryActionLabel: 'Gevolgen bekijken',
      secondaryActionLabel: 'Annuleren',
      onPrimaryAction: async ({ mode, new_gtin }) => {
        if (mode === 'use_other' && !/^(?:[0-9]{8}|[0-9]{12,14})$/.test(String(new_gtin || '').trim())) {
          throw new Error('Vul bij de derde keuze een echte EAN/GTIN van 8, 12, 13 of 14 cijfers in.')
        }
        const data = { receipt_item_id: item.id, mode, new_gtin: mode === 'use_other'
          ? String(new_gtin || '').trim() : '' }
        const response = await fetchJsonWithAuth('/api/catalog/ed2/manual-barcodes/conflicts/preview', {
          method: 'POST', headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(data),
        })
        const preview = await response.json().catch(() => ({}))
        if (!response.ok) throw new Error(typeof preview.detail === 'string'
          ? preview.detail : 'De gevolgen konden niet worden gecontroleerd.')
        if (!preview.can_confirm) {
          showFeedback({
            variant: 'warning', title: 'Deze correctie is nog niet veilig',
            message: (preview.blocked_reasons || []).join(' ') || 'Een bestaande koppeling moet eerst beoordeeld worden.',
            detail: 'Er is niets gewijzigd. Kies eventueel een andere optie.',
            testId: 'ed2-barcode-conflict-blocked',
          })
          return false
        }
        showFeedback({
          variant: 'warning',
          title: 'Barcodecorrectie bevestigen',
          message: 'Voor ' + item.receipt_line_text + ' (' + (item.receipt_article_number || 'zonder bonartikelnummer')
            + ') wordt barcode ' + preview.new_gtin + ' gekozen.',
          detail: mode === 'keep_catalog'
            ? 'De afwijkende handmatige barcodeclaim wordt alleen voor dit bonartikel verwijderd. De overige Catalogusproducten, kassabonnen, huishoudartikelen en voorraad blijven behouden.'
            : 'De bestaande centrale koppeling wordt alleen voor deze exacte bonartikelidentiteit beëindigd en de gekozen barcode opnieuw gecontroleerd. Oude Catalogusproducten, kassabonnen, huishoudartikelen en voorraad blijven behouden.',
          primaryActionLabel: 'Correctie bevestigen',
          secondaryActionLabel: 'Terug',
          dismissMode: 'blocked',
          testId: 'ed2-barcode-conflict-confirm',
          onSecondaryAction: () => showBarcodeConflictOptions(),
          onPrimaryAction: async () => {
            const saved = await fetchJsonWithAuth('/api/catalog/ed2/manual-barcodes/conflicts/confirm', {
              method: 'POST', headers: { 'Content-Type': 'application/json' },
              body: JSON.stringify({ ...data, preview_fingerprint: preview.preview_fingerprint }),
            })
            const result = await saved.json().catch(() => ({}))
            if (!saved.ok || result.corrected !== true) throw new Error(
              typeof result.detail === 'string' ? result.detail
                : 'De barcodecorrectie is niet bevestigd. Er is niets veilig gewijzigd.')
            // The parent refreshes the list and publishes one standard
            // success Melding; avoid competing/double success overlays.
            onSaved({ status: 'success',
              message: 'Barcodeconflict opgelost voor ' + item.receipt_line_text
                + '. Correcte barcode: ' + result.gtin
                + '. De kassabonnen en voorraad zijn niet gewijzigd.' })
            return false
          },
        })
        return false
      },
    })
  }

  useEffect(() => {
    if (!mayResolveConflict || lastConflictPrompted.current === item.id) return
    lastConflictPrompted.current = item.id
    showBarcodeConflictOptions()
  }, [item.id, mayResolveConflict, showFeedback])

  if (mayResolveConflict) return (
    <section className="rz-external-manual-barcode" data-testid="ed2-barcode-conflict-resolver">
      <h4>Barcodeconflict controleren</h4>
      <p>Catalogusbarcode: <strong>{item.article_code}</strong>.
        Handmatig opgeslagen barcode: <strong>{item.manual_barcode}</strong>.
        Deze codes zijn niet gelijk; bevestig eerst de juiste identiteit.</p>
      <Button type="button" onClick={showBarcodeConflictOptions}
        data-testid="ed2-barcode-conflict-open">Barcode corrigeren</Button>
    </section>
  )

  if (identity.catalogOwnerConflict) return (
    <section className="rz-external-manual-barcode" data-testid="ed2-equivalent-gtin-owner-review">
      <h4>Catalogusidentiteit controleren</h4>
      <p>De Catalogusbarcode <strong>{item.article_code}</strong> en de bewaarde
        barcode <strong>{item.manual_barcode}</strong> vertegenwoordigen dezelfde GTIN.
        Ze verwijzen echter naar verschillende Catalogusproducten; dit is geen
        barcodeconflict dat door het kiezen van een code kan worden opgelost.
        Er is geen wijziging uitgevoerd.</p>
    </section>
  )

  if (identity.equivalent) return (
    <section className="rz-external-manual-barcode" data-testid="ed2-equivalent-gtin-info">
      <h4>Dezelfde barcode in twee notaties</h4>
      <p>De Catalogusbarcode <strong>{item.article_code}</strong> en de handmatig
        opgeslagen barcode <strong>{item.manual_barcode}</strong> hebben
        dezelfde geldige GTIN-identiteit. Een barcodecorrectie is niet nodig.
        De gegevens zijn niet gewijzigd.</p>
    </section>
  )

  if (hasBarcodeConflict) return (
    <section className="rz-external-manual-barcode" data-testid="ed2-barcode-conflict-readonly">
      <h4>Barcodeconflict</h4>
      <p>Catalogusbarcode: <strong>{item.article_code}</strong>.
        Handmatig opgeslagen barcode: <strong>{item.manual_barcode}</strong>.
        Alleen een platform-Superuser mag dit conflict na gevolgencontrole corrigeren.</p>
    </section>
  )

  if (!canConfirm) return null

  if (mayCorrectLidl) return (
    <section className="rz-external-manual-barcode" aria-label="Lidl-barcode corrigeren"
      data-testid="ed2-lidl-barcode-correction">
      <h4>Bewaarde Lidl-barcode corrigeren</h4>
      <p>De huidige barcode <strong>{item.manual_barcode}</strong> is eerder opgeslagen. Controleer per artikel
        de juiste barcode. De oorspronkelijke bon en eventuele oude Catalogusproducten blijven behouden.</p>
      <div className="rz-external-off-manual-form">
        <label className="rz-input-field">
          <span className="rz-label">Nieuwe barcode (EAN/GTIN)</span>
          <input className="rz-input" inputMode="numeric" autoComplete="off"
            value={correctionBarcode} maxLength={14}
            onChange={(event) => setCorrectionBarcode(event.target.value)}
            aria-label="Nieuwe Lidl-barcode" data-testid="ed2-lidl-correction-input" />
        </label>
        <Button type="button" variant="secondary"
          disabled={!correctionValid || correcting}
          onClick={() => void previewCorrection()}
          data-testid="ed2-lidl-correction-preview">
          {correcting ? 'Controleren...' : 'Gevolgen bekijken'}
        </Button>
      </div>
    </section>
  )

  return (
    <section className="rz-external-manual-barcode" aria-label="Barcode koppelen of bewaren" data-testid="ed2-manual-barcode-entry">
      <h4>{canSave ? 'Barcode koppelen of bewaren' : 'Artikelidentiteit bevestigen'}</h4>
      <p>Een opgeslagen barcode is voldoende identificatie. Inhuis koppelt aan een bestaand Catalogusproduct of maakt dit aan. OFF en classificatie zijn niet vereist. Lidl-codes blijven winkelgebonden tot je ze handmatig corrigeert.</p>
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
          {saving ? 'Opslaan...' : 'Barcode opslaan in Catalogus'}
        </Button> : null}
      </div>
      {canSave && confirm ? <div className="rz-modal-backdrop">
        <div className="rz-modal-card" role="alertdialog" aria-modal="true"
          aria-labelledby="ed2-manual-barcode-confirm">
          <p id="ed2-manual-barcode-confirm" className="rz-modal-text">
            Barcode <strong>{barcode.trim()}</strong> voor <strong>{item.receipt_line_text}</strong> opslaan?
            Deze opslag bevestigt de productidentiteit en koppelt deze direct aan de Catalogus. Kassabonnen en voorraad blijven intact.
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
