import React from 'react'
import { useNavigate } from 'react-router-dom'
import Header from '../../ui/Header.jsx'
import Card from '../../ui/Card.jsx'
import Button from '../../ui/Button.jsx'
import { API_BASE_URL } from '../../lib/apiClient.js'


const AUDIT_ENDPOINT = '/api/platform/audit?limit=50'

function displayValue(value, fallback = '—') {
  if (value === null || value === undefined || value === '') return fallback
  return String(value)
}

async function fetchPlatformAudit(signal) {
  const response = await fetch(`${API_BASE_URL}${AUDIT_ENDPOINT}`, {
    method: 'GET',
    credentials: 'include',
    headers: { Accept: 'application/json' },
    cache: 'no-store',
    signal,
  })
  if (!response.ok) {
    throw new Error(`Audit kon niet worden geladen (${response.status}).`)
  }
  return response.json()
}

export default function PlatformAuditPage() {
  const navigate = useNavigate()
  const [items, setItems] = React.useState([])
  const [loading, setLoading] = React.useState(true)
  const [error, setError] = React.useState('')
  const [reloadKey, setReloadKey] = React.useState(0)

  React.useEffect(() => {
    const controller = new AbortController()
    let active = true

    async function loadAudit() {
      setLoading(true)
      setError('')
      try {
        const payload = await fetchPlatformAudit(controller.signal)
        if (active) setItems(Array.isArray(payload?.items) ? payload.items : [])
      } catch (err) {
        if (active && err?.name !== 'AbortError') {
          setItems([])
          setError(err?.message || 'Audit kon niet worden geladen.')
        }
      } finally {
        if (active) setLoading(false)
      }
    }

    loadAudit()
    return () => {
      active = false
      controller.abort()
    }
  }, [reloadKey])

  return (
    <div className="rz-screen" data-testid="platform-audit-page">
      <Header title="Audit" />
      <div className="rz-content">
        <div className="rz-content-inner">
          <Card className="rz-card-home">
            <h2>Autorisatie-audit</h2>
            <p>Bekijk recente autorisatiegebeurtenissen van het platform.</p>
            <p>Gevoelige auditpayloads, redenen en ticketreferenties worden hier niet getoond.</p>

            {loading ? <p data-testid="platform-audit-loading">Audit laden…</p> : null}
            {error ? <p role="alert" data-testid="platform-audit-error">{error}</p> : null}

            {!loading && !error && items.length === 0 ? (
              <p data-testid="platform-audit-empty">Er zijn geen auditgebeurtenissen beschikbaar.</p>
            ) : null}

            {!loading && !error && items.length > 0 ? (
              <div data-testid="platform-audit-items">
                {items.map((item) => (
                  <div key={item.id} data-testid={`platform-audit-item-${item.id}`}>
                    <Card className="rz-card-home">
                      <h3>{displayValue(item.action, 'Onbekende actie')}</h3>
                      <p>Actor: {displayValue(item.actor_user_id)} ({displayValue(item.actor_type, 'onbekend')})</p>
                      <p>
                        Object: {displayValue(item.object_type)} / {displayValue(item.object_id)}
                      </p>
                      <p>
                        Context: {item.household_id ? `Huishouden ${item.household_id}` : 'Platformbreed'}
                      </p>
                      <p>Tijdstip: {displayValue(item.created_at)}</p>
                    </Card>
                  </div>
                ))}
              </div>
            ) : null}

            <div>
              <Button type="button" variant="secondary" onClick={() => setReloadKey((value) => value + 1)}>
                Vernieuwen
              </Button>
              <Button type="button" variant="secondary" onClick={() => navigate('/home')}>
                Terug naar platformbeheer
              </Button>
            </div>
          </Card>
        </div>
      </div>
    </div>
  )
}
