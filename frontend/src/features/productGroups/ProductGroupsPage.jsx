import { useEffect, useMemo, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import AppShell from '../../app/AppShell'
import ScreenCard from '../../ui/ScreenCard'
import Table from '../../ui/Table'
import Button from '../../ui/Button'
import { fetchJsonWithAuth } from '../../lib/authSession'
import './productGroups.css'

function formatQuantity(value, unit) {
  const number = Number(value)
  if (!Number.isFinite(number)) return '-'
  return `${number.toLocaleString('nl-NL', { minimumFractionDigits: 0, maximumFractionDigits: 3 })} ${unit || ''}`.trim()
}

function formatConfidence(value) {
  const number = Number(value)
  if (!Number.isFinite(number)) return '-'
  return number.toLocaleString('nl-NL', { minimumFractionDigits: 3, maximumFractionDigits: 3 })
}

function ErrorMessage({ message }) {
  if (!message) return null
  return <div className="rz-inline-feedback rz-inline-feedback--error" role="alert">{message}</div>
}

export default function ProductGroupsPage() {
  const navigate = useNavigate()
  const [data, setData] = useState(null)
  const [isLoading, setIsLoading] = useState(true)
  const [isRefreshingSchema, setIsRefreshingSchema] = useState(false)
  const [message, setMessage] = useState('')
  const [error, setError] = useState('')

  async function loadGroups() {
    setIsLoading(true)
    setError('')
    try {
      const response = await fetchJsonWithAuth('/api/inventory/groups', { method: 'GET' })
      const payload = await response.json().catch(() => ({}))
      if (!response.ok) throw new Error(payload?.detail || 'Productgroepen konden niet worden geladen')
      setData(payload)
    } catch (err) {
      setError(err?.message || 'Productgroepen konden niet worden geladen')
    } finally {
      setIsLoading(false)
    }
  }

  async function ensureSchema() {
    setIsRefreshingSchema(true)
    setMessage('')
    setError('')
    try {
      const response = await fetchJsonWithAuth('/api/admin/inventory/groups/ensure-schema', { method: 'POST' })
      const payload = await response.json().catch(() => ({}))
      if (!response.ok) throw new Error(payload?.detail || 'Schema-initialisatie is mislukt')
      setMessage('Productgroepen zijn gecontroleerd en bijgewerkt.')
      await loadGroups()
    } catch (err) {
      setError(err?.message || 'Schema-initialisatie is mislukt')
    } finally {
      setIsRefreshingSchema(false)
    }
  }

  useEffect(() => {
    loadGroups()
  }, [])

  const groups = useMemo(() => Array.isArray(data?.items) ? data.items : [], [data])
  const unresolved = useMemo(() => Array.isArray(data?.unresolved_items) ? data.unresolved_items : [], [data])

  return (
    <AppShell title="Productgroepen" showExit={false}>
      <div className="rz-product-groups" data-testid="product-groups-page">
        <ScreenCard fullWidth>
          <div className="rz-product-groups-header">
            <div>
              <h2 className="rz-product-groups-title">Productgroepen</h2>
              <p className="rz-product-groups-subtitle">Beheer voorraadgroepen over winkels, merken en barcodes heen. Deze pagina muteert geen voorraad.</p>
            </div>
            <div className="rz-product-groups-actions">
              <Button type="button" variant="secondary" onClick={ensureSchema} disabled={isRefreshingSchema}>{isRefreshingSchema ? 'Controleren...' : 'Groepen controleren'}</Button>
              <Button type="button" variant="primary" onClick={() => navigate('/home')}>Terug</Button>
            </div>
          </div>

          {message ? <div className="rz-inline-feedback rz-inline-feedback--success">{message}</div> : null}
          <ErrorMessage message={error} />

          <div className="rz-product-groups-summary" aria-label="Productgroepen samenvatting">
            <div className="rz-product-groups-summary-card">
              <div className="rz-product-groups-summary-label">Groepen</div>
              <div className="rz-product-groups-summary-value">{data?.total_groups ?? groups.length}</div>
            </div>
            <div className="rz-product-groups-summary-card">
              <div className="rz-product-groups-summary-label">Nog te classificeren</div>
              <div className="rz-product-groups-summary-value">{data?.total_unresolved_items ?? unresolved.length}</div>
            </div>
            <div className="rz-product-groups-summary-card">
              <div className="rz-product-groups-summary-label">Voorraadmutatie</div>
              <div className="rz-product-groups-summary-value">{data?.mutates_inventory ? 'Ja' : 'Nee'}</div>
            </div>
          </div>

          <section className="rz-product-groups-section">
            <div className="rz-product-groups-section-header">
              <h3>Voorraadgroepen</h3>
              {isLoading ? <span className="rz-product-groups-muted">Productgroepen worden geladen...</span> : null}
            </div>
            <Table dataTestId="product-groups-table" tableClassName="rz-product-groups-table" resizableColumns>
              <thead>
                <tr className="rz-table-header">
                  <th>Productgroep</th>
                  <th>Groepssleutel</th>
                  <th className="rz-num">Voorraad</th>
                  <th>Eenheid</th>
                  <th className="rz-num">Artikelen</th>
                  <th className="rz-num">Onbekende inhoud</th>
                  <th>Locaties</th>
                  <th className="rz-num">Betrouwbaarheid</th>
                </tr>
              </thead>
              <tbody>
                {groups.length ? groups.map((group) => (
                  <tr key={group.inventory_group_key}>
                    <td>{group.display_name || '-'}</td>
                    <td>{group.inventory_group_key || '-'}</td>
                    <td className="rz-num">{formatQuantity(group.total_normalized_quantity, group.base_unit)}</td>
                    <td>{group.base_unit || '-'}</td>
                    <td className="rz-num">{group.item_count ?? 0}</td>
                    <td className="rz-num">{group.unknown_quantity_items ?? 0}</td>
                    <td>{Array.isArray(group.locations) && group.locations.length ? group.locations.join(', ') : '-'}</td>
                    <td className="rz-num">{formatConfidence(group.confidence)}</td>
                  </tr>
                )) : (
                  <tr><td colSpan="8">Geen productgroepen gevonden.</td></tr>
                )}
              </tbody>
            </Table>
          </section>

          <section className="rz-product-groups-section">
            <div className="rz-product-groups-section-header">
              <h3>Nog te classificeren artikelen</h3>
              <span className="rz-product-groups-muted">Deze artikelen hebben nog geen voorraadgroepmatch.</span>
            </div>
            <Table dataTestId="product-groups-unresolved-table" tableClassName="rz-product-groups-table" resizableColumns>
              <thead>
                <tr className="rz-table-header">
                  <th>Artikel</th>
                  <th className="rz-num">Voorraad</th>
                  <th>Reden</th>
                </tr>
              </thead>
              <tbody>
                {unresolved.length ? unresolved.map((item) => (
                  <tr key={item.inventory_id || item.product_name}>
                    <td>{item.product_name || '-'}</td>
                    <td className="rz-num">{Number(item.stock_quantity || 0).toLocaleString('nl-NL')}</td>
                    <td>{item.reason || '-'}</td>
                  </tr>
                )) : (
                  <tr><td colSpan="3">Alle zichtbare voorraadregels zijn gekoppeld aan een productgroep.</td></tr>
                )}
              </tbody>
            </Table>
          </section>
        </ScreenCard>
      </div>
    </AppShell>
  )
}
