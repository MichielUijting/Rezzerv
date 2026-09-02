import { useState } from 'react'
import { Link } from 'react-router-dom'
import Header from '../../ui/Header.jsx'
import Card from '../../ui/Card.jsx'
import Input from '../../ui/Input.jsx'
import Button from '../../ui/Button.jsx'
import { apiPost } from '../../lib/apiClient.js'
import useDismissOnComponentClick from '../../lib/useDismissOnComponentClick.js'

export default function ForgotPasswordPage() {
  const [email, setEmail] = useState('')
  const [loading, setLoading] = useState(false)
  const [message, setMessage] = useState('')
  const [error, setError] = useState('')

  useDismissOnComponentClick([() => setError('')], Boolean(error))

  async function onSubmit(event) {
    event.preventDefault()
    setError('')
    setMessage('')
    setLoading(true)
    try {
      const response = await apiPost('/api/auth/password-reset/request', { email })
      const data = await response.json().catch(() => ({}))
      if (!response.ok) throw new Error(data?.detail || 'Herstelverzoek kon niet worden verwerkt')
      setMessage(data?.message || 'Als dit e-mailadres bij ons bekend is, ontvang je een herstellink.')
    } catch (err) {
      setError(err?.message || 'Herstelverzoek kon niet worden verwerkt')
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="rz-screen" data-testid="forgot-password-page">
      <Header title="Wachtwoord vergeten" />
      <div className="rz-content">
        <div className="rz-content-inner">
          <Card className="rz-card-login">
            <form className="rz-form" onSubmit={onSubmit}>
              <p style={{ marginTop: 0 }}>
                Vul het e-mailadres van je Inhuis-account in. Als het adres bij ons bekend is, sturen we een eenmalige herstellink.
              </p>
              <Input
                label="E-mail"
                type="email"
                value={email}
                onChange={(event) => setEmail(event.target.value)}
                autoComplete="email"
                required
                data-testid="forgot-password-email"
              />
              <Button
                type="submit"
                variant="primary"
                disabled={loading}
                className="rz-btn-center"
                data-testid="forgot-password-submit"
              >
                {loading ? 'Bezig...' : 'Herstellink versturen'}
              </Button>
              <div style={{ textAlign: 'center' }}>
                <Link to="/login">Terug naar inloggen</Link>
              </div>
              {message ? <div className="rz-alert" data-testid="forgot-password-message">{message}</div> : null}
              {error ? <div className="rz-alert" data-testid="forgot-password-error">{error}</div> : null}
            </form>
          </Card>
        </div>
      </div>
    </div>
  )
}
