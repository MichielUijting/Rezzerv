import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import Button from '../../ui/Button'
import { fetchJsonWithAuth } from '../../lib/authSession'

const CBS_PAGE_SIZE = 100

async function readJson(url, signal) {
  const response = await fetchJsonWithAuth(url, { signal })
  const payload = await response.json().catch(() => ({}))
  if (!response.ok) throw new Error(typeof payload.detail === 'string' ? payload.detail : 'Werkvoorraad niet beschikbaar.')
  return payload
}

async function loadCbsBacklog(signal) {
  const first = await readJson('/api/cbs-classifications/products?limit=' + CBS_PAGE_SIZE + '&offset=0', signal)
  const total = Number(first.total)
  if (!Number.isSafeInteger(total) || total < 0 || !Array.isArray(first.items)) {
    throw new Error('CBS-totaal kon niet betrouwbaar worden vastgesteld.')
  }
  const items = [...first.items]
  while (items.length < total) {
    const next = await readJson('/api/cbs-classifications/products?limit=' + CBS_PAGE_SIZE + '&offset=' + items.length, signal)
    if (!Array.isArray(next.items) || !next.items.length || Number(next.total) !== total) {
      throw new Error('CBS-werkvoorraad veranderde tijdens ophalen. Vernieuw de monitor.')
    }
    items.push(...next.items)
  }
  return items.filter((item) => !item.classified).length
}

export default function ClassificationWorkMonitor({ counts, refreshVersion }) {
  const navigate = useNavigate()
  const [revision, setRevision] = useState(0)
  const [state, setState] = useState({ loading: true, cbs: null, synonyms: null, error: '' })

  useEffect(() => {
    const controller = new AbortController()
    setState({ loading: true, cbs: null, synonyms: null, error: '' })
    Promise.allSettled([
      loadCbsBacklog(controller.signal),
      readJson('/api/external-databases/article-synonyms/analysis', controller.signal),
    ]).then(([cbs, synonyms]) => {
      if (controller.signal.aborted) return
      const summary = synonyms.status === 'fulfilled' ? synonyms.value.summary : null
      const candidates = Number(summary?.candidate_pairs)
      const synonymCount = Number.isSafeInteger(candidates) && candidates >= 0 ? candidates : null
      setState({
        loading: false,
        cbs: cbs.status === 'fulfilled' ? cbs.value : null,
        synonyms: synonymCount,
        error: [cbs.status === 'rejected' ? 'CBS' : '', synonyms.status === 'rejected' || (synonyms.status === 'fulfilled' && synonymCount === null) ? 'Synoniemen' : '']
          .filter(Boolean).join(' en '),
      })
    })
    return () => controller.abort()
  }, [revision, refreshVersion])

  const pending = Number(counts?.classification_pending || 0)
  const unlinked = Number(counts?.unlinked || 0)
  return <section className="rz-classification-work-monitor" aria-label="Werkvoorraad classificeren en synchroniseren"
    data-testid="classification-work-monitor">
    <h3>Werkvoorraad</h3>
    <p>Werk eerst ontbrekende productkoppelingen weg, classificeer daarna GS1 en CBS en beoordeel vervolgens synoniemen. Bevestigde wijzigingen worden via de bestaande Inhuis-routes opgeslagen; deze monitor verandert zelf geen artikelgegevens.</p>
    <div className="rz-classification-work-grid">
      <div><strong>{unlinked}</strong><span>Nog niet gekoppeld (OFF)</span>
        <Button type="button" variant="secondary" onClick={() => document.getElementById('ed2-work-table')?.scrollIntoView({ behavior: 'smooth' })}>Artikelen bekijken</Button></div>
      <div><strong>{pending}</strong><span>GS1-classificatie ontbreekt na OFF-koppeling</span>
        <Button type="button" variant="secondary" onClick={() => document.getElementById('ed2-work-table')?.scrollIntoView({ behavior: 'smooth' })}>GS1 beoordelen</Button></div>
      <div><strong>{state.cbs === null ? '—' : state.cbs}</strong><span>CBS-classificaties ontbreken (Catalogus)</span>
        <Button type="button" variant="secondary" onClick={() => navigate('/catalogus/artikelclassificaties-toekennen')}>CBS beoordelen</Button></div>
      <div><strong>{state.synonyms === null ? '—' : state.synonyms}</strong><span>Voorgestelde synoniemparen te beoordelen</span>
        <Button type="button" variant="secondary" onClick={() => navigate('/artikelsynoniemen')}>Synoniemen beoordelen</Button></div>
    </div>
    <p data-testid="classification-sync-evidence"><strong>Synchronisatie:</strong> de overname van classificaties via bevestigde synoniemen is afzonderlijke functionaliteit die pas na goedkeuring beschikbaar komt. Een betrouwbare teller voor nog te verwerken of mislukte synchronisaties is nog niet beschikbaar; deze wordt daarom niet als nul weergegeven.</p>
    {state.loading ? <p role="status">Werkvoorraad ophalen…</p> : null}
    {state.error ? <p role="alert">{state.error} kon niet worden gemeten. De betreffende teller toont geen waarde; andere tellers blijven bruikbaar.</p> : null}
    <Button type="button" variant="secondary" disabled={state.loading} onClick={() => setRevision((value) => value + 1)}>Werkvoorraad vernieuwen</Button>
  </section>
}
