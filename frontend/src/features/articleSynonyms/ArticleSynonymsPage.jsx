import { useEffect, useRef, useState } from 'react'
import { Link } from 'react-router-dom'
import AppShell from '../../app/AppShell'
import ScreenCard from '../../ui/ScreenCard'
import DataTable from '../../ui/DataTable'
import Button from '../../ui/Button'
import { useAppFeedback } from '../../ui/AppFeedbackProvider'
import { fetchJsonWithAuth } from '../../lib/authSession'

const API = '/api/external-databases/article-synonyms'
const codeLabel = (product) => [product.primary_gtin, ...(product.article_codes || [])].filter(Boolean).join(' · ')
const sizeLabel = (product) => [product.size_value, product.size_unit].filter(Boolean).join(' ') || 'Onbekend'

export default function ArticleSynonymsPage() {
  const [items, setItems] = useState([])
  const [selected, setSelected] = useState(new Set())
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState('')
  const [revision, setRevision] = useState(0)
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
          ...item, article: [item.left.name, item.left.brand, item.left.variant].filter(Boolean).join(' · '),
          synonym: [item.right.name, item.right.brand, item.right.variant].filter(Boolean).join(' · '),
          article_code: codeLabel(item.left), synonym_code: codeLabel(item.right),
          packaging: `${sizeLabel(item.left)} / ${sizeLabel(item.right)}`,
          similarity: Math.round(item.score * 100),
        })))
      } catch (err) {
        if (!controller.signal.aborted) { setItems([]); setError(err.message) }
      } finally {
        if (!controller.signal.aborted) setLoading(false)
      }
    }
    load()
    return () => controller.abort()
  }, [revision])

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

  const columns = [
    { key: 'select', label: 'Selecteren', width: 90, renderCell: (item) => <input type="checkbox"
      aria-label={`Koppel ${item.article} aan ${item.synonym}`}
      checked={selected.has(item.id)} disabled={saving || (!selected.has(item.id) && selected.size >= 200)}
      onChange={() => toggle(item.id)} /> },
    { key: 'article', label: 'Artikel', width: 240, sortable: true, filterable: true },
    { key: 'article_code', label: 'Artikelcode / barcode', width: 210, sortable: true, filterable: true },
    { key: 'synonym', label: 'Voorgesteld synoniem', width: 240, sortable: true, filterable: true },
    { key: 'synonym_code', label: 'Code / barcode synoniem', width: 210, sortable: true, filterable: true },
    { key: 'packaging', label: 'Inhoud artikel / synoniem', width: 190, sortable: true, filterable: true },
    { key: 'similarity', label: 'Overeenkomst', width: 125, align: 'right', sortable: true, renderCell: (item) => `${item.similarity}%` },
  ]

  return <AppShell title="Artikelsynoniemen" showExit={false}>
    <ScreenCard fullWidth>
      <h2>Artikelsynoniemen</h2>
      <p>Controleer variant, bereiding en inhoud. Selecteer de juiste suggesties en bevestig met Koppelen. Een hoge score is geen zekerheid.</p>
      <p>Artikelen zonder artikelcode of barcode vul je eerst aan in <Link to="/externe-databases-2">Externe databases 2</Link>.</p>
      {error ? <p role="alert">{error}</p> : null}
      <DataTable columns={columns} data={items} getRowKey={(item) => item.id}
        defaultSort={{ key: 'similarity', direction: 'desc' }} pageSize={10}
        dataTestId="article-synonyms-table"
        emptyMessage={loading ? 'Suggesties laden...' : error ? 'Suggesties niet beschikbaar.' : 'Geen nieuwe suggesties voor artikelen met een code of barcode.'}
        paginationActions={<><span aria-live="polite">{selected.size} geselecteerd</span><Button disabled={loading || saving || !selected.size} onClick={link}>Koppelen</Button></>}
      />
      <Button variant="secondary" disabled={loading || saving} onClick={() => setRevision((current) => current + 1)}>Vernieuwen</Button>
    </ScreenCard>
  </AppShell>
}
