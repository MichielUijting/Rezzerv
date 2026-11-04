import { useEffect, useMemo, useState } from 'react'
import AppShell from '../../app/AppShell'
import ScreenCard from '../../ui/ScreenCard'
import ClassificationSearchOverlay from '../externalDatabases/ClassificationSearchOverlay'
import Button from '../../ui/Button'
import DelayedTableLoadingOverlay from '../../ui/DelayedTableLoadingOverlay'
import { limitSearchCandidates } from '../../ui/searchCandidatePolicy.js'
import { fetchJsonWithAuth } from '../../lib/authSession'
import './catalog.css'

function text(value, fallback = '—') {
  const normalized = String(value ?? '').trim()
  return normalized || fallback
}

function functionalError(data, fallback) {
  const detail = String(data?.detail || '').trim()
  if (!detail || detail.toLowerCase() === 'not found') return fallback
  return detail
}

function rejectionStorageKey(productId, brickCode) {
  return `rezzerv:gpc-suggestion-rejected:${String(productId || '').trim()}:${String(brickCode || '').trim()}`
}

function isSuggestionRejected(productId, suggestion) {
  if (!productId || !suggestion?.brick_code) return false
  try {
    return window.localStorage.getItem(rejectionStorageKey(productId, suggestion.brick_code)) === '1'
  } catch {
    return false
  }
}

function rememberSuggestionRejection(productId, suggestion) {
  if (!productId || !suggestion?.brick_code) return
  try {
    window.localStorage.setItem(rejectionStorageKey(productId, suggestion.brick_code), '1')
  } catch {
    // De handmatige classificatie blijft beschikbaar wanneer browseropslag is geblokkeerd.
  }
}

export default function CatalogGpcActionPage({ embedded = false, readOnly = false, selectedProduct = undefined, onArticleChange = () => {} }) {
  const [items, setItems] = useState([])
  const [articleQuery, setArticleQuery] = useState('')
  const [selectedArticle, setSelectedArticle] = useState(null)
  const [assignment, setAssignment] = useState(null)
  const [suggestions, setSuggestions] = useState([])
  const [brickEditorOpen, setBrickEditorOpen] = useState(false)
  const [brickQuery, setBrickQuery] = useState('')
  const [brickResults, setBrickResults] = useState([])
  const [loading, setLoading] = useState(true)
  const [checking, setChecking] = useState(false)
  const [searchingBricks, setSearchingBricks] = useState(false)
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState('')
  const [feedback, setFeedback] = useState('')

  useEffect(() => {
    let cancelled = false
    async function loadCatalog() {
      if (selectedProduct !== undefined) { setLoading(false); return }
      setLoading(true)
      setError('')
      try {
        const response = await fetchJsonWithAuth('/api/catalog?limit=2000')
        const data = await response.json().catch(() => ({}))
        if (!response.ok) throw new Error(functionalError(data, 'Catalogus kon niet worden geladen.'))
        if (!cancelled) setItems(Array.isArray(data?.items) ? data.items : [])
      } catch (loadError) {
        if (!cancelled) setError(loadError?.message || 'Catalogus kon niet worden geladen.')
      } finally {
        if (!cancelled) setLoading(false)
      }
    }
    loadCatalog()
    return () => { cancelled = true }
  }, [selectedProduct !== undefined])

  useEffect(() => {
    if (selectedProduct === undefined) return
    if (selectedProduct?.id) void chooseArticle(selectedProduct)
    else resetArticle()
  }, [selectedProduct?.id])

  const articleResults = useMemo(() => {
    const query = articleQuery.trim().toLowerCase()
    if (!query) return []
    return limitSearchCandidates(items.filter((item) => [item.name, item.brand, item.primary_gtin]
      .some((value) => String(value || '').toLowerCase().includes(query))))
  }, [items, articleQuery])

  async function chooseArticle(article) {
    setSelectedArticle(article)
    onArticleChange(article)
    setAssignment(null)
    setSuggestions([])
    setBrickEditorOpen(false)
    setBrickQuery('')
    setBrickResults([])
    setError('')
    setFeedback('')
    setChecking(true)
    try {
      const response = await fetchJsonWithAuth(`/api/catalog/${encodeURIComponent(article.id)}/gpc-brick`)
      const data = await response.json().catch(() => ({}))
      if (!response.ok) throw new Error(functionalError(data, 'De GPC-classificatie kon niet worden opgehaald.'))
      setAssignment(data?.assignment || null)
      const rawSuggestions = Array.isArray(data?.suggestions)
        ? data.suggestions
        : data?.suggestion ? [data.suggestion] : []
      const visibleSuggestions = rawSuggestions
        .filter((candidate) => !isSuggestionRejected(article.id, candidate))
        .slice(0, 5)
      setSuggestions(visibleSuggestions)
      if (data?.assignment) {
        setFeedback('De bestaande bevestigde GPC-classificatie is gevonden.')
      } else if (visibleSuggestions.length) {
        setFeedback(`Inhuis heeft ${visibleSuggestions.length} waarschijnlijke GPC-kandidaat${visibleSuggestions.length === 1 ? '' : 'en'} gevonden. Bevestig de beste match of kies een alternatief.`)
      } else {
        setFeedback('Inhuis kon nog geen bruikbare GPC-kandidaat afleiden. Zoek en selecteer hieronder een Brick.')
        if (!readOnly && !embedded) setBrickEditorOpen(true)
      }
    } catch (chooseError) {
      setError(chooseError?.message || 'De GPC-classificatie kon niet worden opgehaald.')
    } finally {
      setChecking(false)
    }
  }

  useEffect(() => {
    let cancelled = false
    const normalized = brickQuery.trim()
    if (!selectedArticle || !brickEditorOpen || !normalized) {
      setBrickResults([])
      setSearchingBricks(false)
      return () => { cancelled = true }
    }
    const timer = window.setTimeout(async () => {
      setSearchingBricks(true)
      setError('')
      try {
        const response = await fetchJsonWithAuth(`/api/catalog/gpc/bricks?query=${encodeURIComponent(normalized)}&limit=5`)
        const data = await response.json().catch(() => ({}))
        if (!response.ok) throw new Error(functionalError(data, 'De GPC-catalogus kon niet worden doorzocht.'))
        if (!cancelled) setBrickResults(limitSearchCandidates(Array.isArray(data?.items) ? data.items : []))
      } catch (searchError) {
        if (!cancelled) setError(searchError?.message || 'De GPC-catalogus kon niet worden doorzocht.')
      } finally {
        if (!cancelled) setSearchingBricks(false)
      }
    }, 250)
    return () => {
      cancelled = true
      window.clearTimeout(timer)
    }
  }, [selectedArticle, brickEditorOpen, brickQuery])

  async function saveBrick(brick) {
    if (!selectedArticle || readOnly) return
    setSaving(true)
    setError('')
    setFeedback('')
    try {
      const response = await fetchJsonWithAuth(`/api/catalog/${encodeURIComponent(selectedArticle.id)}/gpc-brick`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ brick_code: brick.brick_code }),
      })
      const data = await response.json().catch(() => ({}))
      if (!response.ok) throw new Error(functionalError(data, 'De GPC-classificatie kon niet worden opgeslagen.'))
      setAssignment(data?.assignment || brick)
      setSuggestions([])
      setBrickEditorOpen(false)
      setBrickQuery('')
      setBrickResults([])
      setFeedback('De GPC Brick is bevestigd en opgeslagen bij het universele artikel.')
    } catch (saveError) {
      setError(saveError?.message || 'De GPC-classificatie kon niet worden opgeslagen.')
    } finally {
      setSaving(false)
    }
  }

  function searchAlternative() {
    setBrickEditorOpen(true)
    setBrickQuery('')
    setBrickResults(suggestions)
    setError('')
    setFeedback('Selecteer de juiste officiële GS1 Brick in de zoeklijst.')
    window.setTimeout(() => document.getElementById('catalog-gpc-action-brick-search')?.focus(), 0)
  }

  function rejectSuggestion(candidate) {
    if (!selectedArticle || !candidate) return
    rememberSuggestionRejection(selectedArticle.id, candidate)
    const remaining = suggestions.filter((item) => item?.brick_code !== candidate?.brick_code)
    setSuggestions(remaining)
    if (remaining.length) {
      setFeedback('Deze kandidaat is genegeerd. Kies een van de overige voorstellen of zoek handmatig.')
      return
    }
    setBrickEditorOpen(true)
    setFeedback('Alle automatische voorstellen zijn genegeerd. Zoek hieronder een betere Brick.')
    window.setTimeout(() => document.getElementById('catalog-gpc-action-brick-search')?.focus(), 0)
  }

  function resetArticle() {
    onArticleChange(null)
    setSelectedArticle(null)
    setAssignment(null)
    setSuggestions([])
    setBrickEditorOpen(false)
    setArticleQuery('')
    setBrickQuery('')
    setBrickResults([])
    setError('')
    setFeedback('')
  }

  const content = (
    <>
      <DelayedTableLoadingOverlay active={loading || checking || searchingBricks || saving} />
      <div className="rz-catalog-page" data-testid="catalog-gpc-action-page">
        <ScreenCard fullWidth style={embedded ? { padding: 0, margin: 0, borderRadius: 0, overflow: 'visible' } : undefined}>
          <div className="rz-catalog-card">
            <div className="rz-catalog-section-header">
              <div>
                <h2>{selectedProduct !== undefined ? 'GS1 GPC' : 'GPC classificeren'}</h2>
                {selectedProduct === undefined ? <p>Selecteer een universeel catalogusartikel en bevestig de bijbehorende GS1 GPC Brick.</p> : null}
              </div>
            </div>

            {error ? <div className="rz-inline-feedback rz-inline-feedback--error">{error}</div> : null}
            {feedback && !embedded ? <div className="rz-inline-feedback">{feedback}</div> : null}

            {selectedProduct === undefined ? <section className="rz-catalog-detail-section">
              <h3>1. Selecteer een catalogusartikel</h3>
              {!selectedArticle ? (
                <>
                  <input
                    className="rz-input rz-catalog-gpc-action-search"
                    value={articleQuery}
                    onChange={(event) => setArticleQuery(event.target.value)}
                    placeholder="Zoeken op artikelnaam, merk, barcode, GTIN of EAN"
                    autoFocus
                  />
                  {loading ? <div className="rz-catalog-gpc-state">Catalogus laden…</div> : null}
                  {articleQuery.trim() && !loading && !articleResults.length ? (
                    <div className="rz-catalog-gpc-empty">Geen catalogusartikelen gevonden.</div>
                  ) : null}
                  {articleResults.length ? (
                    <div className="rz-catalog-gpc-results">
                      {articleResults.map((article) => (
                        <button key={article.id} type="button" className="rz-catalog-gpc-result" onClick={() => chooseArticle(article)}>
                          <span className="rz-catalog-gpc-result-title">{text(article.primary_gtin)} — {text(article.name)}</span>
                          <span className="rz-catalog-gpc-result-path">Merk: {text(article.brand)}</span>
                        </button>
                      ))}
                    </div>
                  ) : null}
                </>
              ) : (
                <div className="rz-catalog-gpc-selected-article">
                  <dl className="rz-catalog-definition-list">
                    <div><dt>Universeel artikel</dt><dd>{text(selectedArticle.name)}</dd></div>
                    <div><dt>Merk</dt><dd>{text(selectedArticle.brand)}</dd></div>
                    <div><dt>GTIN/EAN</dt><dd>{text(selectedArticle.primary_gtin)}</dd></div>
                  </dl>
                  <Button type="button" variant="secondary" onClick={resetArticle} disabled={saving}>Ander artikel kiezen</Button>
                </div>
              )}
            </section> : null}

            {selectedArticle ? (
              <section className="rz-catalog-detail-section">
                {!embedded ? <h3>2. GPC Brick</h3> : null}
                {checking ? <div className="rz-catalog-gpc-state">Bestaande classificatie controleren…</div> : null}
                {!checking && !assignment && !suggestions.length ? <div className="rz-classification-current"><span>Huidige classificatie</span><strong>Niet geclassificeerd</strong><span>Geen bevestigde GS1 Brick</span></div> : null}
                {!checking && assignment ? (
                  <div className="rz-catalog-gpc-summary">
                    <div className="rz-catalog-gpc-primary">
                      <span className="rz-catalog-gpc-label">{embedded ? "Huidige classificatie" : "Bevestigde classificatie"}</span>
                      <strong>{assignment.brick_code} — {text(assignment.brick_description)}</strong>
                    </div>
                    <dl className="rz-catalog-gpc-hierarchy">
                      <div><dt>Segment</dt><dd>{text(assignment.segment_description)}</dd></div>
                      <div><dt>GPC-familie</dt><dd>{text(assignment.family_description)}</dd></div>
                      <div><dt>GPC-groep</dt><dd>{text(assignment.class_description)}</dd></div>
                    </dl>
                  </div>
                ) : null}

                {!embedded && !readOnly && !checking && !assignment && suggestions.length ? (
                  <div className="rz-catalog-gpc-candidates" data-testid="catalog-gpc-action-suggestions">
                    <div className="rz-catalog-gpc-candidates-header">
                      <strong>Waarschijnlijke GPC Bricks</strong>
                      <span>Automatisch gerangschikt op productnaam, categorie, externe metadata en de bestaande Inhuis-producttaxonomie.</span>
                    </div>
                    {suggestions.map((candidate, index) => (
                      <div className="rz-catalog-gpc-suggestion" data-testid="catalog-gpc-action-suggestion" key={candidate.brick_code}>
                        <div>
                          <span className="rz-catalog-gpc-label">{index === 0 ? 'Voorgestelde classificatie' : `Alternatief ${index + 1}`}</span>
                          <strong>{candidate.brick_code} — {text(candidate.brick_description)}</strong>
                          <small>
                            Matchsterkte: {Number(candidate.match_strength_percent || Math.round(Number(candidate.confidence || 0) * 100))}% ({text(candidate.confidence_label, 'indicatief')})
                            {' · '}{text(candidate.suggestion_reason)}
                          </small>
                          <span className="rz-catalog-gpc-result-path">{text(candidate.segment_description)} › {text(candidate.family_description)} › {text(candidate.class_description)}</span>
                        </div>
                        <div className="rz-catalog-gpc-editor-actions">
                          <Button type="button" onClick={() => saveBrick(candidate)} disabled={saving}>{embedded ? "Bevestigen GS1" : "Voorstel bevestigen"}</Button>
                          <Button type="button" variant="secondary" onClick={() => rejectSuggestion(candidate)} disabled={saving}>Voorstel negeren</Button>
                        </div>
                      </div>
                    ))}
                    <div className="rz-catalog-gpc-editor-actions">
                      <Button type="button" variant="secondary" onClick={searchAlternative} disabled={saving}>Andere Brick zoeken</Button>
                    </div>
                  </div>
                ) : null}

                {!embedded && !readOnly && !checking && (brickEditorOpen || assignment) ? (
                  <div className="rz-catalog-gpc-editor">
                    <label htmlFor="catalog-gpc-action-brick-search">{assignment ? 'Andere Brick kiezen' : 'Brick zoeken en selecteren'}</label>
                    <input
                      id="catalog-gpc-action-brick-search"
                      className="rz-input"
                      value={brickQuery}
                      onChange={(event) => setBrickQuery(event.target.value)}
                      placeholder="Zoeken op Brickcode of Nederlandse Brickomschrijving"
                      disabled={saving}
                    />
                    {searchingBricks ? <div className="rz-catalog-gpc-state">Bricks zoeken…</div> : null}
                    {brickQuery.trim() && !searchingBricks && !brickResults.length ? (
                      <div className="rz-catalog-gpc-empty">Geen passende GPC Bricks gevonden.</div>
                    ) : null}
                    {brickResults.length ? (
                      <div className="rz-catalog-gpc-results">
                        {brickResults.map((brick) => (
                          <button key={brick.brick_code} type="button" className="rz-catalog-gpc-result" disabled={saving} onClick={() => saveBrick(brick)}>
                            <span className="rz-catalog-gpc-result-title">{brick.brick_code} — {brick.brick_description}</span>
                            <span className="rz-catalog-gpc-result-path">{brick.segment_description} › {brick.family_description} › {brick.class_description}</span>
                          </button>
                        ))}
                      </div>
                    ) : null}
                  </div>
                ) : null}
              </section>
            ) : null}
            {embedded && !readOnly && selectedArticle && !checking ? <Button type="button"
              variant="secondary" disabled={saving} onClick={searchAlternative}>
              Andere Brick kiezen
            </Button> : null}
          </div>
        </ScreenCard>
      </div>
      {embedded && brickEditorOpen ? <ClassificationSearchOverlay
        title="GS1 GPC Brick kiezen" query={brickQuery} onQueryChange={setBrickQuery}
        rows={brickQuery.trim().length >= 2 ? brickResults : suggestions}
        busy={saving || searchingBricks} onClose={() => setBrickEditorOpen(false)}
        getKey={(item) => item.brick_code}
        getTitle={(item) => item.brick_code + ' — ' + item.brick_description}
        getDetail={(item) => [item.segment_description, item.family_description, item.class_description].filter(Boolean).join(' › ')}
        onChoose={(item) => { void saveBrick(item) }}
        emptyMessage={brickQuery.trim().length < 2 ? 'Vul minstens twee tekens in of kies een voorgestelde Brick.' : 'Geen passende officiële Bricks.'}
      /> : null}
    </>
  )
  return embedded ? content : <AppShell title="GPC classificeren" showExit={false}>{content}</AppShell>
}
