import React, { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import Header from '../../ui/Header.jsx'
import Card from '../../ui/Card.jsx'
import Button from '../../ui/Button.jsx'
import { apiPost } from '../../lib/apiClient.js'
import { fetchAuthContext, getLoginMessage } from '../../lib/authSession.js'
import useDismissOnComponentClick from '../../lib/useDismissOnComponentClick.js'
import { formatInhuisVersionLabel, getRezzervVersionTag } from '../../ui/version.js'
import './loginPage.css'

function MailIcon() {
  return (
    <svg viewBox="0 0 24 24" aria-hidden="true">
      <rect x="3" y="5" width="18" height="14" rx="2" />
      <path d="m4 7 8 6 8-6" />
    </svg>
  )
}

function LockIcon() {
  return (
    <svg viewBox="0 0 24 24" aria-hidden="true">
      <rect x="5" y="10" width="14" height="11" rx="2" />
      <path d="M8 10V7a4 4 0 0 1 8 0v3" />
      <path d="M12 14v3" />
    </svg>
  )
}

function EyeIcon({ visible }) {
  return (
    <svg viewBox="0 0 24 24" aria-hidden="true">
      <path d="M2.5 12s3.5-6 9.5-6 9.5 6 9.5 6-3.5 6-9.5 6-9.5-6-9.5-6Z" />
      <circle cx="12" cy="12" r="2.5" />
      {!visible ? <path d="M4 4 20 20" /> : null}
    </svg>
  )
}

export default function LoginPage({ onLoggedIn }) {
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [showPassword, setShowPassword] = useState(false)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')
  const [loginMessage] = useState(() => getLoginMessage())
  const [version, setVersion] = useState(getRezzervVersionTag())
  const [loginBackground, setLoginBackground] = useState(null)

  useDismissOnComponentClick([() => setError('')], Boolean(error))

  useEffect(() => {
    let active = true
    const refreshBackground = async () => {
      try {
        const response = await fetch('/api/platform/login-background', { credentials: 'same-origin' })
        const payload = await response.json().catch(() => ({}))
        if (active) setLoginBackground(payload?.configured && payload?.revision ? payload : null)
      } catch {
        if (active) setLoginBackground(null)
      }
    }
    void refreshBackground()
    const backgroundChanged = (event) => {
      const payload = event?.detail
      setLoginBackground(payload?.configured && payload?.revision ? payload : null)
    }
    window.addEventListener('inhuis-login-background-changed', backgroundChanged)
    return () => { active = false; window.removeEventListener('inhuis-login-background-changed', backgroundChanged) }
  }, [])

  useEffect(() => {
    const refreshVersion = () => setVersion(getRezzervVersionTag())
    window.addEventListener('rezzerv-version-ready', refreshVersion)
    return () => window.removeEventListener('rezzerv-version-ready', refreshVersion)
  }, [])

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
    <div className="rz-screen rz-login-screen" data-testid="login-page">
      <div className="rz-login-desktop-header">
        <Header title="Inloggen" />
      </div>

      <div
        className={loginBackground ? 'rz-login-background rz-login-background--custom' : 'rz-login-background'}
        style={loginBackground ? { backgroundImage: `url("/api/platform/login-background/image?v=${encodeURIComponent(loginBackground.revision)}")` } : undefined}
        aria-hidden="true"
      >
        <span className="rz-login-wave rz-login-wave-one" />
        <span className="rz-login-wave rz-login-wave-two" />
        <span className="rz-login-leaves">
          <i /><i /><i /><i /><i />
        </span>
      </div>

      <main className="rz-login-layout">
        <div className="rz-login-brand" aria-label="InHuis" data-testid="login-wordmark">
          <span className="rz-login-wordmark-in" aria-hidden="true">In</span>
          <span className="rz-login-wordmark-huis" aria-hidden="true">Huis</span>
        </div>

        <h1 className="rz-login-welcome" data-rz-text-size="title">Welkom</h1>

        <Card className="rz-card-login">
          <form className="rz-form rz-login-form" onSubmit={onSubmit}>
            <label className="rz-login-field">
              <span className="rz-login-field-label">E-mailadres</span>
              <span className="rz-login-input-shell">
                <span className="rz-login-field-icon"><MailIcon /></span>
                <input
                  className="rz-login-input"
                  value={email}
                  onChange={(e) => setEmail(e.target.value)}
                  placeholder="naam@voorbeeld.nl"
                  autoComplete="email"
                  inputMode="email"
                  data-testid="login-email"
                />
              </span>
            </label>

            <label className="rz-login-field">
              <span className="rz-login-field-label">Wachtwoord</span>
              <span className="rz-login-input-shell">
                <span className="rz-login-field-icon"><LockIcon /></span>
                <input
                  className="rz-login-input"
                  type={showPassword ? 'text' : 'password'}
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  placeholder="Je wachtwoord"
                  autoComplete="current-password"
                  data-testid="login-password"
                />
                <button
                  type="button"
                  className="rz-login-password-toggle"
                  onClick={() => setShowPassword((value) => !value)}
                  aria-label={showPassword ? 'Wachtwoord verbergen' : 'Wachtwoord tonen'}
                  data-testid="login-show-password"
                >
                  <EyeIcon visible={showPassword} />
                </button>
              </span>
            </label>

            <div className="rz-login-forgot">
              <Link to="/wachtwoord-vergeten" data-testid="forgot-password-link">Wachtwoord vergeten?</Link>
            </div>

            <Button type="submit" variant="primary" disabled={loading} className="rz-login-submit" data-testid="login-submit">
              <span>{loading ? 'Bezig...' : 'Inloggen'}</span>
              {!loading ? <span className="rz-login-submit-arrow" aria-hidden="true">→</span> : null}
            </Button>

            <div className="rz-login-register">
              <span>Nog geen account?</span>{' '}
              <Link to="/registreren" data-testid="register-link">Account maken</Link>
            </div>

            {loginMessage && !error ? <div className="rz-inline-feedback rz-inline-feedback--warning">{loginMessage}</div> : null}
            {error && <div className="rz-alert">{error}</div>}
          </form>
        </Card>
      </main>

      <div className="rz-buildtag" aria-hidden="true" data-testid="build-tag">{formatInhuisVersionLabel(version)}</div>
    </div>
  )
}
