import { useEffect, useState } from 'react'
import Button from '../../ui/Button'
import Table from '../../ui/Table'
import Pagination from '../../ui/Pagination.jsx'
import { fetchJsonWithAuth } from '../../lib/authSession'
import { useAppFeedback } from '../../ui/AppFeedbackProvider.jsx'

/** Product-level review; receipt text + receipt number, not bare code, is the PO key. */
export default function CatalogRetailerCodesReview({ globalProductId, canEdit }) {
  const { showFeedback } = useAppFeedback()
  const [rows, setRows] = useState([])
  const [loading, setLoading] = useState(true)
  const [selection, setSelection] = useState(null)
  const [targetGtin, setTargetGtin] = useState('')
  const [saving, setSaving] = useState(false)
  const [refresh, setRefresh] = useState(0)
  const [page, setPage] = useState(1)
  const pageCount = Math.max(1, Math.ceil(rows.length / 10))
  const pageRows = rows.slice((page - 1) * 10, page * 10)

  useEffect(() => {
    let alive = true
    setLoading(true)
    fetchJsonWithAuth(`/api/catalog/${encodeURIComponent(globalProductId)}/retailer-codes`)
      .then(async response => {
        const data = await response.json().catch(() => ({}))
        if (!response.ok) throw new Error(data?.detail || 'Winkelartikelcodes konden niet worden geladen.')
        if (alive) { setRows(Array.isArray(data.items) ? data.items : []); setPage(1) }
      })
      .catch(error => {
        if (alive) showFeedback({ variant: 'error', message: error?.message || 'Ophalen is mislukt.' })
      })
      .finally(() => { if (alive) setLoading(false) })
    return () => { alive = false }
  }, [globalProductId, refresh, showFeedback])

  async function submit() {
    if (!selection || saving) return
    setSaving(true)
    try {
      const response = await fetchJsonWithAuth(
        `/api/catalog/${encodeURIComponent(globalProductId)}/retailer-codes/review`,
        { method: 'POST', headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            link_id: selection.id, expected_product_id: globalProductId,
            retailer_code: selection.retailer_code,
            receipt_text: selection.receipt_text_normalized,
            external_article_code: selection.external_article_code,
            action: targetGtin.trim() ? 'correct' : 'confirm',
            target_gtin: targetGtin.trim() || null,
          }) },
      )
      const data = await response.json().catch(() => ({}))
      if (!response.ok) throw new Error(typeof data?.detail === 'string' ? data.detail : 'De beoordeling is niet verwerkt.')
      showFeedback({ variant: 'success', message: targetGtin.trim() ? 'Correctie bevestigd.' : 'Bestaande productidentiteit gecontroleerd; geen wijziging nodig.' })
      setSelection(null)
      setTargetGtin('')
      setRefresh(v => v + 1)
    } catch (error) {
      showFeedback({ variant: 'error', message: error?.message || 'De beoordeling is niet verwerkt.' })
    } finally {
      setSaving(false)
    }
  }

  return (
    <section aria-label="Winkelartikelcodes beoordelen" data-testid="catalog-retailer-code-review">
      <h3>Winkelartikelcodes</h3>
      <p>Een winkel mag meerdere bonartikelnummers voor dezelfde omschrijving gebruiken.
        De combinatie van winkel, kassabonomschrijving en bonartikelnummer hoort bij maximaal één Artikel-/barcode.
        Kies geen product op basis van alleen de naam.</p>
      {loading ? <p>Winkelartikelcodes laden…</p> : null}
      {!loading && rows.length === 0 ? <p>Geen actieve winkelartikelcodes vastgelegd voor dit Catalogusproduct.</p> : null}
      {rows.length ? <Table dataTestId="catalog-retailer-code-table" tableClassName="rz-catalog-detail-table">
          <thead><tr><th>Winkel</th><th>Kassabonomschrijving</th><th>Bonartikelnummer</th><th>Artikel-/barcode</th><th>Status</th>{canEdit ? <th>Actie</th> : null}</tr></thead>
          <tbody>{pageRows.map(row => <tr key={row.id}>
            <td>{row.retailer_code}</td>
            <td>{row.receipt_text_normalized || 'Ontbreekt'}</td>
            <td>{row.external_article_code || 'Ontbreekt'}</td>
            <td>{row.primary_gtin || 'Geen barcode'}</td>
            <td>{row.status === 'confirmed' ? 'Gekoppeld' : 'Classificatie ontbreekt'}</td>
            {canEdit ? <td>{row.receipt_text_normalized && row.external_article_code
              ? <Button type="button" variant="secondary" onClick={() => { setSelection(row); setTargetGtin('') }}>Beoordelen</Button>
              : <span>Bronomschrijving en bonartikelnummer vereist</span>}</td> : null}
          </tr>)}</tbody>
        </Table> : null}
      {rows.length > 10 ? <Pagination page={page} pageCount={pageCount} onPageChange={setPage} /> : null}
      {selection ? <div className="rz-modal-backdrop">
        <div className="rz-modal-card" role="dialog" aria-modal="true" aria-label="Winkelartikelcode beoordelen">
          <h3>Winkelartikelcode beoordelen</h3>
          <p>Winkel: {selection.retailer_code}</p>
          <p>Omschrijving: {selection.receipt_text_normalized}</p>
          <p>Bonartikelnummer: {selection.external_article_code}</p>
          <p>Huidige Artikel-/barcode: {selection.primary_gtin || 'Geen barcode'}</p>
          <label>Andere bevestigde Artikel-/barcode (alleen bij een correctie)
            <input className="rz-input" inputMode="numeric" value={targetGtin}
              onChange={event => setTargetGtin(event.target.value)} />
          </label>
          <p>Een correctie wordt geblokkeerd als bestaande koppelingen of de voorraadidentiteit in gevaar komen.</p>
          <div className="rz-modal-actions">
            <Button type="button" variant="secondary" onClick={() => { setSelection(null); setTargetGtin('') }} disabled={saving}>Annuleren</Button>
            <Button type="button" onClick={submit} disabled={saving}>
              {saving ? 'Controleren…' : targetGtin.trim() ? 'Correctie controleren' : 'Bevestigen'}
            </Button>
          </div>
        </div>
      </div> : null}
    </section>
  )
}
