import { useEffect, useMemo, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import AppShell from '../../app/AppShell'
import ScreenCard from '../../ui/ScreenCard'
import DataTable from '../../ui/DataTable'
import Button from '../../ui/Button'
import Select from '../../ui/Select.jsx'
import CatalogProductImage from '../catalog/CatalogProductImage'
import { fetchJsonWithAuth } from '../../lib/authSession'
import './synonymAnalysis.css'

const API = '/api/external-databases/article-synonyms/analysis'
const statuses = [
  { value: '', label: 'Alle statussen' },
  { value: 'review', label: 'Te beoordelen' },
  { value: 'linked', label: 'Gekoppeld, zonder open voorstel' },
  { value: 'no_candidate', label: 'Geen kandidaat gevonden' },
  { value: 'insufficient', label: 'Winkel onbekend' },
]
const labels = {
  review: 'Te beoordelen',
  linked: 'Gekoppeld',
  no_candidate: 'Geen kandidaat gevonden',
  insufficient: 'Winkel onbekend',
}

export default function SynonymAnalysisPage() {
  const navigate = useNavigate()
  const [data, setData] = useState(null)
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(true)
  const [category, setCategory] = useState('')
  const [store, setStore] = useState('')
  const [status, setStatus] = useState('')
  const [search, setSearch] = useState('')
  const [selectedGroup, setSelectedGroup] = useState(null)

  useEffect(() => {
    const controller = new AbortController()
    async function load() {
      try {
        const response = await fetchJsonWithAuth(API, { signal: controller.signal })
        const result = await response.json().catch(() => ({}))
        if (!response.ok) throw new Error(result.detail || 'Synoniemenanalyse kon niet worden geladen.')
        if (!controller.signal.aborted) setData(result)
      } catch (err) {
        if (!controller.signal.aborted) setError(err.message || 'Synoniemenanalyse kon niet worden geladen.')
      } finally {
        if (!controller.signal.aborted) setLoading(false)
      }
    }
    load()
    return () => controller.abort()
  }, [])

  const groups = data?.groups || []
  const products = data?.items || []
  const categoryOptions = useMemo(() => [
    { value: '', label: 'Alle artikelsoorten' },
    ...Array.from(new Map(groups.map((row) => [row.group_key, {
      value: row.group_key, label: row.group_label,
    }])).values()),
  ], [groups])
  const storeOptions = useMemo(() => [
    { value: '', label: 'Alle winkels' },
    ...[...new Set(groups.map((row) => row.store))].sort().map((name) => ({ value: name, label: name })),
  ], [groups])

  const matches = (item) => (
    (!category || item.group_key === category)
    && (!store || (item.store || '') === store)
    && (!status || item.status === status)
    && (!search || (item.name + ' ' + item.brand + ' ' + item.variant + ' ' + item.store).toLocaleLowerCase('nl-NL').includes(search.toLocaleLowerCase('nl-NL')))
  )
  const filtered = products.filter(matches)
  const rows = groups.filter((row) => (
    (!category || row.group_key === category)
    && (!store || row.store === store)
    && (!status || filtered.some((p) => p.group_key === row.group_key && p.store === row.store))
    && (!search || filtered.some((p) => p.group_key === row.group_key && p.store === row.store))
  ))
  const details = selectedGroup
    ? filtered.filter((p) => p.group_key === selectedGroup.group_key && p.store === selectedGroup.store)
    : filtered

  const groupColumns = [
    { key: 'group_label', label: 'Artikelsoort', sortable: true, filterable: true, width: 340 },
    { key: 'store', label: 'Winkel', sortable: true, filterable: true, width: 180 },
    { key: 'articles', label: 'Artikelen', sortable: true, align: 'right', width: 105 },
    { key: 'linked', label: 'Gekoppeld', sortable: true, align: 'right', width: 105 },
    { key: 'review', label: 'Te beoordelen', sortable: true, align: 'right', width: 135 },
    { key: 'open', label: 'Bekijken', width: 125, renderCell: (item) => <Button type="button" variant="secondary" onClick={() => setSelectedGroup({ group_key: item.group_key, store: item.store })}>Artikelen</Button> },
  ]
  const detailColumns = [
    { key: 'name', label: 'Artikel', sortable: true, filterable: true, width: 290, renderCell: (item) => <div className="rz-synonym-analysis-product"><CatalogProductImage imageUrl={item.image_url} productName={item.name} compact /><span>{item.name}</span></div> },
    { key: 'store', label: 'Winkel', sortable: true, filterable: true, width: 130 },
    { key: 'group_label', label: 'Artikelsoort', sortable: true, filterable: true, width: 245 },
    { key: 'linked_stores', label: 'Gekoppelde winkels', width: 190, renderCell: (item) => item.linked_stores.length ? item.linked_stores.join(', ') : 'Geen' },
    { key: 'pending_count', label: 'Voorstellen', sortable: true, align: 'right', width: 100 },
    { key: 'status', label: 'Status', width: 170, renderCell: (item) => labels[item.status] },
    { key: 'action', label: 'Actie', width: 135, renderCell: (item) => item.pending_count
      ? <Button type="button" onClick={() => navigate('/artikelsynoniemen?artikel=' + encodeURIComponent(item.id))}>Beoordelen</Button>
      : <Button type="button" variant="secondary" onClick={() => navigate('/catalogus/' + encodeURIComponent(item.id))}>Catalogus</Button> },
  ]
  const detailRows = details.map((p) => ({ ...p, pending_count: p.pending.length }))

  return <AppShell title="Synoniemenanalyse" showExit={false}>
    <ScreenCard fullWidth>
      <div className="rz-synonym-analysis" data-testid="synonym-analysis-page">
        <h2>Synoniemenanalyse</h2>
        <p>Ontdek mogelijke ontbrekende koppelingen tussen winkels. Voorstellen zijn gebaseerd op tekstovereenkomst en zijn nog geen bewezen functionele gelijkwaardigheid. Controleer inhoud, variant en samenstelling vóór Koppelen.</p>
        {loading ? <p role="status">Synoniemenanalyse laden…</p> : null}
        {error ? <p role="alert" className="rz-inline-feedback rz-inline-feedback--error">{error}</p> : null}
        {!loading && !error && data ? <>
          <div className="rz-synonym-analysis-summary" aria-label="Overzicht synoniemen">
            {[
              ['Bevestigde artikelparen', data.summary.confirmed_pairs],
              ['Open kandidaatparen', data.summary.candidate_pairs],
              ['Zonder kandidaat', data.summary.no_candidate_articles],
              ['Winkel onbekend', data.summary.insufficient_articles],
            ].map(([label, value]) => <div className="rz-synonym-analysis-stat" key={label}><strong>{value}</strong><span>{label}</span></div>)}
          </div>
          <p className="rz-synonym-analysis-note">Analyse van {data.summary.eligible_articles} actieve artikelen met geldige barcode of bevestigde winkelartikelcode. Geen kandidaat betekent niet dat de winkel het artikel niet verkoopt. Bevestigde relaties tellen alleen rechtstreeks; een artikel kan zowel koppelingen als open voorstellen hebben.</p>
          <div className="rz-synonym-analysis-filters">
            <label>Artikelsoort<Select value={category} onChange={(value) => { setCategory(value); setSelectedGroup(null) }} options={categoryOptions} ariaLabel="Filter artikelsoort" /></label>
            <label>Winkel<Select value={store} onChange={(value) => { setStore(value); setSelectedGroup(null) }} options={storeOptions} ariaLabel="Filter winkel" /></label>
            <label>Status<Select value={status} onChange={(value) => setStatus(value)} options={statuses} ariaLabel="Filter status" /></label>
            <label>Zoek artikel<input className="rz-input" type="search" value={search} onChange={(event) => setSearch(event.target.value)} placeholder="Artikel, merk of winkel" /></label>
          </div>
          <h3>Artikelsoorten per winkel</h3>
          <DataTable columns={groupColumns} data={rows} pageSize={10} dataTestId="synonym-analysis-groups" emptyMessage="Geen passende artikelsoorten gevonden." />
          <div className="rz-synonym-analysis-details-heading">
            <h3>{selectedGroup ? selectedGroup.store + ' · ' + groups.find((g) => g.group_key === selectedGroup.group_key)?.group_label : 'Artikelen en ontbrekende koppelingen'}</h3>
            {selectedGroup ? <Button type="button" variant="secondary" onClick={() => setSelectedGroup(null)}>Alle artikelen tonen</Button> : null}
          </div>
          <DataTable columns={detailColumns} data={detailRows} pageSize={10} dataTestId="synonym-analysis-items" emptyMessage="Geen artikelen voor deze selectie." />
          <p className="rz-synonym-analysis-note">De artikelsoort komt uit een bevestigde Artikelclassificatie, anders uit de GS1 Brick of 'Niet geclassificeerd'. De indeling is geen bewijs voor synoniemrelaties. Winkels zonder aantoonbare artikelen worden niet als ontbrekend assortiment geteld.</p>
          <Button type="button" variant="secondary" onClick={() => navigate('/artikelsynoniemen')}>Alle voorstellen beoordelen</Button>
        </> : null}
      </div>
    </ScreenCard>
  </AppShell>
}
