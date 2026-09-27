import React from 'react'
import { API_BASE_URL } from '../../lib/apiClient.js'
import Button from '../../ui/Button.jsx'
import Card from '../../ui/Card.jsx'
import DataTable from '../../ui/DataTable.jsx'
import Header from '../../ui/Header.jsx'
import './settingsHousehold.css'

const FRONTTEAM_ROLE_KEY = 'platform.frontteam'

async function api(path, options = {}) {
  const response = await fetch(`${API_BASE_URL}${path}`, {
    credentials: 'include',
    headers: { Accept: 'application/json', 'Content-Type': 'application/json', ...(options.headers || {}) },
    ...options,
  })
  const payload = await response.json().catch(() => ({}))
  if (!response.ok) throw new Error(payload?.detail || `Actie mislukt (${response.status})`)
  return payload
}

function isActiveMember(member) {
  return (member.platform_role_keys || []).includes(FRONTTEAM_ROLE_KEY) && member.frontteam_status === 'active'
}

export default function SettingsFrontteamPage() {
  const [members, setMembers] = React.useState([])
  const [email, setEmail] = React.useState('')
  const [loading, setLoading] = React.useState(true)
  const [busy, setBusy] = React.useState(false)
  const [selectedIds, setSelectedIds] = React.useState([])
  const [error, setError] = React.useState('')
  const [result, setResult] = React.useState('')

  const load = React.useCallback(async () => {
    setLoading(true); setError('')
    try {
      const payload = await api('/api/platform/frontteam-management')
      const nextMembers = Array.isArray(payload?.frontteam_memberships) ? payload.frontteam_memberships : []
      setMembers(nextMembers)
      setSelectedIds((current) => current.filter((id) => nextMembers.some((member) => member.user_id === id)))
    } catch (err) { setError(err.message) } finally { setLoading(false) }
  }, [])

  React.useEffect(() => { load() }, [load])

  async function addMember(event) {
    event.preventDefault()
    const normalized = email.trim()
    if (!normalized) { setError('Vul een e-mailadres in.'); return }
    setBusy(true); setError(''); setResult('')
    try {
      await api('/api/platform/frontteam-management/members', {
        method: 'POST', body: JSON.stringify({ email: normalized }),
      })
      setEmail('')
      setResult(`${normalized} is toegevoegd aan het Frontteam.`)
      await load()
    } catch (err) { setError(err.message) } finally { setBusy(false) }
  }

  function toggleMember(userId, checked) {
    setSelectedIds((current) => checked
      ? Array.from(new Set([...current, userId]))
      : current.filter((id) => id !== userId))
  }

  function toggleAll(checked) {
    setSelectedIds(checked ? members.map((member) => member.user_id) : [])
  }

  async function setSelectedActive(active) {
    const selected = members.filter((member) => selectedIds.includes(member.user_id))
    if (selected.length === 0) return
    setBusy(true); setError(''); setResult('')
    try {
      for (const member of selected) {
        await api(`/api/platform/authorizations/users/${encodeURIComponent(member.user_id)}/frontteam/${active ? 'grant' : 'revoke'}`, { method: 'POST' })
      }
      setResult(`${selected.length} Frontteam${selected.length === 1 ? 'lid is' : 'leden zijn'} ${active ? 'geactiveerd' : 'gedeactiveerd'}.`)
      await load()
    } catch (err) { setError(err.message) } finally { setBusy(false) }
  }

  async function removeSelected() {
    const selected = members.filter((member) => selectedIds.includes(member.user_id))
    if (selected.length === 0) return
    if (!window.confirm(`${selected.length} geselecteerde Frontteam${selected.length === 1 ? 'lid' : 'leden'} verwijderen? De Inhuis-accounts en eigen huishoudens blijven bestaan.`)) return
    setBusy(true); setError(''); setResult('')
    try {
      for (const member of selected) {
        await api(`/api/platform/frontteam-management/members/${encodeURIComponent(member.user_id)}`, { method: 'DELETE' })
      }
      setSelectedIds([])
      setResult(`${selected.length} Frontteam${selected.length === 1 ? 'lid is' : 'leden zijn'} verwijderd. De Inhuis-accounts en eigen huishoudens zijn behouden.`)
      await load()
    } catch (err) { setError(err.message) } finally { setBusy(false) }
  }

  function exportSelected() {
    const selected = members.filter((member) => selectedIds.includes(member.user_id))
    if (selected.length === 0) return
    const escapeCsv = (value) => `"${String(value ?? '').replaceAll('"', '""')}"`
    const csv = [
      ['E-mailadres', 'Status'],
      ...selected.map((member) => [member.email, isActiveMember(member) ? 'Actief' : 'Inactief']),
    ].map((row) => row.map(escapeCsv).join(';')).join('\r\n')
    const blob = new Blob(['\uFEFF', csv], { type: 'text/csv;charset=utf-8' })
    const url = URL.createObjectURL(blob)
    const link = document.createElement('a')
    link.href = url
    link.download = 'inhuis-frontteamleden.csv'
    document.body.appendChild(link)
    link.click()
    link.remove()
    URL.revokeObjectURL(url)
  }

  const allSelected = members.length > 0 && members.every((member) => selectedIds.includes(member.user_id))
  const someSelected = selectedIds.length > 0

  const columns = React.useMemo(() => [
    {
      key: 'select',
      width: 56,
      renderFilter: ({ placement }) => placement === 'header' ? (
        <input
          type="checkbox"
          aria-label="Selecteer alle Frontteamleden"
          checked={allSelected}
          onChange={(event) => toggleAll(event.target.checked)}
        />
      ) : null,
      renderCell: (member) => (
        <input
          type="checkbox"
          aria-label={`Selecteer ${member.email}`}
          checked={selectedIds.includes(member.user_id)}
          onChange={(event) => toggleMember(member.user_id, event.target.checked)}
        />
      ),
    },
    {
      key: 'email',
      label: 'E-mailadres',
      width: 420,
      sortable: true,
      filterable: true,
      filterPlaceholder: 'Filter e-mailadres',
    },
    {
      key: 'status',
      label: 'Status',
      width: 180,
      sortable: true,
      filterable: true,
      getValue: (member) => isActiveMember(member) ? 'Actief' : 'Inactief',
      renderCell: (member) => <strong>{isActiveMember(member) ? 'Actief' : 'Inactief'}</strong>,
    },
  ], [allSelected, selectedIds, members])

  const bulkActions = (
    <>
      <Button type="button" disabled={busy || !someSelected} onClick={() => setSelectedActive(true)}>Activeren</Button>
      <Button type="button" variant="secondary" disabled={busy || !someSelected} onClick={() => setSelectedActive(false)}>Deactiveren</Button>
      <Button type="button" variant="secondary" disabled={busy || !someSelected} onClick={removeSelected}>Verwijderen</Button>
      <Button type="button" variant="secondary" disabled={busy || !someSelected} onClick={exportSelected}>Exporteren</Button>
    </>
  )

  return (
    <div data-testid="settings-frontteam-page">
      <Header title="Frontteam beheren" subtitle="Beheer de aanvullende Frontteambevoegdheden van bestaande Inhuis-gebruikers." />
      <div className="rz-content"><div className="rz-content-inner rz-frontteam-layout">
        <Card>
          <form onSubmit={addMember} data-testid="frontteam-add-form">
            <h2>Lid toevoegen aan Frontteam</h2>
            <label htmlFor="frontteam-email"><strong>E-mailadres</strong></label>
            <div className="rz-frontteam-add-row">
              <input id="frontteam-email" type="email" value={email} onChange={(e) => setEmail(e.target.value)} placeholder="naam@voorbeeld.nl" autoComplete="off" />
              <Button type="submit" disabled={busy}>{busy ? 'Bezig...' : 'Toevoegen aan Frontteam'}</Button>
            </div>
            <p>Alleen een bestaand Inhuis-account kan worden toegevoegd. Het eigen huishouden en de huishoudrol blijven ongewijzigd.</p>
          </form>
        </Card>

        {error ? <Card><p role="alert">{error}</p></Card> : null}
        {result ? <Card><p role="status">{result}</p></Card> : null}

        <Card>
          <h2>Frontteamleden</h2>
          {loading ? <p>Frontteamleden laden...</p> : (
            <DataTable
              columns={columns}
              data={members}
              getRowKey={(member) => member.user_id}
              emptyMessage="Er zijn nog geen Frontteamleden."
              dataTestId="frontteam-members-table"
              pagination
              pageSize={10}
              paginationActions={bulkActions}
              renderRow={(member) => (
                <tr
                  key={member.user_id}
                  data-testid={`frontteam-member-${member.user_id}`}
                  className={selectedIds.includes(member.user_id) ? 'rz-row-selected' : ''}
                >
                  {columns.map((column) => (
                    <td key={column.key}>
                      {column.renderCell ? column.renderCell(member) : String(column.getValue ? column.getValue(member) : member[column.key] ?? '')}
                    </td>
                  ))}
                </tr>
              )}
            />
          )}
        </Card>
      </div></div>
    </div>
  )
}
