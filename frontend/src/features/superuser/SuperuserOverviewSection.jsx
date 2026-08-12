import { useEffect, useMemo, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import Button from '../../ui/Button.jsx'
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

export default function SuperuserOverviewSection() {
  const navigate = useNavigate()
  const [data, setData] = useState(null)
  const [error, setError] = useState('')

  useEffect(() => {
    let cancelled = false
    fetchJsonWithAuth('/api/superuser/overview')
      .then(async (response) => {
        const payload = await response.json().catch(() => ({}))
        if (!response.ok) throw new Error(payload?.detail || 'Platformoverzicht kon niet worden geladen.')
        if (!cancelled) setData(payload)
      })
      .catch((loadError) => { if (!cancelled) setError(String(loadError?.message || loadError)) })
    return () => { cancelled = true }
  }, [])

  const columns = useMemo(() => [
    { key: 'household_name', header: 'Huishouden', width: 260, sortable: true, filterable: true, filterPlaceholder: 'Zoek', getValue: (row) => row.household_name || row.household_id || '' },
    { key: 'signal', header: 'Aandachtspunt', width: 420, sortable: true, filterable: true, filterPlaceholder: 'Filter', getValue: (row) => row.signal || '' },
    { key: 'signal_count', header: 'Aantal', width: 110, sortable: true, align: 'right', getValue: (row) => row.signal_count ?? 0 },
  ], [])

  if (error) return <div role="alert">{error}</div>
  if (!data) return <div role="status">Platformoverzicht wordt geladen…</div>

  const metrics = data.metrics || {}
  const notificationRoute = data.notification_route || '/superuser/meldingen'

  function openHouseholdNotifications(householdId) {
    if (!householdId) return
    navigate(`/superuser/meldingen?householdId=${encodeURIComponent(householdId)}`)
  }

  return (
    <section aria-label="Superuser overzicht" data-testid="superuser-platform-overview" style={{ minWidth: 0, width: '100%' }}>
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 16, flexWrap: 'wrap', marginBottom: 16 }}>
        <div>
          <h2 style={{ margin: 0, fontSize: 20 }}>Platformoverzicht</h2>
          <p style={{ marginBottom: 0 }}>Actuele platformstatus en aandachtspunten op basis van bestaande Rezzerv-gegevens.</p>
        </div>
        <Button type="button" onClick={() => navigate(notificationRoute)}>Meldingen ({metrics.open_notifications ?? 0})</Button>
      </div>

      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit,minmax(180px,1fr))', gap: 12, marginBottom: 24 }}>
        <MetricCard label="Actieve huishoudens" value={metrics.active_households ?? 0} />
        <MetricCard label="Actieve gebruikers" value={metrics.active_users ?? 0} />
        <MetricCard label="Kassabonnen" value={metrics.receipt_count ?? 0} detail={`Laatste: ${formatDateTimeToSeconds(metrics.last_receipt_at)}`} />
        <MetricCard label="Open meldingen" value={metrics.open_notifications ?? 0} detail="Open + In behandeling" />
      </div>

      <h2 style={{ fontSize: 20, marginBottom: 8 }}>Aandacht vereist</h2>
      <p style={{ marginTop: 0 }}>Dubbelklik op een aandachtspunt om direct de meldingen van het betreffende huishouden te openen.</p>
      <DataTable
        columns={columns}
        data={data.attention_items || []}
        dataTestId="superuser-attention-table"
        getRowKey={(row) => row.household_id}
        defaultSort={{ key: 'signal_count', direction: 'desc' }}
        emptyMessage="Geen bestaande aandachtspunten gevonden."
        pagination
        pageSize={PAGE_SIZE}
        renderRow={(item) => (
          <tr
            key={item.household_id}
            onDoubleClick={() => openHouseholdNotifications(item.household_id)}
            title="Dubbelklik om de meldingen van dit huishouden te bekijken"
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
