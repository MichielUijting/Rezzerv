import { useMemo, useState } from 'react'
import Button from '../../ui/Button'
import DataTable from '../../ui/DataTable'
import { useAppFeedback } from '../../ui/AppFeedbackProvider.jsx'
import { fetchJsonWithAuth, canCurrentUserPerform, readStoredAuthContext } from '../../lib/authSession'

const LIMIT = 100

function selectionKey(row, system) { return row.product_id + ':' + system }

async function parseError(response, fallback) {
  const data = await response.json().catch(() => ({}))
  return String(data?.detail || fallback)
}

export default function ClassificationImportPanel({ onApplied = () => {} }) {
  const { showFeedback } = useAppFeedback()
  const session = readStoredAuthContext()
  const canView = Boolean((session?.is_platform_superuser || session?.is_frontteam)
    && canCurrentUserPerform('platform.external_products.view', session))
  const canConfirm = canCurrentUserPerform('platform.external_products.link_existing', session)
  const canGpc = canCurrentUserPerform('platform.gpc.update', session)
  const [file, setFile] = useState(null)
  const [preview, setPreview] = useState(null)
  const [selection, setSelection] = useState({})
  const [overrides, setOverrides] = useState({})
  const [processed, setProcessed] = useState({})
  const [filter, setFilter] = useState('all')
  const [search, setSearch] = useState('')
  const [busy, setBusy] = useState(false)
  const [exportBusy, setExportBusy] = useState(false)

  const selected = useMemo(() => Object.entries(selection).filter(([, choice]) => Boolean(choice)), [selection])
  const rows = useMemo(() => {
    const needle = search.trim().toLowerCase()
    return (preview?.rows || []).filter((row) => {
      if (needle && ![row.name, row.brand, row.product_id, row.current_gpc, row.current_cbs]
        .some((value) => String(value || '').toLowerCase().includes(needle))) return false
      if (filter === 'review') return row.review_existing
      if (filter === 'proposals') return Boolean(row.gpc_options.length || row.cbs_options.length)
      if (filter === 'problems') return Boolean(row.problem || row.invalid_gpc.length || row.invalid_cbs.length)
      return true
    })
  }, [preview, search, filter])

  async function exportCatalog() {
    if (exportBusy) return
    setExportBusy(true)
    showFeedback({ variant: 'progress', message: 'De Catalogus wordt geëxporteerd...' })
    try {
      const response = await fetchJsonWithAuth('/api/cbs-classifications/catalog-export')
      if (!response.ok || !String(response.headers.get('content-type') || '').includes('application/zip')) {
        throw new Error(await parseError(response, 'De Catalogusexport is niet beschikbaar.'))
      }
      const blob = await response.blob()
      if (!blob.size) throw new Error('De Catalogusexport is leeg.')
      const url = URL.createObjectURL(blob)
      const anchor = document.createElement('a')
      anchor.href = url
      anchor.download = 'Inhuis_Catalogus_Classificatie.zip'
      document.body.appendChild(anchor)
      try { anchor.click() } finally { anchor.remove(); window.setTimeout(() => URL.revokeObjectURL(url), 1000) }
      showFeedback({ variant: 'success', message: 'De volledige Catalogus is geëxporteerd.' })
    } catch (error) {
      showFeedback({ variant: 'error', message: error.message || 'Catalogus kon niet worden geëxporteerd.' })
    } finally {
      setExportBusy(false)
    }
  }

  async function inspectFile() {
    if (!file || busy) return
    setBusy(true)
    setPreview(null)
    setSelection({})
    setOverrides({})
    setProcessed({})
    showFeedback({ variant: 'progress', message: 'Voorstellen worden gelezen en met de actuele Catalogus gecontroleerd...' })
    try {
      const response = await fetchJsonWithAuth('/api/cbs-classifications/classification-import/preview', {
        method: 'POST',
        headers: {
          'Content-Type': file.name.toLowerCase().endsWith('.csv') ? 'text/csv' : 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
          'X-Inhuis-Filename': encodeURIComponent(file.name),
        },
        body: file,
      })
      if (!response.ok) throw new Error(await parseError(response, 'Het classificatiebestand kon niet worden gecontroleerd.'))
      const result = await response.json()
      if (!Array.isArray(result.rows)) throw new Error('Ongeldige importvoorvertoning.')
      setPreview(result)
      showFeedback({ variant: result.blocked ? 'warning' : 'success',
        message: `${result.total} Catalogusartikelen gecontroleerd. ${result.blocked} artikelen hebben een blokkade. Er is nog niets opgeslagen.` })
    } catch (error) {
      showFeedback({ variant: 'error', message: error.message || 'Importcontrole is mislukt.' })
    } finally {
      setBusy(false)
    }
  }

  function setChoice(row, system, code) {
    const key = selectionKey(row, system)
    const options = system === 'gpc' ? row.gpc_options : row.cbs_options
    const option = options.find((item) => item.code === code)
    if (row.problem || (system === 'gpc' && !canGpc) || !canConfirm || processed[key]) return
    setSelection((previous) => ({ ...previous, [key]: option || null }))
    setOverrides((previous) => ({ ...previous, [key]: false }))
  }

  function selectHigh() {
    const choices = {}
    let count = 0
    for (const row of preview?.rows || []) {
      if (row.problem || row.invalid_gpc.length || row.invalid_cbs.length) continue
      const productChoices = []
      for (const system of ['gpc', 'cbs']) {
        if (system === 'gpc' && !canGpc) continue
        if (!canConfirm || processed[selectionKey(row, system)]) continue
        const status = system === 'gpc' ? row.gpc_status : row.cbs_status
        const current = system === 'gpc' ? row.current_gpc : row.current_cbs
        const candidate = (system === 'gpc' ? row.gpc_options : row.cbs_options)
          .find((option) => option.kind === 'voorstel')
        if (status === 'Voorstel hoog' && !current && candidate) {
          productChoices.push([selectionKey(row, system), candidate])
        }
      }
      // Never split GS1 and CBS for one product across separate batches:
      // that would invalidate the export fingerprint after the first write.
      if (count + productChoices.length > LIMIT) continue
      for (const [key, candidate] of productChoices) choices[key] = candidate
      count += productChoices.length
      if (count === LIMIT) break
    }
    setSelection(choices)
    setOverrides({})
    showFeedback({ variant: 'info', message: `${count} hoge voorstellen zonder bestaande classificatie geselecteerd. Controleer de keuzes vóór goedkeuring.` })
  }

  async function commit() {
    if (busy) return false
    const decisions = []
    for (const row of preview?.rows || []) {
      for (const system of ['gpc', 'cbs']) {
        const key = selectionKey(row, system)
        const choice = selection[key]
        if (!choice || processed[key]) continue
        const current = system === 'gpc' ? row.current_gpc : row.current_cbs
        if (current && current !== choice.code && !overrides[key]) {
          throw new Error('Bevestig per artikel expliciet dat de bestaande classificatie mag worden vervangen.')
        }
        decisions.push({
          product_id: row.product_id,
          expected_name: row.name,
          expected_sha256: row.snapshot_sha256,
          system,
          code: choice.code,
          reference_version: choice.reference_version || '',
          approved: true,
          allow_replace: Boolean(overrides[key]),
        })
      }
    }
    if (!decisions.length || decisions.length > LIMIT) throw new Error('Kies 1 tot en met 100 codes per verwerking.')
    setBusy(true)
    try {
      const response = await fetchJsonWithAuth('/api/cbs-classifications/classification-import/confirm', {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ decisions }),
      })
      if (!response.ok) throw new Error(await parseError(response, 'Classificaties konden niet veilig worden bevestigd.'))
      const result = await response.json()
      setProcessed((previous) => ({ ...previous, ...Object.fromEntries(decisions.map((d) => [d.product_id + ':' + d.system, true])) }))
      setSelection({})
      setOverrides({})
      onApplied()
      showFeedback({ variant: 'success', message: `${result.updated_gpc} GS1- en ${result.updated_cbs} CBS-classificaties opgeslagen. ${result.unchanged} waren al gelijk. Andere artikelen zijn ongewijzigd.` })
      return true
    } catch (error) {
      showFeedback({ variant: 'error', message: error.message || 'Classificaties zijn niet opgeslagen.' })
      return false
    } finally {
      setBusy(false)
    }
  }

  function approveSelection() {
    if (!selected.length || selected.length > LIMIT || busy) return
    const replacements = (preview?.rows || []).flatMap((row) =>
      ['gpc', 'cbs'].filter((system) => {
        const choice = selection[selectionKey(row, system)]
        return choice && (system === 'gpc' ? row.current_gpc : row.current_cbs)
          && choice.code !== (system === 'gpc' ? row.current_gpc : row.current_cbs)
      }))
    showFeedback({
      variant: 'warning',
      title: 'Classificaties definitief verwerken?',
      message: `${selected.length} expliciet geselecteerde classificaties. Daarvan vervangen ${replacements.length} een bestaande classificatie. De hele batch wordt in één transactie opgeslagen.`,
      primaryActionLabel: 'Goedkeuren en verwerken',
      secondaryActionLabel: 'Annuleren',
      onPrimaryAction: commit,
      onSecondaryAction: () => {},
    })
  }

  function selector(row, system) {
    const key = selectionKey(row, system)
    const current = system === 'gpc' ? row.current_gpc : row.current_cbs
    const options = system === 'gpc' ? row.gpc_options : row.cbs_options
    const picked = selection[key]
    const disabled = busy || row.problem || !canConfirm || (system === 'gpc' && !canGpc) || processed[key]
    return <div className="rz-classification-import-choice">
      <select aria-label={system.toUpperCase() + ' voorstel ' + row.name}
        value={picked?.code || ''} disabled={Boolean(disabled)}
        onChange={(event) => setChoice(row, system, event.target.value)}>
        <option value="">Niet verwerken</option>
        {options.map((option) => <option key={option.code} value={option.code}>
          {option.code} · {option.label} {option.kind === 'bestaand controleren' ? '(controle)' : ''}
        </option>)}
      </select>
      <small className="rz-classification-import-explanation">
        {system === 'gpc' ? row.gpc_status : row.cbs_status}
        {(system === 'gpc' ? row.gpc_reason : row.cbs_reason)
          ? ' · ' + (system === 'gpc' ? row.gpc_reason : row.cbs_reason) : ''}
      </small>
      {picked && current && picked.code !== current ? <label>
        <input type="checkbox" checked={Boolean(overrides[key])} disabled={Boolean(disabled)}
          onChange={(event) => setOverrides((previous) => ({ ...previous, [key]: event.target.checked }))} />
        Bestaande code vervangen
      </label> : null}
      {processed[key] ? <span>Verwerkt</span> : null}
    </div>
  }

  const columns = [
    { key: 'name', label: 'Artikel', width: 240, sortable: true, filterable: true },
    { key: 'current_gpc', label: 'GS1 bestaand', width: 130, filterable: true },
    { key: 'gpc_options', label: 'GS1 verwerken', width: 290 },
    { key: 'current_cbs', label: 'CBS bestaand', width: 130, filterable: true },
    { key: 'cbs_options', label: 'CBS verwerken', width: 290 },
    { key: 'problem', label: 'Controle', width: 250, filterable: true,
      getFilterValue: (row) => [row.problem, row.gpc_status, row.cbs_status].join(' ') },
  ]

  return <section className="rz-classification-import-panel" aria-label="Catalogus exporteren en classificaties importeren"
    data-testid="classification-import-panel">
    <h3>Classificaties importeren en exporteren</h3>
    <p>Importeer de Excel uit ChatGPT of de bijbehorende CSV. Voorstellen zijn niet automatisch bewezen: kies zelf welke officiële codes mogen worden toegepast. Bestaande classificaties worden niet zonder aparte toestemming vervangen.</p>
    <div className="rz-classification-import-actions">
      {canView ? <Button type="button" variant="secondary" onClick={exportCatalog}
        disabled={exportBusy} data-testid="classification-catalog-export">Catalogus exporteren</Button> : null}
      {canView ? <label>
        Classificatiebestand
        <input type="file" accept=".xlsx,.csv" data-testid="classification-file"
          onChange={(event) => { setFile(event.target.files?.[0] || null); setPreview(null); setSelection({}); setProcessed({}) }} />
      </label> : null}
      {canView ? <Button type="button" variant="secondary" disabled={!file || busy}
        onClick={inspectFile} data-testid="classification-import-preview">Import controleren</Button> : null}
    </div>
    {preview ? <>
      <p role="status" data-testid="classification-import-summary">
        {preview.total} artikelen · {preview.review_existing} bestaande classificaties ter controle · {preview.blocked} blokkades · {selected.length} geselecteerde codes. Maximaal {LIMIT} per verwerking.
      </p>
      <div className="rz-classification-import-actions">
        <label>Zoeken <input value={search} onChange={(e) => setSearch(e.target.value)} /></label>
        <label>Weergave <select value={filter} onChange={(e) => setFilter(e.target.value)}>
          <option value="all">Alle artikelen</option>
          <option value="proposals">Met voorstellen</option>
          <option value="review">Bestaand controleren</option>
          <option value="problems">Blokkades</option>
        </select></label>
        <Button type="button" variant="secondary" onClick={selectHigh} disabled={!canConfirm || busy}>
          Selecteer 100 hoge voorstellen
        </Button>
        <Button type="button" variant="secondary" onClick={() => { setSelection({}); setOverrides({}) }} disabled={busy}>
          Selectie wissen
        </Button>
        <Button type="button" onClick={approveSelection} disabled={busy || !canConfirm || !selected.length || selected.length > LIMIT}
          data-testid="classification-import-confirm">Goedkeuren ({selected.length})</Button>
      </div>
      <DataTable dataTestId="classification-import-table" columns={columns} data={rows}
        getRowKey={(row) => row.product_id} pageSize={8}
        emptyMessage="Geen artikelen gevonden."
        renderRow={(row) => <tr key={row.product_id}>
          <td>{row.name}{row.brand ? ' · ' + row.brand : ''}</td>
          <td>{row.current_gpc || '—'}</td>
          <td>{selector(row, 'gpc')}</td>
          <td>{row.current_cbs || '—'}</td>
          <td>{selector(row, 'cbs')}</td>
          <td>{row.problem || (row.invalid_gpc.length || row.invalid_cbs.length
            ? 'Niet-officiële voorstelcode: ' + [...row.invalid_gpc, ...row.invalid_cbs].join(', ')
            : row.review_existing ? 'Bestaande GS1 controleren'
              : row.gpc_status + ' / ' + row.cbs_status)}</td>
        </tr>} />
    </> : null}
  </section>
}
