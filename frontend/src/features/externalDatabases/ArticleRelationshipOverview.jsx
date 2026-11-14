import { useEffect, useMemo, useRef, useState } from 'react'
import Button from '../../ui/Button'
import CatalogProductImage from '../catalog/CatalogProductImage'
import { fetchJsonWithAuth } from '../../lib/authSession'
import { buildArticleRelationshipGraph } from './articleRelationshipModel'
import './articleRelationshipOverview.css'

const SYNONYMS_API = '/api/external-databases/article-synonyms/analysis'
const RECEIPTS_API = '/api/external-databases/articles-overview'
const SHOPS = { ah: 'Albert Heijn', albert_heijn: 'Albert Heijn',
  lidl: 'Lidl', jumbo: 'Jumbo', aldi: 'Aldi', plus: 'PLUS', picnic: 'Picnic' }

async function readJson(url, signal) {
  const response = await fetchJsonWithAuth(url, { method: 'GET', signal })
  if (!response.ok) throw new Error('De opgeslagen artikelrelaties konden niet worden geladen.')
  return response.json()
}
function retailerName(row) {
  return SHOPS[row.retailer_code] || row.retailer_code || 'Winkel onbekend'
}
function ReceiptCard({ item, pending = false }) {
  return <div className={'rz-rel-receipt' + (pending ? ' rz-rel-receipt--pending' : '')}
    aria-label={'Bonartikel ' + retailerName(item) + ' ' + item.receipt_line_text}>
    <span className="rz-rel-receipt-icon" aria-hidden="true">▤</span>
    <div className="rz-rel-receipt-body">
      <small>Bonartikel · {retailerName(item)}</small>
      <strong>{item.receipt_line_text}</strong>
      <span>{item.receipt_article_number || 'Geen winkelartikelnummer'}</span>
      {pending ? <em>Identificatie nog te beoordelen</em> : null}
    </div>
  </div>
}
function CatalogCard({ product, isRoot = false }) {
  return <div className={'rz-rel-catalog' + (isRoot ? ' rz-rel-catalog--root' : '')}
    aria-label={'Catalogusartikel ' + product.name}>
    <div className="rz-rel-catalog-heading">◇ <span>Catalogusartikel</span></div>
    <div className="rz-rel-catalog-main">
      <CatalogProductImage compact imageUrl={product.image_url} productName={product.name} />
      <div><strong>{product.name}</strong>
        <span>{product.primary_gtin ? 'Barcode: ' + product.primary_gtin
          : 'Geen barcode vastgelegd'}</span>
      </div>
    </div>
  </div>
}
function MatchBranch({ item }) {
  return <div className="rz-rel-match-branch">
    <ReceiptCard item={item} />
    <div className="rz-rel-match-stem" aria-hidden="true" />
    <span className="rz-rel-edge-label rz-rel-edge-label--match">Match</span>
  </div>
}
function SynonymBranch({ entry }) {
  return <div className="rz-rel-synonym-branch">
    <div className="rz-rel-synonym-stem" aria-hidden="true" />
    <span className="rz-rel-edge-label rz-rel-edge-label--synonym">Synoniem</span>
    <CatalogCard product={entry.product} />
    {entry.receipts.length ? <div className="rz-rel-variant-receipts">
      {entry.receipts.map((receipt) => <div key={receipt.id} className="rz-rel-variant-match">
        <span className="rz-rel-edge-label rz-rel-edge-label--match">Match</span>
        <ReceiptCard item={receipt} />
      </div>)}
    </div> : <p className="rz-rel-variant-empty">Geen bevestigde bonartikelen</p>}
  </div>
}

export default function ArticleRelationshipOverview() {
  const [products, setProducts] = useState([])
  const [receipts, setReceipts] = useState([])
  const [options, setOptions] = useState([])
  const [search, setSearch] = useState('')
  const [selectedId, setSelectedId] = useState('')
  const [searchOpen, setSearchOpen] = useState(false)
  const [activeFilter, setActiveFilter] = useState('all')
  const [expanded, setExpanded] = useState(false)
  const [loading, setLoading] = useState(true)
  const [loadingLinks, setLoadingLinks] = useState(false)
  const [error, setError] = useState('')
  const [reloadCount, setReloadCount] = useState(0)
  const searchRef = useRef(null)

  useEffect(() => {
    const controller = new AbortController()
    setLoading(true)
    setError('')
    Promise.all([
      readJson(SYNONYMS_API, controller.signal),
      readJson(RECEIPTS_API, controller.signal),
    ]).then(([catalog, overview]) => {
      if (controller.signal.aborted) return
      setProducts(Array.isArray(catalog.items) ? catalog.items : [])
      setReceipts(Array.isArray(overview.items) ? overview.items : [])
    }).catch((err) => { if (!controller.signal.aborted) setError(err.message) })
      .finally(() => { if (!controller.signal.aborted) setLoading(false) })
    return () => controller.abort()
  }, [reloadCount])

  useEffect(() => {
    const controller = new AbortController()
    setOptions([])
    if (!selectedId) { setLoadingLinks(false); return () => controller.abort() }
    setLoadingLinks(true)
    readJson(SYNONYMS_API + '/' + encodeURIComponent(selectedId) + '/options', controller.signal)
      .then((result) => {
        if (!controller.signal.aborted) setOptions(Array.isArray(result.items) ? result.items : [])
      })
      .catch((err) => { if (!controller.signal.aborted) setError(err.message) })
      .finally(() => { if (!controller.signal.aborted) setLoadingLinks(false) })
    return () => controller.abort()
  }, [selectedId, reloadCount])

  const suggestions = useMemo(() => {
    const needle = search.trim().toLocaleLowerCase('nl')
    if (!needle) return []
    return products.filter((product) => [
      product.name, product.primary_gtin, ...(product.article_codes || []),
    ].some((value) => String(value || '').toLocaleLowerCase('nl').includes(needle)))
      .slice(0, 5)
  }, [products, search])
  const graph = useMemo(() =>
    buildArticleRelationshipGraph(products, receipts, options, selectedId),
  [products, receipts, options, selectedId])

  function selectArticle(product) {
    setSelectedId(String(product.id))
    setSearch(product.name + (product.primary_gtin ? ' — ' + product.primary_gtin : ''))
    setSearchOpen(false)
    setActiveFilter('all')
    setExpanded(false)
    setError('')
    searchRef.current?.blur()
  }

  const showMatches = activeFilter === 'all' || activeFilter === 'matches'
  const showSynonyms = activeFilter === 'all' || activeFilter === 'synonyms'
  const showPending = activeFilter === 'all' || activeFilter === 'pending'
  const rootMatches = graph?.rootReceipts || []
  const synonyms = graph?.synonyms || []
  const visibleMatches = expanded ? rootMatches : rootMatches.slice(0, 8)
  const visibleSynonyms = expanded ? synonyms : synonyms.slice(0, 8)
  const pending = graph?.pending || []
  const visiblePending = expanded ? pending : pending.slice(0, 8)

  return <section className="rz-rel-overview" aria-label="Relatieoverzicht"
    data-testid="article-relationship-overview">
    <div className="rz-rel-title"><h2>Relatieoverzicht</h2>
      <p>Ontdek welke bonartikelen bij hetzelfde Catalogusproduct horen en welke
        Catalogusproducten als synoniem zijn bevestigd.</p></div>
    <div className="rz-rel-search-bar">
      <label htmlFor="rz-rel-search">Catalogusartikel selecteren</label>
      <div className="rz-rel-search-wrap">
        <input ref={searchRef} id="rz-rel-search" type="search"
          autoComplete="off" value={search} disabled={loading}
          placeholder="Zoek op artikelnaam, barcode of artikelcode"
          aria-label="Catalogusartikel zoeken"
          aria-expanded={searchOpen && suggestions.length > 0}
          onFocus={() => setSearchOpen(true)}
          onChange={(event) => {
            setSearch(event.target.value)
            setSearchOpen(true)
            setSelectedId('')
            setOptions([])
          }}
          onKeyDown={(event) => {
            if (event.key === 'Escape') setSearchOpen(false)
            if (event.key === 'Enter' && searchOpen && suggestions[0]) {
              event.preventDefault(); selectArticle(suggestions[0])
            }
          }} />
        {searchOpen && suggestions.length > 0 ? <div className="rz-rel-search-options"
          aria-label="Catalogusartikelen kiezen">
          {suggestions.map((product) => <Button type="button" variant="secondary"
            key={product.id} className="rz-rel-search-option" onClick={() => selectArticle(product)}>
            {product.name}{product.primary_gtin ? ' · ' + product.primary_gtin : ''}
          </Button>)}
        </div> : null}
      </div>
      <Button type="button" variant="secondary" onClick={() => setReloadCount((count) => count + 1)}
        disabled={loading || loadingLinks}>Verversen</Button>
    </div>

    {error ? <div className="rz-rel-error" role="alert">{error}
      <Button type="button" variant="secondary" onClick={() => setReloadCount((count) => count + 1)}>
        Opnieuw proberen
      </Button></div> : null}
    {loading ? <p role="status">Relaties laden...</p> : null}
    {!loading && !error && !graph ? <div className="rz-rel-empty">
      <strong>Kies een Catalogusartikel</strong>
      <p>Zoek hierboven een artikel. Je ziet daarna alle bewezen matches en
        bevestigde synoniemen als een grafisch netwerk.</p>
    </div> : null}
    {!loading && !error && graph && <>
      <div className="rz-rel-filter-row" aria-label="Relaties filteren">
        {[
          ['all', 'Alles'], ['matches', 'Matches'],
          ['synonyms', 'Synoniemen'], ['pending', 'Nog te beoordelen'],
        ].map(([key, label]) => <Button key={key} type="button"
          aria-pressed={activeFilter === key}
          variant={activeFilter === key ? 'primary' : 'secondary'}
          onClick={() => setActiveFilter(key)}>{label}</Button>)}
      </div>
      {loadingLinks ? <p role="status">Synoniemrelaties controleren...</p> : null}
      {!loadingLinks ? <div className="rz-rel-layout">
        <div className="rz-rel-network" aria-label="Grafiek met bevestigde artikelrelaties">
          {showMatches && rootMatches.length > 0 ? <div className="rz-rel-main-matches">
            <div className="rz-rel-match-branches">
              {visibleMatches.map((item) => <MatchBranch key={item.id} item={item} />)}
            </div>
            <div className="rz-rel-main-connector" aria-hidden="true" />
          </div> : null}
          <div className="rz-rel-hub"><CatalogCard product={graph.root} isRoot /></div>
          {showSynonyms && synonyms.length > 0 ? <div className="rz-rel-synonyms">
            {visibleSynonyms.map((entry) => <SynonymBranch key={entry.product.id} entry={entry} />)}
          </div> : null}
          {showMatches && rootMatches.length === 0 && !showSynonyms
            ? <p className="rz-rel-muted">Geen bevestigde bonartikelmatches.</p> : null}
          {showSynonyms && synonyms.length === 0
            ? <p className="rz-rel-muted">Geen bevestigde synoniemrelaties voor dit product.</p> : null}
          {activeFilter === 'pending' ? <p className="rz-rel-muted">
            Alleen openstaande naamovereenkomsten, geen bevestigde koppelingen.
          </p> : null}
          {(rootMatches.length > 8 || synonyms.length > 8 || pending.length > 8) &&
            <Button type="button" variant="secondary"
              onClick={() => setExpanded((old) => !old)}>
              {expanded ? 'Minder tonen' : 'Alle relaties tonen'}
            </Button>}
        </div>
        <aside className="rz-rel-aside">
          <div className="rz-rel-panel">
            <h3>Overzicht</h3>
            <div className="rz-rel-stat rz-rel-stat--matches"><span aria-hidden="true">✓</span>
              <strong>{graph.counts.matches}</strong> matches
              {graph.counts.variantMatches ? <small>+ {graph.counts.variantMatches} bij synoniemen</small> : null}
            </div>
            <div className="rz-rel-stat rz-rel-stat--synonyms"><span aria-hidden="true">↔</span>
              <strong>{graph.counts.synonyms}</strong> synoniemen</div>
            <div className="rz-rel-stat rz-rel-stat--pending"><span aria-hidden="true">◷</span>
              <strong>{graph.counts.pending}</strong> nog te beoordelen</div>
          </div>
          <div className="rz-rel-panel">
            <h3>Legenda</h3>
            <div className="rz-rel-legend"><span aria-hidden="true">◇</span>
              <div><strong>Catalogusartikel</strong><p>Bewezen centraal product</p></div></div>
            <div className="rz-rel-legend"><span className="rz-rel-line--match" aria-hidden="true" />
              <div><strong>Match = zelfde product</strong>
                <p>Bonartikel hoort bij dit Catalogusproduct</p></div></div>
            <div className="rz-rel-legend"><span className="rz-rel-line--synonym" aria-hidden="true" />
              <div><strong>Synoniem = verwant product</strong>
                <p>Bevestigde koppeling tussen twee aparte Catalogusproducten</p></div></div>
          </div>
          {showPending ? <div className="rz-rel-panel rz-rel-pending">
            <h3>Nog te beoordelen</h3>
            <p>Exact gelijke bonnamen zonder bevestigde identiteit. Een naam is
              geen bewijs van een match.</p>
            {visiblePending.length > 0 ? visiblePending.map((item) =>
              <ReceiptCard key={item.id} item={item} pending />)
              : <span className="rz-rel-muted">Geen openstaande exacte naamovereenkomsten.</span>}
          </div> : null}
        </aside>
      </div> : null}
    </>}
  </section>
}