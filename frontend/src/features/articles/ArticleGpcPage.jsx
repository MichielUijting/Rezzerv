import { useEffect, useMemo, useState } from 'react'
import { useNavigate, useParams } from 'react-router-dom'

import AppShell from '../../app/AppShell'
import ScreenCard from '../../ui/ScreenCard'
import { fetchJsonWithAuth, readStoredAuthContext } from '../../lib/authSession'

function hierarchyLabel(item) {
  return [
    item?.segment_description,
    item?.family_description,
    item?.class_description,
  ].filter(Boolean).join(' › ')
}

export default function ArticleGpcPage() {
  const { articleId = '' } = useParams()
  const navigate = useNavigate()
  const authContext = readStoredAuthContext() || {}
  const role = String(authContext?.display_role || '').trim().toLowerCase()
  const canEdit = role === 'admin' || role === 'lid'

  const [query, setQuery] = useState('')
  const [results, setResults] = useState([])
  const [assignment, setAssignment] = useState(null)
  const [loading, setLoading] = useState(true)
  const [searching, setSearching] = useState(false)
  const [saving, setSaving] = useState(false)
  const [message, setMessage] = useState('')
  const [error, setError] = useState('')

  const trimmedArticleId = useMemo(() => String(articleId || '').trim(), [articleId])

  async function loadAssignment() {
    if (!trimmedArticleId) return
    const response = await fetchJsonWithAuth(`/api/household-articles/${encodeURIComponent(trimmedArticleId)}/gpc-brick`)
    const data = await response.json().catch(() => ({}))
    if (!response.ok) throw new Error(data?.detail || 'GPC-classificatie kon niet worden geladen.')
    setAssignment(data?.assignment || null)
  }

  async function searchBricks(searchQuery = query) {
    setSearching(true)
    setError('')
    try {
      const params = new URLSearchParams({ query: String(searchQuery || '').trim(), limit: '40' })
      const response = await fetchJsonWithAuth(`/api/gpc/bricks?${params.toString()}`)
      const data = await response.json().catch(() => ({}))
      if (!response.ok) throw new Error(data?.detail || 'GPC Bricks konden niet worden gezocht.')
      setResults(Array.isArray(data?.items) ? data.items : [])
    } catch (nextError) {
      setResults([])
      setError(nextError?.message || 'GPC Bricks konden niet worden gezocht.')
    } finally {
      setSearching(false)
    }
  }

  useEffect(() => {
    let cancelled = false
    setLoading(true)
    setError('')
    Promise.all([loadAssignment(), searchBricks('')])
      .catch((nextError) => {
        if (!cancelled) setError(nextError?.message || 'GPC-gegevens konden niet worden geladen.')
      })
      .finally(() => {
        if (!cancelled) setLoading(false)
      })
    return () => { cancelled = true }
  }, [trimmedArticleId])

  useEffect(() => {
    const timer = window.setTimeout(() => searchBricks(query), 300)
    return () => window.clearTimeout(timer)
  }, [query])

  async function selectBrick(item) {
    if (!canEdit || !item?.brick_code) return
    setSaving(true)
    setMessage('')
    setError('')
    try {
      const response = await fetchJsonWithAuth(`/api/household-articles/${encodeURIComponent(trimmedArticleId)}/gpc-brick`, {
        method: 'PUT',
        body: JSON.stringify({ brick_code: item.brick_code }),
      })
      const data = await response.json().catch(() => ({}))
      if (!response.ok) throw new Error(data?.detail || 'GPC Brick kon niet worden opgeslagen.')
      setAssignment(data?.assignment || item)
      setMessage('GPC-classificatie opgeslagen.')
    } catch (nextError) {
      setError(nextError?.message || 'GPC Brick kon niet worden opgeslagen.')
    } finally {
      setSaving(false)
    }
  }

  async function clearAssignment() {
    if (!canEdit || !assignment) return
    setSaving(true)
    setMessage('')
    setError('')
    try {
      const response = await fetchJsonWithAuth(`/api/household-articles/${encodeURIComponent(trimmedArticleId)}/gpc-brick`, {
        method: 'DELETE',
      })
      const data = await response.json().catch(() => ({}))
      if (!response.ok) throw new Error(data?.detail || 'GPC-classificatie kon niet worden verwijderd.')
      setAssignment(null)
      setMessage('GPC-classificatie verwijderd.')
    } catch (nextError) {
      setError(nextError?.message || 'GPC-classificatie kon niet worden verwijderd.')
    } finally {
      setSaving(false)
    }
  }

  return (
    <AppShell title="GS1 GPC-classificatie" showExit={false}>
      <ScreenCard fullWidth>
        <div className="rz-article-detail-page" data-testid="article-gpc-page" style={{ display: 'grid', gap: 16 }}>
          <div>
            <button type="button" className="rz-button rz-button--secondary" onClick={() => navigate(`/voorraad/${encodeURIComponent(trimmedArticleId)}`)}>
              Terug naar artikelgegevens
            </button>
          </div>

          <section className="rz-article-detail-section">
            <h3 className="rz-article-detail-section-title">Huidige classificatie</h3>
            <div className="rz-article-detail-section-body" style={{ display: 'grid', gap: 8 }}>
              {loading ? <div>Classificatie laden…</div> : assignment ? (
                <>
                  <div className="rz-field-row"><div className="rz-field-row-label">Brickcode:</div><div className="rz-field-row-value">{assignment.brick_code}</div></div>
                  <div className="rz-field-row"><div className="rz-field-row-label">Brickomschrijving:</div><div className="rz-field-row-value">{assignment.brick_description}</div></div>
                  <div className="rz-field-row"><div className="rz-field-row-label">Hiërarchie:</div><div className="rz-field-row-value">{hierarchyLabel(assignment)}</div></div>
                  {assignment.brick_description_en && assignment.brick_description_en !== assignment.brick_description ? (
                    <div className="rz-field-row"><div className="rz-field-row-label">Engelse brontekst:</div><div className="rz-field-row-value">{assignment.brick_description_en}</div></div>
                  ) : null}
                  {canEdit ? <button type="button" className="rz-button rz-button--secondary" disabled={saving} onClick={clearAssignment}>Classificatie verwijderen</button> : null}
                </>
              ) : <div className="rz-empty-state">Nog geen GPC Brick gekozen.</div>}
            </div>
          </section>

          <section className="rz-article-detail-section">
            <h3 className="rz-article-detail-section-title">GPC Brick zoeken</h3>
            <div className="rz-article-detail-section-body" style={{ display: 'grid', gap: 12 }}>
              <input
                className="rz-input"
                value={query}
                onChange={(event) => setQuery(event.target.value)}
                placeholder="Zoek op Brickcode, Nederlandse of Engelse omschrijving"
                aria-label="GPC Brick zoeken"
                data-testid="gpc-brick-search"
              />
              {message ? <div className="rz-inline-feedback rz-inline-feedback--success">{message}</div> : null}
              {error ? <div className="rz-article-detail-alert">{error}</div> : null}
              {searching ? <div>Zoeken…</div> : null}
              {!searching && !results.length ? <div className="rz-empty-state">Geen GPC Bricks gevonden.</div> : null}
              <div style={{ display: 'grid', gap: 8 }}>
                {results.map((item) => (
                  <button
                    key={item.brick_code}
                    type="button"
                    className="rz-button rz-button--secondary"
                    disabled={!canEdit || saving}
                    onClick={() => selectBrick(item)}
                    style={{ textAlign: 'left', display: 'grid', gap: 3 }}
                    data-testid={`gpc-brick-option-${item.brick_code}`}
                  >
                    <strong>{item.brick_code} — {item.brick_description}</strong>
                    <span>{hierarchyLabel(item)}</span>
                    {item.brick_description_en && item.brick_description_en !== item.brick_description ? <span>EN: {item.brick_description_en}</span> : null}
                  </button>
                ))}
              </div>
              {!canEdit ? <div className="rz-empty-state">Je kunt de classificatie bekijken, maar niet wijzigen.</div> : null}
            </div>
          </section>
        </div>
      </ScreenCard>
    </AppShell>
  )
}
