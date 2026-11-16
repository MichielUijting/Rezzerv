import { useCallback, useMemo, useState } from 'react'
import Button from '../../ui/Button'
import DataTable from '../../ui/DataTable'
import { useAppFeedback } from '../../ui/AppFeedbackProvider.jsx'
import { fetchJsonWithAuth, canCurrentUserPerform, readStoredAuthContext } from '../../lib/authSession'

const LIMIT = 100

function changesFor(row) {
  return [row.gpc_change, row.cbs_change].filter(Boolean).length
}

const columns = [
  { key: 'select', width: 176 },
  { key: 'name', label: 'Artikel', width: 230, sortable: true, filterable: true },
  { key: 'current_gpc', label: 'GS1 bestaand', width: 130, filterable: true },
  { key: 'gpc_change', label: 'GS1 voorgesteld', width: 270 },
  { key: 'current_cbs', label: 'CBS bestaand', width: 130, filterable: true },
  { key: 'cbs_change', label: 'CBS voorgesteld', width: 270 },
  { key: 'problem', label: 'Controle', width: 200 },
]

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
  const [selectedRows, setSelectedRows] = useState({})
  const [processed, setProcessed] = useState({})
  const [filter, setFilter] = useState('all')
  const [search, setSearch] = useState('')
  const [filteredTableRows, setFilteredTableRows] = useState([])
  const [busy, setBusy] = useState(false)
  const [exportBusy, setExportBusy] = useState(false)

  const rows = useMemo(() => {
    const needle = search.trim().toLowerCase()
    return (preview?.rows || []).filter((row) => {
      if (processed[row.product_id]) return false
      if (needle && ![row.name, row.brand, row.product_id, row.current_gpc,
        row.current_cbs, row.gpc_change?.code, row.cbs_change?.code,
        row.gpc_change?.label, row.cbs_change?.label]
        .some((value) => String(value || '').toLowerCase().includes(needle))) return false
      if (filter === 'new') return Boolean(
        (!row.current_gpc && row.gpc_change) || (!row.current_cbs && row.cbs_change))
      if (filter === 'different') return Boolean(
        (row.current_gpc && row.gpc_change) || (row.current_cbs && row.cbs_change))
      if (filter === 'problems') return Boolean(row.problem)
      return true
    })
  }, [preview, search, filter, processed])

  const selected = useMemo(() =>
    (preview?.rows || []).filter((row) => selectedRows[row.product_id] && !processed[row.product_id]),
  [preview, selectedRows, processed])
  const selectedCodes = selected.reduce((count, row) => count + changesFor(row), 0)
  const canSelect = useCallback((row) => Boolean(canConfirm && !busy && !row.problem &&
    changesFor(row) && (!row.gpc_change || canGpc) && !processed[row.product_id]),
  [canConfirm, busy, canGpc, processed])

  // DataTable is the single authority for its filters/sorting. This callback
  // receives ALL rows passing those filters, not just the active page.
  const onFilteredRowsChange = useCallback((items) => {
    setFilteredTableRows((previous) => {
      const currentIds = previous.map((row) => row.product_id).join('|')
      const nextIds = items.map((row) => row.product_id).join('|')
      return currentIds === nextIds ? previous : items
    })
  }, [])
  const selectableTableRows = filteredTableRows.filter(canSelect)
  const allTableSelected = Boolean(selectableTableRows.length &&
    selectableTableRows.every((row) => selectedRows[row.product_id]))

  const toggleAllTableRows = useCallback(() => {
    if (!selectableTableRows.length) return
    const next = { ...selectedRows }
    if (allTableSelected) {
      for (const row of selectableTableRows) delete next[row.product_id]
    } else {
      for (const row of selectableTableRows) next[row.product_id] = true
    }
    setSelectedRows(next)
    const count = (preview?.rows || []).reduce((sum, row) =>
      sum + (next[row.product_id] ? changesFor(row) : 0), 0)
    if (count > LIMIT) {
      showFeedback({ variant: 'warning',
        message: `${count} codes geselecteerd. Er kunnen maximaal ${LIMIT} codes per verwerking worden verwerkt. Beperk je selectie met de filters of vink rijen uit.` })
    }
  }, [allTableSelected, selectableTableRows, selectedRows, preview, showFeedback])

  const tableColumns = useMemo(() => [
    { ...columns[0], renderFilter: () => <label className="rz-classification-import-select-all">
      <input type="checkbox" aria-label="Alle rijen in de tabel"
        checked={allTableSelected} disabled={busy || !selectableTableRows.length}
        onChange={toggleAllTableRows} />
      <span>Alle rijen in de tabel</span>
    </label> },
    ...columns.slice(1),
  ], [allTableSelected, busy, selectableTableRows.length, toggleAllTableRows])

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
    setSelectedRows({})
    setProcessed({})
    setFilteredTableRows([])
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

  function toggleRow(row) {
    if (!canSelect(row)) return
    const isSelected = Boolean(selectedRows[row.product_id])
    setSelectedRows((previous) => {
      const next = { ...previous }
      if (next[row.product_id]) delete next[row.product_id]
      else next[row.product_id] = true
      return next
    })
  }

  function buildDecisions() {
    const decisions = []
    for (const row of selected) {
      if (!canSelect(row)) throw new Error('Een geselecteerd artikel is niet meer verwerkbaar. Controleer het bestand opnieuw.')
      for (const [system, change] of [['gpc', row.gpc_change], ['cbs', row.cbs_change]]) {
        if (!change) continue
        const existing = system === 'gpc' ? row.current_gpc : row.current_cbs
        decisions.push({
          product_id: row.product_id, expected_name: row.name,
          expected_sha256: row.snapshot_sha256,
          system, code: change.code, reference_version: change.reference_version || '',
          approved: true, allow_replace: Boolean(existing && existing !== change.code),
        })
      }
    }
    if (!decisions.length || decisions.length > LIMIT) {
      throw new Error('Selecteer rijen met in totaal 1 tot en met 100 classificaties.')
    }
    return decisions
  }

  async function commit() {
    if (busy) return false
    let decisions
    try { decisions = buildDecisions() } catch (error) {
      showFeedback({ variant: 'error', message: error.message })
      return false
    }
    setBusy(true)
    try {
      const response = await fetchJsonWithAuth('/api/cbs-classifications/classification-import/confirm', {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ decisions }),
      })
      if (!response.ok) throw new Error(await parseError(response, 'Classificaties konden niet veilig worden bevestigd.'))
      const result = await response.json()
      setProcessed((previous) => ({ ...previous,
        ...Object.fromEntries(decisions.map((decision) => [decision.product_id, true])) }))
      setSelectedRows({})
      onApplied()
      showFeedback({ variant: 'success',
        message: `${result.updated_gpc} GS1- en ${result.updated_cbs} CBS-classificaties opgeslagen. ${result.unchanged} waren al gelijk. De overige artikelen zijn ongewijzigd.` })
      return true
    } catch (error) {
      showFeedback({ variant: 'error', message: error.message || 'Classificaties zijn niet opgeslagen.' })
      return false
    } finally {
      setBusy(false)
    }
  }

  function approveSelection() {
    if (!selected.length || !selectedCodes || selectedCodes > LIMIT || busy) return
    const changes = { newGpc: 0, replaceGpc: 0, newCbs: 0, replaceCbs: 0 }
    for (const row of selected) {
      if (row.gpc_change) changes[row.current_gpc ? 'replaceGpc' : 'newGpc'] += 1
      if (row.cbs_change) changes[row.current_cbs ? 'replaceCbs' : 'newCbs'] += 1
    }
    showFeedback({
      variant: 'warning',
      title: 'Geselecteerde classificaties verwerken?',
      message: `${selected.length} artikelen, ${selectedCodes} classificaties: ${changes.newGpc} GS1 nieuw, ${changes.replaceGpc} GS1 vervangen, ${changes.newCbs} CBS nieuw, ${changes.replaceCbs} CBS vervangen. De bestaande codes van geselecteerde artikelen worden alleen vervangen na deze expliciete bevestiging. De hele batch wordt samen opgeslagen.`,
      primaryActionLabel: 'Goedkeuren en verwerken',
      secondaryActionLabel: 'Annuleren',
      onPrimaryAction: commit,
      onSecondaryAction: () => {},
    })
  }

  function proposedCell(row, system) {
    const choice = system === 'gpc' ? row.gpc_change : row.cbs_change
    const existing = system === 'gpc' ? row.current_gpc : row.current_cbs
    const invalid = system === 'gpc' ? row.invalid_gpc : row.invalid_cbs
    if (!choice) {
      const alternatives = system === 'gpc' ? row.gpc_options : row.cbs_options
      if (invalid?.length) return <span>Niet-officiële code: {invalid.join(', ')}</span>
      if (alternatives?.length > 1) return <span>Meerdere alternatieven: {alternatives.map((option) => option.code).join(', ')}</span>
      return <span>—</span>
    }
    const status = system === 'gpc' ? row.gpc_status : row.cbs_status
    const reason = system === 'gpc' ? row.gpc_reason : row.cbs_reason
    return <div className="rz-classification-import-proposal">
      <strong>{choice.code} · {choice.label}</strong>
      <small>{existing ? 'Anders dan bestaand' : 'Nieuw'}{status ? ' · ' + status : ''}</small>
      {reason ? <small>{reason}</small> : null}
    </div>
  }

  return <section className="rz-classification-import-panel" aria-label="Catalogus exporteren en classificaties importeren"
    data-testid="classification-import-panel">
    <h3>Classificaties importeren en exporteren</h3>
    <p>Alleen nieuwe of afwijkende officiële GS1- en CBS-codes worden getoond. Selecteer de artikelen die je wilt verwerken en bevestig alle toevoegingen en vervangingen gezamenlijk.</p>
    <div className="rz-classification-import-actions">
      {canView ? <Button type="button" variant="secondary" onClick={exportCatalog}
        disabled={exportBusy} data-testid="classification-catalog-export">Catalogus exporteren</Button> : null}
      {canView ? <label>
        Classificatiebestand
        <input type="file" accept=".xlsx,.csv" data-testid="classification-file"
          onChange={(event) => { setFile(event.target.files?.[0] || null); setPreview(null); setSelectedRows({}); setProcessed({}); setFilteredTableRows([]) }} />
      </label> : null}
      {canView ? <Button type="button" variant="secondary" disabled={!file || busy}
        onClick={inspectFile} data-testid="classification-import-preview">Import controleren</Button> : null}
    </div>
    {preview ? <>
      <p role="status" data-testid="classification-import-summary">
        {preview.total} artikelen gecontroleerd · {preview.unchanged} gelijke overgeslagen · {preview.changed_count} met nieuwe of afwijkende codes · {preview.blocked} blokkades.
        GPC: {preview.gpc_new} nieuw, {preview.gpc_replace} anders. CBS: {preview.cbs_new} nieuw, {preview.cbs_replace} anders.
      </p>
      <div className="rz-classification-import-actions">
        <label>Zoeken <input value={search} onChange={(event) => setSearch(event.target.value)} /></label>
        <label>Weergave <select value={filter} onChange={(event) => setFilter(event.target.value)}>
          <option value="all">Nieuw en afwijkend</option>
          <option value="new">Nieuwe classificaties</option>
          <option value="different">Afwijkend van bestaande</option>
          <option value="problems">Blokkades</option>
        </select></label>
        <span>{selected.length} rijen geselecteerd · {selectedCodes} codes (maximaal {LIMIT} per verwerking)</span>
      </div>
      <DataTable dataTestId="classification-import-table" columns={tableColumns} data={rows}
        getRowKey={(row) => row.product_id} pageSize={8} onFilteredRowsChange={onFilteredRowsChange}
        emptyMessage="Geen nieuwe of afwijkende classificaties gevonden."
        paginationActions={<>
          <Button type="button" variant="secondary" onClick={() => setSelectedRows({})}
            disabled={busy || !selected.length}>Selectie wissen</Button>
          <Button type="button" onClick={approveSelection}
            disabled={busy || !selected.length || selectedCodes > LIMIT}
            data-testid="classification-import-confirm">Geselecteerde rijen verwerken ({selected.length})</Button>
        </>}
        renderRow={(row) => <tr key={row.product_id} aria-selected={Boolean(selectedRows[row.product_id])}>
          <td><input type="checkbox" aria-label={`Selecteer ${row.name}`}
            checked={Boolean(selectedRows[row.product_id])}
            disabled={!canSelect(row)} onChange={() => toggleRow(row)} /></td>
          <td>{row.name}{row.brand ? ' · ' + row.brand : ''}</td>
          <td>{row.gpc_change ? row.current_gpc || '—' : '—'}</td>
          <td>{proposedCell(row, 'gpc')}</td>
          <td>{row.cbs_change ? row.current_cbs || '—' : '—'}</td>
          <td>{proposedCell(row, 'cbs')}</td>
          <td>{row.problem || (row.review_existing && row.gpc_change ? 'Bestaande GS1 controleren' : 'Klaar voor beoordeling')}</td>
        </tr>} />
    </> : null}
  </section>
}
