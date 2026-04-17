import { useEffect, useMemo, useRef, useState } from 'react'
import { Link, useBlocker } from 'react-router-dom'
import AppShell from '../../app/AppShell'
import Card from '../../ui/Card'
import Button from '../../ui/Button'
import Input from '../../ui/Input'
import {
  createHouseholdMember,
  deleteHouseholdMember,
  fetchHouseholdMembers,
  updateHouseholdPermissionPolicy,
  updateHouseholdMember,
  updateHouseholdName,
} from './services/householdMembersService'
import './settingsHousehold.css'
import useDismissOnComponentClick from '../../lib/useDismissOnComponentClick.js'

const initialForm = {
  email: '',
  password: '',
  role: 'member',
}

function roleLabel(value) {
  const normalized = String(value || '').trim().toLowerCase()
  if (normalized === 'admin' || normalized === 'owner') return 'Eigenaar'
  if (normalized === 'viewer') return 'Kijker'
  return 'Lid'
}

function buildMutationMessage(payload, fallback) {
  const inviteStatus = String(payload?.invite_email_status || '').trim().toLowerCase()
  const inviteMessage = String(payload?.invite_email_message || '').trim()
  if (!inviteMessage) return fallback
  if (inviteStatus === 'sent') return `${fallback} ${inviteMessage}`.trim()
  let normalizedInviteMessage = inviteMessage
  if (/browser['’]s signature/i.test(normalizedInviteMessage)) {
    normalizedInviteMessage = [
      'Externe blokkade: Resend of een tussenliggende beveiligingslaag ziet dit verzoek als verdacht browser/signature-verkeer.',
      'Controleer of het afzenderadres een geverifieerd domein gebruikt, of REZZERV_RESEND_API_KEY in de backend-container actief is en of firewall, proxy, VPN of browserbeveiliging verkeer naar api.resend.com wijzigt.',
      normalizedInviteMessage,
    ].join('\n')
  }
  if (inviteStatus === 'disabled' || inviteStatus === 'not_configured' || inviteStatus === 'config_invalid') {
    return `${fallback} ${normalizedInviteMessage}`.trim()
  }
  return `${fallback} ${normalizedInviteMessage}`.trim()
}

function ConfirmRemoveModal({ member, onConfirm, onCancel, busy }) {
  if (!member) return null
  return (
    <div className="rz-modal-backdrop" role="presentation">
      <div
        className="rz-modal-card"
        role="dialog"
        aria-modal="true"
        aria-labelledby="household-remove-modal-title"
        data-testid="household-remove-modal"
      >
        <h3 id="household-remove-modal-title" className="rz-modal-title">Huishoudlid ontkoppelen</h3>
        <p className="rz-modal-text">
          Weet je zeker dat je <strong>{member.email}</strong> uit dit huishouden wilt verwijderen?
        </p>
        <div className="rz-modal-actions">
          <Button variant="secondary" onClick={onCancel} disabled={busy} data-testid="household-remove-cancel">
            Annuleren
          </Button>
          <Button onClick={onConfirm} disabled={busy} data-testid="household-remove-confirm">
            {busy ? 'Bezig…' : 'Ontkoppelen'}
          </Button>
        </div>
      </div>
    </div>
  )
}

export default function SettingsHouseholdPage() {
  const [data, setData] = useState(null)

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
  const [form, setForm] = useState(initialForm)
  const [isLoading, setIsLoading] = useState(true)
  const [isSaving, setIsSaving] = useState(false)
  const [message, setMessage] = useState('')
  const [error, setError] = useState('')
  const [memberToRemove, setMemberToRemove] = useState(null)
  const [householdNameDraft, setHouseholdNameDraft] = useState('')
  const [memberCanCreateArticle, setMemberCanCreateArticle] = useState(false)
  const [memberCanUpdateArticle, setMemberCanUpdateArticle] = useState(false)
  const [lastSavedPermissionSnapshot, setLastSavedPermissionSnapshot] = useState('')
  const [showLeaveModal, setShowLeaveModal] = useState(false)
  const dismissTimerRef = useRef(null)
  const isAdmin = Boolean(data?.is_household_admin)
  const roleAudit = Array.isArray(data?.role_change_audit) ? data.role_change_audit : []
  const permissionSnapshot = JSON.stringify({ articleCreate: Boolean(memberCanCreateArticle), articleUpdate: Boolean(memberCanUpdateArticle) })
  const permissionIsDirty = !isLoading && !!lastSavedPermissionSnapshot && permissionSnapshot !== lastSavedPermissionSnapshot
  const blocker = useBlocker(permissionIsDirty)

  useDismissOnComponentClick([() => setError(''), () => setMessage('')], Boolean(error || message))

  useEffect(() => {
    let active = true
    async function load() {
      setIsLoading(true)
      setError('')
      try {
        const payload = await fetchHouseholdMembers()
        if (!active) return
        setData(payload)
        setHouseholdNameDraft(String(payload?.household_name || ''))
        setMemberCanCreateArticle(Boolean(payload?.member_permission_policies?.['article.create']))
        setMemberCanUpdateArticle(Boolean(payload?.member_permission_policies?.['article.update']))
        setLastSavedPermissionSnapshot(JSON.stringify({ articleCreate: Boolean(payload?.member_permission_policies?.['article.create']), articleUpdate: Boolean(payload?.member_permission_policies?.['article.update']) }))
        syncHouseholdName(payload)
      } catch (loadError) {
        if (!active) return
        setError(loadError?.message || 'Huishoudleden konden niet worden geladen.')
      } finally {
        if (active) setIsLoading(false)
      }
    }
    load()
    return () => {
      active = false
    }
  }, [])

  useEffect(() => {
    if (blocker.state === 'blocked') setShowLeaveModal(true)
  }, [blocker.state])

  useEffect(() => {
    function handleBeforeUnload(event) {
      if (!permissionIsDirty) return
      event.preventDefault()
      event.returnValue = ''
    }
    window.addEventListener('beforeunload', handleBeforeUnload)
    return () => window.removeEventListener('beforeunload', handleBeforeUnload)
  }, [permissionIsDirty])

  useEffect(() => () => {
    if (dismissTimerRef.current) clearTimeout(dismissTimerRef.current)
  }, [])

  const householdSummary = useMemo(() => {
    if (!data) return 'Huishoudleden laden…'
    return `${data.household_name || 'Mijn huishouden'} · ${data.member_count || 0} leden`
  }, [data])

  async function applyMutation(run, successMessageBuilder) {
    setIsSaving(true)
    setError('')
    setMessage('')
    try {
      const payload = await run()
      setData(payload)
      setHouseholdNameDraft(String(payload?.household_name || ''))
      setMemberCanCreateArticle(Boolean(payload?.member_permission_policies?.['article.create']))
      setMemberCanUpdateArticle(Boolean(payload?.member_permission_policies?.['article.update']))
      setLastSavedPermissionSnapshot(JSON.stringify({ articleCreate: Boolean(payload?.member_permission_policies?.['article.create']), articleUpdate: Boolean(payload?.member_permission_policies?.['article.update']) }))
      syncHouseholdName(payload)
      const successMessage = typeof successMessageBuilder === 'function'
        ? successMessageBuilder(payload)
        : successMessageBuilder
      setMessage(successMessage)
      return true
    } catch (mutationError) {
      setError(mutationError?.message || 'Actie is niet gelukt.')
      return false
    } finally {
      setIsSaving(false)
    }
  }

  async function handleCreateMember(event) {
    event.preventDefault()
    const ok = await applyMutation(
      () => createHouseholdMember({
        email: form.email,
        password: form.password || undefined,
        role: form.role,
      }),
      (payload) => buildMutationMessage(payload, 'Huishoudlid opgeslagen.'),
    )
    if (ok) setForm(initialForm)
  }

  async function handleHouseholdNameSubmit(event) {
    event.preventDefault()
    await applyMutation(
      () => updateHouseholdName({ name: householdNameDraft }),
      (payload) => String(payload?.household_rename_message || 'Huishoudnaam opgeslagen.'),
    )
  }

  async function handleRoleChange(member, nextRole) {
    await applyMutation(
      () => updateHouseholdMember(member.email, { role: nextRole }),
      `${member.email} is nu ${roleLabel(nextRole).toLowerCase()}.`,
    )
  }

  async function handlePermissionSubmit(event) {
    event.preventDefault()
    const okCreate = await applyMutation(
      () => updateHouseholdPermissionPolicy('article.create', { member_allowed: memberCanCreateArticle }),
      (payload) => String(payload?.permission_policy_message || 'Lidrechten opgeslagen.'),
    )
    if (!okCreate) return false
    return applyMutation(
      () => updateHouseholdPermissionPolicy('article.update', { member_allowed: memberCanUpdateArticle }),
      (payload) => String(payload?.permission_policy_message || 'Lidrechten opgeslagen.'),
    )
  }

  async function handleSaveAndLeave() {
    const ok = await handlePermissionSubmit({ preventDefault() {} })
    if (!ok) return
    setShowLeaveModal(false)
    if (blocker.state === 'blocked') blocker.proceed()
  }

  function handleStay() {
    setShowLeaveModal(false)
    if (blocker.state === 'blocked') blocker.reset()
  }

  function handleLeaveWithoutSaving() {
    setShowLeaveModal(false)
    if (blocker.state === 'blocked') blocker.proceed()
  }

  async function confirmRemoveMember() {
    if (!memberToRemove) return
    const currentMember = memberToRemove
    const ok = await applyMutation(
      () => deleteHouseholdMember(currentMember.email),
      `${currentMember.email} is ontkoppeld van het huishouden.`,
    )
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
                <p className="rz-household-subtitle">
                  Beheer hier wie aan het huishouden is gekoppeld, welke rol ieder lid heeft en hoe het huishouden heet.
                </p>
                <p className="rz-household-summary">{householdSummary}</p>
                {!isLoading && !isAdmin ? (
                  <p className="rz-household-warning">
                    Alleen de admin van het huishouden kan leden toevoegen, ontkoppelen, rollen wijzigen of de naam aanpassen.
                  </p>
                ) : null}
              </div>

              <Link to="/instellingen" className="rz-household-back-link">← Terug naar instellingen</Link>
            </div>

            {(message || error) ? (
              <div className={error ? 'rz-inline-feedback rz-inline-feedback--error' : 'rz-inline-feedback rz-inline-feedback--success'}>
                {error || message}
              </div>
            ) : null}

            {isLoading ? <div>Huishoudleden laden…</div> : (
              <>
                <section className="rz-household-name-section">
                  <div>
                    <h3 className="rz-household-section-title">Naam huishouden</h3>
                    <p className="rz-household-section-copy">
                      De admin kan hier de naam van het huishouden aanpassen. Deze naam wordt ook gebruikt in uitnodigingen en de huishoudcontext van Rezzerv.
                    </p>
                  </div>
                  <form onSubmit={handleHouseholdNameSubmit} className="rz-form rz-household-name-form">
                    <div className="rz-household-form-field rz-household-form-field--wide">
                      <Input
                        label="Huishoudnaam"
                        value={householdNameDraft}
                        onChange={(event) => setHouseholdNameDraft(event.target.value)}
                        disabled={!isAdmin || isSaving}
                        required
                        maxLength={120}
                        data-testid="household-name-input"
                      />
                    </div>
                    {isAdmin ? (
                      <div className="rz-household-form-actions">
                        <Button
                          type="submit"
                          disabled={isSaving || !String(householdNameDraft || '').trim() || String(householdNameDraft || '').trim() === String(data?.household_name || '').trim()}
                          data-testid="household-name-save"
                        >
                          Naam opslaan
                        </Button>
                      </div>
                    ) : null}
                  </form>
                </section>

                <section className="rz-household-permissions-section">
                  <div>
                    <h3 className="rz-household-section-title">Rechten voor leden</h3>
                    <p className="rz-household-section-copy">
                      Stel hier als admin in of een lid van het huishouden artikelen mag toevoegen of wijzigen.
                    </p>
                  </div>
                  <form onSubmit={handlePermissionSubmit} className="rz-household-permissions-form">
                    <label className="rz-household-permission-toggle" data-testid="household-permission-article-create-toggle-wrap">
                      <input
                        type="checkbox"
                        checked={memberCanCreateArticle}
                        onChange={(event) => setMemberCanCreateArticle(event.target.checked)}
                        disabled={!isAdmin || isSaving}
                        data-testid="household-permission-article-create-toggle"
                      />
                      <span>
                        <strong>Lid mag artikel toevoegen</strong>
                        <small>Geldt voor het aanmaken van een nieuw artikel vanuit de import van winkel- en bonregels.</small>
                      </span>
                    </label>
                    <label className="rz-household-permission-toggle" data-testid="household-permission-article-update-toggle-wrap">
                      <input
                        type="checkbox"
                        checked={memberCanUpdateArticle}
                        onChange={(event) => setMemberCanUpdateArticle(event.target.checked)}
                        disabled={!isAdmin || isSaving}
                        data-testid="household-permission-article-update-toggle"
                      />
                      <span>
                        <strong>Lid mag artikel wijzigen</strong>
                        <small>Bij verlaten zonder opslaan verschijnt een waarschuwing.</small>
                      </span>
                    </label>
                    {isAdmin ? (
                      <div className="rz-household-form-actions">
                        <Button
                          type="submit"
                          disabled={isSaving || !permissionIsDirty}
                          data-testid="household-permission-save"
                        >
                          Rechten opslaan
                        </Button>
                      </div>
                    ) : (
                      <p className="rz-household-warning rz-household-warning--subtle">
                        Alleen de admin van het huishouden kan deze rechten aanpassen.
                      </p>
                    )}
                  </form>
                </section>

                <div className="rz-household-members-list">
                  {(data?.members || []).map((member) => {
                    const nextRole = member.display_role === 'admin' ? 'member' : 'owner'
                    return (
                      <div
                        key={member.email}
                        data-testid={`household-member-${member.email}`}
                        className="rz-household-member-card"
                      >
                        <div className="rz-household-member-content">
                          <div className="rz-household-member-email">{member.email}</div>
                          <div className="rz-household-member-meta">
                            Rol: <strong>{roleLabel(member.display_role)}</strong>
                            {member.is_current_user ? ' · huidige gebruiker' : ''}
                          </div>
                        </div>
                        <div className="rz-household-member-actions">
                          {isAdmin ? (
                            <>
                              <label className="rz-household-form-field" style={{ minWidth: '160px' }}>
                                <span className="rz-label">Rol</span>
                                <select
                                  className="rz-input rz-household-select"
                                  value={member.display_role === 'admin' ? 'owner' : (member.display_role === 'viewer' ? 'viewer' : 'member')}
                                  onChange={(event) => handleRoleChange(member, event.target.value)}
                                  disabled={isSaving || !member.can_change_role}
                                  data-testid={`household-role-select-${member.email}`}
                                >
                                  <option value="owner">Eigenaar</option>
                                  <option value="member">Lid</option>
                                  <option value="viewer">Kijker</option>
                                </select>
                              </label>
                              <Button
                                variant="secondary"
                                onClick={() => setMemberToRemove(member)}
                                disabled={isSaving || !member.can_remove}
                                data-testid={`household-remove-${member.email}`}
                              >
                                Ontkoppelen
                              </Button>
                            </>
                          ) : null}
                        </div>
                      </div>
                    )
                  })}
                </div>

                <section className="rz-household-form-section">
                  <div>
                    <h3 className="rz-household-section-title">Nieuw huishoudlid koppelen</h3>
                    <p className="rz-household-section-copy">
                      Gebruik een nieuw e-mailadres met wachtwoord voor een nieuw account. Laat het wachtwoord leeg als je een bestaand account opnieuw aan dit huishouden wilt koppelen.
                    </p>
                  </div>
                  <form onSubmit={handleCreateMember} className="rz-form rz-household-form">
                    <div className="rz-household-form-field rz-household-form-field--wide">
                      <Input
                        label="E-mailadres"
                        type="email"
                        value={form.email}
                        onChange={(event) => setForm((current) => ({ ...current, email: event.target.value }))}
                        disabled={!isAdmin || isSaving}
                        required
                        data-testid="household-member-email-input"
                      />
                    </div>
                    <div className="rz-household-form-field">
                      <Input
                        label="Wachtwoord"
                        type="text"
                        value={form.password}
                        onChange={(event) => setForm((current) => ({ ...current, password: event.target.value }))}
                        disabled={!isAdmin || isSaving}
                        placeholder="Bij nieuw account verplicht"
                        data-testid="household-member-password-input"
                      />
                    </div>
                    <label className="rz-household-form-field">
                      <span className="rz-label">Rol</span>
                      <select
                        className="rz-input rz-household-select"
                        value={form.role}
                        onChange={(event) => setForm((current) => ({ ...current, role: event.target.value }))}
                        disabled={!isAdmin || isSaving}
                        data-testid="household-member-role-select"
                      >
                        <option value="member">Lid</option>
                        <option value="owner">Eigenaar</option>
                        <option value="viewer">Kijker</option>
                      </select>
                    </label>
                    <div className="rz-form-actions rz-household-form-actions rz-household-form-field--wide">
                      <Button type="submit" disabled={!isAdmin || isSaving} data-testid="household-add-member">
                        {isSaving ? 'Opslaan…' : 'Lid koppelen'}
                      </Button>
                    </div>
                  </form>
                </section>

                <section className="rz-household-form-section">
                  <div>
                    <h3 className="rz-household-section-title">Rolwijzigingen</h3>
                    <p className="rz-household-section-copy">De laatste wijzigingen aan leden en rollen binnen dit huishouden.</p>
                  </div>
                  <div className="rz-household-members-list" data-testid="household-role-audit-list">
                    {roleAudit.length ? roleAudit.map((entry, index) => (
                      <div key={`${entry.changed_user_email}-${entry.created_at}-${index}`} className="rz-household-member-card">
                        <div className="rz-household-member-content">
                          <div className="rz-household-member-email">{entry.changed_user_email}</div>
                          <div className="rz-household-member-meta">
                            Actie: <strong>{entry.action_type === 'member_added' ? 'Lid toegevoegd' : entry.action_type === 'member_removed' ? 'Lid verwijderd' : 'Rol gewijzigd'}</strong>
                            {entry.old_role ? ` · van ${roleLabel(entry.old_role)}` : ''}
                            {entry.new_role ? ` naar ${roleLabel(entry.new_role)}` : ''}
                            {entry.changed_by_user_email ? ` · door ${entry.changed_by_user_email}` : ''}
                            {entry.created_at ? ` · ${entry.created_at}` : ''}
                          </div>
                        </div>
                      </div>
                    )) : (
                      <p className="rz-household-section-copy">Nog geen rolwijzigingen geregistreerd.</p>
                    )}
                  </div>
                </section>

              </>
            )}
          </div>
        </Card>

        <ConfirmRemoveModal
          member={memberToRemove}
          onConfirm={confirmRemoveMember}
          onCancel={() => setMemberToRemove(null)}
          busy={isSaving}
        />

        {showLeaveModal ? (
          <div className="rz-modal-backdrop" role="presentation">
            <div className="rz-modal-card" role="dialog" aria-modal="true" aria-labelledby="leave-household-settings-title" data-testid="warning-dialog">
              <h3 id="leave-household-settings-title" className="rz-modal-title">Wijzigingen niet opgeslagen</h3>
              <p className="rz-modal-text">Je hebt wijzigingen aangebracht die nog niet zijn opgeslagen.</p>
              <div className="rz-modal-actions">
                <Button variant="secondary" onClick={handleStay} data-testid="warning-cancel">Blijven</Button>
                <Button variant="secondary" onClick={handleLeaveWithoutSaving} data-testid="warning-confirm">Niet opslaan</Button>
                <Button onClick={handleSaveAndLeave} disabled={isSaving}>{isSaving ? 'Opslaan…' : 'Opslaan'}</Button>
              </div>
            </div>
          </div>
        ) : null}
      </div>
    </AppShell>
  )
}
