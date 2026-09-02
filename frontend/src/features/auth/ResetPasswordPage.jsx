import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import Header from '../../ui/Header.jsx'
import Card from '../../ui/Card.jsx'
import Input from '../../ui/Input.jsx'
import Button from '../../ui/Button.jsx'
import { apiPost } from '../../lib/apiClient.js'

function readResetTokenFromFragment() {
  const fragment = String(window.location.hash || '').replace(/^#/, '')
  return new URLSearchParams(fragment).get('token') || ''
}

export default function ResetPasswordPage() {
  const [token] = useState(() => readResetTokenFromFragment())
  const [password, setPassword] = useState('')
  const [passwordRepeat, setPasswordRepeat] = useState('')
  const [showPassword, setShowPassword] = useState(false)
  const [loading, setLoading] = useState(false)
  const [success, setSuccess] = useState('')
  const [error, setError] = useState('')

  useEffect(() => {
    if (!token) return
    const cleanUrl = `${window.location.pathname}${window.location.search}`
    window.history.replaceState(null, '', cleanUrl)
  }, [token])

  async function onSubmit(event) {
    event.preventDefault()
    setError('')
    setSuccess('')

    if (!token) {
      setError('Deze herstellink is ongeldig of onvolledig. Vraag een nieuwe herstellink aan.')
      return
    }
    if (password !== passwordRepeat) {
      setError('De wachtwoorden zijn niet gelijk.')
      return
    }
    if (password.length < 10) {
      setError('Gebruik een wachtwoord van minimaal 10 tekens.')
      return
    }
    if (password.length > 256) {
      setError('Wachtwoord mag maximaal 256 tekens bevatten.')
      return
    }

    setLoading(true)
    try {
      const response = await apiPost('/api/auth/password-reset/confirm', {
        token,
        new_password: password,
      })
      const data = await response.json().catch(() => ({}))
      if (!response.ok) throw new Error(data?.detail || 'Wachtwoord herstellen mislukt.')
      setPassword('')
      setPasswordRepeat('')
      setSuccess(data?.message || 'Wachtwoord gewijzigd. Log opnieuw in met je nieuwe wachtwoord.')
    } catch (err) {
      setError(err?.message || 'Wachtwoord herstellen mislukt.')
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="rz-screen" data-testid="reset-password-page">
      <Header title="Nieuw wachtwoord instellen" />
      <div className="rz-content">
        <div className="rz-content-inner">
          <Card className="rz-card-login">
            {success ? (
              <div className="rz-form">
                <div className="rz-inline-feedback rz-inline-feedback--success" data-testid="reset-password-success">{success}</div>
                <div style={{ textAlign: 'center' }}>
                  <Link to="/login" data-testid="reset-password-login">Inloggen met nieuw wachtwoord</Link>
                </div>
              </div>
            ) : (
              <form className="rz-form" onSubmit={onSubmit}>
                <p style={{ marginTop: 0 }}>Kies een nieuw wachtwoord van minimaal 10 tekens.</p>
                <Input
                  label="Nieuw wachtwoord"
                  type={showPassword ? 'text' : 'password'}
                  value={password}
                  onChange={(event) => setPassword(event.target.value)}
                  autoComplete="new-password"
                  required
                  data-testid="reset-password-new"
                />
                <Input
                  label="Herhaal nieuw wachtwoord"
                  type={showPassword ? 'text' : 'password'}
                  value={passwordRepeat}
                  onChange={(event) => setPasswordRepeat(event.target.value)}
                  autoComplete="new-password"
                  required
                  data-testid="reset-password-repeat"
                />
                <label style={{ display: 'flex', alignItems: 'center', gap: 8, cursor: 'pointer' }}>
                  <input
                    type="checkbox"
                    checked={showPassword}
                    onChange={(event) => setShowPassword(event.target.checked)}
                    data-testid="reset-password-show"
                  />
                  <span>Wachtwoord tonen</span>
                </label>
                <Button
                  type="submit"
                  variant="primary"
                  disabled={loading || !token}
                  className="rz-btn-center"
                  data-testid="reset-password-submit"
                >
                  {loading ? 'Bezig...' : 'Wachtwoord opslaan'}
                </Button>
                {!token ? (
                  <div className="rz-alert" data-testid="reset-password-missing-token">
                    Deze herstellink is ongeldig of onvolledig. Vraag een nieuwe herstellink aan.
                  </div>
                ) : null}
                {error ? <div className="rz-alert" data-testid="reset-password-error">{error}</div> : null}
                <div style={{ textAlign: 'center' }}>
                  <Link to="/wachtwoord-vergeten" data-testid="reset-password-request-new">Nieuwe herstellink aanvragen</Link>
                </div>
              </form>
            )}
          </Card>
        </div>
      </div>
    </div>
  )
}
