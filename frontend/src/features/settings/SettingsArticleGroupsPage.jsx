import { useEffect, useMemo, useRef, useState } from 'react'
import AppShell from '../../app/AppShell'
import Card from '../../ui/Card'
import Button from '../../ui/Button'
import Table from '../../ui/Table'
import { buildTableWidth, ResizableHeaderCell, useResizableColumnWidths } from '../../ui/resizableTable.jsx'
import { fetchJsonWithAuth, readStoredAuthContext } from '../../lib/authSession'

const UNASSIGNED_LABEL = 'Niet ingedeeld'
const initialGroupForm = { name: '', active: true }
const initialGroupFilters = { name: '', active: false, articles: '' }
const initialArticleFilters = { article: '', group: '' }
const groupTableColumns = [
  { key: 'select', width: 48 },
  { key: 'name', width: 420 },
  { key: 'active', width: 140 },
  { key: 'articles', width: 180 },
]
const articleTableColumns = [
  { key: 'select', width: 48 },
  { key: 'article', width: 420 },
  { key: 'group', width: 320 },
]
const groupColumnDefaults = Object.fromEntries(groupTableColumns.map(({ key, width }) => [key, width]))
const articleColumnDefaults = Object.fromEntries(articleTableColumns.map(({ key, width }) => [key, width]))
const greenCheckboxStyle = { accentColor: '#1A3E2B', width: 16, height: 16 }

function getActiveHouseholdId() {
  return String(readStoredAuthContext()?.active_household_id || '1').trim() || '1'
}

function extractErrorMessage(payload, fallback) {
  if (typeof payload === 'string' && payload.trim()) return payload.trim()
  if (payload && typeof payload === 'object') {
    if (typeof payload.detail === 'string' && payload.detail.trim()) return payload.detail.trim()
    if (typeof payload.error === 'string' && payload.error.trim()) return payload.error.trim()
    if (typeof payload.message === 'string' && payload.message.trim()) return payload.message.trim()
  }
  return fallback
}

async function requestJson(url, options = {}) {
  const response = await fetchJsonWithAuth(url, options)
  const data = await response.json().catch(() => ({}))
  if (!response.ok) throw new Error(extractErrorMessage(data, 'Verzoek mislukt'))
  return data
}

function FeedbackOverlay({ type = 'info', message, onClose }) {
  if (!message) return null
  const isError = type === 'error'
  const title = isError ? 'Melding' : 'Bevestiging'
  return (
    <div className="rz-modal-backdrop" role="presentation">
      <div className="rz-modal-card" role="dialog" aria-modal="true" aria-labelledby="article-groups-feedback-title">
        <h3 id="article-groups-feedback-title" className="rz-modal-title">{title}</h3>
        <p className="rz-modal-text">{message}</p>
        <div className="rz-modal-actions">
          <Button type="button" onClick={onClose}>OK</Button>
        </div>
      </div>
    </div>
  )
}

function ArticleGroupModal({ open, form, onChange, onClose, onSubmit, busy }) {
  if (!open) return null
  return (
    <div className="rz-modal-backdrop" role="presentation">
      <div className="rz-modal-card" role="dialog" aria-modal="true" aria-labelledby="article-group-modal-title">
        <h3 id="article-group-modal-title" className="rz-modal-title">Nieuwe Artikelgroep</h3>
        <div style={{ display: 'grid', gap: 16 }}>
          <label className="rz-input-field">
            <div className="rz-label">Artikelgroep naam</div>
            <input className="rz-input" autoFocus value={form.name} onChange={(event) => onChange({ ...form, name: event.target.value })} placeholder="Bijvoorbeeld: Zuivel" />
          </label>
          <label style={{ display: 'flex', alignItems: 'center', gap: 10, color: '#0f172a', fontWeight: 600 }}>
            <input type="checkbox" style={greenCheckboxStyle} checked={Boolean(form.active)} onChange={(event) => onChange({ ...form, active: event.target.checked })} />
            Actief
          </label>
        </div>
        <div className="rz-modal-actions">
          <Button type="button" variant="secondary" onClick={onClose} disabled={busy}>Annuleren</Button>
          <Button type="button" onClick={onSubmit} disabled={busy}>{busy ? 'Opslaan…' : 'Opslaan'}</Button>
        </div>
      </div>
    </div>
  )
}

function ActionModal({ open, title, noun, selectedCount, onClose, onDelete, onArchive, busy }) {
  if (!open) return null
  return (
    <div className="rz-modal-backdrop" role="presentation">
      <div className="rz-modal-card" role="dialog" aria-modal="true" aria-labelledby="article-group-action-modal-title">
        <h3 id="article-group-action-modal-title" className="rz-modal-title">{title}</h3>
        <p className="rz-modal-text">Je hebt {selectedCount} {noun}{selectedCount === 1 ? '' : 'en'} geselecteerd. Kies wat je wilt doen.</p>
        <div className="rz-modal-actions">
          <Button type="button" variant="secondary" onClick={onClose} disabled={busy}>Annuleren</Button>
          <Button type="button" variant="secondary" onClick={onArchive} disabled={busy}>{busy ? 'Bezig…' : 'Archiveren'}</Button>
          <Button type="button" onClick={onDelete} disabled={busy}>{busy ? 'Bezig…' : 'Verwijderen'}</Button>
        </div>
      </div>
    </div>
  )
}

function BulkAssignArticleGroupModal({ open, selectedCount, groups, value, onChange, onClose, onApply, busy }) {
  if (!open) return null
  return (
    <div className="rz-modal-backdrop" role="presentation">
      <div className="rz-modal-card" role="dialog" aria-modal="true" aria-labelledby="article-group-bulk-assign-title">
        <h3 id="article-group-bulk-assign-title" className="rz-modal-title">Toewijzen aan artikelgroep</h3>
        <p className="rz-modal-text">Je wijst {selectedCount} geselecteerde voorraadartikel{selectedCount === 1 ? '' : 'en'} toe aan één Artikelgroep.</p>
        <label className="rz-input-field">
          <div className="rz-label">Artikelgroep</div>
          <select className="rz-input" autoFocus value={value} onChange={(event) => onChange(event.target.value)}>
            <option value="">{UNASSIGNED_LABEL}</option>
            {groups.map((group) => <option key={group.id} value={group.id}>{group.name}</option>)}
          </select>
        </label>
        <div className="rz-modal-actions">
          <Button type="button" variant="secondary" onClick={onClose} disabled={busy}>Annuleren</Button>
          <Button type="button" onClick={onApply} disabled={busy}>{busy ? 'Toewijzen…' : 'Toewijzen'}</Button>
        </div>
      </div>
    </div>
  )
}

function PendingChangesModal({ open, onSave, onDiscard, onCancel, busy }) {
  if (!open) return null
  return (
    <div className="rz-modal-backdrop" role="presentation">
      <div className="rz-modal-card" role="dialog" aria-modal="true" aria-labelledby="article-group-pending-modal-title">
        <h3 id="article-group-pending-modal-title" className="rz-modal-title">Wijzigingen bewaren?</h3>
        <p className="rz-modal-text">Er zijn nog niet-opgeslagen wijzigingen in Artikelgroepen en/of artikelkoppelingen. Kies of je deze wilt opslaan of annuleren.</p>
        <div className="rz-modal-actions">
          <Button type="button" variant="secondary" onClick={onCancel} disabled={busy}>Terug naar scherm</Button>
          <Button type="button" variant="secondary" onClick={onDiscard} disabled={busy}>Wijzigingen annuleren</Button>
          <Button type="button" onClick={onSave} disabled={busy}>{busy ? 'Opslaan…' : 'Wijzigingen opslaan'}</Button>
        </div>
      </div>
    </div>
  )
}

function groupDraftMapFromItems(items) {
  return Object.fromEntries(items.map((item) => [String(item.id), { name: String(item.name || ''), active: String(item.status || 'active') !== 'inactive' }]))
}

function articleDraftMapFromItems(items) {
  return Object.fromEntries(items.map((item) => [String(item.id), { article_group_id: item.article_group_id ? String(item.article_group_id) : '' }]))
}

function countArticlesByGroup(items) {
  return items.reduce((counts, item) => {
    const key = item.article_group_id ? String(item.article_group_id) : ''
    counts[key] = (counts[key] || 0) + 1
    return counts
  }, {})
}

function csvEscape(value) {
  const text = String(value ?? '')
  if (!text.includes(',') && !text.includes('"') && !text.includes('\n')) return text
  return `"${text.replace(/"/g, '""')}"`
}

export default function SettingsArticleGroupsPage() {
  const householdId = useMemo(() => getActiveHouseholdId(), [])
  const [groups, setGroups] = useState([])
  const [articles, setArticles] = useState([])
  const [groupDrafts, setGroupDrafts] = useState({})
  const [articleDrafts, setArticleDrafts] = useState({})
  const [isLoading, setIsLoading] = useState(true)
  const [isSaving, setIsSaving] = useState(false)
  const [message, setMessage] = useState('')
  const [error, setError] = useState('')
  const [groupModalOpen, setGroupModalOpen] = useState(false)
  const [groupForm, setGroupForm] = useState(initialGroupForm)
  const [groupFilters, setGroupFilters] = useState(initialGroupFilters)
  const [articleFilters, setArticleFilters] = useState(initialArticleFilters)
  const [selectedGroupIds, setSelectedGroupIds] = useState([])
  const [selectedArticleIds, setSelectedArticleIds] = useState([])
  const [selectedGroupId, setSelectedGroupId] = useState('')
  const [showGroupActionModal, setShowGroupActionModal] = useState(false)
  const [showArticleActionModal, setShowArticleActionModal] = useState(false)
  const [showAssignArticleGroupModal, setShowAssignArticleGroupModal] = useState(false)
  const [bulkAssignGroupId, setBulkAssignGroupId] = useState('')
  const [showPendingModal, setShowPendingModal] = useState(false)
  const pendingNavigationRef = useRef(null)
  const { widths: groupColumnWidths, startResize: startGroupResize } = useResizableColumnWidths(groupColumnDefaults)
  const { widths: articleColumnWidths, startResize: startArticleResize } = useResizableColumnWidths(articleColumnDefaults)

  async function loadData() {
    setIsLoading(true)
    setError('')
    try {
      const [groupsData, articlesData] = await Promise.all([
        requestJson(`/api/article-groups?household_id=${encodeURIComponent(householdId)}`),
        requestJson(`/api/article-groups/household-articles?household_id=${encodeURIComponent(householdId)}`),
      ])
      const nextGroups = Array.isArray(groupsData?.items) ? groupsData.items : []
      const nextArticles = Array.isArray(articlesData?.items) ? articlesData.items : []
      setGroups(nextGroups)
      setArticles(nextArticles)
      setGroupDrafts(groupDraftMapFromItems(nextGroups))
      setArticleDrafts(articleDraftMapFromItems(nextArticles))
      setSelectedGroupId((current) => {
        if (current && nextGroups.some((item) => String(item.id) === String(current))) return current
        const first = [...nextGroups].sort((a, b) => String(a?.name || '').localeCompare(String(b?.name || ''), 'nl'))[0]
        return first ? String(first.id) : ''
      })
    } catch (loadError) {
      setError(loadError?.message || 'Artikelgroepen konden niet worden geladen')
    } finally {
      setIsLoading(false)
    }
  }

  useEffect(() => {
    loadData()
  }, [])

  const sortedGroups = useMemo(() => [...groups].sort((a, b) => String(a?.name || '').localeCompare(String(b?.name || ''), 'nl')), [groups])
  const groupArticleCounts = useMemo(() => countArticlesByGroup(articles), [articles])
  const selectedGroup = useMemo(() => sortedGroups.find((item) => String(item.id) === String(selectedGroupId)) || null, [sortedGroups, selectedGroupId])

  const groupDirtyCount = useMemo(() => groups.reduce((count, item) => {
    const draft = groupDrafts[String(item.id)]
    if (!draft) return count
    if (String(draft.name || '').trim() !== String(item.name || '').trim()) return count + 1
    if (Boolean(draft.active) !== (String(item.status || 'active') !== 'inactive')) return count + 1
    return count
  }, 0), [groups, groupDrafts])

  const articleDirtyCount = useMemo(() => articles.reduce((count, item) => {
    const draft = articleDrafts[String(item.id)]
    if (!draft) return count
    if (String(draft.article_group_id || '') !== String(item.article_group_id || '')) return count + 1
    return count
  }, 0), [articles, articleDrafts])

  const hasPendingChanges = groupDirtyCount > 0 || articleDirtyCount > 0

  useEffect(() => {
    const handleBeforeUnload = (event) => {
      if (!hasPendingChanges) return undefined
      event.preventDefault()
      event.returnValue = ''
      return ''
    }
    window.addEventListener('beforeunload', handleBeforeUnload)
    return () => window.removeEventListener('beforeunload', handleBeforeUnload)
  }, [hasPendingChanges])

  useEffect(() => {
    const handleDocumentClick = (event) => {
      if (!hasPendingChanges) return
      const anchor = event.target instanceof Element ? event.target.closest('a[href]') : null
      if (!anchor) return
      const href = anchor.getAttribute('href')
      if (!href || href.startsWith('#') || href.startsWith('javascript:')) return
      if (anchor.target === '_blank' || event.metaKey || event.ctrlKey || event.shiftKey || event.altKey) return
      const next = new URL(anchor.href, window.location.origin)
      const current = new URL(window.location.href)
      if (next.pathname === current.pathname && next.search === current.search && next.hash === current.hash) return
      event.preventDefault()
      pendingNavigationRef.current = () => { window.location.href = next.href }
      setShowPendingModal(true)
    }
    document.addEventListener('click', handleDocumentClick, true)
    return () => document.removeEventListener('click', handleDocumentClick, true)
  }, [hasPendingChanges])

  const filteredGroups = useMemo(() => sortedGroups.filter((item) => {
    const draft = groupDrafts[String(item.id)] || { name: item.name, active: String(item.status || 'active') !== 'inactive' }
    const nameOk = !groupFilters.name || String(draft?.name || '').toLowerCase().includes(groupFilters.name.toLowerCase())
    const activeOk = !groupFilters.active || Boolean(draft?.active)
    const countOk = !groupFilters.articles || String(Number(groupArticleCounts[String(item.id)] || 0)).includes(groupFilters.articles)
    return nameOk && activeOk && countOk
  }), [sortedGroups, groupFilters, groupDrafts, groupArticleCounts])

  const visibleArticles = useMemo(() => {
    if (!selectedGroupId) return articles
    return articles.filter((item) => String(item.article_group_id || '') === String(selectedGroupId || ''))
  }, [articles, selectedGroupId])

  const filteredArticles = useMemo(() => {
    return [...visibleArticles]
      .sort((a, b) => String(a?.article_name || '').localeCompare(String(b?.article_name || ''), 'nl'))
      .filter((item) => {
        const draft = articleDrafts[String(item.id)] || { article_group_id: item.article_group_id || '' }
        const groupName = draft.article_group_id ? (groups.find((group) => String(group.id) === String(draft.article_group_id))?.name || '') : UNASSIGNED_LABEL
        const articleOk = !articleFilters.article || String(item?.article_name || '').toLowerCase().includes(articleFilters.article.toLowerCase())
        const groupOk = !articleFilters.group || String(groupName || '').toLowerCase().includes(articleFilters.group.toLowerCase())
        return articleOk && groupOk
      })
  }, [visibleArticles, articleFilters, articleDrafts, groups])

  const allFilteredGroupsSelected = filteredGroups.length > 0 && filteredGroups.every((item) => selectedGroupIds.includes(String(item.id)))
  const allFilteredArticlesSelected = filteredArticles.length > 0 && filteredArticles.every((item) => selectedArticleIds.includes(String(item.id)))

  function toggleSelectedGroup(id) {
    const key = String(id)
    setSelectedGroupIds((current) => current.includes(key) ? current.filter((value) => value !== key) : [...current, key])
  }

  function toggleSelectedArticle(id) {
    const key = String(id)
    setSelectedArticleIds((current) => current.includes(key) ? current.filter((value) => value !== key) : [...current, key])
  }

  function toggleAllFilteredGroups() {
    if (allFilteredGroupsSelected) {
      const filteredSet = new Set(filteredGroups.map((item) => String(item.id)))
      setSelectedGroupIds((current) => current.filter((id) => !filteredSet.has(id)))
      return
    }
    const merged = new Set(selectedGroupIds)
    filteredGroups.forEach((item) => merged.add(String(item.id)))
    setSelectedGroupIds(Array.from(merged))
  }

  function toggleAllFilteredArticles() {
    if (allFilteredArticlesSelected) {
      const filteredSet = new Set(filteredArticles.map((item) => String(item.id)))
      setSelectedArticleIds((current) => current.filter((id) => !filteredSet.has(id)))
      return
    }
    const merged = new Set(selectedArticleIds)
    filteredArticles.forEach((item) => merged.add(String(item.id)))
    setSelectedArticleIds(Array.from(merged))
  }

  function openCreateGroup() {
    setMessage('')
    setError('')
    setGroupForm(initialGroupForm)
    setGroupModalOpen(true)
  }

  function openBulkAssignArticleGroup() {
    if (!selectedArticleIds.length) return
    setMessage('')
    setError('')
    const preferredGroupId = selectedGroupId && sortedGroups.some((group) => String(group.id) === String(selectedGroupId)) ? String(selectedGroupId) : ''
    setBulkAssignGroupId(preferredGroupId)
    setShowAssignArticleGroupModal(true)
  }

  function applyBulkAssignArticleGroup() {
    if (!selectedArticleIds.length) return
    selectedArticleIds.forEach((id) => updateArticleDraft(id, { article_group_id: bulkAssignGroupId || '' }))
    const groupName = bulkAssignGroupId ? (sortedGroups.find((group) => String(group.id) === String(bulkAssignGroupId))?.name || 'gekozen Artikelgroep') : UNASSIGNED_LABEL
    setShowAssignArticleGroupModal(false)
    setMessage(`${selectedArticleIds.length} voorraadartikel${selectedArticleIds.length === 1 ? '' : 'en'} klaargezet voor Artikelgroep ${groupName}. Kies Wijzigingen opslaan om te bewaren.`)
  }

  function updateGroupDraft(id, patch) {
    const key = String(id)
    setGroupDrafts((current) => ({ ...current, [key]: { ...(current[key] || {}), ...patch } }))
  }

  function updateArticleDraft(id, patch) {
    const key = String(id)
    setArticleDrafts((current) => ({ ...current, [key]: { ...(current[key] || {}), ...patch } }))
  }

  function discardPendingChanges() {
    setGroupDrafts(groupDraftMapFromItems(groups))
    setArticleDrafts(articleDraftMapFromItems(articles))
    setMessage('Wijzigingen geannuleerd.')
    setError('')
  }

  async function savePendingChanges() {
    const changedGroups = groups.filter((item) => {
      const draft = groupDrafts[String(item.id)]
      return draft && (String(draft.name || '').trim() !== String(item.name || '').trim() || Boolean(draft.active) !== (String(item.status || 'active') !== 'inactive'))
    })
    const changedArticles = articles.filter((item) => {
      const draft = articleDrafts[String(item.id)]
      return draft && String(draft.article_group_id || '') !== String(item.article_group_id || '')
    })

    for (const item of changedGroups) {
      const draft = groupDrafts[String(item.id)]
      if (!String(draft?.name || '').trim()) {
        setError('Elke Artikelgroep moet een naam hebben voordat je opslaat.')
        return false
      }
    }

    if (!changedGroups.length && !changedArticles.length) {
      setShowPendingModal(false)
      return true
    }

    setIsSaving(true)
    setError('')
    setMessage('')
    try {
      for (const item of changedGroups) {
        const draft = groupDrafts[String(item.id)]
        await requestJson(`/api/article-groups/${encodeURIComponent(item.id)}`, {
          method: 'PUT',
          body: JSON.stringify({ household_id: householdId, name: String(draft.name || '').trim(), status: draft.active ? 'active' : 'inactive' }),
        })
      }
      for (const item of changedArticles) {
        const draft = articleDrafts[String(item.id)]
        await requestJson(`/api/household-articles/${encodeURIComponent(item.id)}/article-group`, {
          method: 'PUT',
          body: JSON.stringify({ household_id: householdId, article_group_id: draft.article_group_id || null }),
        })
      }
      await loadData()
      setSelectedArticleIds([])
      setMessage(`${changedGroups.length + changedArticles.length} wijziging${changedGroups.length + changedArticles.length === 1 ? '' : 'en'} opgeslagen.`)
      setShowPendingModal(false)
      return true
    } catch (saveError) {
      setError(saveError?.message || 'Wijzigingen opslaan mislukt.')
      return false
    } finally {
      setIsSaving(false)
    }
  }

  async function handleSaveGroup() {
    const name = String(groupForm.name || '').trim()
    if (!name) {
      setError('Artikelgroepnaam is verplicht.')
      return
    }
    setIsSaving(true)
    setError('')
    setMessage('')
    try {
      await requestJson('/api/article-groups', { method: 'POST', body: JSON.stringify({ household_id: householdId, name }) })
      setMessage('Artikelgroep opgeslagen.')
      setGroupModalOpen(false)
      await loadData()
    } catch (saveError) {
      setError(saveError?.message || 'Artikelgroep opslaan mislukt.')
    } finally {
      setIsSaving(false)
    }
  }

  async function deleteSelectedGroups() {
    const selectedItems = groups.filter((item) => selectedGroupIds.includes(String(item.id)))
    if (!selectedItems.length) return
    setIsSaving(true)
    setError('')
    setMessage('')
    let deletedCount = 0
    let deactivatedCount = 0
    const blocked = []
    try {
      for (const item of selectedItems) {
        try {
          const result = await requestJson(`/api/article-groups/${encodeURIComponent(item.id)}?household_id=${encodeURIComponent(householdId)}`, { method: 'DELETE' })
          if (result?.deactivated) deactivatedCount += 1
          else if (result?.deleted) deletedCount += 1
          else blocked.push(item.name)
        } catch {
          blocked.push(item.name)
        }
      }
      await loadData()
      setSelectedGroupIds([])
      const parts = []
      if (deletedCount) parts.push(`${deletedCount} Artikelgroep${deletedCount === 1 ? '' : 'en'} verwijderd`)
      if (deactivatedCount) parts.push(`${deactivatedCount} Artikelgroep${deactivatedCount === 1 ? '' : 'en'} gearchiveerd omdat deze in gebruik was`)
      if (blocked.length) parts.push(`${blocked.length} Artikelgroep${blocked.length === 1 ? '' : 'en'} niet verwerkt`)
      if (parts.length) setMessage(`${parts.join('. ')}.`)
      else setError('Geen Artikelgroepen verwijderd.')
    } finally {
      setIsSaving(false)
      setShowGroupActionModal(false)
    }
  }

  async function archiveSelectedGroups() {
    const selectedItems = groups.filter((item) => selectedGroupIds.includes(String(item.id)))
    if (!selectedItems.length) return
    setIsSaving(true)
    setError('')
    setMessage('')
    let archivedCount = 0
    try {
      for (const item of selectedItems) {
        const draft = groupDrafts[String(item.id)] || item
        await requestJson(`/api/article-groups/${encodeURIComponent(item.id)}`, {
          method: 'PUT',
          body: JSON.stringify({ household_id: householdId, name: String(draft.name || item.name || '').trim(), status: 'inactive' }),
        })
        archivedCount += 1
      }
      await loadData()
      setSelectedGroupIds([])
      setMessage(`${archivedCount} Artikelgroep${archivedCount === 1 ? '' : 'en'} gearchiveerd.`)
    } catch (archiveError) {
      setError(archiveError?.message || 'Artikelgroepen archiveren mislukt.')
    } finally {
      setIsSaving(false)
      setShowGroupActionModal(false)
    }
  }

  function clearSelectedArticleGroups() {
    if (!selectedArticleIds.length) return
    selectedArticleIds.forEach((id) => updateArticleDraft(id, { article_group_id: '' }))
    setShowArticleActionModal(false)
    setMessage(`${selectedArticleIds.length} artikel${selectedArticleIds.length === 1 ? '' : 'en'} klaargezet als ${UNASSIGNED_LABEL}. Kies Wijzigingen opslaan om te bewaren.`)
  }

  function archiveSelectedArticlesNoop() {
    setShowArticleActionModal(false)
    clearSelectedArticleGroups()
  }

  function exportGroupsCsv() {
    const rows = [['Artikelgroep', 'Actief', 'Aantal artikelen'], ...filteredGroups.map((item) => {
      const draft = groupDrafts[String(item.id)] || { name: item.name, active: String(item.status || 'active') !== 'inactive' }
      return [draft.name, draft.active ? 'Ja' : 'Nee', Number(groupArticleCounts[String(item.id)] || 0)]
    })]
    const csv = rows.map((row) => row.map(csvEscape).join(',')).join('\n')
    const blob = new Blob([csv], { type: 'text/csv;charset=utf-8' })
    const url = URL.createObjectURL(blob)
    const anchor = document.createElement('a')
    anchor.href = url
    anchor.download = 'rezzerv-artikelgroepen.csv'
    document.body.appendChild(anchor)
    anchor.click()
    anchor.remove()
    URL.revokeObjectURL(url)
  }

  function exportArticleLinksCsv() {
    const rows = [['Artikel', 'Artikelgroep'], ...filteredArticles.map((item) => {
      const draft = articleDrafts[String(item.id)] || { article_group_id: item.article_group_id || '' }
      const groupName = draft.article_group_id ? (groups.find((group) => String(group.id) === String(draft.article_group_id))?.name || '') : UNASSIGNED_LABEL
      return [item.article_name || 'Onbekend artikel', groupName]
    })]
    const csv = rows.map((row) => row.map(csvEscape).join(',')).join('\n')
    const blob = new Blob([csv], { type: 'text/csv;charset=utf-8' })
    const url = URL.createObjectURL(blob)
    const anchor = document.createElement('a')
    anchor.href = url
    anchor.download = 'rezzerv-artikelgroep-koppelingen.csv'
    document.body.appendChild(anchor)
    anchor.click()
    anchor.remove()
    URL.revokeObjectURL(url)
  }

  async function confirmSaveAndContinue() {
    const ok = await savePendingChanges()
    if (!ok) return
    if (pendingNavigationRef.current) {
      const navigate = pendingNavigationRef.current
      pendingNavigationRef.current = null
      navigate()
    }
  }

  function confirmDiscardAndContinue() {
    discardPendingChanges()
    setShowPendingModal(false)
    if (pendingNavigationRef.current) {
      const navigate = pendingNavigationRef.current
      pendingNavigationRef.current = null
      navigate()
    }
  }

  function cancelPendingDialog() {
    pendingNavigationRef.current = null
    setShowPendingModal(false)
  }

  const groupTableWidth = buildTableWidth(groupColumnWidths)
  const articleTableWidth = buildTableWidth(articleColumnWidths)

  return (
    <AppShell title="Artikelgroepen" showExit={false}>
      <Card className="rz-settings-spaces-card">
        <div style={{ display: 'grid', gap: 24, width: '100%' }} data-testid="settings-article-groups-page">
          <div>
            <h2 style={{ margin: 0, fontSize: 20 }}>Beheer Artikelgroepen</h2>
          </div>

          <section style={{ display: 'grid', gap: 18 }}>
            <div style={{ fontWeight: 700, color: '#0f172a' }}>Artikelgroepen</div>
            <Table wrapperClassName="rz-stock-table-wrapper" tableClassName="rz-stock-table" tableStyle={{ tableLayout: 'fixed', width: groupTableWidth, minWidth: groupTableWidth }}>
              <colgroup>
                <col style={{ width: `${groupColumnWidths.select}px` }} />
                <col style={{ width: `${groupColumnWidths.name}px` }} />
                <col style={{ width: `${groupColumnWidths.active}px` }} />
                <col style={{ width: `${groupColumnWidths.articles}px` }} />
              </colgroup>
              <thead>
                <tr className="rz-table-header">
                  <ResizableHeaderCell columnKey="select" widths={groupColumnWidths} onStartResize={startGroupResize}>
                    <input type="checkbox" style={greenCheckboxStyle} checked={allFilteredGroupsSelected} onChange={toggleAllFilteredGroups} aria-label="Selecteer alle zichtbare Artikelgroepen" />
                  </ResizableHeaderCell>
                  <ResizableHeaderCell columnKey="name" widths={groupColumnWidths} onStartResize={startGroupResize}>Artikelgroep</ResizableHeaderCell>
                  <ResizableHeaderCell columnKey="active" widths={groupColumnWidths} onStartResize={startGroupResize} className="rz-num">Actief</ResizableHeaderCell>
                  <ResizableHeaderCell columnKey="articles" widths={groupColumnWidths} onStartResize={startGroupResize} className="rz-num">Aantal artikelen</ResizableHeaderCell>
                </tr>
                <tr className="rz-table-filters">
                  <th />
                  <th><input className="rz-input rz-inline-input" value={groupFilters.name} onChange={(event) => setGroupFilters((current) => ({ ...current, name: event.target.value }))} placeholder="Filter" aria-label="Filter op Artikelgroep" /></th>
                  <th className="rz-num">
                    <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'flex-end', minHeight: 20, width: '100%' }}>
                      <input type="checkbox" className="rz-filter-checkbox" style={greenCheckboxStyle} checked={groupFilters.active} onChange={(event) => setGroupFilters((current) => ({ ...current, active: event.target.checked }))} aria-label="Filter actieve Artikelgroepen" title="Alleen actieve Artikelgroepen tonen" />
                    </div>
                  </th>
                  <th><input className="rz-input rz-inline-input" value={groupFilters.articles} onChange={(event) => setGroupFilters((current) => ({ ...current, articles: event.target.value }))} placeholder="Filter" aria-label="Filter op aantal artikelen" /></th>
                </tr>
              </thead>
              <tbody>
                {isLoading ? (
                  <tr><td colSpan={4}>Artikelgroepen laden…</td></tr>
                ) : filteredGroups.length === 0 ? (
                  <tr><td colSpan={4}>Nog geen Artikelgroepen. Artikelen zonder groep worden getoond als “{UNASSIGNED_LABEL}”.</td></tr>
                ) : filteredGroups.map((item) => {
                  const selected = selectedGroupIds.includes(String(item.id))
                  const detailSelected = String(selectedGroupId) === String(item.id)
                  const draft = groupDrafts[String(item.id)] || { name: item.name, active: String(item.status || 'active') !== 'inactive' }
                  return (
                    <tr key={item.id} className={selected || detailSelected ? 'rz-row-selected' : ''} onDoubleClick={() => setSelectedGroupId(String(item.id))} title="Dubbelklik om artikelen van deze Artikelgroep te tonen">
                      <td><input type="checkbox" style={greenCheckboxStyle} checked={selected} onChange={() => toggleSelectedGroup(item.id)} aria-label={`Selecteer ${item.name}`} /></td>
                      <td><input className="rz-input rz-inline-input" value={draft.name} onChange={(event) => updateGroupDraft(item.id, { name: event.target.value })} aria-label={`Artikelgroepnaam ${item.name}`} /></td>
                      <td className="rz-num"><input type="checkbox" style={greenCheckboxStyle} checked={Boolean(draft.active)} onChange={(event) => updateGroupDraft(item.id, { active: event.target.checked })} aria-label={`Actief ${item.name}`} /></td>
                      <td className="rz-num">{Number(groupArticleCounts[String(item.id)] || 0)}</td>
                    </tr>
                  )
                })}
              </tbody>
            </Table>
            <div className="rz-stock-table-actions" style={{ justifyContent: 'flex-end', gap: 12, flexWrap: 'wrap' }}>
              <Button type="button" variant="secondary" onClick={exportGroupsCsv} disabled={isLoading || selectedGroupIds.length === 0 || isSaving}>Exporteren</Button>
              <Button type="button" variant="secondary" onClick={() => setShowGroupActionModal(true)} disabled={isSaving || selectedGroupIds.length === 0}>Verwijderen</Button>
              <Button type="button" onClick={openCreateGroup} disabled={isSaving}>Toevoegen Artikelgroep</Button>
            </div>
          </section>

          <section style={{ display: 'grid', gap: 18 }}>
            <div style={{ fontWeight: 700, color: '#0f172a' }}>Voorraadartikelen{selectedGroup ? ` van ${selectedGroup.name}` : ''}</div>
            <p style={{ margin: 0, color: '#667085' }}>Koppelen is handmatig. Barcodeherkenning, externe databases en Uitpakken wijzigen deze koppeling niet.</p>
            <Table wrapperClassName="rz-stock-table-wrapper" tableClassName="rz-stock-table" tableStyle={{ tableLayout: 'fixed', width: articleTableWidth, minWidth: articleTableWidth }}>
              <colgroup>
                <col style={{ width: `${articleColumnWidths.select}px` }} />
                <col style={{ width: `${articleColumnWidths.article}px` }} />
                <col style={{ width: `${articleColumnWidths.group}px` }} />
              </colgroup>
              <thead>
                <tr className="rz-table-header">
                  <ResizableHeaderCell columnKey="select" widths={articleColumnWidths} onStartResize={startArticleResize}>
                    <input type="checkbox" style={greenCheckboxStyle} checked={allFilteredArticlesSelected} onChange={toggleAllFilteredArticles} aria-label="Selecteer alle zichtbare artikelen" />
                  </ResizableHeaderCell>
                  <ResizableHeaderCell columnKey="article" widths={articleColumnWidths} onStartResize={startArticleResize}>Artikel</ResizableHeaderCell>
                  <ResizableHeaderCell columnKey="group" widths={articleColumnWidths} onStartResize={startArticleResize}>Artikelgroep</ResizableHeaderCell>
                </tr>
                <tr className="rz-table-filters">
                  <th />
                  <th><input className="rz-input rz-inline-input" value={articleFilters.article} onChange={(event) => setArticleFilters((current) => ({ ...current, article: event.target.value }))} placeholder="Filter" aria-label="Filter op artikel" /></th>
                  <th><input className="rz-input rz-inline-input" value={articleFilters.group} onChange={(event) => setArticleFilters((current) => ({ ...current, group: event.target.value }))} placeholder="Filter" aria-label="Filter op Artikelgroep" /></th>
                </tr>
              </thead>
              <tbody>
                {isLoading ? (
                  <tr><td colSpan={3}>Voorraadartikelen laden…</td></tr>
                ) : !articles.length ? (
                  <tr><td colSpan={3}>Geen huishoudelijke voorraadartikelen gevonden.</td></tr>
                ) : filteredArticles.length === 0 ? (
                  <tr><td colSpan={3}>Geen voorraadartikelen voor deze selectie.</td></tr>
                ) : filteredArticles.map((item) => {
                  const selected = selectedArticleIds.includes(String(item.id))
                  const draft = articleDrafts[String(item.id)] || { article_group_id: item.article_group_id || '' }
                  return (
                    <tr key={item.id} className={selected ? 'rz-row-selected' : ''}>
                      <td><input type="checkbox" style={greenCheckboxStyle} checked={selected} onChange={() => toggleSelectedArticle(item.id)} aria-label={`Selecteer ${item.article_name || 'Onbekend artikel'}`} /></td>
                      <td>{item.article_name || 'Onbekend artikel'}</td>
                      <td>
                        <select className="rz-input rz-inline-input" value={draft.article_group_id || ''} onChange={(event) => updateArticleDraft(item.id, { article_group_id: event.target.value })} aria-label={`Artikelgroep ${item.article_name || 'Onbekend artikel'}`}>
                          <option value="">{UNASSIGNED_LABEL}</option>
                          {sortedGroups.map((group) => <option key={group.id} value={group.id}>{group.name}</option>)}
                        </select>
                      </td>
                    </tr>
                  )
                })}
              </tbody>
            </Table>
            <div className="rz-stock-table-actions" style={{ justifyContent: 'flex-end', gap: 12, flexWrap: 'wrap' }}>
              <Button type="button" variant="secondary" onClick={exportArticleLinksCsv} disabled={isLoading || selectedArticleIds.length === 0 || isSaving}>Exporteren</Button>
              <Button type="button" variant="secondary" onClick={openBulkAssignArticleGroup} disabled={isLoading || selectedArticleIds.length === 0 || isSaving || sortedGroups.length === 0}>Toewijzen aan artikelgroep</Button>
              <Button type="button" variant="secondary" onClick={() => setShowArticleActionModal(true)} disabled={isSaving || selectedArticleIds.length === 0}>Verwijderen</Button>
            </div>
          </section>

          <div className="rz-stock-table-actions" style={{ justifyContent: 'flex-end', gap: 12, flexWrap: 'wrap' }}>
            <Button type="button" variant="secondary" onClick={() => { discardPendingChanges(); setShowPendingModal(false) }} disabled={isSaving || !hasPendingChanges}>Wijzigingen annuleren</Button>
            <Button type="button" onClick={savePendingChanges} disabled={isSaving || !hasPendingChanges}>{isSaving ? 'Opslaan…' : 'Wijzigingen opslaan'}</Button>
          </div>
        </div>
      </Card>

      <FeedbackOverlay type="error" message={error} onClose={() => setError('')} />
      <FeedbackOverlay type="success" message={message} onClose={() => setMessage('')} />
      <ArticleGroupModal open={groupModalOpen} form={groupForm} onChange={setGroupForm} onClose={() => setGroupModalOpen(false)} onSubmit={handleSaveGroup} busy={isSaving} />
      <ActionModal open={showGroupActionModal} title="Geselecteerde Artikelgroepen verwerken" noun="Artikelgroep" selectedCount={selectedGroupIds.length} onClose={() => setShowGroupActionModal(false)} onDelete={deleteSelectedGroups} onArchive={archiveSelectedGroups} busy={isSaving} />
      <ActionModal open={showArticleActionModal} title="Geselecteerde artikelkoppelingen verwerken" noun="artikel" selectedCount={selectedArticleIds.length} onClose={() => setShowArticleActionModal(false)} onDelete={clearSelectedArticleGroups} onArchive={archiveSelectedArticlesNoop} busy={isSaving} />
      <BulkAssignArticleGroupModal open={showAssignArticleGroupModal} selectedCount={selectedArticleIds.length} groups={sortedGroups} value={bulkAssignGroupId} onChange={setBulkAssignGroupId} onClose={() => setShowAssignArticleGroupModal(false)} onApply={applyBulkAssignArticleGroup} busy={isSaving} />
      <PendingChangesModal open={showPendingModal} onSave={confirmSaveAndContinue} onDiscard={confirmDiscardAndContinue} onCancel={cancelPendingDialog} busy={isSaving} />
    </AppShell>
  )
}
