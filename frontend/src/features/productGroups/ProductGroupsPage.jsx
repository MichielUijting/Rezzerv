import { useEffect, useMemo, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import AppShell from '../../app/AppShell'
import ScreenCard from '../../ui/ScreenCard'
import Table from '../../ui/Table'
import Button from '../../ui/Button'
import { fetchJsonWithAuth } from '../../lib/authSession'
import { useAppFeedback } from '../../ui/AppFeedbackProvider.jsx'
import './productGroups.css'

const COMBINED_COLUMN_STYLES = [
  { width: '430px', minWidth: '430px' },
  { width: '360px', minWidth: '360px' },
  { width: '160px', minWidth: '160px' },
]

export default function ProductGroupsPage() {
  const navigate = useNavigate()
  const { showFeedback } = useAppFeedback()
  const [data, setData] = useState(null)
  const [selectedAssignments, setSelectedAssignments] = useState({})
  const [originalAssignments, setOriginalAssignments] = useState({})
  const [articleSearch, setArticleSearch] = useState('')
  const [groupFilter, setGroupFilter] = useState('')
  const [isLoading, setIsLoading] = useState(true)
  const [isRefreshingSchema, setIsRefreshingSchema] = useState(false)
  const [savingInventoryId, setSavingInventoryId] = useState('')

  function showError(message, technicalDetail = '') {
    showFeedback({
      variant: 'error',
      title: 'Melding',
      message,
      technicalDetail,
      showTechnicalToggle: Boolean(technicalDetail),
      testId: 'product-groups-feedback-error',
    })
  }

  function buildAssignmentMap(payload) {
    const next = {}
    const groups = Array.isArray(payload?.items) ? payload.items : []
    for (const group of groups) {
      const products = Array.isArray(group?.products) ? group.products : []
      for (const product of products) {
        const inventoryId = product?.inventory_id || ''
        if (inventoryId) next[inventoryId] = group?.inventory_group_key || ''
      }
    }
    return next
  }

  async function loadGroups({ silent = true } = {}) {
    setIsLoading(true)
    try {
      const response = await fetchJsonWithAuth('/api/inventory/groups', { method: 'GET' })
      const payload = await response.json().catch(() => ({}))
      if (!response.ok) throw new Error(payload?.detail || 'Productgroepen konden niet worden geladen')
      setData(payload)
      const assignments = buildAssignmentMap(payload)
      setOriginalAssignments(assignments)
      setSelectedAssignments(assignments)
    } catch (err) {
      if (!silent) showError(err?.message || 'Productgroepen konden niet worden geladen', err?.stack || '')
    } finally {
      setIsLoading(false)
    }
  }

  async function ensureSchema() {
    setIsRefreshingSchema(true)
    try {
      const response = await fetchJsonWithAuth('/api/admin/inventory/groups/ensure-schema', { method: 'POST' })
      const payload = await response.json().catch(() => ({}))
      if (!response.ok) throw new Error(payload?.detail || 'Schema-initialisatie is mislukt')
      await loadGroups()
      showFeedback({
        variant: 'success',
        title: 'Gelukt',
        message: 'Productgroepen zijn gecontroleerd en bijgewerkt.',
        testId: 'product-groups-feedback-success',
      })
    } catch (err) {
      showError(err?.message || 'Schema-initialisatie is mislukt', err?.stack || '')
    } finally {
      setIsRefreshingSchema(false)
    }
  }

  async function assignGroup(row) {
    const inventoryId = row?.inventory_id || ''
    const inventoryGroupKey = selectedAssignments[inventoryId] || ''
    if (!inventoryId || !inventoryGroupKey) return
    setSavingInventoryId(inventoryId)
    try {
      const response = await fetchJsonWithAuth(`/api/inventory/items/${encodeURIComponent(inventoryId)}/group`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ inventory_group_key: inventoryGroupKey, source: 'productgroepen_ui' }),
      })
      const payload = await response.json().catch(() => ({}))
      if (!response.ok) throw new Error(payload?.detail || 'Artikel kon niet worden ingedeeld')
      await loadGroups()
      showFeedback({
        variant: 'success',
        title: 'Gelukt',
        message: 'Artikel is aan de productgroep toegevoegd.',
        testId: 'product-groups-feedback-success',
      })
    } catch (err) {
      showError(err?.message || 'Artikel kon niet worden ingedeeld', err?.stack || '')
    } finally {
      setSavingInventoryId('')
    }
  }

  useEffect(() => {
    loadGroups({ silent: false })
  }, [])

  const groups = useMemo(() => Array.isArray(data?.items) ? data.items : [], [data])
  const unresolved = useMemo(() => Array.isArray(data?.unresolved_items) ? data.unresolved_items : [], [data])
  const groupOptions = useMemo(() => {
    const fromApi = Array.isArray(data?.group_options) ? data.group_options : []
    if (fromApi.length) return fromApi
    return groups.map((group) => ({ inventory_group_key: group.inventory_group_key, display_name: group.display_name, default_base_unit: group.base_unit }))
  }, [data, groups])
  const rows = useMemo(() => {
    const classifiedRows = []
    for (const group of groups) {
      const products = Array.isArray(group?.products) ? group.products : []
      for (const product of products) {
        classifiedRows.push({
          inventory_id: product.inventory_id,
          article_name: product.product_name || '-',
          inventory_group_key: group.inventory_group_key,
          inventory_group_name: group.display_name || group.inventory_group_key,
          is_classified: true,
        })
      }
    }
    const unresolvedRows = unresolved.map((item) => ({
      inventory_id: item.inventory_id,
      article_name: item.product_name || '-',
      inventory_group_key: '',
      inventory_group_name: '',
      is_classified: false,
    }))
    return [...classifiedRows, ...unresolvedRows].sort((a, b) => String(a.article_name).localeCompare(String(b.article_name), 'nl'))
  }, [groups, unresolved])
  const filteredRows = useMemo(() => {
    const searchValue = articleSearch.trim().toLowerCase()
    return rows.filter((row) => {
      const inventoryId = row.inventory_id || row.article_name
      const selectedValue = selectedAssignments[inventoryId] || row.inventory_group_key || ''
      const articleMatches = !searchValue || String(row.article_name || '').toLowerCase().includes(searchValue)
      const groupMatches = !groupFilter || selectedValue === groupFilter
      return articleMatches && groupMatches
    })
  }, [rows, selectedAssignments, articleSearch, groupFilter])

  return (
    <AppShell title="Productgroepen" showExit={false}>
      <div className="rz-product-groups" data-testid="product-groups-page">
        <ScreenCard fullWidth>
          <div className="rz-product-groups-header">
            <div>
              <h2 className="rz-product-groups-title">Productgroepen beheren</h2>
              <p className="rz-product-groups-subtitle">Koppel voorraadartikelen aan productgroepen om voorraad over winkels heen te kunnen bepalen. Deze pagina muteert geen voorraad.</p>
            </div>
            <div className="rz-product-groups-actions">
              <Button type="button" variant="secondary" onClick={ensureSchema} disabled={isRefreshingSchema}>{isRefreshingSchema ? 'Controleren...' : 'Groepen controleren'}</Button>
              <Button type="button" variant="primary" onClick={() => navigate('/home')}>Terug</Button>
            </div>
          </div>

          <section className="rz-product-groups-section">
            <div className="rz-product-groups-section-header">
              <h3>Productgroepen</h3>
              {isLoading ? <span className="rz-product-groups-muted">Productgroepen worden geladen...</span> : null}
            </div>
            <Table dataTestId="product-groups-table" tableClassName="rz-product-groups-table rz-product-groups-table--combined" tableStyle={{ width: '950px', minWidth: '950px' }} resizableColumns>
              <colgroup>{COMBINED_COLUMN_STYLES.map((style, index) => <col key={`combined-col-${index}`} style={style} />)}</colgroup>
              <thead>
                <tr className="rz-table-header">
                  <th style={COMBINED_COLUMN_STYLES[0]}>Artikel</th>
                  <th style={COMBINED_COLUMN_STYLES[1]}>Productgroep</th>
                  <th style={COMBINED_COLUMN_STYLES[2]}>Bevestigen</th>
                </tr>
                <tr className="rz-table-filter-row">
                  <th style={COMBINED_COLUMN_STYLES[0]}>
                    <input
                      className="rz-input rz-product-groups-filter-input"
                      aria-label="Zoek artikel"
                      placeholder="Zoek"
                      value={articleSearch}
                      onChange={(event) => setArticleSearch(event.target.value)}
                    />
                  </th>
                  <th style={COMBINED_COLUMN_STYLES[1]}>
                    <select
                      className="rz-input rz-product-groups-select"
                      aria-label="Filter productgroep"
                      value={groupFilter}
                      onChange={(event) => setGroupFilter(event.target.value)}
                    >
                      <option value="">Filter</option>
                      {groupOptions.map((group) => (
                        <option key={group.inventory_group_key} value={group.inventory_group_key}>{group.display_name || group.inventory_group_key}</option>
                      ))}
                    </select>
                  </th>
                  <th style={COMBINED_COLUMN_STYLES[2]}></th>
                </tr>
              </thead>
              <tbody>
                {filteredRows.length ? filteredRows.map((row) => {
                  const inventoryId = row.inventory_id || row.article_name
                  const selectedValue = selectedAssignments[inventoryId] || ''
                  const originalValue = originalAssignments[inventoryId] || ''
                  const isChanged = selectedValue !== originalValue
                  const canSave = Boolean(selectedValue) && (isChanged || !row.is_classified)
                  return (
                    <tr key={inventoryId}>
                      <td style={COMBINED_COLUMN_STYLES[0]}>{row.article_name || '-'}</td>
                      <td style={COMBINED_COLUMN_STYLES[1]}>
                        <select
                          className="rz-input rz-product-groups-select"
                          aria-label={`Productgroep voor ${row.article_name}`}
                          value={selectedValue}
                          onChange={(event) => setSelectedAssignments((current) => ({ ...current, [inventoryId]: event.target.value }))}
                        >
                          <option value="">Kies productgroep</option>
                          {groupOptions.map((group) => (
                            <option key={group.inventory_group_key} value={group.inventory_group_key}>{group.display_name || group.inventory_group_key}</option>
                          ))}
                        </select>
                      </td>
                      <td style={COMBINED_COLUMN_STYLES[2]}>
                        <Button type="button" variant="secondary" disabled={!canSave || savingInventoryId === inventoryId} onClick={() => assignGroup(row)}>
                          {savingInventoryId === inventoryId ? 'Bezig...' : 'Bevestigen'}
                        </Button>
                      </td>
                    </tr>
                  )
                }) : (
                  <tr><td colSpan="3">Geen voorraadartikelen gevonden.</td></tr>
                )}
              </tbody>
            </Table>
          </section>
        </ScreenCard>
      </div>
    </AppShell>
  )
}
