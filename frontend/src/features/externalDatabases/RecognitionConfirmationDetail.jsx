import { useEffect, useMemo, useState } from 'react'
import Button from '../../ui/Button'
import Table from '../../ui/Table'
import { fetchJsonWithAuth } from '../../lib/authSession'
import './externalDatabasesRecovery.css'

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

export function isRecognitionConfirmed(candidate) {
  return statusValue(candidate) === 'external_resolved'
    || text(candidate?.candidate_status).toLowerCase() === 'external_resolved'
    || text(candidate?.external_match_status).toLowerCase() === 'external_resolved'
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

export function candidateCanBeRecognitionConfirmed(candidate) {
  return Boolean(candidateId(candidate) && candidateCode(candidate))
    && !isCatalogLinked(candidate)
    && !isFallbackCandidate(candidate)
}

export function dedupeRecognitionCandidates(candidates) {
  const deduped = new Map()
  for (const candidate of Array.isArray(candidates) ? candidates : []) {
    if (!candidate || typeof candidate !== 'object') continue
    const id = candidateId(candidate)
    if (!id) continue
    const existing = deduped.get(id)
    if (!existing || isRecognitionConfirmed(candidate) || Number(candidate?.score || 0) > Number(existing?.score || 0)) {
      deduped.set(id, candidate)
    }
  }
  return Array.from(deduped.values()).sort((left, right) => {
    if (isRecognitionConfirmed(left) !== isRecognitionConfirmed(right)) return isRecognitionConfirmed(left) ? -1 : 1
    return Number(right?.score || 0) - Number(left?.score || 0)
  })
}

export function recognitionStatus(candidates) {
  const rows = dedupeRecognitionCandidates(candidates)
  if (rows.some(isRecognitionConfirmed)) return 'Herkenning bevestigd'
  if (rows.some(candidateCanBeRecognitionConfirmed)) return 'Herkenning beschikbaar'
  return ''
}

export default function RecognitionConfirmationDetail({ item, onConfirmed, onError, onMessage }) {
  const candidates = useMemo(
    () => dedupeRecognitionCandidates(item?.recognitionCandidates),
    [item?.recognitionCandidates],
  )
  const [selectedCandidateId, setSelectedCandidateId] = useState('')
  const [isConfirming, setIsConfirming] = useState(false)
  const [requiresOverwrite, setRequiresOverwrite] = useState(false)
  const [feedback, setFeedback] = useState('')

  useEffect(() => {
    const confirmed = candidates.find(isRecognitionConfirmed)
    const firstConfirmable = candidates.find(candidateCanBeRecognitionConfirmed)
    setSelectedCandidateId(candidateId(confirmed || firstConfirmable || {}))
    setRequiresOverwrite(false)
    setFeedback('')
  }, [item?.id])

  const selectedCandidate = useMemo(
    () => candidates.find((candidate) => candidateId(candidate) === selectedCandidateId) || null,
    [candidates, selectedCandidateId],
  )

  async function confirmRecognition(forceOverwrite = false) {
    if (!selectedCandidate || !candidateCanBeRecognitionConfirmed(selectedCandidate)) return
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
      if (!data?.confirmed) throw new Error(data?.reason || 'Herkenning is niet bevestigd')
      setRequiresOverwrite(false)
      setFeedback('Herkenning bevestigd')
      onMessage?.('Herkenning bevestigd')
      await onConfirmed?.()
    } catch (err) {
      onError?.(err?.message || 'Herkenning bevestigen is mislukt')
    } finally {
      setIsConfirming(false)
    }
  }

  if (!item || candidates.length === 0) return null

  const canConfirm = Boolean(
    selectedCandidate
    && candidateCanBeRecognitionConfirmed(selectedCandidate)
    && !isRecognitionConfirmed(selectedCandidate),
  )

  return (
    <div className="rz-external-recognition-detail" data-testid="external-recognition-detail">
      <h4>Herkenning bevestigen</h4>
      <p className="rz-external-databases-muted">
        Bevestigen legt alleen de externe bron en winkel-/broncode vast. De Catalogus-koppeling blijft een aparte vervolgstap.
      </p>
      <div className="rz-table-scroll rz-table-scroll--wide">
        <Table dataTestId="external-recognition-candidates-table" tableClassName="rz-external-candidate-detail-table" tableStyle={DETAIL_TABLE_STYLE} resizableColumns>
          <colgroup><col style={{ width: '60px' }} /><col style={{ width: '220px' }} /><col style={{ width: '140px' }} /><col style={{ width: '180px' }} /><col style={{ width: '210px' }} /><col style={{ width: '80px' }} /><col style={{ width: '170px' }} /></colgroup>
          <thead><tr className="rz-table-header"><th>Keuze</th><th>Kandidaat</th><th>Merk</th><th>Bron</th><th>Winkel-/broncode</th><th className="rz-num">Score</th><th>Status</th></tr></thead>
          <tbody>
            {candidates.map((candidate) => {
              const id = candidateId(candidate)
              const confirmable = candidateCanBeRecognitionConfirmed(candidate)
              return (
                <tr key={id} className={selectedCandidateId === id ? 'rz-row-selected' : ''}>
                  <td className="rz-check"><input type="radio" name="external-recognition-candidate" checked={selectedCandidateId === id} disabled={!confirmable} onChange={() => { setSelectedCandidateId(id); setRequiresOverwrite(false); setFeedback('') }} /></td>
                  <td>{text(candidate.candidate_name, '-')}</td><td>{text(candidate.candidate_brand, '-')}</td><td>{candidateSource(candidate)}</td><td>{candidateCode(candidate) || '-'}</td><td className="rz-num">{scoreText(candidate.score)}</td><td>{candidateStatusLabel(candidate)}</td>
                </tr>
              )
            })}
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
  )
}
