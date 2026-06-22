import { useEffect, useMemo, useRef, useState } from 'react'
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

function gtinText(value) {
  const normalized = String(value || '').trim()
  if (/^\d{8}$|^\d{12}$|^\d{13}$|^\d{14}$/.test(normalized)) return normalized
  return '-'
}

function scoreText(value) {
  const number = Number(value)
  if (!Number.isFinite(number)) return '-'
  return number.toLocaleString('nl-NL', { minimumFractionDigits: 3, maximumFractionDigits: 3 })
}

function retailerLabel(value) {
  const normalized = String(value || '').trim()
  const key = normalized.toLowerCase()

  if (!key || key === '-' || key === 'import' || key === 'onbekend') return 'Onbekend'

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

  return labels[key] || normalized
}

function candidateStatusLabel(value) {
  const normalized = String(value || '').trim().toLowerCase()
  const labels = {
    linked_to_catalog: 'Gekoppeld',
    user_confirmed: 'Bevestigd',
    probable_candidate: 'Waarschijnlijke kandidaat',
    weak_candidate: 'Lage zekerheid',
    candidate: 'Kandidaat',
  }
  return labels[normalized] || text(value)
}

function rowKey(item) {
  return text(item.context_key || item.receipt_line_id || item.purchase_import_line_id || item.receipt_line_text, 'receipt-item')
}

function candidateKey(candidate) {
  return text(
    candidate.candidate_id ||
    candidate.id ||
    `${candidate.candidate_name}-${candidate.external_source_product_code || candidate.candidate_source_product_code}-${candidate.variant}`,
    'candidate'
  )
}

function candidateDedupValue(value) {
  return String(value || '').trim().toLowerCase()
}

function candidateDedupKey(candidate) {
  const raw = candidate?.raw || {}
  const source = candidateDedupValue(candidate.source || raw.external_source_name || raw.candidate_source_name || raw.source_name)
  const externalCode = candidateDedupValue(candidate.externalCode || raw.external_source_product_code || raw.candidate_source_product_code || raw.source_product_code || raw.retailer_article_number)
  const gtin = candidateDedupValue(raw.gtin || raw.ean)

  if (source && externalCode) return `source:${source}|code:${externalCode}`
  if (gtin) return `gtin:${gtin}`

  const name = candidateDedupValue(candidate.candidateName || raw.candidate_name)
  const brand = candidateDedupValue(candidate.brand || raw.candidate_brand)
  const variant = candidateDedupValue(candidate.variant || raw.variant)

  return `fallback:${name}|brand:${brand}|variant:${variant}`
}

function preferCandidate(current, next) {
  if (!current) return next

  if (next.isLinkedToCatalog && !current.isLinkedToCatalog) return next
  if (current.isLinkedToCatalog && !next.isLinkedToCatalog) return current

  const currentScore = Number(current.score || 0)
  const nextScore = Number(next.score || 0)

  if (nextScore > currentScore) return next

  return current
}

function dedupeCandidates(candidates) {
  const deduped = new Map()

  candidates.forEach((candidate) => {
    const key = candidateDedupKey(candidate)
    deduped.set(key, preferCandidate(deduped.get(key), candidate))
  })

  return Array.from(deduped.values())
}

function bestCandidateForItem(candidates) {
  const linkedCandidate = candidates.find((candidate) => candidate.isLinkedToCatalog)
  if (linkedCandidate) return linkedCandidate
  return candidates[0] || null
}

function candidateExternalCode(candidate) {
  if (!candidate) return ''
  const raw = candidate.raw || {}
  return text(
    candidate.externalCode ||
    raw.external_source_product_code ||
    raw.candidate_source_product_code ||
    raw.source_product_code,
    ''
  )
}

function candidateExternalGtin(candidate) {
  if (!candidate) return '-'
  const raw = candidate.raw || {}
  return gtinText(
    raw.gtin ||
    raw.ean ||
    candidate.externalCode ||
    raw.external_source_product_code ||
    raw.candidate_source_product_code ||
    raw.source_product_code
  )
}

function isBackendLinkedCandidate(candidate) {
  // Single source of truth: de backend bepaalt of deze kandidaat de actieve koppeling is.
  return candidate?.is_linked_to_catalog === true
}

function candidateStatusFromBackend(candidate, linked) {
  if (linked) return 'Gekoppeld'

  const rawLabel = text(candidate.status_label, '')
  if (rawLabel && rawLabel.toLowerCase() !== 'gekoppeld') return rawLabel

  const rawStatus = String(candidate.candidate_status || candidate.status || '').trim().toLowerCase()
  if (rawStatus === 'linked_to_catalog' || rawStatus === 'user_confirmed') return 'Kandidaat'

  return candidateStatusLabel(candidate.candidate_status || candidate.status)
}

function buildReceiptItems(candidates) {
  const grouped = new Map()

  candidates.forEach((candidate) => {
    const key = rowKey(candidate)
    const isPlaceholder = Boolean(candidate.is_receipt_item_placeholder)
    const linked = isBackendLinkedCandidate(candidate)

    const candidateItem = {
      id: candidateKey(candidate),
      candidateName: text(candidate.candidate_name),
      brand: text(candidate.candidate_brand),
      source: text(candidate.external_source_name || candidate.candidate_source_name || candidate.source_name),
      externalCode: text(candidate.external_source_product_code || candidate.candidate_source_product_code || candidate.source_product_code || candidate.retailer_article_number),
      variant: text(candidate.variant),
      score: candidate.score,
      status: candidateStatusFromBackend(candidate, linked),
      catalogLinked: linked,
      isLinkedToCatalog: linked,
      isLinkableToCatalog: Boolean(candidate.is_linkable_to_catalog) && !linked,
      isExistingLinkForReceiptItem: linked,
      canonicalCatalogProductId: text(candidate.canonical_catalog_product_id, ''),
      raw: candidate,
    }

    const current = grouped.get(key) || {
      id: key,
      contextKey: text(candidate.context_key, ''),
      receiptLineId: text(candidate.receipt_line_id, ''),
      purchaseImportLineId: text(candidate.purchase_import_line_id, ''),
      receiptLineText: text(candidate.receipt_line_text),
      retailerCode: retailerLabel(candidate.retailer_code),
      retailerCodeRaw: text(candidate.retailer_code, ''),
      articleNumber: text(candidate.retailer_article_number || candidate.source_product_code || candidate.candidate_source_product_code),
      gtin: gtinText(candidate.gtin || candidate.ean),
      quantity: text(candidate.quantity_label),
      price: candidate.price ?? '-',
      amount: '-',
      candidateCount: 0,
      catalogLinked: false,
      linkedGlobalProductId: '',
      linkedProductIdentityId: '',
      linkedMatchedGlobalProductId: '',
      linkedMatchedGlobalArticleId: '',
      status: 'Nog niet verwerkt',
      candidates: [],
    }

    if (!isPlaceholder) {
      current.candidateCount += 1
      current.candidates.push(candidateItem)
    }

    if (isPlaceholder && Array.isArray(candidate.candidates)) {
      candidate.candidates.forEach((nestedCandidate) => {
        const nestedLinked = isBackendLinkedCandidate(nestedCandidate)
        const nestedItem = {
          id: candidateKey(nestedCandidate),
          candidateName: text(nestedCandidate.candidate_name),
          brand: text(nestedCandidate.candidate_brand),
          source: text(nestedCandidate.external_source_name || nestedCandidate.candidate_source_name || nestedCandidate.source_name),
          externalCode: text(nestedCandidate.external_source_product_code || nestedCandidate.candidate_source_product_code || nestedCandidate.source_product_code || nestedCandidate.retailer_article_number),
          variant: text(nestedCandidate.variant),
          score: nestedCandidate.score,
          status: candidateStatusFromBackend(nestedCandidate, nestedLinked),
          catalogLinked: nestedLinked,
          isLinkedToCatalog: nestedLinked,
          isLinkableToCatalog: Boolean(nestedCandidate.is_linkable_to_catalog) && !nestedLinked,
          isExistingLinkForReceiptItem: nestedLinked,
          canonicalCatalogProductId: text(nestedCandidate.canonical_catalog_product_id, ''),
          raw: nestedCandidate,
        }

        current.candidateCount += 1
        current.candidates.push(nestedItem)

        if (nestedLinked) {
          current.catalogLinked = true
          current.status = 'Gekoppeld'
          current.linkedGlobalProductId = text(nestedCandidate.global_product_id, current.linkedGlobalProductId || '')
          current.linkedProductIdentityId = text(nestedCandidate.product_identity_id, current.linkedProductIdentityId || '')
          current.linkedMatchedGlobalProductId = text(nestedCandidate.matched_global_product_id, current.linkedMatchedGlobalProductId || '')
          current.linkedMatchedGlobalArticleId = text(nestedCandidate.matched_global_article_id, current.linkedMatchedGlobalArticleId || '')
        }
      })
    }

    if (linked) {
      current.catalogLinked = true
      current.status = 'Gekoppeld'
      current.linkedGlobalProductId = text(candidate.global_product_id, current.linkedGlobalProductId || '')
      current.linkedProductIdentityId = text(candidate.product_identity_id, current.linkedProductIdentityId || '')
      current.linkedMatchedGlobalProductId = text(candidate.matched_global_product_id, current.linkedMatchedGlobalProductId || '')
      current.linkedMatchedGlobalArticleId = text(candidate.matched_global_article_id, current.linkedMatchedGlobalArticleId || '')
    } else if (current.candidateCount > 0) {
      current.status = 'Kandidaten gevonden'
    }

    if (!current.contextKey && candidate.context_key) current.contextKey = String(candidate.context_key)
    grouped.set(key, current)
  })

  return Array.from(grouped.values()).map((item) => {
    const uniqueCandidates = dedupeCandidates(item.candidates)
    const sortedCandidates = [...uniqueCandidates].sort((left, right) => Number(right.score || 0) - Number(left.score || 0))
    if (item.catalogLinked && sortedCandidates.length === 0) {
      sortedCandidates.push({
        id: `${item.id}-catalog-link`,
        candidateName: item.receiptLineText || 'Gekoppeld catalogusartikel',
        brand: '-',
        source: 'Rezzerv catalogus',
        externalCode: item.articleNumber || item.gtin || '-',
        variant: 'Bestaande koppeling',
        score: null,
        status: 'Gekoppeld',
        catalogLinked: true,
        isLinkedToCatalog: true,
        isLinkableToCatalog: false,
        isExistingLinkForReceiptItem: true,
        raw: {
          is_synthetic_catalog_link: true,
          context_key: item.contextKey,
          global_product_id: item.linkedGlobalProductId,
          product_identity_id: item.linkedProductIdentityId,
          matched_global_product_id: item.linkedMatchedGlobalProductId,
          matched_global_article_id: item.linkedMatchedGlobalArticleId,
          candidate_status: 'Gekoppeld',
          status: 'Gekoppeld',
        },
      })
    }
    const bestCandidate = bestCandidateForItem(sortedCandidates)
    const externalArticleNumber = candidateExternalCode(bestCandidate)
    const externalGtin = candidateExternalGtin(bestCandidate)

    return {
      ...item,
      articleNumber: externalArticleNumber || '-',
      gtin: externalGtin,
      candidateCount: sortedCandidates.length,
      candidates: sortedCandidates,
      bestCandidateName: text(bestCandidate?.candidateName, ''),
      bestCandidateScore: bestCandidate?.score ?? null,
    }
  })
}

function sortValue(item, key) {
  if (key === 'candidateCount') return Number(item.candidateCount || 0)
  if (key === 'bestCandidateScore') return Number(item.bestCandidateScore || 0)
  if (key === 'catalogLinked') return item.catalogLinked ? 1 : 0
  if (key === 'selected') return 0
  return String(item[key] || '').toLowerCase()
}

function csvValue(value) {
  const normalized = String(value ?? '').replaceAll('"', '""')
  return `"${normalized}"`
}

function CandidateProgressOverlay({ progress, percent }) {
  if (!progress?.active) return null
  return (
    <div className="rz-modal-backdrop" role="presentation">
      <div className="rz-modal-card" role="status" aria-live="polite" aria-label="Bonartikelen worden ingelezen">
        <h3 className="rz-modal-title">Bonartikelen inlezen</h3>
        <p className="rz-modal-text">{progress.label}</p>
        <div className="rz-external-progress-track">
          <div className="rz-external-progress-bar" style={{ width: `${percent}%` }} />
        </div>
        <p className="rz-modal-text">{progress.current} van {progress.total} verwerkt</p>
      </div>
    </div>
  )
}

export default function ReceiptItemsOverview({ onError, onMessage }) {
  const [items, setItems] = useState([])
  const [selectedItem, setSelectedItem] = useState(null)
  const [selectedCandidateId, setSelectedCandidateId] = useState('')
  const [selectedItemIds, setSelectedItemIds] = useState([])
  const [isLoading, setIsLoading] = useState(false)
  const [isProcessingCandidate, setIsProcessingCandidate] = useState(false)
  const [isUnlinking, setIsUnlinking] = useState(false)
  const [confirmOverwrite, setConfirmOverwrite] = useState(false)
  const [filters, setFilters] = useState({ receiptLineText: '', retailerCode: '', catalogLinked: 'all', articleNumber: '', gtin: '', quantity: '', price: '', amount: '', bestCandidateName: '', bestCandidateScore: '', candidateCount: '' })
  const [sortKey, setSortKey] = useState('receiptLineText')
  const [sortDesc, setSortDesc] = useState(false)
  const [page, setPage] = useState(1)
  const [ensuredPages, setEnsuredPages] = useState([])
  const [candidateProgress, setCandidateProgress] = useState({ active: false, current: 0, total: 0, label: '' })
  const [selectedItemCandidateLoadingId, setSelectedItemCandidateLoadingId] = useState('')
  const ensuringRef = useRef(false)
  const selectedItemRequestRef = useRef(0)

  async function fetchItems() {
    const response = await fetchJsonWithAuth('/api/external-databases/receipt-items?limit=500', { method: 'GET' })
    const data = await response.json().catch(() => ({}))
    if (!response.ok) throw new Error(data?.detail || 'Bonartikelen konden niet worden geladen')
    const candidates = Array.isArray(data?.items) ? data.items : []
    return buildReceiptItems(candidates)
  }

  async function loadItems() {
    setIsLoading(true)
    try {
      const nextItems = await fetchItems()
      setItems(nextItems)
      if (selectedItem) {
        const refreshedSelection = nextItems.find((item) => item.id === selectedItem.id) || null
        setSelectedItem(refreshedSelection)
      }
      setSelectedItemIds((current) => current.filter((id) => nextItems.some((item) => item.id === id)))
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
      const left = sortValue(leftItem, sortKey)
      const right = sortValue(rightItem, sortKey)
      if (left < right) return sortDesc ? 1 : -1
      if (left > right) return sortDesc ? -1 : 1
      return 0
    })

    return rows
  }, [items, filters, sortKey, sortDesc])

  // De backend levert Ã©Ã©n rij per bonartikelcontext.
  // Niet extra ontdubbelen op artikeltekst: gelijke omschrijvingen met andere artikelcode zijn aparte bonartikelen.
  const dedupedItems = filteredItems

  const pageCount = Math.max(1, Math.ceil(dedupedItems.length / PAGE_SIZE))
  const currentPage = Math.min(page, pageCount)
  const visibleItems = dedupedItems.slice((currentPage - 1) * PAGE_SIZE, currentPage * PAGE_SIZE)
  const emptyRows = Math.max(0, 3 - visibleItems.length)
  const visibleIds = visibleItems.map((item) => item.id)
  const allVisibleSelected = visibleIds.length > 0 && visibleIds.every((id) => selectedItemIds.includes(id))
  const selectedLinkedCount = items.filter((item) => selectedItemIds.includes(item.id) && item.catalogLinked).length
  const selectedItemCandidatesAreLoading = Boolean(selectedItem && selectedItemCandidateLoadingId === selectedItem.id)
  const selectedCandidates = selectedItemCandidatesAreLoading ? [] : (selectedItem?.candidates || [])
  const selectedCandidate = selectedCandidates.find((candidate) => candidate.id === selectedCandidateId) || null
  const selectedCandidateIsLinked = selectedCandidate?.isLinkedToCatalog === true
  const selectedCandidateCanBeLinked = Boolean(
    selectedCandidate &&
    selectedCandidate.isLinkableToCatalog === true &&
    selectedCandidateIsLinked === false
  )

  async function ensureCandidatesForPage(targetPage, sourceItems) {
    if (ensuringRef.current) return
    if (ensuredPages.includes(targetPage)) return

    const rows = sourceItems.slice((targetPage - 1) * PAGE_SIZE, targetPage * PAGE_SIZE)
    if (!rows.length) return

    ensuringRef.current = true
    setCandidateProgress({ active: true, current: 0, total: rows.length, label: 'Kandidaatartikelen bijlezen en wegen' })

    try {
      for (let index = 0; index < rows.length; index += 1) {
        const item = rows[index]
        setCandidateProgress({
          active: true,
          current: index + 1,
          total: rows.length,
          label: `Bijlezen en wegen: ${item.receiptLineText}`,
        })

        const response = await fetchJsonWithAuth('/api/external-databases/receipt-items/ensure-candidates', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            include_below_threshold: true,
            items: [{
              receipt_line_text: item.receiptLineText,
              retailer_code: item.retailerCodeRaw || item.retailerCode,
              purchase_import_line_id: item.purchaseImportLineId,
              receipt_line_id: item.receiptLineId,
            }],
          }),
        })
        const data = await response.json().catch(() => ({}))
        if (!response.ok) throw new Error(data?.detail || 'Kandidaten bijlezen is mislukt')
      }

      setEnsuredPages((current) => Array.from(new Set([...current, targetPage])))
      const refreshed = await fetchItems()
      setItems(refreshed)
    } catch (err) {
      onError?.(err?.message || 'Kandidaten bijlezen is mislukt')
    } finally {
      setCandidateProgress({ active: false, current: 0, total: 0, label: '' })
      ensuringRef.current = false
    }
  }

  useEffect(() => {
    if (items.length && dedupedItems.length) {
      ensureCandidatesForPage(currentPage, dedupedItems)
    }
  }, [items.length, dedupedItems.length, currentPage])

  async function selectReceiptItem(item) {
    const requestId = selectedItemRequestRef.current + 1
    selectedItemRequestRef.current = requestId

    setSelectedCandidateId('')
    setConfirmOverwrite(false)
    setSelectedItemCandidateLoadingId('')

    if (!item) {
      setSelectedItem(null)
      return
    }

    if (item.candidates?.length) {
      setSelectedItem(item)
      return
    }

    setSelectedItem({ ...item, candidates: [], candidateCount: 0 })
    setSelectedItemCandidateLoadingId(item.id)
    setCandidateProgress({
      active: true,
      current: 1,
      total: 1,
      label: `Bijlezen en wegen: ${item.receiptLineText}`,
    })

    try {
      const response = await fetchJsonWithAuth('/api/external-databases/receipt-items/ensure-candidates', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          include_below_threshold: true,
          items: [{
            receipt_line_text: item.receiptLineText,
            retailer_code: item.retailerCodeRaw || item.retailerCode,
            purchase_import_line_id: item.purchaseImportLineId,
            receipt_line_id: item.receiptLineId,
          }],
        }),
      })
      const data = await response.json().catch(() => ({}))
      if (!response.ok) throw new Error(data?.detail || 'Kandidaten bijlezen is mislukt')

      const refreshed = await fetchItems()
      if (selectedItemRequestRef.current !== requestId) return

      setItems(refreshed)
      const refreshedSelection = refreshed.find((nextItem) => nextItem.id === item.id) || null
      setSelectedItem(refreshedSelection || { ...item, candidates: [], candidateCount: 0 })
    } catch (err) {
      if (selectedItemRequestRef.current === requestId) {
        onError?.(err?.message || 'Kandidaten bijlezen is mislukt')
      }
    } finally {
      if (selectedItemRequestRef.current === requestId) {
        setCandidateProgress({ active: false, current: 0, total: 0, label: '' })
        setSelectedItemCandidateLoadingId('')
      }
    }
  }

  function toggleSelectedItem(itemId) {
    setSelectedItemIds((current) => (
      current.includes(itemId) ? current.filter((id) => id !== itemId) : [...current, itemId]
    ))
  }

  function toggleVisibleItems() {
    const allSelected = visibleIds.length > 0 && visibleIds.every((id) => selectedItemIds.includes(id))
    setSelectedItemIds((current) => {
      if (allSelected) return current.filter((id) => !visibleIds.includes(id))
      return Array.from(new Set([...current, ...visibleIds]))
    })
  }

  function goToPage(targetPage) {
    const normalized = Math.max(1, Math.min(pageCount, targetPage))
    setPage(normalized)
  }

  function exportSelectedItems() {
    const selectedRows = items.filter((item) => selectedItemIds.includes(item.id))
    if (!selectedRows.length) {
      onMessage?.('Selecteer eerst Ã©Ã©n of meer bonartikelen om te exporteren.')
      return
    }

    const rows = [
      ['Bonartikel', 'Winkelketen', 'Catalogus', 'Artikelnummer', 'GTIN / EAN', 'Omvang / gewicht', 'Prijs', 'Aantal', 'Kandidaat', 'Kandidaatscore', 'Externe kandidaten'],
      ...selectedRows.map((item) => [
        item.receiptLineText,
        item.retailerCode,
        item.catalogLinked ? 'Gekoppeld' : 'Niet gekoppeld',
        item.articleNumber,
        item.gtin,
        item.quantity,
        numberText(item.price),
        item.amount,
        item.bestCandidateName || '-',
        scoreText(item.bestCandidateScore),
        item.candidateCount,
      ]),
    ]

    const csv = rows.map((row) => row.map(csvValue).join(';')).join('\r\n')
    const blob = new Blob([csv], { type: 'text/csv;charset=utf-8' })
    const url = URL.createObjectURL(blob)
    const link = document.createElement('a')
    link.href = url
    link.download = 'rezzerv-externe-databases-bonartikelen.csv'
    link.click()
    URL.revokeObjectURL(url)
    onMessage?.(`Export gemaakt voor ${selectedRows.length} bonartikel(en).`)
  }

  async function unlinkByContextKeys(contextKeys) {
    const normalizedContextKeys = contextKeys.filter(Boolean)
    if (!normalizedContextKeys.length) {
      onMessage?.('Er zijn geen gekoppelde bonartikelen geselecteerd om te ontkoppelen.')
      return
    }

    setIsUnlinking(true)
    try {
      const response = await fetchJsonWithAuth('/api/external-databases/catalog/unlink', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ context_keys: normalizedContextKeys }),
      })
      const data = await response.json().catch(() => ({}))
      if (!response.ok) throw new Error(data?.detail || 'Ontkoppelen is mislukt')
      onMessage?.(`Ontkoppeld: ${data?.unlinked_count ?? 0} koppeling(en).`)
      setSelectedItemIds([])
      await loadItems()
    } catch (err) {
      onError?.(err?.message || 'Ontkoppelen is mislukt')
    } finally {
      setIsUnlinking(false)
    }
  }

  async function unlinkSelectedItems() {
    const selectedRows = items.filter((item) => selectedItemIds.includes(item.id) && item.catalogLinked)
    await unlinkByContextKeys(selectedRows.map((item) => item.contextKey))
  }

  async function unlinkCandidate(candidate) {
    if (!candidate?.id) return
    setIsUnlinking(true)
    try {
      const response = await fetchJsonWithAuth('/api/external-databases/catalog/unlink', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ candidate_ids: [candidate.id] }),
      })
      const data = await response.json().catch(() => ({}))
      if (!response.ok) throw new Error(data?.detail || 'Ontkoppelen is mislukt')
      onMessage?.(`Ontkoppeld: ${data?.unlinked_count ?? 0} koppeling(en).`)
      await loadItems()
    } catch (err) {
      onError?.(err?.message || 'Ontkoppelen is mislukt')
    } finally {
      setIsUnlinking(false)
    }
  }

  async function handleUnlinkSelectedCandidate() {
    if (!selectedCandidate) {
      onMessage?.('Selecteer eerst een kandidaat om te ontkoppelen.')
      return
    }
    if (!selectedCandidateIsLinked) {
      onMessage?.('Deze kandidaat is nog niet gekoppeld en kan daarom niet worden ontkoppeld.')
      return
    }
    if (selectedCandidate.isExistingLinkForReceiptItem || selectedCandidate.raw?.is_synthetic_catalog_link) {
      await unlinkByContextKeys([selectedItem?.contextKey])
    } else {
      await unlinkCandidate(selectedCandidate)
    }
    setSelectedCandidateId('')
  }

  async function processSelectedCandidate(options = {}) {
    if (!selectedItem || !selectedCandidate) return
    if (!selectedCandidateCanBeLinked) return

    setConfirmOverwrite(false)
    setIsProcessingCandidate(true)

    try {
      const response = await fetchJsonWithAuth('/api/external-databases/catalog/promote-candidate', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          candidate_id: selectedCandidate.raw?.id || selectedCandidate.id,
          force_overwrite: Boolean(options.forceOverwrite),
        }),
      })

      const data = await response.json().catch(() => ({}))
      if (!response.ok) throw new Error(data?.detail || 'Kandidaat verwerken is mislukt')

      if (data?.requires_overwrite && !options.forceOverwrite) {
        setConfirmOverwrite(true)
        return
      }

      if (data?.promoted) {
        onMessage?.('Kandidaat is gekoppeld.')
      } else {
        onMessage?.('Cataloguskoppeling is afgerond zonder mutatie.')
      }

      setSelectedCandidateId('')
      await loadItems()
    } catch (err) {
      onError?.(err?.message || 'Kandidaat verwerken is mislukt')
    } finally {
      setIsProcessingCandidate(false)
    }
  }

  function updateFilter(key, value) {
    setFilters((current) => ({ ...current, [key]: value }))
    setPage(1)
    setEnsuredPages([])
  }

  function updateSort(key) {
    if (sortKey === key) setSortDesc((value) => !value)
    else {
      setSortKey(key)
      setSortDesc(false)
    }
    setPage(1)
    setEnsuredPages([])
  }

  function sortMark(key) {
    if (sortKey !== key) return 'v'
    return sortDesc ? 'v' : '^'
  }

  const progressPercent = candidateProgress.total
    ? Math.round((candidateProgress.current / candidateProgress.total) * 100)
    : 0

  return (
    <div className="rz-external-receipt-overview">
      <div className="rz-external-databases-section-header">
        <h3>Bonartikelen voor externe herkenning</h3>
        <Button type="button" variant="secondary" disabled={isLoading || candidateProgress.active} onClick={loadItems}>Vernieuwen</Button>
      </div>

      {isLoading ? <div>Bonartikelen worden geladen...</div> : null}

      <CandidateProgressOverlay progress={candidateProgress} percent={progressPercent} />

      <div className="rz-external-databases-actions">
        <Button type="button" variant="secondary" disabled={!selectedItemIds.length} onClick={exportSelectedItems}>Exporteren</Button>
        <Button type="button" variant="secondary" disabled={!selectedLinkedCount || isUnlinking} onClick={unlinkSelectedItems}>
          {isUnlinking ? 'Ontkoppelen...' : 'Ontkoppelen'}
        </Button>
        <span className="rz-external-databases-muted">Geselecteerd: {selectedItemIds.length}</span>
      </div>

      {confirmOverwrite ? (
        <div className="rz-modal-backdrop" role="dialog" aria-modal="true" aria-labelledby="external-overwrite-title">
          <div className="rz-modal-card">
            <h3 id="external-overwrite-title" className="rz-modal-title">Cataloguskoppeling overschrijven?</h3>
            <p className="rz-modal-text">Dit bonartikel is al gekoppeld aan een catalogusartikel.</p>
            <p className="rz-modal-text">Wil je de bestaande koppeling overschrijven?</p>
            <div className="rz-modal-actions">
              <Button type="button" variant="primary" disabled={isProcessingCandidate} onClick={() => processSelectedCandidate({ forceOverwrite: true })}>Overschrijven</Button>
              <Button type="button" variant="secondary" disabled={isProcessingCandidate} onClick={() => setConfirmOverwrite(false)}>Annuleren</Button>
            </div>
          </div>
        </div>
      ) : null}

      <div className="rz-table-scroll rz-table-scroll--wide">
        <Table dataTestId="external-receipt-items-table" tableClassName="rz-external-receipt-table">
          <colgroup>
            <col className="rz-external-receipt-col-select" />
            <col className="rz-external-receipt-col-receipt" />
            <col className="rz-external-receipt-col-retailer" />
            <col className="rz-external-receipt-col-catalog" />
            <col className="rz-external-receipt-col-code" />
            <col className="rz-external-receipt-col-gtin" />
            <col className="rz-external-receipt-col-quantity" />
            <col className="rz-external-receipt-col-price" />
            <col className="rz-external-receipt-col-amount" />
            <col className="rz-external-receipt-col-candidate" />
            <col className="rz-external-receipt-col-candidate-score" />
            <col className="rz-external-receipt-col-candidates" />
          </colgroup>
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
              <th>
                <select className="rz-table-filter" value={filters.catalogLinked} onChange={(event) => updateFilter('catalogLinked', event.target.value)} aria-label="Catalogus filter">
                  <option value="all">Alle</option>
                  <option value="linked">Gekoppeld</option>
                  <option value="unlinked">Niet gekoppeld</option>
                </select>
              </th>
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

      <div className="rz-external-databases-pagination">
        <Button type="button" variant="secondary" disabled={currentPage <= 1 || candidateProgress.active} onClick={() => goToPage(currentPage - 1)}>Vorige</Button>
        <span className="rz-external-databases-page-indicator">Pagina {currentPage} van {pageCount}</span>
        <Button type="button" variant="secondary" disabled={currentPage >= pageCount || candidateProgress.active} onClick={() => goToPage(currentPage + 1)}>Volgende</Button>
      </div>

      <div className="rz-external-receipt-detail">
        {selectedItem ? (
          <>
            <h3>Koppelen kandidaten in artikel-catalogus</h3>

            <div className="rz-table-scroll">
              <Table dataTestId="external-receipt-item-candidates-table" tableClassName="rz-external-candidate-detail-table">
                <colgroup>
                  <col className="rz-external-candidate-col-choice" />
                  <col className="rz-external-candidate-col-name" />
                  <col className="rz-external-candidate-col-score" />
                  <col className="rz-external-candidate-col-brand" />
                  <col className="rz-external-candidate-col-source" />
                  <col className="rz-external-candidate-col-code" />
                  <col className="rz-external-candidate-col-variant" />
                  <col className="rz-external-candidate-col-status" />
                </colgroup>
                <thead>
                  <tr className="rz-table-header">
                    <th>Keuze</th>
                    <th>Kandidaat</th>
                    <th>Score</th>
                    <th>Merk</th>
                    <th>Bron</th>
                    <th>Externe code</th>
                    <th>Variant</th>
                    <th>Status</th>
                  </tr>
                </thead>
                <tbody>
                  {selectedItemCandidatesAreLoading ? (
                    <tr><td colSpan="8">Kandidaten worden bijgewerkt voor dit bonartikel...</td></tr>
                  ) : selectedCandidates.length ? selectedCandidates.map((candidate) => (
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
                      <td className="rz-num">{scoreText(candidate.score)}</td>
                      <td>{candidate.brand}</td>
                      <td>{candidate.source}</td>
                      <td>{candidate.externalCode}</td>
                      <td>{candidate.variant}</td>
                      <td>{candidate.status}</td>
                    </tr>
                  )) : <tr><td colSpan="8">Geen externe kandidaten gevonden voor dit bonartikel.</td></tr>}
                </tbody>
              </Table>
            </div>

            <div className="rz-external-databases-actions rz-external-detail-actions">
              <Button
                type="button"
                disabled={!selectedCandidateCanBeLinked || isProcessingCandidate}
                onClick={processSelectedCandidate}
              >
                {isProcessingCandidate ? 'Verwerken...' : 'Koppel artikel'}
              </Button>
              <Button
                type="button"
                variant="secondary"
                disabled={!selectedCandidateIsLinked || isUnlinking}
                onClick={handleUnlinkSelectedCandidate}
              >
                {isUnlinking ? 'Ontkoppelen...' : 'Ontkoppel artikel'}
              </Button>
            </div>
          </>
        ) : <p className="rz-external-databases-muted">Dubbelklik op een bonartikel om de externe kandidaten te bekijken.</p>}
      </div>
    </div>
  )
}

