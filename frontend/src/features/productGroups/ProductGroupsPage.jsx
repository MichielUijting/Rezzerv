import { useEffect, useMemo, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import AppShell from '../../app/AppShell'
import ScreenCard from '../../ui/ScreenCard'
import Table from '../../ui/Table'
import Button from '../../ui/Button'
import { fetchJsonWithAuth } from '../../lib/authSession'
import './productGroups.css'

function ErrorMessage({ message }) {
  if (!message) return null
  return <div className="rz-inline-feedback rz-inline-feedback--error" role="alert">{message}</div>
}

export default function ProductGroupsPage() {
  const navigate = useNavigate()
  const [data, setData] = useState(null)
  const [selectedGroupKey, setSelectedGroupKey] = useState('')
  const [selectedAssignments, setSelectedAssignments] = useState({})
  const [isLoading, setIsLoading] = useState(true)
  const [isRefreshingSchema, setIsRefreshingSchema] = useState(false)
  const [savingInventoryId, setSavingInventoryId] = useState('')
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
      const groups = Array.isArray(payload?.items) ? payload.items : []
      if (!selectedGroupKey && groups[0]?.inventory_group_key) setSelectedGroupKey(groups[0].inventory_group_key)
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

  async function assignGroup(item) {
    const inventoryId = item?.inventory_id || ''
    const inventoryGroupKey = selectedAssignments[inventoryId] || ''
    if (!inventoryId || !inventoryGroupKey) return
    setSavingInventoryId(inventoryId)
    setMessage('')
    setError('')
    try {
      const response = await fetchJsonWithAuth(`/api/inventory/items/${encodeURIComponent(inventoryId)}/group`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ inventory_group_key: inventoryGroupKey, source: 'productgroepen_ui' }),
      })
      const payload = await response.json().catch(() => ({}))
      if (!response.ok) throw new Error(payload?.detail || 'Artikel kon niet worden ingedeeld')
      setSelectedGroupKey(inventoryGroupKey)
      setSelectedAssignments((current) => {
        const next = { ...current }
        delete next[inventoryId]
        return next
      })
      setMessage('Artikel is aan de productgroep toegevoegd.')
      await loadGroups()
    } catch (err) {
      setError(err?.message || 'Artikel kon niet worden ingedeeld')
    } finally {
      setSavingInventoryId('')
    }
  }

  useEffect(() => {
    loadGroups()
  }, [])

  const groups = useMemo(() => Array.isArray(data?.items) ? data.items : [], [data])
  const unresolved = useMemo(() => Array.isArray(data?.unresolved_items) ? data.unresolved_items : [], [data])
  const groupOptions = useMemo(() => {
    const fromApi = Array.isArray(data?.group_options) ? data.group_options : []
    if (fromApi.length) return fromApi
    return groups.map((group) => ({ inventory_group_key: group.inventory_group_key, display_name: group.display_name }))
  }, [data, groups])
  const selectedGroup = groups.find((group) => group.inventory_group_key === selectedGroupKey) || groups[0] || null
  const selectedProducts = Array.isArray(selectedGroup?.products) ? selectedGroup.products : []

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

          <section className="rz-product-groups-section">
            <div className="rz-product-groups-section-header">
              <h3>Productgroepen</h3>
              {isLoading ? <span className="rz-product-groups-muted">Productgroepen worden geladen...</span> : null}
            </div>
            <Table dataTestId="product-groups-table" tableClassName="rz-product-groups-table" resizableColumns>
              <thead>
                <tr className="rz-table-header">
                  <th>Productgroep</th>
                  <th className="rz-num">Artikelen</th>
                  <th>Eenheid</th>
                </tr>
              </thead>
              <tbody>
                {groups.length ? groups.map((group) => (
                  <tr
                    key={group.inventory_group_key}
                    className={group.inventory_group_key === selectedGroup?.inventory_group_key ? 'rz-product-groups-selected-row' : ''}
                    onClick={() => setSelectedGroupKey(group.inventory_group_key)}
                  >
                    <td>{group.display_name || '-'}</td>
                    <td className="rz-num">{group.item_count ?? 0}</td>
                    <td>{group.base_unit || '-'}</td>
                  </tr>
                )) : (
                  <tr><td colSpan="3">Geen productgroepen gevonden.</td></tr>
                )}
              </tbody>
            </Table>
          </section>

          <section className="rz-product-groups-section">
            <div className="rz-product-groups-section-header">
              <h3>Artikelen in productgroep</h3>
              <span className="rz-product-groups-muted">{selectedGroup?.display_name || 'Geen productgroep geselecteerd'}</span>
            </div>
            <Table dataTestId="product-groups-detail-table" tableClassName="rz-product-groups-table" resizableColumns>
              <thead>
                <tr className="rz-table-header">
                  <th>Artikel</th>
                </tr>
              </thead>
              <tbody>
                {selectedProducts.length ? selectedProducts.map((product) => (
                  <tr key={product.inventory_id || product.product_name}>
                    <td>{product.product_name || '-'}</td>
                  </tr>
                )) : (
                  <tr><td>Geen artikelen in deze productgroep.</td></tr>
                )}
              </tbody>
            </Table>
          </section>

          <section className="rz-product-groups-section">
            <div className="rz-product-groups-section-header">
              <h3>Nog te classificeren artikelen</h3>
              <span className="rz-product-groups-muted">Kies een productgroep en bevestig.</span>
            </div>
            <Table dataTestId="product-groups-unresolved-table" tableClassName="rz-product-groups-table" resizableColumns>
              <thead>
                <tr className="rz-table-header">
                  <th>Artikel</th>
                  <th>Productgroep</th>
                  <th>Bevestigen</th>
                </tr>
              </thead>
              <tbody>
                {unresolved.length ? unresolved.map((item) => {
                  const inventoryId = item.inventory_id || item.product_name
                  const selectedValue = selectedAssignments[inventoryId] || ''
                  return (
                    <tr key={inventoryId}>
                      <td>{item.product_name || '-'}</td>
                      <td>
                        <select
                          className="rz-input rz-product-groups-select"
                          aria-label={`Productgroep voor ${item.product_name}`}
                          value={selectedValue}
                          onChange={(event) => setSelectedAssignments((current) => ({ ...current, [inventoryId]: event.target.value }))}
                        >
                          <option value="">Kies productgroep</option>
                          {groupOptions.map((group) => (
                            <option key={group.inventory_group_key} value={group.inventory_group_key}>{group.display_name || group.inventory_group_key}</option>
                          ))}
                        </select>
                      </td>
                      <td>
                        <Button type="button" variant="secondary" disabled={!selectedValue || savingInventoryId === inventoryId} onClick={() => assignGroup(item)}>
                          {savingInventoryId === inventoryId ? 'Bezig...' : 'Bevestigen'}
                        </Button>
                      </td>
                    </tr>
                  )
                }) : (
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
