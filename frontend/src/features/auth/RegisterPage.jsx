import { useState } from 'react'
import { Link } from 'react-router-dom'
import Header from '../../ui/Header.jsx'
import Card from '../../ui/Card.jsx'
import Input from '../../ui/Input.jsx'
import Button from '../../ui/Button.jsx'
import { apiPost } from '../../lib/apiClient.js'
import { fetchAuthContext } from '../../lib/authSession.js'
import useDismissOnComponentClick from '../../lib/useDismissOnComponentClick.js'

export default function RegisterPage({ onRegistered }) {
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [passwordRepeat, setPasswordRepeat] = useState('')
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')

  useDismissOnComponentClick([() => setError('')], Boolean(error))

  async function onSubmit(event) {
    event.preventDefault()
    setError('')
    if (password !== passwordRepeat) {
      setError('De wachtwoorden zijn niet gelijk.')
      return
    }
    if (password.length < 10) {
      setError('Gebruik een wachtwoord van minimaal 10 tekens.')
      return
    }

    setLoading(true)
    try {
      const response = await apiPost('/api/auth/register', { email, password })
      const data = await response.json().catch(() => ({}))
      if (!response.ok) throw new Error(data?.detail || 'Account aanmaken mislukt')
      await fetchAuthContext({ force: true })
      onRegistered()
    } catch (err) {
      setError(err?.message || 'Account aanmaken mislukt')
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
            <form className="rz-form" onSubmit={onSubmit}>
              <p style={{ marginTop: 0 }}>
                Maak je account aan. Inhuis maakt daarbij automatisch een eigen huishouden aan.
              </p>
              <Input
                label="E-mail"
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
                label="Herhaal wachtwoord"
                type="password"
                value={passwordRepeat}
                onChange={(event) => setPasswordRepeat(event.target.value)}
                autoComplete="new-password"
                required
                data-testid="register-password-repeat"
              />

              <Button type="submit" variant="primary" disabled={loading} className="rz-btn-center" data-testid="register-submit">
                {loading ? 'Bezig...' : 'Account maken'}
              </Button>

              <div style={{ textAlign: 'center' }}>
                <Link to="/login">Al een account? Inloggen</Link>
              </div>

              {error ? <div className="rz-alert">{error}</div> : null}
            </form>
          </Card>
        </div>
      </div>
    </div>
  )
}
