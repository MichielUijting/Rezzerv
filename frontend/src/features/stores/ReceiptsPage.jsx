import { useEffect, useMemo, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import AppShell from '../../app/AppShell'
import ScreenCard from '../../ui/ScreenCard'
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
  const [providers, setProviders] = useState([])
  const [batches, setBatches] = useState([])
  const [filters, setFilters] = useState({ winkel: '', datum: '', regels: '', status: '' })
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

        const [providerData, connectionData] = await Promise.all([
          fetchJson('/api/store-providers'),
          fetchJson(`/api/store-connections?householdId=${encodeURIComponent(householdData.id)}`),
        ])
        if (cancelled) return
        setProviders(providerData || [])

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
      dateLabel: batch.purchase_date || batch.created_at?.slice(0, 10) || '-',
      totalLines: Number(batch.summary?.total || batch.lines?.length || 0),
      statusLabel: batch.import_status === 'processed' ? 'Verwerkt' : batchStatusLabel(batch.import_status),
    }))

    return enriched
      .filter((item) => String(item.providerName || '').toLowerCase().includes(filters.winkel.trim().toLowerCase()))
      .filter((item) => String(item.dateLabel || '').toLowerCase().includes(filters.datum.trim().toLowerCase()))
      .filter((item) => String(item.totalLines).includes(filters.regels.trim()))
      .filter((item) => String(item.statusLabel || '').toLowerCase().includes(filters.status.trim().toLowerCase()))
      .sort((a, b) => String(b.created_at || '').localeCompare(String(a.created_at || '')))
  }, [batches, providersByCode, filters])

  function handleFilterChange(key, value) {
    setFilters((current) => ({ ...current, [key]: value }))
  }

  return (
    <AppShell title="Kassabonnen" showExit={false}>
      <ScreenCard>
        {error ? <div className="rz-inline-feedback rz-inline-feedback--error" style={{ marginBottom: '12px' }}>{error}</div> : null}
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
              <tr className="rz-table-filters">
                <th>
                  <input
                    className="rz-input rz-inline-input"
                    value={filters.winkel}
                    onChange={(event) => handleFilterChange('winkel', event.target.value)}
                    placeholder="Filter"
                    aria-label="Filter op winkel"
                  />
                </th>
                <th>
                  <input
                    className="rz-input rz-inline-input"
                    value={filters.datum}
                    onChange={(event) => handleFilterChange('datum', event.target.value)}
                    placeholder="Filter"
                    aria-label="Filter op datum"
                  />
                </th>
                <th>
                  <input
                    className="rz-input rz-inline-input"
                    value={filters.regels}
                    onChange={(event) => handleFilterChange('regels', event.target.value)}
                    placeholder="Filter"
                    aria-label="Filter op regels"
                  />
                </th>
                <th>
                  <input
                    className="rz-input rz-inline-input"
                    value={filters.status}
                    onChange={(event) => handleFilterChange('status', event.target.value)}
                    placeholder="Filter"
                    aria-label="Filter op status"
                  />
                </th>
                <th />
              </tr>
            </thead>
            <tbody>
              {isLoading ? (
                <tr><td colSpan={5}>Bonnen laden…</td></tr>
              ) : listItems.length === 0 ? (
                <tr><td colSpan={5}>Er zijn nog geen kassabonnen.</td></tr>
              ) : listItems.map((item) => (
                <tr key={item.batch_id}>
                  <td>
                    <div style={{ fontWeight: 700 }}>{item.providerName}</div>
                    <div style={{ color: '#667085', marginTop: '4px' }}>{batchRowSubline(item)}</div>
                  </td>
                  <td>{item.dateLabel}</td>
                  <td className="rz-num">{item.totalLines}</td>
                  <td>
                    <span className={`rz-store-status-badge rz-store-status-badge--${item.uiState?.statusKey || 'new'}`}>
                      {item.statusLabel}
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
      </ScreenCard>
    </AppShell>
  )
}
