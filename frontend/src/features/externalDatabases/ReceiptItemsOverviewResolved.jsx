import { useEffect, useMemo, useState } from 'react'
import Table from '../../ui/Table'
import Button from '../../ui/Button'
import { fetchJsonWithAuth } from '../../lib/authSession'

const PAGE_SIZE = 10
const RESOLVED_STATUSES = new Set(['external_resolved', 'user_confirmed'])
const LINKED_STATUSES = new Set(['linked_to_catalog'])
const FALLBACK_STATUSES = new Set(['fallback_candidate', 'receipt_fallback_candidate', 'receipt_unresolved_fallback', 'unresolved_fallback', 'unresolved', 'no_external_match'])

function valueText(value, fallback = '-') {
  const normalized = String(value ?? '').trim()
  return normalized || fallback
}

function statusKey(value) {
  return String(value || '').trim().toLowerCase()
}

function scoreText(value) {
  if (value === null || value === undefined || value === '') return '-'
  const number = Number(value)
  if (!Number.isFinite(number)) return '-'
  return number.toLocaleString('nl-NL', { minimumFractionDigits: 3, maximumFractionDigits: 3 })
}

function retailerLabel(value) {
  const normalized = String(value || '').trim()
  const key = normalized.toLowerCase()
  const labels = {
    ah: 'Albert Heijn',
    albert_heijn: 'Albert Heijn',
    'albert heijn': 'Albert Heijn',
    jumbo: 'Jumbo',
    lidl: 'Lidl',
    aldi: 'Aldi',
    plus: 'PLUS',
    picnic: 'Picnic',
  }
  if (!key || key === '-' || key === 'import' || key === 'onbekend') return 'Onbekend'
  return labels[key] || normalized
}

function externalCode(row) {
  return valueText(
    row?.external_source_product_code ||
    row?.candidate_source_product_code ||
    row?.source_product_code ||
    row?.retailer_article_number ||
    row?.external_article_code ||
    row?.gtin ||
    row?.ean,
    ''
  )
}

function sourceName(row) {
  return valueText(row?.external_source_name || row?.candidate_source_name || row?.source_name, '')
}

function isExternalResolved(row) {
  const statuses = [row?.status, row?.candidate_status, row?.external_match_status].map(statusKey)
  return Boolean(externalCode(row)) && statuses.some((status) => RESOLVED_STATUSES.has(status))
}

function isCatalogLinked(row) {
  const statuses = [row?.status, row?.candidate_status].map(statusKey)
  return Boolean(row?.is_linked_to_catalog || row?.global_product_id || row?.matched_global_product_id || statuses.some((status) => LINKED_STATUSES.has(status)))
}

function isFallback(row) {
  const statuses = [row?.status, row?.candidate_status, row?.source_name, row?.candidate_source_name].map(statusKey)
  return statuses.some((status) => FALLBACK_STATUSES.has(status) || status.includes('fallback') || status.includes('unresolved'))
}

function statusLabel(row) {
  if (isCatalogLinked(row)) return 'Artikel gekoppeld'
  if (isExternalResolved(row)) return 'Herkenning bevestigd'
  if (isFallback(row)) return 'Geen herkenning'
  const raw = statusKey(row?.candidate_status || row?.status)
  const labels = {
    probable_candidate: 'Waarschijnlijke herkenning',
    possible_candidate: 'Herkenningskandidaat',
    weak_candidate: 'Lage zekerheid',
    candidate: 'Herkenningskandidaat',
    no_candidate: 'Nog niet verwerkt',
  }
  return labels[raw] || valueText(row?.candidate_status || row?.status || 'Nog niet verwerkt')
}

function rowId(row) {
  return valueText(row.context_key || row.purchase_import_line_id || row.receipt_line_id || row.receipt_line_text, 'receipt-item')
}

function candidateId(row) {
  return valueText(row.candidate_id || row.id || `${row.candidate_name}-${externalCode(row)}-${row.variant}`, 'candidate')
}

function mapCandidate(row) {
  return {
    id: candidateId(row),
    raw: row,
    name: valueText(row.candidate_name || row.receipt_line_text),
    brand: valueText(row.candidate_brand),
    source: valueText(sourceName(row)),
    code: valueText(externalCode(row)),
    variant: valueText(row.variant),
    score: row.score,
    status: statusLabel(row),
    externalResolved: isExternalResolved(row),
    catalogLinked: isCatalogLinked(row),
    fallback: isFallback(row),
    linkable: Boolean(row.is_linkable_to_catalog) && !isFallback(row),
  }
}

function buildRows(payloadItems) {
  const grouped = new Map()

  payloadItems.forEach((row) => {
    const key = rowId(row)
    const placeholder = Boolean(row.is_receipt_item_placeholder)
    const current = grouped.get(key) || {
      id: key,
      contextKey: valueText(row.context_key, ''),
      receiptLineId: valueText(row.receipt_line_id, ''),
      purchaseImportLineId: valueText(row.purchase_import_line_id, ''),
      receiptLineText: valueText(row.receipt_line_text),
      retailerCode: retailerLabel(row.retailer_code),
      retailerCodeRaw: valueText(row.retailer_code, ''),
      externalReference: valueText(externalCode(row)),
      quantity: valueText(row.quantity_label),
      price: row.price ?? '-',
      candidateCount: 0,
      status: statusLabel(row),
      externalResolved: isExternalResolved(row),
      catalogLinked: isCatalogLinked(row),
      candidates: [],
    }

    if (!current.externalReference || current.externalReference === '-') current.externalReference = valueText(externalCode(row))
    if (isExternalResolved(row)) {
      current.externalResolved = true
      current.status = 'Herkenning bevestigd'
    }
    if (isCatalogLinked(row)) {
      current.catalogLinked = true
      current.status = 'Artikel gekoppeld'
    }

    if (!placeholder && row.candidate_name) {
      const candidate = mapCandidate(row)
      current.candidates.push(candidate)
      if (!candidate.fallback) current.candidateCount += 1
      if (candidate.externalResolved && !current.catalogLinked) {
        current.externalResolved = true
        current.status = 'Herkenning bevestigd'
        current.externalReference = candidate.code
      }
    }

    if (placeholder && Array.isArray(row.candidates)) {
      row.candidates.forEach((candidateRow) => {
        const candidate = mapCandidate(candidateRow)
        current.candidates.push(candidate)
        if (!candidate.fallback) current.candidateCount += 1
        if (candidate.externalResolved && !current.catalogLinked) {
          current.externalResolved = true
          current.status = 'Herkenning bevestigd'
          current.externalReference = candidate.code
        }
        if (candidate.catalogLinked) {
          current.catalogLinked = true
          current.status = 'Artikel gekoppeld'
          current.externalReference = candidate.code
        }
      })
    }

    if (current.candidateCount > 0 && !current.externalResolved && !current.catalogLinked) {
      current.status = 'Herkenningskandidaten gevonden'
    }

    grouped.set(key, current)
  })

  return Array.from(grouped.values()).map((row) => {
    const unique = new Map()
    row.candidates.forEach((candidate) => {
      const key = `${candidate.source}|${candidate.code}|${candidate.name}`.toLowerCase()
      const existing = unique.get(key)
      if (!existing || Number(candidate.score || 0) > Number(existing.score || 0)) unique.set(key, candidate)
    })
    const candidates = Array.from(unique.values()).sort((a, b) => {
      if (a.externalResolved !== b.externalResolved) return a.externalResolved ? -1 : 1
      if (a.catalogLinked !== b.catalogLinked) return a.catalogLinked ? -1 : 1
      return Number(b.score || 0) - Number(a.score || 0)
    })
    const best = candidates.find((candidate) => !candidate.fallback) || null
    return {
      ...row,
      candidates,
      bestCandidateName: valueText(best?.name, ''),
      bestCandidateScore: best?.score ?? null,
      candidateCount: candidates.filter((candidate) => !candidate.fallback).length,
    }
  })
}

export default function ReceiptItemsOverviewResolved({ onError, onMessage }) {
  const [items, setItems] = useState([])
  const [selectedItem, setSelectedItem] = useState(null)
  const [selectedCandidateId, setSelectedCandidateId] = useState('')
  const [isLoading, setIsLoading] = useState(false)
  const [isEnsuring, setIsEnsuring] = useState(false)
  const [isConfirming, setIsConfirming] = useState(false)
  const [page, setPage] = useState(1)
  const [filter, setFilter] = useState('')

  async function fetchItems() {
    const response = await fetchJsonWithAuth('/api/external-databases/receipt-items?limit=500', { method: 'GET' })
    const data = await response.json().catch(() => ({}))
    if (!response.ok) throw new Error(data?.detail || 'Bonartikelen konden niet worden geladen')
    return buildRows(Array.isArray(data?.items) ? data.items : [])
  }

  async function loadItems() {
    setIsLoading(true)
    try {
      const rows = await fetchItems()
      setItems(rows)
      if (selectedItem) setSelectedItem(rows.find((row) => row.id === selectedItem.id) || null)
    } catch (err) {
      onError?.(err?.message || 'Bonartikelen konden niet worden geladen')
    } finally {
      setIsLoading(false)
    }
  }

  useEffect(() => {
    loadItems()
  }, [])

  const filteredItems = useMemo(() => {
    const normalized = filter.toLowerCase().trim()
    if (!normalized) return items
    return items.filter((item) => [item.receiptLineText, item.retailerCode, item.externalReference, item.status, item.bestCandidateName].join(' ').toLowerCase().includes(normalized))
  }, [items, filter])

  const pageCount = Math.max(1, Math.ceil(filteredItems.length / PAGE_SIZE))
  const currentPage = Math.min(page, pageCount)
  const visibleItems = filteredItems.slice((currentPage - 1) * PAGE_SIZE, currentPage * PAGE_SIZE)
  const selectedCandidate = selectedItem?.candidates?.find((candidate) => candidate.id === selectedCandidateId) || null
  const canConfirmSelectedCandidate = Boolean(selectedCandidate && !selectedCandidate.externalResolved && !selectedCandidate.catalogLinked && !selectedCandidate.fallback && selectedCandidate.code && selectedCandidate.code !== '-')

  async function ensureVisibleCandidates() {
    if (!visibleItems.length) return
    setIsEnsuring(true)
    try {
      const response = await fetchJsonWithAuth('/api/external-databases/receipt-items/ensure-candidates', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          include_below_threshold: true,
          items: visibleItems.map((item) => ({
            receipt_line_text: item.receiptLineText,
            retailer_code: item.retailerCodeRaw || item.retailerCode,
            purchase_import_line_id: item.purchaseImportLineId,
            receipt_line_id: item.receiptLineId,
            retailer_article_number: item.externalResolved ? item.externalReference : '',
            external_match_status: item.externalResolved ? 'external_resolved' : '',
          })),
        }),
      })
      const data = await response.json().catch(() => ({}))
      if (!response.ok) throw new Error(data?.detail || 'Herkenningskandidaten bijlezen is mislukt')
      await loadItems()
      onMessage?.(`Bijlezen afgerond. Bevestigde herkenningen overgeslagen: ${data?.external_resolved_skipped_count ?? 0}.`)
    } catch (err) {
      onError?.(err?.message || 'Herkenningskandidaten bijlezen is mislukt')
    } finally {
      setIsEnsuring(false)
    }
  }

  async function confirmSelectedCandidate() {
    if (!selectedCandidate) return
    setIsConfirming(true)
    try {
      const response = await fetchJsonWithAuth('/api/external-databases/candidates/confirm-external', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ candidate_id: selectedCandidate.raw?.id || selectedCandidate.id }),
      })
      const data = await response.json().catch(() => ({}))
      if (!response.ok) throw new Error(data?.detail || 'Herkenning bevestigen is mislukt')
      if (!data?.confirmed) throw new Error(data?.reason || 'Herkenning is niet bevestigd')
      onMessage?.(`Herkenning bevestigd met code: ${data.external_product_code || selectedCandidate.code}`)
      setSelectedCandidateId('')
      await loadItems()
    } catch (err) {
      onError?.(err?.message || 'Herkenning bevestigen is mislukt')
    } finally {
      setIsConfirming(false)
    }
  }

  function openItem(item) {
    setSelectedItem(item)
    setSelectedCandidateId('')
  }

  return (
    <div className="rz-external-receipt-overview">
      <div className="rz-external-databases-section-header">
        <h3>Bonartikelen herkennen</h3>
        <div className="rz-external-databases-actions">
          <Button type="button" variant="secondary" disabled={isLoading} onClick={loadItems}>{isLoading ? 'Laden...' : 'Vernieuwen'}</Button>
          <Button type="button" variant="secondary" disabled={isEnsuring || !visibleItems.length} onClick={ensureVisibleCandidates}>{isEnsuring ? 'Bijlezen...' : 'Herkenningskandidaten bijlezen'}</Button>
        </div>
      </div>

      <div className="rz-external-databases-muted">Bevestigen betekent alleen: deze bonregel is herkend als deze winkel-/broncode. Er ontstaat geen Mijn artikel, product of voorraadmutatie.</div>
      <div className="rz-external-databases-actions">
        <input className="rz-table-filter" value={filter} onChange={(event) => { setFilter(event.target.value); setPage(1) }} placeholder="Zoek bonartikel, status of winkel-/broncode" />
      </div>

      <div className="rz-table-scroll rz-table-scroll--wide">
        <Table dataTestId="external-receipt-items-table" tableClassName="rz-external-receipt-table">
          <thead>
            <tr className="rz-table-header">
              <th>Bonartikel</th>
              <th>Winkelketen</th>
              <th>Status herkenning</th>
              <th>Winkel-/broncode</th>
              <th>Beste herkenning</th>
              <th className="rz-num">Score</th>
              <th className="rz-num">Kandidaten</th>
            </tr>
          </thead>
          <tbody>
            {visibleItems.length ? visibleItems.map((item) => (
              <tr key={item.id} className={selectedItem?.id === item.id ? 'rz-row-active' : ''} onDoubleClick={() => openItem(item)}>
                <td>{item.receiptLineText}</td>
                <td>{item.retailerCode}</td>
                <td>{item.status}</td>
                <td>{item.externalReference || '-'}</td>
                <td>{item.bestCandidateName || '-'}</td>
                <td className="rz-num">{scoreText(item.bestCandidateScore)}</td>
                <td className="rz-num">{item.candidateCount}</td>
              </tr>
            )) : <tr><td colSpan="7">Geen bonartikelen beschikbaar voor externe herkenning.</td></tr>}
          </tbody>
        </Table>
      </div>

      <div className="rz-external-databases-pagination">
        <Button type="button" variant="secondary" disabled={currentPage <= 1 || isEnsuring} onClick={() => setPage((value) => Math.max(1, value - 1))}>Vorige</Button>
        <span className="rz-external-databases-page-indicator">Pagina {currentPage} van {pageCount}</span>
        <Button type="button" variant="secondary" disabled={currentPage >= pageCount || isEnsuring} onClick={() => setPage((value) => Math.min(pageCount, value + 1))}>Volgende</Button>
      </div>

      <div className="rz-external-receipt-detail">
        {selectedItem ? (
          <>
            <h3>Herkenningskandidaten voor: {selectedItem.receiptLineText}</h3>
            <div className="rz-table-scroll">
              <Table dataTestId="external-receipt-item-candidates-table" tableClassName="rz-external-candidate-detail-table">
                <thead>
                  <tr className="rz-table-header">
                    <th>Keuze</th>
                    <th>Herkenning</th>
                    <th>Score</th>
                    <th>Merk</th>
                    <th>Bron</th>
                    <th>Winkel-/broncode</th>
                    <th>Status</th>
                  </tr>
                </thead>
                <tbody>
                  {selectedItem.candidates.length ? selectedItem.candidates.map((candidate) => (
                    <tr key={candidate.id}>
                      <td className="rz-check">
                        <input type="radio" name="external-candidate-choice" checked={selectedCandidateId === candidate.id} onChange={() => setSelectedCandidateId(candidate.id)} />
                      </td>
                      <td>{candidate.name}</td>
                      <td className="rz-num">{scoreText(candidate.score)}</td>
                      <td>{candidate.brand}</td>
                      <td>{candidate.source}</td>
                      <td>{candidate.code}</td>
                      <td>{candidate.status}</td>
                    </tr>
                  )) : <tr><td colSpan="7">Geen herkenningskandidaten gevonden voor dit bonartikel.</td></tr>}
                </tbody>
              </Table>
            </div>
            <div className="rz-external-databases-actions rz-external-detail-actions">
              <Button type="button" disabled={!canConfirmSelectedCandidate || isConfirming} onClick={confirmSelectedCandidate}>
                {isConfirming ? 'Bevestigen...' : 'Bevestig herkenning'}
              </Button>
              <span className="rz-external-databases-muted">Na bevestigen blijft alleen de winkel-/broncode aan de bonregel hangen.</span>
            </div>
          </>
        ) : <p className="rz-external-databases-muted">Dubbelklik op een bonartikel om herkenningskandidaten te bekijken.</p>}
      </div>
    </div>
  )
}
