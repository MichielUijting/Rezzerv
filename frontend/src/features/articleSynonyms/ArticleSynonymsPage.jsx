import { useCallback, useEffect, useRef, useState } from 'react'
import { Link, useSearchParams } from 'react-router-dom'
import AppShell from '../../app/AppShell'
import ScreenCard from '../../ui/ScreenCard'
import DataTable from '../../ui/DataTable'
import Button from '../../ui/Button'
import CatalogProductImage from '../catalog/CatalogProductImage'
import { useAppFeedback } from '../../ui/AppFeedbackProvider'
import { fetchJsonWithAuth } from '../../lib/authSession'
import './synonymAnalysis.css'

const API = '/api/external-databases/article-synonyms'
const identity = (item) => item?.primary_gtin || item?.article_codes?.[0] || String(item?.id || '').slice(0, 12)
const statusOrder = { linked: 0, suggested: 1, other: 2 }

export default function ArticleSynonymsPage() {
  const [searchParams] = useSearchParams()
  const initialArticleId = searchParams.get('artikel') || ''
  const [articles, setArticles] = useState([])
  const [activeArticle, setActiveArticle] = useState(initialArticleId)
  const [options, setOptions] = useState([])
  const [selected, setSelected] = useState(new Set())
  const [loading, setLoading] = useState(true)
  const [loadingOptions, setLoadingOptions] = useState(false)
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState('')
  const savingRef = useRef(false)
  const { showFeedback } = useAppFeedback()

  const loadArticles = useCallback(async (signal) => {
    const response = await fetchJsonWithAuth(`${API}/analysis`, { signal })
    if (!response.ok) throw new Error('Catalogusartikelen konden niet worden geladen.')
    const data = await response.json()
    if (!signal?.aborted) setArticles(data.items || [])
  }, [])

  const loadOptions = useCallback(async (id, signal) => {
    const response = await fetchJsonWithAuth(`${API}/analysis/${encodeURIComponent(id)}/options`, { signal })
    if (!response.ok) throw new Error('Synoniemrelaties konden niet worden geladen.')
    const data = await response.json()
    if (!signal?.aborted) setOptions(data.items || [])
  }, [])

  useEffect(() => {
    const controller = new AbortController()
    setLoading(true)
    setError('')
    loadArticles(controller.signal)
      .catch((err) => { if (!controller.signal.aborted) setError(err.message) })
      .finally(() => { if (!controller.signal.aborted) setLoading(false) })
    return () => controller.abort()
  }, [loadArticles])

  useEffect(() => {
    const controller = new AbortController()
    setOptions([])
    setSelected(new Set())
    if (!activeArticle) return () => controller.abort()
    setLoadingOptions(true)
    loadOptions(activeArticle, controller.signal)
      .catch((err) => { if (!controller.signal.aborted) setError(err.message) })
      .finally(() => { if (!controller.signal.aborted) setLoadingOptions(false) })
    return () => controller.abort()
  }, [activeArticle, loadOptions])

  function chooseArticle(id) {
    if (savingRef.current) return
    setError('')
    setActiveArticle(id)
    setSelected(new Set())
  }

  function toggleOption(item) {
    if (savingRef.current || !item.linkable || item.status === 'linked') return
    setSelected((current) => {
      const next = new Set(current)
      if (next.has(item.id)) next.delete(item.id)
      else if (next.size < 200) next.add(item.id)
      return next
    })
  }

  async function link() {
    if (savingRef.current || !selected.size || !activeArticle) return
    const current = options.filter((item) => selected.has(item.id) && item.linkable && item.status !== 'linked')
    if (!current.length || current.length !== selected.size) return
    const selections = current.map((item) => {
      const ids = [activeArticle, item.id].sort()
      return {
        left_product_id: ids[0], right_product_id: ids[1],
        fingerprint: item.fingerprint, manual: Boolean(item.manual),
      }
    })
    if (selections.some((pair) => pair.left_product_id === pair.right_product_id)) {
      setError('Een artikel kan niet aan zichzelf worden gekoppeld.')
      return
    }
    savingRef.current = true
    setSaving(true)
    setError('')
    try {
      const response = await fetchJsonWithAuth(`${API}/link`, {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ selections }),
      })
      const payload = await response.json()
      if (!response.ok) throw new Error(typeof payload.detail === 'string'
        ? payload.detail : 'Koppelen is niet gelukt.')
      await Promise.all([loadArticles(), loadOptions(activeArticle)])
      setSelected(new Set())
      showFeedback({ variant: 'success', message: `${payload.linked} synoniemkoppeling(en) bevestigd.` })
    } catch (err) {
      setError(err.message)
    } finally {
      savingRef.current = false
      setSaving(false)
    }
  }

  const currentArticle = articles.find((item) => item.id === activeArticle)
  const leftRows = articles.map((item) => ({
    ...item,
    count: item.synonym_count || 0,
  }))
  const rightRows = [...options].sort((a, b) =>
    statusOrder[a.status] - statusOrder[b.status]
    || (b.score || 0) - (a.score || 0)
    || a.name.localeCompare(b.name, 'nl') || a.id.localeCompare(b.id)
  )
  const articleColumns = [
    { key: 'name', label: 'Artikel', width: 210, sortable: true, filterable: true },
    { key: 'code', label: 'Art./Barcode', width: 130, sortable: true, filterable: true },
    { key: 'store', label: 'Winkel', width: 120, sortable: true, filterable: true },
    { key: 'count', label: 'Synoniemen', width: 100, sortable: true, align: 'right' },
  ]
  const rightColumns = [
    { key: 'status_label', label: 'Relatie', width: 120, sortable: true, filterable: true },
    { key: 'name', label: 'Artikel', width: 210, sortable: true, filterable: true },
    { key: 'code', label: 'Art./Barcode', width: 130, sortable: true, filterable: true },
    { key: 'store', label: 'Winkel', width: 120, sortable: true, filterable: true },
  ]
  return <AppShell title="Artikel-synoniemen" showExit={false}>
    <ScreenCard fullWidth>
      <h2>Artikel-synoniemen</h2>
      <p>Kies links één artikel. Rechts zie je bestaande koppelingen, automatische voorstellen en alle overige gecodeerde Catalogusartikelen. De winkel bepaalt niet of artikelen synoniemen zijn.</p>
      <p>Artikelen zonder code of barcode voeg je toe in <Link to="/externe-databases-2">Externe databases 2</Link>.</p>
      {error ? <p role="alert">{error}</p> : null}
      <div className="rz-synonym-side-by-side">
        <section className="rz-synonym-side" aria-label="Catalogusartikelen links">
          <h3>Artikel kiezen</h3>
          <DataTable columns={articleColumns}
            data={leftRows.map((item) => ({ ...item, code: identity(item) }))}
            getRowKey={(item) => item.id} pageSize={10}
            wrapperClassName="rz-synonym-analysis-table-wrapper"
            dataTestId="article-synonyms-articles"
            emptyMessage={loading ? 'Catalogusartikelen laden...' : 'Geen gecodeerde Catalogusartikelen beschikbaar.'}
            renderRow={(item) => <tr key={item.id} tabIndex={0}
              className="rz-synonym-analysis-main-row" aria-selected={activeArticle === item.id}
              aria-label={`Kies ${item.name}, code ${item.code}`}
              onClick={() => chooseArticle(item.id)}
              onKeyDown={(event) => {
                if (event.key === 'Enter' || event.key === ' ') {
                  event.preventDefault()
                  chooseArticle(item.id)
                }
              }}>
              <td><div className="rz-synonym-analysis-product">
                <CatalogProductImage imageUrl={item.image_url} productName={item.name} compact />
                <span>{item.name}</span>
              </div></td>
              <td>{item.code}</td>
              <td>{item.store}</td>
              <td className="rz-num">{item.count}</td>
            </tr>} />
        </section>
        <section className="rz-synonym-side" data-testid="article-synonyms-candidates"
          aria-label="Synoniemen rechts">
          <h3>{currentArticle ? `Synoniemen van ${currentArticle.name}` : 'Synoniemen kiezen'}</h3>
          {!currentArticle
            ? <p role="status">Selecteer links een artikel om de bestaande koppelingen en alle andere artikelen te bekijken.</p>
            : <>
              <p className="rz-synonym-analysis-note">
                Al gekoppeld = bestaande relatie. Voorstel = naam-/kenmerkovereenkomst.
                Overig = overige artikelen. De gekozen regel links staat rechts nooit als kandidaat.
                Klik rechts op een artikel en bevestig met Koppelen.
              </p>
              <DataTable columns={rightColumns}
                data={rightRows.map((item) => ({ ...item, code: identity(item) }))}
                getRowKey={(item) => item.id} pageSize={10}
                wrapperClassName="rz-synonym-analysis-table-wrapper"
                dataTestId="article-synonyms-table"
                emptyMessage={loadingOptions ? 'Synoniemen laden...' : 'Geen andere artikelen beschikbaar.'}
                renderRow={(item) => <tr key={item.id}
                  tabIndex={item.linkable ? 0 : -1}
                  className={`rz-synonym-analysis-candidate-row rz-synonym-relation-${item.status}`}
                  aria-selected={selected.has(item.id)}
                  aria-label={`${item.status_label}: ${item.name}, code ${item.code}`}
                  title={item.linkable ? 'Klik om te selecteren voor koppelen' : item.reason}
                  onClick={() => toggleOption(item)}
                  onKeyDown={(event) => {
                    if ((event.key === 'Enter' || event.key === ' ') && item.linkable) {
                      event.preventDefault()
                      toggleOption(item)
                    }
                  }}>
                  <td><span className="rz-synonym-relation-label">{item.status_label}</span>
                    {selected.has(item.id) ? ' ✓' : ''}</td>
                  <td><div className="rz-synonym-analysis-product">
                    <CatalogProductImage imageUrl={item.image_url} productName={item.name} compact />
                    <span>{item.name}</span>
                  </div></td>
                  <td>{item.code}</td>
                  <td>{item.store}</td>
                </tr>} />
              <div className="rz-synonym-analysis-actions">
                <span aria-live="polite">{selected.size} geselecteerd</span>
                <Button disabled={loading || loadingOptions || saving || !selected.size}
                  onClick={link}>Koppelen</Button>
              </div>
            </>}
        </section>
      </div>
    </ScreenCard>
  </AppShell>
}
