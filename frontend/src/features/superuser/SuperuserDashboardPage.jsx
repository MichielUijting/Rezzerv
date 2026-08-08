import { useEffect, useMemo, useState } from 'react'
import Header from '../../ui/Header.jsx'
import ScreenCard from '../../ui/ScreenCard.jsx'
import Tabs from '../../ui/Tabs.jsx'
import Button from '../../ui/Button.jsx'
import DataTable from '../../ui/DataTable.jsx'
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

function ReadOnlyTable({ rows, dataTestId }) {
  const columns = useMemo(() => {
    const keys = []
    for (const row of rows || []) {
      for (const key of Object.keys(row || {})) {
        if (!keys.includes(key)) keys.push(key)
      }
    }
    return keys.map((key, index) => ({
      key,
      header: key.replaceAll('_', ' '),
      width: index === 0 ? 190 : 145,
      sortable: true,
      filterable: true,
      filterPlaceholder: index === 0 ? 'Zoek' : 'Filter',
      getValue: (row) => row?.[key] == null ? '' : String(row[key]),
    }))
  }, [rows])

  return (
    <DataTable
      columns={columns}
      data={rows || []}
      dataTestId={dataTestId}
      emptyMessage="Geen gegevens beschikbaar voor dit huishouden in dit onderdeel."
      defaultSort={columns[0] ? { key: columns[0].key, direction: 'asc' } : null}
    />
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
      {screen === 'diagnose' ? <Diagnostics data={overview.diagnostics} /> : !screenData ? <p>Gegevens worden geladen…</p> : <ReadOnlyTable rows={screenData.rows || []} dataTestId={`superuser-${screen}-table`} />}
      <h3 style={{ marginTop: 24 }}>Gebruikers</h3>
      <ReadOnlyTable rows={overview.members || []} dataTestId="superuser-household-members-table" />
    </section>
  )
}

function HouseholdsSection() {
  const [items, setItems] = useState([])
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')
  const [selectedId, setSelectedId] = useState(null)

  async function loadHouseholds() {
    setLoading(true); setError('')
    try {
      const response = await fetchJsonWithAuth('/api/superuser/households')
      const payload = await response.json().catch(() => ({}))
      if (!response.ok) throw new Error(payload?.detail || 'Huishoudens konden niet worden geladen.')
      setItems(payload.items || [])
    } catch (e) { setError(String(e?.message || e)) } finally { setLoading(false) }
  }

  useEffect(() => { loadHouseholds() }, [])

  const columns = useMemo(() => [
    {
      key: 'name', header: 'Huishouden', width: 250, sortable: true, filterable: true,
      filterPlaceholder: 'Zoek', getValue: (row) => row.name || row.household_id || '',
    },
    {
      key: 'member_count', header: 'Gebruikers', width: 120, sortable: true, align: 'right',
      getValue: (row) => row.member_count ?? 0,
    },
    {
      key: 'last_active_at', header: 'Laatst actief', width: 190, sortable: true, filterable: true,
      filterPlaceholder: 'Filter', getValue: (row) => row.last_active_at ? String(row.last_active_at) : '—',
    },
    {
      key: 'receipt_count', header: 'Bonnen', width: 110, sortable: true, align: 'right',
      getValue: (row) => row.receipt_count ?? 0,
    },
    {
      key: 'status', header: 'Status', width: 130, sortable: true, filterable: true,
      filterPlaceholder: 'Filter', getValue: (row) => row.status || 'active',
    },
  ], [])

  if (selectedId) return <HouseholdInspector householdId={selectedId} onBack={() => setSelectedId(null)} />

  return (
    <section aria-label="Huishoudens" data-testid="superuser-households">
      <h2 style={{ marginTop: 0, fontSize: 20 }}>Huishoudens</h2>
      <p style={{ marginTop: 0 }}>Dubbelklik op een huishouden om het alleen-lezen te bekijken.</p>
      {error && <div role="alert">{error}</div>}
      {loading ? <p>Huishoudens worden geladen…</p> : (
        <DataTable
          columns={columns}
          data={items}
          dataTestId="superuser-households-table"
          getRowKey={(row) => row.household_id}
          defaultSort={{ key: 'name', direction: 'asc' }}
          emptyMessage="Geen huishoudens gevonden."
          renderRow={(item) => (
            <tr
              key={item.household_id}
              onDoubleClick={() => setSelectedId(item.household_id)}
              title="Dubbelklik om dit huishouden alleen-lezen te bekijken"
            >
              {columns.map((column) => (
                <td key={column.key} className={column.align === 'right' ? 'rz-num' : ''}>
                  {String(column.getValue(item) ?? '')}
                </td>
              ))}
            </tr>
          )}
        />
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
