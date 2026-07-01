import { useEffect, useMemo, useState } from 'react'
import Table from '../../ui/Table'
import Button from '../../ui/Button'
import { fetchJsonWithAuth } from '../../lib/authSession'

const PAGE_SIZE = 10
const MIN_VISIBLE_CANDIDATE_SCORE = 0.5
const RECEIPT_TABLE_STYLE = { width: '1086px', minWidth: '1086px' }
const CANDIDATE_TABLE_STYLE = { width: '1086px', minWidth: '1086px' }
const RECEIPT_COL_WIDTHS = ['40px', '140px', '90px', '76px', '126px', '96px', '96px', '80px', '156px', '86px', '100px']
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
function hasCatalogLink(candidate) { return Boolean(candidate?.is_linked_to_catalog === true || text(candidate?.global_product_id, '') || text(candidate?.product_identity_id, '') || text(candidate?.matched_global_product_id, '') || text(candidate?.matched_global_article_id, '')) }
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
function rowKey(item) { return text(item.context_key || item.receipt_line_id || item.purchase_import_line_id || item.receipt_line_text, 'receipt-item') }
function rawGtin(rawItem) { return gtinText(rawItem.gtin || rawItem.ean || rawItem.barcode) }
function buildReceiptItems(rawItems) {
  const grouped = new Map()
  rawItems.forEach((rawItem) => {
    const key = rowKey(rawItem)
    const itemGtin = rawGtin(rawItem)
    const current = grouped.get(key) || { id: key, contextKey: text(rawItem.context_key, ''), receiptLineId: text(rawItem.receipt_line_id, ''), purchaseImportLineId: text(rawItem.purchase_import_line_id, ''), receiptLineText: text(rawItem.receipt_line_text), retailerCode: retailerLabel(rawItem.retailer_code), retailerCodeRaw: text(rawItem.retailer_code, ''), articleNumber: manualArticleNumberText(rawItem), receiptArticleNumber: receiptArticleNumberText(rawItem), gtin: itemGtin, quantity: text(rawItem.quantity_label), price: rawItem.price ?? '-', catalogLinked: false, status: itemGtin !== '-' ? 'GTIN / EAN bekend' : 'Nog niet verwerkt', candidates: [], hasKnownGtin: itemGtin !== '-' }
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
    const displayBest = linked || candidates.find((candidate) => !candidate.isFallbackCandidate && candidateMeetsScoreThreshold(candidate)) || null
    const selectableBest = candidates.find((candidate) => candidate.hasUniversalCode && !candidate.isFallbackCandidate && candidateMeetsScoreThreshold(candidate)) || null
    const hasSelectableCandidate = candidates.some((candidate) => candidate.hasUniversalCode && !candidate.isFallbackCandidate && candidateMeetsScoreThreshold(candidate))
    const hasVisibleCandidate = candidates.some((candidate) => !candidate.isFallbackCandidate && candidateMeetsScoreThreshold(candidate))
    const hasFallback = candidates.some((candidate) => candidate.isFallbackCandidate)
    return { ...item, candidates, status: item.hasKnownGtin ? 'GTIN / EAN bekend' : (item.catalogLinked ? 'Gekoppeld' : (hasSelectableCandidate ? 'Universele kandidaten gevonden' : (hasVisibleCandidate ? 'Kandidaten gevonden' : (hasFallback ? 'Geen externe match' : item.status)))), candidateCount: candidates.filter((candidate) => candidate.hasUniversalCode && !candidate.isFallbackCandidate && candidateMeetsScoreThreshold(candidate)).length, bestCandidateName: item.hasKnownGtin ? '' : text(displayBest?.candidateName, ''), bestCandidateCode: item.hasKnownGtin ? '' : text(selectableBest?.externalCode, ''), bestCandidateScore: item.hasKnownGtin ? null : displayBest?.score ?? null, gtin: item.gtin, bestSelectableCandidateName: item.hasKnownGtin ? '' : text(selectableBest?.candidateName, '') }
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
function defaultOffQuery(item) { return text(item?.bestSelectableCandidateName || item?.bestCandidateName || item?.receiptLineText, '') }

export default function ReceiptItemsOverview({ onError, onMessage }) {
  const [items, setItems] = useState([])
  const [selectedItem, setSelectedItem] = useState(null)
  const [selectedCandidateId, setSelectedCandidateId] = useState('')
  const [selectedItemIds, setSelectedItemIds] = useState([])
  const [isLoading, setIsLoading] = useState(false)
  const [isOffLoading, setIsOffLoading] = useState(false)
  const [offPreview, setOffPreview] = useState(null)
  const [offError, setOffError] = useState('')
  const [offSearchText, setOffSearchText] = useState('')
  const [offSearchMode, setOffSearchMode] = useState('automatisch')
  const [filters, setFilters] = useState({ receiptLineText: '', retailerCode: '', catalogLinked: 'all', gtin: '', quantity: '', price: '', bestCandidateName: '', bestCandidateCode: '', bestCandidateScore: '', candidateCount: '' })
  const [sortKey, setSortKey] = useState('receiptLineText')
  const [sortDesc, setSortDesc] = useState(false)
  const [page, setPage] = useState(1)

  async function fetchItems() {
    const response = await fetchJsonWithAuth('/api/external-databases/receipt-items?limit=500', { method: 'GET' })
    const data = await response.json().catch(() => ({}))
    if (!response.ok) throw new Error(data?.detail || 'Bonartikelen konden niet worden geladen')
    return buildReceiptItems(Array.isArray(data?.items) ? data.items : [])
  }
  async function loadItems() {
    setIsLoading(true)
    try {
      const nextItems = await fetchItems()
      setItems(nextItems)
      setSelectedItem((current) => current ? nextItems.find((item) => item.id === current.id) || null : null)
      setSelectedItemIds((current) => current.filter((id) => nextItems.some((item) => item.id === id)))
    } catch (err) { onError?.(err?.message || 'Bonartikelen konden niet worden geladen') } finally { setIsLoading(false) }
  }
  useEffect(() => { loadItems() }, [])

  const filteredItems = useMemo(() => {
    const rows = items.filter((item) => item.receiptLineText.toLowerCase().includes(filters.receiptLineText.toLowerCase()) && item.retailerCode.toLowerCase().includes(filters.retailerCode.toLowerCase()) && ((filters.catalogLinked === 'all') || (filters.catalogLinked === 'linked' && item.catalogLinked) || (filters.catalogLinked === 'unlinked' && !item.catalogLinked)) && item.gtin.toLowerCase().includes(filters.gtin.toLowerCase()) && item.quantity.toLowerCase().includes(filters.quantity.toLowerCase()) && numberText(item.price).toLowerCase().includes(filters.price.toLowerCase()) && String(item.bestCandidateName || '').toLowerCase().includes(filters.bestCandidateName.toLowerCase()) && String(item.bestCandidateCode || '').toLowerCase().includes(filters.bestCandidateCode.toLowerCase()) && scoreText(item.bestCandidateScore).toLowerCase().includes(filters.bestCandidateScore.toLowerCase()) && String(item.candidateCount || '').toLowerCase().includes(filters.candidateCount.toLowerCase()))
    rows.sort((leftItem, rightItem) => { const left = String(leftItem[sortKey] ?? '').toLowerCase(); const right = String(rightItem[sortKey] ?? '').toLowerCase(); if (left < right) return sortDesc ? 1 : -1; if (left > right) return sortDesc ? -1 : 1; return 0 })
    return rows
  }, [items, filters, sortKey, sortDesc])

  useEffect(() => {
    if (!selectedItem) return
    if (filteredItems.some((item) => item.id === selectedItem.id)) return
    setSelectedItem(null); setSelectedCandidateId(''); setOffPreview(null); setOffError(''); setOffSearchText(''); setOffSearchMode('automatisch')
  }, [filteredItems, selectedItem])

  const pageCount = Math.max(1, Math.ceil(filteredItems.length / PAGE_SIZE))
  const currentPage = Math.min(page, pageCount)
  const visibleItems = filteredItems.slice((currentPage - 1) * PAGE_SIZE, currentPage * PAGE_SIZE)
  const emptyRows = Math.max(0, PAGE_SIZE - visibleItems.length)
  const visibleIds = visibleItems.map((item) => item.id)
  const allVisibleSelected = visibleIds.length > 0 && visibleIds.every((id) => selectedItemIds.includes(id))
  const selectedCandidates = (selectedItem?.candidates || []).filter(isVisibleSelectionCandidate)
  const selectedCandidate = selectedCandidates.find((candidate) => candidate.id === selectedCandidateId) || null
  const selectedCandidateCanBeLinked = Boolean(selectedCandidate && selectedCandidate.isLinkableToCatalog && !selectedCandidate.isFallbackCandidate && !selectedCandidate.isLinkedToCatalog)
  const selectedCandidateCanBeUnlinked = Boolean(selectedCandidate && selectedCandidate.isLinkedToCatalog)
  const selectedItemHasKnownGtin = Boolean(selectedItem?.hasKnownGtin || hasKnownGtin(selectedItem?.gtin))

  function updateFilter(key, value) { setFilters((current) => ({ ...current, [key]: value })); setPage(1) }
  function updateSort(key) { if (sortKey === key) setSortDesc((value) => !value); else { setSortKey(key); setSortDesc(false) }; setPage(1) }
  function sortMark(key) { return sortKey === key && !sortDesc ? '^' : 'v' }
  function toggleSelectedItem(itemId) { setSelectedItemIds((current) => current.includes(itemId) ? current.filter((id) => id !== itemId) : [...current, itemId]) }
  function toggleVisibleItems() { setSelectedItemIds((current) => allVisibleSelected ? current.filter((id) => !visibleIds.includes(id)) : Array.from(new Set([...current, ...visibleIds]))) }
  function goToPage(targetPage) { setPage(Math.max(1, Math.min(pageCount, targetPage))) }
  function selectReceiptItem(item) { setSelectedItem(item); setSelectedCandidateId(''); setOffPreview(null); setOffError(''); setOffSearchText(defaultOffQuery(item)); setOffSearchMode('automatisch'); if (!item.hasKnownGtin) consultOpenFoodFactsForItem(item, defaultOffQuery(item), 'automatisch') }

  function exportSelectedItems() {
    const selectedRows = items.filter((item) => selectedItemIds.includes(item.id))
    if (!selectedRows.length) { onMessage?.('Selecteer eerst een of meer bonartikelen om te exporteren.'); return }
    const rows = [['Bonartikel', 'Winkelketen', 'Catalogus', 'Kandidaat GTIN / EAN', 'GTIN / EAN', 'Omvang / gewicht', 'Prijs', 'Kandidaat', 'Score', 'Externe kandidaten'], ...selectedRows.map((item) => [item.receiptLineText, item.retailerCode, item.catalogLinked ? 'Gekoppeld' : 'Niet gekoppeld', item.bestCandidateCode || '-', item.gtin, item.quantity, numberText(item.price), item.bestCandidateName || '-', scoreText(item.bestCandidateScore), item.candidateCount])]
    const blob = new Blob([rows.map((row) => row.map((value) => `"${String(value ?? '').replaceAll('"', '""')}"`).join(';')).join('\r\n')], { type: 'text/csv;charset=utf-8' })
    const url = URL.createObjectURL(blob); const link = document.createElement('a'); link.href = url; link.download = 'rezzerv-externe-databases-bonartikelen.csv'; link.click(); URL.revokeObjectURL(url); onMessage?.(`Export gemaakt voor ${selectedRows.length} bonartikel(en).`)
  }
  async function processSelectedCandidate() {
    if (!selectedItem || !selectedCandidate || !selectedCandidateCanBeLinked) return
    try {
      const response = await fetchJsonWithAuth('/api/external-databases/catalog/promote-candidate', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ candidate_id: selectedCandidate.raw?.id || selectedCandidate.id }) })
      const data = await response.json().catch(() => ({})); if (!response.ok) throw new Error(data?.detail || 'Kandidaat verwerken is mislukt')
      onMessage?.(data?.promoted ? 'Kandidaat is gekoppeld.' : 'Cataloguskoppeling is afgerond zonder mutatie.'); setSelectedCandidateId(''); await loadItems()
    } catch (err) { onError?.(err?.message || 'Kandidaat verwerken is mislukt') }
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
    if (!query) { setOffError('Vul een zoektekst in om in OFF te zoeken.'); return }
    setIsOffLoading(true); setOffPreview(null); setOffError(''); setOffSearchMode(mode)
    try {
      const response = await fetchJsonWithAuth('/api/external-databases/off/save-candidates', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ receipt_line_text: item.receiptLineText, retailer_code: item.retailerCodeRaw, receipt_line_id: item.receiptLineId, purchase_import_line_id: item.purchaseImportLineId, candidate_name: query, quantity_label: item.quantity, limit: 5, source: mode === 'handmatig' ? 'manual_off_search' : 'automatic_off_search' }) })
      const data = await response.json().catch(() => ({})); if (!response.ok) throw new Error(data?.detail || 'Open Food Facts kon niet worden geraadpleegd')
      setOffPreview({ ...(data.preview || data), query, search_mode: mode }); await loadItems()
    } catch (err) { setOffError(err?.message || 'Open Food Facts kon niet worden geraadpleegd') } finally { setIsOffLoading(false) }
  }
  function runManualOffSearch() { if (selectedItem) consultOpenFoodFactsForItem(selectedItem, offSearchText, 'handmatig') }

  return <div className="rz-external-receipt-overview"><div className="rz-external-databases-section-header"><h3>Bonartikelen voor externe herkenning</h3><Button type="button" variant="secondary" disabled={isLoading} onClick={loadItems}>Vernieuwen</Button></div><div className="rz-external-databases-actions"><Button type="button" variant="secondary" disabled={!selectedItemIds.length} onClick={exportSelectedItems}>Exporteren</Button><span className="rz-external-databases-muted">Geselecteerd: {selectedItemIds.length}</span></div><div className="rz-table-scroll rz-table-scroll--wide"><Table dataTestId="external-receipt-items-table" tableClassName="rz-external-receipt-table" tableStyle={RECEIPT_TABLE_STYLE} resizableColumns><colgroup>{RECEIPT_COL_WIDTHS.map((width, index) => <col key={`receipt-col-${index}`} style={{ width }} />)}</colgroup><thead><tr className="rz-table-header"><th className="rz-check"><input type="checkbox" checked={allVisibleSelected} onChange={toggleVisibleItems} /></th><th><button type="button" className="rz-external-databases-sort" onClick={() => updateSort('receiptLineText')}>Bonartikel <span>{sortMark('receiptLineText')}</span></button></th><th><button type="button" className="rz-external-databases-sort" onClick={() => updateSort('retailerCode')}>Winkelketen <span>{sortMark('retailerCode')}</span></button></th><th className="rz-check"><button type="button" className="rz-external-databases-sort" onClick={() => updateSort('catalogLinked')}>Catalogus <span>{sortMark('catalogLinked')}</span></button></th><th>Kand. GTIN/EAN</th><th>GTIN / EAN</th><th><button type="button" className="rz-external-databases-sort" onClick={() => updateSort('quantity')}>Omvang / gewicht <span>{sortMark('quantity')}</span></button></th><th className="rz-num">Prijs</th><th><button type="button" className="rz-external-databases-sort" onClick={() => updateSort('bestCandidateName')}>Kandidaat <span>{sortMark('bestCandidateName')}</span></button></th><th className="rz-num"><button type="button" className="rz-external-databases-sort" onClick={() => updateSort('bestCandidateScore')}>Score <span>{sortMark('bestCandidateScore')}</span></button></th><th className="rz-num"><button type="button" className="rz-external-databases-sort" onClick={() => updateSort('candidateCount')}>Externe <span>{sortMark('candidateCount')}</span></button></th></tr><tr className="rz-external-databases-filter-row"><th></th><th><input className="rz-table-filter" value={filters.receiptLineText} onChange={(event) => updateFilter('receiptLineText', event.target.value)} placeholder="Zoek" /></th><th><input className="rz-table-filter" value={filters.retailerCode} onChange={(event) => updateFilter('retailerCode', event.target.value)} placeholder="Filter" /></th><th><select className="rz-table-filter" value={filters.catalogLinked} onChange={(event) => updateFilter('catalogLinked', event.target.value)} aria-label="Catalogus filter"><option value="all">Alle</option><option value="linked">Gekoppeld</option><option value="unlinked">Niet gekoppeld</option></select></th><th><input className="rz-table-filter" value={filters.bestCandidateCode} onChange={(event) => updateFilter('bestCandidateCode', event.target.value)} placeholder="Filter" /></th><th><input className="rz-table-filter" value={filters.gtin} onChange={(event) => updateFilter('gtin', event.target.value)} placeholder="Filter" /></th><th><input className="rz-table-filter" value={filters.quantity} onChange={(event) => updateFilter('quantity', event.target.value)} placeholder="Filter" /></th><th><input className="rz-table-filter" value={filters.price} onChange={(event) => updateFilter('price', event.target.value)} placeholder="Filter" /></th><th><input className="rz-table-filter" value={filters.bestCandidateName} onChange={(event) => updateFilter('bestCandidateName', event.target.value)} placeholder="Filter" /></th><th><input className="rz-table-filter" value={filters.bestCandidateScore} onChange={(event) => updateFilter('bestCandidateScore', event.target.value)} placeholder="Filter" /></th><th><input className="rz-table-filter" value={filters.candidateCount} onChange={(event) => updateFilter('candidateCount', event.target.value)} placeholder="Filter" /></th></tr></thead><tbody>{visibleItems.length ? visibleItems.map((item) => <tr key={item.id} className={selectedItem?.id === item.id ? 'rz-row-active' : ''} onDoubleClick={() => selectReceiptItem(item)}><td className="rz-check"><input type="checkbox" checked={selectedItemIds.includes(item.id)} onChange={() => toggleSelectedItem(item.id)} /></td><td>{item.receiptLineText}</td><td>{item.retailerCode}</td><td className="rz-check"><input type="checkbox" checked={item.catalogLinked} readOnly /></td><td>{item.bestCandidateCode || '-'}</td><td>{item.gtin}</td><td>{item.quantity}</td><td className="rz-num">{numberText(item.price)}</td><td>{item.bestCandidateName || '-'}</td><td className="rz-num">{scoreText(item.bestCandidateScore)}</td><td className="rz-num">{item.candidateCount}</td></tr>) : <tr><td colSpan="11">Geen bonartikelen beschikbaar voor externe herkenning.</td></tr>}{Array.from({ length: emptyRows }).map((_, index) => <tr key={`empty-${index}`}><td colSpan="11"></td></tr>)}</tbody></Table></div><div className="rz-external-databases-pagination" aria-label="Paginering bonartikelen"><Button type="button" variant="secondary" disabled={currentPage <= 1} onClick={() => goToPage(1)}>Eerste</Button><Button type="button" variant="secondary" disabled={currentPage <= 1} onClick={() => goToPage(currentPage - 1)}>Vorige</Button><span className="rz-external-databases-page-indicator">Pagina {currentPage} van {pageCount}</span><Button type="button" variant="secondary" disabled={currentPage >= pageCount} onClick={() => goToPage(currentPage + 1)}>Volgende</Button><Button type="button" variant="secondary" disabled={currentPage >= pageCount} onClick={() => goToPage(pageCount)}>Laatste</Button></div>{selectedItem ? <div className="rz-external-receipt-detail"><h3>Koppelen kandidaten in artikel-catalogus</h3><p>Universele kandidaten voor: {selectedItem.receiptLineText}</p><dl><dt>Winkelketen</dt><dd>{selectedItem.retailerCode}</dd><dt>Bonartikelnummer</dt><dd>{selectedItem.receiptArticleNumber}</dd><dt>Artikelnummer</dt><dd>{selectedItem.articleNumber}</dd><dt>GTIN / EAN</dt><dd>{selectedItem.gtin}</dd><dt>Status</dt><dd>{selectedItem.status}</dd></dl>{!selectedItemHasKnownGtin ? <div className="rz-external-databases-actions" data-testid="external-off-manual-search"><label className="rz-input-field"><div className="rz-label">OFF zoektekst</div><input className="rz-input" aria-label="OFF zoektekst" value={offSearchText} onChange={(event) => setOffSearchText(event.target.value)} /></label><Button type="button" variant="secondary" disabled={isOffLoading || !offSearchText.trim()} onClick={runManualOffSearch}>Zelf zoeken</Button><span className="rz-external-databases-muted">Pas de zoektekst aan als OFF geen goede kandidaat vindt.</span></div> : null}<Table dataTestId="external-receipt-item-candidates-table" tableClassName="rz-external-candidate-detail-table" tableStyle={CANDIDATE_TABLE_STYLE} resizableColumns><colgroup>{CANDIDATE_COL_WIDTHS.map((width, index) => <col key={`candidate-col-${index}`} style={{ width }} />)}</colgroup><thead><tr className="rz-table-header"><th>Keuze</th><th>Kandidaat</th><th>Merk</th><th>Bron</th><th>GTIN / EAN</th><th className="rz-num">Score</th><th>Status</th></tr></thead><tbody>{selectedCandidates.length ? selectedCandidates.map((candidate) => <tr key={candidate.id} className={selectedCandidateId === candidate.id ? 'rz-row-selected' : ''}><td className="rz-check"><input type="radio" name="external-candidate" checked={selectedCandidateId === candidate.id} disabled={!candidate.isLinkableToCatalog && !candidate.isLinkedToCatalog} onChange={() => setSelectedCandidateId(candidate.id)} /></td><td>{candidate.candidateName}</td><td>{candidate.brand}</td><td>{candidate.source}</td><td>{candidate.externalCode}</td><td className="rz-num">{scoreText(candidate.score)}</td><td>{candidate.status}</td></tr>) : <tr><td colSpan="7">Geen universele kandidaten met score 0,500 of hoger voor dit bonartikel.</td></tr>}</tbody></Table><div className="rz-external-databases-actions"><Button type="button" disabled={!selectedCandidateCanBeLinked} onClick={processSelectedCandidate}>Koppel artikel</Button><Button type="button" variant="secondary" disabled={!selectedCandidateCanBeUnlinked} onClick={unlinkSelectedCandidate}>Ontkoppel artikel</Button><span className="rz-external-databases-muted">{selectedItemHasKnownGtin ? 'GTIN/EAN is al bekend; OFF-kandidaten worden niet automatisch toegevoegd.' : (isOffLoading ? 'OFF wordt geraadpleegd...' : 'OFF wordt automatisch geraadpleegd bij openen van dit detail; gebruik Zelf zoeken om de zoektekst handmatig aan te passen.')}</span></div>{offError ? <div className="rz-inline-feedback">{offError}</div> : null}{offPreview ? <div className="rz-external-databases-preview-meta" data-testid="external-off-preview-meta"><span>OFF-status: {offStatusLabel(offPreview)}</span><span>Provider: {text(offPreview.provider)}</span><span>Zoektype: {offSearchMode}</span><span>Zoektekst: {offPreview.query || offSearchText || '-'}</span><span>Productmutatie: nee</span></div> : null}</div> : null}</div>
}
