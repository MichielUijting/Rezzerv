import React from 'react'
import { API_BASE_URL } from '../../lib/apiClient.js'
import Button from '../../ui/Button.jsx'
import Card from '../../ui/Card.jsx'
import Header from '../../ui/Header.jsx'

const FRONTTEAM_ROLE_KEY = 'platform.frontteam'

export default function SettingsFrontteamPage() {
  const [users, setUsers] = React.useState([])
  const [loading, setLoading] = React.useState(true)
  const [error, setError] = React.useState('')
  const [result, setResult] = React.useState('')
  const [pending, setPending] = React.useState(null)
  const [submitting, setSubmitting] = React.useState(false)

  const loadUsers = React.useCallback(async () => {
    setLoading(true)
    setError('')
    try {
      const response = await fetch(`${API_BASE_URL}/api/platform/frontteam-management`, {
        credentials: 'include',
        headers: { Accept: 'application/json' },
      })
      if (!response.ok) {
        const payload = await response.json().catch(() => ({}))
        throw new Error(payload?.detail || `Gebruikers ophalen mislukt (${response.status})`)
      }
      const payload = await response.json()
      setUsers(Array.isArray(payload?.users) ? payload.users : [])
    } catch (err) {
      setError(err?.message || 'Gebruikers ophalen mislukt.')
    } finally {
      setLoading(false)
    }
  }, [])

  React.useEffect(() => { loadUsers() }, [loadUsers])

  async function confirmChange() {
    if (!pending || submitting) return
    const active = (pending.user.platform_role_keys || []).includes(FRONTTEAM_ROLE_KEY)
    const action = active ? 'revoke' : 'grant'
    setSubmitting(true)
    setError('')
    setResult('')
    try {
      const response = await fetch(
        `${API_BASE_URL}/api/platform/authorizations/users/${encodeURIComponent(pending.user.user_id)}/frontteam/${action}`,
        { method: 'POST', credentials: 'include', headers: { Accept: 'application/json' } },
      )
      if (!response.ok) {
        const payload = await response.json().catch(() => ({}))
        throw new Error(payload?.detail || `Frontteamlidmaatschap wijzigen mislukt (${response.status})`)
      }
      const payload = await response.json()
      const item = payload?.item
      if (item?.user_id) {
        setUsers((current) => current.map((user) => user.user_id === item.user_id ? item : user))
      }
      setResult(active
        ? `${pending.user.email} is geen Frontteamlid meer. Het eigen huishouden en de huishoudrol zijn behouden.`
        : `${pending.user.email} is nu Frontteamlid. Het eigen huishouden en de huishoudrol zijn behouden.`)
      setPending(null)
    } catch (err) {
      setError(err?.message || 'Frontteamlidmaatschap wijzigen mislukt.')
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <div data-testid="settings-frontteam-page">
      <Header title="Frontteam beheren" subtitle="Geef een bestaande gebruiker aanvullende Frontteambevoegdheden." />
      <div className="rz-content"><div className="rz-content-inner">
        <Card>
          <p>Frontteamlidmaatschap is een aanvullende platformrol. Het reguliere huishouden en de rol binnen dat huishouden blijven ongewijzigd.</p>
          <p>Superuser en IP-eigenaar kunnen deze aanvullende rol toekennen of intrekken.</p>
        </Card>
        {error ? <Card><p role="alert">{error}</p></Card> : null}
        {result ? <Card><p role="status">{result}</p></Card> : null}
        {loading ? <Card><p>Gebruikers laden...</p></Card> : null}
        {!loading && users.map((user) => {
          const active = (user.platform_role_keys || []).includes(FRONTTEAM_ROLE_KEY)
          const action = user.role_actions?.[FRONTTEAM_ROLE_KEY] || {}
          const allowed = active ? action.can_revoke : action.can_grant
          return (
            <Card key={user.user_id}>
              <div data-testid={`frontteam-user-${user.user_id}`}>
                <h3>{user.email}</h3>
                <p>Frontteam: {active ? 'Ja' : 'Nee'}</p>
                {allowed ? (
                  <Button type="button" onClick={() => setPending({ user })}>
                    {active ? 'Frontteamlidmaatschap intrekken' : 'Frontteamlid maken'}
                  </Button>
                ) : action.grant_blocked_reason || action.revoke_blocked_reason ? (
                  <p>{active ? action.revoke_blocked_reason : action.grant_blocked_reason}</p>
                ) : null}
              </div>
            </Card>
          )
        })}
      </div></div>
      {pending ? (
        <Card>
          <div data-testid="frontteam-confirmation">
            <h3>{(pending.user.platform_role_keys || []).includes(FRONTTEAM_ROLE_KEY) ? 'Frontteamlidmaatschap intrekken?' : 'Frontteamlid maken?'}</h3>
            <p>Gebruiker: <strong>{pending.user.email}</strong></p>
            <p>Het eigen reguliere huishouden en de huishoudrol worden niet gewijzigd.</p>
            <Button type="button" variant="secondary" disabled={submitting} onClick={() => setPending(null)}>Annuleren</Button>
            <Button type="button" disabled={submitting} onClick={confirmChange}>{submitting ? 'Wijzigen...' : 'Bevestigen'}</Button>
          </div>
        </Card>
      ) : null}
    </div>
  )
}
