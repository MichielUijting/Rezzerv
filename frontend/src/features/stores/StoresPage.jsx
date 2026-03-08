import { useEffect, useMemo, useState } from 'react'
import AppShell from '../../app/AppShell'
import Card from '../../ui/Card'
import Button from '../../ui/Button'

async function fetchJson(url, options = {}) {
  const response = await fetch(url, {
    headers: {
      'Content-Type': 'application/json',
      ...(options.headers || {}),
    },
    ...options,
  })

  const text = await response.text()
  const data = text ? JSON.parse(text) : null

  if (!response.ok) {
    throw new Error(data?.detail || 'Verzoek mislukt')
  }

  return data
}

export default function StoresPage() {
  const [household, setHousehold] = useState(null)
  const [providers, setProviders] = useState([])
  const [connections, setConnections] = useState([])
  const [activeBatch, setActiveBatch] = useState(null)
  const [status, setStatus] = useState('')
  const [error, setError] = useState('')
  const [isLoading, setIsLoading] = useState(true)
  const [isConnecting, setIsConnecting] = useState(false)
  const [isPulling, setIsPulling] = useState(false)

  const lidlProvider = useMemo(
    () => providers.find((provider) => provider.code === 'lidl') || null,
    [providers],
  )

  const lidlConnection = useMemo(
    () => connections.find((connection) => connection.store_provider_code === 'lidl') || null,
    [connections],
  )

  async function loadPageData() {
    setIsLoading(true)
    setError('')
    try {
      const token = localStorage.getItem('rezzerv_token')
      const householdData = await fetchJson('/api/household', {
        headers: token ? { Authorization: `Bearer ${token}` } : {},
      })
      setHousehold(householdData)

      const [providerData, connectionData] = await Promise.all([
        fetchJson('/api/store-providers'),
        fetchJson(`/api/store-connections?householdId=${encodeURIComponent(householdData.id)}`),
      ])

      setProviders(providerData)
      setConnections(connectionData)
    } catch (err) {
      setError(err.message || 'Winkelgegevens konden niet worden geladen.')
    } finally {
      setIsLoading(false)
    }
  }

  useEffect(() => {
    loadPageData()
  }, [])

  async function handleConnect() {
    if (!household) return
    setIsConnecting(true)
    setError('')
    setStatus('')
    try {
      const connection = await fetchJson('/api/store-connections', {
        method: 'POST',
        body: JSON.stringify({ household_id: household.id, store_provider_code: 'lidl' }),
      })
      setConnections((current) => {
        const filtered = current.filter((item) => item.id !== connection.id)
        return [...filtered, connection]
      })
      setStatus('Lidl is gekoppeld aan dit huishouden.')
    } catch (err) {
      setError(err.message || 'Lidl kon niet worden gekoppeld.')
    } finally {
      setIsConnecting(false)
    }
  }

  async function handlePullPurchases() {
    if (!lidlConnection) return
    setIsPulling(true)
    setError('')
    setStatus('')
    try {
      const pullResult = await fetchJson(`/api/store-connections/${lidlConnection.id}/pull-purchases`, {
        method: 'POST',
        body: JSON.stringify({ mock_profile: 'default' }),
      })
      const batch = await fetchJson(`/api/purchase-import-batches/${pullResult.batch_id}`)
      setActiveBatch(batch)
      setStatus('Mock aankopen zijn opgehaald. Deze regels zijn nog niet verwerkt naar voorraad.')
      const refreshedConnections = await fetchJson(`/api/store-connections?householdId=${encodeURIComponent(household.id)}`)
      setConnections(refreshedConnections)
    } catch (err) {
      setError(err.message || 'Aankopen konden niet worden opgehaald.')
    } finally {
      setIsPulling(false)
    }
  }

  return (
    <AppShell title="Winkels" showExit={false}>
      <div style={{ display: 'grid', gap: '18px' }}>
        <Card>
          <div style={{ display: 'grid', gap: '10px' }}>
            <div>
              <h2 style={{ margin: '0 0 8px 0', fontSize: '20px' }}>Winkelkoppelingen</h2>
              <p style={{ margin: 0, color: '#667085' }}>
                Koppel hier winkels en haal voorbeeld-aankopen op. In deze release gaat het om een rudimentaire Lidl-pilot.
              </p>
            </div>
            {household && (
              <div style={{ color: '#344054', fontSize: '14px' }}>
                Huishouden: <strong>{household.naam}</strong>
              </div>
            )}
          </div>
        </Card>

        {error && (
          <Card>
            <div style={{ color: '#b42318', fontWeight: 700 }}>{error}</div>
          </Card>
        )}

        {status && (
          <Card>
            <div style={{ color: '#0f5132', fontWeight: 700 }}>{status}</div>
          </Card>
        )}

        <Card>
          {isLoading ? (
            <div>Winkelgegevens laden…</div>
          ) : (
            <div style={{ display: 'grid', gap: '16px' }}>
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', gap: '16px', flexWrap: 'wrap' }}>
                <div>
                  <div style={{ fontWeight: 700, fontSize: '18px' }}>Lidl</div>
                  <div style={{ color: '#667085', fontSize: '14px' }}>
                    Status provider: {lidlProvider ? `${lidlProvider.status} / ${lidlProvider.import_mode}` : 'niet beschikbaar'}
                  </div>
                  <div style={{ color: '#667085', fontSize: '14px' }}>
                    Koppeling: {lidlConnection ? 'gekoppeld' : 'nog niet gekoppeld'}
                  </div>
                </div>
                <div style={{ display: 'flex', gap: '12px', flexWrap: 'wrap' }}>
                  {!lidlConnection ? (
                    <Button variant="primary" onClick={handleConnect} disabled={isConnecting || !lidlProvider}>
                      {isConnecting ? 'Koppelen…' : 'Lidl koppelen'}
                    </Button>
                  ) : (
                    <Button variant="secondary" onClick={handlePullPurchases} disabled={isPulling}>
                      {isPulling ? 'Ophalen…' : 'Aankopen ophalen'}
                    </Button>
                  )}
                </div>
              </div>

              <div style={{ borderTop: '1px solid #e4e7ec', paddingTop: '14px', color: '#667085', fontSize: '14px' }}>
                Deze pilot maakt alleen een importbatch met regels aan. Voorraad wordt nog niet bijgewerkt.
              </div>
            </div>
          )}
        </Card>

        {activeBatch && (
          <Card>
            <div style={{ display: 'grid', gap: '12px' }}>
              <div>
                <h3 style={{ margin: '0 0 6px 0', fontSize: '18px' }}>Laatste opgehaalde aankopen</h3>
                <div style={{ color: '#667085', fontSize: '14px' }}>
                  Batch: {activeBatch.batch_id} · Bron: {activeBatch.store_provider_code} · Status: {activeBatch.import_status}
                </div>
              </div>

              <div style={{ overflowX: 'auto' }}>
                <table style={{ width: '100%', borderCollapse: 'collapse' }}>
                  <thead>
                    <tr>
                      <th style={tableHeadStyle}>Artikel</th>
                      <th style={tableHeadStyle}>Merk</th>
                      <th style={tableHeadStyle}>Aantal</th>
                      <th style={tableHeadStyle}>Prijs</th>
                    </tr>
                  </thead>
                  <tbody>
                    {activeBatch.lines.map((line) => (
                      <tr key={line.id}>
                        <td style={tableCellStyle}>{line.article_name_raw}</td>
                        <td style={tableCellStyle}>{line.brand_raw || '—'}</td>
                        <td style={tableCellStyle}>{line.quantity_raw} {line.unit_raw || ''}</td>
                        <td style={tableCellStyle}>{line.line_price_raw != null ? `€ ${line.line_price_raw.toFixed(2)}` : '—'}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          </Card>
        )}
      </div>
    </AppShell>
  )
}

const tableHeadStyle = {
  textAlign: 'left',
  padding: '10px 8px',
  borderBottom: '1px solid #d0d5dd',
  fontSize: '14px',
}

const tableCellStyle = {
  padding: '10px 8px',
  borderBottom: '1px solid #eaecf0',
  fontSize: '14px',
}
