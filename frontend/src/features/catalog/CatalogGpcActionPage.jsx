import { useEffect, useMemo, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import AppShell from '../../app/AppShell'
import ScreenCard from '../../ui/ScreenCard'
import Button from '../../ui/Button'
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

export default function CatalogGpcActionPage() {
  const navigate = useNavigate()
  const [items, setItems] = useState([])
  const [articleQuery, setArticleQuery] = useState('')
  const [selectedArticle, setSelectedArticle] = useState(null)
  const [assignment, setAssignment] = useState(null)
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
  }, [])

  const articleResults = useMemo(() => {
    const query = articleQuery.trim().toLowerCase()
    if (!query) return []
    return items.filter((item) => [item.name, item.brand, item.primary_gtin]
      .some((value) => String(value || '').toLowerCase().includes(query)))
      .slice(0, 25)
  }, [items, articleQuery])

  async function chooseArticle(article) {
    setSelectedArticle(article)
    setAssignment(null)
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
      if (data?.assignment) {
        setFeedback('De bestaande bevestigde GPC-classificatie is gevonden.')
      } else {
        setFeedback('Voor dit artikel is nog geen bevestigde GPC Brick opgeslagen. Kies hieronder een Brick.')
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
    if (!selectedArticle || !normalized) {
      setBrickResults([])
      setSearchingBricks(false)
      return () => { cancelled = true }
    }
    const timer = window.setTimeout(async () => {
      setSearchingBricks(true)
      setError('')
      try {
        const response = await fetchJsonWithAuth(`/api/catalog/gpc/bricks?query=${encodeURIComponent(normalized)}&limit=25`)
        const data = await response.json().catch(() => ({}))
        if (!response.ok) throw new Error(functionalError(data, 'De GPC-catalogus kon niet worden doorzocht.'))
        if (!cancelled) setBrickResults(Array.isArray(data?.items) ? data.items : [])
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
  }, [selectedArticle, brickQuery])

  async function saveBrick(brick) {
    if (!selectedArticle) return
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
      setBrickQuery('')
      setBrickResults([])
      setFeedback('De GPC Brick is bevestigd en opgeslagen bij het universele artikel.')
    } catch (saveError) {
      setError(saveError?.message || 'De GPC-classificatie kon niet worden opgeslagen.')
    } finally {
      setSaving(false)
    }
  }

  function resetArticle() {
    setSelectedArticle(null)
    setAssignment(null)
    setArticleQuery('')
    setBrickQuery('')
    setBrickResults([])
    setError('')
    setFeedback('')
  }

  return (
    <AppShell title="GPC classificeren" showExit={false}>
      <div className="rz-catalog-page" data-testid="catalog-gpc-action-page">
        <ScreenCard fullWidth>
          <div className="rz-catalog-card">
            <div className="rz-catalog-section-header">
              <div>
                <h2>GPC classificeren</h2>
                <p>Selecteer een universeel catalogusartikel en bevestig de bijbehorende GS1 GPC Brick.</p>
              </div>
              <Button type="button" variant="secondary" onClick={() => navigate('/catalogus')}>Terug naar Catalogus</Button>
            </div>

            {error ? <div className="rz-inline-feedback rz-inline-feedback--error">{error}</div> : null}
            {feedback ? <div className="rz-inline-feedback">{feedback}</div> : null}

            <section className="rz-catalog-detail-section">
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
            </section>

            {selectedArticle ? (
              <section className="rz-catalog-detail-section">
                <h3>2. GPC Brick</h3>
                {checking ? <div className="rz-catalog-gpc-state">Bestaande classificatie controleren…</div> : null}
                {!checking && assignment ? (
                  <div className="rz-catalog-gpc-summary">
                    <div className="rz-catalog-gpc-primary">
                      <span className="rz-catalog-gpc-label">Bevestigde classificatie</span>
                      <strong>{assignment.brick_code} — {text(assignment.brick_description || assignment.brick_description_en)}</strong>
                    </div>
                    <dl className="rz-catalog-gpc-hierarchy">
                      <div><dt>Segment</dt><dd>{text(assignment.segment_description)}</dd></div>
                      <div><dt>Family</dt><dd>{text(assignment.family_description)}</dd></div>
                      <div><dt>Class</dt><dd>{text(assignment.class_description)}</dd></div>
                    </dl>
                  </div>
                ) : null}

                {!checking ? (
                  <div className="rz-catalog-gpc-editor">
                    <label htmlFor="catalog-gpc-action-brick-search">{assignment ? 'Andere Brick kiezen' : 'Brick zoeken en selecteren'}</label>
                    <input
                      id="catalog-gpc-action-brick-search"
                      className="rz-input"
                      value={brickQuery}
                      onChange={(event) => setBrickQuery(event.target.value)}
                      placeholder="Zoeken op Brickcode of Nederlandse/Engelse Brickomschrijving"
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
          </div>
        </ScreenCard>
      </div>
    </AppShell>
  )
}
