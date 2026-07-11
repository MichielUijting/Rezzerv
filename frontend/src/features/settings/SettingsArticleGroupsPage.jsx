import { useEffect, useMemo, useState } from 'react'
import AppShell from '../../app/AppShell'
import Card from '../../ui/Card'
import Button from '../../ui/Button'
import { fetchJsonWithAuth, readStoredAuthContext } from '../../lib/authSession'

const UNASSIGNED_LABEL = 'Niet ingedeeld'

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

export default function SettingsArticleGroupsPage() {
  const householdId = useMemo(() => getActiveHouseholdId(), [])
  const [groups, setGroups] = useState([])
  const [articles, setArticles] = useState([])
  const [newName, setNewName] = useState('')
  const [editing, setEditing] = useState({})
  const [isLoading, setIsLoading] = useState(true)
  const [isSaving, setIsSaving] = useState(false)
  const [message, setMessage] = useState('')
  const [error, setError] = useState('')

  async function loadData() {
    setIsLoading(true)
    setError('')
    try {
      const [groupsData, articlesData] = await Promise.all([
        requestJson(`/api/article-groups?household_id=${encodeURIComponent(householdId)}`),
        requestJson(`/api/article-groups/household-articles?household_id=${encodeURIComponent(householdId)}`),
      ])
      setGroups(Array.isArray(groupsData?.items) ? groupsData.items : [])
      setArticles(Array.isArray(articlesData?.items) ? articlesData.items : [])
      setEditing({})
    } catch (loadError) {
      setError(loadError.message || 'Artikelgroepen konden niet worden geladen')
    } finally {
      setIsLoading(false)
    }
  }

  useEffect(() => {
    loadData()
  }, [])

  async function handleCreateGroup(event) {
    event.preventDefault()
    const name = String(newName || '').trim()
    if (!name) {
      setError('Artikelgroepnaam is verplicht')
      return
    }
    setIsSaving(true)
    setError('')
    setMessage('')
    try {
      await requestJson('/api/article-groups', {
        method: 'POST',
        body: JSON.stringify({ household_id: householdId, name }),
      })
      setNewName('')
      setMessage('Artikelgroep toegevoegd')
      await loadData()
    } catch (createError) {
      setError(createError.message || 'Artikelgroep toevoegen mislukt')
    } finally {
      setIsSaving(false)
    }
  }

  async function handleRenameGroup(group) {
    const name = String(editing[group.id] ?? group.name ?? '').trim()
    if (!name) {
      setError('Artikelgroepnaam is verplicht')
      return
    }
    setIsSaving(true)
    setError('')
    setMessage('')
    try {
      await requestJson(`/api/article-groups/${encodeURIComponent(group.id)}`, {
        method: 'PUT',
        body: JSON.stringify({ household_id: householdId, name }),
      })
      setMessage('Artikelgroep bijgewerkt')
      await loadData()
    } catch (renameError) {
      setError(renameError.message || 'Artikelgroep bijwerken mislukt')
    } finally {
      setIsSaving(false)
    }
  }

  async function handleDeleteGroup(group) {
    setIsSaving(true)
    setError('')
    setMessage('')
    try {
      const result = await requestJson(`/api/article-groups/${encodeURIComponent(group.id)}?household_id=${encodeURIComponent(householdId)}`, {
        method: 'DELETE',
      })
      setMessage(result?.deactivated ? 'Artikelgroep was in gebruik en is gedeactiveerd' : 'Artikelgroep verwijderd')
      await loadData()
    } catch (deleteError) {
      setError(deleteError.message || 'Artikelgroep verwijderen mislukt')
    } finally {
      setIsSaving(false)
    }
  }

  async function handleAssignArticle(article, groupId) {
    setIsSaving(true)
    setError('')
    setMessage('')
    try {
      await requestJson(`/api/household-articles/${encodeURIComponent(article.id)}/article-group`, {
        method: 'PUT',
        body: JSON.stringify({ household_id: householdId, article_group_id: groupId || null }),
      })
      setMessage('Artikelgroepkoppeling bijgewerkt')
      await loadData()
    } catch (assignError) {
      setError(assignError.message || 'Artikelgroep koppelen mislukt')
    } finally {
      setIsSaving(false)
    }
  }

  return (
    <AppShell title="Instellingen" showExit={false}>
      <Card>
        <div style={{ display: 'grid', gap: '22px' }} data-testid="settings-article-groups-page">
          <div>
            <h2 style={{ margin: '0 0 8px 0', fontSize: '20px' }}>Artikelgroepen</h2>
            <p style={{ margin: 0, color: '#667085' }}>Beheer je eigen indeling van voorraadartikelen. Rezzerv maakt geen groepen automatisch aan.</p>
          </div>

          {error ? <div className="rz-inline-feedback rz-inline-feedback--error">{error}</div> : null}
          {message ? <div className="rz-inline-feedback rz-inline-feedback--success">{message}</div> : null}

          <form onSubmit={handleCreateGroup} style={{ display: 'flex', gap: '12px', flexWrap: 'wrap', alignItems: 'center' }}>
            <input
              className="rz-input"
              value={newName}
              placeholder="Nieuwe artikelgroep"
              onChange={(event) => setNewName(event.target.value)}
              disabled={isSaving}
              style={{ minWidth: '260px' }}
            />
            <Button type="submit" disabled={isSaving}>Toevoegen</Button>
          </form>

          <section style={{ display: 'grid', gap: '12px' }}>
            <h3 style={{ margin: 0, fontSize: '16px' }}>Groepen</h3>
            {isLoading ? <div>Artikelgroepen laden…</div> : null}
            {!isLoading && !groups.length ? <div className="rz-empty-state">Nog geen Artikelgroepen. Artikelen zonder groep worden getoond als “{UNASSIGNED_LABEL}”.</div> : null}
            {groups.map((group) => (
              <div key={group.id} style={{ display: 'flex', gap: '12px', alignItems: 'center', flexWrap: 'wrap' }}>
                <input
                  className="rz-input"
                  value={editing[group.id] ?? group.name ?? ''}
                  onChange={(event) => setEditing((current) => ({ ...current, [group.id]: event.target.value }))}
                  disabled={isSaving}
                  style={{ minWidth: '260px' }}
                />
                <Button variant="secondary" onClick={() => handleRenameGroup(group)} disabled={isSaving}>Opslaan</Button>
                <Button variant="secondary" onClick={() => handleDeleteGroup(group)} disabled={isSaving}>Verwijderen</Button>
              </div>
            ))}
          </section>

          <section style={{ display: 'grid', gap: '12px' }}>
            <h3 style={{ margin: 0, fontSize: '16px' }}>Voorraadartikelen koppelen</h3>
            <p style={{ margin: 0, color: '#667085' }}>Koppelen is handmatig. Barcodeherkenning, externe databases en Uitpakken wijzigen deze koppeling niet.</p>
            {!isLoading && !articles.length ? <div className="rz-empty-state">Geen huishoudelijke voorraadartikelen gevonden.</div> : null}
            {articles.length ? (
              <table className="rz-table" style={{ width: '100%' }}>
                <thead>
                  <tr>
                    <th>Artikel</th>
                    <th>Artikelgroep</th>
                  </tr>
                </thead>
                <tbody>
                  {articles.map((article) => (
                    <tr key={article.id}>
                      <td>{article.article_name || 'Onbekend artikel'}</td>
                      <td>
                        <select
                          className="rz-input"
                          value={article.article_group_id || ''}
                          disabled={isSaving}
                          onChange={(event) => handleAssignArticle(article, event.target.value || null)}
                        >
                          <option value="">{UNASSIGNED_LABEL}</option>
                          {groups.map((group) => <option key={group.id} value={group.id}>{group.name}</option>)}
                        </select>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            ) : null}
          </section>
        </div>
      </Card>
    </AppShell>
  )
}
