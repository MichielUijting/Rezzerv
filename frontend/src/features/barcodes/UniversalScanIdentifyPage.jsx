import { useCallback, useMemo, useRef, useState } from 'react'
import { useLocation, useNavigate } from 'react-router-dom'
import AppShell from '../../app/AppShell.jsx'
import ScreenCard from '../../ui/ScreenCard.jsx'
import Button from '../../ui/Button.jsx'
import { useAppFeedback } from '../../ui/AppFeedbackProvider.jsx'
import { fetchJsonWithAuth } from '../../lib/authSession.js'
import useBarcodeScanner from '../../lib/useBarcodeScanner.js'
import BarcodeScannerModal from './BarcodeScannerModal.jsx'
import './universalScanIdentify.css'

function safeGtin(value) {
  return String(value || '').replace(/[\s-]+/g, '').trim()
}

function readableDetail(payload, fallback) {
  return typeof payload?.detail === 'string' ? payload.detail : fallback
}

function matchesReceipt(item, needle) {
  const text = [item.receipt_line_text, item.retailer, item.retailer_code, item.receipt_article_number]
    .filter(Boolean).join(' ').toLocaleLowerCase('nl-NL')
  return text.includes(needle.toLocaleLowerCase('nl-NL'))
}

export default function UniversalScanIdentifyPage() {
  const navigate = useNavigate()
  const location = useLocation()
  const { showFeedback } = useAppFeedback()
  const photoRef = useRef(null)
  const requestRef = useRef(0)
  const source = location.state || {}
  const [barcode, setBarcode] = useState(() => safeGtin(source.scannedBarcode || ''))
  const [lookup, setLookup] = useState(null)
  const [checking, setChecking] = useState(false)
  const [saving, setSaving] = useState(false)
  const [productName, setProductName] = useState(() => String(source.articleName || ''))
  const [offSuggestion, setOffSuggestion] = useState(null)
  const [offBusy, setOffBusy] = useState(false)
  const [offChecked, setOffChecked] = useState(false)
  const [receiptQuery, setReceiptQuery] = useState('')
  const [receiptItems, setReceiptItems] = useState(null)
  const [receiptsBusy, setReceiptsBusy] = useState(false)

  const inspect = useCallback(async (raw) => {
    const gtin = safeGtin(raw)
    const serial = ++requestRef.current
    setBarcode(gtin)
    setLookup(null)
    setReceiptItems(null)
    setOffSuggestion(null)
    setOffChecked(false)
    setOffBusy(false)
    if (!/^(?:\d{8}|\d{12,14})$/.test(gtin)) {
      showFeedback({ variant: 'warning', message: 'Scan of vul een barcode van 8, 12, 13 of 14 cijfers in.' })
      return
    }
    setChecking(true)
    try {
      const response = await fetchJsonWithAuth('/api/barcodes/' + encodeURIComponent(gtin))
      const result = await response.json().catch(() => ({}))
      if (!response.ok) throw new Error(readableDetail(result, 'Barcodecontrole mislukt.'))
      if (serial !== requestRef.current) return
      setLookup(result)
      if (result.product?.name) {
        setProductName(result.product.name)
        setReceiptQuery(result.product.name)
      }
      if (!result.valid) {
        showFeedback({ variant: 'warning', message: 'De barcode heeft geen geldig controlecijfer. Er is niets opgeslagen.' })
      } else if (result.match_status === 'scope_required') {
        showFeedback({ variant: 'warning', message: 'Winkelinterne barcode: kies een bestaand bonartikel om de juiste winkelidentiteit te bevestigen.' })
      } else if (result.match_status === 'conflict' || result.match_status === 'incomplete') {
        showFeedback({ variant: 'warning', message: 'Deze barcode heeft een onduidelijke Catalogusidentiteit. Er is niets gewijzigd.' })
      }
    } catch (error) {
      if (serial === requestRef.current) {
        showFeedback({ variant: 'error', message: error.message || 'Barcodecontrole mislukt.' })
      }
    } finally {
      if (serial === requestRef.current) setChecking(false)
    }
  }, [showFeedback])

  const {
    videoRef, isOpen, cameraState, cameraMeta, availableCameras,
    startScanner, stopScanner, switchCamera, scanImageFile,
  } = useBarcodeScanner({
    timeoutMs: 0,
    screenContext: 'Scan & Identificeer',
    onDetected: (detected) => { void inspect(detected) },
  })

  const current = lookup && lookup.gtin === safeGtin(barcode) ? lookup : null
  const resultStatus = current?.match_status || ''
  const canRegister = Boolean(current?.valid && resultStatus === 'not_found'
    && String(productName).trim() && String(productName).trim().length <= 200)
  const matchingReceipts = useMemo(() => {
    if (!receiptItems) return []
    const needle = receiptQuery.trim()
    return (needle ? receiptItems.filter((item) => matchesReceipt(item, needle)) : receiptItems)
      .slice(0, 15)
  }, [receiptItems, receiptQuery])

  function editBarcode(value) {
    ++requestRef.current
    setBarcode(value)
    setLookup(null)
    setChecking(false)
    setReceiptItems(null)
    setOffSuggestion(null)
    setOffChecked(false)
    setOffBusy(false)
  }

  async function checkOpenFoodFacts() {
    if (!current?.valid || resultStatus !== 'not_found' || offBusy) return
    const serial = requestRef.current
    setOffBusy(true)
    setOffChecked(false)
    setOffSuggestion(null)
    try {
      const response = await fetchJsonWithAuth('/api/barcodes/identify-suggestion/' + encodeURIComponent(current.gtin))
      const result = await response.json().catch(() => ({}))
      if (!response.ok) throw new Error(readableDetail(result, 'Open Food Facts kon niet worden gecontroleerd.'))
      if (serial !== requestRef.current) return
      setOffChecked(true)
      setOffSuggestion(result.status === 'found' ? result.product : null)
      if (result.status === 'external_source_unavailable') {
        showFeedback({ variant: 'warning', message: 'Open Food Facts is tijdelijk niet bereikbaar. Je kunt de productnaam zelf invullen.' })
      } else if (result.status !== 'found') {
        showFeedback({ variant: 'info', message: 'Geen product gevonden met precies deze barcode. Je kunt de productnaam zelf invullen.' })
      }
    } catch (error) {
      if (serial === requestRef.current) {
        showFeedback({ variant: 'warning', message: error.message || 'Productinformatie kon niet worden opgehaald.' })
      }
    } finally {
      if (serial === requestRef.current) setOffBusy(false)
    }
  }

  async function loadReceiptCandidates() {
    setReceiptsBusy(true)
    try {
      const response = await fetchJsonWithAuth('/api/external-databases/articles-overview')
      const data = await response.json().catch(() => ({}))
      if (!response.ok || !Array.isArray(data.items)) {
        throw new Error(readableDetail(data, 'Bonartikelen konden niet worden opgehaald.'))
      }
      setReceiptItems(data.items)
    } catch (error) {
      showFeedback({ variant: 'error', message: error.message || 'Bonartikelen konden niet worden opgehaald.' })
    } finally {
      setReceiptsBusy(false)
    }
  }

  function selectReceipt(item) {
    const id = String(item.id || '')
    if (!id || !current?.valid) return
    navigate('/externe-databases-2', {
      state: {
        selectedItemId: id,
        scannedBarcode: current.gtin,
        scanSource: 'universal',
      },
    })
  }

  function confirmCatalogCreate() {
    if (!canRegister || saving) return
    const gtin = current.gtin
    const name = productName.trim().replace(/\s+/g, ' ')
    showFeedback({
      variant: 'warning', title: 'Nieuw Catalogusartikel bevestigen',
      message: 'Product ' + name + ' met barcode ' + gtin + ' opslaan?',
      detail: 'Dit wijzigt uitsluitend de centrale Catalogus. Er ontstaat geen kassabon, aankoop, huishoudartikel of voorraadmutatie. GS1/CBS is niet verplicht.',
      dismissMode: 'blocked',
      primaryActionLabel: 'Opslaan in Catalogus',
      secondaryActionLabel: 'Annuleren',
      testId: 'universal-scan-confirm-catalog',
      onPrimaryAction: async () => {
        setSaving(true)
        try {
          const response = await fetchJsonWithAuth('/api/barcodes/identify-catalog', {
            method: 'POST', body: JSON.stringify({ gtin, product_name: name }),
          })
          const data = await response.json().catch(() => ({}))
          if (!response.ok || !['created', 'already_known'].includes(data.status)) {
            throw new Error(readableDetail(data, 'Catalogusidentiteit kon niet worden opgeslagen.'))
          }
          await inspect(gtin)
          showFeedback({ variant: 'success', message: data.saved
            ? 'Barcode is bevestigd en als nieuw Catalogusartikel opgeslagen.'
            : 'Barcode was inmiddels al bekend in de Catalogus.' })
          return false
        } catch (error) {
          showFeedback({ variant: 'error', message: error.message || 'Barcode is niet opgeslagen.' })
          return false
        } finally {
          setSaving(false)
        }
      },
    })
  }

  async function choosePhoto(event) {
    const file = event.target.files?.[0]
    event.target.value = ''
    if (!file) return
    stopScanner()
    const decoded = await scanImageFile(file)
    if (!decoded) showFeedback({ variant: 'warning', message: 'Geen leesbare barcode gevonden. Probeer een scherpere foto.' })
  }

  const hasSource = Boolean(source.articleName || source.receiptItemId || source.householdArticleId)
  return (
    <AppShell title="Scan & Identificeer" showExit={false}>
      <ScreenCard fullWidth>
        <div className="rz-universal-scan" data-testid="universal-scan-identify">
          <h2>Scan & Identificeer</h2>
          <p>Scan een artikel in de winkel, thuis, tijdens Uitpakken of vanuit Identificeren. Een scan leest alleen de barcode en verandert nooit je voorraad.</p>
          {hasSource ? <p className="rz-universal-scan-context">Geselecteerd: <strong>{source.articleName || 'Artikel'}</strong>. Alleen bevestigde koppelingen worden opgeslagen.</p> : null}
          <div className="rz-universal-scan-actions">
            <Button type="button" onClick={() => void startScanner()} data-testid="universal-scan-camera">Barcode scannen</Button>
            <Button type="button" variant="secondary" onClick={() => photoRef.current?.click()}>Barcode uit foto</Button>
          </div>
          <input ref={photoRef} type="file" accept="image/*" capture="environment"
            aria-label="Foto van barcode kiezen" style={{ display: 'none' }} onChange={choosePhoto} />
          <label htmlFor="universal-scan-code">Barcode (EAN/GTIN)</label>
          <div className="rz-universal-scan-actions">
            <input id="universal-scan-code" className="rz-input" inputMode="numeric" autoComplete="off" maxLength={18}
              value={barcode} onChange={(event) => editBarcode(event.target.value)}
              placeholder="Scan of vul een barcode in" />
            <Button type="button" variant="secondary" disabled={checking || !barcode.trim()}
              onClick={() => void inspect(barcode)}>
              {checking ? 'Controleren…' : 'Controleren'}
            </Button>
          </div>
          {current ? (
            <section className="rz-universal-scan-result" aria-label="Barcodecontrole" data-testid="universal-scan-result">
              <h3>Resultaat</h3>
              <p>Barcode: <strong>{current.gtin}</strong></p>
              {['matched', 'incomplete'].includes(resultStatus) && current.product ? (
                <>
                  <div className="rz-universal-scan-product">
                    {current.product.image_url ? <img src={current.product.image_url} alt={current.product.name || 'Productfoto'} /> : null}
                    <div>
                      <strong>{current.product.name || 'Catalogusproduct'}</strong>
                      {current.product.brand ? <p>Merk: {current.product.brand}</p> : null}
                      <p>{resultStatus === 'matched' ? 'Bekende Catalogusidentiteit' : 'Bestaande Catalogusidentiteit vraagt controle'}</p>
                    </div>
                  </div>
                  <Button type="button" variant="secondary" onClick={() => navigate('/catalogus/' + encodeURIComponent(current.product.global_product_id))}>
                    Open Catalogusartikel
                  </Button>
                </>
              ) : resultStatus === 'not_found' ? (
                <>
                  <p>Deze barcode is nog niet bekend in de Catalogus. Vul de productnaam in en bevestig het opslaan.</p>
                  <Button type="button" variant="secondary" disabled={offBusy}
                    data-testid="universal-scan-off-suggestion"
                    onClick={() => void checkOpenFoodFacts()}>
                    {offBusy ? 'OFF controleren…' : 'Productgegevens zoeken in Open Food Facts'}
                  </Button>
                  {offChecked && offSuggestion ? (
                    <div className="rz-universal-scan-product" data-testid="universal-scan-off-result">
                      {offSuggestion.image_url ? <img src={offSuggestion.image_url} alt="Voorgestelde productfoto van Open Food Facts" /> : null}
                      <div>
                        <strong>{offSuggestion.product_name || 'Productvoorstel'}</strong>
                        {offSuggestion.brand ? <p>{offSuggestion.brand}</p> : null}
                        <p>Voorstel van Open Food Facts — nog niet opgeslagen</p>
                        <Button type="button" variant="secondary"
                          onClick={() => setProductName(String(offSuggestion.product_name || ''))}>
                          Productnaam overnemen
                        </Button>
                      </div>
                    </div>
                  ) : null}
                  <label htmlFor="universal-scan-product-name">Productnaam op de verpakking</label>
                  <input id="universal-scan-product-name" className="rz-input" value={productName} maxLength={200}
                    onChange={(event) => setProductName(event.target.value)} placeholder="Bijvoorbeeld: Halfvolle melk 1 liter" />
                  <Button type="button" disabled={!canRegister || saving} onClick={confirmCatalogCreate} data-testid="universal-scan-save-catalog">
                    {saving ? 'Opslaan…' : 'Opslaan in Catalogus'}
                  </Button>
                </>
              ) : (
                <p>{resultStatus === 'scope_required'
                  ? 'Winkelinterne barcode. Deze mag niet als algemene GTIN worden geregistreerd; kies het exacte winkelartikel in Identificeren.'
                  : 'De barcode kan niet veilig worden gekoppeld. Bestaande identiteiten blijven ongewijzigd.'}</p>
              )}
              {current.valid ? (
                <div className="rz-universal-scan-receipts">
                  <h3>Koppelen aan een bonartikel</h3>
                  <p>Kies bewust het juiste artikel. Inhuis koppelt niet op basis van alleen een overeenkomende naam.</p>
                  {source.receiptItemId ? <Button type="button" variant="secondary"
                    onClick={() => selectReceipt({ id: source.receiptItemId })}>
                    Naar eerder geselecteerd bonartikel
                  </Button> : null}
                  <Button type="button" variant="secondary" disabled={receiptsBusy}
                    onClick={() => void loadReceiptCandidates()}>
                    {receiptsBusy ? 'Ophalen…' : 'Bonartikel zoeken'}
                  </Button>
                  {receiptItems ? <>
                    <label htmlFor="universal-scan-receipt-search">Zoek naam, winkel of artikelcode</label>
                    <input id="universal-scan-receipt-search" className="rz-input" value={receiptQuery}
                      onChange={(event) => setReceiptQuery(event.target.value)} />
                    {matchingReceipts.length ? (
                      <div className="rz-universal-scan-candidates" role="list" aria-label="Bonartikelen">
                        {matchingReceipts.map((item) => <div role="listitem" key={item.id} className="rz-universal-scan-candidate">
                          <span><strong>{item.receipt_line_text}</strong> · {item.retailer_code || 'Winkel onbekend'}
                            {item.receipt_article_number ? ' · ' + item.receipt_article_number : ''}</span>
                          <Button type="button" variant="secondary" onClick={() => selectReceipt(item)}>Selecteren</Button>
                        </div>)}
                      </div>
                    ) : <p>Geen passend bonartikel gevonden. Pas de zoektekst aan.</p>}
                  </> : null}
                </div>
              ) : null}
            </section>
          ) : null}
          <div className="rz-universal-scan-actions">
            <Button type="button" variant="secondary" onClick={() => navigate(-1)}>Terug</Button>
          </div>
          <BarcodeScannerModal open={isOpen || cameraState.status === 'error'}
            title="Scan & Identificeer" videoRef={videoRef} cameraState={cameraState}
            cameraMeta={cameraMeta} availableCameras={availableCameras}
            onSwitchCamera={switchCamera} onRetry={() => void startScanner()}
            onChoosePhoto={() => { stopScanner(); photoRef.current?.click() }}
            onClose={() => stopScanner()} />
        </div>
      </ScreenCard>
    </AppShell>
  )
}
