import { useEffect, useMemo, useState } from 'react'
import DataTable from '../../ui/DataTable.jsx'
import { fetchJsonWithAuth } from '../../lib/authSession.js'

const PAGE_SIZE = 10

function formatDateTimeToSeconds(value) {
  if (value == null || value === '') return '—'
  const text = String(value)
  const match = text.match(/^(\d{4}-\d{2}-\d{2})[T ](\d{2}:\d{2}:\d{2})/)
  return match ? `${match[1]} ${match[2]}` : text
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

  return (
    <section aria-label="Superuser gebruik" data-testid="superuser-usage" style={{ minWidth: 0, width: '100%' }}>
      <h2 style={{ marginTop: 0, fontSize: 20 }}>Gebruik</h2>
      <p style={{ marginTop: 0 }}>
        Vergelijk hier de operationele activiteit van huishoudens: aantallen gebruikers, kassabonnen, voorraadmutaties, meldingen en het laatste activiteitstijdstip.
        Dit tabblad gaat dus over gebruiksvolume en activiteit; <strong>Overzicht</strong> gaat over platformstatus en aandachtspunten.
      </p>
      <p>
        Er wordt uitsluitend gebruikgemaakt van gegevens die Rezzerv al voor de normale werking vastlegt. Er is geen nieuwe gebruikers- of schermtracking toegevoegd.
      </p>

      <h2 style={{ fontSize: 20, marginBottom: 8 }}>Operationeel gebruik per huishouden</h2>
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
