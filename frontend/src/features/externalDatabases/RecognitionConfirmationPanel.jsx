import { useEffect, useMemo, useState } from 'react'
import Button from '../../ui/Button'
import Table from '../../ui/Table'
import { fetchJsonWithAuth } from '../../lib/authSession'

const TABLE_STYLE = { width: '1120px', minWidth: '1120px' }
const DETAIL_TABLE_STYLE = { width: '980px', minWidth: '980px' }
const FALLBACK_MARKERS = ['fallback', 'unresolved', 'no_external_match', 'receipt_product_intent_fallback']

function text(value, fallback = '') {
  const normalized = String(value ?? '').trim()
  return normalized || fallback
}

function scoreText(value) {
  if (value === null || value === undefined || value === '') return '-'
  const number = Number(value)
  if (!Number.isFinite(number)) return '-'
  return number.toLocaleString('nl-NL', { minimumFractionDigits: 3, maximumFractionDigits: 3 })
}

function retailerLabel(value) {
  const normalized = text(value)
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

function candidateId(candidate) {
  return text(candidate?.candidate_id || candidate?.id)
}

function candidateCode(candidate) {
  return text(
    candidate?.external_source_product_code
    || candidate?.candidate_source_product_code
    || candidate?.source_product_code
    || candidate?.retailer_article_number
    || candidate?.gtin
    || candidate?.ean
    || candidate?.code,
  )
}

function candidateSource(candidate) {
  return text(
    candidate?.external_source_name
    || candidate?.candidate_source_name
    || candidate?.source_name,
    'Onbekende bron',
  )
}

function statusValue(candidate) {
  return text(candidate?.status || candidate?.candidate_status).toLowerCase()
}

function isFallbackCandidate(candidate) {
  const haystack = [
    candidate?.status,
    candidate?.candidate_status,
    candidate?.candidate_source_name,
    candidate?.source_name,
    candidate?.candidate_source_product_code,
    candidate?.source_product_code,
    candidate?.variant,
  ].map((value) => text(value).toLowerCase()).join(' ')
  return FALLBACK_MARKERS.some((marker) => haystack.includes(marker))
}

function isCatalogLinked(candidate) {
  return statusValue(candidate) === 'linked_to_catalog'
    || Boolean(candidate?.is_linked_to_catalog)
    || Boolean(text(candidate?.global_product_id))
    || Boolean(candidate?.central_link_active)
}

function isRecognitionConfirmed(candidate) {
  return statusValue(candidate) === 'external_resolved'
    || text(candidate?.candidate_status).toLowerCase() === 'external_resolved'
    || text(candidate?.external_match_status).toLowerCase() === 'external_resolved'
}

function recognitionStatusLabel(candidate) {
  if (isCatalogLinked(candidate)) return 'Catalogus gekoppeld'
  if (isRecognitionConfirmed(candidate)) return 'Herkenning bevestigd'
  if (isFallbackCandidate(candidate)) return 'Geen externe match'
  if (candidateCode(candidate)) return 'Herkenning beschikbaar'
  return 'Nog niet herkend'
}

function candidateStatusLabel(candidate) {
  if (isCatalogLinked(candidate)) return 'Catalogus gekoppeld'
  if (isRecognitionConfirmed(candidate)) return 'Herkenning bevestigd'
  if (isFallbackCandidate(candidate)) return 'Niet bevestigbaar'
  const status = text(candidate?.candidate_status || candidate?.status)
  if (status === 'probable_candidate') return 'Waarschijnlijke kandidaat'
  if (status === 'possible_candidate') return 'Mogelijke kandidaat'
  if (status === 'weak_candidate') return 'Lage zekerheid'
  if (status === 'off_candidate') return 'OFF-kandidaat'
  return status || 'Kandidaat'
}

function candidateCanBeConfirmed(candidate) {
  return Boolean(candidateId(candidate) && candidateCode(candidate))
    && !isCatalogLinked(candidate)
    && !isFallbackCandidate(candidate)
}

function receiptItemId(rawItem) {
  return text(
    rawItem?.receipt_item_id
    || rawItem?.context_key
    || rawItem?.purchase_import_line_id
    || rawItem?.receipt_line_id
    || rawItem?.id,
  )
}

function buildRecognitionItems(rawItems) {
  const grouped = new Map()

  for (const rawItem of Array.isArray(rawItems) ? rawItems : []) {
    if (!rawItem || typeof rawItem !== 'object') continue
    const id = receiptItemId(rawItem)
    if (!id) continue

    const current = grouped.get(id) || {
      id,
      receiptLineText: text(rawItem.receipt_line_text || rawItem.raw_label || rawItem.normalized_label, '-'),
      retailerCode: retailerLabel(rawItem.retailer_code),
      contextKey: text(rawItem.context_key),
      receiptLineId: text(rawItem.receipt_line_id),
      purchaseImportLineId: text(rawItem.purchase_import_line_id),
      candidates: [],
    }

    const nested = Array.isArray(rawItem.candidates) ? rawItem.candidates : []
    for (const candidate of nested) {
      if (!candidate || typeof candidate !== 'object') continue
      if (!candidateId(candidate)) continue
      current.candidates.push({ ...candidate })
    }

    if (!rawItem.is_receipt_item_placeholder && candidateId(rawItem) && candidateCode(rawItem)) {
      current.candidates.push({ ...rawItem })
    }

    if (isRecognitionConfirmed(rawItem) && candidateId(rawItem)) {
      current.candidates.push({ ...rawItem })
    }

    grouped.set(id, current)
  }

  return Array.from(grouped.values()).map((item) => {
    const deduped = new Map()
    for (const candidate of item.candidates) {
      const key = candidateId(candidate)
      if (!key) continue
      const existing = deduped.get(key)
      if (!existing || isRecognitionConfirmed(candidate) || Number(candidate?.score || 0) > Number(existing?.score || 0)) {
        deduped.set(key, candidate)
      }
    }

    const candidates = Array.from(deduped.values()).sort((left, right) => {
      if (isRecognitionConfirmed(left) !== isRecognitionConfirmed(right)) return isRecognitionConfirmed(left) ? -1 : 1
      return Number(right?.score || 0) - Number(left?.score || 0)
    })
    const confirmed = candidates.find(isRecognitionConfirmed) || null
    const best = confirmed || candidates.find(candidateCanBeConfirmed) || candidates[0] || null

    return {
      ...item,
      candidates,
      status: best ? recognitionStatusLabel(best) : 'Nog niet herkend',
      recognizedName: best ? text(best.candidate_name, '-') : '-',
      source: best ? candidateSource(best) : '-',
      externalCode: best ? candidateCode(best) || '-' : '-',
      candidateCount: candidates.filter(candidateCanBeConfirmed).length,
      confirmedCandidateId: confirmed ? candidateId(confirmed) : '',
    }
  }).sort((left, right) => left.receiptLineText.localeCompare(right.receiptLineText, 'nl'))
}

export default function RecognitionConfirmationPanel({ onError, onMessage }) {
  const [items, setItems] = useState([])
  const [selectedItemId, setSelectedItemId] = useState('')
  const [selectedCandidateId, setSelectedCandidateId] = useState('')
  const [isLoading, setIsLoading] = useState(true)
  const [isConfirming, setIsConfirming] = useState(false)
  const [requiresOverwrite, setRequiresOverwrite] = useState(false)
  const [feedback, setFeedback] = useState('')

  async function loadItems() {
    setIsLoading(true)
    try {
      const response = await fetchJsonWithAuth('/api/external-databases/receipt-items?limit=500', { method: 'GET' })
      const data = await response.json().catch(() => ({}))
      if (!response.ok) throw new Error(data?.detail || 'Bonartikelen voor herkenning konden niet worden geladen')
      const nextItems = buildRecognitionItems(data?.items)
      setItems(nextItems)
      setSelectedItemId((current) => current && nextItems.some((item) => item.id === current) ? current : '')
      setSelectedCandidateId((current) => current && nextItems.some((item) => item.candidates.some((candidate) => candidateId(candidate) === current)) ? current : '')
    } catch (err) {
      onError?.(err?.message || 'Bonartikelen voor herkenning konden niet worden geladen')
    } finally {
      setIsLoading(false)
    }
  }

  useEffect(() => {
    loadItems()
  }, [])

  const selectedItem = useMemo(
    () => items.find((item) => item.id === selectedItemId) || null,
    [items, selectedItemId],
  )
  const selectedCandidate = useMemo(
    () => selectedItem?.candidates.find((candidate) => candidateId(candidate) === selectedCandidateId) || null,
    [selectedItem, selectedCandidateId],
  )

  function selectItem(item) {
    setSelectedItemId(item.id)
    setRequiresOverwrite(false)
    setFeedback('')
    const confirmed = item.candidates.find(isRecognitionConfirmed)
    const firstConfirmable = item.candidates.find(candidateCanBeConfirmed)
    setSelectedCandidateId(candidateId(confirmed || firstConfirmable || {}))
  }

  async function confirmRecognition(forceOverwrite = false) {
    if (!selectedCandidate || !candidateCanBeConfirmed(selectedCandidate)) return
    setIsConfirming(true)
    setFeedback('')
    try {
      const response = await fetchJsonWithAuth('/api/external-databases/candidates/confirm-external', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          candidate_id: candidateId(selectedCandidate),
          force_overwrite: forceOverwrite,
        }),
      })
      const data = await response.json().catch(() => ({}))
      if (!response.ok || data?.ok === false) {
        throw new Error(data?.detail || data?.reason || 'Herkenning bevestigen is mislukt')
      }
      if (data?.requires_overwrite) {
        setRequiresOverwrite(true)
        setFeedback('Er is al een bevestigde herkenning voor dit bonartikel. Kies Vervang bevestigde herkenning om deze keuze bewust te vervangen.')
        return
      }
      if (!data?.confirmed) {
        throw new Error(data?.reason || 'Herkenning is niet bevestigd')
      }
      setRequiresOverwrite(false)
      setFeedback('Herkenning bevestigd')
      onMessage?.('Herkenning bevestigd')
      await loadItems()
    } catch (err) {
      onError?.(err?.message || 'Herkenning bevestigen is mislukt')
    } finally {
      setIsConfirming(false)
    }
  }

  const canConfirm = Boolean(selectedCandidate && candidateCanBeConfirmed(selectedCandidate) && !isRecognitionConfirmed(selectedCandidate))

  return (
    <div className="rz-external-receipt-overview" data-testid="external-recognition-panel">
      <div className="rz-external-databases-section-header">
        <div>
          <h3>Herkenning bevestigen</h3>
          <p className="rz-external-databases-muted">
            Bevestigen legt alleen de externe bron en winkel-/broncode vast. Dit is geen cataloguskoppeling en maakt geen Mijn artikel of voorraadmutatie.
          </p>
        </div>
        <Button type="button" variant="secondary" disabled={isLoading} onClick={loadItems}>
          {isLoading ? 'Laden...' : 'Vernieuwen'}
        </Button>
      </div>

      <div className="rz-table-scroll rz-table-scroll--wide">
        <Table dataTestId="external-recognition-items-table" tableClassName="rz-external-receipt-table" tableStyle={TABLE_STYLE} resizableColumns>
          <colgroup><col style={{ width: '170px' }} /><col style={{ width: '120px' }} /><col style={{ width: '160px' }} /><col style={{ width: '220px' }} /><col style={{ width: '180px' }} /><col style={{ width: '190px' }} /><col style={{ width: '80px' }} /></colgroup>
          <thead>
            <tr className="rz-table-header">
              <th>Bonartikel</th><th>Winkelketen</th><th>Status</th><th>Herkend artikel</th><th>Bron</th><th>Winkel-/broncode</th><th className="rz-num">Kandidaten</th>
            </tr>
          </thead>
          <tbody>
            {items.length ? items.map((item) => (
              <tr key={item.id} className={selectedItemId === item.id ? 'rz-row-active' : ''} onDoubleClick={() => selectItem(item)} data-testid={`external-recognition-row-${item.id}`}>
                <td>{item.receiptLineText}</td><td>{item.retailerCode}</td><td>{item.status}</td><td>{item.recognizedName}</td><td>{item.source}</td><td>{item.externalCode}</td><td className="rz-num">{item.candidateCount}</td>
              </tr>
            )) : (
              <tr><td colSpan="7">Geen bonartikelen met externe herkenningsinformatie beschikbaar.</td></tr>
            )}
          </tbody>
        </Table>
      </div>

      {selectedItem ? (
        <div className="rz-external-receipt-detail" data-testid="external-recognition-detail">
          <h3>Herkenningskandidaten voor {selectedItem.receiptLineText}</h3>
          <p className="rz-external-databases-muted">Selecteer de externe bron die bij dit bonartikel hoort. De Catalogus-koppeling blijft een aparte vervolgstap.</p>
          <div className="rz-table-scroll rz-table-scroll--wide">
            <Table dataTestId="external-recognition-candidates-table" tableClassName="rz-external-candidate-detail-table" tableStyle={DETAIL_TABLE_STYLE} resizableColumns>
              <colgroup><col style={{ width: '60px' }} /><col style={{ width: '220px' }} /><col style={{ width: '140px' }} /><col style={{ width: '180px' }} /><col style={{ width: '210px' }} /><col style={{ width: '80px' }} /><col style={{ width: '170px' }} /></colgroup>
              <thead><tr className="rz-table-header"><th>Keuze</th><th>Kandidaat</th><th>Merk</th><th>Bron</th><th>Winkel-/broncode</th><th className="rz-num">Score</th><th>Status</th></tr></thead>
              <tbody>
                {selectedItem.candidates.length ? selectedItem.candidates.map((candidate) => {
                  const id = candidateId(candidate)
                  const confirmable = candidateCanBeConfirmed(candidate)
                  return (
                    <tr key={id || `${candidateSource(candidate)}-${candidateCode(candidate)}`} className={selectedCandidateId === id ? 'rz-row-selected' : ''}>
                      <td className="rz-check"><input type="radio" name="external-recognition-candidate" checked={selectedCandidateId === id} disabled={!confirmable} onChange={() => { setSelectedCandidateId(id); setRequiresOverwrite(false); setFeedback('') }} /></td>
                      <td>{text(candidate.candidate_name, '-')}</td><td>{text(candidate.candidate_brand, '-')}</td><td>{candidateSource(candidate)}</td><td>{candidateCode(candidate) || '-'}</td><td className="rz-num">{scoreText(candidate.score)}</td><td>{candidateStatusLabel(candidate)}</td>
                    </tr>
                  )
                }) : <tr><td colSpan="7">Geen herkenningskandidaten beschikbaar.</td></tr>}
              </tbody>
            </Table>
          </div>
          <div className="rz-external-databases-actions">
            <Button type="button" disabled={!canConfirm || isConfirming || requiresOverwrite} onClick={() => confirmRecognition(false)}>
              {isConfirming && !requiresOverwrite ? 'Bevestigen...' : 'Bevestig herkenning'}
            </Button>
            {requiresOverwrite ? (
              <Button type="button" variant="secondary" disabled={isConfirming} onClick={() => confirmRecognition(true)}>
                {isConfirming ? 'Vervangen...' : 'Vervang bevestigde herkenning'}
              </Button>
            ) : null}
            {feedback ? <span className="rz-inline-feedback rz-inline-feedback--success" data-testid="external-recognition-feedback">{feedback}</span> : null}
          </div>
        </div>
      ) : null}
    </div>
  )
}
