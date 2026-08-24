import React from 'react'
import { API_BASE_URL } from '../../lib/apiClient.js'
import Button from '../../ui/Button'
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
  const [loading, setLoading] = React.useState(true)
  const [error, setError] = React.useState('')
  const [result, setResult] = React.useState('')
  const [pendingUser, setPendingUser] = React.useState(null)
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

  return (
    <div data-testid="platform-users-page">
      <Header title="Gebruikers" subtitle="Bekijk platformaccounts en schors een account met directe sessie-intrekking." />

      <Card>
        <p>
          Deze pagina gebruikt uitsluitend <strong>platform.users.suspend</strong>. Er is geen actief
          huishouden nodig en er is nooit een fallback naar huishouden 0.
        </p>
        <p>
          Wachtwoorden, password-hashes, sessietokens en token-hashes worden niet getoond. Schorsen wijzigt
          geen platformrol en geen household-membership; het blokkeert de identity en trekt actieve sessies in.
        </p>
      </Card>

      {error ? <Card><p role="alert">{error}</p></Card> : null}
      {result ? <Card><p role="status">{result}</p></Card> : null}
      {loading ? <Card><p>Gebruikers laden...</p></Card> : null}

      {!loading && !users.length ? (
        <Card><p>Er zijn geen gebruikers gevonden.</p></Card>
      ) : null}

      {!loading && users.map((user) => {
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
                <p>Huidig beheeraccount — dit account kan zichzelf hier niet schorsen.</p>
              ) : suspended ? (
                <p>Dit account is al geschorst.</p>
              ) : (
                <Button type="button" onClick={() => {
                  setPendingUser(user)
                  setResult('')
                }}>
                  Gebruiker schorsen
                </Button>
              )}
            </div>
          </Card>
        )
      })}

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
    </div>
  )
}
