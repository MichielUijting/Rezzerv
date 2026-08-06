import { useEffect, useMemo, useState } from 'react'
import AppShell from '../../app/AppShell'
import Card from '../../ui/Card'
import Button from '../../ui/Button'
import Table from '../../ui/Table'
import { buildTableWidth, ResizableHeaderCell, useResizableColumnWidths } from '../../ui/resizableTable.jsx'
import { fetchJsonWithAuth, readStoredAuthContext } from '../../lib/authSession'

const STOCK = 'STOCK'
const DIRECT_CONSUMPTION = 'DIRECT_CONSUMPTION'
const UNASSIGNED_LABEL = 'Niet ingedeeld'
const greenCheckboxStyle = { accentColor: '#1A3E2B', width: 16, height: 16 }

const groupTableColumns = [
  { key: 'select', width: 48 },
  { key: 'name', width: 330 },
  { key: 'articles', width: 190 },
  { key: 'handling', width: 180 },
]
const articleTableColumns = [
  { key: 'select', width: 48 },
  { key: 'article', width: 300 },
  { key: 'group', width: 240 },
  { key: 'handling', width: 180 },
]
const groupColumnDefaults = Object.fromEntries(groupTableColumns.map(({ key, width }) => [key, width]))
const articleColumnDefaults = Object.fromEntries(articleTableColumns.map(({ key, width }) => [key, width]))

function normalizeHandling(value) {
  return String(value || '').trim().toUpperCase() === DIRECT_CONSUMPTION
    ? DIRECT_CONSUMPTION
    : STOCK
}

function getAuthContext() {
  return readStoredAuthContext() || {}
}

function getActiveHouseholdId() {
  const householdId = String(getAuthContext()?.active_household_id ?? '').trim()
  if (!householdId) throw new Error('Geen actief huishouden beschikbaar. Log opnieuw in.')
  return householdId
}

function canManageDefaults() {
  const auth = getAuthContext()
  const displayRole = String(auth?.display_role || '').toLowerCase()
  const role = String(auth?.role || '').toLowerCase()
  const permissions = auth?.permissions || {}
  return Boolean(
    permissions['articles.manage'] === true
    || displayRole === 'admin'
    || role === 'owner'
    || role === 'admin'
    || role === 'household.owner'
    || role === 'household.admin'
  )
}

async function requestJson(url, options = {}) {
  const response = await fetchJsonWithAuth(url, options)
  const data = await response.json().catch(() => ({}))
  if (!response.ok) throw new Error(data?.detail || data?.message || 'Verzoek mislukt')
  return data
}

function FeedbackOverlay({ message, error, onClose }) {
  if (!message && !error) return null
  return (
    <div className="rz-modal-backdrop" role="presentation">
      <div className="rz-modal-card" role="dialog" aria-modal="true">
        <h3 className="rz-modal-title">{error ? 'Melding' : 'Bevestiging'}</h3>
        <p className="rz-modal-text">{error || message}</p>
        <div className="rz-modal-actions"><Button type="button" onClick={onClose}>OK</Button></div>
      </div>
    </div>
  )
}

function GroupModal({ open, onClose, onSave, busy }) {
  const [name, setName] = useState('')
  useEffect(() => { if (open) setName('') }, [open])
  if (!open) return null
  return (
    <div className="rz-modal-backdrop" role="presentation">
      <div className="rz-modal-card" role="dialog" aria-modal="true">
        <h3 className="rz-modal-title">Nieuwe Artikelgroep</h3>
        <label className="rz-input-field">
          <div className="rz-label">Artikelgroepnaam</div>
          <input className="rz-input" value={name} onChange={(event) => setName(event.target.value)} autoFocus />
        </label>
        <div className="rz-modal-actions">
          <Button type="button" variant="secondary" onClick={onClose} disabled={busy}>Annuleren</Button>
          <Button type="button" onClick={() => onSave(name)} disabled={busy || !name.trim()}>Opslaan</Button>
        </div>
      </div>
    </div>
  )
}

function BulkAssignModal({ open, groups, onClose, onSave, busy }) {
  const [groupId, setGroupId] = useState('')
  useEffect(() => { if (open) setGroupId('') }, [open])
  if (!open) return null
  return (
    <div className="rz-modal-backdrop" role="presentation">
      <div className="rz-modal-card" role="dialog" aria-modal="true">
        <h3 className="rz-modal-title">Toewijzen aan Artikelgroep</h3>
        <select className="rz-input" value={groupId} onChange={(event) => setGroupId(event.target.value)}>
          <option value="">{UNASSIGNED_LABEL}</option>
          {groups.map((group) => <option key={group.id} value={group.id}>{group.name}</option>)}
        </select>
        <div className="rz-modal-actions">
          <Button type="button" variant="secondary" onClick={onClose} disabled={busy}>Annuleren</Button>
          <Button type="button" onClick={() => onSave(groupId)} disabled={busy}>Opslaan</Button>
        </div>
      </div>
    </div>
  )
}

export default function SettingsArticleGroupsPage() {
  const householdId = useMemo(() => getActiveHouseholdId(), [])
  const mayManageDefaults = useMemo(() => canManageDefaults(), [])
  const [groups, setGroups] = useState([])
  const [articles, setArticles] = useState([])
  const [defaults, setDefaults] = useState({})
  const [groupFilter, setGroupFilter] = useState('')
  const [articleFilter, setArticleFilter] = useState('')
  const [articleGroupFilter, setArticleGroupFilter] = useState('')
  const [selectedGroupIds, setSelectedGroupIds] = useState([])
  const [selectedArticleIds, setSelectedArticleIds] = useState([])
  const [selectedGroupId, setSelectedGroupId] = useState('')
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const [message, setMessage] = useState('')
  const [error, setError] = useState('')
  const [groupModalOpen, setGroupModalOpen] = useState(false)
  const [bulkModalOpen, setBulkModalOpen] = useState(false)
  const { widths: groupColumnWidths, startResize: startGroupResize } = useResizableColumnWidths(groupColumnDefaults)
  const { widths: articleColumnWidths, startResize: startArticleResize } = useResizableColumnWidths(articleColumnDefaults)

  async function loadData() {
    setLoading(true)
    setError('')
    try {
      const [groupData, articleData] = await Promise.all([
        requestJson(`/api/article-groups?household_id=${encodeURIComponent(householdId)}`),
        requestJson(`/api/article-groups/household-articles?household_id=${encodeURIComponent(householdId)}`),
      ])
      const nextGroups = Array.isArray(groupData?.items) ? groupData.items : []
      const nextArticles = Array.isArray(articleData?.items) ? articleData.items : []
      const batch = await requestJson(
        `/api/households/${encodeURIComponent(householdId)}/articles/inventory-handling/batch`,
        { method: 'POST', body: JSON.stringify({ household_article_ids: nextArticles.map((item) => item.id) }) },
      )
      setGroups(nextGroups)
      setArticles(nextArticles)
      setDefaults(Object.fromEntries(
        (Array.isArray(batch?.items) ? batch.items : []).map(
          (item) => [String(item.id), normalizeHandling(item.default_inventory_handling)],
        ),
      ))
    } catch (loadError) {
      setError(loadError?.message || 'Artikelgroepen konden niet worden geladen.')
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => { loadData() }, [])

  const sortedGroups = useMemo(
    () => [...groups].sort((a, b) => String(a.name || '').localeCompare(String(b.name || ''), 'nl')),
    [groups],
  )
  const articleCounts = useMemo(() => articles.reduce((result, article) => {
    const key = String(article.article_group_id || '')
    result[key] = (result[key] || 0) + 1
    return result
  }, {}), [articles])
  const filteredGroups = useMemo(
    () => sortedGroups.filter((group) => String(group.name || '').toLowerCase().includes(groupFilter.toLowerCase())),
    [sortedGroups, groupFilter],
  )
  const visibleArticles = useMemo(() => {
    const base = selectedGroupId
      ? articles.filter((article) => String(article.article_group_id || '') === String(selectedGroupId))
      : articles
    return [...base]
      .sort((a, b) => String(a.article_name || '').localeCompare(String(b.article_name || ''), 'nl'))
      .filter((article) => {
        const groupName = article.article_group_id
          ? String(groups.find((group) => String(group.id) === String(article.article_group_id))?.name || '')
          : UNASSIGNED_LABEL
        return String(article.article_name || '').toLowerCase().includes(articleFilter.toLowerCase())
          && groupName.toLowerCase().includes(articleGroupFilter.toLowerCase())
      })
  }, [articles, groups, selectedGroupId, articleFilter, articleGroupFilter])

  const selectableVisibleGroupIds = useMemo(
    () => filteredGroups
      .filter((group) => Number(articleCounts[String(group.id)] || 0) === 0)
      .map((group) => String(group.id)),
    [filteredGroups, articleCounts],
  )
  const visibleArticleIds = useMemo(
    () => visibleArticles.map((article) => String(article.id)),
    [visibleArticles],
  )
  const allVisibleGroupsSelected = selectableVisibleGroupIds.length > 0
    && selectableVisibleGroupIds.every((id) => selectedGroupIds.includes(id))
  const allVisibleArticlesSelected = visibleArticleIds.length > 0
    && visibleArticleIds.every((id) => selectedArticleIds.includes(id))

  function toggleAllVisibleGroups() {
    const visibleSet = new Set(selectableVisibleGroupIds)
    if (allVisibleGroupsSelected) {
      setSelectedGroupIds((current) => current.filter((id) => !visibleSet.has(id)))
      return
    }
    setSelectedGroupIds((current) => Array.from(new Set([...current, ...selectableVisibleGroupIds])))
  }

  function toggleAllVisibleArticles() {
    const visibleSet = new Set(visibleArticleIds)
    if (allVisibleArticlesSelected) {
      setSelectedArticleIds((current) => current.filter((id) => !visibleSet.has(id)))
      return
    }
    setSelectedArticleIds((current) => Array.from(new Set([...current, ...visibleArticleIds])))
  }

  async function saveHandling(articleId, checked) {
    const next = checked ? DIRECT_CONSUMPTION : STOCK
    const previous = defaults[String(articleId)] || STOCK
    setDefaults((current) => ({ ...current, [String(articleId)]: next }))
    try {
      const saved = await requestJson(
        `/api/households/${encodeURIComponent(householdId)}/articles/${encodeURIComponent(articleId)}/inventory-handling`,
        { method: 'PUT', body: JSON.stringify({ default_inventory_handling: next }) },
      )
      setDefaults((current) => ({ ...current, [String(articleId)]: normalizeHandling(saved?.default_inventory_handling) }))
    } catch (saveError) {
      setDefaults((current) => ({ ...current, [String(articleId)]: previous }))
      throw saveError
    }
  }

  async function setGroupHandling(groupId, checked) {
    if (!mayManageDefaults) return
    const groupArticles = articles.filter((article) => String(article.article_group_id || '') === String(groupId))
    setSaving(true)
    setError('')
    try {
      for (const article of groupArticles) await saveHandling(article.id, checked)
    } catch (saveError) {
      setError(saveError?.message || 'Standaardverwerking van de Artikelgroep kon niet worden opgeslagen.')
      await loadData()
    } finally {
      setSaving(false)
    }
  }

  async function setArticleHandling(articleId, checked) {
    if (!mayManageDefaults) return
    setSaving(true)
    setError('')
    try {
      await saveHandling(articleId, checked)
    } catch (saveError) {
      setError(saveError?.message || 'Standaardverwerking kon niet worden opgeslagen.')
    } finally {
      setSaving(false)
    }
  }

  async function saveGroupName(group, name) {
    const trimmed = String(name || '').trim()
    if (!trimmed || trimmed === group.name) return
    setSaving(true)
    try {
      await requestJson(`/api/article-groups/${encodeURIComponent(group.id)}`, {
        method: 'PUT', body: JSON.stringify({ household_id: householdId, name: trimmed }),
      })
      setGroups((current) => current.map((item) => String(item.id) === String(group.id) ? { ...item, name: trimmed } : item))
    } catch (saveError) {
      setError(saveError?.message || 'Artikelgroepnaam kon niet worden opgeslagen.')
    } finally {
      setSaving(false)
    }
  }

  async function changeArticleGroup(articleId, groupId) {
    setSaving(true)
    try {
      await requestJson(`/api/household-articles/${encodeURIComponent(articleId)}/article-group`, {
        method: 'PUT', body: JSON.stringify({ household_id: householdId, article_group_id: groupId || null }),
      })
      setArticles((current) => current.map((item) => String(item.id) === String(articleId) ? { ...item, article_group_id: groupId || null } : item))
    } catch (saveError) {
      setError(saveError?.message || 'Artikelgroep kon niet worden gewijzigd.')
    } finally {
      setSaving(false)
    }
  }

  async function addGroup(name) {
    setSaving(true)
    try {
      await requestJson('/api/article-groups', { method: 'POST', body: JSON.stringify({ household_id: householdId, name: name.trim() }) })
      setGroupModalOpen(false)
      await loadData()
      setMessage('Artikelgroep toegevoegd.')
    } catch (saveError) {
      setError(saveError?.message || 'Artikelgroep kon niet worden toegevoegd.')
    } finally {
      setSaving(false)
    }
  }

  async function deleteSelectedGroups() {
    setSaving(true)
    try {
      for (const groupId of selectedGroupIds) {
        if (Number(articleCounts[String(groupId)] || 0) > 0) continue
        await requestJson(`/api/article-groups/${encodeURIComponent(groupId)}?household_id=${encodeURIComponent(householdId)}`, { method: 'DELETE' })
      }
      setSelectedGroupIds([])
      await loadData()
    } catch (saveError) {
      setError(saveError?.message || 'Artikelgroepen konden niet worden verwijderd.')
    } finally {
      setSaving(false)
    }
  }

  async function bulkAssign(groupId) {
    setSaving(true)
    try {
      for (const articleId of selectedArticleIds) await changeArticleGroup(articleId, groupId)
      setBulkModalOpen(false)
      setSelectedArticleIds([])
      setMessage('Geselecteerde huishoudartikelen bijgewerkt.')
    } finally {
      setSaving(false)
    }
  }

  function exportArticles() {
    const rows = [['Artikel', 'Artikelgroep', 'Standaardverwerking'], ...visibleArticles.map((article) => {
      const groupName = article.article_group_id
        ? groups.find((group) => String(group.id) === String(article.article_group_id))?.name || ''
        : UNASSIGNED_LABEL
      const handling = normalizeHandling(defaults[String(article.id)]) === DIRECT_CONSUMPTION ? 'Direct consumeren' : 'Opslaan in voorraad'
      return [article.article_name || '', groupName, handling]
    })]
    const csv = rows.map((row) => row.map((value) => `"${String(value).replaceAll('"', '""')}"`).join(',')).join('\n')
    const url = URL.createObjectURL(new Blob([csv], { type: 'text/csv;charset=utf-8' }))
    const anchor = document.createElement('a')
    anchor.href = url
    anchor.download = 'rezzerv-huishoudartikelen.csv'
    anchor.click()
    URL.revokeObjectURL(url)
  }

  const groupTableWidth = buildTableWidth(groupColumnWidths)
  const articleTableWidth = buildTableWidth(articleColumnWidths)

  return (
    <AppShell title="Artikelgroepen" showExit={false}>
      <Card className="rz-settings-spaces-card">
        <div style={{ display: 'grid', gap: 24, width: '100%' }} data-testid="settings-article-groups-page">
          <h2 style={{ margin: 0, fontSize: 20 }}>Beheer Artikelgroepen</h2>

          <section style={{ display: 'grid', gap: 18 }}>
            <strong>Artikelgroepen</strong>
            <Table wrapperClassName="rz-stock-table-wrapper" tableClassName="rz-stock-table" tableStyle={{ tableLayout: 'fixed', width: groupTableWidth, minWidth: groupTableWidth, maxWidth: '100%' }}>
              <colgroup>
                <col style={{ width: `${groupColumnWidths.select}px` }} />
                <col style={{ width: `${groupColumnWidths.name}px` }} />
                <col style={{ width: `${groupColumnWidths.articles}px` }} />
                <col style={{ width: `${groupColumnWidths.handling}px` }} />
              </colgroup>
              <thead>
                <tr className="rz-table-header">
                  <ResizableHeaderCell columnKey="select" widths={groupColumnWidths} onStartResize={startGroupResize}>
                    <input type="checkbox" style={greenCheckboxStyle} checked={allVisibleGroupsSelected} disabled={selectableVisibleGroupIds.length === 0} onChange={toggleAllVisibleGroups} aria-label="Selecteer alle zichtbare selecteerbare Artikelgroepen" />
                  </ResizableHeaderCell>
                  <ResizableHeaderCell columnKey="name" widths={groupColumnWidths} onStartResize={startGroupResize}>Artikelgroep</ResizableHeaderCell>
                  <ResizableHeaderCell columnKey="articles" widths={groupColumnWidths} onStartResize={startGroupResize} className="rz-num">Aantal artikelen</ResizableHeaderCell>
                  <ResizableHeaderCell columnKey="handling" widths={groupColumnWidths} onStartResize={startGroupResize}>Standaardverwerking</ResizableHeaderCell>
                </tr>
                <tr className="rz-table-filters">
                  <th />
                  <th><input className="rz-input rz-inline-input" value={groupFilter} onChange={(event) => setGroupFilter(event.target.value)} placeholder="Filter" /></th>
                  <th />
                  <th />
                </tr>
              </thead>
              <tbody>
                {loading ? <tr><td colSpan={4}>Artikelgroepen laden…</td></tr> : filteredGroups.length === 0 ? <tr><td colSpan={4}>Geen Artikelgroepen gevonden.</td></tr> : filteredGroups.map((group) => {
                  const groupArticles = articles.filter((article) => String(article.article_group_id || '') === String(group.id))
                  const directChecked = groupArticles.length > 0 && groupArticles.every((article) => normalizeHandling(defaults[String(article.id)]) === DIRECT_CONSUMPTION)
                  const deletable = groupArticles.length === 0
                  return (
                    <tr key={group.id} className={String(selectedGroupId) === String(group.id) ? 'rz-row-selected' : ''} onDoubleClick={() => setSelectedGroupId(String(group.id))}>
                      <td><input type="checkbox" style={greenCheckboxStyle} checked={selectedGroupIds.includes(String(group.id))} disabled={!deletable} onChange={() => setSelectedGroupIds((current) => current.includes(String(group.id)) ? current.filter((id) => id !== String(group.id)) : [...current, String(group.id)])} /></td>
                      <td><input className="rz-input rz-inline-input" defaultValue={group.name} onBlur={(event) => saveGroupName(group, event.target.value)} /></td>
                      <td className="rz-num">{groupArticles.length}</td>
                      <td style={{ textAlign: 'center' }}><input type="checkbox" style={greenCheckboxStyle} checked={directChecked} disabled={!mayManageDefaults || saving || groupArticles.length === 0} onChange={(event) => setGroupHandling(group.id, event.target.checked)} aria-label={`Standaardverwerking Artikelgroep ${group.name}`} /></td>
                    </tr>
                  )
                })}
              </tbody>
            </Table>
            <div className="rz-stock-table-actions" style={{ justifyContent: 'flex-end', gap: 12 }}>
              <Button type="button" variant="secondary" onClick={deleteSelectedGroups} disabled={saving || selectedGroupIds.length === 0}>Verwijderen</Button>
              <Button type="button" onClick={() => setGroupModalOpen(true)} disabled={saving}>Toevoegen Artikelgroep</Button>
            </div>
          </section>

          <section style={{ display: 'grid', gap: 18 }}>
            <strong>Huishoudartikelen{selectedGroupId ? ` van ${groups.find((group) => String(group.id) === String(selectedGroupId))?.name || ''}` : ''}</strong>
            <p style={{ margin: 0, color: '#667085' }}>Koppelen is handmatig. Barcodeherkenning, externe databases en Uitpakken wijzigen deze koppeling niet.</p>
            <Table wrapperClassName="rz-stock-table-wrapper" tableClassName="rz-stock-table" tableStyle={{ tableLayout: 'fixed', width: articleTableWidth, minWidth: articleTableWidth, maxWidth: '100%' }}>
              <colgroup>
                <col style={{ width: `${articleColumnWidths.select}px` }} />
                <col style={{ width: `${articleColumnWidths.article}px` }} />
                <col style={{ width: `${articleColumnWidths.group}px` }} />
                <col style={{ width: `${articleColumnWidths.handling}px` }} />
              </colgroup>
              <thead>
                <tr className="rz-table-header">
                  <ResizableHeaderCell columnKey="select" widths={articleColumnWidths} onStartResize={startArticleResize}>
                    <input type="checkbox" style={greenCheckboxStyle} checked={allVisibleArticlesSelected} disabled={visibleArticleIds.length === 0} onChange={toggleAllVisibleArticles} aria-label="Selecteer alle zichtbare huishoudartikelen" />
                  </ResizableHeaderCell>
                  <ResizableHeaderCell columnKey="article" widths={articleColumnWidths} onStartResize={startArticleResize}>Artikel</ResizableHeaderCell>
                  <ResizableHeaderCell columnKey="group" widths={articleColumnWidths} onStartResize={startArticleResize}>Artikelgroep</ResizableHeaderCell>
                  <ResizableHeaderCell columnKey="handling" widths={articleColumnWidths} onStartResize={startArticleResize}>Standaardverwerking</ResizableHeaderCell>
                </tr>
                <tr className="rz-table-filters">
                  <th />
                  <th><input className="rz-input rz-inline-input" value={articleFilter} onChange={(event) => setArticleFilter(event.target.value)} placeholder="Filter" /></th>
                  <th><input className="rz-input rz-inline-input" value={articleGroupFilter} onChange={(event) => setArticleGroupFilter(event.target.value)} placeholder="Filter" /></th>
                  <th />
                </tr>
              </thead>
              <tbody>
                {loading ? <tr><td colSpan={4}>Huishoudartikelen laden…</td></tr> : visibleArticles.length === 0 ? <tr><td colSpan={4}>Geen huishoudartikelen gevonden.</td></tr> : visibleArticles.map((article) => (
                  <tr key={article.id} className={selectedArticleIds.includes(String(article.id)) ? 'rz-row-selected' : ''}>
                    <td><input type="checkbox" style={greenCheckboxStyle} checked={selectedArticleIds.includes(String(article.id))} onChange={() => setSelectedArticleIds((current) => current.includes(String(article.id)) ? current.filter((id) => id !== String(article.id)) : [...current, String(article.id)])} /></td>
                    <td>{article.article_name || 'Onbekend artikel'}</td>
                    <td><select className="rz-input rz-inline-input" value={article.article_group_id || ''} onChange={(event) => changeArticleGroup(article.id, event.target.value)} disabled={saving}><option value="">{UNASSIGNED_LABEL}</option>{sortedGroups.map((group) => <option key={group.id} value={group.id}>{group.name}</option>)}</select></td>
                    <td style={{ textAlign: 'center' }}><input type="checkbox" style={greenCheckboxStyle} checked={normalizeHandling(defaults[String(article.id)]) === DIRECT_CONSUMPTION} disabled={!mayManageDefaults || saving} onChange={(event) => setArticleHandling(article.id, event.target.checked)} aria-label={`Standaardverwerking ${article.article_name || 'huishoudartikel'}`} /></td>
                  </tr>
                ))}
              </tbody>
            </Table>
            <div className="rz-stock-table-actions" style={{ justifyContent: 'flex-end', gap: 12, flexWrap: 'wrap' }}>
              <Button type="button" variant="secondary" onClick={exportArticles} disabled={loading}>Exporteren</Button>
              <Button type="button" variant="secondary" onClick={() => setBulkModalOpen(true)} disabled={saving || selectedArticleIds.length === 0}>Toewijzen aan Artikelgroep</Button>
              <Button type="button" variant="secondary" onClick={() => bulkAssign('')} disabled={saving || selectedArticleIds.length === 0}>Verwijderen</Button>
            </div>
          </section>
        </div>
      </Card>

      <FeedbackOverlay message={message} error={error} onClose={() => { setMessage(''); setError('') }} />
      <GroupModal open={groupModalOpen} onClose={() => setGroupModalOpen(false)} onSave={addGroup} busy={saving} />
      <BulkAssignModal open={bulkModalOpen} groups={sortedGroups} onClose={() => setBulkModalOpen(false)} onSave={bulkAssign} busy={saving} />
    </AppShell>
  )
}
