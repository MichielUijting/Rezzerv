import { useEffect, useMemo, useState } from 'react'
import AppShell from '../../app/AppShell'
import ScreenCard from '../../ui/ScreenCard'
import Table from '../../ui/Table'
import Button from '../../ui/Button'
import { fetchJsonWithAuth } from '../../lib/authSession'
import { useAppFeedback } from '../../ui/AppFeedbackProvider.jsx'
import { buildTableWidth, ResizableHeaderCell, useResizableColumnWidths } from '../../ui/resizableTable.jsx'
import './productGroups.css'

export default function ProductGroupsPage() {
  const { showFeedback } = useAppFeedback()
  const [data, setData] = useState(null)
  const [selectedAssignments, setSelectedAssignments] = useState({})
  const [originalAssignments, setOriginalAssignments] = useState({})
  const [articleSearch, setArticleSearch] = useState('')
  const [groupFilter, setGroupFilter] = useState('')
  const [crudGroupKey, setCrudGroupKey] = useState('')
  const [crudName, setCrudName] = useState('')
  const [isLoading, setIsLoading] = useState(true)
  const [isSavingGroup, setIsSavingGroup] = useState(false)
  const [savingInventoryId, setSavingInventoryId] = useState('')

  const productGroupsTableColumns = useMemo(() => ([
    { key: 'artikel', width: 360 },
    { key: 'productgroep', width: 360 },
    { key: 'bevestigen', width: 160 },
  ]), [])
  const columnDefaults = useMemo(() => Object.fromEntries(productGroupsTableColumns.map(({ key, width }) => [key, width])), [productGroupsTableColumns])
  const { widths: tableWidths, startResize: startTableResize } = useResizableColumnWidths(columnDefaults)

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

  function showSuccess(message) {
    showFeedback({
      variant: 'success',
      title: 'Gelukt',
      message,
      testId: 'product-groups-feedback-success',
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
      showSuccess('Artikel is aan de productgroep toegevoegd.')
    } catch (err) {
      showError(err?.message || 'Artikel kon niet worden ingedeeld', err?.stack || '')
    } finally {
      setSavingInventoryId('')
    }
  }

  async function saveProductGroup(method, url, successMessage) {
    setIsSavingGroup(true)
    try {
      const response = await fetchJsonWithAuth(url, {
        method,
        headers: { 'Content-Type': 'application/json' },
        body: method === 'DELETE' ? undefined : JSON.stringify({ display_name: crudName, default_base_unit: 'stuk' }),
      })
      const payload = await response.json().catch(() => ({}))
      if (!response.ok) throw new Error(payload?.detail || 'Productgroep kon niet worden opgeslagen')
      setCrudGroupKey('')
      setCrudName('')
      await loadGroups()
      showSuccess(successMessage)
    } catch (err) {
      showError(err?.message || 'Productgroep kon niet worden opgeslagen', err?.stack || '')
    } finally {
      setIsSavingGroup(false)
    }
  }

  function selectCrudGroup(key, groupOptions) {
    setCrudGroupKey(key)
    const selected = groupOptions.find((group) => group.inventory_group_key === key)
    setCrudName(selected?.display_name || '')
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
          </div>

          <section className="rz-product-groups-section">
            <div className="rz-product-groups-section-header">
              <h3>Productgroepen</h3>
              {isLoading ? <span className="rz-product-groups-muted">Productgroepen worden geladen...</span> : null}
            </div>
            <Table dataTestId="product-groups-table" tableStyle={{ tableLayout: 'fixed', width: buildTableWidth(tableWidths), minWidth: buildTableWidth(tableWidths) }}>
              <colgroup>
                <col style={{ width: `${tableWidths.artikel}px` }} />
                <col style={{ width: `${tableWidths.productgroep}px` }} />
                <col style={{ width: `${tableWidths.bevestigen}px` }} />
              </colgroup>
              <thead>
                <tr className="rz-table-header">
                  <ResizableHeaderCell columnKey="artikel" widths={tableWidths} onStartResize={startTableResize}>Artikel</ResizableHeaderCell>
                  <ResizableHeaderCell columnKey="productgroep" widths={tableWidths} onStartResize={startTableResize}>Productgroep</ResizableHeaderCell>
                  <ResizableHeaderCell columnKey="bevestigen" widths={tableWidths} onStartResize={startTableResize}>Bevestigen</ResizableHeaderCell>
                </tr>
                <tr className="rz-table-filters">
                  <th>
                    <input className="rz-input rz-inline-input" aria-label="Zoek artikel" placeholder="Zoek" value={articleSearch} onChange={(event) => setArticleSearch(event.target.value)} />
                  </th>
                  <th>
                    <select className="rz-input rz-inline-input rz-product-groups-filter-select" aria-label="Filter productgroep" value={groupFilter} onChange={(event) => setGroupFilter(event.target.value)}>
                      <option value="">Filter</option>
                      {groupOptions.map((group) => <option key={group.inventory_group_key} value={group.inventory_group_key}>{group.display_name || group.inventory_group_key}</option>)}
                    </select>
                  </th>
                  <th />
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
                      <td className="rz-receipts-cell">{row.article_name || '-'}</td>
                      <td>
                        <select className="rz-input rz-inline-input" aria-label={`Productgroep voor ${row.article_name}`} value={selectedValue} onChange={(event) => setSelectedAssignments((current) => ({ ...current, [inventoryId]: event.target.value }))}>
                          <option value="">Kies productgroep</option>
                          {groupOptions.map((group) => <option key={group.inventory_group_key} value={group.inventory_group_key}>{group.display_name || group.inventory_group_key}</option>)}
                        </select>
                      </td>
                      <td>
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

        <ScreenCard fullWidth>
          <section className="rz-product-groups-crud-frame" aria-label="Productgroep beheren">
            <h3>Productgroep beheren</h3>
            <div className="rz-product-groups-crud">
              <select className="rz-input rz-inline-input" aria-label="Bestaande productgroep" value={crudGroupKey} onChange={(event) => selectCrudGroup(event.target.value, groupOptions)}>
                <option value="">Nieuwe productgroep</option>
                {groupOptions.map((group) => <option key={group.inventory_group_key} value={group.inventory_group_key}>{group.display_name}</option>)}
              </select>
              <input className="rz-input rz-inline-input" aria-label="Productgroepnaam" placeholder="Productgroepnaam" value={crudName} onChange={(event) => setCrudName(event.target.value)} />
              <Button type="button" variant="secondary" disabled={isSavingGroup || !crudName.trim()} onClick={() => saveProductGroup('POST', '/api/product-groups', 'Productgroep is toegevoegd.')}>Toevoegen</Button>
              <Button type="button" variant="secondary" disabled={isSavingGroup || !crudGroupKey || !crudName.trim()} onClick={() => saveProductGroup('PUT', `/api/product-groups/${encodeURIComponent(crudGroupKey)}`, 'Productgroep is bijgewerkt.')}>Bijwerken</Button>
              <Button type="button" variant="secondary" disabled={isSavingGroup || !crudGroupKey} onClick={() => saveProductGroup('DELETE', `/api/product-groups/${encodeURIComponent(crudGroupKey)}`, 'Productgroep is verwijderd.')}>Verwijderen</Button>
            </div>
          </section>
        </ScreenCard>
      </div>
    </AppShell>
  )
}
