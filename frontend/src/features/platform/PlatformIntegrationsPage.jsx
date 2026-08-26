import React from 'react'
import Header from '../../ui/Header.jsx'
import Card from '../../ui/Card.jsx'
import Button from '../../ui/Button.jsx'
import { API_BASE_URL } from '../../lib/apiClient.js'

const INTEGRATIONS_ENDPOINT = '/api/platform/integrations'

const STATUS_LABELS = {
  ready: 'Gereed',
  disabled: 'Uitgeschakeld',
  incomplete: 'Onvolledig geconfigureerd',
  configuration_error: 'Configuratiefout',
}

async function fetchPlatformIntegrations() {
  const response = await fetch(`${API_BASE_URL}${INTEGRATIONS_ENDPOINT}`, {
    method: 'GET',
    credentials: 'include',
    headers: {
      Accept: 'application/json',
    },
    cache: 'no-store',
  })
  const payload = await response.json().catch(() => ({}))
  if (!response.ok) {
    throw new Error(payload?.detail || `Integratiestatus ophalen is mislukt (${response.status}).`)
  }
  return payload
}

function statusLabel(status) {
  return STATUS_LABELS[status] || status || 'Onbekend'
}

export default function PlatformIntegrationsPage() {
  const [loading, setLoading] = React.useState(true)
  const [refreshing, setRefreshing] = React.useState(false)
  const [items, setItems] = React.useState([])
  const [error, setError] = React.useState('')

  const load = React.useCallback(async ({ refresh = false } = {}) => {
    if (refresh) {
      setRefreshing(true)
    } else {
      setLoading(true)
    }
    setError('')
    try {
      const payload = await fetchPlatformIntegrations()
      setItems(Array.isArray(payload?.items) ? payload.items : [])
    } catch (requestError) {
      setItems([])
      setError(requestError?.message || 'Integratiestatus ophalen is mislukt.')
    } finally {
      setLoading(false)
      setRefreshing(false)
    }
  }, [])

  React.useEffect(() => {
    load()
  }, [load])

  return (
    <div className="rz-screen" data-testid="platform-integrations-page">
      <Header title="Integraties" />
      <div className="rz-content">
        <div className="rz-content-inner">
          <Card className="rz-card-home">
            <h2>Platformintegraties</h2>
            <p>Toont uitsluitend een veilige, alleen-lezen status van platformbrede integraties.</p>
            <p>Er is geen actief huishouden en deze pagina valt nooit terug op huishouden 0.</p>
            <p>Huishoudgebonden Gmail-koppelingen en externe-productkoppelingen met eigen platformpermissies vallen bewust buiten deze pagina.</p>

            <Button
              type="button"
              variant="secondary"
              onClick={() => load({ refresh: true })}
              disabled={loading || refreshing}
            >
              {refreshing ? 'Vernieuwen…' : 'Status vernieuwen'}
            </Button>

            {loading ? <p data-testid="platform-integrations-loading">Integratiestatus laden…</p> : null}
            {error ? <p role="alert">{error}</p> : null}
            {!loading && !error && items.length === 0 ? (
              <p data-testid="platform-integrations-empty">Geen platformintegraties beschikbaar.</p>
            ) : null}

            {!loading && !error ? items.map((item) => (
              <div key={item.key} data-testid={`platform-integration-${item.key}`}>
                <Card className="rz-card-home">
                  <h3>{item.label || item.key}</h3>
                  <p>Status: {statusLabel(item.status)}</p>
                  <p>Provider: {item.provider || 'Niet beschikbaar'}</p>

                  {item.key === 'receipt-scanner' ? (
                    <>
                      <p>Contractversie: {item.contract_version || 'Onbekend'}</p>
                      <p>Beschikbare providers: {(item.available_providers || []).join(', ') || 'Geen'}</p>
                    </>
                  ) : null}

                  {item.key === 'outbound-email' ? (
                    <>
                      <p>Verzending ingeschakeld: {item.delivery_enabled ? 'ja' : 'nee'}</p>
                      <p>API-sleutel geconfigureerd: {item.api_key_configured ? 'ja' : 'nee'}</p>
                      <p>Afzender geconfigureerd: {item.sender_configured ? 'ja' : 'nee'}</p>
                    </>
                  ) : null}
                </Card>
              </div>
            )) : null}
          </Card>
        </div>
      </div>
    </div>
  )
}
