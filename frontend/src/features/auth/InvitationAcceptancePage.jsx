import { useEffect, useMemo, useState } from 'react'
import { Link, useNavigate, useParams } from 'react-router-dom'
import Header from '../../ui/Header.jsx'
import Card from '../../ui/Card.jsx'
import Input from '../../ui/Input.jsx'
import Button from '../../ui/Button.jsx'
import { apiPost } from '../../lib/apiClient.js'
import { clearAuthSession, fetchAuthContext } from '../../lib/authSession.js'

function detailMessage(data, fallback) {
  if (typeof data?.detail === 'string' && data.detail.trim()) return data.detail
  return fallback
}

export default function InvitationAcceptancePage() {
  const { token = '' } = useParams()
  const navigate = useNavigate()
  const encodedToken = useMemo(() => encodeURIComponent(token), [token])
  const [preview, setPreview] = useState(null)
  const [mode, setMode] = useState('login')
  const [loading, setLoading] = useState(true)
  const [submitting, setSubmitting] = useState(false)
  const [error, setError] = useState('')
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [passwordRepeat, setPasswordRepeat] = useState('')

  useEffect(() => {
    let cancelled = false
    async function load() {
      setLoading(true)
      setError('')
      try {
        const response = await fetch(`/api/household/invitations/accept/${encodedToken}`, {
          method: 'GET', credentials: 'include', headers: { Accept: 'application/json' }, cache: 'no-store',
        })
        const data = await response.json().catch(() => ({}))
        if (!response.ok) throw new Error(detailMessage(data, 'Deze uitnodiging is niet geldig.'))
        if (!cancelled) {
          setPreview(data)
          setMode(data?.account_exists ? 'login' : 'register')
        }
      } catch (err) {
        if (!cancelled) setError(err?.message || 'Deze uitnodiging is niet geldig.')
      } finally {
        if (!cancelled) setLoading(false)
      }
    }
    if (token) load()
    else {
      setError('Uitnodigingstoken ontbreekt.')
      setLoading(false)
    }
    return () => { cancelled = true }
  }, [encodedToken, token])

  async function finishAcceptance() {
    await fetchAuthContext({ force: true })
    navigate('/home', { replace: true })
  }

  async function acceptCurrentSession() {
    setSubmitting(true)
    setError('')
    try {
      const response = await apiPost(`/api/household/invitations/accept/${encodedToken}`, {})
      const data = await response.json().catch(() => ({}))
      if (!response.ok) throw new Error(detailMessage(data, 'Uitnodiging accepteren mislukt.'))
      await finishAcceptance()
    } catch (err) {
      setError(err?.message || 'Uitnodiging accepteren mislukt.')
    } finally {
      setSubmitting(false)
    }
  }

  async function useAnotherAccount() {
    setSubmitting(true)
    setError('')
    try {
      await apiPost('/api/auth/logout', {})
    } catch {
      // Clearing local session state is safe even when the server session is already absent.
    } finally {
      clearAuthSession()
      setPreview((current) => current ? {
        ...current,
        authenticated: false,
        authenticated_email_matches: false,
      } : current)
      setMode(preview?.account_exists ? 'login' : 'register')
      setEmail('')
      setPassword('')
      setPasswordRepeat('')
      setSubmitting(false)
    }
  }

  async function loginAndAccept(event) {
    event.preventDefault()
    setSubmitting(true)
    setError('')
    try {
      const loginResponse = await apiPost('/api/auth/login', { email, password })
      const loginData = await loginResponse.json().catch(() => ({}))
      if (!loginResponse.ok) throw new Error(detailMessage(loginData, 'Inloggen mislukt.'))
      const acceptResponse = await apiPost(`/api/household/invitations/accept/${encodedToken}`, {})
      const acceptData = await acceptResponse.json().catch(() => ({}))
      if (!acceptResponse.ok) throw new Error(detailMessage(acceptData, 'Uitnodiging accepteren mislukt.'))
      await finishAcceptance()
    } catch (err) {
      setError(err?.message || 'Uitnodiging accepteren mislukt.')
    } finally {
      setSubmitting(false)
    }
  }

  async function registerAndAccept(event) {
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
    setSubmitting(true)
    try {
      const response = await apiPost(`/api/household/invitations/accept/${encodedToken}/register`, { email, password })
      const data = await response.json().catch(() => ({}))
      if (!response.ok) throw new Error(detailMessage(data, 'Account aanmaken en uitnodiging accepteren mislukt.'))
      await finishAcceptance()
    } catch (err) {
      setError(err?.message || 'Account aanmaken en uitnodiging accepteren mislukt.')
    } finally {
      setSubmitting(false)
    }
  }

  const authenticatedCorrectAccount = Boolean(preview?.authenticated && preview?.authenticated_email_matches)
  const authenticatedWrongAccount = Boolean(preview?.authenticated && !preview?.authenticated_email_matches)

  return (
    <div className="rz-screen" data-testid="invitation-acceptance-page">
      <Header title="Uitnodiging" />
      <div className="rz-content">
        <div className="rz-content-inner">
          <Card className="rz-card-login">
            {loading ? <p data-testid="invitation-loading">Uitnodiging controleren...</p> : null}
            {!loading && preview ? (
              <>
                <h2 style={{ marginTop: 0 }}>Je bent uitgenodigd</h2>
                <p>
                  Je bent uitgenodigd voor <strong>{preview.household_name}</strong> als Lid.
                  De uitnodiging is gericht aan <strong>{preview.invitee_email_masked}</strong>.
                </p>

                {authenticatedCorrectAccount ? (
                  <div className="rz-form" data-testid="invitation-authenticated-actions">
                    <p>Je bent ingelogd met het account waarvoor deze uitnodiging is bedoeld.</p>
                    <Button type="button" variant="primary" disabled={submitting} onClick={acceptCurrentSession} data-testid="invitation-accept-current">
                      {submitting ? 'Bezig...' : 'Uitnodiging accepteren'}
                    </Button>
                  </div>
                ) : authenticatedWrongAccount ? (
                  <div className="rz-form" data-testid="invitation-wrong-account-actions">
                    <p>Je bent ingelogd met een ander account. Gebruik het account dat hoort bij {preview.invitee_email_masked}.</p>
                    <Button type="button" variant="primary" disabled={submitting} onClick={useAnotherAccount} data-testid="invitation-use-another-account">
                      {submitting ? 'Bezig...' : 'Ander account gebruiken'}
                    </Button>
                  </div>
                ) : (
                  <>
                    <div style={{ display: 'flex', gap: 8, marginBottom: 16 }}>
                      <Button type="button" variant={mode === 'login' ? 'primary' : 'secondary'} onClick={() => { setMode('login'); setError('') }} data-testid="invitation-mode-login">
                        Ik heb al een account
                      </Button>
                      <Button type="button" variant={mode === 'register' ? 'primary' : 'secondary'} onClick={() => { setMode('register'); setError('') }} data-testid="invitation-mode-register">
                        Account maken
                      </Button>
                    </div>

                    {mode === 'login' ? (
                      <form className="rz-form" onSubmit={loginAndAccept} data-testid="invitation-login-form">
                        <Input label="E-mail" type="email" value={email} onChange={(e) => setEmail(e.target.value)} required data-testid="invitation-login-email" />
                        <Input label="Wachtwoord" type="password" value={password} onChange={(e) => setPassword(e.target.value)} required data-testid="invitation-login-password" />
                        <Button type="submit" variant="primary" disabled={submitting} data-testid="invitation-login-submit">
                          {submitting ? 'Bezig...' : 'Inloggen en accepteren'}
                        </Button>
                      </form>
                    ) : (
                      <form className="rz-form" onSubmit={registerAndAccept} data-testid="invitation-register-form">
                        <p style={{ marginTop: 0 }}>
                          Dit account wordt direct lid van het uitgenodigde huishouden; er wordt geen extra leeg huishouden aangemaakt.
                        </p>
                        <Input label="E-mail" type="email" value={email} onChange={(e) => setEmail(e.target.value)} required data-testid="invitation-register-email" />
                        <Input label="Wachtwoord" type="password" value={password} onChange={(e) => setPassword(e.target.value)} required data-testid="invitation-register-password" />
                        <Input label="Herhaal wachtwoord" type="password" value={passwordRepeat} onChange={(e) => setPasswordRepeat(e.target.value)} required data-testid="invitation-register-password-repeat" />
                        <Button type="submit" variant="primary" disabled={submitting} data-testid="invitation-register-submit">
                          {submitting ? 'Bezig...' : 'Account maken en accepteren'}
                        </Button>
                      </form>
                    )}
                  </>
                )}
              </>
            ) : null}

            {error ? <div className="rz-alert" data-testid="invitation-error">{error}</div> : null}
            {!preview && !loading ? <div style={{ marginTop: 16 }}><Link to="/login">Naar inloggen</Link></div> : null}
          </Card>
        </div>
      </div>
    </div>
  )
}
