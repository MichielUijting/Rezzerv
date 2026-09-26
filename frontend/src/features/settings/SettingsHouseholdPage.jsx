import { useEffect, useMemo, useState } from 'react'
import AppShell from '../../app/AppShell'
import Card from '../../ui/Card'
import Button from '../../ui/Button'
import Input from '../../ui/Input'
import { useAppFeedback } from '../../ui/AppFeedbackProvider.jsx'
import {
  deleteHouseholdMember,
  fetchHouseholdMembers,
  updateHouseholdName,
} from './services/householdMembersService'
import {
  createHouseholdInvitation,
  fetchHouseholdInvitations,
  resendHouseholdInvitation,
  revokeHouseholdInvitation,
} from './services/householdInvitationsService'
import {
  fetchAuthorizationOverview,
  updateAuthorizationRole,
} from './services/authorizationMembershipService'
import './settingsHousehold.css'

const initialInvitationForm = { email: '' }

const ROLE_LABELS = {
  'household.viewer': 'Kijker (bestaande rol)',
  'household.member': 'Lid',
  'household.advanced_member': 'Geavanceerd lid (bestaande rol)',
  'household.admin': 'Beheerder',
  'household.owner': 'Superuser',
  'household.frontteam': 'Frontteamlid',
}

const INVITATION_STATUS_LABELS = {
  pending: 'In afwachting',
  accepted: 'Geaccepteerd',
  expired: 'Verlopen',
  revoked: 'Ingetrokken',
}

const DELIVERY_STATUS_LABELS = {
  not_sent: 'Nog niet verzonden',
  sent: 'E-mail verzonden',
  failed: 'Verzenden mislukt',
  disabled: 'E-mail nog niet geactiveerd',
  config_invalid: 'E-mailconfiguratie nog niet gereed',
}

const ASSIGNABLE_ROLE_KEYS = new Set(['household.member', 'household.admin'])

function payloadCanManageInvitations(payload) {
  const permissions = payload?.permissions
  if (permissions && Object.prototype.hasOwnProperty.call(permissions, 'members.manage')) {
    return Boolean(permissions['members.manage'])
  }
  return Boolean(payload?.is_household_admin)
}

function formatDateTime(value) {
  if (!value) return ''
  const parsed = new Date(value)
  if (Number.isNaN(parsed.getTime())) return String(value)
  return new Intl.DateTimeFormat('nl-NL', {
    dateStyle: 'medium',
    timeStyle: 'short',
  }).format(parsed)
}

function invitationCreatedMessage(delivery) {
  const status = String(delivery?.status || '')
  if (status === 'sent') return 'Uitnodiging aangemaakt en e-mail verzonden.'
  if (status === 'disabled' || status === 'config_invalid') {
    return 'Uitnodiging aangemaakt. E-mailverzending is nog niet geactiveerd.'
  }
  if (status === 'failed') {
    return 'Uitnodiging aangemaakt. De e-mail kon niet worden verzonden; probeer dit later opnieuw.'
  }
  return 'Uitnodiging aangemaakt.'
}

function ConfirmRemoveModal({ member, onConfirm, onCancel, busy }) {
  if (!member) return null
  return (
    <div className="rz-modal-backdrop" role="presentation">
      <div className="rz-modal-card" role="dialog" aria-modal="true" aria-labelledby="household-remove-modal-title" data-testid="household-remove-modal">
        <h3 id="household-remove-modal-title" className="rz-modal-title">Huishoudlid ontkoppelen</h3>
        <p className="rz-modal-text">Weet je zeker dat je <strong>{member.email}</strong> uit dit huishouden wilt verwijderen?</p>
        <div className="rz-modal-actions">
          <Button variant="secondary" onClick={onCancel} disabled={busy} data-testid="household-remove-cancel">Annuleren</Button>
          <Button onClick={onConfirm} disabled={busy} data-testid="household-remove-confirm">{busy ? 'Bezig…' : 'Ontkoppelen'}</Button>
        </div>
      </div>
    </div>
  )
}

function ConfirmInvitationRevokeModal({ invitation, onConfirm, onCancel, busy }) {
  if (!invitation) return null
  return (
    <div className="rz-modal-backdrop" role="presentation">
      <div className="rz-modal-card" role="dialog" aria-modal="true" aria-labelledby="household-invitation-revoke-modal-title" data-testid="household-invitation-revoke-modal">
        <h3 id="household-invitation-revoke-modal-title" className="rz-modal-title">Uitnodiging intrekken</h3>
        <p className="rz-modal-text">Weet je zeker dat je de uitnodiging voor <strong>{invitation.invitee_email}</strong> wilt intrekken?</p>
        <div className="rz-modal-actions">
          <Button variant="secondary" onClick={onCancel} disabled={busy} data-testid="household-invitation-revoke-cancel">Annuleren</Button>
          <Button onClick={onConfirm} disabled={busy} data-testid="household-invitation-revoke-confirm">{busy ? 'Bezig…' : 'Intrekken'}</Button>
        </div>
      </div>
    </div>
  )
}

export default function SettingsHouseholdPage() {
  const { showFeedback } = useAppFeedback()
  const [data, setData] = useState(null)
  const [authorization, setAuthorization] = useState({ members: [], roles: [] })
  const [invitations, setInvitations] = useState([])
  const [invitationForm, setInvitationForm] = useState(initialInvitationForm)
  const [isLoading, setIsLoading] = useState(true)
  const [isSaving, setIsSaving] = useState(false)
  const [isInvitationSaving, setIsInvitationSaving] = useState(false)
  const [busyInvitationId, setBusyInvitationId] = useState(null)
  const [memberToRemove, setMemberToRemove] = useState(null)
  const [invitationToRevoke, setInvitationToRevoke] = useState(null)
  const [householdNameDraft, setHouseholdNameDraft] = useState('')

  const isAdmin = Boolean(data?.is_household_admin)
  const canManageInvitations = payloadCanManageInvitations(data)
  const householdSummary = useMemo(() => {
    if (!data) return 'Huishouden laden…'
    return `${data.household_name || 'Mijn huishouden'} · ${data.member_count || 0} leden`
  }, [data])

  const authorizationByEmail = useMemo(() => new Map(
    authorization.members.map((member) => [String(member.email || '').toLowerCase(), member]),
  ), [authorization.members])

  function syncHouseholdName(payload) {
    const nextName = String(payload?.household_name || '').trim()
    if (!nextName) return
    try {
      window.localStorage.setItem('rezzerv_household_name', nextName)
      const rawContext = window.localStorage.getItem('rezzerv_auth_context')
      if (!rawContext) return
      const parsed = JSON.parse(rawContext)
      if (!parsed || typeof parsed !== 'object') return
      parsed.active_household_name = nextName
      window.localStorage.setItem('rezzerv_auth_context', JSON.stringify(parsed))
    } catch {}
  }

  function applyPayload(payload) {
    setData(payload)
    setHouseholdNameDraft(String(payload?.household_name || ''))
    syncHouseholdName(payload)
  }

  async function refreshAuthorization() {
    const payload = await fetchAuthorizationOverview()
    setAuthorization(payload)
    return payload
  }

  async function refreshInvitations() {
    const payload = await fetchHouseholdInvitations()
    setInvitations(Array.isArray(payload?.items) ? payload.items : [])
    return payload
  }

  useEffect(() => {
    let active = true
    async function load() {
      setIsLoading(true)
      try {
        const [householdPayload, authorizationPayload] = await Promise.all([
          fetchHouseholdMembers(),
          fetchAuthorizationOverview(),
        ])
        let invitationItems = []
        if (payloadCanManageInvitations(householdPayload)) {
          const invitationPayload = await fetchHouseholdInvitations()
          invitationItems = Array.isArray(invitationPayload?.items) ? invitationPayload.items : []
        }
        if (active) {
          applyPayload(householdPayload)
          setAuthorization(authorizationPayload)
          setInvitations(invitationItems)
        }
      } catch (error) {
        if (active) showFeedback({ variant: 'error', title: 'Huishouden niet geladen', message: error?.message || 'De huishoudgegevens konden niet worden geladen.' })
      } finally {
        if (active) setIsLoading(false)
      }
    }
    load()
    return () => { active = false }
  }, [showFeedback])

  async function runMutation(task, successMessage, { refreshRoles = true } = {}) {
    setIsSaving(true)
    try {
      const payload = await task()
      if (payload?.members) applyPayload(payload)
      if (refreshRoles) await refreshAuthorization()
      showFeedback({ variant: 'success', message: successMessage })
      return true
    } catch (error) {
      showFeedback({ variant: 'error', title: 'Wijziging niet opgeslagen', message: error?.message || 'De wijziging kon niet worden opgeslagen.' })
      return false
    } finally {
      setIsSaving(false)
    }
  }

  async function handleHouseholdNameSubmit(event) {
    event.preventDefault()
    await runMutation(() => updateHouseholdName({ name: householdNameDraft }), 'Huishoudnaam opgeslagen.', { refreshRoles: false })
  }

  async function handleCreateInvitation(event) {
    event.preventDefault()
    setIsInvitationSaving(true)
    try {
      const payload = await createHouseholdInvitation({ email: invitationForm.email })
      setInvitationForm(initialInvitationForm)
      await refreshInvitations()
      showFeedback({ variant: 'success', message: invitationCreatedMessage(payload?.delivery) })
    } catch (error) {
      showFeedback({ variant: 'error', title: 'Uitnodiging niet aangemaakt', message: error?.message || 'De uitnodiging kon niet worden aangemaakt.' })
    } finally {
      setIsInvitationSaving(false)
    }
  }

  async function handleResendInvitation(invitation) {
    const invitationId = String(invitation?.id || '')
    if (!invitationId) return
    setBusyInvitationId(invitationId)
    try {
      await resendHouseholdInvitation(invitationId)
      showFeedback({ variant: 'success', message: `Uitnodiging voor ${invitation.invitee_email} opnieuw verzonden.` })
    } catch (error) {
      showFeedback({ variant: 'error', title: 'Uitnodiging niet opnieuw verzonden', message: error?.message || 'De e-mail kon niet opnieuw worden verzonden.' })
    } finally {
      try {
        await refreshInvitations()
      } catch {}
      setBusyInvitationId(null)
    }
  }

  async function confirmRevokeInvitation() {
    if (!invitationToRevoke?.id) return
    const currentInvitation = invitationToRevoke
    setBusyInvitationId(String(currentInvitation.id))
    try {
      await revokeHouseholdInvitation(currentInvitation.id)
      await refreshInvitations()
      setInvitationToRevoke(null)
      showFeedback({ variant: 'success', message: `Uitnodiging voor ${currentInvitation.invitee_email} ingetrokken.` })
    } catch (error) {
      showFeedback({ variant: 'error', title: 'Uitnodiging niet ingetrokken', message: error?.message || 'De uitnodiging kon niet worden ingetrokken.' })
    } finally {
      setBusyInvitationId(null)
    }
  }

  async function handleRoleChange(member, roleKey) {
    const linkedAuthorization = authorizationByEmail.get(String(member.email || '').toLowerCase())
    if (!linkedAuthorization?.membership_id) {
      showFeedback({ variant: 'error', title: 'Rol niet gewijzigd', message: 'Het gekoppelde huishoudlid kon niet worden gevonden.' })
      return
    }
    await runMutation(
      () => updateAuthorizationRole(linkedAuthorization.membership_id, roleKey),
      `De rol van ${member.email} is gewijzigd naar ${ROLE_LABELS[roleKey] || 'de gekozen rol'}.`,
    )
  }

  async function confirmRemoveMember() {
    if (!memberToRemove) return
    const currentMember = memberToRemove
    const ok = await runMutation(() => deleteHouseholdMember(currentMember.email), `${currentMember.email} is ontkoppeld van het huishouden.`)
    if (ok) setMemberToRemove(null)
  }

  return (
    <AppShell title="Instellingen" showExit={false}>
      <div data-testid="household-settings-page" className="rz-household-page">
        <Card>
          <div className="rz-household-layout">
            <div className="rz-household-header">
              <div>
                <h2 className="rz-household-title">Huishouden</h2>
                <p className="rz-household-subtitle">Beheer de naam, gekoppelde gebruikers en hun rol binnen het huishouden.</p>
                <p className="rz-household-summary">{householdSummary}</p>
                {!isLoading && !isAdmin ? <p className="rz-household-warning">Alleen een beheerder kan de huishoudnaam, leden en rollen wijzigen.</p> : null}
              </div>
            </div>

            {isLoading ? <div>Huishouden laden…</div> : (
              <>
                <section className="rz-household-name-section">
                  <div>
                    <h3 className="rz-household-section-title">Naam huishouden</h3>
                    <p className="rz-household-section-copy">Deze naam wordt gebruikt in de actieve huishoudcontext en in uitnodigingen.</p>
                  </div>
                  <form onSubmit={handleHouseholdNameSubmit} className="rz-form rz-household-name-form">
                    <div className="rz-household-form-field rz-household-form-field--wide">
                      <Input label="Huishoudnaam" value={householdNameDraft} onChange={(event) => setHouseholdNameDraft(event.target.value)} disabled={!isAdmin || isSaving} required maxLength={120} data-testid="household-name-input" />
                    </div>
                    {isAdmin ? <div className="rz-household-form-actions"><Button type="submit" disabled={isSaving || !String(householdNameDraft || '').trim() || String(householdNameDraft || '').trim() === String(data?.household_name || '').trim()} data-testid="household-name-save">Naam opslaan</Button></div> : null}
                  </form>
                </section>

                <section className="rz-household-form-section">
                  <div>
                    <h3 className="rz-household-section-title">Gekoppelde huishoudleden</h3>
                    <p className="rz-household-section-copy">Kies hier de rol van ieder lid. Bekijk de betekenis van de rollen via Autorisaties.</p>
                  </div>
                  <div className="rz-household-members-list">
                    {(data?.members || []).map((member) => {
                      const linkedAuthorization = authorizationByEmail.get(String(member.email || '').toLowerCase())
                      const currentRoleKey = linkedAuthorization?.role_key || ''
                      const assignableRoles = authorization.roles.filter((role) => ASSIGNABLE_ROLE_KEYS.has(role.role_key))
                      const currentRole = authorization.roles.find((role) => role.role_key === currentRoleKey)
                        || (currentRoleKey ? { role_key: currentRoleKey, name: currentRoleKey } : null)
                      const roleOptions = currentRole && !ASSIGNABLE_ROLE_KEYS.has(currentRole.role_key)
                        ? [currentRole, ...assignableRoles]
                        : assignableRoles
                      return (
                        <div key={member.email} data-testid={`household-member-${member.email}`} className="rz-household-member-card">
                          <div className="rz-household-member-content">
                            <div className="rz-household-member-email">{member.email}</div>
                            <div className="rz-household-member-meta">{member.is_current_user ? 'Huidige gebruiker' : 'Gekoppeld huishoudlid'}</div>
                          </div>
                          <div className="rz-household-member-actions">
                            <label className="rz-household-form-field" style={{ minWidth: '180px' }}>
                              <span className="rz-label">Rol</span>
                              <select
                                className="rz-input rz-household-select"
                                value={currentRoleKey}
                                onChange={(event) => handleRoleChange(member, event.target.value)}
                                disabled={!isAdmin || isSaving || !linkedAuthorization}
                                data-testid={`household-role-select-${member.email}`}
                                aria-label={`Rol ${member.email}`}
                              >
                                {roleOptions.map((role) => <option key={role.role_key} value={role.role_key}>{ROLE_LABELS[role.role_key] || role.name}</option>)}
                              </select>
                            </label>
                            {isAdmin ? <Button variant="secondary" onClick={() => setMemberToRemove(member)} disabled={isSaving || !member.can_remove} data-testid={`household-remove-${member.email}`}>Ontkoppelen</Button> : null}
                          </div>
                        </div>
                      )
                    })}
                  </div>
                </section>

                <section className="rz-household-form-section" data-testid="household-invitations-section">
                  <div>
                    <h3 className="rz-household-section-title">Huishoudlid uitnodigen</h3>
                    <p className="rz-household-section-copy">Vul alleen het e-mailadres in. De ontvanger wordt pas Lid nadat de uitnodiging met het bedoelde account is geaccepteerd.</p>
                    {!canManageInvitations ? <p className="rz-household-warning rz-household-warning--subtle">Je hebt geen bevoegdheid om huishoudleden uit te nodigen.</p> : null}
                  </div>
                  <form onSubmit={handleCreateInvitation} className="rz-form rz-household-invitation-form">
                    <div className="rz-household-form-field">
                      <Input
                        label="E-mailadres"
                        type="email"
                        value={invitationForm.email}
                        onChange={(event) => setInvitationForm({ email: event.target.value })}
                        disabled={!canManageInvitations || isInvitationSaving}
                        required
                        data-testid="household-invitation-email-input"
                      />
                    </div>
                    <div className="rz-household-form-actions">
                      <Button type="submit" disabled={!canManageInvitations || isInvitationSaving || !String(invitationForm.email || '').trim()} data-testid="household-invitation-submit">
                        {isInvitationSaving ? 'Uitnodigen…' : 'Uitnodiging versturen'}
                      </Button>
                    </div>
                  </form>

                  {canManageInvitations ? (
                    <div className="rz-household-invitations-list" data-testid="household-invitations-list">
                      <h4 className="rz-household-invitations-title">Uitnodigingen</h4>
                      {invitations.length === 0 ? <p className="rz-household-section-copy">Er zijn nog geen uitnodigingen voor dit huishouden.</p> : null}
                      {invitations.map((invitation) => {
                        const lifecycleStatus = String(invitation.status || '')
                        const deliveryStatus = String(invitation.delivery_status || 'not_sent')
                        const isPending = lifecycleStatus === 'pending'
                        const isBusy = String(busyInvitationId || '') === String(invitation.id || '')
                        return (
                          <div key={invitation.id} className="rz-household-invitation-card" data-testid={`household-invitation-${invitation.id}`}>
                            <div className="rz-household-invitation-content">
                              <div className="rz-household-member-email">{invitation.invitee_email}</div>
                              <div className="rz-household-invitation-status-row">
                                <span className={`rz-household-status-badge rz-household-status-badge--${lifecycleStatus || 'unknown'}`} data-testid={`household-invitation-status-${invitation.id}`}>
                                  {INVITATION_STATUS_LABELS[lifecycleStatus] || lifecycleStatus || 'Onbekend'}
                                </span>
                                <span className="rz-household-delivery-status" data-testid={`household-invitation-delivery-${invitation.id}`}>
                                  {DELIVERY_STATUS_LABELS[deliveryStatus] || deliveryStatus}
                                </span>
                              </div>
                              {invitation.expires_at && isPending ? <div className="rz-household-member-meta">Geldig tot {formatDateTime(invitation.expires_at)}</div> : null}
                              {invitation.last_delivery_error && deliveryStatus !== 'sent' ? <div className="rz-household-invitation-delivery-detail">{invitation.last_delivery_error}</div> : null}
                            </div>
                            {isPending ? (
                              <div className="rz-household-member-actions">
                                <Button variant="secondary" onClick={() => handleResendInvitation(invitation)} disabled={isBusy} data-testid={`household-invitation-resend-${invitation.id}`}>
                                  {isBusy ? 'Bezig…' : 'Opnieuw versturen'}
                                </Button>
                                <Button variant="secondary" onClick={() => setInvitationToRevoke(invitation)} disabled={isBusy} data-testid={`household-invitation-revoke-${invitation.id}`}>Intrekken</Button>
                              </div>
                            ) : null}
                          </div>
                        )
                      })}
                    </div>
                  ) : null}
                </section>
              </>
            )}
          </div>
        </Card>

        <ConfirmRemoveModal member={memberToRemove} onConfirm={confirmRemoveMember} onCancel={() => setMemberToRemove(null)} busy={isSaving} />
        <ConfirmInvitationRevokeModal invitation={invitationToRevoke} onConfirm={confirmRevokeInvitation} onCancel={() => setInvitationToRevoke(null)} busy={Boolean(busyInvitationId)} />
      </div>
    </AppShell>
  )
}
