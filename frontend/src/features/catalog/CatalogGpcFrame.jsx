import { useEffect, useMemo, useState } from 'react'
import { createPortal } from 'react-dom'
import { useParams } from 'react-router-dom'
import Button from '../../ui/Button'
import { fetchJsonWithAuth, readStoredAuthContext } from '../../lib/authSession'

function description(value, fallback = '—') {
  const normalized = String(value || '').trim()
  return normalized || fallback
}

export default function CatalogGpcFrame() {
  const { globalProductId = '' } = useParams()
  const productId = String(globalProductId || '').trim()
  const [target, setTarget] = useState(null)
  const [assignment, setAssignment] = useState(null)
  const [query, setQuery] = useState('')
  const [results, setResults] = useState([])
  const [loading, setLoading] = useState(true)
  const [searching, setSearching] = useState(false)
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState('')
  const [feedback, setFeedback] = useState('')

  const role = String(readStoredAuthContext()?.display_role || '').trim().toLowerCase()
  const canEdit = role === 'admin' || role === 'lid'

  useEffect(() => {
    let cancelled = false
    let attempts = 0
    function findTarget() {
      if (cancelled) return
      const grid = document.querySelector('[data-testid="catalog-detail-page"] .rz-catalog-detail-grid')
      if (grid) {
        const host = document.createElement('section')
        host.dataset.testid = 'catalog-gpc-frame-host'
        grid.insertBefore(host, grid.children[1] || null)
        setTarget(host)
        return
      }
      attempts += 1
      if (attempts < 80) window.setTimeout(findTarget, 100)
    }
    findTarget()
    return () => {
      cancelled = true
      setTarget((current) => {
        current?.remove()
        return null
      })
    }
  }, [productId])

  async function loadAssignment() {
    if (!productId) return
    setLoading(true)
    setError('')
    try {
      const response = await fetchJsonWithAuth(`/api/catalog/${encodeURIComponent(productId)}/gpc-brick`)
      const data = await response.json().catch(() => ({}))
      if (!response.ok) throw new Error(data?.detail || 'GPC-classificatie kon niet worden geladen.')
      setAssignment(data?.assignment || null)
    } catch (loadError) {
      setError(loadError?.message || 'GPC-classificatie kon niet worden geladen.')
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    loadAssignment()
  }, [productId])

  useEffect(() => {
    let cancelled = false
    const normalized = query.trim()
    if (!normalized) {
      setResults([])
      setSearching(false)
      return () => { cancelled = true }
    }
    const timer = window.setTimeout(async () => {
      setSearching(true)
      setError('')
      try {
        const response = await fetchJsonWithAuth(`/api/gpc/bricks?query=${encodeURIComponent(normalized)}&limit=25`)
        const data = await response.json().catch(() => ({}))
        if (!response.ok) throw new Error(data?.detail || 'GPC Bricks konden niet worden gezocht.')
        if (!cancelled) setResults(Array.isArray(data?.items) ? data.items : [])
      } catch (searchError) {
        if (!cancelled) setError(searchError?.message || 'GPC Bricks konden niet worden gezocht.')
      } finally {
        if (!cancelled) setSearching(false)
      }
    }, 250)
    return () => {
      cancelled = true
      window.clearTimeout(timer)
    }
  }, [query])

  async function selectBrick(brickCode) {
    if (!canEdit || !productId) return
    setSaving(true)
    setError('')
    setFeedback('')
    try {
      const response = await fetchJsonWithAuth(`/api/catalog/${encodeURIComponent(productId)}/gpc-brick`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ brick_code: brickCode }),
      })
      const data = await response.json().catch(() => ({}))
      if (!response.ok) throw new Error(data?.detail || 'GPC-classificatie kon niet worden opgeslagen.')
      setAssignment(data?.assignment || null)
      setFeedback('GPC-classificatie opgeslagen.')
      setQuery('')
      setResults([])
    } catch (saveError) {
      setError(saveError?.message || 'GPC-classificatie kon niet worden opgeslagen.')
    } finally {
      setSaving(false)
    }
  }

  async function clearAssignment() {
    if (!canEdit || !productId) return
    setSaving(true)
    setError('')
    setFeedback('')
    try {
      const response = await fetchJsonWithAuth(`/api/catalog/${encodeURIComponent(productId)}/gpc-brick`, {
        method: 'DELETE',
      })
      const data = await response.json().catch(() => ({}))
      if (!response.ok) throw new Error(data?.detail || 'GPC-classificatie kon niet worden verwijderd.')
      setAssignment(null)
      setFeedback('GPC-classificatie verwijderd.')
    } catch (deleteError) {
      setError(deleteError?.message || 'GPC-classificatie kon niet worden verwijderd.')
    } finally {
      setSaving(false)
    }
  }

  const currentLabel = useMemo(() => {
    if (!assignment) return 'Nog niet geclassificeerd'
    return `${description(assignment.brick_code)} — ${description(assignment.brick_description, assignment.brick_description_en)}`
  }, [assignment])

  if (!target || !productId) return null

  return createPortal(
    <div data-testid="catalog-gpc-frame" className="rz-catalog-gpc-frame">
      <h3>GS1 GPC-classificatie</h3>

      {loading ? <div>Classificatie laden...</div> : null}
      {error ? <div className="rz-inline-feedback rz-inline-feedback--error">{error}</div> : null}
      {feedback ? <div className="rz-inline-feedback">{feedback}</div> : null}

      {!loading ? (
        <dl className="rz-catalog-definition-list">
          <div><dt>Huidige classificatie</dt><dd>{currentLabel}</dd></div>
          <div><dt>Segment</dt><dd>{description(assignment?.segment_description)}</dd></div>
          <div><dt>Family</dt><dd>{description(assignment?.family_description)}</dd></div>
          <div><dt>Class</dt><dd>{description(assignment?.class_description)}</dd></div>
          <div><dt>Engelse brontekst</dt><dd>{description(assignment?.brick_description_en)}</dd></div>
        </dl>
      ) : null}

      {canEdit ? (
        <>
          <label htmlFor="catalog-gpc-search"><strong>{assignment ? 'GPC wijzigen' : 'GPC classificeren'}</strong></label>
          <input
            id="catalog-gpc-search"
            data-testid="catalog-gpc-search"
            value={query}
            onChange={(event) => setQuery(event.target.value)}
            placeholder="Zoek op Brickcode, Nederlandse of Engelse omschrijving"
            disabled={saving}
            style={{ width: '100%', marginTop: 8, marginBottom: 8 }}
          />
          {searching ? <div>Zoeken...</div> : null}
          {query.trim() && !searching && !results.length ? <div>Geen GPC Bricks gevonden.</div> : null}
          {results.length ? (
            <div data-testid="catalog-gpc-results" style={{ display: 'grid', gap: 8 }}>
              {results.map((brick) => (
                <button
                  key={brick.brick_code}
                  type="button"
                  className="rz-button"
                  disabled={saving}
                  onClick={() => selectBrick(brick.brick_code)}
                  style={{ textAlign: 'left' }}
                >
                  <strong>{brick.brick_code} — {brick.brick_description}</strong><br />
                  <span>{brick.segment_description} › {brick.family_description} › {brick.class_description}</span>
                </button>
              ))}
            </div>
          ) : null}
          {assignment ? (
            <div style={{ marginTop: 12 }}>
              <Button type="button" variant="secondary" onClick={clearAssignment} disabled={saving}>
                GPC verwijderen
              </Button>
            </div>
          ) : null}
        </>
      ) : <div>Je hebt alleen leesrechten voor deze classificatie.</div>}
    </div>,
    target,
  )
}
