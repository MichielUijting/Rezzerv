import { useEffect, useMemo, useState } from 'react'
import AppShell from '../../app/AppShell'
import Card from '../../ui/Card'
import Button from '../../ui/Button'
import { useAppFeedback } from '../../ui/AppFeedbackProvider.jsx'
import { canCurrentUserPerform } from '../../lib/authSession'
import {
  deleteAuthorizationPermission,
  fetchAuthorizationOverview,
  setAuthorizationPermission,
  updateAuthorizationRole,
} from './services/authorizationMembershipService'
import './settingsAuthorization.css'

function permissionLabel(key) {
  return String(key || '').replaceAll('_', ' ').replaceAll('.', ' · ')
}

export default function SettingsAuthorizationPage() {
  const { showFeedback } = useAppFeedback()
  const [overview, setOverview] = useState({ members: [], roles: [], permissions: [] })
  const [selectedMembershipId, setSelectedMembershipId] = useState('')
  const [loading, setLoading] = useState(true)
  const [busyKey, setBusyKey] = useState('')

  const canManageMembers = canCurrentUserPerform('members.manage')
  const canManagePermissions = canCurrentUserPerform('permissions.manage')

  async function load(preferredMembershipId = '', { showError = true } = {}) {
    setLoading(true)
    try {
      const payload = await fetchAuthorizationOverview()
      setOverview(payload)
      const fallbackId = payload.members[0]?.membership_id || ''
      const nextId = payload.members.some((item) => item.membership_id === preferredMembershipId)
        ? preferredMembershipId
        : fallbackId
      setSelectedMembershipId(nextId)
      return true
    } catch (error) {
      if (showError) {
        showFeedback({
          variant: 'error',
          title: 'Autorisaties niet geladen',
          message: error?.message || 'De autorisatiegegevens konden niet worden geladen.',
        })
      }
      return false
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => { load() }, [])

  const selectedMember = useMemo(
    () => overview.members.find((item) => item.membership_id === selectedMembershipId) || null,
    [overview.members, selectedMembershipId],
  )

  const overrideMap = useMemo(() => {
    const result = new Map()
    for (const item of selectedMember?.permission_overrides || []) result.set(item.permission_key, item.effect)
    return result
  }, [selectedMember])

  async function runMutation(key, task, successMessage) {
    setBusyKey(key)
    try {
      await task()
      await load(selectedMembershipId, { showError: false })
      showFeedback({ variant: 'success', message: successMessage })
    } catch (error) {
      showFeedback({
        variant: 'error',
        title: 'Wijziging niet opgeslagen',
        message: error?.message || 'De autorisatiewijziging kon niet worden opgeslagen.',
      })
    } finally {
      setBusyKey('')
    }
  }

  function handleRoleChange(member, roleKey) {
    runMutation(
      `role:${member.membership_id}`,
      () => updateAuthorizationRole(member.membership_id, roleKey),
      `De rol van ${member.email} is opgeslagen.`,
    )
  }

  function handlePermissionChange(permissionKey, effect) {
    if (!selectedMember) return
    const mutationKey = `permission:${selectedMember.membership_id}:${permissionKey}`
    if (!effect) {
      runMutation(
        mutationKey,
        () => deleteAuthorizationPermission(selectedMember.membership_id, permissionKey),
        `De uitzondering voor ${permissionLabel(permissionKey)} is verwijderd.`,
      )
      return
    }
    runMutation(
      mutationKey,
      () => setAuthorizationPermission(selectedMember.membership_id, permissionKey, effect),
      `De uitzondering voor ${permissionLabel(permissionKey)} is opgeslagen.`,
    )
  }

  return (
    <AppShell title="Instellingen" showExit={false}>
      <div className="rz-authorization-page" data-testid="authorization-settings-page">
        <Card>
          <div className="rz-authorization-header">
            <div>
              <h2>Huishoudleden en autorisaties</h2>
              <p>Beheer rollen en individuele rechten. Alle autorisatiebesluiten blijven server-side.</p>
            </div>
          </div>

          {loading ? <div className="rz-authorization-loading">Autorisaties laden…</div> : (
            <>
              <section className="rz-authorization-section">
                <h3>Huishoudleden</h3>
                <div className="rz-authorization-table-wrap">
                  <table className="rz-authorization-table">
                    <thead><tr><th>Lid</th><th>Rol</th><th>Uitzonderingen</th></tr></thead>
                    <tbody>
                      {overview.members.map((member) => (
                        <tr key={member.membership_id} className={member.membership_id === selectedMembershipId ? 'is-selected' : ''}>
                          <td>
                            <button className="rz-authorization-member-button" type="button" onClick={() => setSelectedMembershipId(member.membership_id)}>
                              {member.email || 'Onbekend lid'}{member.is_current_user ? ' (jij)' : ''}
                            </button>
                          </td>
                          <td>
                            <select
                              aria-label={`Rol ${member.email}`}
                              value={member.role_key || ''}
                              disabled={!canManageMembers || busyKey === `role:${member.membership_id}`}
                              onChange={(event) => handleRoleChange(member, event.target.value)}
                            >
                              {overview.roles.map((role) => <option key={role.role_key} value={role.role_key}>{role.name}</option>)}
                            </select>
                          </td>
                          <td>{member.permission_overrides?.length || 0}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
                {!canManageMembers ? <p className="rz-authorization-note">Je kunt de leden en rollen bekijken, maar niet wijzigen.</p> : null}
              </section>

              <section className="rz-authorization-section">
                <div className="rz-authorization-permission-heading">
                  <div>
                    <h3>Individuele rechten</h3>
                    <p>{selectedMember ? `Uitzonderingen voor ${selectedMember.email}` : 'Selecteer een huishoudlid.'}</p>
                  </div>
                  <Button variant="secondary" onClick={() => load(selectedMembershipId)} disabled={loading || Boolean(busyKey)}>Vernieuwen</Button>
                </div>
                {selectedMember ? (
                  <div className="rz-authorization-permission-list">
                    {overview.permissions.map((permission) => {
                      const currentEffect = overrideMap.get(permission.permission_key) || ''
                      const mutationKey = `permission:${selectedMember.membership_id}:${permission.permission_key}`
                      return (
                        <div className="rz-authorization-permission-row" key={permission.permission_key}>
                          <div>
                            <strong>{permissionLabel(permission.permission_key)}</strong>
                            <span>{permission.description || permission.permission_key}</span>
                          </div>
                          <select
                            aria-label={`Recht ${permission.permission_key}`}
                            value={currentEffect}
                            disabled={!canManagePermissions || busyKey === mutationKey}
                            onChange={(event) => handlePermissionChange(permission.permission_key, event.target.value)}
                          >
                            <option value="">Via rol</option>
                            <option value="allow">Toestaan</option>
                            <option value="deny">Weigeren</option>
                          </select>
                        </div>
                      )
                    })}
                  </div>
                ) : null}
                {!canManagePermissions ? <p className="rz-authorization-note">Je kunt individuele rechten bekijken, maar niet wijzigen.</p> : null}
              </section>
            </>
          )}
        </Card>
      </div>
    </AppShell>
  )
}
