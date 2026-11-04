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
const codeOf = (article) => article?.primary_gtin || article?.article_codes?.[0] || '—'
const order = { linked: 0, suggested: 1, other: 2 }
const orderedPair = (left, right) => [left, right].sort()

export default function ArticleSynonymsPage() {
  const [searchParams] = useSearchParams()
  const [articles, setArticles] = useState([])
  const [activeArticle, setActiveArticle] = useState(searchParams.get('artikel') || '')
  const [options, setOptions] = useState([])
  const [checked, setChecked] = useState(new Set())
  const [loading, setLoading] = useState(true)
  const [loadingOptions, setLoadingOptions] = useState(false)
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState('')
  const savingRef = useRef(false)
  const { showFeedback } = useAppFeedback()

  const loadArticles = useCallback(async (signal) => {
    const response = await fetchJsonWithAuth(`${API}/analysis`, { signal })
    if (!response.ok) throw new Error('Catalogusartikelen konden niet worden geladen.')
    const result = await response.json()
    if (!signal?.aborted) setArticles(result.items || [])
  }, [])

  const loadOptions = useCallback(async (id, signal) => {
    const response = await fetchJsonWithAuth(`${API}/analysis/${encodeURIComponent(id)}/options`, { signal })
    if (!response.ok) throw new Error('Synoniemrelaties konden niet worden geladen.')
    const result = await response.json()
    if (!signal?.aborted) setOptions(result.items || [])
  }, [])

  useEffect(() => {
    const controller = new AbortController()
    setLoading(true)
    loadArticles(controller.signal)
      .catch((err) => { if (!controller.signal.aborted) setError(err.message) })
      .finally(() => { if (!controller.signal.aborted) setLoading(false) })
    return () => controller.abort()
  }, [loadArticles])

  useEffect(() => {
    const controller = new AbortController()
    setChecked(new Set())
    setOptions([])
    if (!activeArticle) return () => controller.abort()
    setLoadingOptions(true)
    loadOptions(activeArticle, controller.signal)
      .catch((err) => { if (!controller.signal.aborted) setError(err.message) })
      .finally(() => { if (!controller.signal.aborted) setLoadingOptions(false) })
    return () => controller.abort()
  }, [activeArticle, loadOptions])

  function chooseArticle(id) {
    if (savingRef.current || loadingOptions) return
    setError('')
    setActiveArticle(id)
    setChecked(new Set())
  }

  function toggle(item) {
    if (savingRef.current || loadingOptions || (!item.linkable && item.status !== 'linked')) return
    setChecked((previous) => {
      const next = new Set(previous)
      if (next.has(item.id)) next.delete(item.id)
      else if (next.size < 200) next.add(item.id)
      return next
    })
  }

  const currentArticle = articles.find((item) => item.id === activeArticle)
  const rightRows = [...options].sort((a, b) =>
    order[a.status] - order[b.status]
    || (b.score || 0) - (a.score || 0)
    || a.name.localeCompare(b.name, 'nl') || a.id.localeCompare(b.id)
  )
  const selectedLinks = options.filter((item) => checked.has(item.id) && item.status !== 'linked' && item.linkable)
  const selectedUnlinks = options.filter((item) => checked.has(item.id) && item.status === 'linked')

  async function changeLinks(action) {
    if (savingRef.current || loadingOptions || !activeArticle) return
    const targets = action === 'unlink' ? selectedUnlinks : selectedLinks
    if (!targets.length) return
    const selections = targets.map((item) => {
      const ids = orderedPair(activeArticle, item.id)
      return {
        left_product_id: ids[0],
        right_product_id: ids[1],
        fingerprint: item.fingerprint,
        ...(action === 'link' ? { manual: Boolean(item.manual) } : {}),
      }
    })
    if (selections.some((entry) => entry.left_product_id === entry.right_product_id)) {
      setError('Een artikel kan niet aan zichzelf worden gekoppeld.')
      return
    }
    savingRef.current = true
    setSaving(true)
    setError('')
    try {
      const response = await fetchJsonWithAuth(`${API}/${action}`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ selections }),
      })
      const result = await response.json()
      if (!response.ok) throw new Error(
        typeof result.detail === 'string' ? result.detail : 'De synoniemrelaties konden niet worden bijgewerkt.'
      )
      await Promise.all([loadArticles(), loadOptions(activeArticle)])
      setChecked(new Set())
      const number = action === 'unlink' ? result.unlinked : result.linked
      showFeedback({
        variant: 'success',
        message: action === 'unlink'
          ? `${number} synoniemkoppeling(en) verwijderd.`
          : `${number} synoniemkoppeling(en) bevestigd.`,
      })
    } catch (err) {
      setError(err.message)
    } finally {
      savingRef.current = false
      setSaving(false)
    }
  }

  const leftColumns = [
    { key: 'selected', label: '', width: 42 },
    { key: 'photo', label: 'Foto', width: 70 },
    { key: 'name', label: 'Artikelnaam', width: 250, sortable: true, filterable: true },
    { key: 'code', label: 'Barcode', width: 150, sortable: true, filterable: true },
  ]
  const rightColumns = [
    { key: 'selected', label: '', width: 42 },
    { key: 'photo', label: 'Foto', width: 70 },
    { key: 'name', label: 'Artikelnaam', width: 250, sortable: true, filterable: true },
    { key: 'code', label: 'Barcode', width: 150, sortable: true, filterable: true },
  ]
  return <AppShell title="Artikel-synoniemen" showExit={false}>
    <ScreenCard fullWidth>
      <h2>Artikel-synoniemen</h2>
      <div className="rz-synonym-side-by-side">
        <section className="rz-synonym-side" aria-label="Catalogusartikelen links">
          <h3>Artikel kiezen</h3>
          <DataTable columns={leftColumns}
            data={articles.map((item) => ({ ...item, code: codeOf(item) }))}
            getRowKey={(item) => item.id} pageSize={10}
            wrapperClassName="rz-synonym-analysis-table-wrapper"
            dataTestId="article-synonyms-articles"
            emptyMessage={loading ? 'Catalogusartikelen laden...' : 'Geen gecodeerde Catalogusartikelen.'}
            renderRow={(item) => <tr key={item.id}
              className="rz-synonym-analysis-main-row"
              tabIndex={0} aria-selected={activeArticle === item.id}
              aria-label={`Artikel kiezen: ${item.name}, barcode ${item.code}`}
              onClick={() => chooseArticle(item.id)}
              onKeyDown={(event) => {
                if (event.key === 'Enter' || event.key === ' ') {
                  event.preventDefault()
                  chooseArticle(item.id)
                }
              }}>
              <td><input type="checkbox" checked={activeArticle === item.id}
                aria-label={`Selecteer links ${item.name}, barcode ${item.code}`}
                disabled={saving || loadingOptions}
                onClick={(event) => event.stopPropagation()}
                onChange={() => chooseArticle(item.id)} /></td>
              <td><CatalogProductImage imageUrl={item.image_url} productName={item.name} compact /></td>
              <td>{item.name}</td>
              <td>{item.code}</td>
            </tr>} />
        </section>
        <section className="rz-synonym-side" aria-label="Synoniemen rechts">
          <h3>Te koppelen artikelen</h3>
          {error ? <p role="alert">{error}</p> : null}
          <DataTable columns={rightColumns}
            data={currentArticle ? rightRows.map((item) => ({ ...item, code: codeOf(item) })) : []}
            getRowKey={(item) => item.id} pageSize={10}
            wrapperClassName="rz-synonym-analysis-table-wrapper"
            dataTestId="article-synonyms-table"
            emptyMessage={!currentArticle
              ? 'Selecteer links één artikel.'
              : loadingOptions ? 'Artikelen laden...' : 'Geen andere gecodeerde artikelen.'}
            renderRow={(item) => <tr key={item.id}
              tabIndex={item.linkable || item.status === 'linked' ? 0 : -1}
              className={`rz-synonym-analysis-candidate-row rz-synonym-relation-${item.status}`}
              aria-selected={checked.has(item.id)}
              aria-label={`${item.status_label}: ${item.name}, barcode ${item.code}`}
              title={item.reason || item.status_label}
              onClick={() => toggle(item)}
              onKeyDown={(event) => {
                if ((event.key === 'Enter' || event.key === ' ') && (item.linkable || item.status === 'linked')) {
                  event.preventDefault()
                  toggle(item)
                }
              }}>
              <td><input type="checkbox"
                checked={checked.has(item.id)}
                disabled={saving || loadingOptions || (!item.linkable && item.status !== 'linked')}
                aria-label={`Selecteer rechts ${item.name}, barcode ${item.code} (${item.status_label})`}
                onClick={(event) => event.stopPropagation()}
                onChange={() => toggle(item)} /></td>
              <td><CatalogProductImage imageUrl={item.image_url} productName={item.name} compact /></td>
              <td>{item.name}</td>
              <td>{item.code}</td>
            </tr>}
            paginationActions={<div className="rz-synonym-analysis-actions">
              <Button disabled={loading || loadingOptions || saving || !selectedLinks.length}
                onClick={() => changeLinks('link')}>Koppelen</Button>
              <Button disabled={loading || loadingOptions || saving || !selectedUnlinks.length}
                onClick={() => changeLinks('unlink')}>Ontkoppelen</Button>
            </div>}
          />
        </section>
      </div>
      <p className="rz-synonym-footer-note">
        <Link to="/externe-databases-2">Externe databases 2</Link> — artikel zonder barcode aanvullen
      </p>
    </ScreenCard>
  </AppShell>
}
