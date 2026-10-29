import { useEffect, useRef, useState } from 'react'
import { Link, useSearchParams } from 'react-router-dom'
import AppShell from '../../app/AppShell'
import ScreenCard from '../../ui/ScreenCard'
import DataTable from '../../ui/DataTable'
import Button from '../../ui/Button'
import CatalogProductImage from '../catalog/CatalogProductImage'
import { useAppFeedback } from '../../ui/AppFeedbackProvider'
import { fetchJsonWithAuth } from '../../lib/authSession'

const API = '/api/external-databases/article-synonyms'
const productName = (product) => [product.name, product.brand, product.variant].filter(Boolean).join(' · ')

export default function ArticleSynonymsPage() {
  const [searchParams] = useSearchParams()
  const articleId = searchParams.get('artikel') || ''
  const [items, setItems] = useState([])
  const [selected, setSelected] = useState(new Set())
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState('')
  const savingRef = useRef(false)
  const { showFeedback } = useAppFeedback()

  useEffect(() => {
    const controller = new AbortController()
    setLoading(true)
    setError('')
    setSelected(new Set())
    async function load() {
      try {
        const response = await fetchJsonWithAuth(API, { signal: controller.signal })
        if (!response.ok) throw new Error('Suggesties konden niet worden geladen.')
        const payload = await response.json()
        if (!controller.signal.aborted) setItems((payload.items || []).map((item) => ({
          ...item,
          article_name: productName(item.left),
          article_store: item.left.store_name || 'Niet vastgelegd',
          synonym_name: productName(item.right),
          synonym_store: item.right.store_name || 'Niet vastgelegd',
        })))
      } catch (err) {
        if (!controller.signal.aborted) { setItems([]); setError(err.message) }
      } finally {
        if (!controller.signal.aborted) setLoading(false)
      }
    }
    load()
    return () => controller.abort()
  }, [])

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
      setItems((current) => current.filter((item) => !selected.has(item.id)))
      setSelected(new Set())
      showFeedback({ variant: 'success', message: `${payload.linked} suggestie(s) gekoppeld.` })
    } catch (err) {
      setError(err.message)
    } finally {
      savingRef.current = false
      setSaving(false)
    }
  }

  const visibleItems = articleId ? items.filter((item) => item.left.id === articleId || item.right.id === articleId) : items

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
      <p>Controleer variant, bereiding en inhoud. Selecteer de juiste suggesties en bevestig met Koppelen. Een hoge score is geen zekerheid.</p>
      <p>Artikelen zonder artikelcode of barcode vul je eerst aan in <Link to="/externe-databases-2">Externe databases 2</Link>.</p>
      {error ? <p role="alert">{error}</p> : null}
      <DataTable columns={columns} data={visibleItems} getRowKey={(item) => item.id}
        pageSize={10}
        dataTestId="article-synonyms-table"
        emptyMessage={loading ? 'Suggesties laden...' : error ? 'Suggesties niet beschikbaar.' : 'Geen nieuwe suggesties voor artikelen met een code of barcode.'}
        paginationActions={<><span aria-live="polite">{selected.size} geselecteerd</span><Button disabled={loading || saving || !selected.size} onClick={link}>Koppelen</Button></>}
      />
    </ScreenCard>
  </AppShell>
}
