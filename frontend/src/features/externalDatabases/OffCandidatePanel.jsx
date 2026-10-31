import { useEffect, useRef, useState } from 'react'
import DataTable from '../../ui/DataTable'
import Button from '../../ui/Button'
import { useNavigate } from 'react-router-dom'
import { fetchJsonWithAuth } from '../../lib/authSession'
import { displayRecognition, displaySource } from './offCandidatePresentation'
import { useMobileAppViewport } from '../../app/mobileViewport'
import Ed2ManualBarcodeEntry from './Ed2ManualBarcodeEntry'
import { useAppFeedback } from '../../ui/AppFeedbackProvider'

const columns = [
  { key: 'rank', label: 'Rangnummer', header: <span className="rz-external-off-visually-hidden">Rangnummer</span>, width: 58, align: 'right', sortable: true },
  { key: 'product_name', label: 'Artikel', width: 280, sortable: true, filterable: true },
  { key: 'brand', label: 'Merk', width: 150, sortable: true, filterable: true },
  { key: 'source', label: 'Bron', width: 125, sortable: true, filterable: true },
  { key: 'evidence_label', label: 'Herkenning', width: 210, sortable: true, filterable: true },
  { key: 'gtin', label: 'Barcode', width: 170, sortable: true, filterable: true },
  { key: 'quantity', label: 'Inhoud', width: 140, sortable: true, filterable: true },
  { key: 'match', label: 'Overeenkomst', width: 140, align: 'right', sortable: true,
    renderCell: (row) => `${Math.round(row.match * 100)}%` },
]

export default function OffCandidatePanel({ item, onLinkOutcome, returnState }) {
  const navigate = useNavigate()
  const isMobile = useMobileAppViewport()
  const { showFeedback } = useAppFeedback()
  const [results, setResults] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [attempt, setAttempt] = useState(0)
  const [verifying, setVerifying] = useState(false)
  const [selectedCandidate, setSelectedCandidate] = useState(null)
  const [linking, setLinking] = useState(false)
  const [linkError, setLinkError] = useState('')
  const verificationRef = useRef(null)

  useEffect(() => () => verificationRef.current?.abort(), [])

  useEffect(() => {
    const controller = new AbortController()
    let active = true
    setLoading(true)
    setResults([])
    setError('')
    async function search() {
      try {
        // Source identity and store evidence are resolved by the backend.
        const response = await fetchJsonWithAuth('/api/external-databases/products/search-preview', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          signal: controller.signal,
          body: JSON.stringify({ receipt_item_id: item.id, mode: 'automatic', limit: 20 }),
        })
        const payload = await response.json().catch(() => ({}))
        if (!response.ok) throw new Error(typeof payload.detail === 'string' ? payload.detail : 'Open Food Facts kon niet worden geraadpleegd.')
        if (payload.provider === 'unavailable') throw new Error('Open Food Facts is tijdelijk niet bereikbaar. Probeer opnieuw.')
        if (active) setResults((Array.isArray(payload.results) ? payload.results : []).map((row, index) => ({
          ...row, rank: index + 1, source: displaySource(row.source),
          evidence_label: displayRecognition(row.evidence_label),
          match: Number(row.automatic_rank_score ?? row.score) || 0,
        })))
      } catch (err) {
        if (active && err.name !== 'AbortError') setError(err.message || 'Open Food Facts kon niet worden geraadpleegd.')
      } finally {
        if (active) setLoading(false)
      }
    }
    search()
    return () => { active = false; controller.abort() }
  }, [item, attempt])

  async function selectCandidate(candidate) {
    if (verifying || linking) return
    setLinkError('')
    if (item.link_status && item.link_status !== 'unlinked') {
      setLinkError('Dit artikel is al gekoppeld of wacht op classificatie. Controleer eerst de bestaande koppeling.')
      return
    }
    // A retailer/automatic preview is not a signed OFF identity. Obtain a
    // short-lived, receipt-bound proof using the existing manual exact-GTIN API.
    // This also rejects store-only candidates not actually found in OFF.
    const gtin = String(candidate.gtin || '')
    if (!/^(?:[0-9]{8}|[0-9]{12,14})$/.test(gtin)) {
      setLinkError('Deze kandidaat heeft geen bruikbare barcode.')
      return
    }
    const lookupGtin = gtin.length === 14 && gtin.startsWith('0') ? gtin.slice(1) : gtin
    const controller = new AbortController()
    verificationRef.current = controller
    setVerifying(true)
    try {
      const response = await fetchJsonWithAuth('/api/external-products/off/search', {
        method: 'POST', headers: { 'Content-Type': 'application/json' }, signal: controller.signal,
        body: JSON.stringify({ receipt_item_id: item.id, mode: 'manual', gtin: lookupGtin, limit: 20 }),
      })
      const payload = await response.json().catch(() => ({}))
      if (!response.ok) throw new Error(typeof payload.detail === 'string' ? payload.detail : 'Verificatie in OFF is niet gelukt.')
      const verified = (Array.isArray(payload.results) ? payload.results : []).find((row) =>
        String(row.gtin || '').padStart(14, '0') === gtin.padStart(14, '0'))
      if (verified?.identity_compatible === false) {
        throw new Error('Dit product past niet veilig bij het bonartikel.')
      }
      if (!verified?.selection_proof) {
        throw new Error('Dit product kon niet in OFF worden bevestigd. Gebruik Zelf zoeken in OFF om een andere kandidaat te vinden.')
      }
      if (!controller.signal.aborted) setSelectedCandidate(verified)
    } catch (err) {
      if (!controller.signal.aborted && err.status !== 401) setLinkError(
        err.name === 'AbortError' ? 'Verificatie niet bevestigd. Probeer opnieuw.' :
          (err.message || 'Verificatie niet bevestigd.'))
    } finally {
      if (verificationRef.current === controller) verificationRef.current = null
      if (!controller.signal.aborted) setVerifying(false)
    }
  }

  async function confirmLink() {
    if (!selectedCandidate || linking) return
    setLinking(true)
    setLinkError('')
    const controller = new AbortController()
    const deadline = window.setTimeout(() => controller.abort(), 30000)
    try {
      const response = await fetchJsonWithAuth('/api/external-databases/off/link-selected', {
        method: 'POST', headers: { 'Content-Type': 'application/json' }, signal: controller.signal,
        body: JSON.stringify({
          receipt_item_id: item.id, gtin: selectedCandidate.gtin,
          selection_proof: selectedCandidate.selection_proof,
        }),
      })
      const payload = await response.json().catch(() => ({}))
      if (!response.ok || (payload.linked !== true && payload.cataloged !== true)) {
        throw new Error(typeof payload.detail === 'string' ? payload.detail : 'Koppeling niet bevestigd.')
      }
      onLinkOutcome({
        status: 'success',
        message: payload.classification_pending === true
          ? 'Artikel opgeslagen in Catalogus. GS1-classificatie ontbreekt nog.'
          : 'Artikel gekoppeld aan de Catalogus.',
      })
    } catch (err) {
      if (err.status !== 401) {
        const message = err.name === 'AbortError'
          ? 'Koppeling niet op tijd bevestigd. Controleer de Catalogus voordat u opnieuw koppelt.'
          : (err.message || 'De koppeling kon niet worden bevestigd.')
        // An unsuccessful POST is not a confirmed link. Show its reason
        // immediately as the standard Melding, instead of leaving an inline
        // error above a scrolled candidate table where it may be invisible.
        showFeedback({ variant: 'error', message: 'Koppeling niet bevestigd: ' + message })
      }
    } finally {
      window.clearTimeout(deadline)
      setSelectedCandidate(null)
      setLinking(false)
    }
  }

  return (
    <section className="rz-external-receipt-detail" aria-labelledby="off-candidate-heading" data-testid="external-databases-2-off-panel" aria-busy={loading || verifying || linking}>
      <div className="rz-external-databases-card rz-external-databases-card--off">
        <h3 id="off-candidate-heading">Productkandidaten voor {item.receipt_line_text} — {item.retailer}</h3>
        <p>Productgegevens van Albert Heijn, Jumbo en Lidl waar beschikbaar, aangevuld met Open Food Facts (OFF). Zoeken slaat niets op. {isMobile ? 'Tik' : 'Dubbelklik'} op een kandidaat om een koppeling te controleren en te bevestigen.</p>
        <div className="rz-external-databases-actions">
          <Button type="button" variant="secondary" onClick={() => navigate('/externe-databases-2/off-zoeken/' + encodeURIComponent(item.id), { state: { item, ed2TableState: returnState } })}>
            Zelf zoeken in OFF
          </Button>
        </div>
        <Ed2ManualBarcodeEntry item={item} onSaved={onLinkOutcome} />
        {loading ? <p role="status">Kandidaten zoeken bij de winkel en in Open Food Facts...</p> : null}
        {verifying ? <p role="status">Kandidaat controleren in OFF...</p> : null}
        {linkError ? <p role="alert">{linkError}</p> : null}
        {error ? <div role="alert"><p>{error}</p><Button type="button" variant="secondary" onClick={() => setAttempt((value) => value + 1)}>Opnieuw zoeken</Button></div> : null}
        {!loading && !error ? <DataTable
          columns={columns}
          data={results}
          pageSize={7}
          getRowKey={(row) => row.gtin}
          defaultSort={{ key: 'rank', direction: 'asc' }}
          emptyMessage="Geen passende productkandidaten gevonden."
          dataTestId="external-databases-2-off-candidates"
          renderRow={(candidate) => <tr
            key={candidate.gtin}
            tabIndex={0}
            className="rz-external-off-link-row"
            onDoubleClick={() => { if (!isMobile) selectCandidate(candidate) }}
            onClick={() => { if (isMobile) selectCandidate(candidate) }}
            onKeyDown={(event) => {
              if (event.target !== event.currentTarget) return
              if (event.key === 'Enter' || event.key === ' ') {
                event.preventDefault()
                selectCandidate(candidate)
              }
            }}
          >{columns.map((column) => <td key={column.key} className={column.align === 'right' ? 'rz-num' : column.cellClassName || ''}>
            {typeof column.renderCell === 'function' ? column.renderCell(candidate) : String(candidate[column.key] ?? '')}
          </td>)}</tr>}
        /> : null}
      </div>
      {selectedCandidate ? <div className="rz-modal-backdrop">
        <div className="rz-modal-card" role="alertdialog" aria-modal="true" aria-labelledby="ed2-link-confirm">
          <p className="rz-modal-text" id="ed2-link-confirm">
            Wilt u <strong>{item.receipt_line_text}</strong> ({item.retailer}) koppelen aan
            <strong> {selectedCandidate.product_name}</strong>
            {selectedCandidate.brand ? ' — ' + selectedCandidate.brand : ''}?
            <span> Barcode: {selectedCandidate.gtin}</span>
          </p>
          <div className="rz-modal-actions">
            <Button type="button" variant="secondary" disabled={linking} onClick={() => setSelectedCandidate(null)}>Annuleren</Button>
            <Button type="button" disabled={linking} onClick={confirmLink}>{linking ? 'Koppelen...' : 'OK'}</Button>
          </div>
        </div>
      </div> : null}
    </section>
  )
}
