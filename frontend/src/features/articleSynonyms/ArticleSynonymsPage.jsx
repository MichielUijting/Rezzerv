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
const productName = (product) => [product.name, product.brand, product.variant].filter(Boolean).join(' · ')

export default function ArticleSynonymsPage() {
  const [searchParams] = useSearchParams()
  const articleId = searchParams.get('artikel') || ''
  const [items, setItems] = useState([])
  const [articles, setArticles] = useState([])
  const [activeArticle, setActiveArticle] = useState(articleId)
  const [selected, setSelected] = useState(new Set())
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState('')
  const savingRef = useRef(false)
  const { showFeedback } = useAppFeedback()

  const refresh = useCallback(async (signal) => {
    // Analysis is the existing central, read-only projection of *all* coded
    // Catalogus products. The candidate endpoint remains authoritative for
    // which pairs can be confirmed.
    const [analysisResponse, suggestionResponse] = await Promise.all([
      fetchJsonWithAuth(`${API}/analysis`, { signal }),
      fetchJsonWithAuth(API, { signal }),
    ])
    if (!analysisResponse.ok || !suggestionResponse.ok) {
      throw new Error('Artikel-synoniemen konden niet worden geladen.')
    }
    const [analysis, suggestions] = await Promise.all([
      analysisResponse.json(), suggestionResponse.json(),
    ])
    if (signal?.aborted) return
    setArticles(analysis.items || [])
    setItems((suggestions.items || []).map((item) => ({
      ...item,
      article_name: productName(item.left),
      article_store: item.left.store_name || 'Niet vastgelegd',
      synonym_name: productName(item.right),
      synonym_store: item.right.store_name || 'Niet vastgelegd',
    })))
  }, [])

  useEffect(() => {
    const controller = new AbortController()
    setActiveArticle(articleId)
    setLoading(true)
    setError('')
    setSelected(new Set())
    refresh(controller.signal)
      .catch((err) => {
        if (!controller.signal.aborted) {
          setItems([])
          setArticles([])
          setError(err.message)
        }
      })
      .finally(() => { if (!controller.signal.aborted) setLoading(false) })
    return () => controller.abort()
  }, [articleId, refresh])

  function toggle(id) {
    setSelected((current) => {
      const next = new Set(current)
      if (next.has(id)) next.delete(id)
      else if (next.size < 200) next.add(id)
      return next
    })
  }

  async function link() {
    if (savingRef.current || !selected.size) return
    savingRef.current = true
    setSaving(true)
    setError('')
    const selections = items.filter((item) => selected.has(item.id)).map((item) => ({
      left_product_id: item.left.id, right_product_id: item.right.id, fingerprint: item.fingerprint,
    }))
    try {
      const response = await fetchJsonWithAuth(`${API}/link`, {
        method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ selections }),
      })
      const payload = await response.json()
      if (!response.ok) throw new Error(typeof payload.detail === 'string' ? payload.detail : 'Koppelen is niet gelukt. Probeer opnieuw.')
      await refresh()
      setSelected(new Set())
      showFeedback({ variant: 'success', message: `${payload.linked} suggestie(s) gekoppeld.` })
    } catch (err) {
      setError(err.message)
    } finally {
      savingRef.current = false
      setSaving(false)
    }
  }

  const currentArticle = articles.find((item) => item.id === activeArticle) || null
  const visibleItems = activeArticle
    ? items.filter((item) => item.left.id === activeArticle || item.right.id === activeArticle)
    : items

  const articleColumns = [
    { key: 'name', label: 'Artikelnaam', width: 315, sortable: true, filterable: true },
    { key: 'store', label: 'Winkel', width: 180, sortable: true, filterable: true },
    { key: 'synonym_count', label: 'Synoniemen', width: 115, sortable: true, align: 'right' },
    { key: 'candidate_count', label: 'Voorstellen', width: 115, sortable: true, align: 'right' },
    { key: 'status_label', label: 'Status', width: 170, sortable: true, filterable: true },
  ]
  const displayArticles = articles.map((item) => ({
    ...item,
    candidate_count: item.pending?.length || 0,
    status_label: item.status === 'insufficient'
      ? 'Winkel onbekend'
      : item.pending?.length
        ? 'Voorstellen beschikbaar'
        : 'Geen nieuwe voorstellen',
  }))

  const columns = [
    { key: 'select', label: '', width: 48, className: 'rz-check', cellClassName: 'rz-check', renderCell: (item) => <input type="checkbox"
      aria-label={`Selecteer ${item.article_name} (${item.article_store}) en ${item.synonym_name} (${item.synonym_store})`}
      checked={selected.has(item.id)} disabled={saving || (!selected.has(item.id) && selected.size >= 200)}
      onChange={() => toggle(item.id)} /> },
    { key: 'article_name', label: 'Artikelnaam', filterLabel: 'Filter op artikelnaam eerste winkel', width: 255, sortable: true, filterable: true },
    { key: 'article_photo', label: 'Foto artikel', width: 115, renderCell: (item) => <CatalogProductImage
      imageUrl={item.left.image_url} productName={item.article_name} compact /> },
    { key: 'article_store', label: 'Winkel', filterLabel: 'Filter op eerste winkel', width: 145, sortable: true, filterable: true },
    { key: 'synonym_name', label: 'Artikelnaam', filterLabel: 'Filter op artikelnaam tweede winkel', width: 255, sortable: true, filterable: true },
    { key: 'synonym_photo', label: 'Foto artikel', width: 115, renderCell: (item) => <CatalogProductImage
      imageUrl={item.right.image_url} productName={item.synonym_name} compact /> },
    { key: 'synonym_store', label: 'Winkel', filterLabel: 'Filter op tweede winkel', width: 145, sortable: true, filterable: true },
  ]

  return <AppShell title="Artikel-synoniemen" showExit={false}>
    <ScreenCard fullWidth>
      <h2>Artikel-synoniemen</h2>
      <p>Dubbelklik op een Catalogusartikel om de mogelijke synoniemen te bekijken. Bevestig uitsluitend juiste voorstellen met Koppelen.</p>
      <p>Artikelen zonder artikelcode of barcode vul je eerst aan in <Link to="/externe-databases-2">Externe databases 2</Link>.</p>
      {error ? <p role="alert">{error}</p> : null}
      <DataTable columns={articleColumns} data={displayArticles} getRowKey={(item) => item.id}
        pageSize={10} wrapperClassName="rz-synonym-analysis-table-wrapper"
        dataTestId="article-synonyms-articles"
        emptyMessage={loading ? 'Catalogusartikelen laden...' : error ? 'Artikelen niet beschikbaar.' : 'Geen gecodeerde Catalogusartikelen beschikbaar.'}
        renderRow={(item) => (
          <tr key={item.id} tabIndex={0} className="rz-synonym-analysis-main-row"
            aria-selected={activeArticle === item.id}
            aria-label={`Voorstellen voor ${item.name} openen`}
            title="Dubbelklik om voorstellen te bekijken"
            onDoubleClick={() => { setActiveArticle(item.id); setSelected(new Set()) }}
            onKeyDown={(event) => {
              if (event.key === 'Enter') {
                event.preventDefault()
                setActiveArticle(item.id)
                setSelected(new Set())
              }
            }}>
            <td><div className="rz-synonym-analysis-product">
              <CatalogProductImage imageUrl={item.image_url} productName={item.name} compact />
              <span>{item.name}</span>
            </div></td>
            <td>{item.store}</td>
            <td className="rz-num">{item.synonym_count}</td>
            <td className="rz-num">{item.candidate_count}</td>
            <td>{item.status_label}</td>
          </tr>
        )} />
      {activeArticle && !loading && !currentArticle ? <p role="status">Dit artikel is niet beschikbaar in het overzicht.</p> : null}
      {(currentArticle || (!activeArticle && visibleItems.length > 0)) ? <section className="rz-synonym-analysis-details" data-testid="article-synonyms-candidates">
        <h3>{currentArticle ? `Voorstellen voor ${currentArticle.name}` : 'Nieuwe synoniemsuggesties'}</h3>
        <DataTable columns={columns} data={visibleItems} getRowKey={(item) => item.id}
          pageSize={10} wrapperClassName="rz-synonym-analysis-table-wrapper"
          dataTestId="article-synonyms-table"
          emptyMessage={loading ? 'Suggesties laden...' : error ? 'Suggesties niet beschikbaar.' : currentArticle?.status === 'insufficient'
            ? 'Geen bevestigde winkelherkomst. Controleer de artikelkoppeling in Externe databases 2.'
            : 'Geen nieuwe synoniemsuggesties voor dit artikel.'}
          paginationActions={<><span aria-live="polite">{selected.size} geselecteerd</span>
            <Button disabled={loading || saving || !selected.size} onClick={link}>Koppelen</Button></>}
        />
      </section> : null}
    </ScreenCard>
  </AppShell>
}
