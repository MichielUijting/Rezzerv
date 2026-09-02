import { useEffect, useRef, useState } from 'react'
import { Link } from 'react-router-dom'
import Header from '../../ui/Header.jsx'
import Card from '../../ui/Card.jsx'
import Input from '../../ui/Input.jsx'
import Button from '../../ui/Button.jsx'
import { apiPost } from '../../lib/apiClient.js'
import useDismissOnComponentClick from '../../lib/useDismissOnComponentClick.js'

export default function ResetPasswordPage() {
  const processedHashRef = useRef(false)
  const [token, setToken] = useState('')
  const [password, setPassword] = useState('')
  const [passwordRepeat, setPasswordRepeat] = useState('')
  const [loading, setLoading] = useState(false)
  const [completed, setCompleted] = useState(false)
  const [message, setMessage] = useState('')
  const [error, setError] = useState('')

  useDismissOnComponentClick([() => setError('')], Boolean(error) && Boolean(token))

  useEffect(() => {
    if (processedHashRef.current) return
    processedHashRef.current = true

    const params = new URLSearchParams(window.location.hash.replace(/^#/, ''))
    const rawToken = params.get('token') || ''
    if (rawToken) {
      setToken(rawToken)
    } else {
      setError('Deze herstellink is ongeldig of onvolledig.')
    }

    // Remove the secret from the visible URL immediately. It remains only in component memory.
    window.history.replaceState(
      window.history.state,
      document.title,
      `${window.location.pathname}${window.location.search}`,
    )
  }, [])

  async function onSubmit(event) {
    event.preventDefault()
    setError('')
    setMessage('')

    if (!token) {
      setError('Deze herstellink is ongeldig of onvolledig.')
      return
    }
    if (password.length < 10) {
      setError('Gebruik een wachtwoord van minimaal 10 tekens.')
      return
    }
    if (password.length > 256) {
      setError('Gebruik een wachtwoord van maximaal 256 tekens.')
      return
    }
    if (password !== passwordRepeat) {
      setError('De wachtwoorden zijn niet gelijk.')
      return
    }

    setLoading(true)
    try {
      const response = await apiPost('/api/auth/password-reset/confirm', {
        token,
        new_password: password,
      })
      const data = await response.json().catch(() => ({}))
      if (!response.ok) throw new Error(data?.detail || 'Wachtwoord herstellen mislukt')
      setToken('')
      setPassword('')
      setPasswordRepeat('')
      setCompleted(true)
      setMessage(data?.message || 'Je wachtwoord is gewijzigd. Log opnieuw in.')
    } catch (err) {
      setError(err?.message || 'Wachtwoord herstellen mislukt')
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="rz-screen" data-testid="reset-password-page">
      <Header title="Nieuw wachtwoord" />
      <div className="rz-content">
        <div className="rz-content-inner">
          <Card className="rz-card-login">
            {completed ? (
              <div className="rz-form">
                <div className="rz-alert" data-testid="reset-password-success">{message}</div>
                <div style={{ textAlign: 'center' }}>
                  <Link to="/login" data-testid="reset-password-login-link">Opnieuw inloggen</Link>
                </div>
              </div>
            ) : (
              <form className="rz-form" onSubmit={onSubmit}>
                <p style={{ marginTop: 0 }}>
                  Kies een nieuw wachtwoord van minimaal 10 tekens. Na deze wijziging worden alle bestaande sessies beëindigd.
                </p>
                <Input
                  label="Nieuw wachtwoord"
                  type="password"
                  value={password}
                  onChange={(event) => setPassword(event.target.value)}
                  autoComplete="new-password"
                  required
                  disabled={!token || loading}
                  data-testid="reset-password-new"
                />
                <Input
                  label="Herhaal nieuw wachtwoord"
                  type="password"
                  value={passwordRepeat}
                  onChange={(event) => setPasswordRepeat(event.target.value)}
                  autoComplete="new-password"
                  required
                  disabled={!token || loading}
                  data-testid="reset-password-repeat"
                />
                <Button
                  type="submit"
                  variant="primary"
                  disabled={!token || loading}
                  className="rz-btn-center"
                  data-testid="reset-password-submit"
                >
                  {loading ? 'Bezig...' : 'Wachtwoord opslaan'}
                </Button>
                {error ? <div className="rz-alert" data-testid="reset-password-error">{error}</div> : null}
              </form>
            )}
          </Card>
        </div>
      </div>
    </div>
  )
}
