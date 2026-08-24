import React from 'react'
import { API_BASE_URL } from '../../lib/apiClient.js'
import Button from '../../ui/Button'
import Card from '../../ui/Card'
import Header from '../../ui/Header'

function formatDateTime(value) {
  if (!value) return 'Onbekend'
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return String(value)
  return new Intl.DateTimeFormat('nl-NL', {
    dateStyle: 'medium',
    timeStyle: 'short',
  }).format(date)
}

export default function PlatformSessionsPage() {
  const [sessions, setSessions] = React.useState([])
  const [loading, setLoading] = React.useState(true)
  const [error, setError] = React.useState('')
  const [pendingSession, setPendingSession] = React.useState(null)
  const [submitting, setSubmitting] = React.useState(false)
  const [result, setResult] = React.useState('')

  const loadSessions = React.useCallback(async () => {
    setLoading(true)
    setError('')
    try {
      const response = await fetch(`${API_BASE_URL}/api/platform/sessions`, {
        method: 'GET',
        credentials: 'include',
        headers: { Accept: 'application/json' },
      })
      if (!response.ok) {
        const payload = await response.json().catch(() => ({}))
        throw new Error(payload?.detail || `Sessies ophalen mislukt (${response.status})`)
      }
      const payload = await response.json()
      setSessions(Array.isArray(payload?.items) ? payload.items : [])
    } catch (err) {
      setError(err?.message || 'Sessies ophalen mislukt.')
    } finally {
      setLoading(false)
    }
  }, [])

  React.useEffect(() => {
    loadSessions()
  }, [loadSessions])

  async function confirmRevoke() {
    if (!pendingSession || submitting) return
    setSubmitting(true)
    setError('')
    setResult('')
    try {
      const response = await fetch(
        `${API_BASE_URL}/api/platform/sessions/${encodeURIComponent(pendingSession.session_id)}/revoke`,
        {
          method: 'POST',
          credentials: 'include',
          headers: { Accept: 'application/json' },
        },
      )
      if (!response.ok) {
        const payload = await response.json().catch(() => ({}))
        throw new Error(payload?.detail || `Sessie intrekken mislukt (${response.status})`)
      }
      const payload = await response.json()
      const revokedId = payload?.item?.session_id || pendingSession.session_id
      setSessions((current) => current.filter((item) => item.session_id !== revokedId))
      setResult(`Sessie van ${pendingSession.email} is ingetrokken.`)
      setPendingSession(null)
    } catch (err) {
      setError(err?.message || 'Sessie intrekken mislukt.')
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <div data-testid="platform-sessions-page">
      <Header title="Sessies" subtitle="Bekijk actieve serversessies en trek een andere sessie gericht in." />

      <Card>
        <p>
          Deze pagina gebruikt uitsluitend <strong>platform.sessions.revoke</strong>. Er is geen actief
          huishouden nodig en er is nooit een fallback naar huishouden 0.
        </p>
        <p>
          Sessietokens en token-hashes worden niet getoond. Je huidige beheersessie kan hier niet worden
          ingetrokken; gebruik daarvoor Uitloggen.
        </p>
      </Card>

      {error ? <Card><p role="alert">{error}</p></Card> : null}
      {result ? <Card><p role="status">{result}</p></Card> : null}
      {loading ? <Card><p>Actieve sessies laden...</p></Card> : null}

      {!loading && !sessions.length ? (
        <Card><p>Er zijn geen actieve sessies om te beheren.</p></Card>
      ) : null}

      {!loading && sessions.map((session) => (
        <Card key={session.session_id}>
          <div data-testid={`platform-session-${session.session_id}`}>
            <h3>{session.email}</h3>
            <p>Gebruiker-ID: {session.user_id}</p>
            <p>Uitgegeven: {formatDateTime(session.issued_at)}</p>
            <p>Verloopt: {formatDateTime(session.expires_at)}</p>
            <p>{session.is_current ? 'Huidige sessie' : 'Andere actieve sessie'}</p>
            {session.is_current ? (
              <p>Deze sessie blijft actief. Gebruik Uitloggen om je eigen sessie te beëindigen.</p>
            ) : (
              <Button type="button" onClick={() => {
                setPendingSession(session)
                setResult('')
              }}>
                Sessie intrekken
              </Button>
            )}
          </div>
        </Card>
      ))}

      {pendingSession ? (
        <Card>
          <div data-testid="platform-session-confirmation">
            <h3>Sessie definitief intrekken?</h3>
            <p>
              Je staat op het punt de actieve sessie van <strong>{pendingSession.email}</strong> in te trekken.
              Die sessie kan daarna geen volgende geauthenticeerde request meer uitvoeren.
            </p>
            <p>Sessie-ID: {pendingSession.session_id}</p>
            <div>
              <Button
                type="button"
                variant="secondary"
                disabled={submitting}
                onClick={() => setPendingSession(null)}
              >
                Annuleren
              </Button>
              <Button
                type="button"
                disabled={submitting}
                onClick={confirmRevoke}
              >
                {submitting ? 'Intrekken...' : 'Definitief intrekken'}
              </Button>
            </div>
          </div>
        </Card>
      ) : null}
    </div>
  )
}
