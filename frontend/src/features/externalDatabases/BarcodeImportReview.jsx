import { useEffect, useRef, useState } from 'react'
import { createPortal } from 'react-dom'
import Button from '../../ui/Button'
import DataTable from '../../ui/DataTable'
import { fetchJsonWithAuth } from '../../lib/authSession'
import { useAppFeedback } from '../../ui/AppFeedbackProvider.jsx'

const columns = [
  { key: 'article', label: 'Artikel', sortable: true, filterable: true },
  { key: 'retailer', label: 'Winkelketen', sortable: true, filterable: true },
  { key: 'article_number', label: 'Bonartikelnummer' },
  { key: 'gtin', label: 'Barcode' },
  { key: 'product_name', label: 'Gevonden product' },
  { key: 'status', label: 'Status' },
  { key: 'decision', label: 'Beoordelen' },
]

async function readResponse(response) {
  const result = await response.json()
  if (!response.ok) throw new Error(typeof result.detail === 'string' ? result.detail : 'De import kon niet worden verwerkt.')
  return result
}

export default function BarcodeImportReview({ onClose, onApplied }) {
  const { showFeedback } = useAppFeedback()
  const [preview, setPreview] = useState(null)
  const [decisions, setDecisions] = useState({})
  const [busy, setBusy] = useState(false)
  const [workingLine, setWorkingLine] = useState(null)
  const [error, setError] = useState('')
  const fileInputRef = useRef(null)
  useEffect(() => {
    fileInputRef.current?.focus()
  }, [])
  useEffect(() => {
    const onKeyDown = (event) => {
      if (event.key === 'Escape' && !busy && workingLine === null) onClose()
    }
    window.addEventListener('keydown', onKeyDown)
    return () => window.removeEventListener('keydown', onKeyDown)
  }, [busy, workingLine, onClose])

  async function loadFile(event) {
    const file = event.target.files?.[0]
    setPreview(null)
    setDecisions({})
    setError('')
    if (!file) return
    if (!file.name.toLowerCase().endsWith('.csv') || file.size > 2000000) {
      setError('Kies in Downloads het bestand inhuis-artikel-classificeren-artikelen_aangevuld.csv (maximaal 2 MB).')
      return
    }
    setBusy(true)
    try {
      const csv_text = await file.text()
      const response = await fetchJsonWithAuth('/api/catalog/ed2/barcode-import/preview', {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ csv_text }),
      })
      setPreview(await readResponse(response))
    } catch (err) {
      setError(err.message)
    } finally {
      setBusy(false)
    }
  }

  async function decide(row, decision) {
    if (decisions[row.line] || workingLine !== null) return
    if (decision === 'afgewezen') {
      setDecisions((current) => ({ ...current, [row.line]: decision }))
      return
    }
    setWorkingLine(row.line)
    setError('')
    try {
      const response = await fetchJsonWithAuth('/api/catalog/ed2/barcode-import/approve', {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          receipt_item_id: row.receipt_item_id, retailer: row.retailer,
          article: row.article, article_number: row.article_number, gtin: row.gtin,
        }),
      })
      const outcome = await readResponse(response)
      if (!outcome.saved) throw new Error('De barcode is niet opgeslagen.')
      setDecisions((current) => ({ ...current, [row.line]: 'goedgekeurd' }))
      onApplied()
      showFeedback({ variant: 'success', message: `Barcode voor ${row.article} opgeslagen.` })
    } catch (err) {
      setError(`Regel ${row.line}: ${err.message}`)
    } finally {
      setWorkingLine(null)
    }
  }

  const items = (preview?.items || []).map((row) => ({
    ...row,
    status: decisions[row.line] || (row.status === 'klaar' ? 'Te beoordelen' : row.reason),
  }))
  const approved = Object.values(decisions).filter((value) => value === 'goedgekeurd').length
  const rejected = Object.values(decisions).filter((value) => value === 'afgewezen').length

  return createPortal(<div className="rz-modal-backdrop rz-classification-overlay-backdrop rz-barcode-import-backdrop"
    onMouseDown={(event) => {
      if (event.target === event.currentTarget && !busy && workingLine === null) onClose()
    }}>
    <section aria-label="Barcodes importeren" role="dialog" aria-modal="true"
      className="rz-classification-search-overlay rz-barcode-import-dialog" data-testid="barcode-import-dialog">
      <div className="rz-classification-overlay-heading">
        <h3>Barcodes importeren</h3>
        <button type="button" className="rz-barcode-import-dismiss" aria-label="Importvenster sluiten"
          title="Venster sluiten" disabled={busy || workingLine !== null} onClick={onClose}>×</button>
      </div>
      <p>Selecteer <strong>inhuis-artikel-classificeren-artikelen_aangevuld.csv</strong>.
        Het oorspronkelijke bestand dat eindigt op <strong>_input.csv</strong> bevat geen nieuwe voorstellen.
        Alleen regels met <strong>Aangevuld: officieel artikelnummer</strong> worden voorgesteld.
        Beoordeel elk artikel afzonderlijk; pas bij Goedkeuren wordt een barcode opgeslagen.</p>
      <label className="rz-input-field"><span className="rz-label">CSV-bestand</span>
        <input ref={fileInputRef} className="rz-input" type="file" accept=".csv,text/csv"
          onChange={loadFile} disabled={busy || workingLine !== null} />
      </label>
    {busy ? <p role="status">Bestand controleren...</p> : null}
    {error ? <p role="alert">{error}</p> : null}
    {preview ? <>
      <p role="status">Regels: {preview.total} · Ter beoordeling: {preview.ready} ·
        Geblokkeerd: {preview.blocked} · Overgeslagen: {preview.skipped} ·
        Goedgekeurd: {approved} · Afgewezen: {rejected}</p>
      <DataTable data={items} columns={columns} getRowKey={(row) => row.line}
        dataTestId="barcode-import-review-table"
        defaultSort={{ key: 'article', direction: 'asc' }}
        renderRow={(row) => <tr key={row.line}>
          <td>{row.article}</td><td>{row.retailer}</td><td>{row.article_number}</td>
          <td>{row.gtin}</td><td title={row.source}>{row.product_name || row.source}</td>
          <td>{row.status}</td>
          <td>{row.reason ? 'Niet beschikbaar' : decisions[row.line] || <>
            <Button type="button" disabled={workingLine !== null}
              onClick={() => decide(row, 'goedgekeurd')}>Goedkeuren</Button>{' '}
            <Button type="button" variant="secondary" disabled={workingLine !== null}
              onClick={() => decide(row, 'afgewezen')}>Afwijzen</Button>
          </>}</td>
        </tr>} />
    </> : null}
    </section>
  </div>, document.body)
}
