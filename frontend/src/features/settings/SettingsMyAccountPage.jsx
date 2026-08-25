import { useState } from 'react'
import { Link } from 'react-router-dom'
import AppShell from '../../app/AppShell'
import Card from '../../ui/Card'
import Button from '../../ui/Button'
import Input from '../../ui/Input'
import { apiPost } from '../../lib/apiClient.js'
import { readStoredAuthContext } from '../../lib/authSession.js'

export default function SettingsMyAccountPage() {
  const context = readStoredAuthContext()
  const [currentPassword, setCurrentPassword] = useState('')
  const [newPassword, setNewPassword] = useState('')
  const [newPasswordRepeat, setNewPasswordRepeat] = useState('')
  const [isSaving, setIsSaving] = useState(false)
  const [message, setMessage] = useState('')
  const [error, setError] = useState('')

  function clearFeedback() {
    setMessage('')
    setError('')
  }

  function updatePasswordField(setValue, value) {
    clearFeedback()
    setValue(value)
  }

  async function handleSubmit(event) {
    event.preventDefault()
    clearFeedback()

    if (newPassword !== newPasswordRepeat) {
      setError('De nieuwe wachtwoorden zijn niet gelijk.')
      return
    }
    if (newPassword.length < 10) {
      setError('Gebruik een nieuw wachtwoord van minimaal 10 tekens.')
      return
    }
    if (currentPassword === newPassword) {
      setError('Nieuw wachtwoord moet verschillen van het huidige wachtwoord.')
      return
    }

    setIsSaving(true)
    try {
      const response = await apiPost('/api/account/password', {
        current_password: currentPassword,
        new_password: newPassword,
      })
      const payload = await response.json().catch(() => ({}))
      if (!response.ok) {
        throw new Error(payload?.detail || 'Wachtwoord wijzigen mislukt.')
      }
      setCurrentPassword('')
      setNewPassword('')
      setNewPasswordRepeat('')
      setMessage(payload?.message || 'Wachtwoord gewijzigd.')
    } catch (saveError) {
      setError(saveError?.message || 'Wachtwoord wijzigen mislukt.')
    } finally {
      setIsSaving(false)
    }
  }

  return (
    <AppShell title="Instellingen" showExit={false}>
      <Card>
        <div style={{ display: 'grid', gap: '20px' }} data-testid="settings-my-account-page">
          <div style={{ display: 'flex', justifyContent: 'space-between', gap: '16px', flexWrap: 'wrap' }}>
            <div>
              <h2 style={{ margin: '0 0 8px 0', fontSize: '20px' }}>Mijn account</h2>
              <p style={{ margin: 0, color: '#667085' }}>Bekijk je inlogadres en beheer je wachtwoord.</p>
            </div>
            <Link to="/instellingen" style={{ textDecoration: 'none', fontWeight: 600 }}>← Terug naar instellingen</Link>
          </div>

          <section style={{ display: 'grid', gap: '12px' }} aria-labelledby="account-identity-title">
            <div>
              <h3 id="account-identity-title" style={{ margin: '0 0 4px 0', fontSize: '17px' }}>Accountgegevens</h3>
              <p style={{ margin: 0, color: '#667085', fontSize: '14px' }}>Dit is het e-mailadres waarmee je bij Inhuis inlogt.</p>
            </div>
            <Input
              label="E-mailadres"
              type="email"
              value={context?.email || ''}
              readOnly
              aria-readonly="true"
              data-testid="my-account-email"
            />
          </section>

          <section style={{ display: 'grid', gap: '12px' }} aria-labelledby="account-password-title">
            <div>
              <h3 id="account-password-title" style={{ margin: '0 0 4px 0', fontSize: '17px' }}>Wachtwoord wijzigen</h3>
              <p style={{ margin: 0, color: '#667085', fontSize: '14px' }}>
                Na een succesvolle wijziging blijf je op dit apparaat ingelogd. Andere actieve sessies worden ingetrokken.
              </p>
            </div>

            {(message || error) ? (
              <div
                className={error ? 'rz-inline-feedback rz-inline-feedback--error' : 'rz-inline-feedback rz-inline-feedback--success'}
                role="status"
                data-testid={error ? 'my-account-error' : 'my-account-success'}
              >
                {error || message}
              </div>
            ) : null}

            <form onSubmit={handleSubmit} style={{ display: 'grid', gap: '12px' }} data-testid="my-account-password-form">
              <Input
                label="Huidig wachtwoord"
                type="password"
                value={currentPassword}
                onChange={(event) => updatePasswordField(setCurrentPassword, event.target.value)}
                autoComplete="current-password"
                required
                disabled={isSaving}
                data-testid="my-account-current-password"
              />
              <Input
                label="Nieuw wachtwoord"
                type="password"
                value={newPassword}
                onChange={(event) => updatePasswordField(setNewPassword, event.target.value)}
                autoComplete="new-password"
                minLength={10}
                required
                disabled={isSaving}
                data-testid="my-account-new-password"
              />
              <Input
                label="Herhaal nieuw wachtwoord"
                type="password"
                value={newPasswordRepeat}
                onChange={(event) => updatePasswordField(setNewPasswordRepeat, event.target.value)}
                autoComplete="new-password"
                minLength={10}
                required
                disabled={isSaving}
                data-testid="my-account-new-password-repeat"
              />
              <div style={{ display: 'flex', justifyContent: 'flex-end' }}>
                <Button type="submit" disabled={isSaving} data-testid="my-account-password-submit">
                  {isSaving ? 'Wijzigen…' : 'Wachtwoord wijzigen'}
                </Button>
              </div>
            </form>
          </section>
        </div>
      </Card>
    </AppShell>
  )
}
