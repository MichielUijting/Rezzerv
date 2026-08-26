import React from 'react'
import Header from '../../ui/Header.jsx'
import Card from '../../ui/Card.jsx'
import Button from '../../ui/Button.jsx'
import { API_BASE_URL } from '../../lib/apiClient.js'

const DIAGNOSTIC_CHECKS = Object.freeze([
  {
    key: 'regression',
    label: 'Kassa regressie',
    endpoint: '/api/admin/kassa-regression/status',
  },
  {
    key: 'smoke',
    label: 'Kassa smoke-check',
    endpoint: '/api/admin/kassa-smoke/status',
  },
])

function displayValue(value, fallback = '—') {
  if (value === null || value === undefined || value === '') return fallback
  return String(value)
}

async function fetchDiagnosticStatus(endpoint, signal) {
  const response = await fetch(`${API_BASE_URL}${endpoint}`, {
    method: 'GET',
    credentials: 'include',
    headers: { Accept: 'application/json' },
    cache: 'no-store',
    signal,
  })
  if (!response.ok) {
    throw new Error(`Diagnostiek kon niet worden geladen (${response.status}).`)
  }
  return response.json()
}

export default function PlatformDiagnosticsPage() {
  const [statuses, setStatuses] = React.useState({})
  const [loading, setLoading] = React.useState(true)
  const [error, setError] = React.useState('')
  const [reloadKey, setReloadKey] = React.useState(0)

  React.useEffect(() => {
    const controller = new AbortController()
    let active = true

    async function loadStatuses() {
      setLoading(true)
      setError('')
      try {
        const results = await Promise.all(
          DIAGNOSTIC_CHECKS.map(async (check) => [
            check.key,
            await fetchDiagnosticStatus(check.endpoint, controller.signal),
          ]),
        )
        if (active) setStatuses(Object.fromEntries(results))
      } catch (err) {
        if (active && err?.name !== 'AbortError') {
          setStatuses({})
          setError(err?.message || 'Diagnostiek kon niet worden geladen.')
        }
      } finally {
        if (active) setLoading(false)
      }
    }

    loadStatuses()
    return () => {
      active = false
      controller.abort()
    }
  }, [reloadKey])

  return (
    <div className="rz-screen" data-testid="platform-diagnostics-page">
      <Header title="Diagnostiek" />
      <div className="rz-content">
        <div className="rz-content-inner">
          <Card className="rz-card-home">
            <h2>Platformdiagnostiek</h2>
            <p>Bekijk de actuele status van read-only platformcontroles.</p>
            <p>Het starten van controles hoort bij Achtergrondtaken en is hier niet beschikbaar.</p>

            {loading ? <p data-testid="platform-diagnostics-loading">Diagnostiek laden…</p> : null}
            {error ? <p role="alert" data-testid="platform-diagnostics-error">{error}</p> : null}

            {!loading && !error ? (
              <div data-testid="platform-diagnostics-statuses">
                {DIAGNOSTIC_CHECKS.map((check) => {
                  const status = statuses[check.key] || {}
                  return (
                    <div key={check.key} data-testid={`platform-diagnostic-${check.key}`}>
                      <Card className="rz-card-home">
                        <h3>{check.label}</h3>
                        <p>Status: <strong>{displayValue(status.status, 'onbekend')}</strong></p>
                        <p>{displayValue(status.message, 'Geen statusmelding.')}</p>
                        <p>
                          Voortgang: {displayValue(status.progress_current, '0')} / {displayValue(status.progress_total, '0')}
                        </p>
                        <p>Laatst afgerond: {displayValue(status.finished_at)}</p>
                      </Card>
                    </div>
                  )
                })}
              </div>
            ) : null}

            <div>
              <Button type="button" variant="secondary" onClick={() => setReloadKey((value) => value + 1)}>
                Vernieuwen
              </Button>
            </div>
          </Card>
        </div>
      </div>
    </div>
  )
}
