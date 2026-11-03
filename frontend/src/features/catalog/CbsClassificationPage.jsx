import { useEffect, useMemo, useRef, useState } from 'react'
import AppShell from '../../app/AppShell'
import ScreenCard from '../../ui/ScreenCard'
import DataTable from '../../ui/DataTable'
import Button from '../../ui/Button'
import { useAppFeedback } from '../../ui/AppFeedbackProvider'
import { fetchJsonWithAuth } from '../../lib/authSession'
import './catalog.css'

const API = '/api/cbs-classifications'
const PAGE_SIZE = 100

async function call(url, options) {
  const response = await fetchJsonWithAuth(url, options)
  const body = await response.json().catch(() => ({}))
  if (!response.ok) throw new Error(typeof body.detail === 'string' ? body.detail : 'CBS-verzoek mislukt.')
  return body
}

function csvCell(value) {
  const raw = String(value ?? '').replace(/\r?\n/g, ' ')
  const safe = /^[=+@\-\t\r]/.test(raw) ? "'" + raw : raw
  return '"' + safe.replaceAll('"', '""') + '"'
}

export default function CbsClassificationPage() {
  const { showFeedback } = useAppFeedback()
  const [items, setItems] = useState([])
  const [selected, setSelected] = useState(new Set())
  const [filters, setFilters] = useState({ classification: 'Niet geclassificeerd' })
  const [query, setQuery] = useState('')
  const [categories, setCategories] = useState([])
  const [proposal, setProposal] = useState(null)
  const [browsing, setBrowsing] = useState(false)
  const [browseParent, setBrowseParent] = useState(null)
  const [browseTrail, setBrowseTrail] = useState([])
  const [loading, setLoading] = useState(true)
  const [searching, setSearching] = useState(false)
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState('')
  const [note, setNote] = useState('')
  const [revision, setRevision] = useState(0)
  const busy = useRef(false)

  useEffect(() => {
    const controller = new AbortController()
    async function load() {
      setLoading(true)
      setError('')
      setSelected(new Set())
      setCategories([])
      setProposal(null)
      setBrowsing(false)
      setBrowseParent(null)
      setBrowseTrail([])
      try {
        const all = []
        let total = 0
        do {
          const result = await call(API + '/products?limit=' + PAGE_SIZE + '&offset=' + all.length,
            { signal: controller.signal })
          if (controller.signal.aborted) return
          const batch = Array.isArray(result.items) ? result.items : []
          total = Number(result.total || 0)
          if (!batch.length && total > all.length) throw new Error('Cataloguslijst is onvolledig geladen.')
          all.push(...batch)
        } while (all.length < total)
        if (!controller.signal.aborted) setItems(all)
      } catch (err) {
        if (!controller.signal.aborted) setError(err.message)
      } finally {
        if (!controller.signal.aborted) setLoading(false)
      }
    }
    load()
    return () => controller.abort()
  }, [revision])

  const selectedItems = useMemo(() => items.filter((item) => selected.has(item.id)), [items, selected])
  const allClassified = selectedItems.length > 0 && selectedItems.every((item) => item.classified)
  const isBusy = loading || searching || saving

  function toggle(id) {
    setProposal(null)
    setSelected((prev) => {
      const next = new Set(prev)
      if (next.has(id)) next.delete(id)
      else if (next.size < 100) next.add(id)
      return next
    })
  }

  async function findCategories() {
    if (busy.current || !selectedItems.length) return
    const term = query.trim() || (selectedItems.length === 1 ? selectedItems[0].name.trim() : '')
    if (term.length < 2) {
      setError('Vul minstens twee letters van een officiële CBS-categorie in.')
      return
    }
    busy.current = true
    setSearching(true)
    setError('')
    setProposal(null)
    setCategories([])
    setBrowsing(false)
    setBrowseParent(null)
    setBrowseTrail([])
    try {
      const result = await call(API + '/categories?query=' + encodeURIComponent(term) + '&limit=50')
      let candidates = Array.isArray(result.items) ? result.items : []
      if (!candidates.length) {
        const suggestions = await call(API + '/categories/suggest?query=' + encodeURIComponent(term) + '&limit=50')
        candidates = Array.isArray(suggestions.items) ? suggestions.items : []
      }
      setCategories(candidates)
      setNote(candidates.length
        ? candidates.some((item) => item.suggestion_reason)
          ? 'Dit zijn zoeksuggesties op productwoorden, geen automatische classificaties. Controleer de volledige CBS-omschrijving.'
          : 'Kies de juiste officiële CBS-categorie. Een overeenkomst in naam is nog geen bevestiging.'
        : 'Geen eenduidige categorie gevonden. Blader door de CBS-hiërarchie om zelf een categorie te kiezen.')
    } catch (err) {
      setError(err.message)
    } finally {
      setSearching(false)
      busy.current = false
    }
  }

  async function browseCategories(parent = null, trail = []) {
    if (busy.current) return
    busy.current = true
    setSearching(true)
    setError('')
    setProposal(null)
    try {
      const result = await call(API + '/categories/browse' +
        (parent ? '?parent_code=' + encodeURIComponent(parent) : ''))
      setCategories(Array.isArray(result.items) ? result.items : [])
      setBrowsing(true)
      setBrowseParent(parent)
      setBrowseTrail(trail)
      setNote(parent
        ? 'Kies een onderliggende categorie of blader verder. Alleen laagste categorieën zijn selecteerbaar.'
        : 'Blader door de officiële CBS-hoofdcategorieën. Open een categorie om de onderliggende indeling te zien.')
    } catch (err) {
      setError(err.message)
    } finally {
      setSearching(false)
      busy.current = false
    }
  }

  function confirmSelected() {
    if (busy.current || !proposal || !selectedItems.length) return
    showFeedback({
      variant: 'warning',
      title: 'CBS-artikelclassificatie bevestigen',
      message: selectedItems.length + ' geselecteerde artikel(en) classificeren als ' +
        proposal.cbs_code + ' – ' + proposal.name_nl + '?',
      detail: 'Deze categorie is een bestedingsindeling. Hiermee worden geen artikelen, barcodes of voorraadhoeveelheden samengevoegd.',
      primaryActionLabel: 'Bevestigen',
      secondaryActionLabel: 'Annuleren',
      onPrimaryAction: async () => {
        if (busy.current) return false
        busy.current = true
        setSaving(true)
        try {
          const selections = selectedItems.map((item) => ({
            global_product_id: item.id,
            expected_product_name: item.name,
            cbs_code: proposal.cbs_code,
            reference_version: proposal.reference_version,
            expected_version: item.version,
          }))
          const result = await call(API + '/bulk-confirm', {
            method: 'POST', headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ selections }),
          })
          showFeedback({ variant: 'success',
            message: result.confirmed + ' CBS-classificaties bevestigd.' })
          setNote(result.confirmed + ' artikelclassificaties opgeslagen; bestaande productidentiteiten behouden.')
          setFilters({})
          setRevision((v) => v + 1)
        } catch (err) {
          setError(err.message)
          throw err
        } finally {
          busy.current = false
          setSaving(false)
        }
      },
    })
  }

  function removeSelected() {
    if (busy.current || !allClassified) return
    showFeedback({
      variant: 'warning',
      title: 'CBS-classificatie verwijderen',
      message: 'De classificatie van ' + selectedItems.length + ' geselecteerde artikel(en) verwijderen?',
      detail: 'Catalogusproducten en eventuele barcodes blijven behouden. De wijzigingshistorie blijft beschikbaar.',
      primaryActionLabel: 'Verwijderen',
      secondaryActionLabel: 'Annuleren',
      onPrimaryAction: async () => {
        if (busy.current) return false
        busy.current = true
        setSaving(true)
        try {
          const result = await call(API + '/bulk-remove', {
            method: 'POST', headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ selections: selectedItems.map((item) => ({
              global_product_id: item.id,
              expected_product_name: item.name,
              expected_version: item.version,
            })) }),
          })
          showFeedback({ variant: 'success', message: result.removed + ' classificaties verwijderd.' })
          setRevision((v) => v + 1)
        } catch (err) {
          setError(err.message)
          throw err
        } finally {
          busy.current = false
          setSaving(false)
        }
      },
    })
  }

  function exportSelected() {
    if (!selectedItems.length) return
    const rows = [
      ['Artikel', 'Merk', 'Barcode', 'CBS-code', 'CBS-omschrijving'],
      ...selectedItems.map((item) => [
        item.name, item.brand, item.gtin, item.cbs_code, item.category_name,
      ]),
    ]
    const body = String.fromCharCode(0xFEFF) +
      rows.map((row) => row.map(csvCell).join(';')).join('\r\n')
    const url = URL.createObjectURL(new Blob([body], { type: 'text/csv;charset=utf-8' }))
    const anchor = document.createElement('a')
    anchor.href = url
    anchor.download = 'Inhuis_Artikelclassificaties_CBS.csv'
    document.body.appendChild(anchor)
    anchor.click()
    anchor.remove()
    window.setTimeout(() => URL.revokeObjectURL(url), 0)
  }

  const columns = [
    { key: 'select', label: '', width: 45,
      renderCell: (item) => <input type="checkbox"
        aria-label={'Selecteer ' + item.name} checked={selected.has(item.id)}
        disabled={isBusy || (!selected.has(item.id) && selected.size >= 100)}
        onChange={() => toggle(item.id)} /> },
    { key: 'name', label: 'Artikel', width: 270, sortable: true, filterable: true,
      getFilterValue: (item) => item.name + ' ' + item.brand,
      renderCell: (item) => <span>{item.name}{item.brand ? ' · ' + item.brand : ''}</span> },
    { key: 'gtin', label: 'Barcode', width: 140, sortable: true, filterable: true,
      renderCell: (item) => item.gtin || '—' },
    { key: 'classification', label: 'Artikelclassificatie', width: 300,
      sortable: true, filterable: true,
      getFilterValue: (item) => item.classified
        ? item.cbs_code + ' ' + item.category_name : 'Niet geclassificeerd',
      getSortValue: (item) => item.category_name || '',
      renderCell: (item) => item.classified
        ? item.cbs_code + ' · ' + item.category_name : 'Niet geclassificeerd' },
  ]

  const categoryColumns = [
    { key: 'cbs_code', label: 'CBS-code', width: 110, sortable: true },
    { key: 'name_nl', label: 'Officiële CBS-omschrijving', sortable: true },
    { key: 'path', label: 'Hiërarchie', sortable: true },
    { key: 'suggestion_reason', label: 'Zoekhulp', renderCell: (item) => item.suggestion_reason || 'Officiële CBS-omschrijving' },
    { key: 'choose', label: '', width: 110,
      renderCell: (item) => <Button type="button" variant="secondary"
        disabled={isBusy}
        onClick={() => item.lowest ? setProposal(item) : browseCategories(item.cbs_code, [...browseTrail, item])}>
        {!item.lowest ? 'Openen' : proposal?.cbs_code === item.cbs_code ? 'Gekozen' : 'Kiezen'}
      </Button> },
  ]

  return <AppShell title="Artikelclassificaties toekennen" showExit={false}>
    <ScreenCard fullWidth>
      <h2>Artikelclassificaties toekennen</h2>
      <p>Zoek een officiële CBS ECOICOPv2-categorie en bevestig de juiste classificatie handmatig.
        Niet geclassificeerd blokkeert een product- of voorraadkoppeling niet.</p>
      {error ? <p role="alert">{error}</p> : null}
      {note ? <p role="status">{note}</p> : null}
      <div className="rz-article-classification-layout">
        <DataTable dataTestId="cbs-classification-table" columns={columns} data={items}
          filterState={filters}
          onFilterChange={(key, value) => setFilters((prev) => ({ ...prev, [key]: value }))}
          wrapperClassName="rz-classification-table-wrapper"
          getRowKey={(item) => item.id} pageSize={8}
          emptyMessage={loading ? 'Artikelen laden...' : 'Geen Catalogusartikelen.'}
          paginationActions={<span aria-live="polite">{selected.size} geselecteerd</span>} />
        <div className="rz-article-classification-actions" aria-label="CBS-classificatieacties">
          <label className="rz-input-field">
            <span className="rz-label">Zoek productnaam, CBS-code of officiële categorie</span>
            <input className="rz-input" value={query} disabled={isBusy}
              onChange={(event) => setQuery(event.target.value)}
              placeholder="Bijvoorbeeld melk of 011420" />
          </label>
          <Button type="button" disabled={isBusy || !selectedItems.length}
            onClick={findCategories}>{searching ? 'Zoeken...' : 'Voorstel ophalen'}</Button>
          <Button type="button" variant="secondary" disabled={isBusy}
            onClick={() => browseCategories()}>CBS-indeling doorbladeren</Button>
          <Button type="button" disabled={isBusy || !proposal || !selectedItems.length}
            onClick={confirmSelected}>{saving ? 'Opslaan...' : 'Voorstel bevestigen'}</Button>
          <Button type="button" variant="secondary" disabled={isBusy || !selectedItems.length}
            onClick={exportSelected}>Exporteren</Button>
          <Button type="button" variant="secondary" disabled={isBusy || !allClassified}
            onClick={removeSelected}>Classificatie verwijderen</Button>
        </div>
        {proposal ? <p role="status">Gekozen: {proposal.cbs_code} – {proposal.path}.
          Nog niet bevestigd.</p> : null}
        {browsing ? <div aria-label="CBS-navigatie">
          <Button type="button" variant="secondary" disabled={isBusy || !browseParent}
            onClick={() => browseCategories(browseTrail.length > 1 ? browseTrail[browseTrail.length - 2].cbs_code : null, browseTrail.slice(0, -1))}>Bovenliggende categorie openen</Button>
          <p role="status">{browseTrail.length ? browseTrail.map((item) => item.name_nl).join(' › ') : 'Alle CBS-hoofdcategorieën'}</p>
        </div> : null}
        {categories.length ? <section aria-label="Officiële CBS-kandidaten">
          <h3>Officiële CBS-kandidaten</h3>
          <p>Kies alleen de categorie die inhoudelijk bij alle geselecteerde artikelen past.</p>
          <DataTable dataTestId="cbs-category-candidates" columns={categoryColumns}
            data={categories} getRowKey={(item) => item.cbs_code} pageSize={8}
            emptyMessage="Geen CBS-categorieën gevonden." />
        </section> : null}
      </div>
    </ScreenCard>
  </AppShell>
}
