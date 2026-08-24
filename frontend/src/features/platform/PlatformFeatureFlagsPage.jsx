import React from 'react'
import { useNavigate } from 'react-router-dom'
import Header from '../../ui/Header.jsx'
import Card from '../../ui/Card.jsx'
import Button from '../../ui/Button.jsx'
import { API_BASE_URL } from '../../lib/apiClient.js'

const FEATURE_FLAGS_ENDPOINT = '/api/platform/feature-flags'

async function fetchPlatformFeatureFlags() {
  const response = await fetch(`${API_BASE_URL}${FEATURE_FLAGS_ENDPOINT}`, {
    method: 'GET',
    credentials: 'include',
    headers: { Accept: 'application/json' },
    cache: 'no-store',
  })
  const payload = await response.json().catch(() => ({}))
  if (!response.ok) {
    throw new Error(payload?.detail || `Featureflags ophalen is mislukt (${response.status}).`)
  }
  return payload
}

async function persistPlatformFeatureFlag(flagKey, enabled) {
  const response = await fetch(`${API_BASE_URL}${FEATURE_FLAGS_ENDPOINT}/${encodeURIComponent(flagKey)}`, {
    method: 'PUT',
    credentials: 'include',
    headers: {
      Accept: 'application/json',
      'Content-Type': 'application/json',
    },
    body: JSON.stringify({ enabled }),
  })
  const payload = await response.json().catch(() => ({}))
  if (!response.ok) {
    throw new Error(payload?.detail || `Featureflag wijzigen is mislukt (${response.status}).`)
  }
  return payload?.item
}

export default function PlatformFeatureFlagsPage() {
  const navigate = useNavigate()
  const [loading, setLoading] = React.useState(true)
  const [items, setItems] = React.useState([])
  const [error, setError] = React.useState('')
  const [pendingChange, setPendingChange] = React.useState(null)
  const [updating, setUpdating] = React.useState(false)

  React.useEffect(() => {
    let active = true
    setLoading(true)
    fetchPlatformFeatureFlags()
      .then((payload) => {
        if (!active) return
        setItems(Array.isArray(payload?.items) ? payload.items : [])
        setError('')
      })
      .catch((requestError) => {
        if (!active) return
        setItems([])
        setError(requestError?.message || 'Featureflags ophalen is mislukt.')
      })
      .finally(() => {
        if (active) setLoading(false)
      })
    return () => {
      active = false
    }
  }, [])

  const proposeChange = (item) => {
    if (updating) return
    setError('')
    setPendingChange({
      key: item.key,
      label: item.label || item.key,
      enabled: !Boolean(item.enabled),
    })
  }

  const confirmChange = async () => {
    if (!pendingChange || updating) return
    setUpdating(true)
    setError('')
    try {
      const updatedItem = await persistPlatformFeatureFlag(
        pendingChange.key,
        pendingChange.enabled,
      )
      setItems((currentItems) => currentItems.map((item) => (
        item.key === updatedItem?.key ? updatedItem : item
      )))
      setPendingChange(null)
    } catch (requestError) {
      setError(requestError?.message || 'Featureflag wijzigen is mislukt.')
    } finally {
      setUpdating(false)
    }
  }

  return (
    <div className="rz-screen" data-testid="platform-feature-flags-page">
      <Header title="Featureflags" />
      <div className="rz-content">
        <div className="rz-content-inner">
          <Card className="rz-card-home">
            <h2>Platformbrede featureflags</h2>
            <p>Featureflags bepalen beschikbaarheid van functionaliteit en verlenen nooit extra permissies.</p>
            <p>Er is geen actief huishouden en deze pagina valt nooit terug op huishouden 0.</p>
            <p>Een wijziging wordt pas opgeslagen na een expliciete tweede bevestiging.</p>

            {loading ? <p data-testid="platform-feature-flags-loading">Featureflags laden…</p> : null}
            {error ? <p role="alert">{error}</p> : null}
            {!loading && !error && items.length === 0 ? (
              <p data-testid="platform-feature-flags-empty">Geen featureflags geregistreerd.</p>
            ) : null}

            {!loading ? items.map((item) => (
              <div key={item.key} data-testid={`platform-feature-flag-${item.key}`}>
                <Card className="rz-card-home">
                  <h3>{item.label || item.key}</h3>
                  <p>{item.description}</p>
                  <p>Status: <strong>{item.enabled ? 'Ingeschakeld' : 'Uitgeschakeld'}</strong></p>
                  <p>Standaard: {item.default_enabled ? 'ingeschakeld' : 'uitgeschakeld'}</p>
                  <p>Bron: {item.source === 'override' ? 'opgeslagen platforminstelling' : 'veilige standaardwaarde'}</p>
                  <Button
                    type="button"
                    variant={item.enabled ? 'danger' : 'primary'}
                    disabled={updating || Boolean(pendingChange)}
                    onClick={() => proposeChange(item)}
                  >
                    {item.enabled ? 'Uitschakelen' : 'Inschakelen'}
                  </Button>
                </Card>
              </div>
            )) : null}

            {pendingChange ? (
              <Card className="rz-card-home">
                <div data-testid="platform-feature-flag-confirmation">
                  <h3>Wijziging bevestigen</h3>
                  <p>
                    {pendingChange.label} wordt platformbreed{' '}
                    <strong>{pendingChange.enabled ? 'ingeschakeld' : 'uitgeschakeld'}</strong>.
                  </p>
                  <p>Bestaande gebruikerspermissies veranderen hierdoor niet.</p>
                  <Button
                    type="button"
                    variant={pendingChange.enabled ? 'primary' : 'danger'}
                    disabled={updating}
                    onClick={confirmChange}
                  >
                    {updating ? 'Opslaan…' : 'Definitief bevestigen'}
                  </Button>
                  <Button
                    type="button"
                    variant="secondary"
                    disabled={updating}
                    onClick={() => setPendingChange(null)}
                  >
                    Annuleren
                  </Button>
                </div>
              </Card>
            ) : null}

            <Button type="button" variant="secondary" onClick={() => navigate('/home')} disabled={updating}>
              Terug naar platformbeheer
            </Button>
          </Card>
        </div>
      </div>
    </div>
  )
}
