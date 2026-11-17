import { useCallback, useMemo, useRef, useState } from 'react'
import { useLocation, useNavigate } from 'react-router-dom'
import AppShell from '../../app/AppShell.jsx'
import ScreenCard from '../../ui/ScreenCard.jsx'
import Button from '../../ui/Button.jsx'
import { useAppFeedback } from '../../ui/AppFeedbackProvider.jsx'
import { fetchJsonWithAuth } from '../../lib/authSession.js'
import { useMobileAppViewport } from '../../app/mobileViewport.js'
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
  const isMobile = useMobileAppViewport()
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
  const [purpose, setPurpose] = useState('bonartikel')
  const [targetReceipt, setTargetReceipt] = useState(() => {
    const id = String(source.receiptItemId || '').trim()
    return id ? {
      id,
      receipt_line_text: String(source.articleName || 'Geselecteerd bonartikel'),
      retailer: String(source.retailer || source.retailerCode || ''),
      retailer_code: String(source.retailerCode || ''),
      receipt_article_number: String(source.receiptArticleNumber || ''),
    } : null
  })
  const [showReceiptPicker, setShowReceiptPicker] = useState(false)
  const [receiptQuery, setReceiptQuery] = useState(() => String(source.receiptItemId ? '' : source.articleName || ''))
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
    startScanner, startCompatibleCamera, stopScanner, switchCamera, scanImageFile,
  } = useBarcodeScanner({
    timeoutMs: 0,
    screenContext: 'Scan & Identificeer',
    onDetected: (detected) => { void inspect(detected) },
  })

  const current = lookup && lookup.gtin === safeGtin(barcode) ? lookup : null
  const resultStatus = current?.match_status || ''
  const canRegister = Boolean(purpose === 'catalogus' && current?.valid && resultStatus === 'not_found'
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
    setShowReceiptPicker(true)
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
    const id = String(item.id || '').trim()
    if (!id) return
    // Selecting a destination is not yet barcode registration.
    setTargetReceipt({
      id,
      receipt_line_text: String(item.receipt_line_text || 'Bonartikel'),
      retailer: String(item.retailer || item.retailer_code || ''),
      retailer_code: String(item.retailer_code || ''),
      receipt_article_number: String(item.receipt_article_number || ''),
    })
    setShowReceiptPicker(false)
  }

  function continueToReceiptIdentification() {
    if (purpose !== 'bonartikel' || !current?.valid || !targetReceipt?.id) return
    const selectedTarget = { ...targetReceipt }
    const scannedGtin = current.gtin
    const name = selectedTarget.receipt_line_text
    const retailer = selectedTarget.retailer || selectedTarget.retailer_code || 'winkel onbekend'
    const code = selectedTarget.receipt_article_number || 'artikelnummer onbekend'
    showFeedback({
      variant: 'warning',
      title: 'Identificatie voor dit bonartikel controleren',
      message: `${name} · ${retailer} · ${code}: barcode ${scannedGtin} beoordelen?`,
      detail: 'Er is nog niets gekoppeld. In Artikelbeheer → Identificeren controleer en bevestig je de opslag. Bestaande conflicten blijven beveiligd. Je voorraad en kassabonnen wijzigen niet door deze stap.',
      dismissMode: 'blocked',
      primaryActionLabel: 'Verder naar Identificeren',
      secondaryActionLabel: 'Annuleren',
      testId: 'universal-scan-confirm-target',
      onPrimaryAction: () => {
        navigate('/externe-databases-2', {
          state: {
            selectedItemId: selectedTarget.id,
            scannedBarcode: scannedGtin,
            scanSource: 'universal',
          },
        })
        return true
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
  const sourceType = source.householdArticleId ? 'Voorraadartikel'
    : String(source.from || '').includes('/kassabonnen') ? 'Uitpakken'
    : 'Artikelcontext'

  if (!isMobile) return (
    <AppShell title="Scan & Identificeer" showExit={false}>
      <ScreenCard fullWidth>
        <div data-testid="universal-scan-desktop-disabled" className="rz-universal-scan">
          <h2>Barcode scannen is alleen voor mobiel</h2>
          <p>Open Inhuis op je telefoon om een verpakking te scannen. Op desktop kun je bestaande bonartikelen handmatig identificeren via Artikelbeheer.</p>
          <Button type="button" variant="secondary" onClick={() => navigate('/externe-databases-2')}>Naar Artikelbeheer</Button>
        </div>
      </ScreenCard>
    </AppShell>
  )

  return (
    <AppShell title="Scan & Identificeer" showExit={false}>
      <ScreenCard fullWidth>
        <div className="rz-universal-scan" data-testid="universal-scan-identify">
          <h2>Scan &amp; Identificeer</h2>
          <p>Je kunt eerst een bonartikel kiezen of eerst een barcode scannen. <strong>Scannen koppelt nog niets.</strong></p>

          <fieldset className="rz-universal-scan-purpose" data-testid="universal-scan-purpose">
            <legend><strong>1. Wat wil je doen?</strong></legend>
            <label>
              <input type="radio" name="scan-purpose" value="bonartikel"
                checked={purpose === 'bonartikel'} onChange={() => setPurpose('bonartikel')} />
              Een barcode koppelen aan een bonartikel
            </label>
            <label>
              <input type="radio" name="scan-purpose" value="catalogus"
                checked={purpose === 'catalogus'} onChange={() => setPurpose('catalogus')} />
              Alleen een product in de Catalogus herkennen of toevoegen
            </label>
          </fieldset>

          {purpose === 'bonartikel' ? (
            <section className="rz-universal-scan-destination" data-testid="universal-scan-bonartikel-destination"
              aria-label="Bonartikel dat geïdentificeerd wordt">
              <h3>Aan welk bonartikel wordt de barcode gekoppeld?</h3>
              {targetReceipt ? (
                <>
                  <p><strong>Gekozen bonartikel:</strong> {targetReceipt.receipt_line_text}</p>
                  <p>Winkel: {targetReceipt.retailer || targetReceipt.retailer_code || 'onbekend'} ·
                    Artikelnummer: {targetReceipt.receipt_article_number || 'niet bekend'}</p>
                  <p className="rz-universal-scan-status">Nog niet gekoppeld — pas na bevestiging in Identificeren.</p>
                </>
              ) : (
                <p className="rz-universal-scan-status"><strong>Er is nog geen bonartikel gekozen.</strong> Je kunt nu een bonartikel kiezen of eerst de barcode scannen en daarna kiezen. Inhuis koppelt nooit op basis van alleen een overeenkomende naam.</p>
              )}
              {hasSource && !source.receiptItemId ? (
                <p className="rz-universal-scan-context">
                  Je kwam vanuit {sourceType}: <strong>{source.articleName || 'artikel'}</strong>.
                  Dit is alleen context, <strong>geen gekozen bonartikel</strong> en wordt niet automatisch gekoppeld.
                </p>
              ) : null}
              <div className="rz-universal-scan-actions">
                <Button type="button" variant="secondary" disabled={receiptsBusy}
                  data-testid="universal-scan-select-target"
                  onClick={() => { if (receiptItems) setShowReceiptPicker((value) => !value)
                    else void loadReceiptCandidates() }}>
                  {receiptsBusy ? 'Bonartikelen ophalen…' : targetReceipt ? 'Ander bonartikel kiezen' : 'Bonartikel kiezen'}
                </Button>
                {targetReceipt ? <Button type="button" variant="secondary" onClick={() => {
                  setTargetReceipt(null)
                  setShowReceiptPicker(false)
                }}>Keuze wissen</Button> : null}
              </div>
              {showReceiptPicker && receiptItems ? (
                <div className="rz-universal-scan-pick" data-testid="universal-scan-target-picker">
                  <label htmlFor="universal-scan-receipt-search">Zoek op artikelnaam, winkel of bonartikelnummer</label>
                  <input id="universal-scan-receipt-search" className="rz-input"
                    value={receiptQuery} onChange={(event) => setReceiptQuery(event.target.value)} />
                  {matchingReceipts.length ? (
                    <div className="rz-universal-scan-candidates" role="list" aria-label="Bonartikelen">
                      {matchingReceipts.map((item) => <div role="listitem" key={item.id} className="rz-universal-scan-candidate">
                        <span><strong>{item.receipt_line_text}</strong> · {item.retailer || item.retailer_code || 'Winkel onbekend'}
                          {' · '}{item.receipt_article_number || 'Artikelnummer ontbreekt'}</span>
                        <Button type="button" variant="secondary" onClick={() => selectReceipt(item)}>Dit artikel kiezen</Button>
                      </div>)}
                    </div>
                  ) : <p>Geen passend bonartikel. Pas de zoektekst aan; er wordt niets gekoppeld.</p>}
                </div>
              ) : null}
            </section>
          ) : (
            <section className="rz-universal-scan-destination" data-testid="universal-scan-catalog-only">
              <h3>Alleen Catalogus</h3>
              <p>Je controleert een barcode in de centrale Catalogus. Als het product nog onbekend is, kun je het afzonderlijk opslaan. <strong>Er wordt geen bonartikel of voorraadartikel gekoppeld.</strong></p>
              {targetReceipt ? <p className="rz-universal-scan-context">Eerder gekozen bonartikel: {targetReceipt.receipt_line_text}. Deze keuze wordt in deze stand niet gebruikt.</p> : null}
            </section>
          )}

          <section className="rz-universal-scan-read" aria-label="Barcode lezen">
            <h3>2. Scan de barcode op de verpakking</h3>
            <p>Een scan leest alleen de code; er verandert nog niets in Inhuis.</p>
            <div className="rz-universal-scan-actions">
              <Button type="button" onClick={() => void startScanner()} data-testid="universal-scan-camera">Barcode scannen</Button>
              <Button type="button" variant="secondary" onClick={() => photoRef.current?.click()}>Barcode uit foto</Button>
            </div>
            <input ref={photoRef} type="file" accept="image/*" capture="environment"
              aria-label="Foto van barcode kiezen" style={{ display: 'none' }} onChange={choosePhoto} />
            <label htmlFor="universal-scan-code">Of vul de barcode handmatig in</label>
            <div className="rz-universal-scan-actions">
              <input id="universal-scan-code" className="rz-input" inputMode="numeric"
                autoComplete="off" maxLength={18} value={barcode}
                onChange={(event) => editBarcode(event.target.value)}
                placeholder="EAN/GTIN van de verpakking" />
              <Button type="button" variant="secondary" disabled={checking || !barcode.trim()}
                onClick={() => void inspect(barcode)}>
                {checking ? 'Controleren…' : 'Barcode controleren'}
              </Button>
            </div>
          </section>

          {current ? (
            <section className="rz-universal-scan-result" aria-label="Barcode en bestemmingscontrole"
              data-testid="universal-scan-result">
              <h3>3. Wat gebeurt er met deze barcode?</h3>
              <p><strong>Gescande barcode:</strong> {current.gtin}</p>
              {['matched', 'incomplete'].includes(resultStatus) && current.product ? (
                <div className="rz-universal-scan-product">
                  {current.product.image_url ? <img src={current.product.image_url} alt={current.product.name || 'Productfoto'} /> : null}
                  <div>
                    <strong>Gevonden in Catalogus: {current.product.name || 'Catalogusproduct'}</strong>
                    {current.product.brand ? <p>Merk: {current.product.brand}</p> : null}
                    <p>{resultStatus === 'matched' ? 'Bekende productidentiteit' : 'Bestaande productidentiteit vraagt controle'}</p>
                  </div>
                </div>
              ) : resultStatus === 'not_found' ? (
                <p>Deze barcode is nog niet bekend in de Catalogus.</p>
              ) : (
                <p>{resultStatus === 'scope_required'
                  ? 'Dit is een winkelinterne barcode. Deze mag niet als algemene GTIN worden geregistreerd; controle per winkelartikel is vereist.'
                  : 'De barcode kan niet veilig worden herkend of gebruikt. Er is nog niets gewijzigd.'}</p>
              )}

              {purpose === 'bonartikel' ? (
                <div className="rz-universal-scan-next" data-testid="universal-scan-target-confirmation">
                  <h3>Bestemming: bonartikel</h3>
                  {targetReceipt ? (
                    <>
                      <p><strong>{targetReceipt.receipt_line_text}</strong> ·
                        {' '}{targetReceipt.retailer || targetReceipt.retailer_code || 'winkel onbekend'} ·
                        {' '}{targetReceipt.receipt_article_number || 'zonder bonartikelnummer'}</p>
                      <p><strong>Status: nog niet gekoppeld.</strong> Met de knop hieronder open je Identificeren. Pas daar controleer en bevestig je de opslag van barcode {current.gtin} bij dit bonartikel.</p>
                      <Button type="button" data-testid="universal-scan-continue-to-identification"
                        disabled={!current.valid || checking}
                        onClick={continueToReceiptIdentification}>
                        Barcode voor dit bonartikel beoordelen
                      </Button>
                    </>
                  ) : (
                    <p><strong>Er is nog geen bonartikel gekozen.</strong> Kies bij stap 1 het bonartikel waaraan je deze barcode wilt koppelen. Tot die tijd wordt er niets opgeslagen.</p>
                  )}
                </div>
              ) : (
                <div className="rz-universal-scan-next" data-testid="universal-scan-catalog-confirmation">
                  <h3>Bestemming: Catalogus, zonder bonartikelkoppeling</h3>
                  {resultStatus === 'not_found' ? (
                    <>
                      <p>Je kunt dit onbekende product in de Catalogus toevoegen. Dit legt de barcode niet vast bij een bonartikel of huishouden.</p>
                      <Button type="button" variant="secondary" disabled={offBusy}
                        data-testid="universal-scan-off-suggestion" onClick={() => void checkOpenFoodFacts()}>
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
                              onClick={() => setProductName(String(offSuggestion.product_name || ''))}>Productnaam overnemen</Button>
                          </div>
                        </div>
                      ) : null}
                      <label htmlFor="universal-scan-product-name">Controleer de productnaam op de verpakking</label>
                      <input id="universal-scan-product-name" className="rz-input"
                        value={productName} maxLength={200}
                        onChange={(event) => setProductName(event.target.value)}
                        placeholder="Bijvoorbeeld: Halfvolle melk 1 liter" />
                      <Button type="button" disabled={!canRegister || saving}
                        onClick={confirmCatalogCreate} data-testid="universal-scan-save-catalog">
                        {saving ? 'Opslaan…' : 'Alleen product in Catalogus opslaan'}
                      </Button>
                    </>
                  ) : (
                    <p>Er is geen nieuwe Catalogusregistratie uitgevoerd. Een bestaande identiteit wordt niet automatisch overschreven of aan een bonartikel gekoppeld.</p>
                  )}
                </div>
              )}
            </section>
          ) : null}

          <Button type="button" variant="secondary" onClick={() => navigate(-1)}>Terug</Button>
          <BarcodeScannerModal open={isOpen || cameraState.status === 'error'}
            title="Barcode scannen (nog niet koppelen)"
            videoRef={videoRef} cameraState={cameraState} cameraMeta={cameraMeta}
            availableCameras={availableCameras} onSwitchCamera={switchCamera}
            onRetry={() => void startScanner()}
            onTryCompatibility={() => void startCompatibleCamera()}
            onChoosePhoto={() => { stopScanner(); photoRef.current?.click() }}
            onClose={() => stopScanner()} />
        </div>
      </ScreenCard>
    </AppShell>
  )
}
