import React from 'react'
import { Link } from 'react-router-dom'
import Header from '../../ui/Header.jsx'
import Card from '../../ui/Card.jsx'
import Input from '../../ui/Input.jsx'
import Button from '../../ui/Button.jsx'
import { apiPost } from '../../lib/apiClient.js'
import { useState } from 'react'
import { fetchAuthContext, getLoginMessage } from '../../lib/authSession.js'
import useDismissOnComponentClick from '../../lib/useDismissOnComponentClick.js'

export default function LoginPage({ onLoggedIn }) {
  const [email, setEmail] = useState('admin@rezzerv.local')
  const [password, setPassword] = useState('Rezzerv123')
  const [showPassword, setShowPassword] = useState(false)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')
  const [loginMessage] = useState(() => getLoginMessage())

  useDismissOnComponentClick([() => setError('')], Boolean(error))

  async function onSubmit(e) {
    e.preventDefault()
    setError('')
    setLoading(true)
    try {
      const res = await apiPost('/api/auth/login', { email, password })
      const data = await res.json().catch(() => ({}))
      if (!res.ok) throw new Error(data?.detail || 'Inloggen mislukt')
      await fetchAuthContext({ force: true })
      onLoggedIn()
    } catch (err) {
      setError(err.message)
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="rz-screen" data-testid="login-page">
      <Header title="Inloggen" />
      <div className="rz-content">
        <div className="rz-content-inner">
          <Card className="rz-card-login">
            <form className="rz-form" onSubmit={onSubmit}>
              <Input
                label="E-mail"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                placeholder="admin@rezzerv.local"
                data-testid="login-email"
              />
              <Input
                label="Wachtwoord"
                type={showPassword ? 'text' : 'password'}
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                placeholder="Rezzerv123"
                data-testid="login-password"
              />

              <label style={{ display: 'flex', alignItems: 'center', gap: 8, cursor: 'pointer' }}>
                <input
                  type="checkbox"
                  checked={showPassword}
                  onChange={(event) => setShowPassword(event.target.checked)}
                  data-testid="login-show-password"
                />
                <span>Wachtwoord tonen</span>
              </label>

              <div style={{ textAlign: 'center' }}>
                <Link to="/wachtwoord-vergeten" data-testid="forgot-password-link">Wachtwoord vergeten?</Link>
              </div>

              <Button type="submit" variant="primary" disabled={loading} className="rz-btn-center" data-testid="login-submit">
                {loading ? 'Bezig...' : 'Inloggen'}
              </Button>

              <div style={{ textAlign: 'center' }}>
                <Link to="/registreren" data-testid="register-link">Nog geen account? Account maken</Link>
              </div>

              {loginMessage && !error ? <div className="rz-inline-feedback rz-inline-feedback--warning">{loginMessage}</div> : null}
              {error && <div className="rz-alert">{error}</div>}
            </form>
          </Card>
        </div>
      </div>
    </div>
  )
}
