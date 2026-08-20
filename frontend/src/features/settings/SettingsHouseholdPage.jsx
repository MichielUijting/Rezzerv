import { useEffect, useMemo, useState } from 'react'
import AppShell from '../../app/AppShell'
import Card from '../../ui/Card'
import Button from '../../ui/Button'
import Input from '../../ui/Input'
import { useAppFeedback } from '../../ui/AppFeedbackProvider.jsx'
import {
  createHouseholdMember,
  deleteHouseholdMember,
  fetchHouseholdMembers,
  updateHouseholdName,
} from './services/householdMembersService'
import {
  fetchAuthorizationOverview,
  updateAuthorizationRole,
} from './services/authorizationMembershipService'
import './settingsHousehold.css'

const initialForm = { email: '', password: '' }

const ROLE_LABELS = {
  'household.viewer': 'Kijker (bestaande rol)',
  'household.member': 'Lid',
  'household.advanced_member': 'Geavanceerd lid (bestaande rol)',
  'household.admin': 'Beheerder',
  'household.owner': 'Superuser',
  'household.frontteam': 'Frontteamlid',
}

const ASSIGNABLE_ROLE_KEYS = new Set(['household.member', 'household.admin'])

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

export default function SettingsHouseholdPage() {
  const { showFeedback } = useAppFeedback()
  const [data, setData] = useState(null)
  const [authorization, setAuthorization] = useState({ members: [], roles: [] })
  const [form, setForm] = useState(initialForm)
  const [isLoading, setIsLoading] = useState(true)
  const [isSaving, setIsSaving] = useState(false)
  const [memberToRemove, setMemberToRemove] = useState(null)
  const [householdNameDraft, setHouseholdNameDraft] = useState('')

  const isAdmin = Boolean(data?.is_household_admin)
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

  useEffect(() => {
    let active = true
    async function load() {
      setIsLoading(true)
      try {
        const [householdPayload, authorizationPayload] = await Promise.all([
          fetchHouseholdMembers(),
          fetchAuthorizationOverview(),
        ])
        if (active) {
          applyPayload(householdPayload)
          setAuthorization(authorizationPayload)
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

  async function handleCreateMember(event) {
    event.preventDefault()
    const ok = await runMutation(
      () => createHouseholdMember({ email: form.email, password: form.password || undefined, role: 'member' }),
      'Huishoudlid gekoppeld. De standaardrol Lid is toegepast.',
    )
    if (ok) setForm(initialForm)
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

                <section className="rz-household-form-section">
                  <div>
                    <h3 className="rz-household-section-title">Nieuw huishoudlid koppelen</h3>
                    <p className="rz-household-section-copy">Nieuwe leden krijgen standaard de rol Lid. Wijzig de rol daarna hierboven.</p>
                  </div>
                  <form onSubmit={handleCreateMember} className="rz-form rz-household-form">
                    <div className="rz-household-form-field rz-household-form-field--wide"><Input label="E-mailadres" type="email" value={form.email} onChange={(event) => setForm((current) => ({ ...current, email: event.target.value }))} disabled={!isAdmin || isSaving} required data-testid="household-member-email-input" /></div>
                    <div className="rz-household-form-field"><Input label="Wachtwoord" type="text" value={form.password} onChange={(event) => setForm((current) => ({ ...current, password: event.target.value }))} disabled={!isAdmin || isSaving} placeholder="Bij nieuw account verplicht" data-testid="household-member-password-input" /></div>
                    <div className="rz-form-actions rz-household-form-actions rz-household-form-field--wide"><Button type="submit" disabled={!isAdmin || isSaving} data-testid="household-add-member">{isSaving ? 'Opslaan…' : 'Lid koppelen'}</Button></div>
                  </form>
                </section>
              </>
            )}
          </div>
        </Card>

        <ConfirmRemoveModal member={memberToRemove} onConfirm={confirmRemoveMember} onCancel={() => setMemberToRemove(null)} busy={isSaving} />
      </div>
    </AppShell>
  )
}
