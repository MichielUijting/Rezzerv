import React from 'react'
import { API_BASE_URL } from '../../lib/apiClient.js'
import Button from '../../ui/Button.jsx'
import Card from '../../ui/Card.jsx'
import Header from '../../ui/Header.jsx'
import Input from '../../ui/Input.jsx'

export default function IpOwnerSuperusersPage() {
  const [users, setUsers] = React.useState([])
  const [email, setEmail] = React.useState('')
  const [loading, setLoading] = React.useState(true)
  const [error, setError] = React.useState('')
  const [result, setResult] = React.useState('')
  const [pending, setPending] = React.useState(false)
  const [confirmation, setConfirmation] = React.useState(null)

  const load = React.useCallback(async () => {
    setLoading(true)
    setError('')
    try {
      const response = await fetch(`${API_BASE_URL}/api/ip-owner/superusers`, {
        method: 'GET',
        credentials: 'include',
        headers: { Accept: 'application/json' },
      })
      const payload = await response.json().catch(() => ({}))
      if (!response.ok) throw new Error(payload?.detail || 'Superusers ophalen mislukt.')
      setUsers(Array.isArray(payload?.users) ? payload.users : [])
    } catch (err) {
      setError(err?.message || 'Superusers ophalen mislukt.')
    } finally {
      setLoading(false)
    }
  }, [])

  React.useEffect(() => { load() }, [load])

  async function confirmChange() {
    if (!confirmation || pending) return
    setPending(true)
    setError('')
    setResult('')
    try {
      const isGrant = confirmation.action === 'grant'
      const response = await fetch(
        isGrant
          ? `${API_BASE_URL}/api/ip-owner/superusers`
          : `${API_BASE_URL}/api/platform/authorizations/users/${encodeURIComponent(confirmation.user.user_id)}/superuser/revoke`,
        isGrant
          ? {
              method: 'POST',
              credentials: 'include',
              headers: { Accept: 'application/json', 'Content-Type': 'application/json' },
              body: JSON.stringify({ email: confirmation.email }),
            }
          : {
              method: 'POST',
              credentials: 'include',
              headers: { Accept: 'application/json' },
            },
      )
      const payload = await response.json().catch(() => ({}))
      if (!response.ok) throw new Error(payload?.detail || 'Superuser wijzigen mislukt.')
      setResult(
        isGrant
          ? `${confirmation.email} is nu Superuser.`
          : `${confirmation.user.email} is niet langer Superuser.`,
      )
      if (isGrant) setEmail('')
      setConfirmation(null)
      await load()
    } catch (err) {
      setError(err?.message || 'Superuser wijzigen mislukt.')
    } finally {
      setPending(false)
    }
  }

  function requestGrant(event) {
    event.preventDefault()
    const normalizedEmail = email.trim()
    if (!normalizedEmail) {
      setError('Vul het e-mailadres van een bestaande Inhuis-gebruiker in.')
      return
    }
    setError('')
    setResult('')
    setConfirmation({ action: 'grant', email: normalizedEmail })
  }

  return (
    <div data-testid="ip-owner-superusers-page">
      <Header title="Superusers" subtitle="IP-eigenaar" />
      <div className="rz-content"><div className="rz-content-inner">
        <Card>
          <h2>Superuser aanstellen</h2>
          <p>Vul het e-mailadres van een bestaande Inhuis-gebruiker in. De IP-eigenaar kan uitsluitend de Superuserrol beheren.</p>
          <form onSubmit={requestGrant}>
            <Input
              label="E-mailadres"
              type="email"
              value={email}
              onChange={(event) => setEmail(event.target.value)}
              autoComplete="off"
              disabled={pending}
            />
            <div style={{ marginTop: '12px' }}>
              <Button type="submit" disabled={pending}>Superuser maken</Button>
            </div>
          </form>
          {error && <p role="alert">{error}</p>}
          {result && <p role="status">{result}</p>}
        </Card>

        <Card>
          <h2>Actieve Superusers</h2>
          {loading && <p role="status">Superusers inlezen.</p>}
          {!loading && users.length === 0 && <p>Er zijn geen actieve Superusers.</p>}
          {!loading && users.length > 0 && (
            <div style={{ display: 'grid', gap: '10px' }}>
              {users.map((user) => (
                <div
                  key={user.user_id}
                  data-testid={`ip-owner-superuser-${user.user_id}`}
                  style={{ display: 'flex', gap: '12px', alignItems: 'center', justifyContent: 'space-between', flexWrap: 'wrap' }}
                >
                  <div>
                    <strong>{user.email}</strong>
                    <div>Superuser actief</div>
                  </div>
                  {user.can_revoke && (
                    <Button
                      type="button"
                      variant="secondary"
                      disabled={pending}
                      onClick={() => {
                        setError('')
                        setResult('')
                        setConfirmation({ action: 'revoke', user })
                      }}
                    >
                      Deactiveren
                    </Button>
                  )}
                </div>
              ))}
            </div>
          )}
        </Card>

        {confirmation ? (
          <Card>
            <div data-testid="ip-owner-superuser-confirmation">
              <h2>{confirmation.action === 'grant' ? 'Superuser maken?' : 'Superuser deactiveren?'}</h2>
              <p>
                Deze wijziging geldt voor <strong>{confirmation.action === 'grant' ? confirmation.email : confirmation.user.email}</strong>.
              </p>
              <div style={{ display: 'flex', gap: '10px', flexWrap: 'wrap' }}>
                <Button type="button" variant="secondary" disabled={pending} onClick={() => setConfirmation(null)}>
                  Annuleren
                </Button>
                <Button type="button" disabled={pending} onClick={confirmChange}>
                  {confirmation.action === 'grant' ? 'Definitief Superuser maken' : 'Definitief deactiveren'}
                </Button>
              </div>
            </div>
          </Card>
        ) : null}
      </div></div>
    </div>
  )
}
