import { useEffect, useMemo, useState } from 'react'
import Header from '../../ui/Header.jsx'
import ScreenCard from '../../ui/ScreenCard.jsx'
import Tabs from '../../ui/Tabs.jsx'
import Button from '../../ui/Button.jsx'
import { fetchJsonWithAuth } from '../../lib/authSession.js'

const TABS = ['Overzicht', 'Huishoudens', 'Gebruik', 'Kassabonnen', 'Systeem']
const HOUSEHOLD_SCREENS = [
  ['start', 'Start'], ['kassa', 'Kassa'], ['uitpakken', 'Uitpakken'], ['voorraad', 'Voorraad'],
  ['bijna_op', 'Bijna op'], ['winkelen', 'Winkelen'], ['prognoses', 'Prognoses'], ['diagnose', 'Diagnose'],
]

function EmptySection({ title }) {
  return (
    <section aria-label={title}>
      <h2 style={{ marginTop: 0, fontSize: 20 }}>{title}</h2>
      <p style={{ marginBottom: 0 }}>Dit onderdeel volgt in een volgende Superuser-release.</p>
    </section>
  )
}

function ReadOnlyTable({ rows }) {
  const columns = useMemo(() => {
    const keys = []
    for (const row of rows || []) for (const key of Object.keys(row || {})) if (!keys.includes(key)) keys.push(key)
    return keys
  }, [rows])
  if (!rows?.length) return <p>Geen gegevens beschikbaar voor dit huishouden in dit onderdeel.</p>
  return (
    <div style={{ overflowX: 'auto' }}>
      <table className="rz-table" style={{ width: '100%' }}>
        <thead><tr>{columns.map((key) => <th key={key}>{key.replaceAll('_', ' ')}</th>)}</tr></thead>
        <tbody>{rows.map((row, index) => (
          <tr key={row.id || `${index}`}>
            {columns.map((key) => <td key={key}>{row?.[key] == null ? '' : String(row[key])}</td>)}
          </tr>
        ))}</tbody>
      </table>
    </div>
  )
}

function Diagnostics({ data }) {
  const d = data || {}
  const cards = [
    ['Kassabonnen', d.receipt_count ?? 0],
    ['Voorraadregels', d.inventory_count ?? 0],
    ['Voorraadevents', d.inventory_event_count ?? 0],
    ['Uitpakbatches', d.unpack_batch_count ?? 0],
    ['Negatieve voorraad', d.negative_inventory_count ?? 0],
  ]
  return (
    <div>
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit,minmax(150px,1fr))', gap: 12, marginBottom: 18 }}>
        {cards.map(([label, value]) => (
          <div key={label} style={{ border: '1px solid #d4ddd4', borderRadius: 6, padding: 12 }}>
            <div style={{ fontSize: 13 }}>{label}</div><div style={{ fontSize: 24 }}>{value}</div>
          </div>
        ))}
      </div>
      <p><strong>Laatste kassabon:</strong> {d.last_receipt_at ? String(d.last_receipt_at) : '—'}</p>
      <p><strong>Laatste voorraadmutatie:</strong> {d.last_inventory_event_at ? String(d.last_inventory_event_at) : '—'}</p>
      {(d.flags || []).length > 0 && <div>{d.flags.map((flag) => <p key={flag.code}>⚠ {flag.label}</p>)}</div>}
    </div>
  )
}

function HouseholdInspector({ householdId, onBack }) {
  const [overview, setOverview] = useState(null)
  const [screen, setScreen] = useState('diagnose')
  const [screenData, setScreenData] = useState(null)
  const [error, setError] = useState('')

  useEffect(() => {
    let cancelled = false
    fetchJsonWithAuth(`/api/superuser/households/${encodeURIComponent(householdId)}`)
      .then(async (response) => {
        const payload = await response.json().catch(() => ({}))
        if (!response.ok) throw new Error(payload?.detail || 'Huishouden kon niet worden geopend.')
        if (!cancelled) setOverview(payload)
      })
      .catch((e) => { if (!cancelled) setError(String(e?.message || e)) })
    return () => { cancelled = true }
  }, [householdId])

  useEffect(() => {
    let cancelled = false
    if (!overview) return () => {}
    if (screen === 'diagnose') { setScreenData({ diagnostics: overview.diagnostics, rows: [] }); return () => {} }
    fetchJsonWithAuth(`/api/superuser/households/${encodeURIComponent(householdId)}/screens/${screen}`)
      .then(async (response) => {
        const payload = await response.json().catch(() => ({}))
        if (!response.ok) throw new Error(payload?.detail || 'Read-only scherm kon niet worden geladen.')
        if (!cancelled) setScreenData(payload)
      })
      .catch((e) => { if (!cancelled) setError(String(e?.message || e)) })
    return () => { cancelled = true }
  }, [householdId, overview, screen])

  if (error) return <div role="alert">{error}</div>
  if (!overview) return <div role="status">Huishouden wordt geladen…</div>
  const name = overview.household?.name || overview.household?.household_id || householdId
  return (
    <section data-testid="superuser-household-inspector">
      <div style={{ marginBottom: 12 }}><Button onClick={onBack}>Terug naar huishoudens</Button></div>
      <div style={{ border: '1px solid #d4ddd4', background: '#f7faf7', padding: 12, borderRadius: 6, marginBottom: 14 }}>
        <strong>Superuser — Huishouden {name} — Alleen lezen</strong>
      </div>
      <div style={{ display: 'flex', flexWrap: 'wrap', gap: 7, marginBottom: 18 }}>
        {HOUSEHOLD_SCREENS.map(([key, label]) => (
          <button key={key} type="button" className={screen === key ? 'rz-tab rz-tab-active' : 'rz-tab'} onClick={() => setScreen(key)}>{label}</button>
        ))}
      </div>
      <h2 style={{ fontSize: 20 }}>{HOUSEHOLD_SCREENS.find(([key]) => key === screen)?.[1]}</h2>
      {screen === 'diagnose' ? <Diagnostics data={overview.diagnostics} /> : !screenData ? <p>Gegevens worden geladen…</p> : <ReadOnlyTable rows={screenData.rows || []} />}
      <h3 style={{ marginTop: 24 }}>Gebruikers</h3>
      <ReadOnlyTable rows={overview.members || []} />
    </section>
  )
}

function HouseholdsSection() {
  const [query, setQuery] = useState('')
  const [items, setItems] = useState([])
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')
  const [selectedId, setSelectedId] = useState(null)

  async function loadHouseholds(search = query) {
    setLoading(true); setError('')
    try {
      const response = await fetchJsonWithAuth(`/api/superuser/households?q=${encodeURIComponent(search || '')}`)
      const payload = await response.json().catch(() => ({}))
      if (!response.ok) throw new Error(payload?.detail || 'Huishoudens konden niet worden geladen.')
      setItems(payload.items || [])
    } catch (e) { setError(String(e?.message || e)) } finally { setLoading(false) }
  }

  useEffect(() => { loadHouseholds('') }, [])
  if (selectedId) return <HouseholdInspector householdId={selectedId} onBack={() => setSelectedId(null)} />

  return (
    <section aria-label="Huishoudens" data-testid="superuser-households">
      <h2 style={{ marginTop: 0, fontSize: 20 }}>Huishoudens</h2>
      <form onSubmit={(e) => { e.preventDefault(); loadHouseholds(query) }} style={{ display: 'flex', gap: 8, marginBottom: 14 }}>
        <input className="rz-input" value={query} onChange={(e) => setQuery(e.target.value)} placeholder="Zoek huishouden of ID" aria-label="Zoek huishouden" />
        <Button type="submit">Zoeken</Button>
      </form>
      {error && <div role="alert">{error}</div>}
      {loading ? <p>Huishoudens worden geladen…</p> : (
        <div style={{ overflowX: 'auto' }}><table className="rz-table" style={{ width: '100%' }}>
          <thead><tr><th>Huishouden</th><th>Gebruikers</th><th>Laatst actief</th><th>Bonnen</th><th>Status</th><th></th></tr></thead>
          <tbody>{items.map((item) => <tr key={item.household_id}>
            <td>{item.name || item.household_id}</td><td>{item.member_count ?? 0}</td><td>{item.last_active_at ? String(item.last_active_at) : '—'}</td><td>{item.receipt_count ?? 0}</td><td>{item.status || 'active'}</td>
            <td><Button onClick={() => setSelectedId(item.household_id)}>Bekijken</Button></td>
          </tr>)}</tbody>
        </table></div>
      )}
    </section>
  )
}

export default function SuperuserDashboardPage() {
  const [access, setAccess] = useState(null)
  const [error, setError] = useState('')
  useEffect(() => {
    let cancelled = false
    async function bootstrap() {
      try {
        const response = await fetchJsonWithAuth('/api/superuser/bootstrap')
        const payload = await response.json().catch(() => ({}))
        if (!response.ok) throw new Error(payload?.detail || 'Superuser-toegang kon niet worden gevalideerd.')
        if (cancelled) return
        setAccess(payload)
        await fetchJsonWithAuth('/api/superuser/audit/open', { method: 'POST' })
      } catch (nextError) { if (!cancelled) setError(String(nextError?.message || nextError || 'Superuser-toegang mislukt.')) }
    }
    bootstrap(); return () => { cancelled = true }
  }, [])
  return (
    <div className="rz-screen" data-testid="superuser-dashboard">
      <Header title="Rezzerv Beheercentrum" />
      <div className="rz-content"><div className="rz-content-inner"><ScreenCard fullWidth>
        {error ? <div role="alert">{error}</div> : !access ? <div role="status">Superuser-toegang wordt gecontroleerd…</div> : <>
          <div role="status" aria-label="Superuser alleen-lezen status" style={{ marginBottom: 16, padding: '10px 12px', border: '1px solid #d4ddd4', borderRadius: 6, background: '#f7faf7' }}><strong>Superuser</strong> — beheercentrum. Toegang: <strong>alleen lezen</strong>.</div>
          <Tabs tabs={Array.isArray(access.tabs) ? access.tabs : TABS} defaultTab="Overzicht">{(activeTab) => activeTab === 'Huishoudens' ? <HouseholdsSection /> : <EmptySection title={activeTab} />}</Tabs>
        </>}
      </ScreenCard></div></div>
    </div>
  )
}
