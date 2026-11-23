import { useState } from 'react'
import { Link } from 'react-router-dom'
import Header from '../../ui/Header.jsx'
import Card from '../../ui/Card.jsx'
import Input from '../../ui/Input.jsx'
import Button from '../../ui/Button.jsx'
import { apiPost } from '../../lib/apiClient.js'
import { fetchAuthContext } from '../../lib/authSession.js'
import { useAppFeedback } from '../../ui/AppFeedbackProvider.jsx'

export default function RegisterPage({ onRegistered }) {
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [householdName, setHouseholdName] = useState('Mijn huishouden')
  const [loading, setLoading] = useState(false)
  const { showFeedback } = useAppFeedback()

  async function onSubmit(event) {
    event.preventDefault()
    if (password.length < 10) {
      showFeedback({ variant: 'error', message: 'Gebruik een wachtwoord van minimaal 10 tekens.' })
      return
    }
    if (!householdName.trim()) {
      showFeedback({ variant: 'error', message: 'Vul een huishoudnaam in.' })
      return
    }

    setLoading(true)
    try {
      // One atomic registration request: account, household, Wat Inhuis/quantity,
      // Alleen and receipt setup are committed before the session is issued.
      const response = await apiPost('/api/auth/register', {
        email,
        password,
        household_name: householdName.trim(),
        quick_start: true,
      })
      const data = await response.json().catch(() => ({}))
      if (!response.ok) throw new Error(data?.detail || 'Account aanmaken mislukt')
      await fetchAuthContext({ force: true })
      onRegistered?.(data?.onboarding)
    } catch (err) {
      showFeedback({ variant: 'error', message: err?.message || 'Account aanmaken mislukt' })
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="rz-screen" data-testid="register-page">
      <Header title="Account maken" />
      <div className="rz-content">
        <div className="rz-content-inner">
          <Card className="rz-card-login">
            <form className="rz-form" onSubmit={onSubmit} data-testid="quick-start-registration">
              <h1 style={{ margin: 0 }}>Welkom bij Inhuis</h1>
              <Input
                label="E-mailadres"
                type="email"
                value={email}
                onChange={(event) => setEmail(event.target.value)}
                autoComplete="email"
                required
                data-testid="register-email"
              />
              <Input
                label="Wachtwoord"
                type="password"
                value={password}
                onChange={(event) => setPassword(event.target.value)}
                autoComplete="new-password"
                required
                data-testid="register-password"
              />
              <Input
                label="Huishouden"
                value={householdName}
                onChange={(event) => setHouseholdName(event.target.value)}
                maxLength={120}
                required
                data-testid="register-household-name"
              />
              <p style={{ margin: 0 }} data-testid="register-quick-start-defaults">
                Standaard: Wat Inhuis · Aantallen · Alleen.
              </p>
              <Button type="submit" variant="primary" disabled={loading} className="rz-btn-center" data-testid="register-submit">
                {loading ? 'Bezig…' : 'Start Inhuis'}
              </Button>
              <div style={{ textAlign: 'center' }}>
                <Link to="/login">Al een account? Inloggen</Link>
              </div>
            </form>
          </Card>
        </div>
      </div>
    </div>
  )
}
