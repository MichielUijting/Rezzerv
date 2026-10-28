import { useCallback, useEffect, useMemo, useState } from 'react'
import { useLocation } from 'react-router-dom'
import AppShell from '../../app/AppShell'
import ScreenCard from '../../ui/ScreenCard'
import DataTable from '../../ui/DataTable'
import Select from '../../ui/Select'
import Button from '../../ui/Button'
import { fetchJsonWithAuth } from '../../lib/authSession'
import { useMobileAppViewport } from '../../app/mobileViewport'
import OffCandidatePanel from './OffCandidatePanel'
import './externalDatabases.css'

const RETAILERS = { ah: 'Albert Heijn', albert_heijn: 'Albert Heijn', lidl: 'Lidl', jumbo: 'Jumbo', aldi: 'Aldi', plus: 'PLUS', picnic: 'Picnic' }
const STATUSES = { unlinked: 'Niet gekoppeld', classification_pending: 'Classificatie ontbreekt', linked: 'Gekoppeld' }
const CODE_OPTIONS = [
  { value: '', label: 'Alle art.codes' },
  { value: 'with_code', label: 'Met art.code' },
  { value: 'without_code', label: 'Zonder art.code' },
]
const STATUS_OPTIONS = [
  { value: '', label: 'Alle statussen' },
  ...Object.entries(STATUSES).map(([value, label]) => ({ value, label })),
]
const columns = [
  { key: 'select', label: '', width: 54 },
  { key: 'receipt_line_text', label: 'Artikel', width: 320, sortable: true, filterable: true },
  { key: 'retailer', label: 'Winkelketen', width: 170, sortable: true, filterable: true },
  { key: 'receipt_article_number', label: 'Bonartikelnummer', width: 190, sortable: true, filterable: true },
  { key: 'article_code', label: 'Art.code', width: 180, sortable: true, filterable: true,
    filterPredicate: (row, filter) => filter === 'with_code' ? Boolean(row.article_code)
      : filter === 'without_code' ? !row.article_code : true,
    renderFilter: ({ value, onChange }) => <Select ariaLabel="Filter op Art.code" value={value} onChange={onChange} options={CODE_OPTIONS} /> },
  { key: 'link_status', label: 'Status', width: 210, sortable: true, filterable: true,
    filterPredicate: (row, filter) => row.link_status === filter,
    renderFilter: ({ value, onChange }) => <Select ariaLabel="Filter op status" value={value} onChange={onChange} options={STATUS_OPTIONS} />,
    renderCell: (row) => STATUSES[row.link_status] || STATUSES.unlinked },
  { key: 'quantity_label', label: 'Omvang / gewicht', width: 170, sortable: true, filterable: true },
]

const exportColumns = [
  ['receipt_line_text', 'Artikel'], ['retailer', 'Winkelketen'],
  ['receipt_article_number', 'Bonartikelnummer'], ['article_code', 'Art.code'],
  ['link_status', 'Status'], ['quantity_label', 'Omvang / gewicht'],
]

function csvCell(value) {
  const content = String(value ?? '')
  // Spreadsheets must not execute formulas from externally supplied bontekst.
  const safe = /^\s*[=+@-]/.test(content) ? `'${content}` : content
  return `"${safe.replaceAll('"', '""')}"`
}

export default function ExternalDatabases2Page() {
  const location = useLocation()
  const [items, setItems] = useState([])
  const [counts, setCounts] = useState({ unlinked: 0, classification_pending: 0, linked: 0 })
  const [filters, setFilters] = useState({})
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [selectedItem, setSelectedItem] = useState(null)
  const [selectedIds, setSelectedIds] = useState([])
  const [pageRows, setPageRows] = useState([])
  const [confirmUnlink, setConfirmUnlink] = useState(false)
  const [unlinking, setUnlinking] = useState(false)
  const [refreshVersion, setRefreshVersion] = useState(0)
  const [offLinkOutcome, setOffLinkOutcome] = useState(() => location.state?.offLinkOutcome || null)
  const isMobile = useMobileAppViewport()

  const onPageRowsChange = useCallback((rows) => setPageRows(rows), [])
  const selectedRows = useMemo(() => items.filter((row) => selectedIds.includes(row.id)), [items, selectedIds])
  const canUnlink = selectedRows.length > 0 && selectedRows.length <= 100
    && selectedRows.every((row) => Boolean(row.off_link_id))
  const allPageSelected = pageRows.length > 0 && pageRows.every((row) => selectedIds.includes(row.id))

  function togglePageSelection() {
    const ids = pageRows.map((row) => row.id)
    setSelectedIds((current) => allPageSelected
      ? current.filter((id) => !ids.includes(id))
      : [...new Set([...current, ...ids])])
  }

  function exportSelected() {
    if (!selectedRows.length) return
    const content = [exportColumns.map(([, label]) => label),
      ...selectedRows.map((row) => exportColumns.map(([key]) =>
        key === 'link_status' ? STATUSES[row.link_status] || STATUSES.unlinked : row[key]))]
      .map((row) => row.map(csvCell).join(';')).join('\r\n')
    const url = URL.createObjectURL(new Blob([`\uFEFF${content}`], { type: 'text/csv;charset=utf-8' }))
    const anchor = document.createElement('a')
    anchor.href = url
    anchor.download = 'inhuis-externe-databases-2-artikelen.csv'
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

  useEffect(() => {
    const result = location.state?.offLinkOutcome
    if (!result) return undefined
    setOffLinkOutcome(result)
    return undefined
  }, [location.key, location.state?.offLinkOutcome])

  useEffect(() => {
    if (offLinkOutcome?.status !== 'success') return undefined
    const timeout = window.setTimeout(() => setOffLinkOutcome(null), 4000)
    return () => window.clearTimeout(timeout)
  }, [offLinkOutcome])

  useEffect(() => {
    let cancelled = false
    async function load() {
      setLoading(true)
      setError('')
      try {
        const response = await fetchJsonWithAuth('/api/external-databases/articles-overview', { method: 'GET' })
        const payload = await response.json()
        if (!response.ok) throw new Error('De artikelen konden niet worden geladen.')
        if (!cancelled) {
          const loadedItems = (payload.items || []).map((item) => ({
            ...item, retailer: RETAILERS[item.retailer_code] || item.retailer_code || 'Onbekend',
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
        if (!cancelled) setError('De artikelen konden niet worden geladen.')
      } finally {
        if (!cancelled) setLoading(false)
      }
    }
    load()
    return () => { cancelled = true }
  }, [location.state?.selectedItemId, refreshVersion])

  return (
    <AppShell title="Externe databases 2" showExit={false}>
      <ScreenCard fullWidth>
        <h2>Externe databases 2</h2>
        <p>{isMobile ? 'Tik' : 'Dubbelklik'} op een artikel om passende productkandidaten te zoeken. Art.code toont alleen een bekende Catalogusbarcode; het bonartikelnummer is een aparte code.</p>
        {offLinkOutcome ? <p data-testid="external-off-link-outcome"
          role={offLinkOutcome.status === 'success' ? 'status' : 'alert'}
          onClick={() => setOffLinkOutcome(null)}
          onKeyDown={(event) => {
            if (event.key === 'Enter' || event.key === ' ') setOffLinkOutcome(null)
          }}
          tabIndex={0}
          title={offLinkOutcome.status === 'success' ? '' : 'Klik om deze melding te sluiten'}>
          {offLinkOutcome.message}
        </p> : null}
        {error ? <p role="alert">{error}</p> : null}
        <div className="rz-external-receipt-overview">
        <div className="rz-external-ed2-counters" aria-label="Artikelstatussen">
          {Object.entries(STATUSES).map(([status, label]) => <Button
            key={status} type="button" variant="secondary"
            className={`rz-external-ed2-counter--${status}${filters.link_status === status ? ' rz-external-ed2-counter--active' : ''}`}
            aria-pressed={filters.link_status === status}
            onClick={() => setFilters((previous) => ({ ...previous,
              link_status: previous.link_status === status ? '' : status }))}
          >{label}: {counts[status] || 0}</Button>)}
          {Object.values(filters).some(Boolean) ? <Button type="button" variant="secondary"
            onClick={() => setFilters({})}>Wis filters</Button> : null}
        </div>
        <div className="rz-mobile-table-select-row">
          <label><input type="checkbox" checked={allPageSelected} disabled={!pageRows.length || unlinking}
            onChange={togglePageSelection} /> Alles op pagina</label>
        </div>
        <DataTable
          columns={columns}
          data={items}
          onPageRowsChange={onPageRowsChange}
          filterState={filters}
          onFilterChange={(key, value) => setFilters((previous) => ({ ...previous, [key]: value }))}
          getRowKey={(item) => item.id}
          defaultSort={{ key: 'receipt_line_text', direction: 'asc' }}
          emptyMessage={loading ? 'Artikelen laden...' : error ? 'Artikelen niet beschikbaar.' : 'Geen artikelen voor de gekozen filters.'}
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
              checked={selectedIds.includes(item.id)} disabled={unlinking}
              onClick={(event) => event.stopPropagation()}
              onDoubleClick={(event) => event.stopPropagation()}
              onChange={() => setSelectedIds((current) => current.includes(item.id)
                ? current.filter((id) => id !== item.id) : [...current, item.id])} />
              : typeof column.renderCell === 'function' ? column.renderCell(item) : item[column.key]}
          </td>)}</tr>}
        />
        <div className="rz-mobile-table-bulk-actions rz-external-ed2-bulk-actions">
          <span>Geselecteerd: {selectedIds.length}</span>
          <Button type="button" variant="secondary" disabled={!selectedRows.length || unlinking}
            onClick={exportSelected}>Exporteren</Button>
          <Button type="button" variant="secondary" disabled={!canUnlink || unlinking}
            onClick={() => setConfirmUnlink(true)}>{unlinking ? 'Ontkoppelen...' : 'Ontkoppelen'}</Button>
        </div>
        {selectedRows.length > 0 && !canUnlink ? <p className="rz-external-databases-muted">
          Ontkoppelen is alleen mogelijk voor geselecteerde OFF-koppelingen (maximaal 100 tegelijk).
          Exporteren kan voor alle geselecteerde artikelen.
        </p> : null}
        {selectedItem ? <OffCandidatePanel key={selectedItem.id} item={selectedItem} /> : null}
        </div>
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
