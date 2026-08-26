import { useState } from 'react'
import Card from '../../ui/Card.jsx'
import Button from '../../ui/Button.jsx'
import Input from '../../ui/Input.jsx'
import {
  createHouseholdInvitation,
  revokeHouseholdInvitation,
} from '../settings/services/householdInvitationsService.js'
import { ChoiceSummary, RadioChoices } from './OnboardingChoiceControls.jsx'

function invitationMessage(email, delivery) {
  const status = String(delivery?.status || '')
  if (status === 'sent') return `Uitnodiging verzonden naar ${email}.`
  if (status === 'disabled' || status === 'config_invalid') {
    return `Uitnodiging voor ${email} is aangemaakt. E-mailverzending is in deze omgeving nog niet geactiveerd.`
  }
  if (status === 'failed') {
    return `Uitnodiging voor ${email} is aangemaakt, maar de e-mail kon niet worden verzonden.`
  }
  return `Uitnodiging voor ${email} is aangemaakt.`
}

export default function SharedHouseholdMinimumPage({
  initialHouseholdName = '',
  primaryUseCaseTitle = '',
  previousChoices = [],
  onSubmit,
  saving = false,
  error = '',
}) {
  const [householdName, setHouseholdName] = useState(String(initialHouseholdName || ''))
  const [usageMode, setUsageMode] = useState('')
  const [inviteEmail, setInviteEmail] = useState('')
  const [inviteSaving, setInviteSaving] = useState(false)
  const [inviteMessage, setInviteMessage] = useState('')
  const [inviteError, setInviteError] = useState('')
  const [onboardingInvitations, setOnboardingInvitations] = useState([])

  const canFinish = Boolean(String(householdName || '').trim() && usageMode && !inviteSaving)
  const normalizedInviteEmail = String(inviteEmail || '').trim().toLowerCase()
  const canInvite = usageMode === 'together' && normalizedInviteEmail.includes('@') && !inviteSaving

  async function changeUsageMode(nextMode) {
    if (nextMode === usageMode || inviteSaving) return
    setInviteError('')

    if (nextMode === 'alone' && onboardingInvitations.length) {
      setInviteSaving(true)
      try {
        for (const invitation of onboardingInvitations) {
          await revokeHouseholdInvitation(invitation.id)
        }
        setOnboardingInvitations([])
        setInviteMessage('')
        setInviteEmail('')
      } catch (err) {
        setInviteError(
          err?.message
          || 'De eerder verstuurde uitnodiging kon niet worden ingetrokken. Samen blijft daarom geselecteerd.',
        )
        return
      } finally {
        setInviteSaving(false)
      }
    }

    setUsageMode(nextMode)
    if (nextMode !== 'together') setInviteMessage('')
  }

  async function sendInvitation(event) {
    event.preventDefault()
    if (!canInvite) return
    setInviteSaving(true)
    setInviteError('')
    setInviteMessage('')
    try {
      const payload = await createHouseholdInvitation({ email: normalizedInviteEmail })
      const invitation = payload?.invitation
      if (invitation?.id) {
        setOnboardingInvitations((current) => [
          ...current,
          { id: String(invitation.id), email: normalizedInviteEmail },
        ])
      }
      setInviteMessage(invitationMessage(normalizedInviteEmail, payload?.delivery))
    } catch (err) {
      setInviteError(err?.message || 'De uitnodiging kon niet worden aangemaakt.')
    } finally {
      setInviteSaving(false)
    }
  }

  function finish() {
    if (!canFinish) return
    onSubmit?.({
      household_name: String(householdName || '').trim(),
      household_usage_mode: usageMode,
    })
  }

  const invitedEmails = onboardingInvitations.map((item) => item.email)

  return (
    <div className="rz-form" data-testid="onboarding-shared-household-minimum">
      <div>
        <h1 style={{ marginTop: 0 }}>Nog even je huishouden</h1>
        <p>
          Rond je huishouden af. Kies je voor Samen, dan kun je hier meteen iemand per e-mail uitnodigen.
        </p>
      </div>

      <ChoiceSummary
        items={[
          { label: 'Startkeuze', value: primaryUseCaseTitle || 'Nog niet gekozen' },
          ...previousChoices,
          { label: 'Naam huishouden', value: String(householdName || '').trim() || 'Nog niet ingevuld' },
          { label: 'Gebruik huishouden', value: usageMode === 'together' ? 'Samen' : usageMode === 'alone' ? 'Alleen' : 'Nog niet gekozen' },
          ...(usageMode === 'together' ? [{
            label: 'Uitgenodigd',
            value: invitedEmails.length ? invitedEmails.join(', ') : normalizedInviteEmail || 'Nog niemand',
          }] : []),
        ]}
        title="Jouw volledige inrichting"
      />

      <Card>
        <div className="rz-form">
          <div>
            <h2 style={{ marginTop: 0 }}>Hoe heet je huishouden?</h2>
            <p style={{ marginBottom: 0 }}>
              Deze naam zie je terug bij je gedeelde huishoudcontext. Je kunt hem later wijzigen.
            </p>
          </div>
          <Input
            label="Naam huishouden"
            value={householdName}
            onChange={(event) => setHouseholdName(event.target.value)}
            disabled={saving || inviteSaving}
            required
            maxLength={120}
            placeholder="Bijvoorbeeld Familie Jansen"
            data-testid="shared-household-name"
          />
        </div>
      </Card>

      <Card>
        <div className="rz-form">
          <div>
            <h2 style={{ marginTop: 0 }}>Gebruik je Inhuis alleen of samen?</h2>
            <p style={{ marginBottom: 0 }}>
              Kies één optie. De geselecteerde radioknop laat direct zien wat actief is en je kunt vóór afronden altijd wisselen.
            </p>
          </div>
          <RadioChoices
            name="Gebruik je Inhuis alleen of samen"
            value={usageMode}
            onChange={changeUsageMode}
            disabled={saving || inviteSaving}
            testId="shared-household-usage"
            options={[
              { value: 'alone', label: 'Alleen', testId: 'shared-household-usage-alone' },
              { value: 'together', label: 'Samen', testId: 'shared-household-usage-together' },
            ]}
          />
          {usageMode === 'together' && onboardingInvitations.length ? (
            <small>
              Kies je alsnog Alleen, dan trekt Inhuis de uitnodiging(en) die je in deze stap hebt verstuurd eerst in.
            </small>
          ) : null}
        </div>
      </Card>

      {usageMode === 'together' ? (
        <Card>
          <form className="rz-form" onSubmit={sendInvitation} data-testid="shared-household-invite-now">
            <div>
              <h2 style={{ marginTop: 0 }}>Iemand uitnodigen</h2>
              <p style={{ marginBottom: 0 }}>
                Vul het e-mailadres in en verstuur de uitnodiging direct. De ontvanger accepteert via de bestaande beveiligde uitnodigingsflow.
              </p>
            </div>
            <Input
              label="E-mailadres"
              type="email"
              value={inviteEmail}
              onChange={(event) => {
                setInviteEmail(event.target.value)
                setInviteError('')
                setInviteMessage('')
              }}
              disabled={saving || inviteSaving}
              required
              placeholder="naam@voorbeeld.nl"
              data-testid="shared-household-invite-email"
            />
            <Button
              type="submit"
              variant="secondary"
              disabled={saving || !canInvite}
              data-testid="shared-household-invite-send"
            >
              {inviteSaving ? 'Bezig…' : 'Uitnodiging versturen'}
            </Button>
            {inviteMessage ? <div className="rz-inline-feedback" data-testid="shared-household-invite-success">{inviteMessage}</div> : null}
            {inviteError ? <div className="rz-alert" data-testid="shared-household-invite-error">{inviteError}</div> : null}
          </form>
        </Card>
      ) : null}

      <p style={{ marginBottom: 0 }}>
        <strong>Na afronden blijft je actieve inrichting zichtbaar bovenaan Instellingen.</strong>
      </p>

      <Button
        type="button"
        variant="primary"
        disabled={saving || !canFinish}
        onClick={finish}
        data-testid="shared-household-finish"
      >
        {saving ? 'Opslaan…' : 'Onboarding afronden'}
      </Button>

      {error ? <div className="rz-alert">{error}</div> : null}
    </div>
  )
}
