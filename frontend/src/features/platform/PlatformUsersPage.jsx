import React from 'react'
import { useAppFeedback } from '../../ui/AppFeedbackProvider.jsx'
import { API_BASE_URL } from '../../lib/apiClient.js'
import Button from '../../ui/Button'
import Pagination from '../../ui/Pagination.jsx'
import Input from '../../ui/Input'
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
  const [error, setError] = React.useState('')
  const { showFeedback } = useAppFeedback()
  React.useEffect(() => { if (error) showFeedback({ variant: 'error', message: error }) }, [error, showFeedback])
  const [result, setResult] = React.useState('')
  React.useEffect(() => { if (result) showFeedback({ variant: 'success', message: result }) }, [result, showFeedback])
  const [pendingUser, setPendingUser] = React.useState(null)
  const [pendingUnsuspend, setPendingUnsuspend] = React.useState(null)
  const [pendingDelete, setPendingDelete] = React.useState(null)
  const [deletePreview, setDeletePreview] = React.useState(null)
  const [deleteConfirmation, setDeleteConfirmation] = React.useState('')
  const previewTokenRef = React.useRef(0)
  const [submitting, setSubmitting] = React.useState(false)

  const loadUsers = React.useCallback(async () => {
    setLoading(true)
    setError('')
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
      setError(err?.message || 'Gebruikers ophalen mislukt.')
    } finally {
      setLoading(false)
    }
  }, [])

  React.useEffect(() => {
    loadUsers()
  }, [loadUsers])

  async function confirmSuspend() {
    if (!pendingUser || submitting) return
    setSubmitting(true)
    setError('')
    setResult('')
    try {
      const response = await fetch(
        `${API_BASE_URL}/api/platform/users/${encodeURIComponent(pendingUser.user_id)}/suspend`,
        {
          method: 'POST',
          credentials: 'include',
          headers: { Accept: 'application/json' },
        },
      )
      if (!response.ok) {
        const payload = await response.json().catch(() => ({}))
        throw new Error(payload?.detail || `Gebruiker schorsen mislukt (${response.status})`)
      }
      const payload = await response.json()
      const item = payload?.item || {}
      setUsers((current) => current.map((user) => (
        user.user_id === pendingUser.user_id
          ? {
              ...user,
              account_status: 'suspended',
              suspended_at: item.suspended_at || new Date().toISOString(),
              active_session_count: 0,
            }
          : user
      )))
      setResult(
        `${pendingUser.email} is geschorst. ${Number(item.active_sessions_revoked || 0)} actieve sessie(s) zijn ingetrokken.`,
      )
      setPendingUser(null)
    } catch (err) {
      setError(err?.message || 'Gebruiker schorsen mislukt.')
    } finally {
      setSubmitting(false)
    }
  }


  async function confirmUnsuspend() {
    if (!pendingUnsuspend || submitting) return
    setSubmitting(true)
    setError('')
    setResult('')
    try {
      const response = await fetch(
        `${API_BASE_URL}/api/platform/users/${encodeURIComponent(pendingUnsuspend.user_id)}/unsuspend`,
        { method: 'POST', credentials: 'include', headers: { Accept: 'application/json' } },
      )
      const payload = await response.json().catch(() => ({}))
      if (!response.ok) throw new Error(payload?.detail || 'Schorsing opheffen mislukt.')
      setUsers((current) => current.map((user) => (
        user.user_id === pendingUnsuspend.user_id
          ? { ...user, account_status: 'active', suspended_at: null, active_session_count: 0 }
          : user
      )))
      setResult(`De schorsing van ${pendingUnsuspend.email} is opgeheven. Eerdere sessies blijven ingetrokken.`)
      setPendingUnsuspend(null)
    } catch (err) {
      setError(err?.message || 'Schorsing opheffen mislukt.')
    } finally {
      setSubmitting(false)
    }
  }

  async function openDelete(user) {
    if (!canDelete || submitting) return
    const token = ++previewTokenRef.current
    setPendingDelete(user)
    setDeletePreview(null)
    setDeleteConfirmation('')
    setError('')
    setResult('')
    try {
      const response = await fetch(
        `${API_BASE_URL}/api/platform/users/${encodeURIComponent(user.user_id)}/deletion-preview`,
        { credentials: 'include', headers: { Accept: 'application/json' } },
      )
      const payload = await response.json().catch(() => ({}))
      if (!response.ok) throw new Error(payload?.detail || 'Verwijdervoorbeeld laden mislukt.')
      if (previewTokenRef.current === token) {
        if (payload.user_id !== user.user_id) throw new Error('Verwijdervoorbeeld hoort bij een andere gebruiker.')
        setDeletePreview(payload)
      }
    } catch (err) {
      if (previewTokenRef.current === token) {
        setError(err?.message || 'Gebruiker kan niet veilig worden verwijderd.')
        setPendingDelete(null)
      }
    }
  }

  async function confirmDelete(event) {
    event.preventDefault()
    if (!pendingDelete || !deletePreview || submitting || !canDelete) return
    const expected = `VERWIJDER ${pendingDelete.email.toLowerCase()}`
    if (deleteConfirmation !== expected || deletePreview.user_id !== pendingDelete.user_id) return
    setSubmitting(true)
    setError('')
    setResult('')
    try {
      const response = await fetch(
        `${API_BASE_URL}/api/platform/users/${encodeURIComponent(pendingDelete.user_id)}`,
        {
          method: 'DELETE',
          credentials: 'include',
          headers: { Accept: 'application/json', 'Content-Type': 'application/json' },
          body: JSON.stringify({ confirmation: deleteConfirmation }),
        },
      )
      const payload = await response.json().catch(() => ({}))
      if (!response.ok) throw new Error(payload?.detail || 'Gebruiker verwijderen mislukt.')
      setUsers((current) => current.filter((user) => user.user_id !== pendingDelete.user_id))
      setResult(`${pendingDelete.email} is definitief verwijderd. ${payload.households_preserved} huishouden(s) behouden.`)
      previewTokenRef.current += 1
      setPendingDelete(null)
      setDeletePreview(null)
      setDeleteConfirmation('')
    } catch (err) {
      setError(err?.message || 'Gebruiker verwijderen mislukt.')
    } finally {
      setSubmitting(false)
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
                    <Button type="button" onClick={() => {
                      setPendingUser(null)
                      setPendingDelete(null)
                      previewTokenRef.current += 1
                      setPendingUnsuspend(user)
                      setResult('')
                    }}>Schorsing opheffen</Button>
                  ) : (
                    <Button type="button" onClick={() => {
                      setPendingUnsuspend(null)
                      setPendingDelete(null)
                      previewTokenRef.current += 1
                      setPendingUser(user)
                      setResult('')
                    }}>Gebruiker schorsen</Button>
                  )}
                  {canDelete ? (
                    <Button type="button" variant="secondary" onClick={() => {
                      setPendingUser(null)
                      setPendingUnsuspend(null)
                      openDelete(user)
                    }}>Gebruiker verwijderen</Button>
                  ) : null}
                </div>
              )}
            </div>
          </Card>
        )
      })}

      {pageCount > 1 ? <Pagination page={currentPage} pageCount={pageCount} onPageChange={setPage} /> : null}

      {pendingUser ? (
        <Card>
          <div data-testid="platform-user-suspend-confirmation">
            <h3>Gebruiker definitief schorsen?</h3>
            <p>
              Je staat op het punt <strong>{pendingUser.email}</strong> te schorsen. Alle actieve sessies van
              dit account worden direct ingetrokken en een nieuwe login wordt geblokkeerd.
            </p>
            <p>
              Platformrollen en household-memberships worden niet verwijderd of aangepast.
            </p>
            <div>
              <Button
                type="button"
                variant="secondary"
                disabled={submitting}
                onClick={() => setPendingUser(null)}
              >
                Annuleren
              </Button>
              <Button
                type="button"
                disabled={submitting}
                onClick={confirmSuspend}
              >
                {submitting ? 'Schorsen...' : 'Definitief schorsen'}
              </Button>
            </div>
          </div>
        </Card>
      ) : null}

      {pendingUnsuspend ? (
        <Card>
          <div data-testid="platform-user-unsuspend-confirmation">
            <h3>Schorsing opheffen?</h3>
            <p>De toegang van <strong>{pendingUnsuspend.email}</strong> wordt hersteld.
              Eerder ingetrokken sessies blijven ongeldig; de gebruiker moet opnieuw inloggen.</p>
            <div style={{ display: 'flex', flexWrap: 'wrap', gap: 12 }}>
              <Button type="button" variant="secondary" disabled={submitting}
                onClick={() => setPendingUnsuspend(null)}>Annuleren</Button>
              <Button type="button" disabled={submitting} onClick={confirmUnsuspend}>
                {submitting ? 'Opheffen…' : 'Schorsing opheffen bevestigen'}
              </Button>
            </div>
          </div>
        </Card>
      ) : null}

      {pendingDelete ? (
        <Card>
          <form onSubmit={confirmDelete} data-testid="platform-user-delete-confirmation"
            style={{ display: 'grid', gap: 12 }}>
            <h3>Gebruiker definitief verwijderen?</h3>
            <p>Je staat op het punt <strong>{pendingDelete.email}</strong> definitief te verwijderen.
              Het account en de toegang verdwijnen. Dit kan niet ongedaan worden gemaakt.</p>
            {deletePreview ? (
              <p data-testid="platform-user-delete-preview">
                {deletePreview.households_to_keep} gedeelde huishouden(s) blijven met hun gegevens behouden.
                {deletePreview.households_to_delete} huishouden(s) zonder andere leden worden met hun
                gegevens verwijderd. Zo nodig wordt de beheerdersrol overgedragen.
              </p>
            ) : <p>Gevolgen van verwijdering controleren…</p>}
            <Input
              label={`Typ exact: VERWIJDER ${pendingDelete.email.toLowerCase()}`}
              value={deleteConfirmation}
              onChange={(event) => setDeleteConfirmation(event.target.value)}
              disabled={!deletePreview || submitting}
              autoComplete="off"
              data-testid="platform-user-delete-typed-confirmation"
            />
            <div style={{ display: 'flex', flexWrap: 'wrap', gap: 12 }}>
              <Button type="button" variant="secondary" disabled={submitting} onClick={() => {
                previewTokenRef.current += 1
                setPendingDelete(null)
                setDeletePreview(null)
                setDeleteConfirmation('')
              }}>Annuleren</Button>
              <Button type="submit" disabled={
                !deletePreview || submitting ||
                deleteConfirmation !== `VERWIJDER ${pendingDelete.email.toLowerCase()}`
              }> {submitting ? 'Verwijderen…' : 'Gebruiker definitief verwijderen'} </Button>
            </div>
          </form>
        </Card>
      ) : null}
    </div>
  )
}
