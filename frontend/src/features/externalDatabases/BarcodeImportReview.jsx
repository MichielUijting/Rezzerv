import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import AppShell from '../../app/AppShell'
import ScreenCard from '../../ui/ScreenCard'
import DataTable from '../../ui/DataTable'
import Button from '../../ui/Button'
import { fetchJsonWithAuth } from '../../lib/authSession'
import { useAppFeedback } from '../../ui/AppFeedbackProvider.jsx'
import './externalDatabases.css'

const columns = [
  { key: 'select', label: '', width: 56 },
  { key: 'article', label: 'Artikel', width: 245, sortable: true, filterable: true },
  { key: 'retailer', label: 'Winkelketen', width: 150, sortable: true, filterable: true },
  { key: 'article_number', label: 'Bonartikelnummer', width: 155, sortable: true, filterable: true },
  { key: 'gtin', label: 'Barcode', width: 155, sortable: true, filterable: true },
  { key: 'product_name', label: 'Gevonden product', width: 235, sortable: true, filterable: true },
  { key: 'status', label: 'Status', width: 235, sortable: true, filterable: true },
]

async function readResponse(response) {
  const result = await response.json()
  if (!response.ok) {
    const detail = result.detail
    const error = new Error(typeof detail === 'string' ? detail
      : detail?.message || 'De import kon niet worden verwerkt.')
    if (detail?.code === 'off_identity_mismatch') error.offMismatch = detail
    throw error
  }
  return result
}

export default function BarcodeImportReview() {
  const { showFeedback } = useAppFeedback()
  const [preview, setPreview] = useState(null)
  const [removed, setRemoved] = useState([])
  const [approved, setApproved] = useState([])
  const [failures, setFailures] = useState({})
  const [foundProducts, setFoundProducts] = useState({})
  const [offNames, setOffNames] = useState({})
  const offLookupPending = useRef(new Set())
  const offLookupGeneration = useRef(0)
  const [selectedIds, setSelectedIds] = useState([])
  const [pageIds, setPageIds] = useState([])
  const [filteredIds, setFilteredIds] = useState([])
  const [filters, setFilters] = useState({})
  const [sort, setSort] = useState({ key: 'article', direction: 'asc' })
  const [page, setPage] = useState(1)
  const [busy, setBusy] = useState(false)

  const onPageRowsChange = useCallback((rows) => {
    const ids = rows.map((row) => row.line)
    setPageIds((previous) => previous.length === ids.length && previous.every((id, i) => id === ids[i]) ? previous : ids)
  }, [])
  const onFilteredRowsChange = useCallback((rows) => {
    const ids = rows.map((row) => row.line)
    setFilteredIds((previous) => previous.length === ids.length && previous.every((id, i) => id === ids[i]) ? previous : ids)
  }, [])

  // Enrich only the visible rows. The CSV never needs a product-name column,
  // and reading OFF must not persist or approve any product information.
  useEffect(() => {
    if (!preview?.items?.length || !pageIds.length) return
    const visible = new Set(pageIds)
    const gtins = [...new Set(preview.items
      .filter((row) => visible.has(row.line) && /^[0-9]{8,14}$/.test(String(row.gtin || '')))
      .map((row) => row.gtin))]
      .filter((gtin) => !Object.prototype.hasOwnProperty.call(offNames, gtin)
        && !offLookupPending.current.has(gtin))
      .slice(0, 10)
    if (!gtins.length) return
    const generation = offLookupGeneration.current
    gtins.forEach((gtin) => offLookupPending.current.add(gtin))
    void (async () => {
      try {
        const response = await fetchJsonWithAuth('/api/catalog/ed2/barcode-import/off-names', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ gtins }),
        })
        const result = await readResponse(response)
        if (offLookupGeneration.current !== generation) return
        setOffNames((current) => {
          const next = { ...current }
          for (const entry of result.items || []) {
            if (gtins.includes(entry.gtin)) next[entry.gtin] = entry
          }
          // Avoid endlessly retrying malformed or missing response entries.
          for (const gtin of gtins) {
            if (!next[gtin]) next[gtin] = { status: 'unavailable', product_name: '' }
          }
          return next
        })
      } catch {
        if (offLookupGeneration.current === generation) {
          setOffNames((current) => Object.fromEntries([
            ...Object.entries(current),
            ...gtins.map((gtin) => [gtin, { status: 'unavailable', product_name: '' }]),
          ]))
        }
      } finally {
        if (offLookupGeneration.current === generation) {
          gtins.forEach((gtin) => offLookupPending.current.delete(gtin))
        }
      }
    })()
  }, [preview, pageIds, offNames])

  function offNameFor(row) {
    const entry = offNames[row.gtin]
    if (entry?.status === 'found') return entry.product_name
    if (foundProducts[row.line]) return foundProducts[row.line]
    if (entry?.status === 'not_found') return 'Niet gevonden in OFF'
    if (entry?.status === 'no_name') return 'Naam ontbreekt in OFF'
    if (entry?.status === 'unavailable') return 'OFF tijdelijk niet bereikbaar'
    return /^[0-9]{8,14}$/.test(String(row.gtin || '')) ? 'OFF opzoeken…' : 'Geen geldige barcode'
  }

  const items = useMemo(() => (preview?.items || [])
    .filter((row) => !removed.includes(row.line))
    .map((row) => ({
      ...row,
      product_name: offNameFor(row),
      status: approved.includes(row.line) ? 'Goedgekeurd'
        : failures[row.line] ? `Niet opgeslagen: ${failures[row.line]}`
          : row.status === 'klaar' ? 'Te beoordelen'
            : row.reason || 'Geblokkeerd',
    })), [preview, removed, approved, failures, foundProducts, offNames])
  // Geblokkeerde voorstellen mogen wel uit de importlijst worden verwijderd,
  // maar kunnen nooit ter goedkeuring worden aangeboden.
  const selectableIds = useMemo(() => new Set(items.filter((row) => (
    row.status !== 'Goedgekeurd'
  )).map((row) => row.line)), [items])
  const selectedRows = useMemo(() => items.filter((row) => (
    selectedIds.includes(row.line) && selectableIds.has(row.line)
  )), [items, selectedIds, selectableIds])
  const selectedCount = selectedRows.length
  const selectedOnPageCount = selectedRows.filter((row) => pageIds.includes(row.line)).length
  const selectedElsewhereCount = selectedCount - selectedOnPageCount
  const canApproveSelection = selectedCount > 0 && selectedRows.every((row) =>
    row.status === 'Te beoordelen' || row.status.startsWith('Niet opgeslagen:'))
  const selectablePageIds = pageIds.filter((id) => selectableIds.has(id))
  const allPageSelected = selectablePageIds.length > 0 && selectablePageIds.every((id) => selectedIds.includes(id))
  const selectableFilteredIds = filteredIds.filter((id) => selectableIds.has(id))
  const allFilteredSelected = selectableFilteredIds.length > 0 && selectableFilteredIds.every((id) => selectedIds.includes(id))

  const tableColumns = useMemo(() => columns.map((column) => column.key === 'select' ? ({
    ...column,
    renderFilter: () => <input type="checkbox" aria-label="Alles op huidige pagina"
      checked={allPageSelected} disabled={busy || !selectablePageIds.length}
      onChange={() => setSelectedIds((current) => allPageSelected
        ? current.filter((id) => !selectablePageIds.includes(id))
        : [...new Set([...current, ...selectablePageIds])])} />,
  }) : column), [allPageSelected, busy, selectablePageIds])

  async function loadFile(event) {
    const file = event.target.files?.[0]
    setPreview(null)
    setRemoved([])
    setApproved([])
    setFailures({})
    setFoundProducts({})
    setOffNames({})
    setPageIds([])
    offLookupGeneration.current += 1
    offLookupPending.current.clear()
    setSelectedIds([])
    setFilters({})
    setPage(1)
    if (!file) return
    if (!file.name.toLowerCase().endsWith('.csv') || file.size > 2000000) {
      showFeedback({ variant: 'error', title: 'Ongeldig importbestand',
        message: 'Kies een CSV-bestand met artikel, winkelketen, bonartikelnummer en Art./Barcode (maximaal 2 MB).' })
      return
    }
    setBusy(true)
    showFeedback({ variant: 'progress', title: 'Barcodes inlezen',
      message: 'Het importbestand wordt gecontroleerd.', dismissMode: 'blocked',
      key: 'barcode-import-loading', dedupeMs: 0 })
    try {
      const response = await fetchJsonWithAuth('/api/catalog/ed2/barcode-import/preview', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ csv_text: await file.text() }),
      })
      const result = await readResponse(response)
      setPreview(result)
      showFeedback({ variant: 'success', title: 'Importbestand ingelezen',
        message: `${result.items.length} barcodevoorstellen ingelezen.`,
        detail: `${result.ready} te beoordelen · ${result.blocked} geblokkeerd · ${result.skipped} overgeslagen.`,
        dedupeMs: 0 })
    } catch (err) {
      showFeedback({ variant: 'error', title: 'Importbestand niet ingelezen',
        message: err.message, dedupeMs: 0 })
    } finally {
      setBusy(false)
    }
  }

  function deleteSelected() {
    if (!selectedCount || busy) return
    const ids = selectedRows.map((row) => row.line)
    showFeedback({
      variant: 'warning',
      title: 'Importvoorstellen verwijderen',
      message: `${ids.length} geselecteerde voorstellen uit deze importlijst verwijderen?`,
      detail: 'Er worden geen artikelen, barcodes of andere gegevens uit de database verwijderd.',
      primaryActionLabel: 'Verwijderen',
      secondaryActionLabel: 'Annuleren',
      testId: 'barcode-import-delete-confirmation',
      onPrimaryAction: () => {
        setRemoved((current) => [...new Set([...current, ...ids])])
        setSelectedIds((current) => current.filter((id) => !ids.includes(id)))
      },
    })
  }

  function offerOffMismatchOverride(rows, index = 0) {
    const row = rows[index]
    if (!row) return
    showFeedback({
      variant: 'warning',
      title: 'OFF-productgegevens wijken af',
      message: 'De OFF-productgegevens komen niet veilig overeen met dit bonartikel.',
      detail: [
        `Bonartikel: ${row.article} (artikelnummer ${row.article_number || 'onbekend'})`,
        `Voorgestelde barcode: ${row.gtin}`,
        `OFF gevonden product: ${row.offProduct?.product_name || 'Naam ontbreekt'}`,
        row.offProduct?.brand ? `Merk: ${row.offProduct.brand}` : '',
        row.offProduct?.quantity ? `Inhoud: ${row.offProduct.quantity}` : '',
        row.offProduct?.conflict_reason ? `Afwijking: ${row.offProduct.conflict_reason}` : '',
        'Bij Toch koppelen wordt alleen de barcode opgeslagen, niet de afwijkende OFF-productgegevens.',
      ].filter(Boolean).join(' · '),
      dismissMode: 'blocked',
      primaryActionLabel: 'Toch koppelen',
      secondaryActionLabel: 'Annuleren',
      testId: 'barcode-import-off-mismatch',
      onPrimaryAction: async () => {
        const response = await fetchJsonWithAuth('/api/catalog/ed2/barcode-import/approve', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            receipt_item_id: row.receipt_item_id, retailer: row.retailer,
            article: row.article, article_number: row.article_number, gtin: row.gtin,
            allow_off_mismatch: true,
          }),
        })
        const result = await readResponse(response)
        if (!result.saved) throw new Error('De barcode is niet opgeslagen.')
        setApproved((current) => [...new Set([...current, row.line])])
        setSelectedIds((current) => current.filter((id) => id !== row.line))
        setFailures((current) => {
          const next = { ...current }
          delete next[row.line]
          return next
        })
        if (index + 1 < rows.length) offerOffMismatchOverride(rows, index + 1)
        else showFeedback({ variant: 'success', title: 'Barcode opgeslagen',
          message: 'De barcode is opgeslagen zonder afwijkende OFF-productgegevens.', dedupeMs: 0 })
      },
      onSecondaryAction: () => {
        if (index + 1 < rows.length) offerOffMismatchOverride(rows, index + 1)
      },
    })
  }

  async function approveSelected(ids) {
    setBusy(true)
    showFeedback({ variant: 'progress', title: 'Barcodes verwerken',
      message: `${ids.length} geselecteerde barcodes worden gecontroleerd en opgeslagen.`,
      dismissMode: 'blocked', key: 'barcode-import-processing', dedupeMs: 0 })
    let succeeded = 0
    let failed = 0
    const mismatches = []
    for (const id of ids) {
      const row = selectedRows.find((item) => item.line === id)
      if (!row) continue
      try {
        const response = await fetchJsonWithAuth('/api/catalog/ed2/barcode-import/approve', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            receipt_item_id: row.receipt_item_id, retailer: row.retailer,
            article: row.article, article_number: row.article_number, gtin: row.gtin,
          }),
        })
        const result = await readResponse(response)
        if (!result.saved) throw new Error('De barcode is niet opgeslagen.')
        setApproved((current) => [...current, id])
        setSelectedIds((current) => current.filter((currentId) => currentId !== id))
        succeeded += 1
      } catch (err) {
        if (err.offMismatch) {
          const detail = err.offMismatch
          if (detail.gtin !== row.gtin) {
            setFailures((current) => ({ ...current, [id]: 'OFF gaf een andere barcode terug.' }))
            failed += 1
            continue
          }
          setFoundProducts((current) => ({ ...current, [id]: detail.product_name || '' }))
          mismatches.push({ ...row, offProduct: detail })
        } else {
          setFailures((current) => ({ ...current, [id]: err.message }))
          failed += 1
        }
      }
    }
    setBusy(false)
    if (mismatches.length) {
      offerOffMismatchOverride(mismatches)
      return
    }
    showFeedback({
      variant: failed ? 'warning' : 'success',
      title: 'Importresultaat',
      message: `${succeeded} barcodes opgeslagen, ${failed} niet opgeslagen.`,
      detail: failed ? 'Mislukte regels blijven in de tabel staan met hun foutmelding.' : '',
    })
  }

  function confirmApproval() {
    if (!canApproveSelection || busy) return
    // The Goedkeuren button itself is the explicit decision. No redundant confirmation.
    const ids = selectedRows.map((row) => row.line)
    void approveSelected(ids)
  }

  return <AppShell title="Barcodes importeren" showExit={false}>
    <ScreenCard fullWidth>
      <div className="rz-barcode-import-page">
        <h2>Barcodes importeren</h2>
        <p>Importeer een CSV met Artikel, Winkelketen, Bonartikelnummer en Art./Barcode. Een kolom Aanvulstatus mag ook.
          Afgeleide codes uit bonartikelnummers worden ter controle getoond maar niet opgeslagen.
          Goedkeuren slaat alleen toegestane geselecteerde barcodes op; Verwijderen verwijdert alleen voorstellen uit deze lijst.</p>
        <label className="rz-input-field">
          <span className="rz-label">CSV-bestand</span>
          <input type="file" className="rz-input" accept=".csv,text/csv"
            onChange={loadFile} disabled={busy} />
        </label>
        {preview ? <>
          <p role="status">Ingelezen: {preview.total} · Overgeslagen: {preview.skipped} ·
            In importlijst: {items.length} · Geblokkeerd: {items.filter((row) => row.status !== 'Te beoordelen'
              && row.status !== 'Goedgekeurd' && !row.status.startsWith('Niet opgeslagen:')).length} ·
            Goedgekeurd: {approved.length}</p>
          <div className="rz-mobile-table-select-row">
            <label><input type="checkbox" aria-label="Alle gefilterde importvoorstellen selecteren"
              checked={allFilteredSelected} disabled={busy || !selectableFilteredIds.length}
              onChange={() => setSelectedIds((current) => allFilteredSelected
                ? current.filter((id) => !selectableFilteredIds.includes(id))
                : [...new Set([...current, ...selectableFilteredIds])])} />
              Alle artikelen op alle pagina’s</label>
          </div>
          <DataTable
            columns={tableColumns}
            data={items}
            getRowKey={(row) => row.line}
            dataTestId="barcode-import-review-table"
            filterState={filters}
            onFilterChange={(key, value) => { setFilters((current) => ({ ...current, [key]: value })); setPage(1) }}
            sortState={sort}
            onSortChange={(next) => { setSort(next); setPage(1) }}
            pageState={page}
            onPageChange={setPage}
            onPageRowsChange={onPageRowsChange}
            onFilteredRowsChange={onFilteredRowsChange}
            emptyMessage="Geen barcodevoorstellen voor deze filters."
            renderRow={(row) => <tr key={row.line}>
              <td><input type="checkbox" aria-label={`Selecteer ${row.article} (regel ${row.line})`}
                checked={selectedIds.includes(row.line)}
                disabled={busy || !selectableIds.has(row.line)}
                onChange={() => setSelectedIds((current) => current.includes(row.line)
                  ? current.filter((id) => id !== row.line) : [...current, row.line])} /></td>
              <td>{row.article}</td>
              <td>{row.retailer}</td>
              <td>{row.article_number}</td>
              <td>{row.gtin}</td>
              <td title={offNames[row.gtin]?.status === 'found' ? [row.product_name,
                offNames[row.gtin]?.brand, offNames[row.gtin]?.quantity].filter(Boolean).join(' · ') : row.product_name}>{row.product_name}</td>
              <td title={[
                row.reason,
                row.existing_catalog_product ? `Catalogusproduct: ${row.existing_catalog_product}` : '',
                row.existing_catalog_gtin ? `Catalogusbarcode: ${row.existing_catalog_gtin}` : '',
                row.existing_manual_gtin ? `Handmatige barcode: ${row.existing_manual_gtin}` : '',
              ].filter(Boolean).join(' · ')}>
                <span>{row.status}</span>
                {row.existing_catalog_product && row.status !== 'Te beoordelen'
                  ? <div><small>Catalogus: {row.existing_catalog_product}</small></div> : null}
                {row.has_barcode_conflict ? <div>
                  <small>Catalogus: {row.existing_catalog_gtin || 'geen barcode'}</small>
                  <div><small>Handmatig: {row.existing_manual_gtin || 'geen barcode'}</small></div>
                </div> : null}
              </td>
            </tr>}
          />
          <div className="rz-mobile-table-bulk-actions rz-external-ed2-bulk-actions">
            <span data-testid="barcode-import-selection-count">Op deze pagina geselecteerd: {selectedOnPageCount} ·
              Elders geselecteerd: {selectedElsewhereCount} · Totaal: {selectedCount}</span>
            <Button type="button" variant="secondary" disabled={!selectedCount || busy}
              onClick={deleteSelected}>Verwijderen</Button>
            <Button type="button" disabled={!canApproveSelection || busy}
              onClick={confirmApproval}>Goedkeuren</Button>
          </div>
        </> : null}
      </div>
    </ScreenCard>
  </AppShell>
}
