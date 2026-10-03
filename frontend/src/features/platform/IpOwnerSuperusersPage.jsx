import React from 'react'
import { API_BASE_URL } from '../../lib/apiClient.js'
import Button from '../../ui/Button.jsx'
import Card from '../../ui/Card.jsx'
import Header from '../../ui/Header.jsx'

export default function IpOwnerSuperusersPage() {
  const [users, setUsers] = React.useState([])
  const [loading, setLoading] = React.useState(true)
  const [error, setError] = React.useState('')
  const [result, setResult] = React.useState('')
  const [pending, setPending] = React.useState(null)

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

  async function changeRole(user, action) {
    if (pending) return
    setPending(`${user.user_id}:${action}`)
    setError('')
    setResult('')
    try {
      const response = await fetch(
        `${API_BASE_URL}/api/platform/authorizations/users/${encodeURIComponent(user.user_id)}/superuser/${action}`,
        { method: 'POST', credentials: 'include', headers: { Accept: 'application/json' } },
      )
      const payload = await response.json().catch(() => ({}))
      if (!response.ok) throw new Error(payload?.detail || 'Superuser wijzigen mislukt.')
      setResult(action === 'grant'
        ? `${user.email} is nu Superuser.`
        : `${user.email} is niet langer Superuser.`)
      await load()
    } catch (err) {
      setError(err?.message || 'Superuser wijzigen mislukt.')
    } finally {
      setPending(null)
    }
  }

  return (
    <div data-testid="ip-owner-superusers-page">
      <Header title="Superusers" subtitle="IP-eigenaar" />
      <div className="rz-content"><div className="rz-content-inner">
        <Card>
          <p>De IP-eigenaar kan uitsluitend Superusers aanstellen of deactiveren.</p>
          {loading && <p role="status">Superusers inlezen.</p>}
          {error && <p role="alert">{error}</p>}
          {result && <p role="status">{result}</p>}
          {!loading && (
            <div style={{ display: 'grid', gap: '10px' }}>
              {users.map((user) => {
                const isBusy = pending?.startsWith(`${user.user_id}:`)
                return (
                  <div
                    key={user.user_id}
                    data-testid={`ip-owner-superuser-${user.user_id}`}
                    style={{ display: 'flex', gap: '12px', alignItems: 'center', justifyContent: 'space-between', flexWrap: 'wrap' }}
                  >
                    <div>
                      <strong>{user.email}</strong>
                      <div>{user.is_ip_owner ? 'IP-eigenaar' : user.is_superuser ? 'Superuser actief' : 'Geen Superuser'}</div>
                    </div>
                    {!user.is_ip_owner && user.is_superuser && user.can_revoke && (
                      <Button type="button" variant="secondary" disabled={isBusy} onClick={() => changeRole(user, 'revoke')}>
                        Deactiveren
                      </Button>
                    )}
                    {!user.is_ip_owner && !user.is_superuser && user.can_grant && (
                      <Button type="button" disabled={isBusy} onClick={() => changeRole(user, 'grant')}>
                        Superuser maken
                      </Button>
                    )}
                  </div>
                )
              })}
            </div>
          )}
        </Card>
      </div></div>
    </div>
  )
}
