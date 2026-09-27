import React from 'react'
import { API_BASE_URL } from '../../lib/apiClient.js'
import Button from '../../ui/Button.jsx'
import Card from '../../ui/Card.jsx'
import DataTable from '../../ui/DataTable.jsx'
import { useAppFeedback } from '../../ui/AppFeedbackProvider.jsx'
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
  const { showFeedback } = useAppFeedback()
  const [members, setMembers] = React.useState([])
  const [email, setEmail] = React.useState('')
  const [loading, setLoading] = React.useState(true)
  const [busy, setBusy] = React.useState(false)
  const [selectedIds, setSelectedIds] = React.useState([])
  const [error, setError] = React.useState('')

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
    setBusy(true); setError(''); 
    try {
      await api('/api/platform/frontteam-management/members', {
        method: 'POST', body: JSON.stringify({ email: normalized }),
      })
      setEmail('')
      showFeedback({ variant: 'success', title: 'Frontteam bijgewerkt', message: `${normalized} is toegevoegd aan het Frontteam.`, testId: 'frontteam-feedback' })
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
    setBusy(true); setError(''); 
    try {
      for (const member of selected) {
        await api(`/api/platform/authorizations/users/${encodeURIComponent(member.user_id)}/frontteam/${active ? 'grant' : 'revoke'}`, { method: 'POST' })
      }
      showFeedback({ variant: 'success', title: 'Frontteam bijgewerkt', message: `${selected.length} Frontteam${selected.length === 1 ? 'lid is' : 'leden zijn'} ${active ? 'geactiveerd' : 'gedeactiveerd'}.`, testId: 'frontteam-feedback' })
      await load()
    } catch (err) { setError(err.message) } finally { setBusy(false) }
  }

  async function removeSelected() {
    const selected = members.filter((member) => selectedIds.includes(member.user_id))
    if (selected.length === 0) return
    if (!window.confirm(`${selected.length} geselecteerde Frontteam${selected.length === 1 ? 'lid' : 'leden'} verwijderen? De Inhuis-accounts en eigen huishoudens blijven bestaan.`)) return
    setBusy(true); setError(''); 
    try {
      for (const member of selected) {
        await api(`/api/platform/frontteam-management/members/${encodeURIComponent(member.user_id)}`, { method: 'DELETE' })
      }
      setSelectedIds([])
      showFeedback({ variant: 'success', title: 'Frontteam bijgewerkt', message: `${selected.length} Frontteam${selected.length === 1 ? 'lid is' : 'leden zijn'} verwijderd.`, detail: 'De Inhuis-accounts en eigen huishoudens zijn behouden.', testId: 'frontteam-feedback' })
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

  return (
    <div data-testid="settings-frontteam-page">
      <div className="rz-content">
        <div className="rz-content-inner">
          <Card>
            <div className="rz-frontteam-content">
              <h2>Frontteam beheren — {members.length} {members.length === 1 ? 'lid' : 'leden'}</h2>
              <form onSubmit={addMember} data-testid="frontteam-add-form" className="rz-frontteam-add-form">
                <div className="rz-input-field">
                  <label className="rz-label" htmlFor="frontteam-email">Lid toevoegen aan Frontteam</label>
                  <div className="rz-frontteam-add-row">
                    <input id="frontteam-email" className="rz-input" type="email" value={email}
                      onChange={(event) => setEmail(event.target.value)}
                      placeholder="E-mailadres van bestaande Inhuis-gebruiker" autoComplete="off" />
                    <Button type="submit" disabled={busy}>{busy ? 'Bezig...' : 'Toevoegen'}</Button>
                  </div>
                </div>
                <p className="rz-frontteam-help">Het eigen huishouden en de huishoudrol blijven ongewijzigd.</p>
              </form>
              {error ? <div role="alert" className="rz-frontteam-error">{error}</div> : null}
              <DataTable
                columns={columns} data={members} getRowKey={(member) => member.user_id}
                emptyMessage={loading ? 'Frontteamleden laden…' : 'Er zijn nog geen Frontteamleden.'}
                dataTestId="frontteam-members-table" pagination pageSize={10} stickyHeader stickyFilters
                renderRow={(member) => (
                  <tr key={member.user_id} data-testid={`frontteam-member-${member.user_id}`}
                    className={selectedIds.includes(member.user_id) ? 'rz-row-selected' : ''}>
                    {columns.map((column) => (
                      <td key={column.key}>
                        {column.renderCell ? column.renderCell(member) : String(column.getValue ? column.getValue(member) : member[column.key] ?? '')}
                      </td>
                    ))}
                  </tr>
                )}
              />
              <div className="rz-frontteam-bulk-actions">
                <Button type="button" disabled={busy || !someSelected} onClick={() => setSelectedActive(true)}>Activeren</Button>
                <Button type="button" disabled={busy || !someSelected} onClick={() => setSelectedActive(false)}>Deactiveren</Button>
                <Button type="button" disabled={busy || !someSelected} onClick={removeSelected}>Verwijderen</Button>
                <Button type="button" disabled={busy || !someSelected} onClick={exportSelected}>Exporteren</Button>
              </div>
            </div>
          </Card>
        </div>
      </div>
    </div>
  )
}
