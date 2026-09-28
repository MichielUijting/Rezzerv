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
        aria-hidden="true"
      >
        {loginBackground ? (
          <img
            className="rz-login-background-image"
            src={`/api/platform/login-background/image?v=${encodeURIComponent(loginBackground.revision)}`}
            alt=""
            aria-hidden="true"
          />
        ) : null}
        <svg className="rz-login-interior-sketch" viewBox="0 0 900 1200" preserveAspectRatio="xMidYMid slice" focusable="false">
          <defs>
            <filter id="inhuis-sketch-rough">
              <feTurbulence type="fractalNoise" baseFrequency="0.012 0.028" numOctaves="3" seed="17" result="noise" />
              <feDisplacementMap in="SourceGraphic" in2="noise" scale="18" />
            </filter>
            <filter id="inhuis-sketch-wash">
              <feTurbulence type="fractalNoise" baseFrequency="0.025" numOctaves="4" seed="9" result="wash" />
              <feBlend in="SourceGraphic" in2="wash" mode="soft-light" />
              <feGaussianBlur stdDeviation="1.4" />
            </filter>
          </defs>
          <g className="rz-login-sketch-wash" filter="url(#inhuis-sketch-wash)">
            <path d="M0 690 C170 610 315 650 450 710 S735 795 900 705 L900 1200 L0 1200 Z" />
            <path d="M0 880 C190 760 355 820 515 875 S760 960 900 905 L900 1200 L0 1200 Z" />
          </g>
          <g className="rz-login-sketch-room" filter="url(#inhuis-sketch-rough)">
            <path d="M78 850 L78 470 L330 355 L610 470 L610 850" />
            <path d="M330 355 L330 850" />
            <path d="M610 470 L808 390 L808 850" />
            <path d="M128 812 L128 612 L280 612 L280 812" />
            <path d="M390 812 L390 570 L548 570 L548 812" />
            <path d="M650 812 L650 560 L760 520 L760 812" />
            <path d="M90 850 L805 850" />
          </g>
          <g className="rz-login-sketch-furniture" filter="url(#inhuis-sketch-rough)">
            <path d="M120 792 L185 720 L330 720 L370 790" />
            <path d="M150 790 L150 842 M340 790 L340 842" />
            <path d="M420 770 L485 710 L610 738 L650 800" />
            <path d="M470 810 L470 855 M625 805 L625 855" />
            <path d="M685 790 C710 710 755 675 805 670 M735 735 C710 690 695 655 700 610 M765 710 C805 665 825 625 830 585" />
          </g>
          <g className="rz-login-sketch-scribbles">
            <path d="M40 1010 C180 920 270 960 395 1015 S665 1100 880 985" />
            <path d="M25 1060 C210 965 350 1020 480 1065 S735 1140 900 1040" />
          </g>
        </svg>
      </div>

      <main className="rz-login-layout">
        <div className="rz-login-brand" aria-label="InHuis" data-testid="login-wordmark">
          <span className="rz-login-wordmark-in" aria-hidden="true">In</span>
          <span className="rz-login-wordmark-huis" aria-hidden="true">Huis</span>
        </div>

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
