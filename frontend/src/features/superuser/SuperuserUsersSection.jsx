import { useEffect, useMemo, useState } from 'react'
import DataTable from '../../ui/DataTable.jsx'
import Checkbox from '../../ui/Checkbox.jsx'
import Button from '../../ui/Button.jsx'
import { fetchJsonWithAuth } from '../../lib/authSession.js'

const PAGE_SIZE = 10

const DUTCH_VALUE_LABELS = {
  active: 'Actief', inactive: 'Inactief', owner: 'Eigenaar', admin: 'Beheerder', member: 'Lid',
  user: 'Gebruiker', viewer: 'Lezer', pending: 'In behandeling', archived: 'Gearchiveerd',
}

function dutchValue(value) {
  if (value == null || value === '') return ''
  const text = String(value)
  return DUTCH_VALUE_LABELS[text.trim().toLowerCase()] || text
}

function formatDateTimeToSeconds(value) {
  if (value == null || value === '') return '—'
  const text = String(value)
  const match = text.match(/^(\d{4}-\d{2}-\d{2})[T ](\d{2}:\d{2}:\d{2})/)
  return match ? `${match[1]} ${match[2]}` : text
}

function membershipKey(row, index = 0) {
  return `${row.user_id || row.email || 'user'}::${row.household_id || 'household'}::${index}`
}

function csvValue(value) {
  return `"${String(value ?? '').replaceAll('"', '""')}"`
}

export default function SuperuserUsersSection({ onOpenHousehold }) {
  const [items, setItems] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [showTechnicalIds, setShowTechnicalIds] = useState(false)
  const [selectedKeys, setSelectedKeys] = useState([])

  useEffect(() => {
    let cancelled = false
    async function load() {
      try {
        const response = await fetchJsonWithAuth('/api/superuser/households')
        const payload = await response.json().catch(() => ({}))
        if (!response.ok) throw new Error(payload?.detail || 'Gebruikers konden niet worden geladen.')
        const households = payload.items || []
        const memberships = await Promise.all(households.map(async (household) => {
          const householdId = String(household.household_id || '')
          if (!householdId) return []
          const detailResponse = await fetchJsonWithAuth(`/api/superuser/households/${encodeURIComponent(householdId)}`)
          const detail = await detailResponse.json().catch(() => ({}))
          if (!detailResponse.ok) throw new Error(detail?.detail || `Gebruikers van huishouden ${householdId} konden niet worden geladen.`)
          return (detail.members || []).map((member) => ({
            ...member,
            household_id: householdId,
            household_name: household.name || detail?.household?.name || householdId,
            household_last_active_at: household.last_active_at || null,
          }))
        }))
        if (!cancelled) setItems(memberships.flat())
      } catch (e) {
        if (!cancelled) setError(String(e?.message || e))
      } finally {
        if (!cancelled) setLoading(false)
      }
    }
    load()
    return () => { cancelled = true }
  }, [])

  useEffect(() => {
    const validKeys = new Set(items.map((row, index) => membershipKey(row, index)))
    setSelectedKeys((current) => current.filter((key) => validKeys.has(key)))
  }, [items])

  const dataColumns = useMemo(() => {
    const result = [
      { key: 'email', header: 'Gebruiker', width: 300, sortable: true, filterable: true, filterPlaceholder: 'Zoek', getValue: (row) => row.email || '—' },
      { key: 'household_name', header: 'Huishouden', width: 240, sortable: true, filterable: true, filterPlaceholder: 'Filter', getValue: (row) => row.household_name || row.household_id || '—' },
      { key: 'role', header: 'Rol', width: 150, sortable: true, filterable: true, filterPlaceholder: 'Filter', getValue: (row) => dutchValue(row.role) || '—' },
      { key: 'status', header: 'Status', width: 140, sortable: true, filterable: true, filterPlaceholder: 'Filter', getValue: (row) => dutchValue(row.status || 'active') },
      { key: 'last_active_at', header: 'Laatst actief', width: 190, sortable: true, filterable: true, filterPlaceholder: 'Filter', getValue: (row) => formatDateTimeToSeconds(row.last_active_at || row.updated_at || row.household_last_active_at) },
      { key: 'created_at', header: 'Toegevoegd op', width: 190, sortable: true, filterable: true, filterPlaceholder: 'Filter', getValue: (row) => formatDateTimeToSeconds(row.created_at) },
    ]
    if (showTechnicalIds) {
      result.push(
        { key: 'user_id', header: 'Technisch gebruiker-ID', width: 260, sortable: true, filterable: true, filterPlaceholder: 'Filter', getValue: (row) => row.user_id || '—' },
        { key: 'household_id', header: 'Technisch huishouden-ID', width: 220, sortable: true, filterable: true, filterPlaceholder: 'Filter', getValue: (row) => row.household_id || '—' },
      )
    }
    return result
  }, [showTechnicalIds])

  const allSelected = items.length > 0 && items.every((row, index) => selectedKeys.includes(membershipKey(row, index)))
  const columns = useMemo(() => [
    {
      key: 'selection',
      header: <Checkbox checked={allSelected} onChange={(event) => setSelectedKeys(event.target.checked ? items.map((row, index) => membershipKey(row, index)) : [])} aria-label="Selecteer alle gebruikersregels" />,
      width: 60,
      sortable: false,
      filterable: false,
      className: 'rz-center',
    },
    ...dataColumns,
  ], [allSelected, dataColumns, items])

  const selectedRows = useMemo(() => items.filter((row, index) => selectedKeys.includes(membershipKey(row, index))), [items, selectedKeys])

  function toggleRow(key, checked) {
    setSelectedKeys((current) => checked ? [...new Set([...current, key])] : current.filter((item) => item !== key))
  }

  function exportSelectedRows() {
    if (selectedRows.length === 0) return
    const rowsForExport = [
      dataColumns.map((column) => column.header),
      ...selectedRows.map((row) => dataColumns.map((column) => column.getValue(row))),
    ]
    const csv = `\uFEFF${rowsForExport.map((row) => row.map(csvValue).join(';')).join('\r\n')}`
    const blob = new Blob([csv], { type: 'text/csv;charset=utf-8' })
    const url = URL.createObjectURL(blob)
    const link = document.createElement('a')
    link.href = url
    link.download = 'superuser-gebruikers-geselecteerd.csv'
    document.body.appendChild(link)
    link.click()
    link.remove()
    URL.revokeObjectURL(url)
  }

  return (
    <section aria-label="Gebruikers" data-testid="superuser-users-section" style={{ minWidth: 0, width: '100%' }}>
      <h2 style={{ marginTop: 0, fontSize: 20 }}>Gebruikers</h2>
      <p style={{ marginTop: 0 }}>Platformbrede, alleen-lezen inzage in gebruikers en hun huishoudkoppelingen. Dubbelklik op een regel om het huishouden te openen.</p>
      <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 12 }}>
        <Checkbox checked={showTechnicalIds} onChange={(event) => setShowTechnicalIds(event.target.checked)} aria-label="Technische ID's tonen in gebruikersoverzicht" />
        <span>Technische ID's: <strong>{showTechnicalIds ? 'Aan' : 'Uit'}</strong></span>
      </div>
      {error && <div role="alert">{error}</div>}
      {loading ? <p role="status">Gebruikers worden geladen…</p> : (
        <DataTable
          columns={columns}
          data={items}
          dataTestId="superuser-users-table"
          getRowKey={(row, index) => membershipKey(row, index)}
          defaultSort={{ key: 'email', direction: 'asc' }}
          emptyMessage="Geen gebruikers gevonden."
          pagination
          pageSize={PAGE_SIZE}
          paginationActions={<Button type="button" onClick={exportSelectedRows} disabled={selectedRows.length === 0}>Exporteren</Button>}
          renderRow={(row, index) => {
            const key = membershipKey(row, index)
            return (
              <tr key={key} onDoubleClick={() => onOpenHousehold?.(row.household_id)} title="Dubbelklik om het huishouden alleen-lezen te bekijken">
                <td className="rz-center"><Checkbox checked={selectedKeys.includes(key)} onChange={(event) => toggleRow(key, event.target.checked)} aria-label={`Selecteer gebruiker ${row.email || index + 1}`} /></td>
                {dataColumns.map((column) => <td key={column.key}>{String(column.getValue(row) ?? '')}</td>)}
              </tr>
            )
          }}
        />
      )}
    </section>
  )
}
