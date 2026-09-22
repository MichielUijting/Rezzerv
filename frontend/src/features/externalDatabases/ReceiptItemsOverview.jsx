import { useEffect, useMemo, useRef, useState } from 'react'
import Table from '../../ui/Table'
import Button from '../../ui/Button'
import SearchCandidateList from '../../ui/SearchCandidateList'
import DelayedTableLoadingOverlay from '../../ui/DelayedTableLoadingOverlay'
import { fetchJsonWithAuth } from '../../lib/authSession'
import RecognitionConfirmationDetail from './RecognitionConfirmationDetail'
import { limitSearchCandidates } from '../../ui/searchCandidatePolicy.js'

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
function hasValidGtinCheckDigit(value) {
  const normalized = text(value, '').replace(/\D+/g, '')
  if (!/^\d{8}$|^\d{12}$|^\d{13}$|^\d{14}$/.test(normalized)) return false
  const digits = normalized.split('').map(Number)
  const body = digits.slice(0, -1).reverse()
  const weightedSum = body.reduce((total, digit, index) => total + digit * (index % 2 === 0 ? 3 : 1), 0)
  const expected = (10 - (weightedSum % 10)) % 10
  return expected === digits[digits.length - 1]
}
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
    const current = grouped.get(key) || { id: key, receiptItemId: key, receiptItemType: text(rawItem.receipt_item_type, ''), receiptItemSourceId: text(rawItem.receipt_item_source_id, ''), contextKey: text(rawItem.context_key, ''), receiptLineId: text(rawItem.receipt_line_id, ''), purchaseImportLineId: text(rawItem.purchase_import_line_id, ''), receiptLineText: text(rawItem.receipt_line_text), retailerCode: retailerLabel(rawItem.retailer_code), retailerCodeRaw: text(rawItem.retailer_code, ''), articleNumber: manualArticleNumberText(rawItem), receiptArticleNumber: receiptArticleNumberText(rawItem), gtin: itemGtin, quantity: text(rawItem.quantity_label), price: rawItem.price ?? '-', catalogLinked: receiptItemHasCatalogLink(rawItem), status: receiptItemHasCatalogLink(rawItem) ? 'Gekoppeld' : (itemGtin !== '-' ? 'GTIN / EAN bekend' : 'Nog niet verwerkt'), linkedCandidateName: text(rawItem.linked_candidate_name, ''), linkedProductTypeId: text(rawItem.linked_product_type_id || rawItem.product_type_id || rawItem.inventory_group_key, ''), linkedProductType: text(rawItem.linked_product_type || rawItem.product_type_label || rawItem.gpc_brick_name, ''), linkedScore: rawItem.linked_score ?? null, globalProductId: text(rawItem.global_product_id, ''), candidates: [], recognitionCandidates: [], hasKnownGtin: itemGtin !== '-' }
    const nested = rawItem.is_receipt_item_placeholder && Array.isArray(rawItem.candidates) ? rawItem.candidates : [rawItem]
    nested.filter(Boolean).forEach((candidate) => {
      current.recognitionCandidates.push(candidate)
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
function defaultGenericProductName(item) {
  const source = text(item?.receiptLineText, '').trim()
  if (!source) return ''
  const prefixes = ['albert heijn', 'ah', 'jumbo', 'plus', 'aldi', 'lidl', 'picnic']
  let generic = source
  const normalized = source.toLowerCase()
  for (const prefix of prefixes.sort((left, right) => right.length - left.length)) {
    if (normalized === prefix) continue
    if (normalized.startsWith(`${prefix} `)) {
      generic = source.slice(prefix.length).trim()
      break
    }
  }
  if (generic && generic === generic.toUpperCase()) {
    generic = generic.toLowerCase().replace(/\b[a-zà-ÿ]/g, (character) => character.toUpperCase())
  }
  return generic || source
}
function candidateGpcBrickCode(candidate) {
  const raw = candidate?.raw || {}
  const value = raw.gpc_brick_code || raw.explicit_gpc_brick_code || raw.gpcCategoryCode || raw.gpcBrickCode || raw.gpc_code || raw.gpcCode || ''
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
    && String(option?.source || '').startsWith('gs1_gpc_')
  )
  return exact ? expectedKey : ''
}

export default function ReceiptItemsOverview({ onError, onMessage }) {
  const [items, setItems] = useState([])
  const [selectedItem, setSelectedItem] = useState(null)
  const [selectedCandidateId, setSelectedCandidateId] = useState('')
  const [selectedItemIds, setSelectedItemIds] = useState([])
  const [isOffLoading, setIsOffLoading] = useState(false)
  const [isItemsLoading, setIsItemsLoading] = useState(false)
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
  const [genericProductName, setGenericProductName] = useState('')
  const [isLinkingProductType, setIsLinkingProductType] = useState(false)
  const [isLinkingGenericProduct, setIsLinkingGenericProduct] = useState(false)
  const [isClassifyingProductType, setIsClassifyingProductType] = useState(false)
  const [productTypeClassificationStatus, setProductTypeClassificationStatus] = useState('')
  const [productTypeSelectionSource, setProductTypeSelectionSource] = useState('')
  const [gpcSearchText, setGpcSearchText] = useState('')
  const [gpcSearchResults, setGpcSearchResults] = useState([])
  const [gpcSuggestedBricks, setGpcSuggestedBricks] = useState([])
  const [gpcSearchError, setGpcSearchError] = useState('')
  const [isGpcSearching, setIsGpcSearching] = useState(false)
  const userGpcChoiceLockedRef = useRef(false)
  const [filters, setFilters] = useState({ receiptLineText: '', retailerCode: '', catalogLinked: 'all', quantity: '', price: '', bestCandidateName: '', productType: '', bestCandidateCode: '', bestCandidateScore: '', candidateCount: '' })
  const [sortKey, setSortKey] = useState('receiptLineText')
  const [sortDesc, setSortDesc] = useState(false)
  const [page, setPage] = useState(1)

  async function fetchItems() {
    const response = await fetchJsonWithAuth('/api/external-databases/receipt-items?limit=500', { method: 'GET' })
    const data = await response.json().catch(() => ({}))
    if (!response.ok) throw new Error(data?.detail || 'Bonartikelen konden niet worden geladen')
    return buildReceiptItems(Array.isArray(data?.items) ? data.items : [])
  }

  async function findCatalogProductByGtin(gtin) {
    const normalizedGtin = gtinText(gtin)

    if (normalizedGtin === '-') return null

    const response = await fetchJsonWithAuth(
      `/api/catalog?primary_gtin=${encodeURIComponent(normalizedGtin)}&limit=20`,
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

        if (gtin === '-' || !hasValidGtinCheckDigit(gtin) || catalogProducts.has(gtin)) return

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
    setIsItemsLoading(true)
    try {
      const nextItems = await fetchItems()
      setItems(nextItems)
      setSelectedItem((current) => current ? nextItems.find((item) => item.id === current.id) || null : null)
      setSelectedItemIds((current) => current.filter((id) => nextItems.some((item) => item.id === id)))
    } catch (err) {
      onError?.(err?.message || 'Bonartikelen konden niet worden geladen')
    } finally {
      setIsItemsLoading(false)
    }
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
    loadItems()
    loadProductTypeOptions().catch((err) => onError?.(err?.message || 'Producttypen konden niet worden geladen'))
  }, [])

  const filteredItems = useMemo(() => {
    const rows = items.filter((item) => item.receiptLineText.toLowerCase().includes(filters.receiptLineText.toLowerCase()) && item.retailerCode.toLowerCase().includes(filters.retailerCode.toLowerCase()) && ((filters.catalogLinked === 'all') || (filters.catalogLinked === 'linked' && item.catalogLinked) || (filters.catalogLinked === 'unlinked' && !item.catalogLinked)) && item.quantity.toLowerCase().includes(filters.quantity.toLowerCase()) && numberText(item.price).toLowerCase().includes(filters.price.toLowerCase()) && String(item.bestCandidateName || '').toLowerCase().includes(filters.bestCandidateName.toLowerCase()) && String(item.productType || '').toLowerCase().includes(filters.productType.toLowerCase()) && String(item.bestCandidateCode || '').toLowerCase().includes(filters.bestCandidateCode.toLowerCase()) && scoreText(item.bestCandidateScore).toLowerCase().includes(filters.bestCandidateScore.toLowerCase()) && String(item.candidateCount || '').toLowerCase().includes(filters.candidateCount.toLowerCase()))
    rows.sort((leftItem, rightItem) => { const left = String(leftItem[sortKey] ?? '').toLowerCase(); const right = String(rightItem[sortKey] ?? '').toLowerCase(); if (left < right) return sortDesc ? 1 : -1; if (left > right) return sortDesc ? -1 : 1; return 0 })
    return rows
  }, [items, filters, sortKey, sortDesc])

  useEffect(() => {
    if (!selectedItem) return
    if (filteredItems.some((item) => item.id === selectedItem.id)) return
    setSelectedItem(null); setSelectedCandidateId(''); setOffPreview(null); setOffSearchResults([]); setOffError(''); setOffSearchText(''); setOffSearchMode('automatisch'); setProductTypeMode('existing'); setSelectedProductTypeId(''); setNewProductTypeName(''); setGenericProductName('')
  }, [filteredItems, selectedItem])

  const pageCount = Math.max(1, Math.ceil(filteredItems.length / PAGE_SIZE))
  const currentPage = Math.min(page, pageCount)
  const visibleItems = filteredItems.slice((currentPage - 1) * PAGE_SIZE, currentPage * PAGE_SIZE)
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
  const selectedCandidates = linkedSelectedCandidate ? [linkedSelectedCandidate] : limitSearchCandidates(offSearchResults).map((result) => {
    const catalogProduct = result?.existing_catalog_product || null
    const catalogLinked = Boolean(catalogProduct)
    const gtin = gtinText(result?.gtin || result?.ean || result?.code)
    const validGtin = gtin !== '-' && hasValidGtinCheckDigit(gtin)

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
      status: catalogLinked
        ? 'Gekoppeld'
        : (result?.identity_compatible === false
          ? 'Merk wijkt af'
          : (!validGtin ? 'Geen geldige GTIN/EAN' : 'OFF-kandidaat')),
      hasUniversalCode: validGtin,
      isLinkedToCatalog: catalogLinked,
      catalogLinked,
      identityCompatible: result?.identity_compatible !== false,
      isLinkableToCatalog: !catalogLinked && result?.identity_compatible !== false && validGtin,
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
  const hasValidProductTypeSource = productTypeSelectionSource === 'external' || productTypeSelectionSource === 'manual'
  const selectedCandidateCanBeLinked = Boolean(selectedItem && selectedCandidate && selectedCandidate.isLinkableToCatalog && hasValidProductTypeDecision && hasValidProductTypeSource && !isLinkingProductType && !isLinkingGenericProduct && !isClassifyingProductType)
  const genericProductCanBeLinked = Boolean(selectedItem && !selectedItem.catalogLinked && String(genericProductName || '').trim() && hasValidProductTypeDecision && hasValidProductTypeSource && !isLinkingProductType && !isLinkingGenericProduct && !isClassifyingProductType)
  const selectedCandidateCanBeUnlinked = false
  const selectedItemHasKnownGtin = Boolean(selectedItem?.hasKnownGtin || hasKnownGtin(selectedItem?.gtin))
  const hasInvalidExactCandidate = selectedCandidates.some((candidate) => !candidate.isLinkedToCatalog && candidate.identityCompatible && !candidate.hasUniversalCode)
  const hasSelectableExactCandidate = selectedCandidates.some((candidate) => candidate.isLinkableToCatalog)
  const exactLinkGuidance = selectedItemHasKnownGtin
    ? 'GTIN/EAN is al bekend; OFF-kandidaten worden niet automatisch toegevoegd.'
    : hasInvalidExactCandidate
      ? 'De OFF-kandidaat heeft geen geldige GTIN/EAN met correct controlecijfer en kan daarom niet als exact artikel worden gekoppeld. Koppel het artikel generiek als de bontekst het artikeltype wel duidelijk maakt.'
      : (!selectedCandidate && hasSelectableExactCandidate
        ? 'Selecteer eerst de gewenste OFF-kandidaat in de kolom Keuze om artikel en Producttype exact te koppelen.'
        : (isOffLoading
          ? 'OFF wordt geraadpleegd...'
          : 'OFF wordt automatisch geraadpleegd bij openen van dit detail; gebruik Zelf zoeken om de zoektekst handmatig aan te passen.'))

  function updateFilter(key, value) { setFilters((current) => ({ ...current, [key]: value })); setPage(1) }
  function updateSort(key) { if (sortKey === key) setSortDesc((value) => !value); else { setSortKey(key); setSortDesc(false) }; setPage(1) }
  function sortMark(key) { return sortKey === key && !sortDesc ? '^' : 'v' }
  function toggleSelectedItem(itemId) { setSelectedItemIds((current) => current.includes(itemId) ? current.filter((id) => id !== itemId) : [...current, itemId]) }
  function toggleVisibleItems() { setSelectedItemIds((current) => allVisibleSelected ? current.filter((id) => !visibleIds.includes(id)) : Array.from(new Set([...current, ...visibleIds]))) }
  function goToPage(targetPage) { setPage(Math.max(1, Math.min(pageCount, targetPage))) }
  function selectReceiptItem(item) {
    userGpcChoiceLockedRef.current = false
    const linkedCandidateId = item.catalogLinked ? `linked:${item.globalProductId || item.gtin}` : ''
    setSelectedItem(item)
    setSelectedCandidateId(linkedCandidateId)
    setOffPreview(null)
    setOffSearchResults([])
    setOffError('')
    setOffSearchText(defaultOffQuery(item))
    setOffSearchMode('automatisch')
    setProductTypeMode('existing')
    setSelectedProductTypeId(item.catalogLinked ? item.linkedProductTypeId : '')
    setProductTypeSelectionSource('')
    setProductTypeClassificationStatus('')
    setGpcSearchText('')
    setGpcSearchResults([])
    setGpcSuggestedBricks([])
    setGpcSearchError('')
    setNewProductTypeName('')
    setGenericProductName(defaultGenericProductName(item))
    if (!item.hasKnownGtin) consultOpenFoodFactsForItem(item, defaultOffQuery(item), 'automatisch')
  }

  useEffect(() => {
    let cancelled = false
    const timer = window.setTimeout(async () => {
      if (userGpcChoiceLockedRef.current) return
      setGpcSearchText('')
      setGpcSearchResults([])
      setGpcSuggestedBricks([])
      setGpcSearchError('')
      if (!selectedItem) return

      const genericName = String(genericProductName || '').trim()
      const contextCandidate = selectedCandidate || selectedCandidates[0] || null
      const raw = contextCandidate?.raw || {}
      const productName = genericName || raw.product_name || contextCandidate?.candidateName || selectedItem.receiptLineText || ''
      const category = raw.category || raw.categories || raw.variant || ''
      const categoryTags = Array.isArray(raw.category_tags)
        ? raw.category_tags
        : Array.isArray(raw.categories_tags)
          ? raw.categories_tags
          : [raw.category_tags || raw.categories_tags].filter(Boolean)
      const productIntent = raw.candidate_product_intent || raw.receipt_product_intent || ''

      if (!productName) {
        setSelectedProductTypeId('')
        setProductTypeSelectionSource('')
        setProductTypeClassificationStatus('Geen productnaam beschikbaar voor automatische GPC-kandidaten.')
        return
      }

      if (selectedCandidate) {
        const linkedProductTypeId = selectedCandidate.isLinkedToCatalog ? selectedItem?.linkedProductTypeId : ''
        const explicitSuggestion = linkedProductTypeId || suggestProductTypeId(selectedCandidate, productTypeOptions)
        setProductTypeMode('existing')
        setNewProductTypeName(selectedCandidate.candidateName === '-' ? '' : selectedCandidate.candidateName)
        if (explicitSuggestion) {
          setSelectedProductTypeId(explicitSuggestion)
          setProductTypeSelectionSource(selectedCandidate.isLinkedToCatalog ? '' : 'external')
          setProductTypeClassificationStatus('Producttype bepaald via expliciete GPC Brickcode van de externe bron.')
          return
        }
        if (selectedCandidate.isLinkedToCatalog) {
          setSelectedProductTypeId('')
          setProductTypeSelectionSource('')
          setProductTypeClassificationStatus('GPC-classificatie ontbreekt.')
          return
        }
      }

      setIsClassifyingProductType(true)
      setSelectedProductTypeId('')
      setProductTypeSelectionSource('')
      setProductTypeClassificationStatus('Waarschijnlijke GPC Bricks worden bepaald...')
      try {
        const response = await fetchJsonWithAuth('/api/external-products/gpc/classify', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            product_name: productName,
            category,
            category_tags: categoryTags,
            gpc_brick_code: selectedCandidate ? candidateGpcBrickCode(selectedCandidate) : '',
            product_intent: productIntent,
            search_text: [selectedItem?.receiptLineText, genericName, raw.product_name, raw.category, raw.categories, ...categoryTags, raw.variant, contextCandidate?.candidateName, contextCandidate?.brand].filter(Boolean).join(' '),
          }),
        })
        const data = await response.json().catch(() => ({}))
        if (!response.ok) throw new Error(data?.detail || 'GPC-classificatie is mislukt')
        if (cancelled || userGpcChoiceLockedRef.current) return

        const suggestedBricks = limitSearchCandidates(Array.isArray(data?.suggestions) ? data.suggestions : data?.suggestion ? [data.suggestion] : [])
        setGpcSuggestedBricks(suggestedBricks)

        if (selectedCandidate && data?.status === 'classified' && data?.classification_source === 'explicit_gpc_code' && /^gpc:\d{8}$/.test(String(data.product_type_id || ''))) {
          const option = {
            inventory_group_key: data.product_type_id,
            display_name: data.gpc_brick_name || data.gpc_brick_name_en || data.product_type_id,
            gpc_brick_code: data.gpc_brick_code,
            source: data.source || 'gs1_gpc_official',
          }
          setProductTypeOptions((current) => current.some((item) => item.inventory_group_key === option.inventory_group_key) ? current : [...current, option])
          setSelectedProductTypeId(option.inventory_group_key)
          setProductTypeSelectionSource('external')
          setGpcSuggestedBricks([])
          setProductTypeClassificationStatus('Producttype bepaald via expliciete GPC Brickcode van de externe bron.')
          return
        }

        setSelectedProductTypeId('')
        setProductTypeSelectionSource('')
        setProductTypeClassificationStatus(suggestedBricks.length
          ? `Inhuis heeft ${suggestedBricks.length} waarschijnlijke GPC-kandidaat${suggestedBricks.length === 1 ? '' : 'en'} gevonden. Kies de beste match of zoek handmatig.`
          : 'Geen bruikbare GPC-kandidaat gevonden. Zoek handmatig op Brickcode of producttype.')
      } catch (err) {
        if (!cancelled && !userGpcChoiceLockedRef.current) {
          setGpcSuggestedBricks([])
          setSelectedProductTypeId('')
          setProductTypeSelectionSource('')
          setProductTypeClassificationStatus(err?.message || 'GPC-classificatie is mislukt; zoek handmatig op Brickcode of producttype.')
        }
      } finally {
        if (!cancelled) setIsClassifyingProductType(false)
      }
    }, 250)

    return () => { cancelled = true; window.clearTimeout(timer) }
  }, [selectedCandidateId, selectedItem?.id, selectedItem?.linkedProductTypeId, selectedItem?.catalogLinked, genericProductName, selectedCandidates[0]?.id])

  async function searchManualGpcBricks() {
    userGpcChoiceLockedRef.current = true
    const query = String(gpcSearchText || '').trim()
    if (!query) {
      setGpcSearchError('Vul een Brickcode of producttype in.')
      setGpcSearchResults([])
      return
    }
    setIsGpcSearching(true)
    setGpcSearchError('')
    try {
      const response = await fetchJsonWithAuth(
        `/api/catalog/gpc/bricks?query=${encodeURIComponent(query)}&limit=5`,
        { method: 'GET' },
      )
      const data = await response.json().catch(() => ({}))
      if (!response.ok) throw new Error(data?.detail || 'GS1 GPC-catalogus kon niet worden doorzocht')
      const results = limitSearchCandidates(Array.isArray(data?.items) ? data.items : [])
      setGpcSearchResults(results)
      if (!results.length) setGpcSearchError('Geen geldige GS1 GPC Brick gevonden.')
    } catch (err) {
      setGpcSearchResults([])
      setGpcSearchError(err?.message || 'GS1 GPC-catalogus kon niet worden doorzocht')
    } finally {
      setIsGpcSearching(false)
    }
  }

  function applyConfirmedGpcBrick(key, brick, feedback) {
    userGpcChoiceLockedRef.current = true
    const brickCode = String(brick?.brick_code || brick?.gpc_brick_code || '').trim()
    if (!/^\d{8}$/.test(brickCode) || key !== `gpc:${brickCode}`) {
      setGpcSearchError('Ongeldige GS1 GPC Brickcode.')
      return
    }
    const option = {
      inventory_group_key: key,
      display_name: brick?.brick_description || brick?.gpc_brick_name || brick?.brick_description_en || brick?.gpc_brick_name_en || key,
      gpc_brick_code: brickCode,
      source: 'gs1_gpc_official',
    }
    setProductTypeOptions((current) => current.some((item) => item.inventory_group_key === key) ? current : [...current, option])
    setSelectedProductTypeId(key)
    setProductTypeSelectionSource('manual')
    setProductTypeClassificationStatus(feedback)
    setGpcSearchError('')
  }

  function selectSuggestedGpcBrick(key, brick) {
    applyConfirmedGpcBrick(key, brick, 'GPC-kandidaat bevestigd. Je kunt nu koppelen of een andere Brick kiezen.')
  }

  function selectManualGpcBrick(key, brick) {
    applyConfirmedGpcBrick(key, brick, 'Handmatig geselecteerd uit de officiële GS1 GPC-catalogus.')
  }

  function exportSelectedItems() {
    const selectedRows = items.filter((item) => selectedItemIds.includes(item.id))
    if (!selectedRows.length) { onMessage?.('Selecteer eerst een of meer bonartikelen om te exporteren.'); return }
    const rows = [['Bonartikel', 'Winkelketen', 'Catalogus', 'Score', '(Kand.) artikel', 'Producttype', '(Kand.) GTIN/EAN', 'Omvang / gewicht', 'Prijs', 'Externe kandidaten'], ...selectedRows.map((item) => [item.receiptLineText, item.retailerCode, item.catalogLinked ? 'Gekoppeld' : 'Niet gekoppeld', scoreText(item.bestCandidateScore), item.bestCandidateName || '-', item.productType || '-', item.bestCandidateCode || '-', item.quantity, numberText(item.price), item.candidateCount])]
    const blob = new Blob([rows.map((row) => row.map((value) => `"${String(value ?? '').replaceAll('"', '""')}"`).join(';')).join('\r\n')], { type: 'text/csv;charset=utf-8' })
    const url = URL.createObjectURL(blob); const link = document.createElement('a'); link.href = url; link.download = 'inhuis-externe-databases-bonartikelen.csv'; link.click(); URL.revokeObjectURL(url); onMessage?.(`Export gemaakt voor ${selectedRows.length} bonartikel(en).`)
  }
  async function processSelectedCandidate() {
    if (!selectedItem || !selectedCandidate || !selectedCandidateCanBeLinked) return
    const productTypeAssignment = {
      product_type_id: selectedProductTypeId,
      gpc_source: productTypeSelectionSource,
      mapping_source: productTypeSelectionSource === 'manual' ? 'manual_gs1_gpc' : 'external_gs1_gpc',
      confidence_score: 1,
    }
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
            image_url: raw.image_url || raw.image_front_small_url || raw.image_front_url || '',
            variant: raw.variant || '',
          },
          product_type_assignment: productTypeAssignment,
        }),
      })
      const data = await response.json().catch(() => ({}))
      if (!response.ok) throw new Error(data?.detail || 'Artikel en Producttype koppelen is mislukt')
      const selectedProductType = productTypeOptions.find((option) => option.inventory_group_key === selectedProductTypeId)
      const productTypeLabel = selectedProductType
        ? `${selectedProductType.display_name} — GPC ${selectedProductType.gpc_brick_code}`
        : selectedProductTypeId
      onMessage?.(`Artikel is gekoppeld aan Producttype ${productTypeLabel}.`)
      setSelectedCandidateId('')
      setSelectedProductTypeId('')
      setProductTypeSelectionSource('')
      setGpcSearchText('')
      setGpcSearchResults([])
      setGpcSearchError('')
      setNewProductTypeName('')
      await Promise.all([loadItems(), loadProductTypeOptions()])
    } catch (err) {
      onError?.(err?.message || 'Artikel en Producttype koppelen is mislukt')
    } finally {
      setIsLinkingProductType(false)
    }
  }
  async function processGenericProduct() {
    if (!selectedItem || !genericProductCanBeLinked) return
    const genericName = String(genericProductName || '').trim()
    const productTypeAssignment = {
      product_type_id: selectedProductTypeId,
      gpc_source: productTypeSelectionSource,
      mapping_source: productTypeSelectionSource === 'manual' ? 'manual_gs1_gpc' : 'external_gs1_gpc',
      confidence_score: 1,
    }
    setIsLinkingGenericProduct(true)
    try {
      const response = await fetchJsonWithAuth('/api/external-products/generic/link', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          receipt_item_id: selectedItem.receiptItemId || selectedItem.id,
          generic_product_name: genericName,
          product_type_assignment: productTypeAssignment,
        }),
      })
      const data = await response.json().catch(() => ({}))
      if (!response.ok) throw new Error(data?.detail || 'Generiek Catalogusartikel koppelen is mislukt')
      const selectedProductType = productTypeOptions.find((option) => option.inventory_group_key === selectedProductTypeId)
      const productTypeLabel = selectedProductType
        ? `${selectedProductType.display_name} — GPC ${selectedProductType.gpc_brick_code}`
        : selectedProductTypeId
      onMessage?.(`Bonartikel is generiek gekoppeld aan ${genericName} met Producttype ${productTypeLabel}.`)
      setSelectedCandidateId('')
      setSelectedProductTypeId('')
      setProductTypeSelectionSource('')
      setGpcSearchText('')
      setGpcSearchResults([])
      setGpcSearchError('')
      await Promise.all([loadItems(), loadProductTypeOptions()])
    } catch (err) {
      onError?.(err?.message || 'Generiek Catalogusartikel koppelen is mislukt')
    } finally {
      setIsLinkingGenericProduct(false)
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

    setIsOffLoading(true)
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
          limit: 5,
        }),
      })

      const data = await response.json().catch(() => ({}))
      if (!response.ok) {
        throw new Error(data?.detail || 'Open Food Facts kon niet worden geraadpleegd')
      }

      const enrichedResults = await enrichOffResultsWithCatalog(
        Array.isArray(data?.results) ? data.results : [],
      )

      setOffSearchResults(limitSearchCandidates(enrichedResults))
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
      setIsOffLoading(false)
    }
  }

  function runManualOffSearch() { if (selectedItem) consultOpenFoodFactsForItem(selectedItem, offSearchText, 'handmatig') }

  return <div className="rz-external-receipt-overview">
    <DelayedTableLoadingOverlay active={isItemsLoading || isOffLoading || isGpcSearching || isClassifyingProductType} />
    <div className="rz-external-databases-section-header"><h3>Bonartikelen voor externe herkenning</h3></div><div className="rz-external-databases-actions"><Button type="button" variant="secondary" disabled={!selectedItemIds.length} onClick={exportSelectedItems}>Exporteren</Button><span className="rz-external-databases-muted">Geselecteerd: {selectedItemIds.length}</span></div><div className="rz-table-scroll rz-table-scroll--wide"><Table wrapperClassName="rz-data-table-wrapper" dataTestId="external-receipt-items-table" tableClassName="rz-data-table rz-data-table--sticky-header rz-data-table--sticky-filters rz-external-receipt-table" tableStyle={RECEIPT_TABLE_STYLE} resizableColumns><colgroup>{RECEIPT_COL_WIDTHS.map((width, index) => <col key={`receipt-col-${index}`} style={{ width }} />)}</colgroup><thead><tr className="rz-table-header"><th className="rz-check"><input type="checkbox" checked={allVisibleSelected} onChange={toggleVisibleItems} /></th><th><button type="button" className="rz-external-databases-sort" onClick={() => updateSort('receiptLineText')}>Bonartikel <span>{sortMark('receiptLineText')}</span></button></th><th><button type="button" className="rz-external-databases-sort" onClick={() => updateSort('retailerCode')}>Winkelketen <span>{sortMark('retailerCode')}</span></button></th><th className="rz-check"><button type="button" className="rz-external-databases-sort" onClick={() => updateSort('catalogLinked')}>Catalogus <span>{sortMark('catalogLinked')}</span></button></th><th className="rz-num"><button type="button" className="rz-external-databases-sort" onClick={() => updateSort('bestCandidateScore')}>Score <span>{sortMark('bestCandidateScore')}</span></button></th><th><button type="button" className="rz-external-databases-sort" onClick={() => updateSort('bestCandidateName')}>(Kand.) artikel <span>{sortMark('bestCandidateName')}</span></button></th><th><button type="button" className="rz-external-databases-sort" onClick={() => updateSort('productType')}>Producttype <span>{sortMark('productType')}</span></button></th><th>(Kand.) GTIN/EAN</th><th><button type="button" className="rz-external-databases-sort" onClick={() => updateSort('quantity')}>Omvang / gewicht <span>{sortMark('quantity')}</span></button></th><th className="rz-num">Prijs</th><th className="rz-num"><button type="button" className="rz-external-databases-sort" onClick={() => updateSort('candidateCount')}>Externe <span>{sortMark('candidateCount')}</span></button></th></tr><tr className="rz-table-filters rz-external-databases-filter-row"><th></th><th><input className="rz-table-filter" value={filters.receiptLineText} onChange={(event) => updateFilter('receiptLineText', event.target.value)} placeholder="Zoek" aria-label="Filter op Bonartikel" /></th><th><input className="rz-table-filter" value={filters.retailerCode} onChange={(event) => updateFilter('retailerCode', event.target.value)} placeholder="Filter" /></th><th><select className="rz-table-filter" value={filters.catalogLinked} onChange={(event) => updateFilter('catalogLinked', event.target.value)} aria-label="Catalogus filter"><option value="all">Alle</option><option value="linked">Gekoppeld</option><option value="unlinked">Niet gekoppeld</option></select></th><th><input className="rz-table-filter" value={filters.bestCandidateScore} onChange={(event) => updateFilter('bestCandidateScore', event.target.value)} placeholder="Filter" /></th><th><input className="rz-table-filter" value={filters.bestCandidateName} onChange={(event) => updateFilter('bestCandidateName', event.target.value)} placeholder="Filter" /></th><th><input className="rz-table-filter" value={filters.productType} onChange={(event) => updateFilter('productType', event.target.value)} placeholder="Filter" /></th><th><input className="rz-table-filter" value={filters.bestCandidateCode} onChange={(event) => updateFilter('bestCandidateCode', event.target.value)} placeholder="Filter" /></th><th><input className="rz-table-filter" value={filters.quantity} onChange={(event) => updateFilter('quantity', event.target.value)} placeholder="Filter" /></th><th><input className="rz-table-filter" value={filters.price} onChange={(event) => updateFilter('price', event.target.value)} placeholder="Filter" /></th><th><input className="rz-table-filter" value={filters.candidateCount} onChange={(event) => updateFilter('candidateCount', event.target.value)} placeholder="Filter" /></th></tr></thead><tbody>{visibleItems.length ? visibleItems.map((item) => <tr key={item.id} className={selectedItem?.id === item.id ? 'rz-row-active' : ''} onDoubleClick={() => selectReceiptItem(item)}><td className="rz-check"><input type="checkbox" checked={selectedItemIds.includes(item.id)} onChange={() => toggleSelectedItem(item.id)} /></td><td>{item.receiptLineText}</td><td>{item.retailerCode}</td><td className="rz-check"><input type="checkbox" checked={item.catalogLinked} readOnly /></td><td className="rz-num">{scoreText(item.bestCandidateScore)}</td><td>{item.bestCandidateName || '-'}</td><td>{item.productType || '-'}</td><td>{item.bestCandidateCode || '-'}</td><td>{item.quantity}</td><td className="rz-num">{numberText(item.price)}</td><td className="rz-num">{item.candidateCount}</td></tr>) : <tr><td colSpan="11">Geen bonartikelen beschikbaar voor externe herkenning.</td></tr>}{Array.from({ length: emptyRows }).map((_, index) => <tr key={`empty-${index}`}><td colSpan="11"></td></tr>)}</tbody></Table></div><div className="rz-external-databases-pagination" aria-label="Paginering bonartikelen"><Button type="button" variant="secondary" disabled={currentPage <= 1} onClick={() => goToPage(1)}>Eerste</Button><Button type="button" variant="secondary" disabled={currentPage <= 1} onClick={() => goToPage(currentPage - 1)}>Vorige</Button><span className="rz-external-databases-page-indicator">Pagina {currentPage} van {pageCount}</span><Button type="button" variant="secondary" disabled={currentPage >= pageCount} onClick={() => goToPage(currentPage + 1)}>Volgende</Button><Button type="button" variant="secondary" disabled={currentPage >= pageCount} onClick={() => goToPage(pageCount)}>Laatste</Button></div>{selectedItem ? <div className="rz-external-receipt-detail"><h3>Koppelen kandidaten in artikel-catalogus</h3><p>Universele kandidaten voor: {selectedItem.receiptLineText}</p><dl><dt>Winkelketen</dt><dd>{selectedItem.retailerCode}</dd><dt>Bonartikelnummer</dt><dd>{selectedItem.receiptArticleNumber}</dd><dt>Artikelnummer</dt><dd>{selectedItem.articleNumber}</dd><dt>GTIN / EAN</dt><dd>{selectedItem.gtin}</dd><dt>Status</dt><dd>{selectedItem.status}</dd></dl><RecognitionConfirmationDetail item={selectedItem} onConfirmed={loadItems} onError={onError} onMessage={onMessage} />{!selectedItemHasKnownGtin ? <div className="rz-external-databases-actions" data-testid="external-off-manual-search"><label className="rz-input-field"><div className="rz-label">OFF zoektekst</div><input className="rz-input" aria-label="OFF zoektekst" value={offSearchText} onChange={(event) => setOffSearchText(event.target.value)} /></label><Button type="button" variant="secondary" disabled={isOffLoading || !offSearchText.trim()} onClick={runManualOffSearch}>Zelf zoeken</Button><span className="rz-external-databases-muted">Pas de zoektekst aan als OFF geen goede kandidaat vindt.</span></div> : null}<Table dataTestId="external-receipt-item-candidates-table" tableClassName="rz-external-candidate-detail-table" tableStyle={CANDIDATE_TABLE_STYLE} resizableColumns><colgroup>{CANDIDATE_COL_WIDTHS.map((width, index) => <col key={`candidate-col-${index}`} style={{ width }} />)}</colgroup><thead><tr className="rz-table-header"><th>Keuze</th><th>Kandidaat</th><th>Merk</th><th>Bron</th><th>GTIN / EAN</th><th className="rz-num">Score</th><th>Status</th></tr></thead><tbody>{selectedCandidates.length ? selectedCandidates.map((candidate) => <tr key={candidate.id} className={selectedCandidateId === candidate.id ? 'rz-row-selected' : ''}><td className="rz-check"><input type="radio" name="external-candidate" checked={selectedCandidateId === candidate.id} disabled={!candidate.isLinkableToCatalog && !candidate.isLinkedToCatalog} onChange={() => setSelectedCandidateId(candidate.id)} /></td><td>{candidate.candidateName}</td><td>{candidate.brand}</td><td>{candidate.source}</td><td>{candidate.externalCode}</td><td className="rz-num">{scoreText(candidate.score)}</td><td>{candidate.status}</td></tr>) : <tr><td colSpan="7">Geen universele kandidaten met score 0,500 of hoger voor dit bonartikel.</td></tr>}</tbody></Table><div className="rz-external-databases-form" data-testid="external-generic-catalog-link-panel"><h4>Generiek Catalogusartikel</h4><p className="rz-external-databases-muted">Gebruik dit wanneer de kassabon het soort artikel wel duidelijk maakt, maar merk, variant of GTIN niet betrouwbaar vaststaat. De generieke naam en de officiële GS1 GPC Brick worden dan leidend.</p><label className="rz-input-field"><div className="rz-label">Generieke artikelnaam</div><input className="rz-input" aria-label="Generieke artikelnaam" value={genericProductName} onChange={(event) => setGenericProductName(event.target.value)} placeholder="Bijvoorbeeld: Bouillon" /></label></div><div data-testid="external-producttype-link-panel"><h4>Producttype</h4><p className="rz-external-databases-muted">Voor een exact extern product gebruikt Inhuis bij voorkeur de officiële GS1 GPC Brickcode van de bron. Voor een generiek Catalogusartikel is de gekozen Brick leidend. Ontbreekt die of is de classificatie niet eenduidig, selecteer dan handmatig een geldige Brick uit de officiële GPC-catalogus.</p><label className="rz-input-field"><div className="rz-label">GS1 GPC Producttype</div><select className="rz-input" aria-label="Producttype" value={selectedProductTypeId} disabled><option value="">{isClassifyingProductType ? 'Producttype wordt bepaald...' : 'GPC-classificatie ontbreekt'}</option>{productTypeOptions.map((option) => <option key={option.inventory_group_key} value={option.inventory_group_key}>{option.display_name} — GPC {option.gpc_brick_code}</option>)}</select></label><p className="rz-external-databases-muted" data-testid="external-producttype-classification-status">{productTypeClassificationStatus}</p>{gpcSuggestedBricks.length && !isClassifyingProductType && productTypeSelectionSource !== 'external' ? <div className="rz-external-databases-form" data-testid="external-auto-gpc-candidates"><div className="rz-label">Waarschijnlijke GS1 GPC Bricks</div><p className="rz-external-databases-muted">Automatisch bepaald uit de generieke artikelnaam, kassabontekst en beschikbare externe productmetadata. Bevestig één kandidaat voordat je koppelt.</p><SearchCandidateList items={gpcSuggestedBricks} selectedKey={selectedProductTypeId} getKey={(item) => `gpc:${item.brick_code || item.gpc_brick_code}`} getLabel={(item) => `${item.brick_code || item.gpc_brick_code} — ${item.brick_description || item.gpc_brick_name || item.brick_description_en || 'Onbekend producttype'} — ${Number(item.match_strength_percent || Math.round(Number(item.confidence || 0) * 100))}% — ${item.suggestion_reason || 'waarschijnlijke match'}`} onSelect={selectSuggestedGpcBrick} loading={false} emptyMessage="" ariaLabel="Automatische GS1 GPC kandidaten" dataTestId="external-auto-gpc-candidate-list" /></div> : null}{(selectedCandidate || String(genericProductName || '').trim()) && !isClassifyingProductType && productTypeSelectionSource !== 'external' ? <div className="rz-external-databases-form" data-testid="external-manual-gpc-search"><label className="rz-input-field"><div className="rz-label">Handmatig GS1 GPC zoeken</div><input className="rz-input" aria-label="Zoek op Brickcode of producttype" value={gpcSearchText} onChange={(event) => { userGpcChoiceLockedRef.current = true; setGpcSearchText(event.target.value) }} placeholder="Zoek op Brickcode of producttype…" /></label><div className="rz-external-databases-actions"><Button type="button" variant="secondary" disabled={isGpcSearching || !gpcSearchText.trim()} onClick={searchManualGpcBricks}>Zoek GPC</Button><span className="rz-external-databases-muted">Alleen Bricks uit de officiële GS1 GPC-catalogus kunnen worden gekozen.</span></div><SearchCandidateList items={gpcSearchResults} selectedKey={selectedProductTypeId} getKey={(item) => `gpc:${item.brick_code}`} getLabel={(item) => `${item.brick_code} — ${item.brick_description || item.brick_description_en || 'Onbekend producttype'}`} onSelect={selectManualGpcBrick} loading={isGpcSearching} emptyMessage={gpcSearchError} ariaLabel="GS1 GPC zoekresultaten" dataTestId="external-gpc-search-results" /></div> : null}</div><div className="rz-external-databases-actions"><Button type="button" disabled={!selectedCandidateCanBeLinked} onClick={processSelectedCandidate}>{isLinkingProductType ? 'Koppelen...' : 'Koppel artikel en Producttype'}</Button><Button type="button" variant="secondary" disabled={!genericProductCanBeLinked} onClick={processGenericProduct}>{isLinkingGenericProduct ? 'Generiek koppelen...' : 'Koppel als generiek artikel'}</Button><Button type="button" variant="secondary" disabled={!selectedCandidateCanBeUnlinked} onClick={unlinkSelectedCandidate}>Ontkoppel artikel</Button><span className="rz-external-databases-muted" data-testid="external-exact-link-guidance">{exactLinkGuidance}</span></div>{offError ? <div className="rz-inline-feedback">{offError}</div> : null}{offPreview ? <div className="rz-external-databases-preview-meta" data-testid="external-off-preview-meta"><span>OFF-status: {offStatusLabel(offPreview)}</span><span>Provider: {text(offPreview.provider)}</span><span>Zoektype: {offSearchMode}</span><span>Zoektekst: {offPreview.query || offSearchText || '-'}</span><span>Productmutatie: nee</span></div> : null}</div> : null}</div>
}
