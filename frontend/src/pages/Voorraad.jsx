import React, { useEffect, useMemo, useRef, useState } from "react";
import useBarcodeScanner from "../lib/useBarcodeScanner.js";
import { useBlocker, useNavigate } from "react-router-dom";
import Header from "../ui/Header";
import Table from "../ui/Table";
import Button from "../ui/Button";
import { nextSortState, sortItems, sortStringOptions } from "../ui/sorting";
import { buildTableWidth, ResizableHeaderCell, useResizableColumnWidths } from "../ui/resizableTable.jsx";
import useDismissOnComponentClick from "../lib/useDismissOnComponentClick.js";
import { getAuthHeaders, readStoredAuthContext } from "../lib/authSession.js";

function normalizeName(value) {
  return String(value || '').trim().toLowerCase()
}



function normalizeText(value) {
  return String(value || '').trim().toLowerCase()
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
    articleName: hasKnownArticle || hasExternalArticle
      ? matchedArticleName
      : '',
    articleNumber: hasKnownArticle || hasExternalArticle
      ? matchedArticleNumber
      : '',
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


function buildArticleDetailId(articleName, fallbackId = '', householdArticleId = '') {
  const stableHouseholdArticleId = String(householdArticleId || '').trim()
  if (stableHouseholdArticleId) return stableHouseholdArticleId
  const stableId = String(fallbackId || '').trim()
  if (stableId) return stableId
  const normalizedName = String(articleName || '').trim()
  return normalizedName ? `article::${normalizedName}` : ''
}

function buildLocalZeroVisibilityKey(row) {
  return String(row?.detailId || row?.id || row?.artikel || '')
}

function mergeVisibleZeroRows(rows = [], localZeroRows = []) {
  const existingKeys = new Set(rows.map((row) => buildLocalZeroVisibilityKey(row)))
  const appended = [...rows]
  localZeroRows.forEach((row) => {
    const key = buildLocalZeroVisibilityKey(row)
    if (!key || existingKeys.has(key)) return
    appended.push({ ...row, aantal: 0, _localZeroVisible: true })
    existingKeys.add(key)
  })
  return appended
}

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

function buildLocationOptionStateFromRows(rows = []) {
  return buildLocationOptionState(
    rows.flatMap((row) => {
      const locationName = String(row?.locatie || '').trim()
      const sublocationName = String(row?.sublocatie || '').trim()
      if (!locationName) return []
      if (normalizeText(locationName).startsWith('meerdere ')) return []
      if (sublocationName && normalizeText(sublocationName).startsWith('meerdere ')) {
        return [{ label: locationName }]
      }
      return [{ label: sublocationName ? `${locationName} / ${sublocationName}` : locationName }]
    })
  )
}

function mergeLocationOptionStates(primaryState, fallbackState) {
  const mergedLabels = []
  const seen = new Set()
  ;[primaryState, fallbackState].forEach((state) => {
    const locations = Array.isArray(state?.locations) ? state.locations : []
    const sublocationsByLocation = state?.sublocationsByLocation instanceof Map ? state.sublocationsByLocation : new Map()
    locations.forEach((locationName) => {
      const normalizedLocation = String(locationName || '').trim()
      if (!normalizedLocation) return
      const sublocations = sublocationsByLocation.get(normalizedLocation) || []
      if (!sublocations.length) {
        if (!seen.has(normalizedLocation)) {
          seen.add(normalizedLocation)
          mergedLabels.push({ label: normalizedLocation })
        }
        return
      }
      sublocations.forEach((sublocationName) => {
        const label = `${normalizedLocation} / ${String(sublocationName || '').trim()}`.trim()
        if (!label || seen.has(label)) return
        seen.add(label)
        mergedLabels.push({ label })
      })
    })
  })
  return buildLocationOptionState(mergedLabels)
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

function InlineAutocompleteSelect({
  value,
  options,
  placeholder,
  autoFocus = false,
  emptyMessage = 'Geen resultaten',
  onCommit,
  onCancel,
  onInputChange,
}) {
  const [query, setQuery] = useState(value || '')
  const [highlightedIndex, setHighlightedIndex] = useState(0)
  const rootRef = useRef(null)
  const inputRef = useRef(null)

  useEffect(() => {
    setQuery(value || '')
  }, [value])

  const filteredOptions = useMemo(() => {
    const needle = normalizeText(query)
    if (!needle) return sortStringOptions(options)
    return sortStringOptions(options.filter((option) => normalizeText(option).includes(needle)))
  }, [options, query])

  useEffect(() => {
    setHighlightedIndex(0)
  }, [query])

  useEffect(() => {
    if (!autoFocus) return
    window.setTimeout(() => {
      inputRef.current?.focus()
      inputRef.current?.select?.()
    }, 0)
  }, [autoFocus])

  const commitSelection = (nextValue) => {
    if (!options.includes(nextValue)) return
    onCommit(nextValue)
  }

  const handleBlur = (event) => {
    const nextTarget = event.relatedTarget
    if (nextTarget && rootRef.current?.contains(nextTarget)) return
    if (query === value) {
      onCancel()
      return
    }
    if (options.includes(query)) {
      onCommit(query)
      return
    }
    onCancel()
  }
  return (
    <div className="rz-inline-autocomplete" ref={rootRef}>
      <input
        ref={inputRef}
        className="rz-input rz-inline-input"
        type="text"
        value={query}
        placeholder={placeholder}
        onChange={(e) => {
          const nextValue = e.target.value
          setQuery(nextValue)
          onInputChange?.(nextValue)
        }}
        onBlur={handleBlur}
        onKeyDown={(e) => {
          if (e.key === 'ArrowDown') {
            e.preventDefault()
            setHighlightedIndex((prev) => Math.min(prev + 1, Math.max(filteredOptions.length - 1, 0)))
            return
          }
          if (e.key === 'ArrowUp') {
            e.preventDefault()
            setHighlightedIndex((prev) => Math.max(prev - 1, 0))
            return
          }
          if (e.key === 'Enter') {
            e.preventDefault()
            const selected = filteredOptions[highlightedIndex]
            if (selected) commitSelection(selected)
            return
          }
          if (e.key === 'Escape') {
            e.preventDefault()
            onCancel()
          }
        }}
      />
      <div className="rz-inline-autocomplete-menu" role="listbox" aria-label={placeholder}>
        {filteredOptions.length ? filteredOptions.map((option, index) => (
          <button
            key={option}
            type="button"
            className={`rz-inline-autocomplete-option${index === highlightedIndex ? ' is-active' : ''}`}
            onMouseDown={(e) => e.preventDefault()}
            onClick={() => commitSelection(option)}
          >
            {option}
          </button>
        )) : (
          <div className="rz-inline-autocomplete-empty">{emptyMessage}</div>
        )}
      </div>
    </div>
  )
}

function normalizeNumber(value, fallbackValue) {
  if (value === "") return "";
  const parsed = Number(String(value).replace(",", "."));
  return Number.isFinite(parsed) ? parsed : fallbackValue;
}

function mergeInventoryRows(liveRows = []) {
  const grouped = new Map()

  liveRows.forEach((row, index) => {
    const aantal = Number(row?.aantal) || 0
    if (aantal <= 0) return

    const artikel = row?.artikel || ''
    const key = normalizeName(artikel) || `unknown-${index}`
    const existing = grouped.get(key)
    const locatie = row?.locatie || ''
    const sublocatie = row?.sublocatie || ''

    if (!existing) {
      grouped.set(key, {
        id: `agg-${key}`,
        inventoryId: row.id || '',
        detailId: buildArticleDetailId(artikel, row.id, row.household_article_id) || `agg-${key}`,
        artikel,
        huishoudnaam: row?.household_article_name || '',
        productnaam: row?.product_name || artikel,
        householdArticleName: row?.household_article_name || '',
        productName: row?.product_name || artikel,
        aantal,
        locatie,
        sublocatie,
        checked: false,
        _rawCount: 1,
        _firstSeenIndex: index,
        _locationValues: new Set([locatie].filter(Boolean)),
        _sublocationValues: new Set([`${locatie}__${sublocatie}`].filter(() => Boolean(sublocatie || locatie))),
      })
      return
    }

    existing.aantal += aantal
    existing._rawCount += 1
    if (locatie) existing._locationValues.add(locatie)
    if (sublocatie || locatie) existing._sublocationValues.add(`${locatie}__${sublocatie}`)
    if (!existing.inventoryId && row.id) existing.inventoryId = row.id
    if (!existing.detailId) existing.detailId = buildArticleDetailId(existing.artikel, row.id || existing.inventoryId || existing.id, row.household_article_id) || existing.id
  })

  const merged = [...grouped.values()].map((row) => {
    const locations = [...row._locationValues]
    const sublocations = [...row._sublocationValues]
    const isAggregated = row._rawCount > 1
    const hasMultipleLocations = locations.length > 1
    const hasMultipleSublocations = sublocations.length > 1
    return {
      id: row.id,
      inventoryId: row.inventoryId || '',
      detailId: row.detailId || buildArticleDetailId(row.artikel, row.inventoryId || row.id, row.household_article_id) || row.id,
      artikel: row.artikel,
      huishoudnaam: row.huishoudnaam || '',
      productnaam: row.productnaam || row.artikel,
      householdArticleName: row.householdArticleName || '',
      productName: row.productName || row.artikel,
      aantal: row.aantal,
      locatie: hasMultipleLocations ? 'Meerdere locaties' : (locations[0] || ''),
      sublocatie: hasMultipleSublocations ? 'Meerdere sublocaties' : ((sublocations[0] || '').split('__')[1] || ''),
      checked: false,
      isAggregated,
      canOpenDetails: true,
      canInlineEditArtikel: !isAggregated,
      canInlineEditAantal: !isAggregated,
      canInlineEditLocatie: !isAggregated && !hasMultipleLocations,
      canInlineEditSublocatie: !isAggregated && !hasMultipleSublocations,
      _firstSeenIndex: row._firstSeenIndex,
    }
  })

  return merged.sort((a, b) => (a._firstSeenIndex ?? 0) - (b._firstSeenIndex ?? 0))
}
async function fetchInventoryRows() {
  const response = await fetch(`/api/dev/inventory-preview?_ts=${Date.now()}`, { cache: 'no-store', headers: getAuthHeaders() })
  if (!response.ok) throw new Error("Voorraad kon niet worden geladen")
  const data = await response.json()
  if (!Array.isArray(data?.rows)) return []
  return mergeInventoryRows(data.rows)
}

async function saveInventoryRow(row) {
  const inventoryId = String(row?.inventoryId || row?.detailId || '').trim()
  if (!inventoryId) throw new Error('Voorraadregel kan niet worden opgeslagen zonder inventory-id')

  const response = await fetch(`/api/dev/inventory/${encodeURIComponent(inventoryId)}`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json', ...getAuthHeaders() },
    body: JSON.stringify({
      naam: row.artikel,
      aantal: Number(row.aantal) || 0,
      space_name: row.locatie || null,
      sublocation_name: row.sublocatie || null,
    }),
  })

  if (!response.ok) {
    let detail = 'Opslaan mislukt'
    try {
      const errorData = await response.json()
      detail = errorData?.detail || detail
    } catch {
      // ignore
    }
    throw new Error(detail)
  }

  return response.json()
}

const initialData = [];

const editableColumns = [
  { key: "huishoudnaam", label: "Huishoudnaam", type: "text", width: "24%" },
  { key: "productnaam", label: "Productnaam", type: "text", width: "24%" },
  { key: "aantal", label: "Aantal", type: "number", width: "12%" },
  { key: "locatie", label: "Locatie", type: "text", width: "20%" },
  { key: "sublocatie", label: "Sublocatie", type: "text", width: "20%" }
];

function isColumnEditable(row, key) {
  if (key === 'huishoudnaam') return Boolean(row?.canInlineEditArtikel)
  if (key === 'aantal') return Boolean(row?.canInlineEditAantal)
  if (key === 'locatie') return Boolean(row?.canInlineEditLocatie)
  if (key === 'sublocatie') return Boolean(row?.canInlineEditSublocatie)
  return false
}

function getColumnLockMessage(row, key) {
  if (row?.isAggregated) return 'Deze rij bundelt meerdere voorraadregels en is daarom niet inline bewerkbaar.'
  if (key === 'productnaam') return 'Productnaam is afgeleid van de productcatalogus en niet inline bewerkbaar.'
  if ((key === 'locatie' && !row?.canInlineEditLocatie) || (key === 'sublocatie' && !row?.canInlineEditSublocatie)) {
    return 'Locatievelden met meerdere waarden zijn niet inline bewerkbaar.'
  }
  return 'Niet bewerkbaar'
}

export default function Voorraad() {
  const navigate = useNavigate();
  const [rows, setRows] = useState(initialData);
  const [localZeroRows, setLocalZeroRows] = useState([]);
  const rowsRef = useRef(initialData)
  const draftRowsRef = useRef(new Map())

  useEffect(() => {
    rowsRef.current = rows
  }, [rows])

  const reloadInventoryRows = async () => {
    const loadedRows = await fetchInventoryRows()
    const loadedOptions = await fetchLocationOptions().catch(() => buildLocationOptionState([]))
    const mergedLocationOptions = mergeLocationOptionStates(loadedOptions, buildLocationOptionStateFromRows(loadedRows))
    setLocalZeroRows([])
    setRows(loadedRows)
    setLocationOptions(mergedLocationOptions)
    setLoadError(loadedRows.length ? '' : 'Nog geen live voorraad beschikbaar.')
    return loadedRows
  }
  const [filters, setFilters] = useState({
    huishoudnaam: "",
    productnaam: "",
    aantal: "",
    locatie: "",
    sublocatie: ""
  });
  const [tableSort, setTableSort] = useState({ key: "huishoudnaam", direction: "asc" });
  const inventoryTableColumns = useMemo(() => ([
    { key: "select", width: 48 },
    { key: "huishoudnaam", width: 250 },
    { key: "productnaam", width: 250 },
    { key: "aantal", width: 120 },
    { key: "locatie", width: 220 },
    { key: "sublocatie", width: 220 },
  ]), []);
  const inventoryColumnDefaults = useMemo(() => Object.fromEntries(inventoryTableColumns.map(({ key, width }) => [key, width])), [inventoryTableColumns]);
  const { widths: inventoryColumnWidths, startResize: startInventoryResize } = useResizableColumnWidths(inventoryColumnDefaults);
  const [editingCell, setEditingCell] = useState(null);
  const [loadError, setLoadError] = useState("");
  const [saveState, setSaveState] = useState({});
  const [locationOptions, setLocationOptions] = useState({ locations: [], sublocationsByLocation: new Map() });
  const [showLeaveModal, setShowLeaveModal] = useState(false);
  const [showPurchaseModal, setShowPurchaseModal] = useState(false);
  const [purchaseForm, setPurchaseForm] = useState(createInitialPurchaseForm);
  const [purchaseFormSnapshot, setPurchaseFormSnapshot] = useState(() => JSON.stringify(createInitialPurchaseForm()));
  const [purchaseLookupState, setPurchaseLookupState] = useState({ status: 'idle', message: '' });
  const [purchaseSaveState, setPurchaseSaveState] = useState({ status: 'idle', message: '' });
  const purchaseFormRef = useRef(createInitialPurchaseForm());
  const purchaseLookupRequestRef = useRef('');
  const [pendingPurchaseClose, setPendingPurchaseClose] = useState(false);
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
    screenContext: 'Voorraad',
    onDetected: async (detectedBarcode, scannerContext = {}) => {
      const { logEvent } = scannerContext
      logEvent?.('BARCODE_NORMALIZED', { normalizedBarcode: String(detectedBarcode || '').trim() })
      const normalizedDetectedBarcode = String(detectedBarcode || '').trim()
      logEvent?.('BARCODE_FIELD_BEFORE_UPDATE', { value: String(purchaseFormRef.current?.barcode || '') })
      setPurchaseForm((current) => {
        const next = clearBarcodeLinkedFields(current, normalizedDetectedBarcode)
        logEvent?.('BARCODE_FIELD_UPDATED', { value: String(next.barcode || '') })
        return next
      })
      await processDetectedBarcode(normalizedDetectedBarcode, scannerContext)
      logEvent?.('BARCODE_FIELD_AFTER_UPDATE', { value: String(detectedBarcode || '') })
    },
  });

  const hasDirtyEditor = Boolean(editingCell && ['huishoudnaam', 'productnaam', 'aantal', 'locatie', 'sublocatie'].some((key) => String((editingCell?.originalRow || {})[key] ?? '') !== String((draftRowsRef.current.get(editingCell?.rowId) || rowsRef.current.find((entry) => entry.id === editingCell?.rowId) || {})[key] ?? '')));
  const hasPendingSave = Object.values(saveState).some((entry) => entry?.status === 'saving' || entry?.status === 'error');
  const purchaseFormDirty = showPurchaseModal && JSON.stringify(purchaseForm) !== purchaseFormSnapshot;
  const hasPendingPurchaseSave = purchaseSaveState.status === 'saving';
  const shouldWarnBeforeLeaving = hasDirtyEditor || hasPendingSave || purchaseFormDirty || hasPendingPurchaseSave;
  const blocker = useBlocker(shouldWarnBeforeLeaving);

  useDismissOnComponentClick([() => setLoadError(''), () => setSaveState((prev) => Object.fromEntries(Object.entries(prev).filter(([, value]) => value?.status === 'saving')))], Boolean(loadError || Object.keys(saveState).length));

  useEffect(() => {
    purchaseFormRef.current = purchaseForm;
  }, [purchaseForm]);

  useEffect(() => {
    let cancelled = false;
    Promise.all([fetchInventoryRows(), fetchLocationOptions().catch(() => buildLocationOptionState([]))])
      .then(([loadedRows, loadedOptions]) => {
        if (!cancelled) {
          const mergedLocationOptions = mergeLocationOptionStates(loadedOptions, buildLocationOptionStateFromRows(loadedRows))
          setLocalZeroRows([]);
          setRows(loadedRows);
          setLocationOptions(mergedLocationOptions);
          setLoadError(loadedRows.length ? "" : "Nog geen live voorraad beschikbaar.");
        }
      })
      .catch(() => {
        if (!cancelled) {
          setLocalZeroRows([]);
          setRows([]);
          setLoadError("Live voorraad kon niet worden geladen.");
        }
      });
    return () => {
      cancelled = true;
    };
  }, []);

  useEffect(() => {
    if (blocker.state === 'blocked') {
      setShowLeaveModal(true);
    }
  }, [blocker.state]);

  const handleStayOnVoorraad = () => {
    setShowLeaveModal(false);
    if (blocker.state === 'blocked') blocker.reset();
  };

  const handleLeaveVoorraad = () => {
    setShowLeaveModal(false);
    if (blocker.state === 'blocked') blocker.proceed();
  };

  useEffect(() => {
    const handleBeforeUnload = (event) => {
      if (!shouldWarnBeforeLeaving) return;
      event.preventDefault();
      event.returnValue = '';
    };
    window.addEventListener('beforeunload', handleBeforeUnload);
    return () => window.removeEventListener('beforeunload', handleBeforeUnload);
  }, [shouldWarnBeforeLeaving]);



  const handleFilterChange = (key, value) => {
    setFilters((prev) => ({ ...prev, [key]: value }));
  };

  const filteredRows = useMemo(() => {
    const sourceRows = mergeVisibleZeroRows(rows, localZeroRows)
    const filtered = sourceRows.filter((row) =>
      editableColumns.every((column) => {
        const filterValue = String(filters[column.key] ?? "").trim().toLowerCase();
        if (!filterValue) return true;
        return String(row[column.key] ?? "").toLowerCase().includes(filterValue);
      })
    );
    return sortItems(filtered, tableSort, {
      huishoudnaam: (row) => row.huishoudnaam || row.artikel || '',
      productnaam: (row) => row.productnaam || '',
      aantal: (row) => Number(row.aantal ?? 0),
      locatie: (row) => row.locatie || '',
      sublocatie: (row) => row.sublocatie || '',
    });
  }, [rows, localZeroRows, filters, tableSort]);

  const setRowValue = (rowId, key, value) => {
    setRows((prev) => {
      const nextRows = prev.map((row) =>
        row.id === rowId
          ? { ...row, [key]: key === "aantal" ? normalizeNumber(value, row[key]) : value, ...(key === 'huishoudnaam' ? { artikel: value, householdArticleName: value, huishoudnaam: value } : {}) }
          : row
      )
      const latestRow = nextRows.find((entry) => entry.id === rowId)
      if (latestRow) draftRowsRef.current.set(rowId, { ...latestRow })
      return nextRows
    });
  };

  const toggleRowChecked = (rowId) => {
    setRows((prev) =>
      prev.map((row) => (row.id === rowId ? { ...row, checked: !row.checked } : row))
    );
  };

  const allFilteredChecked =
    filteredRows.length > 0 && filteredRows.every((row) => row.checked);

  const toggleAllFiltered = () => {
    const nextValue = !allFilteredChecked;
    const filteredIds = new Set(filteredRows.map((row) => row.id));

    setRows((prev) =>
      prev.map((row) =>
        filteredIds.has(row.id) ? { ...row, checked: nextValue } : row
      )
    );
  };

  const startEdit = (row, key) => {
    if (!isColumnEditable(row, key)) return;
    setEditingCell({ rowId: row.id, key, originalRow: { ...row } });
  };

  const stopEdit = () => {
    setEditingCell(null);
  };

  const persistEdit = async (row) => {
    if (!editingCell || editingCell.rowId !== row.id) {
      stopEdit();
      return;
    }

    const latestRow = draftRowsRef.current.get(row.id) || rowsRef.current.find((entry) => entry.id === row.id) || row
    const originalRow = editingCell.originalRow || latestRow;
    const changed = ['huishoudnaam', 'productnaam', 'aantal', 'locatie', 'sublocatie'].some((key) => String(originalRow[key] ?? '') !== String(latestRow[key] ?? ''));

    stopEdit();

    if (!changed) {
      draftRowsRef.current.delete(row.id)
      return;
    }

    setSaveState((prev) => ({ ...prev, [row.id]: { status: 'saving', message: 'Opslaan...' } }));

    try {
      await saveInventoryRow(latestRow)
      if ((Number(latestRow.aantal) || 0) <= 0) {
        setRows((prev) => prev.map((entry) => entry.id === latestRow.id ? { ...entry, aantal: 0, _localZeroVisible: true } : entry))
        setLocalZeroRows((prev) => {
          const key = buildLocalZeroVisibilityKey(latestRow)
          const next = prev.filter((entry) => buildLocalZeroVisibilityKey(entry) !== key)
          next.push({ ...latestRow, aantal: 0, _localZeroVisible: true })
          return next
        })
      } else {
        setLocalZeroRows((prev) => prev.filter((entry) => buildLocalZeroVisibilityKey(entry) !== buildLocalZeroVisibilityKey(latestRow)))
      }
      const refreshedOptions = await fetchLocationOptions().catch(() => locationOptions)
      setLocationOptions(mergeLocationOptionStates(refreshedOptions, buildLocationOptionStateFromRows(rowsRef.current)))
      setSaveState((prev) => ({ ...prev, [row.id]: { status: 'saved', message: 'Opgeslagen' } }));
      draftRowsRef.current.delete(row.id)
      window.setTimeout(() => {
        setSaveState((prev) => {
          const next = { ...prev }
          if (next[row.id]?.status === 'saved') delete next[row.id]
          return next
        })
      }, 1600)
    } catch (error) {
      draftRowsRef.current.delete(row.id)
      setLocalZeroRows((prev) => prev.filter((entry) => buildLocalZeroVisibilityKey(entry) !== buildLocalZeroVisibilityKey(row)))
      setRows((prev) => prev.map((entry) => entry.id === row.id ? { ...entry, ...originalRow } : entry))
      setSaveState((prev) => ({ ...prev, [row.id]: { status: 'error', message: error.message || 'Opslaan mislukt' } }));
    }
  }


  const openRowDetails = (row) => {
    if (!row?.canOpenDetails) return
    const detailId = row?.detailId || row?.id
    const artikel = encodeURIComponent(row?.artikel || '')
    navigate(`/voorraad/${detailId}?artikel=${artikel}`)
  }

  const handleRowDoubleClick = (event, row) => {
    const interactiveAncestor = event.target.closest('button, input, select, textarea, a, label')
    if (interactiveAncestor) return
    openRowDetails(row)
  }

  const handleRowKeyDown = (event, row) => {
    if (event.key !== 'Enter' && event.key !== ' ') return
    const interactiveAncestor = event.target.closest('button, input, select, textarea, a, label')
    if (interactiveAncestor) return
    event.preventDefault()
    openRowDetails(row)
  }

  const getEditorOptions = (row, key, typedValue = '') => {
    if (key === 'locatie') return locationOptions.locations
    if (key === 'sublocatie') {
      const activeLocation = row?.locatie || typedValue || ''
      return locationOptions.sublocationsByLocation.get(activeLocation) || []
    }
    return []
  }

  const updatePurchaseForm = (key, value) => {
    setPurchaseForm((prev) => {
      const next = { ...prev, [key]: value }
      if (key === 'location') next.sublocation = ''
      if (key === 'barcode') next.route = String(value || '').trim() ? 'barcode' : 'manual'
      return next
    })
    if (key === 'barcode') {
      setPurchaseLookupState({ status: 'idle', message: '' })
    }
    if (key === 'articleName' || key === 'articleNumber' || key === 'quantity' || key === 'purchaseDate' || key === 'supplier' || key === 'price' || key === 'note' || key === 'location' || key === 'sublocation' || key === 'barcode') {
      setPurchaseSaveState((prev) => (prev.status === 'idle' ? prev : { status: 'idle', message: '' }))
    }
  }

  const openPurchaseModal = () => {
    const initial = createInitialPurchaseForm()
    setPurchaseForm(initial)
    setPurchaseFormSnapshot(JSON.stringify(initial))
    purchaseLookupRequestRef.current = ''
    setPurchaseLookupState({ status: 'idle', message: '' })
    setPurchaseSaveState({ status: 'idle', message: '' })
    setPendingPurchaseClose(false)
    setShowPurchaseModal(true)
  }

  const requestClosePurchaseModal = () => {
    if (purchaseSaveState.status === 'saving') return
    if (JSON.stringify(purchaseForm) !== purchaseFormSnapshot) {
      setPendingPurchaseClose(true)
      return
    }
    stopPurchaseBarcodeCamera()
    setShowPurchaseModal(false)
    setPendingPurchaseClose(false)
  }

  const confirmClosePurchaseModal = () => {
    stopPurchaseBarcodeCamera()
    setShowPurchaseModal(false)
    setPendingPurchaseClose(false)
    purchaseLookupRequestRef.current = ''
    setPurchaseLookupState({ status: 'idle', message: '' })
    setPurchaseSaveState({ status: 'idle', message: '' })
  }

  const cancelClosePurchaseModal = () => {
    setPendingPurchaseClose(false)
  }

  const applyBarcodeLookupResult = (barcode, lookupResult) => {
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


  const processDetectedBarcode = async (barcode, scannerContext = {}) => {
    const { logEvent } = scannerContext
    const normalizedBarcode = String(barcode || '').trim()
    purchaseLookupRequestRef.current = normalizedBarcode
    setPurchaseLookupState({ status: 'loading', message: `Barcode ${normalizedBarcode} controleren…` })
    setPurchaseSaveState({ status: 'idle', message: '' })
    const result = await scanBarcodeArticle(normalizedBarcode)
    applyBarcodeLookupResult(normalizedBarcode, result)
    logEvent?.('ENRICH_TRIGGERED', { barcode: String(barcode || '').trim(), found: Boolean(result?.found || result?.external_match) })
  }

  const handleOpenBarcodeCamera = async () => {
    setPurchaseLookupState({ status: 'idle', message: '' })
    setPurchaseSaveState({ status: 'idle', message: '' })
    await startPurchaseBarcodeScanner(purchaseCameraMeta.deviceId)
  }

  const handlePurchaseSubmit = async () => {
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
      await reloadInventoryRows()
      setPurchaseLookupState({ status: 'idle', message: '' })
      setPurchaseSaveState({ status: 'success', message: 'Incidentele aankoop toegevoegd aan Voorraad.' })
      setPurchaseFormSnapshot(JSON.stringify(purchaseForm))
      window.setTimeout(() => {
        const resetForm = createInitialPurchaseForm()
        setPurchaseForm(resetForm)
        setPurchaseFormSnapshot(JSON.stringify(resetForm))
        purchaseLookupRequestRef.current = ''
        setPurchaseLookupState({ status: 'idle', message: '' })
        setPurchaseSaveState((prev) => (prev.status === 'success' ? { status: 'idle', message: '' } : prev))
        setShowPurchaseModal(false)
      }, 1400)
    } catch (error) {
      setPurchaseSaveState({ status: 'error', message: error.message || 'Incidentele aankoop opslaan mislukt' })
    }
  }

  const purchaseSublocationOptions = purchaseForm.location
    ? (locationOptions.sublocationsByLocation.get(purchaseForm.location) || [])
    : []
  const locationOptionsEmpty = locationOptions.locations.length === 0

  const renderCell = (row, column) => {
    const isEditing =
      editingCell &&
      editingCell.rowId === row.id &&
      editingCell.key === column.key;
    const editable = isColumnEditable(row, column.key)

    if (isEditing) {
      if (column.key === 'locatie' || column.key === 'sublocatie') {
        return (
          <InlineAutocompleteSelect
            value={row[column.key]}
            options={getEditorOptions(row, column.key)}
            placeholder={column.key === 'locatie' ? 'Kies locatie' : 'Kies sublocatie'}
            autoFocus
            emptyMessage="Geen resultaten"
            onInputChange={(nextValue) => {
              if (column.key === 'locatie') {
                setRows((prev) => {
                  const nextRows = prev.map((entry) => entry.id === row.id ? { ...entry, locatie: nextValue, sublocatie: '' } : entry)
                  const latestRow = nextRows.find((entry) => entry.id === row.id)
                  if (latestRow) draftRowsRef.current.set(row.id, { ...latestRow })
                  return nextRows
                })
                return
              }
              setRowValue(row.id, column.key, nextValue)
            }}
            onCommit={(nextValue) => {
              if (column.key === 'locatie') {
                const validSublocations = locationOptions.sublocationsByLocation.get(nextValue) || []
                setRows((prev) => {
                  const nextRows = prev.map((entry) => entry.id === row.id ? {
                    ...entry,
                    locatie: nextValue,
                    sublocatie: validSublocations.includes(entry.sublocatie) ? entry.sublocatie : ''
                  } : entry)
                  const latestRow = nextRows.find((entry) => entry.id === row.id)
                  if (latestRow) draftRowsRef.current.set(row.id, { ...latestRow })
                  return nextRows
                })
                window.setTimeout(() => persistEdit({ ...row, locatie: nextValue, sublocatie: (locationOptions.sublocationsByLocation.get(nextValue) || []).includes(row.sublocatie) ? row.sublocatie : '' }), 0)
                return
              }
              setRows((prev) => {
                const nextRows = prev.map((entry) => entry.id === row.id ? { ...entry, [column.key]: nextValue } : entry)
                const latestRow = nextRows.find((entry) => entry.id === row.id)
                if (latestRow) draftRowsRef.current.set(row.id, { ...latestRow })
                return nextRows
              })
              window.setTimeout(() => persistEdit({ ...row, [column.key]: nextValue }), 0)
            }}
            onCancel={() => {
              setRows((prev) => prev.map((entry) => entry.id === row.id ? { ...entry, ...editingCell.originalRow } : entry))
              draftRowsRef.current.delete(row.id)
              stopEdit()
            }}
          />
        )
      }

      return (
        <input
          className="rz-input rz-inline-input"
          type={column.type}
          value={row[column.key]}
          autoFocus
          onChange={(e) => setRowValue(row.id, column.key, e.target.value)}
          onBlur={() => persistEdit(row)}
          onKeyDown={(e) => {
            if (e.key === "Enter") {
              e.preventDefault()
              persistEdit(row)
            }
            if (e.key === "Escape") {
              setRows((prev) => prev.map((entry) => entry.id === row.id ? { ...entry, ...editingCell.originalRow } : entry))
              draftRowsRef.current.delete(row.id)
              stopEdit()
            }
          }}
        />
      );
    }

    if (column.key === "huishoudnaam") {
      const label = row?.isAggregated ? `${row.huishoudnaam || row.artikel || ''} (samengevoegd)` : (row.huishoudnaam || row.artikel || '')
      return (
        <div className="rz-inline-cell rz-inline-label rz-stock-article-cell" title={row?.canOpenDetails ? 'Dubbelklik op de rij voor details' : undefined}>
          <div className="rz-article-name-primary">{label || '—'}</div>
        </div>
      );
    }

    if (column.key === "productnaam") {
      return (
        <div className="rz-inline-cell rz-inline-label rz-stock-article-cell" title={row?.productnaam || row?.productName || ''}>
          <div className="rz-article-name-secondary" style={{ fontSize: 14 }}>{row?.productnaam || row?.productName || '—'}</div>
        </div>
      )
    }

    return (
      <button
        type="button"
        className={
          "rz-inline-cell rz-inline-cell-button" +
          (column.key === "aantal" ? " rz-num" : "") +
          (editable ? "" : " rz-inline-cell-disabled")
        }
        onClick={() => startEdit(row, column.key)}
        title={editable ? 'Klik om te bewerken' : getColumnLockMessage(row, column.key)}
        aria-disabled={!editable}
        disabled={!editable}
      >
        {row[column.key]}
      </button>
    );
  };

  return (
    <div className="rz-screen" data-testid="inventory-page">
      <Header title="Voorraad" />
      <div className="rz-content">
        <div className="rz-content-inner">
          <div className="rz-card">
            {loadError && <div style={{ marginBottom: "12px", color: "#b42318", fontWeight: 700 }}>{loadError}</div>}
            <Table wrapperClassName="rz-stock-table-wrapper" tableClassName="rz-stock-table" dataTestId="inventory-table" tableStyle={{ tableLayout: 'fixed', width: buildTableWidth(inventoryColumnWidths), minWidth: buildTableWidth(inventoryColumnWidths) }}>
                <colgroup>
                  <col style={{ width: `${inventoryColumnWidths.select}px` }} />
                  <col style={{ width: `${inventoryColumnWidths.huishoudnaam}px` }} />
                  <col style={{ width: `${inventoryColumnWidths.productnaam}px` }} />
                  <col style={{ width: `${inventoryColumnWidths.aantal}px` }} />
                  <col style={{ width: `${inventoryColumnWidths.locatie}px` }} />
                  <col style={{ width: `${inventoryColumnWidths.sublocatie}px` }} />
                </colgroup>

                <thead>
                  <tr className="rz-table-header">
                    <ResizableHeaderCell columnKey="select" widths={inventoryColumnWidths} onStartResize={startInventoryResize}>
                      <input
                        type="checkbox"
                        checked={allFilteredChecked}
                        onChange={toggleAllFiltered}
                        aria-label="Selecteer alle zichtbare artikelen"
                      />
                    </ResizableHeaderCell>
                    <ResizableHeaderCell columnKey="huishoudnaam" widths={inventoryColumnWidths} onStartResize={startInventoryResize} sortable isSorted={tableSort.key === "huishoudnaam"} sortDirection={tableSort.direction} onSort={(key) => setTableSort((current) => nextSortState(current, key, { huishoudnaam: "asc", productnaam: "asc", aantal: "desc", locatie: "asc", sublocatie: "asc" }))}>Huishoudnaam</ResizableHeaderCell>
                    <ResizableHeaderCell columnKey="productnaam" widths={inventoryColumnWidths} onStartResize={startInventoryResize} sortable isSorted={tableSort.key === "productnaam"} sortDirection={tableSort.direction} onSort={(key) => setTableSort((current) => nextSortState(current, key, { huishoudnaam: "asc", productnaam: "asc", aantal: "desc", locatie: "asc", sublocatie: "asc" }))}>Productnaam</ResizableHeaderCell>
                    <ResizableHeaderCell columnKey="aantal" widths={inventoryColumnWidths} onStartResize={startInventoryResize} className="rz-num" sortable isSorted={tableSort.key === "aantal"} sortDirection={tableSort.direction} onSort={(key) => setTableSort((current) => nextSortState(current, key, { huishoudnaam: "asc", productnaam: "asc", aantal: "desc", locatie: "asc", sublocatie: "asc" }))}>Aantal</ResizableHeaderCell>
                    <ResizableHeaderCell columnKey="locatie" widths={inventoryColumnWidths} onStartResize={startInventoryResize} sortable isSorted={tableSort.key === "locatie"} sortDirection={tableSort.direction} onSort={(key) => setTableSort((current) => nextSortState(current, key, { huishoudnaam: "asc", productnaam: "asc", aantal: "desc", locatie: "asc", sublocatie: "asc" }))}>Locatie</ResizableHeaderCell>
                    <ResizableHeaderCell columnKey="sublocatie" widths={inventoryColumnWidths} onStartResize={startInventoryResize} sortable isSorted={tableSort.key === "sublocatie"} sortDirection={tableSort.direction} onSort={(key) => setTableSort((current) => nextSortState(current, key, { huishoudnaam: "asc", productnaam: "asc", aantal: "desc", locatie: "asc", sublocatie: "asc" }))}>Sublocatie</ResizableHeaderCell>
                  </tr>

                  <tr className="rz-table-filters">
                    <th />
                    <th>
                      <input
                        className="rz-input rz-inline-input"
                        value={filters.huishoudnaam}
                        onChange={(e) => handleFilterChange("huishoudnaam", e.target.value)}
                        placeholder="Filter"
                        aria-label="Filter op huishoudnaam"
                      />
                    </th>
                    <th>
                      <input
                        className="rz-input rz-inline-input"
                        value={filters.productnaam}
                        onChange={(e) => handleFilterChange("productnaam", e.target.value)}
                        placeholder="Filter"
                        aria-label="Filter op productnaam"
                      />
                    </th>
                    <th className="rz-num">
                      <input
                        className="rz-input rz-inline-input"
                        value={filters.aantal}
                        onChange={(e) => handleFilterChange("aantal", e.target.value)}
                        placeholder="Filter"
                        aria-label="Filter op aantal"
                      />
                    </th>
                    <th>
                      <input
                        className="rz-input rz-inline-input"
                        value={filters.locatie}
                        onChange={(e) => handleFilterChange("locatie", e.target.value)}
                        placeholder="Filter"
                        aria-label="Filter op locatie"
                      />
                    </th>
                    <th>
                      <input
                        className="rz-input rz-inline-input"
                        value={filters.sublocatie}
                        onChange={(e) => handleFilterChange("sublocatie", e.target.value)}
                        placeholder="Filter"
                        aria-label="Filter op sublocatie"
                      />
                    </th>
                  </tr>
                </thead>

                <tbody>
                  {filteredRows.map((row) => (
                    <tr
                      key={row.id}
                      data-testid={`inventory-row-${row.detailId || row.id}`}
                      data-open-detail-testid={row.canOpenDetails ? `inventory-open-detail-${row.detailId || row.id}` : undefined}
                      className={`rz-stock-row-interactive${row.isAggregated ? " rz-stock-row-aggregated" : ""}`}
                      onDoubleClick={(event) => handleRowDoubleClick(event, row)}
                      onKeyDown={(event) => handleRowKeyDown(event, row)}
                      tabIndex={row.canOpenDetails ? 0 : -1}
                      aria-label={row.canOpenDetails ? `Open details van ${row.huishoudnaam || row.artikel}${row.isAggregated ? '. Samengevoegde rij, inline aanpassen via details.' : ''}` : undefined}
                      title={row.isAggregated ? 'Samengevoegde rij — pas verdeling aan in details' : (row.canOpenDetails ? 'Dubbelklik voor details' : undefined)}
                    >
                      <td>
                        <input
                          type="checkbox"
                          checked={row.checked}
                          onChange={() => toggleRowChecked(row.id)}
                          aria-label={`Selecteer ${row.huishoudnaam || row.artikel}`}
                        />
                      </td>
                      {editableColumns.map((column) => (
                        <td
                          key={column.key}
                          className={column.key === "aantal" ? "rz-num" : ""}
                        >
                          {renderCell(row, column)}
                          {column.key === 'artikel' && saveState[row.id]?.message ? (
                            <div style={{ marginTop: 4, fontSize: 12, fontWeight: 700, color: saveState[row.id]?.status === 'error' ? '#b42318' : '#067647' }}>
                              {saveState[row.id].message}
                            </div>
                          ) : null}
                        </td>
                      ))}
                    </tr>
                  ))}

                  {filteredRows.length === 0 && (
                    <tr>
                      <td colSpan={6}>{loadError || "Nog geen live voorraad beschikbaar."}</td>
                    </tr>
                  )}
                </tbody>
              </Table>
            <div className="rz-stock-table-actions" style={{ justifyContent: 'flex-end', alignItems: 'center', gap: 12, flexWrap: 'wrap' }}>
              <div style={{ display: 'flex', gap: 12, flexWrap: 'wrap' }}>
                <Button type="button" variant="primary" onClick={() => navigate('/voorraad/incidentele-aankoop')} data-testid="inventory-add-incidental-purchase">Incidentele aankoop toevoegen</Button>
                <Button type="button" variant="secondary">Exporteren</Button>
              </div>
            </div>
          </div>
        </div>
      </div>

      {showPurchaseModal ? (
        <div className="rz-modal-backdrop" role="presentation" data-testid="inventory-incidental-purchase-backdrop">
          <div className="rz-modal-card" role="dialog" aria-modal="true" aria-labelledby="inventory-incidental-purchase-title" style={{ width: 'min(760px, 100%)' }}>
            <h3 id="inventory-incidental-purchase-title" className="rz-modal-title">Incidentele aankoop toevoegen</h3>
            <p className="rz-modal-text">Voeg een losse aankoop direct toe aan Voorraad. Kies Barcode scannen om de apparaatcamera te openen of vul de velden hieronder handmatig aan.</p>

            <div style={{ display: 'grid', gap: 14 }}>
              <div style={{ display: 'grid', gap: 12 }}>
                <div style={{ display: 'flex', gap: 12, flexWrap: 'wrap', alignItems: 'center' }}>
                  <Button type="button" variant="secondary" onClick={handleOpenBarcodeCamera} disabled={purchaseLookupState.status === 'loading' || purchaseCameraState.status === 'loading'} data-testid="inventory-incidental-open-barcode-camera">
                    {purchaseCameraState.status === 'loading' ? 'Camera openen…' : purchaseLookupState.status === 'loading' ? 'Barcode scannen…' : 'Barcode scannen'}
                  </Button>
                  {purchaseCameraOpen ? (
                    <>
                      <Button type="button" variant="secondary" onClick={switchPurchaseBarcodeCamera} disabled={purchaseAvailableCameras.length < 2}>Camera wisselen</Button>
                      <Button type="button" variant="secondary" onClick={() => stopPurchaseBarcodeCamera(true)} data-testid="inventory-incidental-close-barcode-camera">Camera sluiten</Button>
                    </>
                  ) : null}
                  <span style={{ color: '#475467', fontSize: 14 }}>Opent nu een live camerabeeld in deze overlay, leest de barcode live en vult daarna het formulier aan. Bij handmatige invoer wordt de barcode automatisch gecontroleerd tijdens opslaan.</span>
                </div>
                <div style={{ display: 'grid', gap: 10, border: '1px solid #d0d5dd', borderRadius: 18, padding: 12, background: '#f8fafc', opacity: purchaseCameraOpen ? 1 : 0.75 }}>
                  <video
                    ref={purchaseBarcodeVideoRef}
                    autoPlay
                    muted
                    playsInline
                    data-testid="inventory-incidental-barcode-live-camera"
                    style={{ width: '100%', maxHeight: 320, objectFit: 'cover', borderRadius: 14, background: '#101828', display: 'block', visibility: purchaseCameraOpen ? 'visible' : 'hidden' }}
                  />
                  <div style={{ color: '#475467', fontSize: 14 }}>Richt de barcode horizontaal en scherp in beeld. Zodra een leesbare barcode wordt gevonden, wordt het formulier automatisch ingevuld.</div>
                  <div className="rz-inline-feedback" style={{ marginTop: 8 }}>
                    Camera: {purchaseCameraMeta.label || purchaseCameraMeta.deviceId || 'onbekend'} · Decodepogingen: {purchaseCameraMeta.decodeAttempts}
                  </div>
                </div>
                {purchaseCameraState.message ? (
                  <div className={purchaseCameraState.status === 'error' ? 'rz-inline-feedback rz-inline-feedback--error' : 'rz-inline-feedback rz-inline-feedback--success'}>{purchaseCameraState.message}</div>
                ) : null}
                <div style={{ display: 'grid', gridTemplateColumns: 'minmax(0, 1fr) auto', gap: 12, alignItems: 'end' }}>
                  <label className="rz-input-field">
                    <div className="rz-label">Barcode</div>
                    <input className="rz-input" value={purchaseForm.barcode} onChange={(event) => updatePurchaseForm('barcode', event.target.value)} placeholder="Scan met camera of vul de barcode handmatig in" />
                  </label>
                </div>
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
              </div>

              {purchaseLookupState.message ? (
                <div className={purchaseLookupState.status === 'error' ? 'rz-inline-feedback rz-inline-feedback--error' : purchaseLookupState.status === 'warning' ? 'rz-inline-feedback rz-inline-feedback--warning' : 'rz-inline-feedback rz-inline-feedback--success'}>
                  {purchaseLookupState.message}
                </div>
              ) : null}

              {locationOptionsEmpty ? (
                <div className="rz-inline-feedback rz-inline-feedback--warning">
                  Nog geen locatie- en sublocatielijst beschikbaar. Deze dropdowns worden gevoed vanuit het onderhoudsscherm; totdat daar gegevens beschikbaar zijn worden alleen bestaande locaties uit de huidige voorraad gebruikt.
                </div>
              ) : null}

              <div style={{ display: 'grid', gridTemplateColumns: 'repeat(2, minmax(0, 1fr))', gap: 12 }}>
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

              {purchaseSaveState.status === 'error' || purchaseSaveState.status === 'success' ? (
                <div className={purchaseSaveState.status === 'error' ? 'rz-inline-feedback rz-inline-feedback--error' : 'rz-inline-feedback rz-inline-feedback--success'}>{purchaseSaveState.message}</div>
              ) : null}
            </div>

            <div className="rz-modal-actions" style={{ justifyContent: 'space-between' }}>
              <Button type="button" variant="secondary" onClick={requestClosePurchaseModal}>Annuleren</Button>
              <div style={{ display: 'flex', gap: 12, flexWrap: 'wrap' }}>
                <Button type="button" variant="secondary" onClick={() => {
                  const resetForm = createInitialPurchaseForm()
                  setPurchaseForm(resetForm)
                  setPurchaseFormSnapshot(JSON.stringify(resetForm))
                  purchaseLookupRequestRef.current = ''
                  setPurchaseLookupState({ status: 'idle', message: '' })
                  setPurchaseSaveState({ status: 'idle', message: '' })
                }}>Leegmaken</Button>
                <Button type="button" variant="primary" onClick={handlePurchaseSubmit} disabled={purchaseSaveState.status === 'saving'}>{purchaseSaveState.status === 'saving' ? 'Opslaan…' : 'Opslaan'}</Button>
              </div>
            </div>
          </div>
        </div>
      ) : null}

      {pendingPurchaseClose ? (
        <div className="rz-modal-backdrop" role="presentation">
          <div className="rz-modal-card" role="dialog" aria-modal="true" aria-labelledby="inventory-incidental-close-title">
            <h3 id="inventory-incidental-close-title" className="rz-modal-title">Wijzigingen niet opgeslagen</h3>
            <p className="rz-modal-text">Je hebt in de flow voor incidentele aankoop nog niet-opgeslagen gegevens staan. Sluit dit scherm alleen als je deze invoer wilt loslaten.</p>
            <div className="rz-modal-actions">
              <Button type="button" variant="secondary" onClick={cancelClosePurchaseModal}>Blijf op dit scherm</Button>
              <Button type="button" variant="primary" onClick={confirmClosePurchaseModal}>Sluit zonder opslaan</Button>
            </div>
          </div>
        </div>
      ) : null}

      {showLeaveModal ? (
        <div className="rz-modal-backdrop" role="presentation">
          <div className="rz-modal-card" role="dialog" aria-modal="true" aria-labelledby="voorraad-leave-title">
            <h3 className="rz-modal-title" id="voorraad-leave-title">Wijziging nog niet opgeslagen</h3>
            <p className="rz-modal-text">
              Je hebt in Voorraad een attribuut gewijzigd of een incidentele aankoop nog niet opgeslagen. Verlaat dit scherm alleen als je zeker weet dat je deze wijziging wilt loslaten.
            </p>
            <div className="rz-modal-actions">
              <Button type="button" variant="secondary" onClick={handleStayOnVoorraad}>Blijf op Voorraad</Button>
              <Button type="button" variant="primary" onClick={handleLeaveVoorraad}>Verlaat Voorraad</Button>
            </div>
          </div>
        </div>
      ) : null}
    </div>
  );
}
