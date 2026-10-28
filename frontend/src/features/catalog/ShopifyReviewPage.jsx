import { useEffect, useMemo, useRef, useState } from 'react'
import { Link } from 'react-router-dom'
import AppShell from '../../app/AppShell'
import ScreenCard from '../../ui/ScreenCard'
import DataTable from '../../ui/DataTable'
import Button from '../../ui/Button'
import Select from '../../ui/Select'
import { useAppFeedback } from '../../ui/AppFeedbackProvider'
import { fetchJsonWithAuth } from '../../lib/authSession'

const API = '/api/catalog/shopify'
const LIMIT = 100

async function call(url, options) {
  const response = await fetchJsonWithAuth(url, options)
  const body = await response.json().catch(() => ({}))
  if (!response.ok) throw new Error(typeof body.detail === 'string' ? body.detail : 'Verzoek mislukt.')
  return body
}

export default function ShopifyReviewPage() {
  const { showFeedback } = useAppFeedback()
  const [items, setItems] = useState([])
  const [total, setTotal] = useState(0)
  const [offset, setOffset] = useState(0)
  const [search, setSearch] = useState('')
  const [categorySearch, setCategorySearch] = useState('')
  const [categories, setCategories] = useState([])
  const [choices, setChoices] = useState({})
  const [proposals, setProposals] = useState({})
  const [confirmed, setConfirmed] = useState(new Set())
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const [busyId, setBusyId] = useState('')
  const [error, setError] = useState('')
  const [note, setNote] = useState('')
  const [reload, setReload] = useState(0)
  const savingRef = useRef(false)

  useEffect(() => {
    const controller = new AbortController()
    setLoading(true)
    setError('')
    setConfirmed(new Set())
    setChoices({})
    setProposals({})
    call(API + '?limit=' + LIMIT + '&offset=' + offset + '&search=' +
      encodeURIComponent(search.trim()), { signal: controller.signal })
      .then((data) => {
        if (controller.signal.aborted) return
        setItems(data.items || [])
        setTotal(Number(data.total || 0))
      })
      .catch((err) => { if (!controller.signal.aborted) setError(err.message) })
      .finally(() => { if (!controller.signal.aborted) setLoading(false) })
    return () => controller.abort()
  }, [offset, search, reload])

  async function searchCategories() {
    setError('')
    if (categorySearch.trim().length < 2) {
      setError('Gebruik minimaal twee letters voor een Shopify-categorie.')
      return
    }
    try {
      const data = await call(API + '/categories?query=' + encodeURIComponent(categorySearch.trim()))
      setCategories(data.items || [])
      setNote((data.items || []).length + ' categorieën gevonden. Kies per artikel de passende categorie.')
    } catch (err) { setError(err.message) }
  }

  function selectedCategory(item) {
    return choices[item.id] ?? item.shopify_id ?? ''
  }

  function choose(item, value) {
    setChoices((current) => ({ ...current, [item.id]: value }))
    setConfirmed((current) => {
      const next = new Set(current)
      next.delete(item.id)
      return next
    })
  }

  async function askOff(item) {
    setError('')
    setBusyId(item.id)
    try {
      const result = await call(API + '/' + encodeURIComponent(item.id) + '/proposal')
      if (result.gtin !== item.gtin) throw new Error('Barcode gewijzigd. Ververs de lijst.')
      setProposals((current) => ({ ...current, [item.id]: result }))
      if (result.shopify_id) choose(item, result.shopify_id)
      setNote(result.message || (result.shopify_id ? 'Controleer het voorstel.' : 'Geen eenduidig voorstel gevonden.'))
    } catch (err) { setError(err.message) }
    finally { setBusyId('') }
  }

  function toggle(item) {
    if (!selectedCategory(item)) return
    setConfirmed((current) => {
      const next = new Set(current)
      if (next.has(item.id)) next.delete(item.id)
      else next.add(item.id)
      return next
    })
  }

  async function save() {
    if (savingRef.current || !confirmed.size) return
    const selections = items.filter((item) => confirmed.has(item.id)).map((item) => ({
      global_product_id: item.id,
      expected_gtin: item.gtin,
      expected_version: item.version,
      shopify_id: selectedCategory(item),
      barcode_confirmed: true,
    }))
    if (selections.length !== confirmed.size || selections.length > 100) {
      setError('Selectie is gewijzigd; ververs de lijst.')
      return
    }
    savingRef.current = true
    setSaving(true)
    setError('')
    try {
      const data = await call(API + '/bulk-confirm', { method: 'POST', body: JSON.stringify({ selections }) })
      showFeedback({ variant: 'success', message: data.confirmed + ' Shopify-classificaties bevestigd.' })
      setNote(data.confirmed + ' bevestigde keuzes vastgelegd.')
      setReload((value) => value + 1)
    } catch (err) { setError(err.message) }
    finally { savingRef.current = false; setSaving(false) }
  }

  const columns = useMemo(() => [
    {
      key: 'confirmed', label: '', width: 66, className: 'rz-check', cellClassName: 'rz-check',
      renderCell: (item) => <input type="checkbox" checked={confirmed.has(item.id)}
        aria-label={'Ik bevestig de bestaande barcode ' + item.gtin + ' en mijn Shopify-keuze voor ' + item.name}
        disabled={saving || !selectedCategory(item)} onChange={() => toggle(item)} />,
    },
    { key: 'name', label: 'Artikelnaam', width: 230, sortable: true, filterable: true },
    { key: 'brand', label: 'Merk', width: 120, sortable: true, filterable: true },
    { key: 'gtin', label: 'Bestaande barcode', width: 150, sortable: true, filterable: true },
    { key: 'shopify_path', label: 'Bestaande Shopify-classificatie', width: 245, sortable: true, filterable: true,
      renderCell: (item) => item.shopify_path || 'Nog niet bevestigd' },
    {
      key: 'proposal', label: 'OFF-voorstel', width: 240,
      renderCell: (item) => <div>
        <Button type="button" variant="secondary" disabled={saving || Boolean(busyId)}
          onClick={() => askOff(item)}>{busyId === item.id ? 'Zoeken...' : 'Haal OFF-voorstel op'}</Button>
        {proposals[item.id] ? <p aria-live="polite">
          {proposals[item.id].shopify_path || proposals[item.id].status}
          {proposals[item.id].warning ? ' — ' + proposals[item.id].warning : ''}
        </p> : null}
      </div>,
    },
    {
      key: 'choice', label: 'Shopify-categorie kiezen', width: 280,
      renderCell: (item) => {
        const current = selectedCategory(item)
        const options = [
          { value: '', label: 'Selecteer categorie' },
          ...(current && !categories.some((cat) => cat.id === current)
            ? [{ value: current, label: proposals[item.id]?.shopify_path || item.shopify_path || current }] : []),
          ...categories.map((cat) => ({ value: cat.id, label: cat.path })),
        ]
        return <Select value={current} options={options} onChange={(value) => choose(item, value)}
          ariaLabel={'Shopify-categorie voor ' + item.name} disabled={saving} />
      },
    },
  ], [confirmed, saving, busyId, proposals, categories, choices])

  return <AppShell title="Shopify-classificaties beoordelen" showExit={false}>
    <ScreenCard fullWidth>
      <h2>Shopify-classificaties beoordelen</h2>
      <p>Alleen Catalogusartikelen met een bestaande geldige barcode. Shopify staat los van GS1, Producttype, Artikelgroep en Voorraad.</p>
      <p>Vraag een OFF-voorstel op of kies een categorie. Bevestig daarna per artikel dat je de barcode gecontroleerd hebt. Er wordt niets automatisch opgeslagen.</p>
      <p>Artikelen zonder barcode behandel je eerst in <Link to="/externe-databases-2">Externe databases 2</Link>.</p>
      <div className="rz-external-databases-actions">
        <label>Zoek artikel <input className="rz-input" type="search" value={search}
          onChange={(event) => { setSearch(event.target.value); setOffset(0) }} /></label>
        <label>Zoek Shopify-categorie <input className="rz-input" type="search" value={categorySearch}
          onChange={(event) => setCategorySearch(event.target.value)} /></label>
        <Button type="button" variant="secondary" onClick={searchCategories} disabled={saving}>Zoek categorieën</Button>
      </div>
      {error ? <p role="alert">{error}</p> : null}
      {note ? <p role="status">{note}</p> : null}
      <DataTable dataTestId="shopify-review-table" columns={columns} data={items}
        getRowKey={(item) => item.id} pageSize={8}
        emptyMessage={loading ? 'Artikelen laden...' : 'Geen gecodeerde Catalogusartikelen gevonden.'}
        paginationActions={<>
          <span aria-live="polite">{confirmed.size} gecontroleerd en geselecteerd</span>
          <Button type="button" disabled={saving || loading || !confirmed.size}
            onClick={save}>{saving ? 'Opslaan...' : 'Bulk bevestigen'}</Button>
        </>} />
      <div className="rz-external-databases-actions">
        <Button type="button" variant="secondary" disabled={loading || saving || !offset}
          onClick={() => setOffset((value) => Math.max(0, value - LIMIT))}>Vorige 100</Button>
        <span>{total ? offset + 1 : 0}–{Math.min(total, offset + LIMIT)} van {total} artikelen</span>
        <Button type="button" variant="secondary" disabled={loading || saving || offset + LIMIT >= total}
          onClick={() => setOffset((value) => value + LIMIT)}>Volgende 100</Button>
      </div>
    </ScreenCard>
  </AppShell>
}
