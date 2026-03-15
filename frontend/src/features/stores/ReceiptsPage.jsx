import { useEffect, useMemo, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import AppShell from '../../app/AppShell'
import Card from '../../ui/Card'
import Button from '../../ui/Button'
import {
  batchStatusLabel,
  deriveBatchUiState,
  fetchJson,
  normalizeErrorMessage,
  providerLabel,
} from './storeImportShared'

async function getLatestBatchMeta(connectionId) {
  try {
    const latest = await fetchJson(`/api/store-connections/${connectionId}/latest-batch`)
    return latest?.batch_id ? latest : null
  } catch {
    return null
  }
}

function batchRowSubline(item) {
  const summary = item?.summary || {}
  const klaar = Number(summary.ready || item.uiState?.readyCount || 0)
  const actie = Number(summary.open || item.uiState?.openCount || 0)
  const verwerkt = Number(summary.processed || 0)
  if (verwerkt > 0 && actie === 0 && klaar === 0) return 'Volledig verwerkt'
  if (actie > 0 || klaar > 0) return `${klaar} klaar · ${actie} actie nodig`
  return 'Nog niet beoordeeld'
}

export default function ReceiptsPage() {
  const navigate = useNavigate()
  const [household, setHousehold] = useState(null)
  const [providers, setProviders] = useState([])
  const [connections, setConnections] = useState([])
  const [batches, setBatches] = useState([])
  const [searchValue, setSearchValue] = useState('')
  const [statusFilter, setStatusFilter] = useState('all')
  const [isLoading, setIsLoading] = useState(true)
  const [error, setError] = useState('')

  const providersByCode = useMemo(
    () => Object.fromEntries(providers.map((provider) => [provider.code, provider])),
    [providers],
  )

  useEffect(() => {
    let cancelled = false

    async function loadData() {
      setIsLoading(true)
      setError('')
      try {
        const token = localStorage.getItem('rezzerv_token')
        const householdData = await fetchJson('/api/household', {
          headers: token ? { Authorization: `Bearer ${token}` } : {},
        })
        if (cancelled) return
        setHousehold(householdData)

        const [providerData, connectionData] = await Promise.all([
          fetchJson('/api/store-providers'),
          fetchJson(`/api/store-connections?householdId=${encodeURIComponent(householdData.id)}`),
        ])
        if (cancelled) return
        setProviders(providerData || [])
        setConnections(connectionData || [])

        const latestCandidates = (await Promise.all((connectionData || []).map((connection) => getLatestBatchMeta(connection.id))))
          .filter((item) => item?.batch_id)

        const loadedBatches = (await Promise.all(
          latestCandidates.map((item) => fetchJson(`/api/purchase-import-batches/${item.batch_id}`).catch(() => null)),
        )).filter(Boolean)

        if (cancelled) return
        setBatches(loadedBatches)
      } catch (err) {
        if (!cancelled) {
          setError(normalizeErrorMessage(err?.message) || 'Kassabonnen konden niet worden geladen.')
        }
      } finally {
        if (!cancelled) setIsLoading(false)
      }
    }

    loadData()
    return () => { cancelled = true }
  }, [])

  const listItems = useMemo(() => {
    const enriched = (batches || []).map((batch) => ({
      ...batch,
      uiState: deriveBatchUiState(batch),
      providerName: providerLabel(providersByCode[batch?.store_provider_code] || batch),
    }))

    const normalizedSearch = searchValue.trim().toLowerCase()

    return enriched
      .filter((item) => {
        if (!normalizedSearch) return true
        return String(item.providerName || '').toLowerCase().includes(normalizedSearch)
      })
      .filter((item) => {
        if (statusFilter === 'all') return true
        if (statusFilter === 'open') return item.import_status !== 'processed'
        if (statusFilter === 'action_needed') return item.uiState?.statusKey === 'action_needed'
        if (statusFilter === 'processed') return item.import_status === 'processed'
        return true
      })
      .sort((a, b) => String(b.created_at || '').localeCompare(String(a.created_at || '')))
  }, [batches, providersByCode, searchValue, statusFilter])

  return (
    <AppShell title="Kassabonnen" showExit={false}>
      <div style={{ display: 'grid', gap: '16px' }}>
        <Card>
          <div style={{ display: 'flex', justifyContent: 'space-between', gap: '12px', flexWrap: 'wrap', alignItems: 'center' }}>
            <div style={{ display: 'grid', gap: '6px' }}>
              <h2 style={{ margin: 0, fontSize: '24px' }}>Kassabonnen</h2>
              <div style={{ color: '#667085' }}>Open, bekijk en verwerk je kassabonnen</div>
              {household?.naam ? <div style={{ color: '#667085' }}>Huishouden: {household.naam}</div> : null}
            </div>
            <div style={{ display: 'flex', gap: '12px', flexWrap: 'wrap' }}>
              <Button variant="secondary" onClick={() => navigate('/home')}>Terug naar start</Button>
              <Button variant="secondary" onClick={() => navigate('/import-kassabon')}>Import kassabon</Button>
            </div>
          </div>
        </Card>

        {error ? (
          <Card><div className="rz-inline-feedback rz-inline-feedback--error">{error}</div></Card>
        ) : null}

        <Card>
          <div style={{ display: 'grid', gap: '14px' }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', gap: '12px', flexWrap: 'wrap', alignItems: 'center' }}>
              <div style={{ fontWeight: 700, fontSize: '20px' }}>Kassabonnen</div>
              <div style={{ display: 'grid', gridTemplateColumns: 'minmax(220px, 1fr) 180px', gap: '12px', width: 'min(100%, 520px)' }}>
                <input
                  className="rz-input"
                  type="text"
                  placeholder="Zoek winkel"
                  value={searchValue}
                  onChange={(event) => setSearchValue(event.target.value)}
                />
                <select className="rz-input" value={statusFilter} onChange={(event) => setStatusFilter(event.target.value)}>
                  <option value="all">Alles</option>
                  <option value="open">Open</option>
                  <option value="action_needed">Actie nodig</option>
                  <option value="processed">Verwerkt</option>
                </select>
              </div>
            </div>

            {isLoading ? (
              <div>Bonnen laden…</div>
            ) : listItems.length === 0 ? (
              <div style={{ display: 'grid', gap: '12px' }}>
                <div>Er zijn nog geen kassabonnen.</div>
                <div><Button variant="primary" onClick={() => navigate('/import-kassabon')}>Import kassabon</Button></div>
              </div>
            ) : (
              <div className="rz-table-wrapper">
                <table className="rz-table">
                  <thead>
                    <tr className="rz-table-header">
                      <th>Winkel</th>
                      <th>Datum</th>
                      <th className="rz-num">Regels</th>
                      <th>Status</th>
                      <th>Actie</th>
                    </tr>
                  </thead>
                  <tbody>
                    {listItems.map((item) => (
                      <tr key={item.batch_id}>
                        <td>
                          <div style={{ fontWeight: 700 }}>{item.providerName}</div>
                          <div style={{ color: '#667085', marginTop: '4px' }}>{batchRowSubline(item)}</div>
                        </td>
                        <td>{item.purchase_date || item.created_at?.slice(0, 10) || '-'}</td>
                        <td className="rz-num">{item.summary?.total || item.lines?.length || 0}</td>
                        <td>
                          <span className={`rz-store-status-badge rz-store-status-badge--${item.uiState?.statusKey || 'new'}`}>
                            {item.import_status === 'processed' ? 'Verwerkt' : batchStatusLabel(item.import_status)}
                          </span>
                        </td>
                        <td>
                          <Button variant="secondary" onClick={() => navigate(`/winkels/batch/${item.batch_id}`)}>Open</Button>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </div>
        </Card>
      </div>
    </AppShell>
  )
}
