import React from 'react'
import { useAppFeedback } from '../../ui/AppFeedbackProvider.jsx'
import { API_BASE_URL } from '../../lib/apiClient.js'
import Button from '../../ui/Button'
import Pagination from '../../ui/Pagination.jsx'
import Card from '../../ui/Card'
import Header from '../../ui/Header'

function formatDateTime(value) {
  if (!value) return 'Niet geschorst'
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return String(value)
  return new Intl.DateTimeFormat('nl-NL', {
    dateStyle: 'medium',
    timeStyle: 'short',
  }).format(date)
}

export default function PlatformUsersPage() {
  const [users, setUsers] = React.useState([])
  const [canDelete, setCanDelete] = React.useState(false)
  const [page, setPage] = React.useState(1)
  const pageCount = Math.max(1, Math.ceil(users.length / 10))
  const currentPage = Math.min(page, pageCount)
  const visibleItems = users.slice((currentPage - 1) * 10, currentPage * 10)
  React.useEffect(() => { if (page > pageCount) setPage(pageCount) }, [page, pageCount])
  const [loading, setLoading] = React.useState(true)
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
    showAction(`${user.email} is geschorst. ${Number(item.active_sessions_revoked || 0)} actieve sessie(s) zijn ingetrokken.`)
  }

  function openSuspend(user) {
    showFeedback({
      key: 'platform-users-action',
      dedupeMs: 0,
      variant: 'warning',
      testId: 'platform-user-suspend-confirmation',
      title: 'Gebruiker schorsen?',
      message: `Je staat op het punt ${user.email} te schorsen. Alle actieve sessies worden ingetrokken en aanmelden wordt geblokkeerd.`,
      detail: 'Platformrollen en huishoudlidmaatschappen worden niet gewijzigd.',
      dismissMode: 'ok-only',
      primaryActionLabel: 'Definitief schorsen',
      secondaryActionLabel: 'Annuleren',
      onPrimaryAction: () => suspendUser(user),
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
    showAction(`De schorsing van ${user.email} is opgeheven. Eerdere sessies blijven ingetrokken.`)
  }

  function openUnsuspend(user) {
    showFeedback({
      key: 'platform-users-action',
      dedupeMs: 0,
      variant: 'warning',
      testId: 'platform-user-unsuspend-confirmation',
      title: 'Schorsing opheffen?',
      message: `De toegang van ${user.email} wordt hersteld.`,
      detail: 'Eerder ingetrokken sessies blijven ongeldig; de gebruiker moet opnieuw inloggen.',
      dismissMode: 'ok-only',
      primaryActionLabel: 'Schorsing opheffen bevestigen',
      secondaryActionLabel: 'Annuleren',
      onPrimaryAction: () => unsuspendUser(user),
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
    previewTokenRef.current += 1
    showAction(`${user.email} is definitief verwijderd. ${payload.households_preserved} huishouden(s) behouden.`)
  }

  async function openDelete(user) {
    if (!canDelete) return
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

  return (
    <div data-testid="platform-users-page">
      <Header title="Gebruikers" subtitle="Schors gebruikers, hef schorsingen op of verwijder een regulier account." />

      <Card>
        <p>
          Schorsen en opheffen gebruiken <strong>platform.users.suspend</strong>. Definitief verwijderen
          vereist daarnaast de afzonderlijke bevoegdheid <strong>platform.users.delete</strong>. Er is geen actief
          huishouden nodig en er is nooit een fallback naar huishouden 0.
        </p>
        <p>
          Wachtwoorden, password-hashes, sessietokens en token-hashes worden niet getoond. Schorsen trekt actieve
          sessies in; opheffen herstelt geen oude sessies. Verwijderen is onomkeerbaar en behoudt
          gedeelde huishoudgegevens en draagt zo nodig de beheerdersrol over. Platformaccounts zijn uitgesloten.
        </p>
      </Card>



      {loading ? <Card><p>Nieuwe gegevens laden…</p></Card> : null}

      {!loading && !users.length ? (
        <Card><p>Er zijn geen gebruikers gevonden.</p></Card>
      ) : null}

      {visibleItems.map((user) => {
        const suspended = user.account_status === 'suspended'
        return (
          <Card key={user.user_id}>
            <div data-testid={`platform-user-${user.user_id}`}>
              <h3>{user.email}</h3>
              <p>Gebruiker-ID: {user.user_id}</p>
              <p>Status: {suspended ? 'Geschorst' : 'Actief'}</p>
              <p>Actieve sessies: {Number(user.active_session_count || 0)}</p>
              {suspended ? <p>Geschorst op: {formatDateTime(user.suspended_at)}</p> : null}
              {user.is_current ? (
                <p>Huidig beheeraccount — dit account kan zichzelf hier niet schorsen of verwijderen.</p>
              ) : (
                <div style={{ display: 'flex', flexWrap: 'wrap', gap: 12 }}>
                  {suspended ? (
                    <Button type="button" onClick={() => openUnsuspend(user)}>Schorsing opheffen</Button>
                  ) : (
                    <Button type="button" onClick={() => openSuspend(user)}>Gebruiker schorsen</Button>
                  )}
                  {canDelete ? (
                    <Button type="button" variant="secondary" onClick={() => openDelete(user)}>Gebruiker verwijderen</Button>
                  ) : null}
                </div>
              )}
            </div>
          </Card>
        )
      })}

      {pageCount > 1 ? <Pagination page={currentPage} pageCount={pageCount} onPageChange={setPage} /> : null}


    </div>
  )
}
