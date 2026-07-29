import { useEffect, useMemo, useState } from 'react'
import Button from '../../ui/Button'
import { fetchJsonWithAuth, readStoredAuthContext } from '../../lib/authSession'

function valueOrDash(value) {
  const normalized = String(value ?? '').trim()
  return normalized || '—'
}

function functionalError(data, fallback) {
  const detail = String(data?.detail || '').trim()
  if (!detail || detail.toLowerCase() === 'not found') return fallback
  return detail
}

function assignmentSourceLabel(assignment) {
  const source = String(assignment?.assignment_source || '').trim()
  if (source === 'migrated_confirmed_product_group') return 'Overgenomen uit eerder bevestigde GPC-productgroep'
  if (source === 'manual_catalog_detail') return 'Handmatig bevestigd in Catalogusdetail'
  return source || ''
}

export default function CatalogGpcFrame({ globalProductId }) {
  const productId = String(globalProductId || '').trim()
  const [assignment, setAssignment] = useState(null)
  const [suggestion, setSuggestion] = useState(null)
  const [query, setQuery] = useState('')
  const [results, setResults] = useState([])
  const [loading, setLoading] = useState(true)
  const [searching, setSearching] = useState(false)
  const [saving, setSaving] = useState(false)
  const [editorOpen, setEditorOpen] = useState(false)
  const [error, setError] = useState('')
  const [feedback, setFeedback] = useState('')

  const role = String(readStoredAuthContext()?.display_role || '').trim().toLowerCase()
  const canEdit = role === 'admin' || role === 'lid'

  async function loadAssignment() {
    if (!productId) return
    setLoading(true)
    setError('')
    try {
      const response = await fetchJsonWithAuth(
        `/api/catalog/${encodeURIComponent(productId)}/gpc-brick`,
      )
      const data = await response.json().catch(() => ({}))
      if (!response.ok) {
        throw new Error(functionalError(data, 'De GPC-classificatie kon niet worden geladen.'))
      }
      setAssignment(data?.assignment || null)
      setSuggestion(data?.suggestion || null)
      if (data?.migration?.performed) {
        setFeedback('De eerder bevestigde GPC-classificatie is automatisch overgenomen.')
      }
    } catch (loadError) {
      setError(loadError?.message || 'De GPC-classificatie kon niet worden geladen.')
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
    if (!editorOpen || !normalized) {
      setResults([])
      setSearching(false)
      return () => { cancelled = true }
    }

    const timer = window.setTimeout(async () => {
      setSearching(true)
      setError('')
      try {
        const response = await fetchJsonWithAuth(
          `/api/catalog/gpc/bricks?query=${encodeURIComponent(normalized)}&limit=25`,
        )
        const data = await response.json().catch(() => ({}))
        if (!response.ok) {
          throw new Error(functionalError(data, 'De GPC-catalogus kon niet worden doorzocht.'))
        }
        if (!cancelled) setResults(Array.isArray(data?.items) ? data.items : [])
      } catch (searchError) {
        if (!cancelled) {
          setError(searchError?.message || 'De GPC-catalogus kon niet worden doorzocht.')
        }
      } finally {
        if (!cancelled) setSearching(false)
      }
    }, 300)

    return () => {
      cancelled = true
      window.clearTimeout(timer)
    }
  }, [editorOpen, query])

  async function selectBrick(brickCode) {
    if (!canEdit || !productId) return
    setSaving(true)
    setError('')
    setFeedback('')
    try {
      const response = await fetchJsonWithAuth(
        `/api/catalog/${encodeURIComponent(productId)}/gpc-brick`,
        {
          method: 'PUT',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ brick_code: brickCode }),
        },
      )
      const data = await response.json().catch(() => ({}))
      if (!response.ok) {
        throw new Error(functionalError(data, 'De GPC-classificatie kon niet worden opgeslagen.'))
      }
      setAssignment(data?.assignment || null)
      setSuggestion(null)
      setFeedback('De GPC-classificatie is opgeslagen.')
      setQuery('')
      setResults([])
      setEditorOpen(false)
    } catch (saveError) {
      setError(saveError?.message || 'De GPC-classificatie kon niet worden opgeslagen.')
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
      const response = await fetchJsonWithAuth(
        `/api/catalog/${encodeURIComponent(productId)}/gpc-brick`,
        { method: 'DELETE' },
      )
      const data = await response.json().catch(() => ({}))
      if (!response.ok) {
        throw new Error(functionalError(data, 'De GPC-classificatie kon niet worden verwijderd.'))
      }
      setAssignment(null)
      setSuggestion(null)
      setFeedback('De GPC-classificatie is verwijderd.')
      setEditorOpen(false)
      setQuery('')
      setResults([])
    } catch (deleteError) {
      setError(deleteError?.message || 'De GPC-classificatie kon niet worden verwijderd.')
    } finally {
      setSaving(false)
    }
  }

  const currentLabel = useMemo(() => {
    if (!assignment) return 'Nog niet geclassificeerd'
    const description = assignment.brick_description || assignment.brick_description_en
    return `${valueOrDash(assignment.brick_code)} — ${valueOrDash(description)}`
  }, [assignment])

  return (
    <section className="rz-catalog-gpc-section" data-testid="catalog-gpc-frame">
      <div className="rz-catalog-section-header">
        <div>
          <h3>GS1 GPC-classificatie</h3>
          <p>Universele productclassificatie voor dit catalogusartikel.</p>
        </div>
        {!loading && canEdit ? (
          <Button
            type="button"
            onClick={() => {
              setEditorOpen((open) => !open)
              setError('')
              setFeedback('')
            }}
            disabled={saving}
          >
            {editorOpen ? 'Sluiten' : assignment ? 'GPC wijzigen' : 'GPC classificeren'}
          </Button>
        ) : null}
      </div>

      {loading ? <div className="rz-catalog-gpc-state">Classificatie laden…</div> : null}
      {error ? <div className="rz-inline-feedback rz-inline-feedback--error">{error}</div> : null}
      {feedback ? <div className="rz-inline-feedback">{feedback}</div> : null}

      {!loading ? (
        <div className="rz-catalog-gpc-summary">
          <div className="rz-catalog-gpc-primary">
            <span className="rz-catalog-gpc-label">Huidige classificatie</span>
            <strong>{currentLabel}</strong>
            {assignmentSourceLabel(assignment) ? (
              <small>Bron: {assignmentSourceLabel(assignment)}</small>
            ) : null}
          </div>
          {assignment ? (
            <dl className="rz-catalog-gpc-hierarchy">
              <div><dt>Segment</dt><dd>{valueOrDash(assignment.segment_description)}</dd></div>
              <div><dt>Family</dt><dd>{valueOrDash(assignment.family_description)}</dd></div>
              <div><dt>Class</dt><dd>{valueOrDash(assignment.class_description)}</dd></div>
              <div><dt>Engelse brontekst</dt><dd>{valueOrDash(assignment.brick_description_en)}</dd></div>
            </dl>
          ) : null}
        </div>
      ) : null}

      {!loading && !assignment && suggestion ? (
        <div className="rz-catalog-gpc-suggestion" data-testid="catalog-gpc-suggestion">
          <div>
            <span className="rz-catalog-gpc-label">Voorgestelde classificatie</span>
            <strong>{suggestion.brick_code} — {suggestion.brick_description}</strong>
            <small>{suggestion.suggestion_reason}</small>
          </div>
          {canEdit ? (
            <Button type="button" onClick={() => selectBrick(suggestion.brick_code)} disabled={saving}>
              Voorstel bevestigen
            </Button>
          ) : null}
        </div>
      ) : null}

      {editorOpen && canEdit ? (
        <div className="rz-catalog-gpc-editor">
          <label htmlFor="catalog-gpc-search">Zoek een GPC Brick</label>
          <input
            id="catalog-gpc-search"
            className="rz-input"
            data-testid="catalog-gpc-search"
            value={query}
            onChange={(event) => setQuery(event.target.value)}
            placeholder="Zoeken op Brickcode of Nederlandse/Engelse omschrijving"
            disabled={saving}
            autoFocus
          />

          {searching ? <div className="rz-catalog-gpc-state">Zoeken…</div> : null}
          {query.trim() && !searching && !results.length ? (
            <div className="rz-catalog-gpc-empty">Geen passende GPC Bricks gevonden.</div>
          ) : null}

          {results.length ? (
            <div className="rz-catalog-gpc-results" data-testid="catalog-gpc-results">
              {results.map((brick) => (
                <button
                  key={brick.brick_code}
                  type="button"
                  className="rz-catalog-gpc-result"
                  disabled={saving}
                  onClick={() => selectBrick(brick.brick_code)}
                >
                  <span className="rz-catalog-gpc-result-title">
                    {brick.brick_code} — {brick.brick_description}
                  </span>
                  <span className="rz-catalog-gpc-result-path">
                    {brick.segment_description} › {brick.family_description} › {brick.class_description}
                  </span>
                </button>
              ))}
            </div>
          ) : null}

          {assignment ? (
            <div className="rz-catalog-gpc-editor-actions">
              <Button
                type="button"
                variant="secondary"
                onClick={clearAssignment}
                disabled={saving}
              >
                GPC verwijderen
              </Button>
            </div>
          ) : null}
        </div>
      ) : null}

      {!canEdit && !loading ? (
        <div className="rz-catalog-gpc-readonly">Je hebt alleen leesrechten voor deze classificatie.</div>
      ) : null}
    </section>
  )
}
