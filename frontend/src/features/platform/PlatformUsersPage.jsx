import React from 'react'
import { useAppFeedback } from '../../ui/AppFeedbackProvider.jsx'
import { API_BASE_URL } from '../../lib/apiClient.js'
import Button from '../../ui/Button'
import DataTable from '../../ui/DataTable.jsx'
import Card from '../../ui/Card'
import Header from '../../ui/Header'
import './platformUsers.css'

function formatDateTime(value) {
  if (!value) return 'Niet geschorst'
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return String(value)
  return new Intl.DateTimeFormat('nl-NL', {
    dateStyle: 'medium',
    timeStyle: 'short',
  }).format(date)
}

function csvCell(value) {
  const content = String(value ?? '')
  const safe = /^\s*[=+@-]/.test(content) ? `'${content}` : content
  return `"${safe.replaceAll('"', '""')}"`
}

const USER_COLUMNS = [
  { key: 'select', width: 60 },
  { key: 'email', label: 'E-mailadres', width: 350, sortable: true, filterable: true },
  { key: 'account_status', label: 'Status', width: 145, sortable: true, filterable: true,
    getFilterValue: (user) => user.account_status === 'suspended' ? 'Geschorst' : 'Actief',
    getSortValue: (user) => user.account_status === 'suspended' ? 'Geschorst' : 'Actief' },
  { key: 'active_session_count', label: 'Actieve sessies', width: 160,
    sortable: true, filterable: true, align: 'right' },
  { key: 'suspended_at', label: 'Geschorst op', width: 215, sortable: true, filterable: true,
    getFilterValue: (user) => user.suspended_at ? formatDateTime(user.suspended_at) : '',
    getSortValue: (user) => user.suspended_at || '' },
]

export default function PlatformUsersPage() {
  const [users, setUsers] = React.useState([])
  const [canDelete, setCanDelete] = React.useState(false)
  const [loading, setLoading] = React.useState(true)
  const [page, setPage] = React.useState(1)
  const [selectedIds, setSelectedIds] = React.useState([])
  const [pageRows, setPageRows] = React.useState([])
  const [filteredRows, setFilteredRows] = React.useState([])
  const selectedSet = React.useMemo(() => new Set(selectedIds), [selectedIds])
  const selectedRows = React.useMemo(() => users.filter((user) => (
    !user.is_current && !user.is_protected && selectedSet.has(user.user_id)
  )), [users, selectedSet])
  const activeTargets = selectedRows.filter((user) => user.account_status !== 'suspended')
  const suspendedTargets = selectedRows.filter((user) => user.account_status === 'suspended')
  const selectablePageIds = pageRows.filter((user) => !user.is_current && !user.is_protected).map((user) => user.user_id)
  const selectableFilteredIds = filteredRows.filter((user) => !user.is_current && !user.is_protected).map((user) => user.user_id)
  const allPageSelected = selectablePageIds.length > 0 && selectablePageIds.every((id) => selectedSet.has(id))
  const allFilteredSelected = selectableFilteredIds.length > 0 && selectableFilteredIds.every((id) => selectedSet.has(id))

  const onPageRowsChange = React.useCallback((rows) => {
    setPageRows((previous) => previous.length === rows.length
      && previous.every((user, index) => user.user_id === rows[index].user_id) ? previous : rows)
  }, [])
  const onFilteredRowsChange = React.useCallback((rows) => {
    setFilteredRows((previous) => previous.length === rows.length
      && previous.every((user, index) => user.user_id === rows[index].user_id) ? previous : rows)
  }, [])
  function toggleSelection(ids, allSelected) {
    setSelectedIds((previous) => allSelected
      ? previous.filter((id) => !ids.includes(id))
      : [...new Set([...previous, ...ids])])
  }

  const columns = React.useMemo(() => [
    { ...USER_COLUMNS[0], renderFilter: () => (
      <input type="checkbox" aria-label="Alle rijen op deze pagina"
        checked={allPageSelected} disabled={!selectablePageIds.length || loading}
        onChange={() => toggleSelection(selectablePageIds, allPageSelected)} />
    ) },
    ...USER_COLUMNS.slice(1),
  ], [allPageSelected, selectablePageIds.join('|'), loading])

  const { showFeedback, dismissFeedbackIfKey } = useAppFeedback()
  const previewTokenRef = React.useRef(0)
  React.useEffect(() => () => {
    previewTokenRef.current += 1
    dismissFeedbackIfKey('platform-users-action')
  }, [dismissFeedbackIfKey])

  const loadUsers = React.useCallback(async () => {
    setLoading(true)
    try {
      const response = await fetch(`${API_BASE_URL}/api/platform/users`, {
        method: 'GET',
        credentials: 'include',
        headers: { Accept: 'application/json' },
      })
      if (!response.ok) {
        const payload = await response.json().catch(() => ({}))
        throw new Error(payload?.detail || `Gebruikers ophalen mislukt (${response.status})`)
      }
      const payload = await response.json()
      setUsers(Array.isArray(payload?.items) ? payload.items : [])
      setCanDelete(payload?.can_delete === true)
      setSelectedIds([])
      setPage(1)
    } catch (err) {
      showFeedback({ variant: 'error', key: 'platform-users-action', dedupeMs: 0,
        message: err?.message || 'Gebruikers ophalen mislukt.' })
    } finally {
      setLoading(false)
    }
  }, [showFeedback])

  React.useEffect(() => {
    loadUsers()
  }, [loadUsers])


  function showAction(message) {
    showFeedback({
      key: 'platform-users-action',
      dedupeMs: 0,
      variant: 'success',
      message,
    })
  }

  async function suspendUser(user) {
    const response = await fetch(
      `${API_BASE_URL}/api/platform/users/${encodeURIComponent(user.user_id)}/suspend`,
      { method: 'POST', credentials: 'include', headers: { Accept: 'application/json' } },
    )
    const payload = await response.json().catch(() => ({}))
    if (!response.ok) throw new Error(payload?.detail || `Gebruiker schorsen mislukt (${response.status})`)
    const item = payload?.item || {}
    setUsers((current) => current.map((entry) => (
      entry.user_id === user.user_id
        ? { ...entry, account_status: 'suspended',
            suspended_at: item.suspended_at || new Date().toISOString(), active_session_count: 0 }
        : entry
    )))
    setSelectedIds((current) => current.filter((id) => id !== user.user_id))
    return Number(item.active_sessions_revoked || 0)
  }

  function openSuspend(targets) {
    targets = targets.filter((user) => !user.is_protected && !user.is_current)
    if (!targets.length) return
    showFeedback({
      key: 'platform-users-action', dedupeMs: 0,
      variant: 'warning', testId: 'platform-user-suspend-confirmation',
      title: targets.length === 1 ? 'Gebruiker schorsen?' : 'Gebruikers schorsen?',
      message: targets.length === 1
        ? `Je staat op het punt ${targets[0].email} te schorsen.`
        : `Je staat op het punt ${targets.length} geselecteerde actieve gebruikers te schorsen.`,
      detail: 'Actieve sessies worden ingetrokken. Aanmelden wordt geblokkeerd. Platformrollen en huishoudlidmaatschappen blijven bestaan.',
      dismissMode: 'ok-only',
      primaryActionLabel: 'Definitief schorsen',
      secondaryActionLabel: 'Annuleren',
      onPrimaryAction: async () => {
        let completed = 0
        let revoked = 0
        const failures = []
        for (const user of targets) {
          try {
            revoked += await suspendUser(user)
            completed += 1
          } catch (error) {
            failures.push(`${user.email}: ${error?.message || 'niet uitgevoerd'}`)
          }
        }
        if (failures.length && !completed) throw new Error(failures.join(' | '))
        if (failures.length) {
          showFeedback({ key: 'platform-users-action', dedupeMs: 0, variant: 'error',
            title: 'Niet alle gebruikers geschorst',
            message: `${completed} geschorst; ${failures.length} niet verwerkt. De niet-verwerkte accounts blijven geselecteerd.`,
            detail: failures.join(' | ') })
        } else {
          showAction(`${completed} gebruiker(s) geschorst. ${revoked} actieve sessie(s) ingetrokken.`)
        }
      },
    })
  }

  async function unsuspendUser(user) {
    const response = await fetch(
      `${API_BASE_URL}/api/platform/users/${encodeURIComponent(user.user_id)}/unsuspend`,
      { method: 'POST', credentials: 'include', headers: { Accept: 'application/json' } },
    )
    const payload = await response.json().catch(() => ({}))
    if (!response.ok) throw new Error(payload?.detail || 'Schorsing opheffen mislukt.')
    setUsers((current) => current.map((entry) => (
      entry.user_id === user.user_id
        ? { ...entry, account_status: 'active', suspended_at: null, active_session_count: 0 }
        : entry
    )))
    setSelectedIds((current) => current.filter((id) => id !== user.user_id))
  }

  function openUnsuspend(targets) {
    if (!targets.length) return
    showFeedback({
      key: 'platform-users-action', dedupeMs: 0,
      variant: 'warning', testId: 'platform-user-unsuspend-confirmation',
      title: 'Schorsing annuleren?',
      message: targets.length === 1
        ? `De toegang van ${targets[0].email} wordt hersteld.`
        : `De toegang van ${targets.length} geselecteerde geschorste gebruikers wordt hersteld.`,
      detail: 'Eerder ingetrokken sessies blijven ongeldig. Gebruikers moeten opnieuw inloggen.',
      dismissMode: 'ok-only',
      primaryActionLabel: 'Schorsing annuleren bevestigen',
      secondaryActionLabel: 'Annuleren',
      onPrimaryAction: async () => {
        let completed = 0
        const failures = []
        for (const user of targets) {
          try {
            await unsuspendUser(user)
            completed += 1
          } catch (error) {
            failures.push(`${user.email}: ${error?.message || 'niet uitgevoerd'}`)
          }
        }
        if (failures.length && !completed) throw new Error(failures.join(' | '))
        if (failures.length) {
          showFeedback({ key: 'platform-users-action', dedupeMs: 0, variant: 'error',
            title: 'Niet alle schorsingen geannuleerd',
            message: `${completed} hersteld; ${failures.length} niet verwerkt. De niet-verwerkte accounts blijven geselecteerd.`,
            detail: failures.join(' | ') })
        } else {
          showAction(`${completed} schorsing(en) geannuleerd. Eerdere sessies blijven ingetrokken.`)
        }
      },
    })
  }

  async function deleteUser(user, preview, confirmation) {
    const expected = `VERWIJDER ${user.email.toLowerCase()}`
    if (confirmation !== expected || preview.user_id !== user.user_id) {
      throw new Error('De bevestiging hoort niet bij deze gebruiker.')
    }
    const response = await fetch(
      `${API_BASE_URL}/api/platform/users/${encodeURIComponent(user.user_id)}`,
      {
        method: 'DELETE',
        credentials: 'include',
        headers: { Accept: 'application/json', 'Content-Type': 'application/json' },
        body: JSON.stringify({ confirmation }),
      },
    )
    const payload = await response.json().catch(() => ({}))
    if (!response.ok) throw new Error(payload?.detail || 'Gebruiker verwijderen mislukt.')
    setUsers((current) => current.filter((entry) => entry.user_id !== user.user_id))
    setSelectedIds((current) => current.filter((id) => id !== user.user_id))
    previewTokenRef.current += 1
    showAction(`${user.email} is definitief verwijderd. ${payload.households_preserved} huishouden(s) behouden.`)
  }

  async function openDelete(user) {
    if (!canDelete || user?.is_protected) return
    const token = ++previewTokenRef.current
    showFeedback({
      key: 'platform-users-action',
      dedupeMs: 0,
      variant: 'progress',
      title: 'Gevolgen van verwijdering controleren',
      message: `De gevolgen voor ${user.email} worden gecontroleerd.`,
      dismissMode: 'blocked',
    })
    try {
      const response = await fetch(
        `${API_BASE_URL}/api/platform/users/${encodeURIComponent(user.user_id)}/deletion-preview`,
        { credentials: 'include', headers: { Accept: 'application/json' } },
      )
      const preview = await response.json().catch(() => ({}))
      if (!response.ok) throw new Error(preview?.detail || 'Verwijdervoorbeeld laden mislukt.')
      if (preview.user_id !== user.user_id) throw new Error('Verwijdervoorbeeld hoort bij een andere gebruiker.')
      if (previewTokenRef.current !== token) return
      const expected = `VERWIJDER ${user.email.toLowerCase()}`
      showFeedback({
        key: 'platform-users-action',
        dedupeMs: 0,
        variant: 'warning',
        testId: 'platform-user-delete-confirmation',
        title: 'Gebruiker definitief verwijderen?',
        message: `Het account van ${user.email} wordt definitief verwijderd. Dit kan niet ongedaan worden gemaakt.`,
        detail: `${preview.households_to_keep} gedeelde huishouden(s) blijven met hun gegevens behouden. ${preview.households_to_delete} huishouden(s) zonder andere leden worden met hun gegevens verwijderd. Zo nodig wordt de beheerdersrol overgedragen.`,
        inputFields: [{
          name: 'confirmation',
          label: `Typ exact: ${expected}`,
          value: '',
          required: true,
          matchValue: expected,
          autoFocus: true,
        }],
        dismissMode: 'ok-only',
        primaryActionLabel: 'Gebruiker definitief verwijderen',
        secondaryActionLabel: 'Annuleren',
        onPrimaryAction: ({ confirmation }) => deleteUser(user, preview, confirmation),
        onSecondaryAction: () => { previewTokenRef.current += 1 },
      })
    } catch (err) {
      if (previewTokenRef.current === token) {
        showFeedback({
          key: 'platform-users-action',
          dedupeMs: 0,
          variant: 'error',
          message: err?.message || 'Gebruiker kan niet veilig worden verwijderd.',
        })
      }
    }
  }

  function exportSelected() {
    if (!selectedRows.length) return
    const header = ['E-mailadres', 'Status', 'Actieve sessies', 'Geschorst op']
    const body = selectedRows.map((user) => [
      user.email, user.account_status === 'suspended' ? 'Geschorst' : 'Actief',
      Number(user.active_session_count || 0),
      user.suspended_at ? formatDateTime(user.suspended_at) : '',
    ])
    const csv = [header, ...body].map((line) => line.map(csvCell).join(';')).join('\r\n')
    const url = URL.createObjectURL(new Blob(['\uFEFF', csv], { type: 'text/csv;charset=utf-8' }))
    const anchor = document.createElement('a')
    anchor.href = url
    anchor.download = 'Inhuis_Platformgebruikers.csv'
    document.body.appendChild(anchor)
    try { anchor.click() } finally {
      anchor.remove()
      window.setTimeout(() => URL.revokeObjectURL(url), 1000)
    }
    showAction(`${selectedRows.length} geselecteerde gebruiker(s) geëxporteerd.`)
  }

  return (
    <div data-testid="platform-users-page">
      <Header title="Gebruikers" />

      <section className="rz-platform-users-table-panel" data-testid="platform-users-panel" aria-label="Gebruikersoverzicht">
        {loading ? <Card><p>Gebruikers laden…</p></Card> : null}
        <div className="rz-mobile-table-select-row" data-testid="platform-users-select-all">
        <label><input type="checkbox" aria-label="Alle rijen in de tabel"
          checked={allFilteredSelected} disabled={loading || !selectableFilteredIds.length}
          onChange={() => toggleSelection(selectableFilteredIds, allFilteredSelected)} />
          Alle rijen in de tabel
        </label>
      </div>
      <DataTable
        dataTestId="platform-users-table"
        columns={columns}
        data={users}
        getRowKey={(user) => user.user_id}
        pageSize={8}
        pageState={page}
        onPageChange={setPage}
        onPageRowsChange={onPageRowsChange}
        onFilteredRowsChange={onFilteredRowsChange}
        emptyMessage={loading ? 'Gebruikers laden…' : 'Geen gebruikers gevonden.'}
        paginationActions={<>
          <span data-testid="platform-users-selection-count">Geselecteerd: {selectedRows.length}</span>
          <Button type="button" variant="secondary" onClick={exportSelected}
            disabled={!selectedRows.length || loading}>Exporteren</Button>
          <Button type="button" onClick={() => openSuspend(activeTargets)}
            disabled={!activeTargets.length || loading}>Schorsen</Button>
          <Button type="button" onClick={() => openUnsuspend(suspendedTargets)}
            disabled={!suspendedTargets.length || loading}>Schorsing annuleren</Button>
          {canDelete ? <Button type="button" variant="secondary"
            disabled={selectedRows.length !== 1 || selectedRows[0]?.is_protected || loading}
            onClick={() => openDelete(selectedRows[0])}>Gebruiker verwijderen</Button> : null}
        </>}
        renderRow={(user) => (
          <tr key={user.user_id} data-testid={`platform-user-${user.user_id}`}
            aria-selected={selectedSet.has(user.user_id)}>
            <td><input type="checkbox" aria-label={`Selecteer ${user.email}`}
              checked={selectedSet.has(user.user_id)}
              disabled={user.is_current || user.is_protected || loading}
              onChange={() => toggleSelection([user.user_id], selectedSet.has(user.user_id))} /></td>
            <td>{user.email}{user.is_current ? <span> — Huidig beheeraccount (niet selecteerbaar)</span> : null}{user.is_protected ? <span> — Beschermd: {user.protection_reason} (niet selecteerbaar)</span> : null}</td>
            <td>{user.account_status === 'suspended' ? 'Geschorst' : 'Actief'}</td>
            <td className="rz-num">{Number(user.active_session_count || 0)}</td>
            <td>{user.suspended_at ? formatDateTime(user.suspended_at) : '—'}</td>
          </tr>
        )}
      />
      </section>
    </div>
  )
}
