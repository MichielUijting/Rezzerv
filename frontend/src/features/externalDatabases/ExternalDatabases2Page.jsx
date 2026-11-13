import { useCallback, useEffect, useMemo, useState } from 'react'
import { useLocation, useNavigate } from 'react-router-dom'
import AppShell from '../../app/AppShell'
import ScreenCard from '../../ui/ScreenCard'
import DataTable from '../../ui/DataTable'
import Button from '../../ui/Button'
import { fetchJsonWithAuth, readStoredAuthContext } from '../../lib/authSession'
import { useAppFeedback } from '../../ui/AppFeedbackProvider.jsx'
import { useMobileAppViewport } from '../../app/mobileViewport'
import OffCandidatePanel from './OffCandidatePanel'
import Ed2GpcClassificationPanel from './Ed2GpcClassificationPanel'
import Ed2BarcodeScanner from './Ed2BarcodeScanner'
import Ed2ManualBarcodeEntry from './Ed2ManualBarcodeEntry'
import ClassificationWorkMonitor from './ClassificationWorkMonitor'
import CombinedClassificationWorkspace from './CombinedClassificationWorkspace'
import ArticleSynonymsPage from '../articleSynonyms/ArticleSynonymsPage'
import './externalDatabases.css'

const RETAILERS = { ah: 'Albert Heijn', albert_heijn: 'Albert Heijn', lidl: 'Lidl', jumbo: 'Jumbo', aldi: 'Aldi', plus: 'PLUS', picnic: 'Picnic' }
const STATUSES = { unlinked: 'Niet gekoppeld', classification_pending: 'Classificatie ontbreekt', linked: 'Gekoppeld' }
const columns = [
  { key: 'select', label: '', width: 54 },
  { key: 'receipt_line_text', label: 'Artikel', width: 320, sortable: true, filterable: true },
  { key: 'retailer', label: 'Winkelketen', width: 170, sortable: true, filterable: true },
  { key: 'receipt_article_number', label: 'Bonartikelnummer', width: 190, sortable: true, filterable: true },
  { key: 'article_code', label: 'Art./Barcode', width: 185, sortable: true, filterable: true,
    getSortValue: (row) => row.article_code || row.manual_barcode || '',
    getFilterValue: (row) => [row.article_code, row.manual_barcode].filter(Boolean).join(' '),
    filterPredicate: (row, filter) => [row.article_code, row.manual_barcode].filter(Boolean)
      .join(' ').toLowerCase().includes(String(filter).toLowerCase()),
    renderCell: (row) => row.article_code && row.manual_barcode && row.article_code !== row.manual_barcode
      ? <span title={`Barcodeconflict: Catalogus ${row.article_code}; handmatig ${row.manual_barcode}. Geen automatische wijziging.`}>
        <span>{row.article_code}</span>
        <span style={{ display: 'block' }}>Handmatig: {row.manual_barcode}</span>
      </span>
      : row.article_code || (row.manual_barcode
        ? <span title="Handmatig ingevoerde barcode; geen bevestigde Cataloguskoppeling">{row.manual_barcode}</span>
        : '') },
  { key: 'link_status', label: 'GS1-class.', width: 210, sortable: true, filterable: true,
    filterLabel: 'Filter op GS1-class.',
    getSortValue: (row) => STATUSES[row.link_status] || STATUSES.unlinked,
    filterPredicate: (row, filter) => {
      const normalized = String(filter || '').trim().toLocaleLowerCase('nl')
      const label = STATUSES[row.link_status] || STATUSES.unlinked
      const target = label.toLocaleLowerCase('nl')
      // Een volledige statusnaam filtert exact. Zo toont 'Gekoppeld' niet óók 'Niet gekoppeld'.
      const exactName = Object.values(STATUSES).some((name) => name.toLocaleLowerCase('nl') === normalized)
      return exactName ? target === normalized : target.includes(normalized)
    },
    renderCell: (row) => STATUSES[row.link_status] || STATUSES.unlinked },
  { key: 'quantity_label', label: 'Omvang / gewicht', width: 170, sortable: true, filterable: true },
]

const exportColumns = [
  ['receipt_line_text', 'Artikel'], ['retailer', 'Winkelketen'],
  ['receipt_article_number', 'Bonartikelnummer'], ['article_code', 'Art./Barcode'],
  ['link_status', 'GS1-class.'], ['quantity_label', 'Omvang / gewicht'],
]

function csvCell(value) {
  const content = String(value ?? '')
  // Spreadsheets must not execute formulas from externally supplied bontekst.
  const safe = /^\s*[=+@-]/.test(content) ? `'${content}` : content
  return `"${safe.replaceAll('"', '""')}"`
}

export default function ExternalDatabases2Page() {
  const location = useLocation()
  const navigate = useNavigate()
  const { showFeedback } = useAppFeedback()
  const isPlatformSuperuser = Boolean(readStoredAuthContext()?.is_platform_superuser)
  const restored = location.state?.ed2TableState
  const [items, setItems] = useState([])
  const [activeArea, setActiveArea] = useState(() => location.state?.ed2TableState ? 'identity' : null)
  const [counts, setCounts] = useState({ unlinked: 0, classification_pending: 0, linked: 0 })
  const [filters, setFilters] = useState(() => restored?.filters || {})
  const [activeStatusCounter, setActiveStatusCounter] = useState(() => restored?.activeStatusCounter || '')
  const [tableSort, setTableSort] = useState(() => restored?.sort || { key: 'receipt_line_text', direction: 'asc' })
  const [tablePage, setTablePage] = useState(() => Math.max(1, Number(restored?.page) || 1))
  const [loading, setLoading] = useState(true)
  const [selectedItem, setSelectedItem] = useState(null)
  const [pendingScannedBarcode, setPendingScannedBarcode] = useState(null)
  const [selectedIds, setSelectedIds] = useState([])
  const [pageIds, setPageIds] = useState([])
  const [filteredIds, setFilteredIds] = useState([])
  const [confirmUnlink, setConfirmUnlink] = useState(false)
  const [unlinking, setUnlinking] = useState(false)
  const [deleting, setDeleting] = useState(false)
  const [materializing, setMaterializing] = useState(false)
  const [refreshVersion, setRefreshVersion] = useState(0)
  const [offLinkOutcome, setOffLinkOutcome] = useState(() => location.state?.offLinkOutcome || null)
  const isMobile = useMobileAppViewport()
  const returnState = { filters, activeStatusCounter, sort: tableSort, page: tablePage }
  useEffect(() => {
    if (activeArea !== 'identity') return
    navigate(`${location.pathname}${location.search}`, {
      replace: true, state: { ...location.state, ed2TableState: returnState },
    })
  }, [filters, activeStatusCounter, tableSort, tablePage, activeArea])

  const onPageRowsChange = useCallback((rows) => {
    const ids = rows.map((row) => row.id)
    setPageIds((previous) => previous.length === ids.length && previous.every((id, index) => id === ids[index]) ? previous : ids)
  }, [])
  const onFilteredRowsChange = useCallback((rows) => {
    const ids = rows.map((row) => row.id)
    setFilteredIds((previous) => previous.length === ids.length && previous.every((id, index) => id === ids[index]) ? previous : ids)
  }, [])
  const selectedRows = useMemo(() => items.filter((row) => selectedIds.includes(row.id)), [items, selectedIds])
  const counterFilteredItems = useMemo(() => activeStatusCounter
    ? items.filter((row) => row.link_status === activeStatusCounter) : items, [items, activeStatusCounter])
  const canUnlink = selectedRows.length > 0 && selectedRows.length <= 100
    && selectedRows.every((row) => Boolean(row.off_link_id))
  const canMaterializeSaved = selectedRows.length > 0 && selectedRows.length <= 50
    && selectedRows.every((row) =>
      /^(?:[0-9]{8}|[0-9]{12,14})$/.test(String(row.manual_barcode || '').trim()))
  const allPageSelected = pageIds.length > 0 && pageIds.every((id) => selectedIds.includes(id))
  const allFilteredSelected = filteredIds.length > 0 && filteredIds.every((id) => selectedIds.includes(id))

  function togglePageSelection() {
    setSelectedIds((current) => allPageSelected
      ? current.filter((id) => !pageIds.includes(id))
      : [...new Set([...current, ...pageIds])])
  }

  function toggleAllFilteredSelection() {
    setSelectedIds((current) => allFilteredSelected
      ? current.filter((id) => !filteredIds.includes(id))
      : [...new Set([...current, ...filteredIds])])
  }

  const tableColumns = useMemo(() => columns.map((column) => column.key === 'select'
    ? { ...column, header: <input type="checkbox"
      aria-label="Alles op huidige pagina" checked={allPageSelected}
      disabled={!pageIds.length || unlinking || deleting}
      onChange={togglePageSelection} /> }
    : column), [allPageSelected, pageIds, unlinking, deleting])

  function exportSelected() {
    if (!selectedRows.length) return
    const content = [exportColumns.map(([, label]) => label),
      ...selectedRows.map((row) => exportColumns.map(([key]) =>
        key === 'link_status' ? STATUSES[row.link_status] || STATUSES.unlinked
          : key === 'article_code' ? row.article_code || row.manual_barcode || '' : row[key]))]
      .map((row) => row.map(csvCell).join(';')).join('\r\n')
    const url = URL.createObjectURL(new Blob([`\uFEFF${content}`], { type: 'text/csv;charset=utf-8' }))
    const anchor = document.createElement('a')
    anchor.href = url
    anchor.download = 'inhuis-artikel-classificeren-artikelen.csv'
    document.body.appendChild(anchor)
    anchor.click()
    anchor.remove()
    window.setTimeout(() => URL.revokeObjectURL(url), 1000)
  }

  async function unlinkSelected() {
    if (!canUnlink || unlinking) return
    setConfirmUnlink(false)
    setUnlinking(true)
    setOffLinkOutcome(null)
    const controller = new AbortController()
    const timeout = window.setTimeout(() => controller.abort(), 30000)
    try {
      const response = await fetchJsonWithAuth('/api/external-databases/off/unlink-selected', {
        method: 'POST', headers: { 'Content-Type': 'application/json' }, signal: controller.signal,
        body: JSON.stringify({ selections: selectedRows.map((row) => ({
          receipt_item_id: row.id, link_id: row.off_link_id,
        })) }),
      })
      const result = await response.json().catch(() => ({}))
      if (!response.ok || result.ok !== true || result.unlinked_articles !== selectedRows.length) {
        throw new Error(typeof result.detail === 'string' ? result.detail : 'Ontkoppelen is niet bevestigd.')
      }
      setSelectedIds([])
      setSelectedItem(null)
      setOffLinkOutcome({ status: 'success', message: `${result.unlinked_articles} bonartikel(en) ontkoppeld van OFF.` })
    } catch (err) {
      if (err.status !== 401) setOffLinkOutcome({ status: 'error', message: err.name === 'AbortError'
        ? 'Ontkoppeling niet bevestigd. Vernieuw de lijst om de actuele status te controleren.'
        : `Ontkoppeling niet bevestigd: ${err.message || 'Onbekende fout.'}` })
    } finally {
      window.clearTimeout(timeout)
      setUnlinking(false)
      setRefreshVersion((value) => value + 1)
    }
  }

  function confirmMaterializeSaved() {
    if (!canMaterializeSaved || materializing || deleting || unlinking) return
    const selections = selectedRows.map((row) => ({
      receipt_item_id: row.id, gtin: String(row.manual_barcode).trim(),
    }))
    showFeedback({
      variant: 'warning',
      title: 'Bewaarde barcodes koppelen',
      message: selections.length + ' eerder opgeslagen barcode(s) aan de Catalogus koppelen?',
      detail: 'Alleen bevestigde barcodes worden verwerkt. Er verandert niets aan kassabonnen, huishoudartikelen of voorraad. Bij één conflict wordt niets opgeslagen.',
      primaryActionLabel: 'Koppelen', secondaryActionLabel: 'Annuleren',
      testId: 'ed2-materialize-existing-confirm',
      onPrimaryAction: async () => {
        setMaterializing(true)
        try {
          const response = await fetchJsonWithAuth('/api/catalog/ed2/manual-barcodes/materialize-existing', {
            method: 'POST', headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ selections }),
          })
          const result = await response.json().catch(() => ({}))
          if (!response.ok || result.ok !== true || result.processed !== selections.length) {
            throw new Error(typeof result.detail === 'string' ? result.detail
              : 'De bestaande barcodes konden niet volledig worden gekoppeld.')
          }
          setSelectedIds([])
          setSelectedItem(null)
          setRefreshVersion((value) => value + 1)
          showFeedback({
            variant: 'success', title: 'Catalogus bijgewerkt',
            message: result.catalog_links_created + ' barcode(s) gekoppeld; '
              + result.already_confirmed + ' waren al gekoppeld. '
              + result.catalog_products_created + ' nieuw(e) Catalogusproduct(en).',
          })
          return false
        } catch (error) {
          setRefreshVersion((value) => value + 1)
          showFeedback({
            variant: 'error', title: 'Niet gekoppeld',
            message: error.message || 'Er is een conflict; er is niets gewijzigd.',
          })
          return false
        } finally {
          setMaterializing(false)
        }
      },
    })
  }

  function confirmDeleteSelected() {
    if (!isPlatformSuperuser || !selectedRows.length || selectedRows.length > 100 || unlinking || deleting) return
    const count = selectedRows.length
    showFeedback({
      variant: 'warning',
      title: count === 1 ? 'Artikel verwijderen' : 'Artikelen verwijderen',
      message: count === 1
        ? 'Dit artikel verwijderen uit Artikel classificeren en de Catalogus?'
        : `${count} artikelen verwijderen uit Artikel classificeren en de Catalogus?`,
      detail: 'Kassabonnen en voorraad blijven bestaan. Een gedeeld Catalogusartikel wordt niet verwijderd.',
      primaryActionLabel: 'Verwijderen',
      secondaryActionLabel: 'Annuleren',
      testId: 'ed2-delete-confirmation',
      onPrimaryAction: async () => {
        setDeleting(true)
        const controller = new AbortController()
        const timeout = window.setTimeout(() => controller.abort(), 30000)
        try {
          const response = await fetchJsonWithAuth('/api/external-databases/articles/delete-selected', {
            method: 'POST', headers: { 'Content-Type': 'application/json' },
            signal: controller.signal,
            body: JSON.stringify({ selections: selectedRows.map((row) => ({ receipt_item_id: row.id })) }),
          })
          const payload = await response.json().catch(() => ({}))
          if (!response.ok || payload.ok !== true || payload.removed_articles !== count) {
            throw new Error(typeof payload.detail === 'string' ? payload.detail : 'Verwijderen is niet bevestigd.')
          }
          setSelectedIds([])
          setSelectedItem(null)
          setRefreshVersion((value) => value + 1)
          showFeedback({
            variant: 'success', title: 'Verwijderd',
            message: count === 1 ? 'Artikel verwijderd uit de overzichten.' : `${count} artikelen verwijderd uit de overzichten.`,
          })
          // The dialog provider would otherwise dismiss the new success overlay.
          return false
        } catch (err) {
          setRefreshVersion((value) => value + 1)
          showFeedback({
            variant: 'error', title: 'Niet verwijderd',
            message: err.name === 'AbortError'
              ? 'Geen bevestiging ontvangen. Vernieuw de lijst voordat je opnieuw probeert.'
              : (err.message || 'De artikelen konden niet veilig worden verwijderd.'),
          })
          // Keep the replacement error overlay visible instead of dismissing it.
          return false
        } finally {
          window.clearTimeout(timeout)
          setDeleting(false)
        }
      },
    })
  }

  useEffect(() => {
    const result = location.state?.offLinkOutcome
    if (!result) return
    // A link result is one-time navigation feedback, not a persistent part of
    // browser history. Consume it before a Back/Forward navigation can replay
    // old success messages (or claim that a link just happened again).
    setOffLinkOutcome(result)
    const nextState = { ...(location.state || {}) }
    delete nextState.offLinkOutcome
    navigate(`${location.pathname}${location.search}`, {
      replace: true,
      state: nextState,
    })
  }, [location.key, location.state?.offLinkOutcome])

  useEffect(() => {
    if (!offLinkOutcome?.message) return undefined
    showFeedback({ variant: offLinkOutcome.status === 'success' ? 'success' : (offLinkOutcome.status === 'warning' ? 'warning' : 'error'), message: offLinkOutcome.message })
    const timeout = window.setTimeout(() => setOffLinkOutcome(null), 4000)
    return () => window.clearTimeout(timeout)
  }, [offLinkOutcome, showFeedback])

  useEffect(() => {
    let cancelled = false
    async function load() {
      if (activeArea !== 'identity') return
      setLoading(true)
      try {
        const response = await fetchJsonWithAuth('/api/external-databases/articles-overview', { method: 'GET' })
        const payload = await response.json()
        if (!response.ok) throw new Error('De artikelen konden niet worden geladen.')
        // The overview projects manual barcode evidence by the authoritative
        // server-side retailer/receipt/article identity. Do not reconstruct
        // receipt keys or hide a failed secondary lookup in the browser.
        if (!cancelled) {
          const loadedItems = (payload.items || []).map((item) => ({
            ...item, retailer: RETAILERS[item.retailer_code] || item.retailer_code || 'Onbekend',
            manual_barcode: item.manual_barcode || '',
          }))
          setItems(loadedItems)
          setCounts(payload.counts || {
            unlinked: loadedItems.filter((item) => item.link_status === 'unlinked' || !item.link_status).length,
            classification_pending: loadedItems.filter((item) => item.link_status === 'classification_pending').length,
            linked: loadedItems.filter((item) => item.link_status === 'linked').length,
          })
          if (location.state?.selectedItemId) {
            setSelectedItem(loadedItems.find((item) => item.id === location.state.selectedItemId) || null)
          }
        }
      } catch {
        if (!cancelled) showFeedback({ variant: 'error', message: 'De artikelen konden niet worden geladen.' })
      } finally {
        if (!cancelled) setLoading(false)
      }
    }
    load()
    return () => { cancelled = true }
  }, [location.state?.selectedItemId, refreshVersion, activeArea, showFeedback])

  return (
    <AppShell title="Artikelbeheer" showExit={false}>
      <ScreenCard fullWidth>
        <h2>Artikelbeheer</h2>
        <ClassificationWorkMonitor activeArea={activeArea} onAreaChange={setActiveArea} />
        {activeArea === "classify" ? <CombinedClassificationWorkspace /> : null}
        {activeArea === "synonyms" ? <ArticleSynonymsPage embedded /> : null}
        {activeArea === 'identity' ? <div id="ed2-work-table" className="rz-external-receipt-overview">
        <div className="rz-external-ed2-counters" aria-label="Artikelstatussen">
          {Object.entries(STATUSES).map(([status, label]) => <Button
            key={status} type="button" variant="secondary"
            className={`rz-external-ed2-counter--${status}${activeStatusCounter === status ? ' rz-external-ed2-counter--active' : ''}`}
            aria-pressed={activeStatusCounter === status}
            onClick={() => { setActiveStatusCounter((previous) => previous === status ? '' : status)
              setTablePage(1)
              setFilters((previous) => ({ ...previous, link_status: '' })) }}
          >{label}: {counts[status] || 0}</Button>)}
        </div>
        <div className="rz-mobile-table-select-row">
          <label><input type="checkbox" checked={allFilteredSelected} disabled={!filteredIds.length || unlinking || deleting}
            onChange={toggleAllFilteredSelection} /> Alle artikelen op alle pagina’s</label>
        </div>
        <DataTable
          columns={tableColumns}
          data={counterFilteredItems}
          onPageRowsChange={onPageRowsChange}
          onFilteredRowsChange={onFilteredRowsChange}
          filterState={filters}
          onFilterChange={(key, value) => { setFilters((previous) => ({ ...previous, [key]: value })); setTablePage(1) }}
          sortState={tableSort}
          onSortChange={(value) => { setTableSort(value); setTablePage(1) }}
          pageState={tablePage}
          onPageChange={setTablePage}
          pageReady={!loading}
          getRowKey={(item) => item.id}
          defaultSort={{ key: 'receipt_line_text', direction: 'asc' }}
          emptyMessage={loading ? 'Artikelen laden...' : 'Geen artikelen voor de gekozen filters.'}
          dataTestId="external-databases-2-table"
          renderRow={(item) => <tr key={item.id}
            tabIndex={0}
            aria-selected={selectedItem?.id === item.id}
            className={selectedItem?.id === item.id ? 'rz-row-selected' : ''}
            onClick={() => { if (isMobile) setSelectedItem(item) }}
            onDoubleClick={() => { if (!isMobile) setSelectedItem(item) }}
            onKeyDown={(event) => {
              if (event.target !== event.currentTarget) return
              if (event.key === 'Enter' || event.key === ' ') { event.preventDefault(); setSelectedItem(item) }
            }}
          >{columns.map((column) => <td key={column.key}>
            {column.key === 'select' ? <input type="checkbox" aria-label={`Selecteer ${item.receipt_line_text}`}
              checked={selectedIds.includes(item.id)} disabled={unlinking || deleting}
              onClick={(event) => event.stopPropagation()}
              onDoubleClick={(event) => event.stopPropagation()}
              onChange={() => setSelectedIds((current) => current.includes(item.id)
                ? current.filter((id) => id !== item.id) : [...current, item.id])} />
              : typeof column.renderCell === 'function' ? column.renderCell(item) : item[column.key]}
          </td>)}</tr>}
        />
        <div className="rz-mobile-table-bulk-actions rz-external-ed2-bulk-actions">
          <span>Geselecteerd: {selectedIds.length}</span>
          <Button type="button" variant="secondary" disabled={!selectedRows.length || unlinking || deleting}
            onClick={exportSelected}>Exporteren</Button>
          {isPlatformSuperuser ? <Button type="button" variant="secondary"
            onClick={() => navigate('/externe-databases-2/importeren',
              { state: { ed2TableState: returnState } })}>Importeren</Button> : null}
          <Button type="button" variant="secondary"
            disabled={!canMaterializeSaved || unlinking || deleting || materializing}
            onClick={confirmMaterializeSaved}>
            {materializing ? 'Koppelen...' : 'Bewaarde barcodes koppelen'}
          </Button>
          <Button type="button" variant="secondary" disabled={!canUnlink || unlinking || deleting || materializing}
            onClick={() => setConfirmUnlink(true)}>{unlinking ? 'Ontkoppelen...' : 'Ontkoppelen'}</Button>
          {isPlatformSuperuser ? <Button type="button" variant="secondary"
            disabled={!selectedRows.length || selectedRows.length > 100 || unlinking || deleting}
            onClick={confirmDeleteSelected}>{deleting ? 'Verwijderen...' : 'Verwijderen'}</Button> : null}
        </div>
        {selectedRows.length > 0 && !canUnlink ? <p className="rz-external-databases-muted">
          Ontkoppelen is alleen mogelijk voor geselecteerde OFF-koppelingen (maximaal 100 tegelijk).
          Exporteren kan voor alle geselecteerde artikelen.
        </p> : null}
        {selectedItem?.link_status === 'classification_pending'
          && selectedItem.pending_global_product_id && selectedItem.off_link_id
          ? <div key={selectedItem.id}>
            <Ed2GpcClassificationPanel item={selectedItem}
              onClassified={(message) => {
                setSelectedItem(null)
                setSelectedIds([])
                setActiveStatusCounter('')
                setFilters((previous) => ({ ...previous, link_status: '' }))
                setOffLinkOutcome({ status: 'success', message })
                setRefreshVersion((value) => value + 1)
              }} />
            <section className="rz-external-receipt-detail" aria-label="Artikelidentiteit bevestigen">
              <Ed2BarcodeScanner receiptItemId={selectedItem.id}
                onScanned={(value) => setPendingScannedBarcode({ receiptItemId: selectedItem.id, value })} />
              <Ed2ManualBarcodeEntry item={selectedItem} scannedBarcode={pendingScannedBarcode}
                onSaved={(outcome) => {
                  setSelectedItem(null)
                  setSelectedIds([])
                  setPendingScannedBarcode(null)
                  setOffLinkOutcome(outcome)
                  setRefreshVersion((value) => value + 1)
                }} />
            </section>
          </div>
          : selectedItem ? <OffCandidatePanel key={selectedItem.id} item={selectedItem} returnState={returnState}
            onLinkOutcome={(outcome) => {
              setOffLinkOutcome(outcome)
              setSelectedItem(null)
              setSelectedIds([])
              // Keep the user's existing filters, sort order and page after
              // saving; the refreshed list determines whether a row remains visible.
              // Re-read canonical ED2 statuses; never infer successful linkage from a preview.
              setRefreshVersion((value) => value + 1)
            }} /> : null}
        </div> : null}
        {confirmUnlink ? <div className="rz-modal-backdrop">
          <div className="rz-modal-card" role="alertdialog" aria-modal="true" aria-labelledby="ed2-unlink-confirm">
            <p className="rz-modal-text" id="ed2-unlink-confirm">
              Weet u zeker dat u {selectedRows.length} bonartikel(en) wilt ontkoppelen van OFF?
            </p>
            <div className="rz-modal-actions">
              <Button type="button" variant="secondary" onClick={() => setConfirmUnlink(false)}>Annuleren</Button>
              <Button type="button" onClick={unlinkSelected}>OK</Button>
            </div>
          </div>
        </div> : null}
      </ScreenCard>
    </AppShell>
  )
}
