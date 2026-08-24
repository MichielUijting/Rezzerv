import React from 'react'
import { API_BASE_URL } from '../../lib/apiClient.js'
import Button from '../../ui/Button'
import Card from '../../ui/Card'
import Header from '../../ui/Header'

const SPECIAL_ROLES = [
  { roleKey: 'platform.superuser', slug: 'superuser', label: 'Superuser' },
  { roleKey: 'platform.frontteam', slug: 'frontteam', label: 'Frontteamlid' },
  { roleKey: 'platform.platform_admin', slug: 'platform-admin', label: 'Platformbeheerder' },
]

function roleLabel(roleKey, roles) {
  return roles.find((role) => role.role_key === roleKey)?.name || roleKey
}

export default function PlatformAuthorizationsPage() {
  const [users, setUsers] = React.useState([])
  const [roles, setRoles] = React.useState([])
  const [canManageSpecialRoles, setCanManageSpecialRoles] = React.useState(false)
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
      setCanManageSpecialRoles(payload?.can_manage_special_roles === true)
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
        `${API_BASE_URL}/api/platform/authorizations/users/${encodeURIComponent(pending.user.user_id)}/${pending.role.slug}/${action}`,
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
          ? `${pending.role.label} is toegekend aan ${pending.user.email}.`
          : `${pending.role.label} is ingetrokken bij ${pending.user.email}.`,
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
        subtitle="Bekijk platformrollen; alleen de IP-eigenaar kan Superuser, Frontteamlid en Platformbeheerder aanstellen of intrekken."
      />

      <Card>
        <p>
          Inventarisatie gebruikt <strong>platform.permissions.manage</strong>. Speciale rolmutaties gebruiken
          afzonderlijk <strong>platform.special_roles.manage</strong>. De backend blijft de enige authority;
          er is geen householdcontext en geen H0-fallback voor deze beheeractie.
        </p>
        <p>
          De IP-eigenaar is beschermd en kan hier niet worden verwijderd of gedegradeerd. Superuser en
          Platformbeheerder mogen samen bestaan; Frontteamlid blijft een afzonderlijke accountvorm met een eigen
          persoonlijk regulier huishouden.
        </p>
        <p>
          Wachtwoorden, hashes en sessietokens worden niet geprojecteerd. Iedere rolwijziging wordt in de bestaande
          authorization-audit vastgelegd en is vanaf de eerstvolgende request effectief.
        </p>
        {!canManageSpecialRoles ? (
          <p data-testid="platform-authorizations-read-only">
            Read-only: alleen de IP-eigenaar beschikt over platform.special_roles.manage.
          </p>
        ) : null}
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
        const roleActions = user.role_actions || {}
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
              {user.is_ip_owner ? <p>Beschermde IP-eigenaar — niet wijzigbaar via regulier rolbeheer.</p> : null}

              {SPECIAL_ROLES.map((role) => {
                const action = roleActions[role.roleKey] || {}
                if (action.active && action.can_revoke) {
                  return (
                    <Button
                      key={role.roleKey}
                      type="button"
                      onClick={() => {
                        setPending({ user, role, action: 'revoke' })
                        setResult('')
                      }}
                    >
                      {role.label} intrekken
                    </Button>
                  )
                }
                if (!action.active && action.can_grant) {
                  return (
                    <Button
                      key={role.roleKey}
                      type="button"
                      onClick={() => {
                        setPending({ user, role, action: 'grant' })
                        setResult('')
                      }}
                    >
                      {role.label} toekennen
                    </Button>
                  )
                }
                if (canManageSpecialRoles && (action.grant_blocked_reason || action.revoke_blocked_reason)) {
                  const reason = action.active ? action.revoke_blocked_reason : action.grant_blocked_reason
                  return reason ? <p key={role.roleKey}>{role.label}: {reason}</p> : null
                }
                return null
              })}
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
                <p>{role.protected ? 'Beschermde rol' : role.managed_by_this_page ? 'Beheerbaar door IP-eigenaar' : 'Read-only op deze pagina'}</p>
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
              {pending.role.label} {pending.action === 'grant' ? 'definitief toekennen?' : 'definitief intrekken?'}
            </h3>
            <p>
              Deze wijziging geldt voor <strong>{pending.user.email}</strong> en wordt direct in de canonical
              platformrol-authority vastgelegd.
            </p>
            <p>Alleen de gekozen speciale platformrol wordt gewijzigd; overige rollen blijven behouden.</p>
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
