import React from 'react'
import { API_BASE_URL } from '../../lib/apiClient.js'
import Button from '../../ui/Button'
import Card from '../../ui/Card'
import Header from '../../ui/Header'

const PLATFORM_ADMIN_ROLE_KEY = 'platform.platform_admin'

function roleLabel(roleKey, roles) {
  return roles.find((role) => role.role_key === roleKey)?.name || roleKey
}

export default function PlatformAuthorizationsPage() {
  const [users, setUsers] = React.useState([])
  const [roles, setRoles] = React.useState([])
  const [loading, setLoading] = React.useState(true)
  const [error, setError] = React.useState('')
  const [result, setResult] = React.useState('')
  const [pending, setPending] = React.useState(null)
  const [submitting, setSubmitting] = React.useState(false)

  const loadAuthorizations = React.useCallback(async () => {
    setLoading(true)
    setError('')
    try {
      const response = await fetch(`${API_BASE_URL}/api/platform/authorizations`, {
        method: 'GET',
        credentials: 'include',
        headers: { Accept: 'application/json' },
      })
      if (!response.ok) {
        const payload = await response.json().catch(() => ({}))
        throw new Error(payload?.detail || `Platformautorisaties ophalen mislukt (${response.status})`)
      }
      const payload = await response.json()
      setUsers(Array.isArray(payload?.users) ? payload.users : [])
      setRoles(Array.isArray(payload?.roles) ? payload.roles : [])
    } catch (err) {
      setError(err?.message || 'Platformautorisaties ophalen mislukt.')
    } finally {
      setLoading(false)
    }
  }, [])

  React.useEffect(() => {
    loadAuthorizations()
  }, [loadAuthorizations])

  async function confirmRoleChange() {
    if (!pending || submitting) return
    const action = pending.action === 'revoke' ? 'revoke' : 'grant'
    setSubmitting(true)
    setError('')
    setResult('')
    try {
      const response = await fetch(
        `${API_BASE_URL}/api/platform/authorizations/users/${encodeURIComponent(pending.user.user_id)}/platform-admin/${action}`,
        {
          method: 'POST',
          credentials: 'include',
          headers: { Accept: 'application/json' },
        },
      )
      if (!response.ok) {
        const payload = await response.json().catch(() => ({}))
        throw new Error(payload?.detail || `Platformautorisatie wijzigen mislukt (${response.status})`)
      }
      const payload = await response.json()
      const item = payload?.item
      if (item?.user_id) {
        setUsers((current) => current.map((user) => (
          user.user_id === item.user_id ? item : user
        )))
      }
      setResult(
        action === 'grant'
          ? `${pending.user.email} is Platformbeheerder geworden.`
          : `De Platformbeheerder-rol van ${pending.user.email} is ingetrokken.`,
      )
      setPending(null)
    } catch (err) {
      setError(err?.message || 'Platformautorisatie wijzigen mislukt.')
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <div data-testid="platform-authorizations-page">
      <Header
        title="Platformautorisaties"
        subtitle="Bekijk platformrollen en beheer uitsluitend de normale Platformbeheerder-toekenning."
      />

      <Card>
        <p>
          Deze pagina gebruikt uitsluitend <strong>platform.permissions.manage</strong>. De autorisatie wordt
          live uit de canonical role-permission authority gelezen; er is geen householdcontext en geen H0-fallback.
        </p>
        <p>
          Alleen <strong>{PLATFORM_ADMIN_ROLE_KEY}</strong> is hier wijzigbaar. IP-owner, de bestaande
          Superuser-v1.1-rol, support en frontteam blijven read-only en worden niet via deze capability aangepast.
        </p>
        <p>
          Wachtwoorden, hashes en sessietokens worden niet geprojecteerd. Iedere rolwijziging wordt in de bestaande
          authorization-audit vastgelegd en is vanaf de eerstvolgende request effectief.
        </p>
      </Card>

      {error ? <Card><p role="alert">{error}</p></Card> : null}
      {result ? <Card><p role="status">{result}</p></Card> : null}
      {loading ? <Card><p>Platformautorisaties laden...</p></Card> : null}

      {!loading && !users.length ? <Card><p>Er zijn geen gebruikers gevonden.</p></Card> : null}

      {!loading && users.map((user) => {
        const roleKeys = Array.isArray(user.platform_role_keys) ? user.platform_role_keys : []
        const permissionCount = Array.isArray(user.effective_platform_permissions)
          ? user.effective_platform_permissions.length
          : 0
        return (
          <Card key={user.user_id}>
            <div data-testid={`platform-authorization-user-${user.user_id}`}>
              <h3>{user.email}</h3>
              <p>Gebruiker-ID: {user.user_id}</p>
              <p>Status: {user.account_status === 'suspended' ? 'Geschorst' : 'Actief'}</p>
              <p>
                Platformrollen: {roleKeys.length
                  ? roleKeys.map((roleKey) => roleLabel(roleKey, roles)).join(', ')
                  : 'Geen'}
              </p>
              <p>Effectieve platformpermissies: {permissionCount}</p>

              {user.has_platform_admin ? (
                user.is_current ? (
                  <p>Huidig beheeraccount — de eigen Platformbeheerder-rol kan hier niet worden ingetrokken.</p>
                ) : user.can_revoke_platform_admin ? (
                  <Button
                    type="button"
                    onClick={() => {
                      setPending({ user, action: 'revoke' })
                      setResult('')
                    }}
                  >
                    Platformbeheerder intrekken
                  </Button>
                ) : null
              ) : user.can_grant_platform_admin ? (
                <Button
                  type="button"
                  onClick={() => {
                    setPending({ user, action: 'grant' })
                    setResult('')
                  }}
                >
                  Platformbeheerder maken
                </Button>
              ) : user.account_status === 'suspended' ? (
                <p>Een geschorst account kan geen Platformbeheerder worden.</p>
              ) : null}
            </div>
          </Card>
        )
      })}

      {!loading && roles.length ? (
        <Card>
          <div data-testid="platform-role-matrix">
            <h2>Canonical platformrollen</h2>
            {roles.map((role) => (
              <div key={role.role_key} data-testid={`platform-role-${role.role_key}`}>
                <h3>{role.name}</h3>
                <p>Rol: {role.role_key}</p>
                <p>{role.managed_by_this_page ? 'Beheerbaar op deze pagina' : 'Read-only op deze pagina'}</p>
                <p>Permissies: {(role.permissions || []).join(', ') || 'Geen'}</p>
              </div>
            ))}
          </div>
        </Card>
      ) : null}

      {pending ? (
        <Card>
          <div data-testid="platform-authorization-confirmation">
            <h3>
              {pending.action === 'grant'
                ? 'Platformbeheerder definitief toekennen?'
                : 'Platformbeheerder definitief intrekken?'}
            </h3>
            <p>
              Deze wijziging geldt voor <strong>{pending.user.email}</strong> en wordt direct in de canonical
              platformrol-authority vastgelegd.
            </p>
            <p>Householdrollen, memberships en speciale platformrollen worden niet gewijzigd.</p>
            <div>
              <Button
                type="button"
                variant="secondary"
                disabled={submitting}
                onClick={() => setPending(null)}
              >
                Annuleren
              </Button>
              <Button type="button" disabled={submitting} onClick={confirmRoleChange}>
                {submitting
                  ? 'Wijzigen...'
                  : pending.action === 'grant'
                    ? 'Definitief toekennen'
                    : 'Definitief intrekken'}
              </Button>
            </div>
          </div>
        </Card>
      ) : null}
    </div>
  )
}
