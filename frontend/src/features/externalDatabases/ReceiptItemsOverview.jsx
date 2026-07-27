import { useEffect, useState } from 'react'
import Table from '../../ui/Table'
import Button from '../../ui/Button'
import { fetchJsonWithAuth } from '../../lib/authSession'
import useBarcodeScanner from '../../lib/useBarcodeScanner.js'
import BarcodeIdentityField from '../barcodes/BarcodeIdentityField.jsx'
import BarcodeScannerModal from '../barcodes/BarcodeScannerModal.jsx'
import {
  createIdleBarcodeState,
  validateAndLookupBarcode,
} from '../barcodes/barcodeReceiptWorkflow.js'

const PAGE_SIZE = 10
const MIN_VISIBLE_CANDIDATE_SCORE = 0.5
const RECEIPT_TABLE_STYLE = { width: '1160px', minWidth: '1160px' }
const CANDIDATE_TABLE_STYLE = { width: '1086px', minWidth: '1086px' }
const RECEIPT_COL_WIDTHS = ['40px', '150px', '100px', '76px', '86px', '170px', '170px', '130px', '110px', '86px', '90px']
const CANDIDATE_COL_WIDTHS = ['40px', '240px', '170px', '170px', '160px', '96px', '210px']
const FALLBACK_MARKERS = ['fallback', 'unresolved', 'no_external_match', 'receipt_product_intent_fallback']
const PSEUDO_ARTICLE_CODE_MARKERS = ['receipt_product_intent_fallback', 'product_taxonomy_seed', 'taxonomy_seed', 'retailer_seed_file', 'seed_file', 'm2c2i9_seed']
const RETAILER_PSEUDO_CODE_PREFIXES = ['ah', 'albert heijn', 'albert_heijn', 'lidl', 'aldi', 'plus', 'jumbo', 'picnic']
const RETAILER_INDEX_CODE_PATTERN = /^[A-Z][A-Z0-9 _-]{1,20}-\d{2,}$/i

function text(value, fallback = '-') {
  const normalized = String(value ?? '').trim()
  return normalized || fallback
}
function numberText(value) {
  const number = Number(value)
  if (!Number.isFinite(number)) return '-'
  return number.toLocaleString('nl-NL', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}
function scoreText(value) {
  if (value === null || value === undefined || value === '') return '-'
  const number = Number(value)
  if (!Number.isFinite(number)) return '-'
  return number.toLocaleString('nl-NL', { minimumFractionDigits: 3, maximumFractionDigits: 3 })
}
function gtinText(value) {
  const normalized = text(value, '')
  return /^\d{8}$|^\d{12}$|^\d{13}$|^\d{14}$/.test(normalized) ? normalized : '-'
}
function hasKnownGtin(value) { return gtinText(value) !== '-' }
function isRetailerPseudoArticleCode(value) {
  const normalized = text(value, '').toLowerCase()
  const colonIndex = normalized.indexOf(':')
  if (colonIndex < 1) return false
  const prefix = normalized.slice(0, colonIndex).trim()
  return RETAILER_PSEUDO_CODE_PREFIXES.includes(prefix)
}
function isRetailerIndexCode(value) {
  const normalized = text(value, '')
  if (!normalized) return false
  if (isRetailerPseudoArticleCode(normalized)) return true
  if (gtinText(normalized) !== '-') return false
  return RETAILER_INDEX_CODE_PATTERN.test(normalized)
}
function isPseudoArticleCode(value) {
  const normalized = text(value, '').toLowerCase()
  if (!normalized) return false
  if (PSEUDO_ARTICLE_CODE_MARKERS.some((marker) => normalized.includes(marker))) return true
  return isRetailerPseudoArticleCode(normalized)
}
function externalCodeText(...values) {
  for (const value of values) {
    const normalized = text(value, '')
    if (normalized && !isPseudoArticleCode(normalized)) return normalized
  }
  return '-'
}
function manualArticleNumberText(rawItem) {
  return externalCodeText(rawItem.article_number, rawItem.articleNumber, rawItem.catalog_article_number, rawItem.global_article_number, rawItem.product_article_number, rawItem.matched_article_number, rawItem.linked_article_number, rawItem.user_article_number, rawItem.manual_article_number)
}
function receiptArticleNumberText(rawItem) {
  return externalCodeText(rawItem.retailer_article_number, rawItem.source_product_code, rawItem.candidate_source_product_code, rawItem.external_article_code)
}
function retailerLabel(value) {
  const normalized = text(value, '')
  const labels = { ah: 'Albert Heijn', albert_heijn: 'Albert Heijn', jumbo: 'Jumbo', lidl: 'Lidl', aldi: 'Aldi', plus: 'PLUS', picnic: 'Picnic' }
  return labels[normalized.toLowerCase()] || normalized || 'Onbekend'
}
function isFallbackCandidate(candidate) {
  const haystack = [candidate?.candidate_status, candidate?.status, candidate?.external_source_name, candidate?.external_source_product_code, candidate?.candidate_source_name, candidate?.candidate_source_product_code, candidate?.source_name, candidate?.source_product_code, candidate?.variant, candidate?.candidate_id, candidate?.id].map((value) => text(value, '').toLowerCase()).join(' ')
  return FALLBACK_MARKERS.some((marker) => haystack.includes(marker))
}
function isSeedOrCatalogSource(candidate) {
  const source = text(candidate?.external_source_name || candidate?.candidate_source_name || candidate?.source_name, '').toLowerCase().replaceAll(' ', '_')
  return source.includes('taxonomy_seed') || source.includes('seed_file') || source.includes('catalog_enrich') || source.includes('catalog_enrichment')
}
function isPseudoArticleCandidate(candidate) {
  if (isFallbackCandidate(candidate)) return false
  const explicitCandidateCode = text(candidate?.external_source_product_code || candidate?.candidate_source_product_code || candidate?.source_product_code || candidate?.external_article_code, '')
  if (explicitCandidateCode) return isRetailerPseudoArticleCode(explicitCandidateCode)
  return isRetailerPseudoArticleCode(candidate?.retailer_article_number)
}
function candidateStatusLabel(candidate, linked, fallback, universal) {
  if (linked) return 'Gekoppeld'
  if (fallback) return 'Geen externe match'
  if (!universal) return 'Zoekhulp'
  const status = text(candidate?.candidate_status || candidate?.status, '').toLowerCase()
  if (status === 'linked_to_catalog') return 'Gekoppeld'
  if (status === 'user_confirmed') return 'Bevestigd'
  if (status === 'probable_candidate') return 'Waarschijnlijke kandidaat'
  if (status === 'weak_candidate') return 'Lage zekerheid'
  if (status === 'off_candidate') return 'OFF-kandidaat'
  if (status === 'off_low_score_candidate') return 'OFF lage zekerheid'
  return text(candidate?.status_label || candidate?.candidate_status || candidate?.status || 'Kandidaat')
}
function candidateKey(candidate) { return text(candidate?.candidate_id || candidate?.id || `${candidate?.candidate_name}-${candidate?.candidate_source_product_code || candidate?.external_source_product_code}-${candidate?.variant}`, 'candidate') }
function hasCatalogLink(candidate) { return candidate?.central_link_active === true }
function receiptItemHasCatalogLink(rawItem) {
  // Alleen een actieve centrale koppeling betekent Gekoppeld.
  return rawItem?.central_link_active === true
}
function candidateArticleNumber(candidate) { return externalCodeText(candidate?.external_source_product_code, candidate?.candidate_source_product_code, candidate?.source_product_code, candidate?.retailer_article_number, candidate?.external_article_code) }
function candidateHasUniversalCode(candidate, externalCode) {
  if (candidate?.has_universal_code === true) return true
  return [externalCode, candidate?.gtin, candidate?.ean, candidate?.code, candidate?.external_source_product_code, candidate?.candidate_source_product_code, candidate?.source_product_code].some((value) => gtinText(value) !== '-')
}
function candidateTypeLabel(candidate, externalCode, universal) {
  if (universal) return 'Universele code'
  if (candidate?.is_retailer_index_candidate === true || isRetailerIndexCode(externalCode) || isSeedOrCatalogSource(candidate)) return 'Zoekhulp'
  if (isFallbackCandidate(candidate)) return 'Fallback'
  return 'Niet-universeel'
}
function buildCandidate(candidate) {
  const linked = candidate?.is_linked_to_catalog === true
  const fallback = isFallbackCandidate(candidate)
  const externalCode = candidateArticleNumber(candidate)
  const universal = candidateHasUniversalCode(candidate, externalCode)
  const type = candidateTypeLabel(candidate, externalCode, universal)
  return { id: candidateKey(candidate), candidateName: text(candidate?.candidate_name), brand: text(candidate?.candidate_brand), source: text(candidate?.external_source_name || candidate?.candidate_source_name || candidate?.source_name), externalCode, score: candidate?.score, status: candidateStatusLabel(candidate, linked, fallback, universal), type, hasUniversalCode: universal, isLinkedToCatalog: linked, catalogLinked: hasCatalogLink(candidate), isFallbackCandidate: fallback, isSearchHelper: type === 'Zoekhulp', isLinkableToCatalog: Boolean(candidate?.is_linkable_to_catalog) && universal && !linked && !fallback, raw: candidate }
}
function candidateMeetsScoreThreshold(candidate) {
  if (candidate?.isLinkedToCatalog || candidate?.isFallbackCandidate) return true
  const score = Number(candidate?.score)
  return Number.isFinite(score) && score >= MIN_VISIBLE_CANDIDATE_SCORE
}
function isVisibleSelectionCandidate(candidate) { return !candidate?.isSearchHelper && candidateMeetsScoreThreshold(candidate) }
function dedupeCandidates(candidates) {
  const deduped = new Map()
  candidates.forEach((candidate) => {
    const raw = candidate.raw || {}
    const source = text(candidate.source || raw.external_source_name || raw.candidate_source_name || raw.source_name, '').toLowerCase()
    const code = text(candidate.externalCode || raw.external_source_product_code || raw.candidate_source_product_code || raw.source_product_code || raw.retailer_article_number, '').toLowerCase()
    const rawGtin = text(raw.gtin || raw.ean, '').toLowerCase()
    const key = source && code ? `${source}:${code}` : rawGtin || `${candidate.candidateName}:${candidate.brand}`.toLowerCase()
    const current = deduped.get(key)
    if (!current || candidate.isLinkedToCatalog || Number(candidate.score || 0) > Number(current.score || 0)) deduped.set(key, candidate)
  })
  return Array.from(deduped.values())
}
function rowKey(item) { return text(item?.receipt_item_id, '') }
function rawGtin(rawItem) { return gtinText(rawItem.linked_gtin || rawItem.primary_gtin || rawItem.gtin || rawItem.ean || rawItem.barcode) }
function buildReceiptItems(rawItems) {
  const grouped = new Map()
  rawItems.forEach((rawItem) => {
    const key = rowKey(rawItem)
    if (!key) {
      console.error('Bonartikel zonder receipt_item_id ontvangen', rawItem)
      return
    }
    const itemGtin = rawGtin(rawItem)
    const current = grouped.get(key) || { id: key, receiptItemId: key, receiptItemType: text(rawItem.receipt_item_type, ''), receiptItemSourceId: text(rawItem.receipt_item_source_id, ''), contextKey: text(rawItem.context_key, ''), receiptLineId: text(rawItem.receipt_line_id, ''), purchaseImportLineId: text(rawItem.purchase_import_line_id, ''), receiptLineText: text(rawItem.receipt_line_text), retailerCode: retailerLabel(rawItem.retailer_code), retailerCodeRaw: text(rawItem.retailer_code, ''), articleNumber: manualArticleNumberText(rawItem), receiptArticleNumber: receiptArticleNumberText(rawItem), gtin: itemGtin, quantity: text(rawItem.quantity_label), price: rawItem.price ?? '-', catalogLinked: receiptItemHasCatalogLink(rawItem), status: receiptItemHasCatalogLink(rawItem) ? 'Gekoppeld' : (itemGtin !== '-' ? 'GTIN / EAN bekend' : 'Nog niet verwerkt'), linkedCandidateName: text(rawItem.linked_candidate_name, ''), linkedProductTypeId: text(rawItem.linked_product_type_id || rawItem.product_type_id || rawItem.inventory_group_key, ''), linkedProductType: text(rawItem.linked_product_type || rawItem.product_type_label || rawItem.gpc_brick_name, ''), linkedScore: rawItem.linked_score ?? null, globalProductId: text(rawItem.global_product_id, ''), candidates: [], hasKnownGtin: itemGtin !== '-' }
    const nested = rawItem.is_receipt_item_placeholder && Array.isArray(rawItem.candidates) ? rawItem.candidates : [rawItem]
    nested.filter(Boolean).forEach((candidate) => {
      if (current.hasKnownGtin) return
      if (isPseudoArticleCandidate(candidate)) return
      const built = buildCandidate(candidate)
      if (built.raw?.is_receipt_item_placeholder && built.raw?.candidate_status === 'no_candidate') return
      current.candidates.push(built)
      if (built.catalogLinked) { current.catalogLinked = true; current.status = 'Gekoppeld' }
    })
    grouped.set(key, current)
  })
  return Array.from(grouped.values()).map((item) => {
    const candidates = item.hasKnownGtin ? [] : dedupeCandidates(item.candidates).sort((left, right) => {
      if (left.hasUniversalCode !== right.hasUniversalCode) return left.hasUniversalCode ? -1 : 1
      return Number(right.score || 0) - Number(left.score || 0)
    })
    const linked = candidates.find((candidate) => candidate.isLinkedToCatalog)
    const selectableBest = candidates.find((candidate) => candidate.hasUniversalCode && !candidate.isFallbackCandidate && candidateMeetsScoreThreshold(candidate)) || null
    // Functioneel PO-besluit: de hoofdtabel toont uitsluitend een definitieve
    // Cataloguskoppeling of een kandidaat met een universele GTIN/EAN.
    // Retailer- en leverancierscodes blijven alleen interne zoekhulp.
    const displayBest = linked || selectableBest
    const hasSelectableCandidate = candidates.some((candidate) => candidate.hasUniversalCode && !candidate.isFallbackCandidate && candidateMeetsScoreThreshold(candidate))
    const hasFallback = candidates.some((candidate) => candidate.isFallbackCandidate)
    return { ...item, candidates, status: item.catalogLinked ? 'Gekoppeld' : (item.hasKnownGtin ? 'GTIN / EAN bekend' : (hasSelectableCandidate ? 'Universele kandidaten gevonden' : (hasFallback ? 'Geen externe match' : 'Geen universele kandidaat'))), candidateCount: candidates.filter((candidate) => candidate.hasUniversalCode && !candidate.isFallbackCandidate && candidateMeetsScoreThreshold(candidate)).length, bestCandidateName: item.catalogLinked && item.linkedCandidateName ? item.linkedCandidateName : (item.hasKnownGtin ? '' : text(displayBest?.candidateName, '')), productType: item.linkedProductType || (
        item.catalogLinked
          ? 'Nog niet geclassificeerd'
          : ''
      ), bestCandidateCode: item.catalogLinked && item.gtin !== '-' ? item.gtin : (item.hasKnownGtin ? item.gtin : text(selectableBest?.externalCode, '')), bestCandidateScore: item.catalogLinked && item.linkedScore !== null ? item.linkedScore : (item.hasKnownGtin ? null : displayBest?.score ?? null), gtin: item.gtin, bestSelectableCandidateName: item.hasKnownGtin ? '' : text(selectableBest?.candidateName, '') }
  })
}
function offStatusLabel(preview) {
  if (!preview) return '-'
  if (preview.status === 'found') return 'Gevonden'
  if (preview.status === 'no_results') return 'Geen resultaten'
  if (preview.status === 'external_source_unavailable') return 'OFF niet beschikbaar'
  if (preview.status === 'skipped_known_gtin') return 'GTIN / EAN al bekend'
  return text(preview.status)
}
function defaultOffQuery(item) { return text(item?.receiptLineText || item?.bestSelectableCandidateName || item?.bestCandidateName, '') }
function candidateGpcBrickCode(candidate) {
  const raw = candidate?.raw || {}
  const value = raw.gpc_brick_code || raw.gpcBrickCode || raw.gpc_code || raw.gpcCode || ''
  const normalized = String(value ?? '').trim()
  return /^\d{8}$/.test(normalized) ? normalized : ''
}
function suggestProductTypeId(candidate, options) {
  if (!candidate || !Array.isArray(options) || !options.length) return ''
  const brickCode = candidateGpcBrickCode(candidate)
  if (!brickCode) return ''
  const expectedKey = `gpc:${brickCode}`
  const exact = options.find((option) =>
    String(option?.inventory_group_key || '') === expectedKey
    && String(option?.gpc_brick_code || '') === brickCode
    && String(option?.source || '') === 'gs1_gpc_nl'
  )
  return exact ? expectedKey : ''
}

export default function ReceiptItemsOverview({ onError, onMessage }) {
  const [items, setItems] = useState([])
  const [selectedItem, setSelectedItem] = useState(null)
  const [selectedCandidateId, setSelectedCandidateId] = useState('')
  const [selectedItemIds, setSelectedItemIds] = useState([])
  const [isOffLoading, setIsOffLoading] = useState(false)
  const [showSearchComplete, setShowSearchComplete] = useState(false)
  const [offPreview, setOffPreview] = useState(null)
  const [offSearchResults, setOffSearchResults] = useState([])
  const [offError, setOffError] = useState('')
  const [offSearchText, setOffSearchText] = useState('')
  const [offSearchMode, setOffSearchMode] = useState('automatisch')
  const [productTypeOptions, setProductTypeOptions] = useState([])
  const [productTypeMode, setProductTypeMode] = useState('existing')
  const [selectedProductTypeId, setSelectedProductTypeId] = useState('')
  const [newProductTypeName, setNewProductTypeName] = useState('')
  const [newProductTypeBaseUnit, setNewProductTypeBaseUnit] = useState('stuk')
  const [newProductTypeAggregationMode, setNewProductTypeAggregationMode] = useState('count')
  const [isLinkingProductType, setIsLinkingProductType] = useState(false)
  const [isClassifyingProductType, setIsClassifyingProductType] = useState(false)
  const [productTypeClassificationStatus, setProductTypeClassificationStatus] = useState('')
  const [filters, setFilters] = useState({ receiptLineText: '', retailerCode: '', catalogLinked: 'all', quantity: '', price: '', bestCandidateName: '', productType: '', bestCandidateCode: '', bestCandidateScore: '', candidateCount: '' })
  const [sortKey, setSortKey] = useState('receiptLineText')
  const [sortDesc, setSortDesc] = useState(false)
  const [page, setPage] = useState(1)
  const [pageCount, setPageCount] = useState(1)
  const [totalItems, setTotalItems] = useState(0)
  const [barcodeDraft, setBarcodeDraft] = useState('')
  const [barcodeState, setBarcodeState] = useState(createIdleBarcodeState())
  const [barcodeConfirmation, setBarcodeConfirmation] = useState(null)
  const [isSavingBarcode, setIsSavingBarcode] = useState(false)

  const barcodeScanner = useBarcodeScanner({
    screenContext: 'Externe databases',
    onDetected: async (detectedBarcode) => {
      setBarcodeDraft(detectedBarcode)
      await validateSelectedBarcode(detectedBarcode)
    },
  })

  async function requestBarcodeJson(url, options = {}) {
    const response = await fetchJsonWithAuth(url, {
      ...options,
      headers: {
        'Content-Type': 'application/json',
        ...(options.headers || {}),
      },
    })
    const data = await response.json().catch(() => ({}))
    if (!response.ok) {
      throw new Error(
        data?.detail
        || data?.message
        || 'De barcodeactie is mislukt'
      )
    }
    return data
  }

  async function validateSelectedBarcode(value = barcodeDraft) {
    if (!selectedItem) return

    setBarcodeState({
      ...createIdleBarcodeState(),
      status: 'loading',
    })
    setBarcodeConfirmation(null)

    try {
      const result = await validateAndLookupBarcode({
        value,
        requestJson: requestBarcodeJson,
        fallbackProductName: selectedItem.receiptLineText,
      })

      setBarcodeState(result.state)

      if (!result.ok) {
        onError?.(
          result.state?.message
          || 'Dit is geen geldige barcode.'
        )
        return
      }

      setBarcodeDraft(result.confirmation.gtin)
      setBarcodeConfirmation(result.confirmation)
    } catch (error) {
      setBarcodeState({
        ...createIdleBarcodeState(),
        status: 'error',
        message: error?.message || 'De barcode kon niet worden gecontroleerd.',
      })
      onError?.(
        error?.message
        || 'De barcode kon niet worden gecontroleerd.'
      )
    }
  }

  async function saveSelectedBarcode() {
    if (!selectedItem || !barcodeConfirmation?.gtin) return

    setIsSavingBarcode(true)

    try {
      const data = await requestBarcodeJson(
        `/api/barcodes/${encodeURIComponent(barcodeConfirmation.gtin)}/save-receipt-item`,
        {
          method: 'POST',
          body: JSON.stringify({
            receipt_item_id: selectedItem.receiptItemId || selectedItem.id,
            article_name: selectedItem.receiptLineText,
          }),
        },
      )

      setBarcodeDraft(String(data?.gtin || barcodeConfirmation.gtin))
      setBarcodeState({
        ...createIdleBarcodeState(),
        status: 'success',
        gtin: String(data?.gtin || barcodeConfirmation.gtin),
        productName: String(data?.product?.name || ''),
        globalProductId: String(
          data?.product?.global_product_id || ''
        ),
        product: data?.product || null,
      })
      setBarcodeConfirmation(null)

      onMessage?.('De barcode is opgeslagen en het bonartikel is gekoppeld.')

      void loadItems().catch((refreshError) => {
        onError?.(
          refreshError?.message
          || 'De koppeling is opgeslagen, maar de bonartikelenlijst kon niet worden vernieuwd.',
        )
      })
    } catch (error) {
      onError?.(
        error?.message
        || 'De barcode kon niet worden opgeslagen.'
      )
    } finally {
      setIsSavingBarcode(false)
    }
  }

  useEffect(() => {
    const selectedGtin = gtinText(selectedItem?.gtin)

    setBarcodeDraft(selectedGtin === '-' ? '' : selectedGtin)
    setBarcodeState(createIdleBarcodeState())
    setBarcodeConfirmation(null)
  }, [selectedItem?.id])

  async function fetchItems() {
    const params = new URLSearchParams({
      page: String(page),
      page_size: String(PAGE_SIZE),
      sort_key: sortKey,
      sort_desc: String(sortDesc),
    })
    Object.entries(filters).forEach(([key, value]) => {
      const normalized = String(value ?? '').trim()
      if (normalized || key === 'catalogLinked') params.set(key, normalized || 'all')
    })
    const response = await fetchJsonWithAuth(`/api/external-databases/receipt-items?${params.toString()}`, { method: 'GET' })
    const data = await response.json().catch(() => ({}))
    if (!response.ok) throw new Error(data?.detail || 'Bonartikelen konden niet worden geladen')
    return {
      items: buildReceiptItems(Array.isArray(data?.items) ? data.items : []),
      total: Number(data?.total || 0),
      pageCount: Math.max(1, Number(data?.page_count || 1)),
      page: Math.max(1, Number(data?.page || page)),
    }
  }

  async function findCatalogProductByGtin(gtin) {
    const normalizedGtin = gtinText(gtin)

    if (normalizedGtin === '-') return null

    const response = await fetchJsonWithAuth(
      `/api/catalog?query=${encodeURIComponent(normalizedGtin)}&limit=20`,
      { method: 'GET' },
    )

    const data = await response.json().catch(() => ({}))

    if (!response.ok) {
      throw new Error(
        data?.detail
        || 'De Catalogus kon niet op GTIN worden gecontroleerd',
      )
    }

    const items = Array.isArray(data?.items) ? data.items : []

    return items.find(
      (product) =>
        gtinText(product?.primary_gtin) === normalizedGtin,
    ) || null
  }

  async function enrichOffResultsWithCatalog(results) {
    const sourceResults = Array.isArray(results) ? results : []
    const catalogProducts = new Map()

    await Promise.all(
      sourceResults.map(async (result) => {
        const gtin = gtinText(
          result?.gtin
          || result?.ean
          || result?.code,
        )

        if (gtin === '-' || catalogProducts.has(gtin)) return

        const product = await findCatalogProductByGtin(gtin)
        catalogProducts.set(gtin, product)
      }),
    )

    return sourceResults.map((result) => {
      const gtin = gtinText(
        result?.gtin
        || result?.ean
        || result?.code,
      )
      const product = catalogProducts.get(gtin) || null

      return {
        ...result,
        existing_catalog_product: product,
      }
    })
  }
  async function loadItems() {
    try {
      const payload = await fetchItems()
      const nextItems = payload.items
      setItems(nextItems)
      setTotalItems(payload.total)
      setPageCount(payload.pageCount)
      if (payload.page !== page) setPage(payload.page)
      setSelectedItem((current) => current ? nextItems.find((item) => item.id === current.id) || null : null)
      setSelectedItemIds((current) => current.filter((id) => nextItems.some((item) => item.id === id)))
    } catch (err) { onError?.(err?.message || 'Bonartikelen konden niet worden geladen') }
  }
  async function loadProductTypeOptions() {
    const response = await fetchJsonWithAuth('/api/inventory/groups', { method: 'GET' })
    const data = await response.json().catch(() => ({}))
    if (!response.ok) throw new Error(data?.detail || 'Producttypen konden niet worden geladen')
    const options = Array.isArray(data?.group_options) ? data.group_options : []
    setProductTypeOptions(options.filter((option) =>
      option?.inventory_group_key
      && option?.display_name
      && /^gpc:\d{8}$/.test(String(option.inventory_group_key))
      && /^\d{8}$/.test(String(option.gpc_brick_code || ''))
      && String(option.source || '').startsWith('gs1_gpc_')
    ))
  }
  useEffect(() => {
    loadProductTypeOptions().catch((err) => onError?.(err?.message || 'Producttypen konden niet worden geladen'))
  }, [])

  useEffect(() => {
    loadItems()
  }, [page, sortKey, sortDesc, filters])

  useEffect(() => {
    if (!selectedItem) return
    if (items.some((item) => item.id === selectedItem.id)) return
    setSelectedItem(null); setSelectedCandidateId(''); setOffPreview(null); setOffSearchResults([]); setOffError(''); setOffSearchText(''); setOffSearchMode('automatisch'); setProductTypeMode('existing'); setSelectedProductTypeId(''); setNewProductTypeName('')
  }, [items, selectedItem])

  const currentPage = Math.min(page, pageCount)
  const visibleItems = items
  const emptyRows = Math.max(0, PAGE_SIZE - visibleItems.length)
  const visibleIds = visibleItems.map((item) => item.id)
  const allVisibleSelected = visibleIds.length > 0 && visibleIds.every((id) => selectedItemIds.includes(id))
  const linkedSelectedCandidate = selectedItem?.catalogLinked ? {
    id: `linked:${selectedItem.globalProductId || selectedItem.gtin}`,
    candidateName: text(selectedItem.linkedCandidateName || selectedItem.bestCandidateName),
    brand: '-',
    source: 'Artikelcatalogus',
    externalCode: text(selectedItem.gtin),
    score: selectedItem.linkedScore ?? selectedItem.bestCandidateScore,
    status: 'Gekoppeld',
    hasUniversalCode: true,
    isLinkedToCatalog: true,
    isLinkableToCatalog: false,
    raw: {
      global_product_id: selectedItem.globalProductId,
      gtin: selectedItem.gtin,
      linked_product_type_id: selectedItem.linkedProductTypeId,
    },
  } : null
  const selectedCandidates = linkedSelectedCandidate ? [linkedSelectedCandidate] : offSearchResults.map((result) => {
    const catalogProduct = result?.existing_catalog_product || null
    const catalogLinked = Boolean(catalogProduct)
    const gtin = gtinText(result?.gtin || result?.ean || result?.code)

    return {
      id: catalogLinked
        ? `linked:${catalogProduct.id || gtin}`
        : `off:${gtin}`,
      candidateName: catalogLinked
        ? text(catalogProduct.name)
        : text(result.product_name),
      brand: catalogLinked
        ? text(catalogProduct.brand)
        : text(result.brand),
      source: catalogLinked
        ? 'Artikelcatalogus'
        : 'Open Food Facts',
      externalCode: gtin,
      score: result.automatic_rank_score ?? result.score,
      status: catalogLinked ? 'Gekoppeld' : 'OFF-kandidaat',
      hasUniversalCode: true,
      isLinkedToCatalog: catalogLinked,
      catalogLinked,
      isLinkableToCatalog: !catalogLinked,
      automaticRankScore: result.automatic_rank_score ?? null,
      automaticEvidence: result.automatic_evidence ?? null,
      raw: {
        ...result,
        global_product_id: catalogProduct?.id || '',
        matched_global_product_id: catalogProduct?.id || '',
        primary_gtin: catalogProduct?.primary_gtin || gtin,
      },
    }
  })
  const selectedCandidate = selectedCandidates.find((candidate) => candidate.id === selectedCandidateId) || null
  const hasValidProductTypeDecision = /^gpc:\d{8}$/.test(String(selectedProductTypeId || ''))
  const selectedCandidateCanBeLinked = Boolean(selectedItem && selectedCandidate && !isLinkingProductType && !isClassifyingProductType)
  const selectedCandidateCanBeUnlinked = false
  const selectedItemHasKnownGtin = Boolean(selectedItem?.hasKnownGtin || hasKnownGtin(selectedItem?.gtin))

  function updateFilter(key, value) { setFilters((current) => ({ ...current, [key]: value })); setPage(1) }
  function updateSort(key) { if (sortKey === key) setSortDesc((value) => !value); else { setSortKey(key); setSortDesc(false) }; setPage(1) }
  function sortMark(key) { return sortKey === key && !sortDesc ? '^' : 'v' }
  function toggleSelectedItem(itemId) { setSelectedItemIds((current) => current.includes(itemId) ? current.filter((id) => id !== itemId) : [...current, itemId]) }
  function toggleVisibleItems() { setSelectedItemIds((current) => allVisibleSelected ? current.filter((id) => !visibleIds.includes(id)) : Array.from(new Set([...current, ...visibleIds]))) }
  function goToPage(targetPage) { setPage(Math.max(1, Math.min(pageCount, targetPage))) }
  function selectReceiptItem(item) { const linkedCandidateId = item.catalogLinked ? `linked:${item.globalProductId || item.gtin}` : ''; setSelectedItem(item); setSelectedCandidateId(linkedCandidateId); setOffPreview(null); setOffSearchResults([]); setOffError(''); setOffSearchText(defaultOffQuery(item)); setOffSearchMode('automatisch'); setProductTypeMode('existing'); setSelectedProductTypeId(item.catalogLinked ? item.linkedProductTypeId : ''); setNewProductTypeName(''); if (!item.hasKnownGtin) consultOpenFoodFactsForItem(item, defaultOffQuery(item), 'automatisch') }

  useEffect(() => {
    let cancelled = false
    async function classifySelectedCandidate() {
      if (!selectedCandidate) {
        setSelectedProductTypeId(selectedItem?.catalogLinked ? selectedItem.linkedProductTypeId : '')
        setProductTypeClassificationStatus('')
        return
      }
      const linkedProductTypeId = selectedCandidate.isLinkedToCatalog ? selectedItem?.linkedProductTypeId : ''
      const explicitSuggestion = linkedProductTypeId || suggestProductTypeId(selectedCandidate, productTypeOptions)
      setProductTypeMode('existing')
      setNewProductTypeName(selectedCandidate.candidateName === '-' ? '' : selectedCandidate.candidateName)
      if (explicitSuggestion) {
        setSelectedProductTypeId(explicitSuggestion)
        setProductTypeClassificationStatus('Producttype bepaald via expliciete GPC Brickcode.')
        return
      }
      if (selectedCandidate.isLinkedToCatalog) {
        setSelectedProductTypeId('')
        setProductTypeClassificationStatus('GPC-classificatie ontbreekt.')
        return
      }
      setIsClassifyingProductType(true)
      setSelectedProductTypeId('')
      setProductTypeClassificationStatus('Producttype wordt bepaald...')
      try {
        const raw = selectedCandidate.raw || {}
        const response = await fetchJsonWithAuth('/api/external-products/gpc/classify', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            product_name: raw.product_name || selectedCandidate.candidateName,
            category: raw.category || raw.categories || '',
            gpc_brick_code: candidateGpcBrickCode(selectedCandidate),
          }),
        })
        const data = await response.json().catch(() => ({}))
        if (!response.ok) throw new Error(data?.detail || 'GPC-classificatie is mislukt')
        if (cancelled) return
        if (data?.status === 'classified' && /^gpc:\d{8}$/.test(String(data.product_type_id || ''))) {
          const option = {
            inventory_group_key: data.product_type_id,
            display_name: data.gpc_brick_name || data.gpc_brick_name_en || data.product_type_id,
            gpc_brick_code: data.gpc_brick_code,
            source: data.source || 'gs1_gpc_2026_05_en',
          }
          setProductTypeOptions((current) => current.some((item) => item.inventory_group_key === option.inventory_group_key) ? current : [...current, option])
          setSelectedProductTypeId(option.inventory_group_key)
          setProductTypeClassificationStatus(`Automatisch bepaald met zekerheid ${Number(data.confidence || 0).toLocaleString('nl-NL', { minimumFractionDigits: 3, maximumFractionDigits: 3 })}.`)
        } else {
          setSelectedProductTypeId('')
          setProductTypeClassificationStatus('GPC-classificatie niet eenduidig; koppelen is geblokkeerd.')
        }
      } catch (err) {
        if (!cancelled) {
          setSelectedProductTypeId('')
          setProductTypeClassificationStatus(err?.message || 'GPC-classificatie is mislukt')
        }
      } finally {
        if (!cancelled) setIsClassifyingProductType(false)
      }
    }
    classifySelectedCandidate()
    return () => { cancelled = true }
  }, [selectedCandidateId, productTypeOptions.length, selectedItem?.id, selectedItem?.linkedProductTypeId, selectedItem?.catalogLinked])

  function exportSelectedItems() {
    const selectedRows = items.filter((item) => selectedItemIds.includes(item.id))
    if (!selectedRows.length) { onMessage?.('Selecteer eerst een of meer bonartikelen om te exporteren.'); return }
    const rows = [['Bonartikel', 'Winkelketen', 'Catalogus', 'Score', '(Kand.) artikel', 'Producttype', '(Kand.) GTIN/EAN', 'Omvang / gewicht', 'Prijs', 'Externe kandidaten'], ...selectedRows.map((item) => [item.receiptLineText, item.retailerCode, item.catalogLinked ? 'Gekoppeld' : 'Niet gekoppeld', scoreText(item.bestCandidateScore), item.bestCandidateName || '-', item.productType || '-', item.bestCandidateCode || '-', item.quantity, numberText(item.price), item.candidateCount])]
    const blob = new Blob([rows.map((row) => row.map((value) => `"${String(value ?? '').replaceAll('"', '""')}"`).join(';')).join('\r\n')], { type: 'text/csv;charset=utf-8' })
    const url = URL.createObjectURL(blob); const link = document.createElement('a'); link.href = url; link.download = 'rezzerv-externe-databases-bonartikelen.csv'; link.click(); URL.revokeObjectURL(url); onMessage?.(`Export gemaakt voor ${selectedRows.length} bonartikel(en).`)
  }
  async function processSelectedCandidate() {
    if (!selectedItem || !selectedCandidate || !selectedCandidateCanBeLinked) return
    const productTypeAssignment = hasValidProductTypeDecision ? {
      product_type_id: selectedProductTypeId,
      mapping_source: 'external_gs1_gpc',
      confidence_score: 1,
    } : null
    setIsLinkingProductType(true)
    try {
      const raw = selectedCandidate.raw || {}
      const response = await fetchJsonWithAuth('/api/external-products/off/link', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          receipt_item_id: selectedItem.receiptItemId || selectedItem.id,
          off_product: {
            gtin: raw.gtin || raw.code || selectedCandidate.externalCode,
            product_name: raw.product_name || selectedCandidate.candidateName,
            brand: raw.brand || selectedCandidate.brand,
            category: raw.category || raw.categories || '',
            quantity: raw.quantity || raw.quantity_label || raw.net_content || selectedItem.quantity,
            source_url: raw.source_url || raw.url || '',
            variant: raw.variant || '',
          },
          ...(productTypeAssignment ? { product_type_assignment: productTypeAssignment } : {}),
        }),
      })
      const data = await response.json().catch(() => ({}))
      if (!response.ok) throw new Error(data?.detail || 'Artikel en Producttype koppelen is mislukt')
      if (hasValidProductTypeDecision) {
        const selectedProductType = productTypeOptions.find((option) => option.inventory_group_key === selectedProductTypeId)
        const productTypeLabel = selectedProductType
          ? `${selectedProductType.display_name} — GPC ${selectedProductType.gpc_brick_code}`
          : selectedProductTypeId
        onMessage?.(`Kandidaat is aan het bonartikel gekoppeld met Producttype ${productTypeLabel}.`)
      } else {
        onMessage?.('Kandidaat is aan het bonartikel gekoppeld. Het Producttype moet nog worden vastgesteld.')
      }
      setSelectedCandidateId('')
      setSelectedProductTypeId('')
      setNewProductTypeName('')
      await Promise.all([loadItems(), loadProductTypeOptions()])
    } catch (err) {
      onError?.(err?.message || 'Artikel en Producttype koppelen is mislukt')
    } finally {
      setIsLinkingProductType(false)
    }
  }
  async function unlinkSelectedCandidate() {
    if (!selectedItem || !selectedCandidate || !selectedCandidateCanBeUnlinked) return
    try {
      const response = await fetchJsonWithAuth('/api/external-databases/catalog/unlink', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ context_keys: [selectedItem.contextKey || selectedItem.id], candidate_ids: [selectedCandidate.raw?.id || selectedCandidate.id] }) })
      const data = await response.json().catch(() => ({})); if (!response.ok) throw new Error(data?.detail || 'Kandidaat ontkoppelen is mislukt')
      onMessage?.('Kandidaat is ontkoppeld.'); setSelectedCandidateId(''); await loadItems()
    } catch (err) { onError?.(err?.message || 'Kandidaat ontkoppelen is mislukt') }
  }
  async function consultOpenFoodFactsForItem(item, queryText = defaultOffQuery(item), mode = 'automatisch') {
    if (!item || item.hasKnownGtin || hasKnownGtin(item.gtin)) return
    const query = String(queryText || '').trim()
    if (!query) {
      setOffError('Vul een zoektekst in om in OFF te zoeken.')
      return
    }

    setShowSearchComplete(false)
    setIsOffLoading(true)
    const searchOverlayTimer = window.setTimeout(() => {
      setShowSearchComplete(true)
    }, 1000)
    setOffPreview(null)
    setOffSearchResults([])
    setSelectedCandidateId('')
    setOffError('')
    setOffSearchMode(mode)

    try {
      const response = await fetchJsonWithAuth('/api/external-products/off/search', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          receipt_item_id: item.receiptItemId || item.id,
          ...(mode === 'handmatig' ? { query } : {}),
          mode: mode === 'handmatig' ? 'manual' : 'automatic',
          limit: 10,
        }),
      })

      const data = await response.json().catch(() => ({}))
      if (!response.ok) {
        throw new Error(data?.detail || 'Open Food Facts kon niet worden geraadpleegd')
      }

      const enrichedResults = await enrichOffResultsWithCatalog(
        Array.isArray(data?.results) ? data.results : [],
      )

      setOffSearchResults(enrichedResults)
      setOffPreview({ ...data, search_mode: mode })

      const linkedResult = enrichedResults.find(
        (result) => result?.existing_catalog_product,
      )

      if (linkedResult) {
        const catalogProduct = linkedResult.existing_catalog_product
        const linkedGtin = gtinText(
          catalogProduct?.primary_gtin
          || linkedResult?.gtin
          || linkedResult?.ean
          || linkedResult?.code,
        )

        const linkedFields = {
          catalogLinked: true,
          status: 'Gekoppeld',
          linkedCandidateName: text(catalogProduct?.name),
          globalProductId: text(catalogProduct?.id, ''),
          gtin: linkedGtin,
          hasKnownGtin: linkedGtin !== '-',
          linkedProductTypeId: text(
            catalogProduct?.product_type_id,
            '',
          ),
          linkedProductType: text(
            catalogProduct?.product_type,
            '',
          ),
          productType: text(
            catalogProduct?.product_type,
            'Nog niet geclassificeerd',
          ),
          bestCandidateName: text(catalogProduct?.name),
          bestCandidateCode: linkedGtin,
        }

        setItems((current) =>
          current.map((currentItem) =>
            currentItem.id === item.id
              ? { ...currentItem, ...linkedFields }
              : currentItem
          )
        )

        setSelectedItem((current) =>
          current?.id === item.id
            ? { ...current, ...linkedFields }
            : current
        )

        setSelectedCandidateId(
          `linked:${catalogProduct?.id || linkedGtin}`,
        )
      }
    } catch (err) {
      setOffSearchResults([])
      setOffError(err?.message || 'Open Food Facts kon niet worden geraadpleegd')
    } finally {
      window.clearTimeout(searchOverlayTimer)
      setShowSearchComplete(false)
      setIsOffLoading(false)
    }
  }

  function runManualOffSearch() { if (selectedItem) consultOpenFoodFactsForItem(selectedItem, offSearchText, 'handmatig') }

  return <div className="rz-external-receipt-overview">
    <style>{`
      @keyframes rz-search-progress-pulse {
        0%, 100% {
          color: #b9e8c8;
          text-shadow: 0 0 10px rgba(21, 94, 57, 0.18);
          opacity: 0.72;
        }
        50% {
          color: #155e39;
          text-shadow: 0 0 26px rgba(21, 94, 57, 0.42);
          opacity: 1;
        }
      }

      .rz-search-complete-overlay {
        position: fixed;
        inset: 0;
        z-index: 10000;
        display: flex;
        align-items: center;
        justify-content: center;
        background: rgba(245, 252, 247, 0.72);
        pointer-events: auto;
        cursor: wait;
      }

      .rz-search-progress-indicator {
        position: fixed;
        left: 50%;
        top: 50%;
        width: 220px;
        height: 220px;
        display: flex;
        flex-direction: column;
        align-items: center;
        justify-content: center;
        padding: 18px 28px;
        border: 2px solid rgba(21, 94, 57, 0.32);
        border-radius: 50%;
        background: rgba(245, 252, 247, 0.96);
        box-shadow: 0 12px 34px rgba(21, 94, 57, 0.24);
        transform: translate(-50%, -50%);
      }

      .rz-search-complete-letter {
        font-size: 132px;
        line-height: 0.88;
        font-weight: 700;
        font-family: Arial, sans-serif;
        animation: rz-search-progress-pulse 2.4s ease-in-out infinite;
      }

      .rz-search-complete-label {
        margin-top: 14px;
        color: #155e39;
        font-size: 16px;
        font-weight: 600;
        white-space: nowrap;
      }

      .rz-external-link-header-grid {
        display: grid;
        grid-template-columns: minmax(280px, 1fr) minmax(320px, 420px);
        gap: 32px;
        align-items: start;
        margin-bottom: 22px;
      }

      .rz-external-link-summary dl {
        margin: 0;
      }

      .rz-external-barcode-panel {
        padding: 18px;
        border: 1px solid #4fa86a;
        border-radius: 6px;
        background: #f5fcf7;
      }

      .rz-external-barcode-panel h4 {
        margin: 0 0 8px;
        color: #134e2f;
      }

      .rz-external-barcode-panel .rz-barcode-field {
        margin-top: 14px;
      }

      .rz-external-barcode-panel .rz-input {
        width: 100%;
      }

      .rz-external-barcode-panel .rz-barcode-field__actions {
        display: flex;
        gap: 8px;
        margin-top: 8px;
      }

      @media (max-width: 850px) {
        .rz-external-link-header-grid {
          grid-template-columns: 1fr;
          gap: 18px;
        }
      }

      @media (prefers-reduced-motion: reduce) {
        .rz-search-complete-letter {
          animation: none;
          color: #155e39;
          opacity: 1;
        }
      }
    `}</style>
    {showSearchComplete ? (
      <div
        className="rz-search-complete-overlay"
        role="status"
        aria-live="polite"
        aria-label="Zoekactie wordt uitgevoerd"
        aria-busy="true"
      >
        <div className="rz-search-progress-indicator">
          <span className="rz-search-complete-letter" aria-hidden="true">R</span>
          <span className="rz-search-complete-label">Zoekactie wordt uitgevoerd</span>
        </div>
      </div>
    ) : null}<div className="rz-external-databases-section-header"><h3>Bonartikelen voor externe herkenning</h3></div><div className="rz-external-databases-actions"><Button type="button" variant="secondary" disabled={!selectedItemIds.length} onClick={exportSelectedItems}>Exporteren</Button><span className="rz-external-databases-muted">Geselecteerd: {selectedItemIds.length} · Totaal: {totalItems}</span></div><div className="rz-table-scroll rz-table-scroll--wide"><Table dataTestId="external-receipt-items-table" tableClassName="rz-external-receipt-table" tableStyle={RECEIPT_TABLE_STYLE} resizableColumns><colgroup>{RECEIPT_COL_WIDTHS.map((width, index) => <col key={`receipt-col-${index}`} style={{ width }} />)}</colgroup><thead><tr className="rz-table-header"><th className="rz-check"><input type="checkbox" checked={allVisibleSelected} onChange={toggleVisibleItems} /></th><th><button type="button" className="rz-external-databases-sort" onClick={() => updateSort('receiptLineText')}>Bonartikel <span>{sortMark('receiptLineText')}</span></button></th><th><button type="button" className="rz-external-databases-sort" onClick={() => updateSort('retailerCode')}>Winkelketen <span>{sortMark('retailerCode')}</span></button></th><th className="rz-check"><button type="button" className="rz-external-databases-sort" onClick={() => updateSort('catalogLinked')}>Catalogus <span>{sortMark('catalogLinked')}</span></button></th><th className="rz-num"><button type="button" className="rz-external-databases-sort" onClick={() => updateSort('bestCandidateScore')}>Score <span>{sortMark('bestCandidateScore')}</span></button></th><th><button type="button" className="rz-external-databases-sort" onClick={() => updateSort('bestCandidateName')}>(Kand.) artikel <span>{sortMark('bestCandidateName')}</span></button></th><th><button type="button" className="rz-external-databases-sort" onClick={() => updateSort('productType')}>Producttype <span>{sortMark('productType')}</span></button></th><th>(Kand.) GTIN/EAN</th><th><button type="button" className="rz-external-databases-sort" onClick={() => updateSort('quantity')}>Omvang / gewicht <span>{sortMark('quantity')}</span></button></th><th className="rz-num">Prijs</th><th className="rz-num"><button type="button" className="rz-external-databases-sort" onClick={() => updateSort('candidateCount')}>Externe <span>{sortMark('candidateCount')}</span></button></th></tr><tr className="rz-external-databases-filter-row"><th></th><th><input className="rz-table-filter" value={filters.receiptLineText} onChange={(event) => updateFilter('receiptLineText', event.target.value)} placeholder="Zoek" /></th><th><input className="rz-table-filter" value={filters.retailerCode} onChange={(event) => updateFilter('retailerCode', event.target.value)} placeholder="Filter" /></th><th><select className="rz-table-filter" value={filters.catalogLinked} onChange={(event) => updateFilter('catalogLinked', event.target.value)} aria-label="Catalogus filter"><option value="all">Alle</option><option value="linked">Gekoppeld</option><option value="unlinked">Niet gekoppeld</option></select></th><th><input className="rz-table-filter" value={filters.bestCandidateScore} onChange={(event) => updateFilter('bestCandidateScore', event.target.value)} placeholder="Filter" /></th><th><input className="rz-table-filter" value={filters.bestCandidateName} onChange={(event) => updateFilter('bestCandidateName', event.target.value)} placeholder="Filter" /></th><th><input className="rz-table-filter" value={filters.productType} onChange={(event) => updateFilter('productType', event.target.value)} placeholder="Filter" /></th><th><input className="rz-table-filter" value={filters.bestCandidateCode} onChange={(event) => updateFilter('bestCandidateCode', event.target.value)} placeholder="Filter" /></th><th><input className="rz-table-filter" value={filters.quantity} onChange={(event) => updateFilter('quantity', event.target.value)} placeholder="Filter" /></th><th><input className="rz-table-filter" value={filters.price} onChange={(event) => updateFilter('price', event.target.value)} placeholder="Filter" /></th><th><input className="rz-table-filter" value={filters.candidateCount} onChange={(event) => updateFilter('candidateCount', event.target.value)} placeholder="Filter" /></th></tr></thead><tbody>{visibleItems.length ? visibleItems.map((item) => <tr key={item.id} className={selectedItem?.id === item.id ? 'rz-row-active' : ''} onDoubleClick={() => selectReceiptItem(item)}><td className="rz-check"><input type="checkbox" checked={selectedItemIds.includes(item.id)} onChange={() => toggleSelectedItem(item.id)} /></td><td>{item.receiptLineText}</td><td>{item.retailerCode}</td><td className="rz-check"><input type="checkbox" checked={item.catalogLinked} readOnly /></td><td className="rz-num">{scoreText(item.bestCandidateScore)}</td><td>{item.bestCandidateName || '-'}</td><td>{item.productType || '-'}</td><td>{item.bestCandidateCode || '-'}</td><td>{item.quantity}</td><td className="rz-num">{numberText(item.price)}</td><td className="rz-num">{item.candidateCount}</td></tr>) : <tr><td colSpan="11">Geen bonartikelen beschikbaar voor externe herkenning.</td></tr>}{Array.from({ length: emptyRows }).map((_, index) => <tr key={`empty-${index}`}><td colSpan="11"></td></tr>)}</tbody></Table></div><div className="rz-external-databases-pagination" aria-label="Paginering bonartikelen"><Button type="button" variant="secondary" disabled={currentPage <= 1} onClick={() => goToPage(1)}>Eerste</Button><Button type="button" variant="secondary" disabled={currentPage <= 1} onClick={() => goToPage(currentPage - 1)}>Vorige</Button><span className="rz-external-databases-page-indicator">Pagina {currentPage} van {pageCount}</span><Button type="button" variant="secondary" disabled={currentPage >= pageCount} onClick={() => goToPage(currentPage + 1)}>Volgende</Button><Button type="button" variant="secondary" disabled={currentPage >= pageCount} onClick={() => goToPage(pageCount)}>Laatste</Button></div>{selectedItem ? <div className="rz-external-receipt-detail"><h3>Koppelen kandidaten in artikel-catalogus</h3><p>Universele kandidaten voor: {selectedItem.receiptLineText}</p><div className="rz-external-link-header-grid"><div className="rz-external-link-summary"><dl><dt>Winkelketen</dt><dd>{selectedItem.retailerCode}</dd><dt>Bonartikelnummer</dt><dd>{selectedItem.receiptArticleNumber}</dd><dt>Artikelnummer</dt><dd>{selectedItem.articleNumber}</dd><dt>GTIN / EAN</dt><dd>{selectedItem.gtin}</dd><dt>Status</dt><dd>{selectedItem.status}</dd></dl></div><section className="rz-external-barcode-panel" aria-labelledby="external-barcode-panel-title" data-testid="external-receipt-barcode-entry"><h4 id="external-barcode-panel-title">Barcode scannen of invoeren</h4><p className="rz-external-databases-muted">Scan de barcode met de camera of voer de GTIN handmatig in.</p><BarcodeIdentityField lineId={selectedItem.id} value={barcodeDraft} state={barcodeState} disabled={isSavingBarcode} onChange={(value) => { setBarcodeDraft(value); setBarcodeState(createIdleBarcodeState()); setBarcodeConfirmation(null) }} onValidate={() => validateSelectedBarcode()} onScan={() => barcodeScanner.startScanner()} /></section></div><BarcodeScannerModal open={barcodeScanner.isOpen} title="Barcode voor bonartikel scannen" videoRef={barcodeScanner.videoRef} cameraState={barcodeScanner.cameraState} cameraMeta={barcodeScanner.cameraMeta} availableCameras={barcodeScanner.availableCameras} onSwitchCamera={barcodeScanner.switchCamera} onClose={() => barcodeScanner.stopScanner(false, 'user-close')} />{barcodeConfirmation ? <div className="rz-modal-backdrop" role="presentation" data-testid="external-barcode-confirmation-backdrop"><div className="rz-modal-card" role="dialog" aria-modal="true" aria-labelledby="external-barcode-confirmation-title" onClick={(event) => event.stopPropagation()}><h3 id="external-barcode-confirmation-title" className="rz-modal-title">Barcode controleren</h3><p className="rz-modal-text">Dit is een geldige barcode.</p><div className="rz-modal-actions"><Button type="button" variant="secondary" disabled={isSavingBarcode} onClick={() => setBarcodeConfirmation(null)}>Annuleren</Button><Button type="button" disabled={isSavingBarcode} onClick={saveSelectedBarcode}>{isSavingBarcode ? 'Opslaan…' : 'Opslaan'}</Button></div></div></div> : null}{!selectedItemHasKnownGtin ? <div className="rz-external-databases-actions" data-testid="external-off-manual-search"><label className="rz-input-field"><div className="rz-label">OFF zoektekst</div><input className="rz-input" aria-label="OFF zoektekst" value={offSearchText} onChange={(event) => setOffSearchText(event.target.value)} /></label><Button type="button" variant="secondary" disabled={isOffLoading || !offSearchText.trim()} onClick={runManualOffSearch}>Zelf zoeken</Button><span className="rz-external-databases-muted">Pas de zoektekst aan als OFF geen goede kandidaat vindt.</span></div> : null}<Table dataTestId="external-receipt-item-candidates-table" tableClassName="rz-external-candidate-detail-table" tableStyle={CANDIDATE_TABLE_STYLE} resizableColumns><colgroup>{CANDIDATE_COL_WIDTHS.map((width, index) => <col key={`candidate-col-${index}`} style={{ width }} />)}</colgroup><thead><tr className="rz-table-header"><th>Keuze</th><th>Kandidaat</th><th>Merk</th><th>Bron</th><th>GTIN / EAN</th><th className="rz-num">Score</th><th>Status</th></tr></thead><tbody>{selectedCandidates.length ? selectedCandidates.map((candidate) => <tr key={candidate.id} className={selectedCandidateId === candidate.id ? 'rz-row-selected' : ''}><td className="rz-check"><input type="radio" name="external-candidate" checked={selectedCandidateId === candidate.id} disabled={!candidate.isLinkableToCatalog && !candidate.isLinkedToCatalog} onChange={() => setSelectedCandidateId(candidate.id)} /></td><td>{candidate.candidateName}</td><td>{candidate.brand}</td><td>{candidate.source}</td><td>{candidate.externalCode}</td><td className="rz-num">{scoreText(candidate.score)}</td><td>{candidate.status}</td></tr>) : <tr><td colSpan="7">Geen universele kandidaten met score 0,500 of hoger voor dit bonartikel.</td></tr>}</tbody></Table><div data-testid="external-producttype-link-panel"><h4>Producttype</h4><p className="rz-external-databases-muted">Producttype wordt uitsluitend bepaald door de officiële Nederlandse GS1 GPC Brickcode van de externe productbron.</p><label className="rz-input-field"><div className="rz-label">GS1 GPC Producttype</div><select className="rz-input" aria-label="Producttype" value={selectedProductTypeId} disabled><option value="">{isClassifyingProductType ? 'Producttype wordt bepaald...' : 'GPC-classificatie ontbreekt'}</option>{productTypeOptions.map((option) => <option key={option.inventory_group_key} value={option.inventory_group_key}>{option.display_name} — GPC {option.gpc_brick_code}</option>)}</select></label><p className="rz-external-databases-muted" data-testid="external-producttype-classification-status">{productTypeClassificationStatus}</p></div><div className="rz-external-databases-actions"><Button type="button" disabled={!selectedCandidateCanBeLinked} onClick={processSelectedCandidate}>{isLinkingProductType ? 'Koppelen...' : (hasValidProductTypeDecision ? 'Koppel artikel en Producttype' : 'Koppel kandidaat aan bonartikel')}</Button><Button type="button" variant="secondary" disabled={!selectedCandidateCanBeUnlinked} onClick={unlinkSelectedCandidate}>Ontkoppel artikel</Button><span className="rz-external-databases-muted">{selectedItemHasKnownGtin ? 'GTIN/EAN is al bekend; OFF-kandidaten worden niet automatisch toegevoegd.' : (isOffLoading ? 'OFF wordt geraadpleegd...' : 'OFF wordt automatisch geraadpleegd bij openen van dit detail; gebruik Zelf zoeken om de zoektekst handmatig aan te passen.')}</span></div>{offError ? <div className="rz-inline-feedback">{offError}</div> : null}{offPreview ? <div className="rz-external-databases-preview-meta" data-testid="external-off-preview-meta"><span>OFF-status: {offStatusLabel(offPreview)}</span><span>Provider: {text(offPreview.provider)}</span><span>Zoektype: {offSearchMode}</span><span>Zoektekst: {offPreview.query || offSearchText || '-'}</span><span>Productmutatie: nee</span></div> : null}</div> : null}</div>
}
