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
  const [rowFamilies, setRowFamilies] = useState({})
  const [rowClasses, setRowClasses] = useState({})
  const [articleSearch, setArticleSearch] = useState('')
  const [familyFilter, setFamilyFilter] = useState('')
  const [classFilter, setClassFilter] = useState('')
  const [productGroupFilter, setProductGroupFilter] = useState('')
  const [crudGroupKey, setCrudGroupKey] = useState('')
  const [crudFamily, setCrudFamily] = useState('')
  const [crudClass, setCrudClass] = useState('')
  const [crudName, setCrudName] = useState('')
  const [isLoading, setIsLoading] = useState(true)
  const [isSavingGroup, setIsSavingGroup] = useState(false)
  const [savingInventoryId, setSavingInventoryId] = useState('')
  const cols = useMemo(() => ([{ key: 'artikel', width: 320 }, { key: 'hoofdgroep', width: 240 }, { key: 'groep', width: 260 }, { key: 'productgroep', width: 320 }, { key: 'bevestigen', width: 160 }]), [])
  const defaults = useMemo(() => Object.fromEntries(cols.map(({ key, width }) => [key, width])), [cols])
  const { widths, startResize } = useResizableColumnWidths(defaults)
  const showError = (message, technicalDetail = '') => showFeedback({ variant: 'error', title: 'Melding', message, technicalDetail, showTechnicalToggle: Boolean(technicalDetail), testId: 'product-groups-feedback-error' })
  const showSuccess = (message) => showFeedback({ variant: 'success', title: 'Gelukt', message, testId: 'product-groups-feedback-success' })

  function buildAssignmentMap(payload) {
    const next = {}
    for (const group of Array.isArray(payload?.items) ? payload.items : []) for (const product of Array.isArray(group?.products) ? group.products : []) if (product?.inventory_id) next[product.inventory_id] = group?.inventory_group_key || ''
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
      const response = await fetchJsonWithAuth(`/api/inventory/items/${encodeURIComponent(inventoryId)}/group`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ inventory_group_key: inventoryGroupKey, source: 'productgroepen_ui' }) })
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
      const response = await fetchJsonWithAuth(url, { method, headers: { 'Content-Type': 'application/json' }, body: method === 'DELETE' ? undefined : JSON.stringify({ display_name: crudName, default_base_unit: 'stuk', gpc_family_name: crudFamily, gpc_class_name: crudClass }) })
      const payload = await response.json().catch(() => ({}))
      if (!response.ok) throw new Error(payload?.detail || 'Productgroep kon niet worden opgeslagen')
      setCrudGroupKey(''); setCrudFamily(''); setCrudClass(''); setCrudName('')
      await loadGroups()
      showSuccess(successMessage)
    } catch (err) {
      showError(err?.message || 'Productgroep kon niet worden opgeslagen', err?.stack || '')
    } finally {
      setIsSavingGroup(false)
    }
  }

  function selectCrudGroup(key, groupOptions) {
    const selected = groupOptions.find((group) => group.inventory_group_key === key)
    setCrudGroupKey(key)
    setCrudFamily(selected?.gpc_family_name || '')
    setCrudClass(selected?.gpc_class_name || '')
    setCrudName(selected?.display_name || '')
  }

  useEffect(() => { loadGroups({ silent: false }) }, [])
  const groups = useMemo(() => Array.isArray(data?.items) ? data.items : [], [data])
  const unresolved = useMemo(() => Array.isArray(data?.unresolved_items) ? data.unresolved_items : [], [data])
  const groupOptions = useMemo(() => { const fromApi = Array.isArray(data?.group_options) ? data.group_options : []; return fromApi.length ? fromApi : groups.map((group) => ({ inventory_group_key: group.inventory_group_key, display_name: group.display_name, default_base_unit: group.base_unit, gpc_family_name: group.gpc_family_name || group.hoofdgroep || '', gpc_class_name: group.gpc_class_name || group.groep || '', gpc_brick_code: group.gpc_brick_code || '' })) }, [data, groups])
  const groupByKey = useMemo(() => Object.fromEntries(groupOptions.map((group) => [group.inventory_group_key, group])), [groupOptions])
  const familyOptions = useMemo(() => [...new Set(groupOptions.map((group) => group.gpc_family_name || '').filter(Boolean))].sort((a, b) => a.localeCompare(b, 'nl')), [groupOptions])
  const classOptionsForFamily = (family) => [...new Set(groupOptions.filter((group) => !family || (group.gpc_family_name || '') === family).map((group) => group.gpc_class_name || '').filter(Boolean))].sort((a, b) => a.localeCompare(b, 'nl'))
  const productOptionsFor = (family, className) => groupOptions.filter((group) => !family || (group.gpc_family_name || '') === family).filter((group) => !className || (group.gpc_class_name || '') === className)
  const classOptions = useMemo(() => classOptionsForFamily(familyFilter), [groupOptions, familyFilter])
  const productOptions = useMemo(() => productOptionsFor(familyFilter, classFilter), [groupOptions, familyFilter, classFilter])
  const rows = useMemo(() => { const classified = []; for (const group of groups) for (const product of Array.isArray(group?.products) ? group.products : []) classified.push({ inventory_id: product.inventory_id, article_name: product.product_name || '-', inventory_group_key: group.inventory_group_key, gpc_family_name: group.gpc_family_name || group.hoofdgroep || '', gpc_class_name: group.gpc_class_name || group.groep || '', is_classified: true }); const open = unresolved.map((item) => ({ inventory_id: item.inventory_id, article_name: item.product_name || '-', inventory_group_key: '', gpc_family_name: '', gpc_class_name: '', is_classified: false })); return [...classified, ...open].sort((a, b) => String(a.article_name).localeCompare(String(b.article_name), 'nl')) }, [groups, unresolved])
  const filteredRows = useMemo(() => rows.filter((row) => { const id = row.inventory_id || row.article_name; const selectedKey = selectedAssignments[id] || row.inventory_group_key || ''; const selectedGroup = groupByKey[selectedKey] || {}; const fam = rowFamilies[id] || selectedGroup.gpc_family_name || row.gpc_family_name || ''; const cls = rowClasses[id] || selectedGroup.gpc_class_name || row.gpc_class_name || ''; return (!articleSearch.trim() || String(row.article_name || '').toLowerCase().includes(articleSearch.trim().toLowerCase())) && (!familyFilter || fam === familyFilter) && (!classFilter || cls === classFilter) && (!productGroupFilter || selectedKey === productGroupFilter) }), [rows, selectedAssignments, rowFamilies, rowClasses, articleSearch, familyFilter, classFilter, productGroupFilter, groupByKey])

  return <AppShell title="Productgroepen" showExit={false}><div className="rz-product-groups" data-testid="product-groups-page"><ScreenCard fullWidth><div className="rz-product-groups-header"><div><h2 className="rz-product-groups-title">Productgroepen beheren</h2><p className="rz-product-groups-subtitle">Koppel voorraadartikelen aan productgroepen om voorraad over winkels heen te kunnen bepalen. Deze pagina muteert geen voorraad.</p></div></div><section className="rz-product-groups-section"><div className="rz-product-groups-section-header"><h3>Productgroepen</h3>{isLoading ? <span className="rz-product-groups-muted">Productgroepen worden geladen...</span> : null}</div><Table dataTestId="product-groups-table" tableStyle={{ tableLayout: 'fixed', width: buildTableWidth(widths), minWidth: buildTableWidth(widths) }}><colgroup><col style={{ width: `${widths.artikel}px` }} /><col style={{ width: `${widths.hoofdgroep}px` }} /><col style={{ width: `${widths.groep}px` }} /><col style={{ width: `${widths.productgroep}px` }} /><col style={{ width: `${widths.bevestigen}px` }} /></colgroup><thead><tr className="rz-table-header"><ResizableHeaderCell columnKey="artikel" widths={widths} onStartResize={startResize}>Artikel</ResizableHeaderCell><ResizableHeaderCell columnKey="hoofdgroep" widths={widths} onStartResize={startResize}>Hoofdgroep</ResizableHeaderCell><ResizableHeaderCell columnKey="groep" widths={widths} onStartResize={startResize}>Groep</ResizableHeaderCell><ResizableHeaderCell columnKey="productgroep" widths={widths} onStartResize={startResize}>Productgroep</ResizableHeaderCell><ResizableHeaderCell columnKey="bevestigen" widths={widths} onStartResize={startResize}>Bevestigen</ResizableHeaderCell></tr><tr className="rz-table-filters"><th><input className="rz-input rz-inline-input" aria-label="Zoek artikel" placeholder="Zoek" value={articleSearch} onChange={(event) => setArticleSearch(event.target.value)} /></th><th><select className="rz-input rz-inline-input rz-product-groups-filter-select" aria-label="Filter hoofdgroep" value={familyFilter} onChange={(event) => { setFamilyFilter(event.target.value); setClassFilter(''); setProductGroupFilter('') }}><option value="">Filter</option>{familyOptions.map((family) => <option key={family} value={family}>{family}</option>)}</select></th><th><select className="rz-input rz-inline-input rz-product-groups-filter-select" aria-label="Filter groep" value={classFilter} onChange={(event) => { setClassFilter(event.target.value); setProductGroupFilter('') }}><option value="">Filter</option>{classOptions.map((name) => <option key={name} value={name}>{name}</option>)}</select></th><th><select className="rz-input rz-inline-input rz-product-groups-filter-select" aria-label="Filter productgroep" value={productGroupFilter} onChange={(event) => setProductGroupFilter(event.target.value)}><option value="">Filter</option>{productOptions.map((group) => <option key={group.inventory_group_key} value={group.inventory_group_key}>{group.display_name || group.inventory_group_key}</option>)}</select></th><th /></tr></thead><tbody>{filteredRows.length ? filteredRows.map((row) => { const id = row.inventory_id || row.article_name; const selectedKey = selectedAssignments[id] || ''; const originalKey = originalAssignments[id] || ''; const selectedGroup = groupByKey[selectedKey] || {}; const family = rowFamilies[id] || selectedGroup.gpc_family_name || row.gpc_family_name || ''; const className = rowClasses[id] || selectedGroup.gpc_class_name || row.gpc_class_name || ''; const rowClassOptions = classOptionsForFamily(family); const rowProductOptions = productOptionsFor(family, className); const canSave = Boolean(selectedKey) && (selectedKey !== originalKey || !row.is_classified); return <tr key={id}><td className="rz-receipts-cell">{row.article_name || '-'}</td><td><select className="rz-input rz-inline-input" aria-label={`Hoofdgroep voor ${row.article_name}`} value={family} onChange={(event) => { const value = event.target.value; setRowFamilies((current) => ({ ...current, [id]: value })); setRowClasses((current) => ({ ...current, [id]: '' })); setSelectedAssignments((current) => ({ ...current, [id]: '' })) }}><option value="">Kies hoofdgroep</option>{familyOptions.map((item) => <option key={item} value={item}>{item}</option>)}</select></td><td><select className="rz-input rz-inline-input" aria-label={`Groep voor ${row.article_name}`} value={className} onChange={(event) => { const value = event.target.value; setRowClasses((current) => ({ ...current, [id]: value })); setSelectedAssignments((current) => ({ ...current, [id]: '' })) }}><option value="">Kies groep</option>{rowClassOptions.map((item) => <option key={item} value={item}>{item}</option>)}</select></td><td><select className="rz-input rz-inline-input" aria-label={`Productgroep voor ${row.article_name}`} value={selectedKey} onChange={(event) => { const value = event.target.value; const group = groupByKey[value] || {}; setSelectedAssignments((current) => ({ ...current, [id]: value })); setRowFamilies((current) => ({ ...current, [id]: group.gpc_family_name || current[id] || '' })); setRowClasses((current) => ({ ...current, [id]: group.gpc_class_name || current[id] || '' })) }}><option value="">Kies productgroep</option>{rowProductOptions.map((group) => <option key={group.inventory_group_key} value={group.inventory_group_key}>{group.display_name || group.inventory_group_key}</option>)}</select></td><td><Button type="button" variant="secondary" disabled={!canSave || savingInventoryId === id} onClick={() => assignGroup(row)}>{savingInventoryId === id ? 'Bezig...' : 'Bevestigen'}</Button></td></tr> }) : <tr><td colSpan="5">Geen voorraadartikelen gevonden.</td></tr>}</tbody></Table></section></ScreenCard><ScreenCard fullWidth><section className="rz-product-groups-crud-frame" aria-label="Productgroep beheren"><h3>Productgroep beheren</h3><div className="rz-product-groups-crud"><select className="rz-input rz-inline-input" aria-label="Bestaande productgroep" value={crudGroupKey} onChange={(event) => selectCrudGroup(event.target.value, groupOptions)}><option value="">Nieuwe productgroep</option>{groupOptions.map((group) => <option key={group.inventory_group_key} value={group.inventory_group_key}>{group.display_name}</option>)}</select><input className="rz-input rz-inline-input" aria-label="Hoofdgroep beheren" placeholder="Hoofdgroep" value={crudFamily} onChange={(event) => setCrudFamily(event.target.value)} list="product-groups-family-list" /><datalist id="product-groups-family-list">{familyOptions.map((family) => <option key={family} value={family} />)}</datalist><input className="rz-input rz-inline-input" aria-label="Groep beheren" placeholder="Groep" value={crudClass} onChange={(event) => setCrudClass(event.target.value)} /><input className="rz-input rz-inline-input" aria-label="Productgroepnaam" placeholder="Productgroepnaam" value={crudName} onChange={(event) => setCrudName(event.target.value)} /><Button type="button" variant="secondary" disabled={isSavingGroup || !crudName.trim()} onClick={() => saveProductGroup('POST', '/api/product-groups', 'Productgroep is toegevoegd.')}>Toevoegen</Button><Button type="button" variant="secondary" disabled={isSavingGroup || !crudGroupKey || !crudName.trim()} onClick={() => saveProductGroup('PUT', `/api/product-groups/${encodeURIComponent(crudGroupKey)}`, 'Productgroep is bijgewerkt.')}>Bijwerken</Button><Button type="button" variant="secondary" disabled={isSavingGroup || !crudGroupKey} onClick={() => saveProductGroup('DELETE', `/api/product-groups/${encodeURIComponent(crudGroupKey)}`, 'Productgroep is verwijderd.')}>Verwijderen</Button></div></section></ScreenCard></div></AppShell>
}
