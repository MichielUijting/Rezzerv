import { useEffect, useMemo, useState } from 'react'
import Card from '../../ui/Card.jsx'
import DataTable from '../../ui/DataTable.jsx'
import { fetchJsonWithAuth } from '../../lib/authSession.js'

const PAGE_SIZE = 10

function formatDateTimeToSeconds(value) {
  if (value == null || value === '') return '—'
  const text = String(value)
  const match = text.match(/^(\d{4}-\d{2}-\d{2})[T ](\d{2}:\d{2}:\d{2})/)
  return match ? `${match[1]} ${match[2]}` : text
}

function MetricCard({ label, value, detail = '' }) {
  return (
    <Card>
      <div style={{ minWidth: 150 }}>
        <div style={{ fontSize: 14 }}>{label}</div>
        <div style={{ fontSize: 28, marginTop: 4 }}>{value}</div>
        {detail ? <div style={{ fontSize: 13, marginTop: 5 }}>{detail}</div> : null}
      </div>
    </Card>
  )
}

export default function SuperuserUsageSection({ onOpenHousehold }) {
  const [data, setData] = useState(null)
  const [error, setError] = useState('')

  useEffect(() => {
    let cancelled = false
    fetchJsonWithAuth('/api/superuser/usage')
      .then(async (response) => {
        const payload = await response.json().catch(() => ({}))
        if (!response.ok) throw new Error(payload?.detail || 'Gebruiksinformatie kon niet worden geladen.')
        if (!cancelled) setData(payload)
      })
      .catch((loadError) => { if (!cancelled) setError(String(loadError?.message || loadError)) })
    return () => { cancelled = true }
  }, [])

  const columns = useMemo(() => [
    { key: 'household_name', header: 'Huishouden', width: 260, sortable: true, filterable: true, filterPlaceholder: 'Zoek', getValue: (row) => row.household_name || row.household_id || '' },
    { key: 'active_member_count', header: 'Actieve gebruikers', width: 150, sortable: true, align: 'right', getValue: (row) => row.active_member_count ?? 0 },
    { key: 'receipt_count', header: 'Kassabonnen', width: 125, sortable: true, align: 'right', getValue: (row) => row.receipt_count ?? 0 },
    { key: 'inventory_event_count', header: 'Voorraadmutaties', width: 160, sortable: true, align: 'right', getValue: (row) => row.inventory_event_count ?? 0 },
    { key: 'support_thread_count', header: 'Meldingen', width: 120, sortable: true, align: 'right', getValue: (row) => row.support_thread_count ?? 0 },
    { key: 'last_active_at', header: 'Laatst actief', width: 190, sortable: true, filterable: true, filterPlaceholder: 'Filter', getValue: (row) => formatDateTimeToSeconds(row.last_active_at) },
  ], [])

  if (error) return <div role="alert">{error}</div>
  if (!data) return <div role="status">Gebruiksinformatie wordt geladen…</div>

  const metrics = data.metrics || {}
  return (
    <section aria-label="Superuser gebruik" data-testid="superuser-usage">
      <h2 style={{ marginTop: 0, fontSize: 20 }}>Gebruik</h2>
      <p style={{ marginTop: 0 }}>
        Dit overzicht gebruikt uitsluitend gegevens die Rezzerv al voor de normale werking vastlegt. Er is geen nieuwe gebruikers- of schermtracking toegevoegd.
      </p>

      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit,minmax(180px,1fr))', gap: 12, marginBottom: 24 }}>
        <MetricCard label="Actieve huishoudens" value={metrics.active_households ?? 0} />
        <MetricCard label="Huishoudens met sessieactiviteit" value={metrics.households_with_session_activity ?? 0} />
        <MetricCard label="Kassabonnen" value={metrics.receipt_count ?? 0} />
        <MetricCard label="Voorraadmutaties" value={metrics.inventory_event_count ?? 0} />
        <MetricCard label="Meldingen" value={metrics.support_thread_count ?? 0} />
      </div>

      <h2 style={{ fontSize: 20, marginBottom: 8 }}>Gebruik per huishouden</h2>
      <p style={{ marginTop: 0 }}>Dubbelklik op een huishouden om de bestaande alleen-lezen huishoudinzage te openen.</p>
      <DataTable
        columns={columns}
        data={data.items || []}
        dataTestId="superuser-usage-table"
        getRowKey={(row) => row.household_id}
        defaultSort={{ key: 'last_active_at', direction: 'desc' }}
        emptyMessage="Geen actieve huishoudens gevonden."
        pagination
        pageSize={PAGE_SIZE}
        renderRow={(item) => (
          <tr
            key={item.household_id}
            onDoubleClick={() => onOpenHousehold?.(item.household_id)}
            title="Dubbelklik om dit huishouden alleen-lezen te bekijken"
          >
            {columns.map((column) => (
              <td key={column.key} className={column.align === 'right' ? 'rz-num' : ''}>{String(column.getValue(item) ?? '')}</td>
            ))}
          </tr>
        )}
      />
    </section>
  )
}
