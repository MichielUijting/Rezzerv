import { useEffect, useMemo, useRef, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import AppShell from '../app/AppShell.jsx'
import Card from '../ui/Card.jsx'
import Button from '../ui/Button.jsx'
import useBarcodeScanner from '../lib/useBarcodeScanner.js'
import { getAuthHeaders } from '../lib/authSession.js'

function buildLocationOptionState(options = []) {
  const locations = []
  const seenLocations = new Set()
  const sublocationsByLocation = new Map()

  options.forEach((option) => {
    const label = String(option?.label || '').trim()
    if (!label) return
    const parts = label.split(' / ')
    const locationName = String(parts[0] || '').trim()
    const sublocationName = String(parts.slice(1).join(' / ') || '').trim()
    if (!locationName) return

    if (!seenLocations.has(locationName)) {
      seenLocations.add(locationName)
      locations.push(locationName)
    }

    if (!sublocationsByLocation.has(locationName)) {
      sublocationsByLocation.set(locationName, [])
    }

    if (sublocationName) {
      const current = sublocationsByLocation.get(locationName)
      if (!current.includes(sublocationName)) current.push(sublocationName)
    }
  })

  locations.sort((a, b) => a.localeCompare(b, 'nl'))
  sublocationsByLocation.forEach((items, key) => {
    items.sort((a, b) => a.localeCompare(b, 'nl'))
    sublocationsByLocation.set(key, items)
  })

  return { locations, sublocationsByLocation }
}

async function fetchLocationOptions() {
  const [spacesResponse, sublocationsResponse] = await Promise.all([
    fetch('/api/spaces?_ts=' + Date.now(), { cache: 'no-store', headers: getAuthHeaders() }),
    fetch('/api/sublocations?_ts=' + Date.now(), { cache: 'no-store', headers: getAuthHeaders() }),
  ])
  if (!spacesResponse.ok || !sublocationsResponse.ok) {
    throw new Error('Locatie-opties konden niet worden geladen')
  }
  const spacesData = await spacesResponse.json().catch(() => ({}))
  const sublocationsData = await sublocationsResponse.json().catch(() => ({}))
  const activeSpaces = Array.isArray(spacesData?.items) ? spacesData.items.filter((item) => Boolean(item?.active)) : []
  const activeSublocations = Array.isArray(sublocationsData?.items) ? sublocationsData.items.filter((item) => Boolean(item?.active)) : []
  const sublocationsBySpaceId = new Map()
  activeSublocations.forEach((item) => {
    const key = String(item?.space_id || '')
    if (!key) return
    const current = sublocationsBySpaceId.get(key) || []
    current.push(item)
    sublocationsBySpaceId.set(key, current)
  })
  const rows = []
  activeSpaces.forEach((space) => {
    const spaceName = String(space?.naam || '').trim()
    if (!spaceName) return
    const linked = sublocationsBySpaceId.get(String(space.id)) || []
    if (!linked.length) {
      rows.push({ label: spaceName })
      return
    }
    linked.forEach((sublocation) => {
      const sublocationName = String(sublocation?.naam || '').trim()
      rows.push({ label: sublocationName ? `${spaceName} / ${sublocationName}` : spaceName })
    })
  })
  return buildLocationOptionState(rows)
}

function buildTodayInputValue() {
  const now = new Date()
  const pad = (value) => String(value).padStart(2, '0')
  return `${now.getFullYear()}-${pad(now.getMonth() + 1)}-${pad(now.getDate())}`
}

function toBackendPurchaseDate(inputValue) {
  const normalized = String(inputValue || '').trim()
  if (!normalized) return null
  const match = normalized.match(/^(\d{4})-(\d{2})-(\d{2})$/)
  if (!match) return normalized
  return `${match[3]}-${match[2]}-${match[1]}`
}

function extractApiMessage(payload, fallbackMessage) {
  if (typeof payload === "string") {
    const normalized = payload.trim()
    return normalized || fallbackMessage
  }
  if (!payload || typeof payload !== "object") return fallbackMessage

  const directCandidates = [
    payload.message,
    payload.detail,
    payload.error,
    payload.reason,
    payload.lookup_message,
  ]
  for (const candidate of directCandidates) {
    if (typeof candidate === "string" && candidate.trim()) return candidate.trim()
    if (candidate && typeof candidate === "object") {
      const nested = extractApiMessage(candidate, '')
      if (nested) return nested
    }
  }

  if (Array.isArray(payload.errors)) {
    for (const item of payload.errors) {
      const nested = extractApiMessage(item, '')
      if (nested) return nested
    }
  }

  if (Array.isArray(payload.detail)) {
    for (const item of payload.detail) {
      const nested = extractApiMessage(item, '')
      if (nested) return nested
    }
  }

  if (typeof payload.code === "string" && payload.code.trim()) {
    const code = payload.code.trim().toLowerCase()
    if (code === 'not_found') return 'Geen product gevonden in externe databases. Barcode is bewaard; vul de ontbrekende velden handmatig aan.'
    if (code === 'failed' || code === 'error') return 'Barcode controleren mislukt. Probeer het opnieuw of vul de gegevens handmatig aan.'
  }

  if (typeof payload.lookup_status === "string" && payload.lookup_status.trim()) {
    const status = payload.lookup_status.trim().toLowerCase()
    if (status === 'not_found') return 'Geen product gevonden in externe databases. Barcode is bewaard; vul de ontbrekende velden handmatig aan.'
    if (status === 'failed' || status === 'error') return 'Barcode controleren mislukt. Probeer het opnieuw of vul de gegevens handmatig aan.'
  }

  return fallbackMessage
}

function createInitialPurchaseForm() {
  return {
    route: 'manual',
    barcode: '',
    articleName: '',
    articleNumber: '',
    quantity: '1',
    location: '',
    sublocation: '',
    purchaseDate: buildTodayInputValue(),
    supplier: '',
    price: '',
    note: '',
  }
}

function normalizePriceValue(value) {
  const normalized = String(value || '').trim().replace(',', '.')
  if (!normalized) return null
  const parsed = Number(normalized)
  return Number.isFinite(parsed) ? parsed : Number.NaN
}

function buildPurchaseFormFromBarcodeLookup(previousForm, barcode, lookupResult, locationState) {
  const nextLocation = previousForm.location || (locationState.locations.length === 1 ? locationState.locations[0] : '')
  const availableSublocations = nextLocation ? (locationState.sublocationsByLocation.get(nextLocation) || []) : []
  const nextSublocation = previousForm.sublocation || (availableSublocations.length === 1 ? availableSublocations[0] : '')
  const matchedArticleName = String(lookupResult?.article?.name || '').trim()
  const matchedArticleNumber = String(lookupResult?.article?.article_number || '').trim()
  const hasKnownArticle = Boolean(lookupResult?.found && matchedArticleName)
  const hasExternalArticle = Boolean(lookupResult?.external_match && matchedArticleName)

  return {
    ...previousForm,
    route: 'barcode',
    barcode,
    articleName: hasKnownArticle || hasExternalArticle ? matchedArticleName : '',
    articleNumber: hasKnownArticle || hasExternalArticle ? matchedArticleNumber : '',
    quantity: previousForm.quantity || '1',
    purchaseDate: previousForm.purchaseDate || buildTodayInputValue(),
    location: nextLocation,
    sublocation: nextSublocation,
  }
}

function clearBarcodeLinkedFields(previousForm, nextBarcode) {
  const normalizedCurrentBarcode = String(previousForm?.barcode || '').trim()
  const normalizedNextBarcode = String(nextBarcode || '').trim()
  if (normalizedCurrentBarcode === normalizedNextBarcode) return previousForm
  return {
    ...previousForm,
    barcode: normalizedNextBarcode,
    route: normalizedNextBarcode ? 'barcode' : 'manual',
    articleName: '',
    articleNumber: '',
  }
}

async function scanBarcodeArticle(barcode) {
  const response = await fetch('/api/articles/barcode-scan', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', ...getAuthHeaders() },
    body: JSON.stringify({ barcode }),
  })
  const data = await response.json().catch(() => ({}))
  if (!response.ok) {
    throw new Error(extractApiMessage(data, 'Barcode kon niet worden gecontroleerd'))
  }
  return data
}

function validateIncidentalPurchaseForm(form, availableSublocations = []) {
  if (!String(form.location || '').trim()) {
    throw new Error('Locatie is verplicht')
  }
  if (availableSublocations.length > 0 && !String(form.sublocation || '').trim()) {
    throw new Error('Sublocatie is verplicht')
  }
}

async function createIncidentalPurchase(form, options = {}) {
  const { availableSublocations = [] } = options
  validateIncidentalPurchaseForm(form, availableSublocations)

  const quantity = Number(form.quantity || 0)
  if (!Number.isFinite(quantity) || quantity <= 0) {
    throw new Error('Aantal moet groter zijn dan 0 zijn')
  }
  const normalizedPrice = normalizePriceValue(form.price)
  if (Number.isNaN(normalizedPrice)) {
    throw new Error('Prijs moet een geldig bedrag zijn')
  }

  const payload = {
    quantity,
    space_name: form.location || null,
    sublocation_name: form.sublocation || null,
    purchase_date: toBackendPurchaseDate(form.purchaseDate),
    supplier: form.supplier || null,
    article_number: String(form.articleNumber || '').trim() || null,
    price: normalizedPrice,
    currency: normalizedPrice == null ? null : 'EUR',
    note: form.note || null,
  }

  if (String(form.barcode || '').trim()) {
    payload.barcode = String(form.barcode || '').trim()
    payload.article_name = String(form.articleName || '').trim() || null
    if (!payload.barcode) throw new Error('Barcode is verplicht')
    const response = await fetch('/api/purchases/barcode', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', ...getAuthHeaders() },
      body: JSON.stringify(payload),
    })
    const data = await response.json().catch(() => ({}))
    if (!response.ok) throw new Error(extractApiMessage(data, 'Incidentele aankoop via barcode mislukt'))
    return data
  }

  payload.article_name = String(form.articleName || '').trim()
  if (!payload.article_name) throw new Error('Artikelnaam ontbreekt om op te slaan.')
  const response = await fetch('/api/purchases/manual', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', ...getAuthHeaders() },
    body: JSON.stringify(payload),
  })
  const data = await response.json().catch(() => ({}))
  if (!response.ok) throw new Error(extractApiMessage(data, 'Incidentele aankoop opslaan mislukt'))
  return data
}

function detectMobileScannerSupport() {
  if (typeof window === 'undefined') return false
  const coarse = window.matchMedia?.('(pointer: coarse)').matches
  const narrow = window.matchMedia?.('(max-width: 900px)').matches
  const mobileUA = /Android|iPhone|iPad|iPod/i.test(window.navigator.userAgent || '')
  return Boolean(coarse || narrow || mobileUA)
}

export default function IncidentalPurchasePage() {
  const navigate = useNavigate()
  const [purchaseForm, setPurchaseForm] = useState(createInitialPurchaseForm)
  const [purchaseLookupState, setPurchaseLookupState] = useState({ status: 'idle', message: '' })
  const [purchaseSaveState, setPurchaseSaveState] = useState({ status: 'idle', message: '' })
  const purchaseFormRef = useRef(createInitialPurchaseForm())
  const purchaseLookupRequestRef = useRef('')
  const [locationOptions, setLocationOptions] = useState({ locations: [], sublocationsByLocation: new Map() })
  const isMobileScanner = useMemo(() => detectMobileScannerSupport(), [])

  useEffect(() => {
    purchaseFormRef.current = purchaseForm
  }, [purchaseForm])

  useEffect(() => {
    let cancelled = false
    fetchLocationOptions()
      .then((data) => { if (!cancelled) setLocationOptions(data) })
      .catch(() => { if (!cancelled) setLocationOptions(buildLocationOptionState([])) })
    return () => { cancelled = true }
  }, [])

  const {
    videoRef: purchaseBarcodeVideoRef,
    isOpen: purchaseCameraOpen,
    cameraState: purchaseCameraState,
    cameraMeta: purchaseCameraMeta,
    availableCameras: purchaseAvailableCameras,
    startScanner: startPurchaseBarcodeScanner,
    stopScanner: stopPurchaseBarcodeCamera,
    switchCamera: switchPurchaseBarcodeCamera,
  } = useBarcodeScanner({
    screenContext: 'IncidenteleAankoop',
    onDetected: async (detectedBarcode, scannerContext = {}) => {
      const { logEvent } = scannerContext
      const normalized = String(detectedBarcode || '').trim()
      logEvent?.('BARCODE_NORMALIZED', { normalizedBarcode: normalized })
      logEvent?.('BARCODE_FIELD_BEFORE_UPDATE', { value: String(purchaseFormRef.current?.barcode || '') })
      setPurchaseForm((current) => {
        const next = clearBarcodeLinkedFields(current, normalized)
        logEvent?.('BARCODE_FIELD_UPDATED', { value: normalized })
        return next
      })
      await processDetectedBarcode(normalized, scannerContext)
      logEvent?.('BARCODE_FIELD_AFTER_UPDATE', { value: normalized })
    },
  })

  const purchaseSublocationOptions = purchaseForm.location ? (locationOptions.sublocationsByLocation.get(purchaseForm.location) || []) : []
  const locationOptionsEmpty = locationOptions.locations.length === 0

  function updatePurchaseForm(key, value) {
    setPurchaseForm((prev) => {
      if (key === 'barcode') return clearBarcodeLinkedFields(prev, value)
      const next = { ...prev, [key]: value }
      if (key === 'location') next.sublocation = ''
      return next
    })
    if (key === 'barcode') {
      purchaseLookupRequestRef.current = ''
      setPurchaseLookupState({ status: 'idle', message: '' })
    }
    setPurchaseSaveState((prev) => (prev.status === 'idle' ? prev : { status: 'idle', message: '' }))
  }

  function applyBarcodeLookupResult(barcode, lookupResult) {
    const normalizedBarcode = String(barcode || '').trim()
    if (!normalizedBarcode || purchaseLookupRequestRef.current !== normalizedBarcode) return
    if (String(purchaseFormRef.current?.barcode || '').trim() !== normalizedBarcode) return
    setPurchaseForm((prev) => buildPurchaseFormFromBarcodeLookup(prev, normalizedBarcode, lookupResult, locationOptions))
    if (lookupResult?.found && lookupResult?.article?.name) {
      setPurchaseLookupState({ status: 'success', message: `Barcode gescand. Bekend artikel gevonden: ${lookupResult.article.name}` })
      return
    }
    if (lookupResult?.external_match && lookupResult?.article?.name) {
      const brand = String(lookupResult?.article?.brand || '').trim()
      setPurchaseLookupState({ status: 'success', message: brand ? `Barcode gescand. Productvoorstel gevonden: ${lookupResult.article.name} (${brand}).` : `Barcode gescand. Productvoorstel gevonden: ${lookupResult.article.name}.` })
      return
    }
    setPurchaseLookupState({ status: 'warning', message: 'Barcode niet gevonden. Vul artikelgegevens handmatig in.' })
  }

  async function processDetectedBarcode(barcode, scannerContext = {}) {
    const { logEvent } = scannerContext
    const normalizedBarcode = String(barcode || '').trim()
    purchaseLookupRequestRef.current = normalizedBarcode
    setPurchaseLookupState({ status: 'loading', message: `Barcode ${normalizedBarcode} controleren…` })
    setPurchaseSaveState({ status: 'idle', message: '' })
    const result = await scanBarcodeArticle(normalizedBarcode)
    applyBarcodeLookupResult(normalizedBarcode, result)
    logEvent?.('ENRICH_TRIGGERED', { barcode: String(barcode || '').trim(), found: Boolean(result?.found || result?.external_match) })
  }

  async function handleOpenBarcodeCamera() {
    if (!isMobileScanner) {
      setPurchaseLookupState({ status: 'warning', message: 'Live barcode scannen is op laptop/desktop niet de primaire route. Gebruik mobiel of vul de barcode handmatig in.' })
      return
    }
    setPurchaseLookupState({ status: 'idle', message: '' })
    setPurchaseSaveState({ status: 'idle', message: '' })
    await startPurchaseBarcodeScanner(purchaseCameraMeta.deviceId)
  }

  async function handlePurchaseSubmit() {
    const requiresArticleName = !String(purchaseForm.barcode || '').trim()
    if (requiresArticleName && (!purchaseForm.articleName || String(purchaseForm.articleName).trim() === '')) {
      setPurchaseSaveState({ status: 'error', message: 'Artikelnaam ontbreekt om op te slaan.' })
      return
    }
    if (!purchaseForm.location) {
      setPurchaseSaveState({ status: 'error', message: 'Locatie is verplicht.' })
      return
    }
    if (!purchaseForm.sublocation) {
      setPurchaseSaveState({ status: 'error', message: 'Sublocatie is verplicht.' })
      return
    }

    setPurchaseSaveState({ status: 'saving', message: 'Incidentele aankoop opslaan…' })
    try {
      let formForSave = purchaseFormRef.current
      const normalizedBarcode = String(formForSave?.barcode || '').trim()
      if (normalizedBarcode) {
        purchaseLookupRequestRef.current = normalizedBarcode
        setPurchaseLookupState({ status: 'loading', message: 'Barcode wordt automatisch gecontroleerd…' })
        const lookupResult = await scanBarcodeArticle(normalizedBarcode)
        formForSave = buildPurchaseFormFromBarcodeLookup(formForSave, normalizedBarcode, lookupResult, locationOptions)
        setPurchaseForm(formForSave)
        applyBarcodeLookupResult(normalizedBarcode, lookupResult)
      }
      await createIncidentalPurchase(formForSave, { availableSublocations: purchaseSublocationOptions })
      setPurchaseSaveState({ status: 'success', message: 'Incidentele aankoop toegevoegd aan Voorraad.' })
      window.setTimeout(() => navigate('/voorraad'), 700)
    } catch (error) {
      setPurchaseSaveState({ status: 'error', message: error.message || 'Incidentele aankoop opslaan mislukt' })
    }
  }

  function resetForm() {
    purchaseLookupRequestRef.current = ''
    setPurchaseForm(createInitialPurchaseForm())
    setPurchaseLookupState({ status: 'idle', message: '' })
    setPurchaseSaveState({ status: 'idle', message: '' })
    stopPurchaseBarcodeCamera(false, 'manual-reset')
  }

  return (
    <AppShell title="Incidentele aankoop toevoegen" showExit={false}>
      <Card>
        <div style={{ display: 'grid', gap: 16 }}>
          <p style={{ margin: 0, color: '#475467' }}>Voeg een losse aankoop direct toe aan Voorraad. Op mobiel kun je Barcode scannen gebruiken in een overlay; op laptop/desktop vul je de barcode handmatig in.</p>

          <div style={{ display: 'flex', gap: 12, flexWrap: 'wrap', alignItems: 'center' }}>
            {isMobileScanner ? (
              <Button type="button" variant="secondary" onClick={handleOpenBarcodeCamera} disabled={purchaseLookupState.status === 'loading' || purchaseCameraState.status === 'loading'}>
                {purchaseCameraState.status === 'loading' ? 'Camera openen…' : purchaseLookupState.status === 'loading' ? 'Barcode scannen…' : 'Barcode scannen'}
              </Button>
            ) : null}
            <Button type="button" variant="secondary" onClick={() => navigate('/voorraad')}>Terug naar Voorraad</Button>
            {!isMobileScanner ? <span style={{ color: '#475467', fontSize: 14 }}>Gebruik mobiel voor live scannen of vul de barcode hieronder handmatig in.</span> : null}
          </div>

          <div style={{ display: 'grid', gridTemplateColumns: 'minmax(0, 1fr)', gap: 12, alignItems: 'end' }}>
            <label className="rz-input-field">
              <div className="rz-label">Barcode</div>
              <input className="rz-input" value={purchaseForm.barcode} onChange={(event) => updatePurchaseForm('barcode', event.target.value)} placeholder="Scan met camera of vul de barcode handmatig in" />
              <div style={{ color: '#475467', fontSize: 12, marginTop: 6 }}>Bij handmatige invoer wordt de barcode automatisch gecontroleerd tijdens opslaan.</div>
            </label>
          </div>

          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(2, minmax(0, 1fr))', gap: 12 }}>
            <label className="rz-input-field">
              <div className="rz-label">Artikelnaam</div>
              <input className="rz-input" value={purchaseForm.articleName} onChange={(event) => updatePurchaseForm('articleName', event.target.value)} placeholder={String(purchaseForm.barcode || '').trim() ? 'Bekende artikelnaam of nieuwe naam' : 'Bijvoorbeeld: Waterkoker'} />
            </label>
            <label className="rz-input-field">
              <div className="rz-label">Artikelnummer</div>
              <input className="rz-input" value={purchaseForm.articleNumber} onChange={(event) => updatePurchaseForm('articleNumber', event.target.value)} placeholder="Bijvoorbeeld: SKU-12345" />
            </label>
            <label className="rz-input-field">
              <div className="rz-label">Aantal</div>
              <input className="rz-input" type="number" min="1" step="1" value={purchaseForm.quantity} onChange={(event) => updatePurchaseForm('quantity', event.target.value)} />
            </label>
            <label className="rz-input-field">
              <div className="rz-label">Aankoopdatum</div>
              <input className="rz-input" type="date" value={purchaseForm.purchaseDate} onChange={(event) => updatePurchaseForm('purchaseDate', event.target.value)} />
            </label>
            <label className="rz-input-field">
              <div className="rz-label">Locatie</div>
              <select className="rz-input" value={purchaseForm.location} onChange={(event) => updatePurchaseForm('location', event.target.value)} disabled={locationOptionsEmpty}>
                <option value="">{locationOptionsEmpty ? 'Nog geen locaties beschikbaar' : 'Kies een locatie'}</option>
                {locationOptions.locations.map((option) => <option key={option} value={option}>{option}</option>)}
              </select>
            </label>
            <label className="rz-input-field">
              <div className="rz-label">Sublocatie</div>
              <select className="rz-input" value={purchaseForm.sublocation} onChange={(event) => updatePurchaseForm('sublocation', event.target.value)} disabled={locationOptionsEmpty || !purchaseForm.location || purchaseSublocationOptions.length === 0}>
                <option value="">{locationOptionsEmpty ? 'Nog geen sublocaties beschikbaar' : 'Kies een sublocatie'}</option>
                {purchaseSublocationOptions.map((option) => <option key={option} value={option}>{option}</option>)}
              </select>
            </label>
            <label className="rz-input-field">
              <div className="rz-label">Winkel / platform</div>
              <input className="rz-input" value={purchaseForm.supplier} onChange={(event) => updatePurchaseForm('supplier', event.target.value)} placeholder="Bijvoorbeeld: Bol.com" />
            </label>
            <label className="rz-input-field">
              <div className="rz-label">Prijs (optioneel)</div>
              <input className="rz-input" inputMode="decimal" value={purchaseForm.price} onChange={(event) => updatePurchaseForm('price', event.target.value)} placeholder="0,00" />
            </label>
          </div>

          <label className="rz-input-field">
            <div className="rz-label">Notitie (optioneel)</div>
            <input className="rz-input" value={purchaseForm.note} onChange={(event) => updatePurchaseForm('note', event.target.value)} placeholder="Extra toelichting" />
          </label>

          {purchaseLookupState.message ? (
            <div className={purchaseLookupState.status === 'error' ? 'rz-inline-feedback rz-inline-feedback--error' : purchaseLookupState.status === 'warning' ? 'rz-inline-feedback rz-inline-feedback--warning' : 'rz-inline-feedback rz-inline-feedback--success'}>
              {purchaseLookupState.message}
            </div>
          ) : null}

          {purchaseSaveState.status === 'error' || purchaseSaveState.status === 'success' ? (
            <div className={purchaseSaveState.status === 'error' ? 'rz-inline-feedback rz-inline-feedback--error' : 'rz-inline-feedback rz-inline-feedback--success'}>{purchaseSaveState.message}</div>
          ) : null}

          <div style={{ display: 'flex', justifyContent: 'space-between', gap: 12, flexWrap: 'wrap' }}>
            <Button type="button" variant="secondary" onClick={resetForm}>Leegmaken</Button>
            <div style={{ display: 'flex', gap: 12, flexWrap: 'wrap' }}>
              <Button type="button" variant="secondary" onClick={() => navigate('/voorraad')}>Annuleren</Button>
              <Button type="button" variant="primary" onClick={handlePurchaseSubmit} disabled={purchaseSaveState.status === 'saving'}>{purchaseSaveState.status === 'saving' ? 'Opslaan…' : 'Opslaan'}</Button>
            </div>
          </div>
        </div>
      </Card>

      {isMobileScanner && purchaseCameraOpen ? (
        <div className="rz-modal-backdrop" role="presentation" data-testid="incidental-purchase-barcode-backdrop">
          <div className="rz-modal-card" role="dialog" aria-modal="true" aria-labelledby="incidental-purchase-barcode-title" style={{ width: 'min(760px, 100%)' }}>
            <h3 id="incidental-purchase-barcode-title" className="rz-modal-title">Barcode scannen</h3>
            <p className="rz-modal-text">Richt de barcode horizontaal en scherp in beeld. Zodra een leesbare barcode wordt gevonden, wordt het barcodeveld automatisch ingevuld.</p>
            <div style={{ display: 'flex', gap: 12, flexWrap: 'wrap', alignItems: 'center', marginBottom: 12 }}>
              <Button type="button" variant="secondary" onClick={switchPurchaseBarcodeCamera} disabled={purchaseAvailableCameras.length < 2}>Camera wisselen</Button>
              <Button type="button" variant="secondary" onClick={() => stopPurchaseBarcodeCamera(true, 'mobile-overlay-close')}>Camera sluiten</Button>
            </div>
            <div style={{ display: 'grid', gap: 10, border: '1px solid #d0d5dd', borderRadius: 18, padding: 12, background: '#f8fafc' }}>
              <video ref={purchaseBarcodeVideoRef} autoPlay muted playsInline style={{ width: '100%', maxHeight: 320, objectFit: 'cover', borderRadius: 14, background: '#101828', display: 'block' }} />
              <div className="rz-inline-feedback" style={{ marginTop: 8 }}>Camera: {purchaseCameraMeta.label || purchaseCameraMeta.deviceId || 'onbekend'} · Decodepogingen: {purchaseCameraMeta.decodeAttempts}</div>
            </div>
            {purchaseCameraState.message ? (
              <div className={purchaseCameraState.status === 'error' ? 'rz-inline-feedback rz-inline-feedback--error' : 'rz-inline-feedback rz-inline-feedback--success'} style={{ marginTop: 12 }}>{purchaseCameraState.message}</div>
            ) : null}
          </div>
        </div>
      ) : null}
    </AppShell>
  )
}
