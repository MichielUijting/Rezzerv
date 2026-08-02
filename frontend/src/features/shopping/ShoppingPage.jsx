import { useEffect, useMemo, useState } from 'react'
import AppShell from '../../app/AppShell.jsx'
import Card from '../../ui/Card.jsx'
import Button from '../../ui/Button.jsx'
import Table from '../../ui/Table.jsx'
import { fetchJsonWithAuth } from '../../lib/authSession.js'

const EMPTY_FORM = {
  article_name: '',
  quantity: '',
  volume: '',
  unit: '',
  note: '',
}

const UNITS = [
  ['', 'Geen'],
  ['stuk', 'stuk'],
  ['stuks', 'stuks'],
  ['gram', 'gram'],
  ['kilogram', 'kilogram'],
  ['milliliter', 'milliliter'],
  ['liter', 'liter'],
  ['verpakking', 'verpakking'],
]

async function requestJson(url, options = {}) {
  const response = await fetchJsonWithAuth(url, options)
  if (response.status === 204) return null
  const payload = await response.json().catch(() => ({}))
  if (!response.ok) {
    const detail = typeof payload?.detail === 'string' ? payload.detail : 'Verzoek mislukt'
    throw new Error(detail)
  }
  return payload
}

function formatNumber(value) {
  if (value === null || value === undefined || value === '') return ''
  return new Intl.NumberFormat('nl-NL', { maximumFractionDigits: 3 }).format(Number(value))
}

export default function ShoppingPage() {
  const [list, setList] = useState({ items: [], item_count: 0 })
  const [form, setForm] = useState(EMPTY_FORM)
  const [search, setSearch] = useState('')
  const [checkedFilter, setCheckedFilter] = useState('all')
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState('')
  const [message, setMessage] = useState('')

  async function loadList() {
    setLoading(true)
    setError('')
    try {
      const payload = await requestJson('/api/shopping-list')
      setList(payload)
    } catch (loadError) {
      setError(loadError?.message || 'Winkellijst kon niet worden geladen.')
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    loadList()
  }, [])

  const visibleItems = useMemo(() => {
    const query = search.trim().toLowerCase()
    return (list.items || []).filter((item) => {
      if (query && !String(item.article_name || '').toLowerCase().includes(query)) return false
      if (checkedFilter === 'open' && item.checked) return false
      if (checkedFilter === 'checked' && !item.checked) return false
      return true
    })
  }, [list.items, search, checkedFilter])

  async function addItem(event) {
    event.preventDefault()
    if (!form.article_name.trim()) {
      setError('Artikelnaam is verplicht.')
      return
    }
    setSaving(true)
    setError('')
    setMessage('')
    try {
      await requestJson('/api/shopping-list/items', {
        method: 'POST',
        body: JSON.stringify({
          ...form,
          quantity: form.quantity === '' ? null : form.quantity,
          volume: form.volume === '' ? null : form.volume,
        }),
      })
      setForm(EMPTY_FORM)
      setMessage('Artikel toegevoegd aan de winkellijst.')
      await loadList()
    } catch (saveError) {
      setError(saveError?.message || 'Artikel kon niet worden toegevoegd.')
    } finally {
      setSaving(false)
    }
  }

  async function updateItem(item, patch) {
    setSaving(true)
    setError('')
    setMessage('')
    try {
      await requestJson(`/api/shopping-list/items/${encodeURIComponent(item.id)}`, {
        method: 'PUT',
        body: JSON.stringify(patch),
      })
      await loadList()
    } catch (saveError) {
      setError(saveError?.message || 'Winkellijstregel kon niet worden bijgewerkt.')
    } finally {
      setSaving(false)
    }
  }

  async function deleteItem(item) {
    if (!window.confirm(`${item.article_name} van de winkellijst verwijderen?`)) return
    setSaving(true)
    setError('')
    setMessage('')
    try {
      await requestJson(`/api/shopping-list/items/${encodeURIComponent(item.id)}`, {
        method: 'DELETE',
      })
      setMessage('Artikel verwijderd van de winkellijst.')
      await loadList()
    } catch (deleteError) {
      setError(deleteError?.message || 'Artikel kon niet worden verwijderd.')
    } finally {
      setSaving(false)
    }
  }

  async function completeShopping() {
    if (!window.confirm('De actuele winkellijst wordt leeggemaakt. Voorraad en bronlijsten blijven ongewijzigd.')) return
    setSaving(true)
    setError('')
    setMessage('')
    try {
      await requestJson('/api/shopping-list/complete', { method: 'POST' })
      setMessage('Winkelen is afgerond. De winkellijst is leeggemaakt.')
      await loadList()
    } catch (completeError) {
      setError(completeError?.message || 'Winkelen kon niet worden afgerond.')
    } finally {
      setSaving(false)
    }
  }

  return (
    <AppShell title="Winkelen">
      <Card>
        <div style={{ display: 'grid', gap: 20, width: '100%' }} data-testid="shopping-page">
          <div>
            <h2 style={{ margin: 0 }}>Inkooplijst — {Number(list.item_count || 0)} artikelen</h2>
            <p style={{ marginBottom: 0, color: '#667085' }}>
              Stel de winkellijst samen en vink artikelen tijdens het winkelen af.
            </p>
          </div>

          <form onSubmit={addItem} style={{ display: 'grid', gridTemplateColumns: 'minmax(220px, 2fr) repeat(3, minmax(110px, 1fr)) minmax(220px, 2fr) auto', gap: 12, alignItems: 'end' }}>
            <label className="rz-input-field">
              <span className="rz-label">Artikel</span>
              <input className="rz-input" value={form.article_name} onChange={(event) => setForm((current) => ({ ...current, article_name: event.target.value }))} placeholder="Artikelnaam" />
            </label>
            <label className="rz-input-field">
              <span className="rz-label">Aantal</span>
              <input className="rz-input" inputMode="decimal" value={form.quantity} onChange={(event) => setForm((current) => ({ ...current, quantity: event.target.value }))} />
            </label>
            <label className="rz-input-field">
              <span className="rz-label">Volume</span>
              <input className="rz-input" inputMode="decimal" value={form.volume} onChange={(event) => setForm((current) => ({ ...current, volume: event.target.value }))} />
            </label>
            <label className="rz-input-field">
              <span className="rz-label">Eenheid</span>
              <select className="rz-input" value={form.unit} onChange={(event) => setForm((current) => ({ ...current, unit: event.target.value }))}>
                {UNITS.map(([value, label]) => <option key={value} value={value}>{label}</option>)}
              </select>
            </label>
            <label className="rz-input-field">
              <span className="rz-label">Opmerking</span>
              <input className="rz-input" value={form.note} onChange={(event) => setForm((current) => ({ ...current, note: event.target.value }))} placeholder="Optioneel" />
            </label>
            <Button type="submit" disabled={saving}>Toevoegen</Button>
          </form>

          <div style={{ display: 'grid', gridTemplateColumns: 'minmax(220px, 1fr) 220px', gap: 12 }}>
            <input className="rz-input" value={search} onChange={(event) => setSearch(event.target.value)} placeholder="Zoeken" aria-label="Zoeken" />
            <select className="rz-input" value={checkedFilter} onChange={(event) => setCheckedFilter(event.target.value)} aria-label="Filter gekocht">
              <option value="all">Alle artikelen</option>
              <option value="open">Nog te kopen</option>
              <option value="checked">Gekocht</option>
            </select>
          </div>

          {error ? <div role="alert" style={{ color: '#9b1c1c' }}>{error}</div> : null}
          {message ? <div role="status" style={{ color: '#1A3E2B' }}>{message}</div> : null}

          <Table dataTestId="shopping-list-table" resizableColumns>
            <thead>
              <tr className="rz-table-header">
                <th>Gekocht</th>
                <th>Artikel</th>
                <th className="rz-num">Aantal</th>
                <th className="rz-num">Volume</th>
                <th>Eenheid</th>
                <th>Opmerking</th>
                <th>Actie</th>
              </tr>
            </thead>
            <tbody>
              {loading ? (
                <tr><td colSpan={7}>Winkellijst laden…</td></tr>
              ) : visibleItems.length === 0 ? (
                <>
                  <tr><td colSpan={7}>Nog geen artikelen op de winkellijst.</td></tr>
                  <tr><td colSpan={7}>&nbsp;</td></tr>
                  <tr><td colSpan={7}>&nbsp;</td></tr>
                </>
              ) : visibleItems.map((item) => (
                <tr key={item.id}>
                  <td>
                    <input type="checkbox" checked={Boolean(item.checked)} onChange={(event) => updateItem(item, { checked: event.target.checked })} aria-label={`Gekocht ${item.article_name}`} style={{ accentColor: '#1A3E2B', width: 16, height: 16 }} />
                  </td>
                  <td>{item.article_name}</td>
                  <td className="rz-num">{formatNumber(item.quantity)}</td>
                  <td className="rz-num">{formatNumber(item.volume)}</td>
                  <td>{item.unit}</td>
                  <td>{item.note}</td>
                  <td><Button type="button" variant="secondary" onClick={() => deleteItem(item)} disabled={saving}>Verwijderen</Button></td>
                </tr>
              ))}
            </tbody>
          </Table>

          <div style={{ display: 'flex', justifyContent: 'flex-end' }}>
            <Button type="button" onClick={completeShopping} disabled={saving || Number(list.item_count || 0) === 0}>
              Winkelen afgerond
            </Button>
          </div>
        </div>
      </Card>
    </AppShell>
  )
}
