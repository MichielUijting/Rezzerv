import React from 'react'
import Header from '../../ui/Header.jsx'
import Card from '../../ui/Card.jsx'
import Button from '../../ui/Button.jsx'
import { API_BASE_URL } from '../../lib/apiClient.js'


const LOG_LIMIT = 100
const FALLBACK_LEVELS = ['DEBUG', 'INFO', 'WARNING', 'ERROR', 'CRITICAL']

function displayValue(value, fallback = '—') {
  if (value === null || value === undefined || value === '') return fallback
  return String(value)
}

function buildLogsEndpoint(level) {
  const params = new URLSearchParams({ limit: String(LOG_LIMIT) })
  if (level) params.set('level', level)
  return `/api/platform/logs?${params.toString()}`
}

async function fetchPlatformLogs(level, signal) {
  const response = await fetch(`${API_BASE_URL}${buildLogsEndpoint(level)}`, {
    method: 'GET',
    credentials: 'include',
    headers: { Accept: 'application/json' },
    cache: 'no-store',
    signal,
  })
  if (!response.ok) {
    throw new Error(`Platformlogs konden niet worden geladen (${response.status}).`)
  }
  return response.json()
}

export default function PlatformLogsPage() {
  const [items, setItems] = React.useState([])
  const [levels, setLevels] = React.useState(FALLBACK_LEVELS)
  const [level, setLevel] = React.useState('')
  const [retention, setRetention] = React.useState('runtime_memory')
  const [maxEntries, setMaxEntries] = React.useState(500)
  const [loading, setLoading] = React.useState(true)
  const [error, setError] = React.useState('')
  const [reloadKey, setReloadKey] = React.useState(0)

  React.useEffect(() => {
    const controller = new AbortController()
    let active = true

    async function loadLogs() {
      setLoading(true)
      setError('')
      try {
        const payload = await fetchPlatformLogs(level, controller.signal)
        if (!active) return
        setItems(Array.isArray(payload?.items) ? payload.items : [])
        setLevels(Array.isArray(payload?.levels) && payload.levels.length ? payload.levels : FALLBACK_LEVELS)
        setRetention(payload?.retention || 'runtime_memory')
        setMaxEntries(Number(payload?.max_entries) || 500)
      } catch (err) {
        if (active && err?.name !== 'AbortError') {
          setItems([])
          setError(err?.message || 'Platformlogs konden niet worden geladen.')
        }
      } finally {
        if (active) setLoading(false)
      }
    }

    loadLogs()
    return () => {
      active = false
      controller.abort()
    }
  }, [level, reloadKey])

  return (
    <div className="rz-screen" data-testid="platform-logs-page">
      <Header title="Logs" />
      <div className="rz-content">
        <div className="rz-content-inner">
          <Card className="rz-card-home">
            <h2>Platformlogs</h2>
            <p>Bekijk recente operationele runtime-logrecords uit de Rezzerv-backend.</p>
            <p>
              Deze weergave is read-only en staat los van Audit. Audit registreert platformhandelingen;
              Logs toont technische runtimegebeurtenissen.
            </p>
            <p data-testid="platform-logs-retention">
              Retentie: {retention === 'runtime_memory' ? `alleen huidige backendruntime, maximaal ${maxEntries} records` : retention}.
              Een backendrestart wist deze buffer.
            </p>
            <p>
              Tracebacks, requestbodies en headers worden niet opgeslagen in deze projectie; bekende credentialvormen
              worden voor opname gemaskeerd.
            </p>

            <label htmlFor="platform-logs-level">Logniveau</label>
            <select
              id="platform-logs-level"
              data-testid="platform-logs-level"
              value={level}
              onChange={(event) => setLevel(event.target.value)}
            >
              <option value="">Alle niveaus</option>
              {levels.map((candidate) => (
                <option key={candidate} value={candidate}>{candidate}</option>
              ))}
            </select>

            {loading ? <p data-testid="platform-logs-loading">Logs laden…</p> : null}
            {error ? <p role="alert" data-testid="platform-logs-error">{error}</p> : null}

            {!loading && !error && items.length === 0 ? (
              <p data-testid="platform-logs-empty">Er zijn voor deze runtime geen passende logrecords beschikbaar.</p>
            ) : null}

            {!loading && !error && items.length > 0 ? (
              <div data-testid="platform-logs-items">
                {items.map((item) => (
                  <div key={item.id} data-testid={`platform-log-item-${item.id}`}>
                    <Card className="rz-card-home">
                      <h3>{displayValue(item.level, 'INFO')} — {displayValue(item.logger, 'rezzerv')}</h3>
                      <p>{displayValue(item.message, 'Geen bericht')}</p>
                      <p>Tijdstip: {displayValue(item.created_at)}</p>
                      {item.exception_type ? <p>Exceptiontype: {displayValue(item.exception_type)}</p> : null}
                    </Card>
                  </div>
                ))}
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
