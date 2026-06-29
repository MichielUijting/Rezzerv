import { useEffect, useMemo, useState } from 'react'
import Table from '../../ui/Table'
import Button from '../../ui/Button'
import { fetchJsonWithAuth } from '../../lib/authSession'

const PAGE_SIZE = 10
const FALLBACK_MARKERS = ['fallback', 'unresolved', 'no_external_match', 'receipt_product_intent_fallback']

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

function hasKnownGtin(value) {
  return gtinText(value) !== '-'
}

function retailerLabel(value) {
  const normalized = text(value, '')
  const labels = {
    ah: 'Albert Heijn',
    albert_heijn: 'Albert Heijn',
    jumbo: 'Jumbo',
    lidl: 'Lidl',
    aldi: 'Aldi',
    plus: 'PLUS',
    picnic: 'Picnic',
  }
  return labels[normalized.toLowerCase()] || normalized || 'Onbekend'
}

function isFallbackCandidate(candidate) {
  const haystack = [
    candidate?.candidate_status,
    candidate?.status,
    candidate?.external_source_name,
    candidate?.external_source_product_code,
    candidate?.candidate_source_name,
    candidate?.candidate_source_product_code,
    candidate?.source_name,
    candidate?.source_product_code,
    candidate?.variant,
    candidate?.candidate_id,
    candidate?.id,
  ].map((value) => text(value, '').toLowerCase()).join(' ')
  return FALLBACK_MARKERS.some((marker) => haystack.includes(marker))
}

function candidateStatusLabel(candidate, linked, fallback) {
  if (linked) return 'Gekoppeld'
  if (fallback) return 'Geen externe match'
  const status = text(candidate?.candidate_status || candidate?.status, '').toLowerCase()
  if (status === 'linked_to_catalog') return 'Gekoppeld'
  if (status === 'user_confirmed') return 'Bevestigd'
  if (status === 'probable_candidate') return 'Waarschijnlijke kandidaat'
  if (status === 'weak_candidate') return 'Lage zekerheid'
  if (status === 'off_candidate') return 'OFF-kandidaat'
  if (status === 'off_low_score_candidate') return 'OFF lage zekerheid'
  return text(candidate?.status_label || candidate?.candidate_status || candidate?.status || 'Kandidaat')
}

function candidateKey(candidate) {
  return text(
    candidate?.candidate_id ||
    candidate?.id ||
    `${candidate?.candidate_name}-${candidate?.candidate_source_product_code || candidate?.external_source_product_code}-${candidate?.variant}`,
    'candidate'
  )
}

function hasCatalogLink(candidate) {
  return Boolean(
    candidate?.is_linked_to_catalog === true ||
    text(candidate?.global_product_id, '') ||
    text(candidate?.product_identity_id, '') ||
    text(candidate?.matched_global_product_id, '') ||
    text(candidate?.matched_global_article_id, '')
  )
}

function buildCandidate(candidate) {
  const linked = candidate?.is_linked_to_catalog === true
  const fallback = isFallbackCandidate(candidate)
  return {
    id: candidateKey(candidate),
    candidateName: text(candidate?.candidate_name),
    brand: text(candidate?.candidate_brand),
    source: text(candidate?.external_source_name || candidate?.candidate_source_name || candidate?.source_name),
    externalCode: text(candidate?.external_source_product_code || candidate?.candidate_source_product_code || candidate?.source_product_code || candidate?.retailer_article_number),
    variant: text(candidate?.variant),
    score: candidate?.score,
    status: candidateStatusLabel(candidate, linked, fallback),
    isLinkedToCatalog: linked,
    catalogLinked: hasCatalogLink(candidate),
    isFallbackCandidate: fallback,
    isLinkableToCatalog: Boolean(candidate?.is_linkable_to_catalog) && !linked && !fallback,
    raw: candidate,
  }
}

function dedupeCandidates(candidates) {
  const deduped = new Map()
  candidates.forEach((candidate) => {
    const raw = candidate.raw || {}
    const source = text(candidate.source || raw.external_source_name || raw.candidate_source_name || raw.source_name, '').toLowerCase()
    const code = text(candidate.externalCode || raw.external_source_product_code || raw.candidate_source_product_code || raw.source_product_code || raw.retailer_article_number, '').toLowerCase()
    const rawGtin = text(raw.gtin || raw.ean, '').toLowerCase()
    const key = source && code
      ? `${source}:${code}`
      : rawGtin || `${candidate.candidateName}:${candidate.brand}:${candidate.variant}`.toLowerCase()
    const current = deduped.get(key)
    if (!current || candidate.isLinkedToCatalog || Number(candidate.score || 0) > Number(current.score || 0)) {
      deduped.set(key, candidate)
    }
  })
  return Array.from(deduped.values())
}

function rowKey(item) {
  return text(item.context_key || item.receipt_line_id || item.purchase_import_line_id || item.receipt_line_text, 'receipt-item')
}

function rawArticleNumber(rawItem) {
  return text(
    rawItem.retailer_article_number ||
    rawItem.source_product_code ||
    rawItem.candidate_source_product_code ||
    rawItem.external_article_code,
    '-'
  )
}

function rawGtin(rawItem) {
  return gtinText(rawItem.gtin || rawItem.ean || rawItem.barcode)
}

function buildReceiptItems(rawItems) {
  const grouped = new Map()
  rawItems.forEach((rawItem) => {
    const key = rowKey(rawItem)
    const itemGtin = rawGtin(rawItem)
    const current = grouped.get(key) || {
      id: key,
      contextKey: text(rawItem.context_key, ''),
      receiptLineId: text(rawItem.receipt_line_id, ''),
      purchaseImportLineId: text(rawItem.purchase_import_line_id, ''),
      receiptLineText: text(rawItem.receipt_line_text),
      retailerCode: retailerLabel(rawItem.retailer_code),
      retailerCodeRaw: text(rawItem.retailer_code, ''),
      articleNumber: rawArticleNumber(rawItem),
      gtin: itemGtin,
      quantity: text(rawItem.quantity_label),
      price: rawItem.price ?? '-',
      amount: '-',
      catalogLinked: false,
      status: itemGtin !== '-' ? 'GTIN / EAN bekend' : 'Nog niet verwerkt',
      candidates: [],
      hasKnownGtin: itemGtin !== '-',
    }

    const nested = rawItem.is_receipt_item_placeholder && Array.isArray(rawItem.candidates)
      ? rawItem.candidates
      : [rawItem]

    nested.filter(Boolean).forEach((candidate) => {
      if (current.hasKnownGtin) return
      const built = buildCandidate(candidate)
      if (built.raw?.is_receipt_item_placeholder && built.raw?.candidate_status === 'no_candidate') return
      current.candidates.push(built)
      if (built.catalogLinked) {
        current.catalogLinked = true
        current.status = 'Gekoppeld'
      }
    })
    grouped.set(key, current)
  })

  return Array.from(grouped.values()).map((item) => {
    const candidates = item.hasKnownGtin
      ? []
      : dedupeCandidates(item.candidates).sort((left, right) => Number(right.score || 0) - Number(left.score || 0))
    const linked = candidates.find((candidate) => candidate.isLinkedToCatalog)
    const best = linked || candidates.find((candidate) => !candidate.isFallbackCandidate) || null
    const hasRealCandidate = candidates.some((candidate) => !candidate.isFallbackCandidate)
    const hasFallback = candidates.some((candidate) => candidate.isFallbackCandidate)
    const candidateGtin = gtinText(best?.raw?.gtin || best?.raw?.ean)
    return {
      ...item,
      candidates,
      status: item.hasKnownGtin
        ? 'GTIN / EAN bekend'
        : (item.catalogLinked ? 'Gekoppeld' : (hasRealCandidate ? 'Kandidaten gevonden' : (hasFallback ? 'Geen externe match' : item.status))),
      candidateCount: candidates.filter((candidate) => !candidate.isFallbackCandidate).length,
      bestCandidateName: item.hasKnownGtin ? '' : text(best?.candidateName, ''),
      bestCandidateScore: item.hasKnownGtin ? null : best?.score ?? null,
      articleNumber: best ? text(best.externalCode, item.articleNumber) : item.articleNumber,
      gtin: candidateGtin !== '-' ? candidateGtin : item.gtin,
    }
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

export default function ReceiptItemsOverview({ onError, onMessage }) {
  const [items, setItems] = useState([])
  const [selectedItem, setSelectedItem] = useState(null)
  const [selectedCandidateId, setSelectedCandidateId] = useState('')
  const [selectedItemIds, setSelectedItemIds] = useState([])
  const [isLoading, setIsLoading] = useState(false)
  const [isOffLoading, setIsOffLoading] = useState(false)
  const [offPreview, setOffPreview] = useState(null)
  const [offError, setOffError] = useState('')
  const [filters, setFilters] = useState({ receiptLineText: '', retailerCode: '', catalogLinked: 'all', articleNumber: '', gtin: '', quantity: '', price: '', amount: '', bestCandidateName: '', bestCandidateScore: '', candidateCount: '' })
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
    } catch (err) {
      onError?.(err?.message || 'Bonartikelen konden niet worden geladen')
    } finally {
      setIsLoading(false)
    }
  }

  useEffect(() => { loadItems() }, [])

  const filteredItems = useMemo(() => {
    const rows = items.filter((item) => (
      item.receiptLineText.toLowerCase().includes(filters.receiptLineText.toLowerCase()) &&
      item.retailerCode.toLowerCase().includes(filters.retailerCode.toLowerCase()) &&
      ((filters.catalogLinked === 'all') || (filters.catalogLinked === 'linked' && item.catalogLinked) || (filters.catalogLinked === 'unlinked' && !item.catalogLinked)) &&
      item.articleNumber.toLowerCase().includes(filters.articleNumber.toLowerCase()) &&
      item.gtin.toLowerCase().includes(filters.gtin.toLowerCase()) &&
      item.quantity.toLowerCase().includes(filters.quantity.toLowerCase()) &&
      numberText(item.price).toLowerCase().includes(filters.price.toLowerCase()) &&
      String(item.amount || '').toLowerCase().includes(filters.amount.toLowerCase()) &&
      String(item.bestCandidateName || '').toLowerCase().includes(filters.bestCandidateName.toLowerCase()) &&
      scoreText(item.bestCandidateScore).toLowerCase().includes(filters.bestCandidateScore.toLowerCase()) &&
      String(item.candidateCount || '').toLowerCase().includes(filters.candidateCount.toLowerCase())
    ))
    rows.sort((leftItem, rightItem) => {
      const left = String(leftItem[sortKey] ?? '').toLowerCase()
      const right = String(rightItem[sortKey] ?? '').toLowerCase()
      if (left < right) return sortDesc ? 1 : -1
      if (left > right) return sortDesc ? -1 : 1
      return 0
    })
    return rows
  }, [items, filters, sortKey, sortDesc])

  useEffect(() => {
    if (!selectedItem) return
    if (filteredItems.some((item) => item.id === selectedItem.id)) return
    setSelectedItem(null)
    setSelectedCandidateId('')
    setOffPreview(null)
    setOffError('')
  }, [filteredItems, selectedItem])

  const pageCount = Math.max(1, Math.ceil(filteredItems.length / PAGE_SIZE))
  const currentPage = Math.min(page, pageCount)
  const visibleItems = filteredItems.slice((currentPage - 1) * PAGE_SIZE, currentPage * PAGE_SIZE)
  const emptyRows = Math.max(0, PAGE_SIZE - visibleItems.length)
  const visibleIds = visibleItems.map((item) => item.id)
  const allVisibleSelected = visibleIds.length > 0 && visibleIds.every((id) => selectedItemIds.includes(id))
  const selectedCandidates = selectedItem?.candidates || []
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

  function selectReceiptItem(item) {
    setSelectedItem(item)
    setSelectedCandidateId('')
    setOffPreview(null)
    setOffError('')
    if (!item.hasKnownGtin) consultOpenFoodFactsForItem(item)
  }

  function exportSelectedItems() {
    const selectedRows = items.filter((item) => selectedItemIds.includes(item.id))
    if (!selectedRows.length) { onMessage?.('Selecteer eerst Ã©Ã©n of meer bonartikelen om te exporteren.'); return }
    const rows = [
      ['Bonartikel', 'Winkelketen', 'Catalogus', 'Artikelnummer', 'GTIN / EAN', 'Omvang / gewicht', 'Prijs', 'Aantal', 'Kandidaat', 'Score', 'Externe kandidaten'],
      ...selectedRows.map((item) => [item.receiptLineText, item.retailerCode, item.catalogLinked ? 'Gekoppeld' : 'Niet gekoppeld', item.articleNumber, item.gtin, item.quantity, numberText(item.price), item.amount, item.bestCandidateName || '-', scoreText(item.bestCandidateScore), item.candidateCount]),
    ]
    const blob = new Blob([rows.map((row) => row.map((value) => `"${String(value ?? '').replaceAll('"', '""')}"`).join(';')).join('\r\n')], { type: 'text/csv;charset=utf-8' })
    const url = URL.createObjectURL(blob)
    const link = document.createElement('a')
    link.href = url
    link.download = 'rezzerv-externe-databases-bonartikelen.csv'
    link.click()
    URL.revokeObjectURL(url)
    onMessage?.(`Export gemaakt voor ${selectedRows.length} bonartikel(en).`)
  }

  async function processSelectedCandidate() {
    if (!selectedItem || !selectedCandidate || !selectedCandidateCanBeLinked) return
    try {
      const response = await fetchJsonWithAuth('/api/external-databases/catalog/promote-candidate', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ candidate_id: selectedCandidate.raw?.id || selectedCandidate.id }),
      })
      const data = await response.json().catch(() => ({}))
      if (!response.ok) throw new Error(data?.detail || 'Kandidaat verwerken is mislukt')
      onMessage?.(data?.promoted ? 'Kandidaat is gekoppeld.' : 'Cataloguskoppeling is afgerond zonder mutatie.')
      setSelectedCandidateId('')
      await loadItems()
    } catch (err) {
      onError?.(err?.message || 'Kandidaat verwerken is mislukt')
    }
  }

  async function unlinkSelectedCandidate() {
    if (!selectedItem || !selectedCandidate || !selectedCandidateCanBeUnlinked) return
    try {
      const response = await fetchJsonWithAuth('/api/external-databases/catalog/unlink', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ context_keys: [selectedItem.contextKey || selectedItem.id], candidate_ids: [selectedCandidate.raw?.id || selectedCandidate.id] }),
      })
      const data = await response.json().catch(() => ({}))
      if (!response.ok) throw new Error(data?.detail || 'Kandidaat ontkoppelen is mislukt')
      onMessage?.('Kandidaat is ontkoppeld.')
      setSelectedCandidateId('')
      await loadItems()
    } catch (err) {
      onError?.(err?.message || 'Kandidaat ontkoppelen is mislukt')
    }
  }

  async function consultOpenFoodFactsForItem(item) {
    if (!item || item.hasKnownGtin || hasKnownGtin(item.gtin)) return
    setIsOffLoading(true)
    setOffPreview(null)
    setOffError('')
    try {
      const response = await fetchJsonWithAuth('/api/external-databases/off/save-candidates', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          receipt_line_text: item.receiptLineText,
          retailer_code: item.retailerCodeRaw,
          receipt_line_id: item.receiptLineId,
          purchase_import_line_id: item.purchaseImportLineId,
          candidate_name: item.bestCandidateName || item.receiptLineText,
          quantity_label: item.quantity,
          limit: 5,
        }),
      })
      const data = await response.json().catch(() => ({}))
      if (!response.ok) throw new Error(data?.detail || 'Open Food Facts kon niet worden geraadpleegd')
      setOffPreview(data.preview || data)
      await loadItems()
    } catch (err) {
      setOffError(err?.message || 'Open Food Facts kon niet worden geraadpleegd')
    } finally {
      setIsOffLoading(false)
    }
  }

  return (
    <div className="rz-external-receipt-overview">
      <div className="rz-external-databases-section-header">
        <h3>Bonartikelen voor externe herkenning</h3>
        <Button type="button" variant="secondary" disabled={isLoading} onClick={loadItems}>Vernieuwen</Button>
      </div>
      <div className="rz-external-databases-actions">
        <Button type="button" variant="secondary" disabled={!selectedItemIds.length} onClick={exportSelectedItems}>Exporteren</Button>
        <span className="rz-external-databases-muted">Geselecteerd: {selectedItemIds.length}</span>
      </div>
      {isLoading ? <div>Bonartikelen worden geladen...</div> : null}

      <div className="rz-table-scroll rz-table-scroll--wide">
        <Table dataTestId="external-receipt-items-table" tableClassName="rz-external-receipt-table" resizableColumns>
          <colgroup><col /><col /><col /><col /><col /><col /><col /><col /><col /><col /><col /><col /></colgroup>
          <thead>
            <tr className="rz-table-header">
              <th className="rz-check"><input type="checkbox" checked={allVisibleSelected} onChange={toggleVisibleItems} /></th>
              <th><button type="button" className="rz-external-databases-sort" onClick={() => updateSort('receiptLineText')}>Bonartikel <span>{sortMark('receiptLineText')}</span></button></th>
              <th><button type="button" className="rz-external-databases-sort" onClick={() => updateSort('retailerCode')}>Winkelketen <span>{sortMark('retailerCode')}</span></button></th>
              <th className="rz-check"><button type="button" className="rz-external-databases-sort" onClick={() => updateSort('catalogLinked')}>Catalogus <span>{sortMark('catalogLinked')}</span></button></th>
              <th><button type="button" className="rz-external-databases-sort" onClick={() => updateSort('articleNumber')}>Artikelnummer <span>{sortMark('articleNumber')}</span></button></th>
              <th>GTIN / EAN</th>
              <th><button type="button" className="rz-external-databases-sort" onClick={() => updateSort('quantity')}>Omvang / gewicht <span>{sortMark('quantity')}</span></button></th>
              <th className="rz-num">Prijs</th>
              <th className="rz-num">Aantal</th>
              <th><button type="button" className="rz-external-databases-sort" onClick={() => updateSort('bestCandidateName')}>Kandidaat <span>{sortMark('bestCandidateName')}</span></button></th>
              <th className="rz-num"><button type="button" className="rz-external-databases-sort" onClick={() => updateSort('bestCandidateScore')}>Score <span>{sortMark('bestCandidateScore')}</span></button></th>
              <th className="rz-num"><button type="button" className="rz-external-databases-sort" onClick={() => updateSort('candidateCount')}>Externe kandidaten <span>{sortMark('candidateCount')}</span></button></th>
            </tr>
            <tr className="rz-external-databases-filter-row">
              <th></th>
              <th><input className="rz-table-filter" value={filters.receiptLineText} onChange={(event) => updateFilter('receiptLineText', event.target.value)} placeholder="Zoek" /></th>
              <th><input className="rz-table-filter" value={filters.retailerCode} onChange={(event) => updateFilter('retailerCode', event.target.value)} placeholder="Filter" /></th>
              <th><select className="rz-table-filter" value={filters.catalogLinked} onChange={(event) => updateFilter('catalogLinked', event.target.value)} aria-label="Catalogus filter"><option value="all">Alle</option><option value="linked">Gekoppeld</option><option value="unlinked">Niet gekoppeld</option></select></th>
              <th><input className="rz-table-filter" value={filters.articleNumber} onChange={(event) => updateFilter('articleNumber', event.target.value)} placeholder="Filter" /></th>
              <th><input className="rz-table-filter" value={filters.gtin} onChange={(event) => updateFilter('gtin', event.target.value)} placeholder="Filter" /></th>
              <th><input className="rz-table-filter" value={filters.quantity} onChange={(event) => updateFilter('quantity', event.target.value)} placeholder="Filter" /></th>
              <th><input className="rz-table-filter" value={filters.price} onChange={(event) => updateFilter('price', event.target.value)} placeholder="Filter" /></th>
              <th><input className="rz-table-filter" value={filters.amount} onChange={(event) => updateFilter('amount', event.target.value)} placeholder="Filter" /></th>
              <th><input className="rz-table-filter" value={filters.bestCandidateName} onChange={(event) => updateFilter('bestCandidateName', event.target.value)} placeholder="Filter" /></th>
              <th><input className="rz-table-filter" value={filters.bestCandidateScore} onChange={(event) => updateFilter('bestCandidateScore', event.target.value)} placeholder="Filter" /></th>
              <th><input className="rz-table-filter" value={filters.candidateCount} onChange={(event) => updateFilter('candidateCount', event.target.value)} placeholder="Filter" /></th>
            </tr>
          </thead>
          <tbody>
            {visibleItems.length ? visibleItems.map((item) => (
              <tr key={item.id} className={selectedItem?.id === item.id ? 'rz-row-active' : ''} onDoubleClick={() => selectReceiptItem(item)}>
                <td className="rz-check"><input type="checkbox" checked={selectedItemIds.includes(item.id)} onChange={() => toggleSelectedItem(item.id)} /></td>
                <td>{item.receiptLineText}</td>
                <td>{item.retailerCode}</td>
                <td className="rz-check"><input type="checkbox" checked={item.catalogLinked} readOnly /></td>
                <td>{item.articleNumber}</td>
                <td>{item.gtin}</td>
                <td>{item.quantity}</td>
                <td className="rz-num">{numberText(item.price)}</td>
                <td className="rz-num">{item.amount}</td>
                <td>{item.bestCandidateName || '-'}</td>
                <td className="rz-num">{scoreText(item.bestCandidateScore)}</td>
                <td className="rz-num">{item.candidateCount}</td>
              </tr>
            )) : <tr><td colSpan="12">Geen bonartikelen beschikbaar voor externe herkenning.</td></tr>}
            {Array.from({ length: emptyRows }).map((_, index) => <tr key={`empty-${index}`}><td colSpan="12"></td></tr>)}
          </tbody>
        </Table>
      </div>

      <div className="rz-external-databases-pagination" aria-label="Paginering bonartikelen">
        <Button type="button" variant="secondary" disabled={currentPage <= 1} onClick={() => goToPage(1)}>Eerste</Button>
        <Button type="button" variant="secondary" disabled={currentPage <= 1} onClick={() => goToPage(currentPage - 1)}>Vorige</Button>
        <span className="rz-external-databases-page-indicator">Pagina {currentPage} van {pageCount}</span>
        <Button type="button" variant="secondary" disabled={currentPage >= pageCount} onClick={() => goToPage(currentPage + 1)}>Volgende</Button>
        <Button type="button" variant="secondary" disabled={currentPage >= pageCount} onClick={() => goToPage(pageCount)}>Laatste</Button>
      </div>

      {selectedItem ? (
        <div className="rz-external-receipt-detail">
          <h3>Koppelen kandidaten in artikel-catalogus</h3>
          <p>Kandidaten voor: {selectedItem.receiptLineText}</p>
          <dl>
            <dt>Winkelketen</dt><dd>{selectedItem.retailerCode}</dd>
            <dt>Artikelnummer</dt><dd>{selectedItem.articleNumber}</dd>
            <dt>GTIN / EAN</dt><dd>{selectedItem.gtin}</dd>
            <dt>Status</dt><dd>{selectedItem.status}</dd>
          </dl>
          <Table dataTestId="external-receipt-item-candidates-table" tableClassName="rz-external-candidate-detail-table" resizableColumns>
            <thead>
              <tr className="rz-table-header"><th>Keuze</th><th>Kandidaat</th><th>Merk</th><th>Bron</th><th>Artikelnummer</th><th>Variant</th><th className="rz-num">Score</th><th>Status</th></tr>
            </thead>
            <tbody>
              {selectedCandidates.length ? selectedCandidates.map((candidate) => (
                <tr key={candidate.id} className={selectedCandidateId === candidate.id ? 'rz-row-selected' : ''}>
                  <td className="rz-check"><input type="radio" name="external-candidate" checked={selectedCandidateId === candidate.id} disabled={!candidate.isLinkableToCatalog && !candidate.isLinkedToCatalog} onChange={() => setSelectedCandidateId(candidate.id)} /></td>
                  <td>{candidate.candidateName}</td>
                  <td>{candidate.brand}</td>
                  <td>{candidate.source}</td>
                  <td>{candidate.externalCode}</td>
                  <td>{candidate.variant}</td>
                  <td className="rz-num">{scoreText(candidate.score)}</td>
                  <td>{candidate.status}</td>
                </tr>
              )) : <tr><td colSpan="8">Geen externe kandidaten voor dit bonartikel.</td></tr>}
            </tbody>
          </Table>
          <div className="rz-external-databases-actions">
            <Button type="button" disabled={!selectedCandidateCanBeLinked} onClick={processSelectedCandidate}>Koppel artikel</Button>
            <Button type="button" variant="secondary" disabled={!selectedCandidateCanBeUnlinked} onClick={unlinkSelectedCandidate}>Ontkoppel artikel</Button>
            <span className="rz-external-databases-muted">
              {selectedItemHasKnownGtin
                ? 'GTIN/EAN is al bekend; OFF-kandidaten worden niet automatisch toegevoegd.'
                : (isOffLoading ? 'OFF wordt automatisch geraadpleegd...' : 'OFF wordt automatisch geraadpleegd bij openen van dit detail; koppelen blijft een expliciete keuze.')}
            </span>
          </div>
          {offError ? <div className="rz-inline-feedback">{offError}</div> : null}
          {offPreview ? <div className="rz-external-databases-preview-meta" data-testid="external-off-preview-meta"><span>OFF-status: {offStatusLabel(offPreview)}</span><span>Provider: {text(offPreview.provider)}</span><span>Productmutatie: nee</span></div> : null}
        </div>
      ) : null}
    </div>
  )
}


