import { useEffect, useMemo, useState } from 'react'
import Table from '../../ui/Table'
import Button from '../../ui/Button'
import { fetchJsonWithAuth } from '../../lib/authSession'

const PAGE_SIZE = 10

function text(value, fallback = '-') {
  const normalized = String(value || '').trim()
  return normalized || fallback
}

function numberText(value) {
  const number = Number(value)
  if (!Number.isFinite(number)) return '-'
  return number.toLocaleString('nl-NL', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}

function scoreText(value) {
  const number = Number(value)
  if (!Number.isFinite(number)) return '-'
  return number.toLocaleString('nl-NL', { minimumFractionDigits: 3, maximumFractionDigits: 3 })
}

function rowKey(item) {
  return text(item.context_key || item.receipt_line_id || item.purchase_import_line_id || item.receipt_line_text, 'receipt-item')
}

function candidateKey(candidate) {
  return text(candidate.id || `${candidate.candidate_name}-${candidate.candidate_source_product_code}-${candidate.variant}`, 'candidate')
}

function buildReceiptItems(candidates) {
  const grouped = new Map()

  candidates.forEach((candidate) => {
    const key = rowKey(candidate)
    const candidateItem = {
      id: candidateKey(candidate),
      candidateName: text(candidate.candidate_name),
      brand: text(candidate.candidate_brand),
      articleNumber: text(candidate.retailer_article_number || candidate.source_product_code || candidate.candidate_source_product_code),
      gtin: text(candidate.gtin || candidate.ean),
      quantity: text(candidate.quantity_label),
      source: text(candidate.candidate_source_name || candidate.source_name),
      score: candidate.score,
      status: text(candidate.candidate_status),
      raw: candidate,
    }

    const current = grouped.get(key) || {
      id: key,
      contextKey: text(candidate.context_key, ''),
      receiptLineText: text(candidate.receipt_line_text),
      normalizedName: text(candidate.parsed_name || candidate.receipt_line_text),
      retailerCode: text(candidate.retailer_code),
      articleNumber: text(candidate.retailer_article_number || candidate.source_product_code || candidate.candidate_source_product_code),
      gtin: text(candidate.gtin || candidate.ean),
      quantity: text(candidate.quantity_label),
      price: '-',
      amount: '-',
      candidateCount: 0,
      catalogLinked: false,
      status: 'Nog niet verwerkt',
      candidates: [],
    }

    current.candidateCount += 1
    current.candidates.push(candidateItem)

    if (candidate.global_product_id || candidate.product_identity_id || candidate.candidate_status === 'user_confirmed' || candidate.candidate_status === 'linked_to_catalog') {
      current.catalogLinked = true
      current.status = 'Catalogus kandidaat'
    }

    grouped.set(key, current)
  })

  return Array.from(grouped.values())
}

function sortValue(item, key) {
  if (key === 'candidateCount') return Number(item.candidateCount || 0)
  if (key === 'catalogLinked') return item.catalogLinked ? 1 : 0
  return String(item[key] || '').toLowerCase()
}

export default function ReceiptItemsOverview({ onError }) {
  const [items, setItems] = useState([])
  const [selectedItem, setSelectedItem] = useState(null)
  const [selectedCandidateId, setSelectedCandidateId] = useState('')
  const [isLoading, setIsLoading] = useState(false)
  const [filters, setFilters] = useState({ receiptLineText: '', retailerCode: '', articleNumber: '', quantity: '', status: '' })
  const [sortKey, setSortKey] = useState('receiptLineText')
  const [sortDesc, setSortDesc] = useState(false)
  const [page, setPage] = useState(1)

  async function loadItems() {
    setIsLoading(true)
    try {
      const response = await fetchJsonWithAuth('/api/external-databases/candidates?limit=200', { method: 'GET' })
      const data = await response.json().catch(() => ({}))
      if (!response.ok) throw new Error(data?.detail || 'Bonartikelen konden niet worden geladen')
      const candidates = Array.isArray(data?.items) ? data.items : []
      const nextItems = buildReceiptItems(candidates)
      setItems(nextItems)
      setPage(1)

      if (selectedItem) {
        const refreshedSelection = nextItems.find((item) => item.id === selectedItem.id) || null
        setSelectedItem(refreshedSelection)
      }
    } catch (err) {
      onError?.(err?.message || 'Bonartikelen konden niet worden geladen')
    } finally {
      setIsLoading(false)
    }
  }

  useEffect(() => {
    loadItems()
  }, [])

  function selectReceiptItem(item) {
    setSelectedItem(item)
    setSelectedCandidateId('')
  }

  function updateFilter(key, value) {
    setFilters((current) => ({ ...current, [key]: value }))
    setPage(1)
  }

  function updateSort(key) {
    if (sortKey === key) setSortDesc((value) => !value)
    else {
      setSortKey(key)
      setSortDesc(false)
    }
    setPage(1)
  }

  function sortMark(key) {
    if (sortKey !== key) return 'v'
    return sortDesc ? 'v' : '^'
  }

  const filteredItems = useMemo(() => {
    const rows = items.filter((item) => (
      item.receiptLineText.toLowerCase().includes(filters.receiptLineText.toLowerCase()) &&
      item.retailerCode.toLowerCase().includes(filters.retailerCode.toLowerCase()) &&
      item.articleNumber.toLowerCase().includes(filters.articleNumber.toLowerCase()) &&
      item.quantity.toLowerCase().includes(filters.quantity.toLowerCase()) &&
      item.status.toLowerCase().includes(filters.status.toLowerCase())
    ))

    rows.sort((leftItem, rightItem) => {
      const left = sortValue(leftItem, sortKey)
      const right = sortValue(rightItem, sortKey)
      if (left < right) return sortDesc ? 1 : -1
      if (left > right) return sortDesc ? -1 : 1
      return 0
    })

    return rows
  }, [items, filters, sortKey, sortDesc])

  const selectedCandidates = selectedItem?.candidates || []
  const pageCount = Math.max(1, Math.ceil(filteredItems.length / PAGE_SIZE))
  const currentPage = Math.min(page, pageCount)
  const visibleItems = filteredItems.slice((currentPage - 1) * PAGE_SIZE, currentPage * PAGE_SIZE)
  const emptyRows = Math.max(0, 3 - visibleItems.length)

  return (
    <div className="rz-external-receipt-overview">
      <div className="rz-external-databases-section-header">
        <h3>Bonartikelen voor externe herkenning</h3>
        <Button type="button" variant="secondary" disabled={isLoading} onClick={loadItems}>Vernieuwen</Button>
      </div>

      {isLoading ? <div>Bonartikelen worden geladen...</div> : null}

      <Table dataTestId="external-receipt-items-table" tableClassName="rz-external-receipt-table">
        <colgroup>
          <col className="rz-external-receipt-col-receipt" />
          <col className="rz-external-receipt-col-normalized" />
          <col className="rz-external-receipt-col-retailer" />
          <col className="rz-external-receipt-col-code" />
          <col className="rz-external-receipt-col-gtin" />
          <col className="rz-external-receipt-col-quantity" />
          <col className="rz-external-receipt-col-price" />
          <col className="rz-external-receipt-col-amount" />
          <col className="rz-external-receipt-col-candidates" />
          <col className="rz-external-receipt-col-catalog" />
          <col className="rz-external-receipt-col-status" />
        </colgroup>
        <thead>
          <tr className="rz-table-header">
            <th><button type="button" className="rz-external-databases-sort" onClick={() => updateSort('receiptLineText')}>Bonartikel <span>{sortMark('receiptLineText')}</span></button></th>
            <th><button type="button" className="rz-external-databases-sort" onClick={() => updateSort('normalizedName')}>Genormaliseerde naam <span>{sortMark('normalizedName')}</span></button></th>
            <th><button type="button" className="rz-external-databases-sort" onClick={() => updateSort('retailerCode')}>Winkelketen <span>{sortMark('retailerCode')}</span></button></th>
            <th><button type="button" className="rz-external-databases-sort" onClick={() => updateSort('articleNumber')}>Artikelnummer <span>{sortMark('articleNumber')}</span></button></th>
            <th>GTIN / EAN</th>
            <th><button type="button" className="rz-external-databases-sort" onClick={() => updateSort('quantity')}>Omvang / gewicht <span>{sortMark('quantity')}</span></button></th>
            <th className="rz-num">Prijs</th>
            <th className="rz-num">Aantal</th>
            <th className="rz-num"><button type="button" className="rz-external-databases-sort" onClick={() => updateSort('candidateCount')}>Externe kandidaten <span>{sortMark('candidateCount')}</span></button></th>
            <th className="rz-check"><button type="button" className="rz-external-databases-sort" onClick={() => updateSort('catalogLinked')}>Catalogus <span>{sortMark('catalogLinked')}</span></button></th>
            <th><button type="button" className="rz-external-databases-sort" onClick={() => updateSort('status')}>Status <span>{sortMark('status')}</span></button></th>
          </tr>
          <tr className="rz-external-databases-filter-row">
            <th><input className="rz-table-filter" value={filters.receiptLineText} onChange={(event) => updateFilter('receiptLineText', event.target.value)} placeholder="Zoek" /></th>
            <th></th>
            <th><input className="rz-table-filter" value={filters.retailerCode} onChange={(event) => updateFilter('retailerCode', event.target.value)} placeholder="Filter" /></th>
            <th><input className="rz-table-filter" value={filters.articleNumber} onChange={(event) => updateFilter('articleNumber', event.target.value)} placeholder="Filter" /></th>
            <th></th>
            <th><input className="rz-table-filter" value={filters.quantity} onChange={(event) => updateFilter('quantity', event.target.value)} placeholder="Filter" /></th>
            <th></th>
            <th></th>
            <th></th>
            <th></th>
            <th><input className="rz-table-filter" value={filters.status} onChange={(event) => updateFilter('status', event.target.value)} placeholder="Filter" /></th>
          </tr>
        </thead>
        <tbody>
          {visibleItems.length ? visibleItems.map((item) => (
            <tr key={item.id} className={selectedItem?.id === item.id ? 'rz-row-active' : ''} onDoubleClick={() => selectReceiptItem(item)}>
              <td>{item.receiptLineText}</td>
              <td>{item.normalizedName}</td>
              <td>{item.retailerCode}</td>
              <td>{item.articleNumber}</td>
              <td>{item.gtin}</td>
              <td>{item.quantity}</td>
              <td className="rz-num">{numberText(item.price)}</td>
              <td className="rz-num">{item.amount}</td>
              <td className="rz-num">{item.candidateCount}</td>
              <td className="rz-check"><input type="checkbox" checked={item.catalogLinked} readOnly /></td>
              <td>{item.status}</td>
            </tr>
          )) : <tr><td colSpan="11">Geen bonartikelen beschikbaar voor externe herkenning.</td></tr>}
          {Array.from({ length: emptyRows }).map((_, index) => <tr key={`empty-${index}`}><td colSpan="11"></td></tr>)}
        </tbody>
      </Table>

      <div className="rz-external-databases-pagination">
        <Button type="button" variant="secondary" disabled={currentPage <= 1} onClick={() => setPage((value) => Math.max(1, value - 1))}>Vorige</Button>
        <span className="rz-external-databases-page-indicator">Pagina {currentPage} van {pageCount}</span>
        <Button type="button" variant="secondary" disabled={currentPage >= pageCount} onClick={() => setPage((value) => Math.min(pageCount, value + 1))}>Volgende</Button>
      </div>

      <div className="rz-external-receipt-detail">
        {selectedItem ? (
          <>
            <h3>Bonartikel verwerken</h3>
            <dl>
              <dt>Bonartikel</dt><dd>{selectedItem.receiptLineText}</dd>
              <dt>Winkelketen</dt><dd>{selectedItem.retailerCode}</dd>
              <dt>Artikelnummer</dt><dd>{selectedItem.articleNumber}</dd>
              <dt>GTIN / EAN</dt><dd>{selectedItem.gtin}</dd>
              <dt>Omvang / gewicht</dt><dd>{selectedItem.quantity}</dd>
              <dt>Externe kandidaten</dt><dd>{selectedItem.candidateCount}</dd>
              <dt>Catalogus</dt><dd>{selectedItem.catalogLinked ? 'Kandidaat aanwezig' : 'Nog geen kandidaat'}</dd>
            </dl>

            <h3>Externe kandidaten voor dit bonartikel</h3>
            <Table dataTestId="external-receipt-item-candidates-table" tableClassName="rz-external-candidate-detail-table">
              <colgroup>
                <col className="rz-external-candidate-col-choice" />
                <col className="rz-external-candidate-col-name" />
                <col className="rz-external-candidate-col-brand" />
                <col className="rz-external-candidate-col-code" />
                <col className="rz-external-candidate-col-gtin" />
                <col className="rz-external-candidate-col-quantity" />
                <col className="rz-external-candidate-col-source" />
                <col className="rz-external-candidate-col-score" />
                <col className="rz-external-candidate-col-status" />
              </colgroup>
              <thead>
                <tr className="rz-table-header">
                  <th>Keuze</th>
                  <th>Kandidaat</th>
                  <th>Merk</th>
                  <th>Artikelnummer</th>
                  <th>GTIN / EAN</th>
                  <th>Omvang / gewicht</th>
                  <th>Bron</th>
                  <th className="rz-num">Score</th>
                  <th>Status</th>
                </tr>
              </thead>
              <tbody>
                {selectedCandidates.length ? selectedCandidates.map((candidate) => (
                  <tr key={candidate.id}>
                    <td className="rz-check">
                      <input
                        type="radio"
                        name="external-candidate-choice"
                        checked={selectedCandidateId === candidate.id}
                        onChange={() => setSelectedCandidateId(candidate.id)}
                      />
                    </td>
                    <td>{candidate.candidateName}</td>
                    <td>{candidate.brand}</td>
                    <td>{candidate.articleNumber}</td>
                    <td>{candidate.gtin}</td>
                    <td>{candidate.quantity}</td>
                    <td>{candidate.source}</td>
                    <td className="rz-num">{scoreText(candidate.score)}</td>
                    <td>{candidate.status}</td>
                  </tr>
                )) : <tr><td colSpan="9">Geen externe kandidaten gevonden voor dit bonartikel.</td></tr>}
              </tbody>
            </Table>

            <p className="rz-external-databases-muted">Catalogusverwerking volgt in de volgende patch van M2C2h-2.</p>
          </>
        ) : <p className="rz-external-databases-muted">Dubbelklik op een bonartikel om de detailcontext te openen.</p>}
      </div>
    </div>
  )
}
