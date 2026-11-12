import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { useLocation, useNavigate } from 'react-router-dom'
import Button from '../../ui/Button'
import DataTable from '../../ui/DataTable.jsx'
import { useAppFeedback } from '../../ui/AppFeedbackProvider.jsx'
import { fetchJsonWithAuth, readStoredAuthContext } from '../../lib/authSession'

const PAGE_SIZE = 10
const REVIEW_URL = '/api/catalog/household-identity-conflicts'

function reasonLabel(reason) {
  if (reason === 'meerdere_huishoudartikelen') return 'Meerdere huishoudartikelen bij één Catalogusproduct'
  if (reason === 'catalogusproduct_al_bezet') return 'Catalogusproduct al gekoppeld aan een huishoudartikel'
  return 'Tegenstrijdige bronidentiteiten of bestaande koppeling'
}

/** The conflict list is from the current authorized household, never from a user-provided household ID. */
export default function CatalogHouseholdConflictsReview() {
  const location = useLocation()
  const navigate = useNavigate()
  const { showFeedback } = useAppFeedback()
  const context = readStoredAuthContext()
  const inSystemHousehold = context?.context_type === 'system'
    && context?.is_platform_superuser === true
    && String(context?.active_household_id) === '0'
  const reviewScope = inSystemHousehold ? 'Systeemhuishouden' : 'je actieve huishouden'
  const [data, setData] = useState(null)
  const [loading, setLoading] = useState(true)
  const [refresh, setRefresh] = useState(0)
  // React StrictMode replays effect setup on mount; share the same in-flight
  // GET instead of making duplicate household-scoped requests.
  const inFlightReviewRef = useRef(null)
  const [checkedArticleIds, setCheckedArticleIds] = useState([])
  const [articlePageRows, setArticlePageRows] = useState([])
  const [checkedSourceIds, setCheckedSourceIds] = useState([])
  const [sourcePageRows, setSourcePageRows] = useState([])
  const rememberArticlePageRows = useCallback(rows => {
    setArticlePageRows(previous =>
      previous.length === rows.length && previous.every((row, index) =>
        row.household_article_id === rows[index].household_article_id) ? previous : rows)
  }, [])
  const rememberSourcePageRows = useCallback(rows => {
    setSourcePageRows(previous =>
      previous.length === rows.length && previous.every((row, index) =>
        row.source_selection_key === rows[index].source_selection_key) ? previous : rows)
  }, [])
  const [selectedSource, setSelectedSource] = useState(null)
  const [targetGtin, setTargetGtin] = useState('')
  const [saving, setSaving] = useState(false)

  useEffect(() => {
    let alive = true
    setLoading(true)
    // The first StrictMode setup is cleaned up immediately, but the request
    // remains in flight. Its second setup may safely observe the same response.
    // After settlement, a later explicit refresh always fetches fresh data.
    if (!inFlightReviewRef.current) {
      const pending = fetchJsonWithAuth(REVIEW_URL).then(async response => {
        const payload = await response.json().catch(() => ({}))
        if (!response.ok) throw new Error(typeof payload.detail === 'string'
          ? payload.detail : 'Historische conflicten konden niet worden geladen.')
        return payload
      })
      inFlightReviewRef.current = pending
      pending.then(
        () => { if (inFlightReviewRef.current === pending) inFlightReviewRef.current = null },
        () => { if (inFlightReviewRef.current === pending) inFlightReviewRef.current = null },
      )
    }
    inFlightReviewRef.current
      .then(payload => {
        if (alive) {
          if (!payload.complete) {
            showFeedback({
              variant: 'error',
              message: 'De historische broncontrole is onvolledig. Beoordelen is geblokkeerd totdat alle bronregels zijn gecontroleerd.',
            })
          }
          setData(payload)
          setCheckedSourceIds([])
        }
      })
      .catch(error => {
        if (alive) showFeedback({ variant: 'error', message: error?.message || 'Ophalen is mislukt.' })
      })
      .finally(() => { if (alive) setLoading(false) })
    return () => { alive = false }
  }, [refresh, showFeedback])

  const items = useMemo(() => Array.isArray(data?.items) ? data.items : [], [data])
  const products = useMemo(() => new Map(
    (Array.isArray(data?.products) ? data.products : []).map(product => [product.id, product])
  ), [data])

  const reviewingIds = useMemo(
    () => (new URLSearchParams(location.search).get('artikelen') || '').split(',').filter(Boolean),
    [location.search],
  )
  const activeArticles = useMemo(
    () => items.filter(item => reviewingIds.includes(item.household_article_id)),
    [items, reviewingIds],
  )
  const sourceRows = useMemo(() => activeArticles.flatMap(article =>
    (article.sources || []).map(source => ({
      ...source,
      household_article_id: article.household_article_id,
      article_name: article.article_name,
      source_selection_key: [article.household_article_id, source.receipt_line_id,
        source.retailer_code, source.receipt_text, source.external_article_code].join('|'),
    }))
  ), [activeArticles])
  const selectedSources = sourceRows.filter(source => checkedSourceIds.includes(source.source_selection_key))
  const sourceArticle = activeArticles.find(article => article.household_article_id === selectedSource?.household_article_id)

  function toggleArticle(id, checked) {
    setCheckedArticleIds(previous => checked
      ? [...new Set([...previous, id])]
      : previous.filter(value => value !== id))
  }

  function toggleSource(id, checked) {
    setCheckedSourceIds(previous => checked
      ? [...new Set([...previous, id])]
      : previous.filter(value => value !== id))
  }

  function selectArticlePage(checked) {
    const ids = articlePageRows.map(item => item.household_article_id)
    setCheckedArticleIds(previous => checked
      ? [...new Set([...previous, ...ids])]
      : previous.filter(id => !ids.includes(id)))
  }

  function selectSourcePage(checked) {
    const ids = sourcePageRows.map(source => source.source_selection_key)
    setCheckedSourceIds(previous => checked
      ? [...new Set([...previous, ...ids])]
      : previous.filter(id => !ids.includes(id)))
  }

  function startSourceReview() {
    if (!checkedArticleIds.length) return
    const params = new URLSearchParams(location.search)
    params.set('artikelen', checkedArticleIds.join(','))
    navigate(`${location.pathname}?${params.toString()}`, { state: location.state })
    setCheckedSourceIds([])
  }

  function startBarcodeDecision() {
    const first = selectedSources[0]
    if (!first) return
    const sameIdentity = selectedSources.every(source => (
      source.retailer_code === first.retailer_code
      && source.receipt_text === first.receipt_text
      && source.external_article_code === first.external_article_code
    ))
    if (!sameIdentity) {
      showFeedback({
        variant: 'warning',
        dismissMode: 'ok-only',
        message: 'Je hebt verschillende bonartikelcombinaties geselecteerd. Beoordeel die afzonderlijk: ze mogen niet automatisch dezelfde barcode krijgen.',
      })
      return
    }
    setSelectedSource(first)
    setTargetGtin('')
  }

  function productName(id) {
    const product = products.get(id)
    return product ? `${product.name || 'Catalogusproduct'} (${product.primary_gtin || 'geen barcode'})` : 'Catalogusidentiteit niet beschikbaar'
  }

  // Both review tables use the shared Inhuis DataTable with its standard
  // filters, sorting, resizable columns, sticky headings and pagination.
  const conflictColumns = useMemo(() => [
    {
      key: 'select', label: 'Selecteren', width: 70,
      renderFilter: ({ placement }) => placement === 'header' ? (
        <input type="checkbox" aria-label="Alles: zichtbare huishoudartikelen"
          checked={articlePageRows.length > 0 && articlePageRows.every(item => checkedArticleIds.includes(item.household_article_id))}
          onChange={event => selectArticlePage(event.target.checked)} />
      ) : null,
      renderCell: item => (
        <input type="checkbox" aria-label={`Selecteer huishoudartikel ${item.article_name || item.household_article_id}`}
          checked={checkedArticleIds.includes(item.household_article_id)}
          onChange={event => toggleArticle(item.household_article_id, event.target.checked)} />
      ),
    },
    {
      key: 'article_name', label: 'Huishoudartikel', width: 245,
      sortable: true, filterable: true, filterPlaceholder: 'Zoek',
      getValue: item => item.article_name || 'Huishoudartikel zonder naam',
      renderCell: item => (
        <span title={item.article_name || 'Huishoudartikel zonder naam'}>
          {item.article_name || 'Huishoudartikel zonder naam'}
        </span>
      ),
    },
    {
      key: 'reason', label: 'Reden', width: 300,
      sortable: true, filterable: true,
      getValue: item => reasonLabel(item.reason),
      renderCell: item => <span title={reasonLabel(item.reason)}>{reasonLabel(item.reason)}</span>,
    },
    {
      key: 'candidates', label: 'Cataloguskandidaten', width: 340,
      sortable: true, filterable: true,
      getValue: item => item.candidate_product_ids?.map(id => {
        const product = products.get(id)
        return product ? `${product.name || 'Catalogusproduct'} (${product.primary_gtin || 'geen barcode'})`
          : 'Catalogusidentiteit niet beschikbaar'
      }).join(' · ') || 'Niet eenduidig',
      renderCell: item => {
        const value = item.candidate_product_ids?.map(id => {
          const product = products.get(id)
          return product ? `${product.name || 'Catalogusproduct'} (${product.primary_gtin || 'geen barcode'})`
            : 'Catalogusidentiteit niet beschikbaar'
        }).join(' · ') || 'Niet eenduidig'
        return <span title={value}>{value}</span>
      },
    },
    {
      key: 'source_count', label: 'Bonregels', width: 125, align: 'right',
      sortable: true, filterable: true,
      getValue: item => Number(item.source_count || 0),
      renderCell: item => Number(item.source_count || 0),
    },
  ], [products, checkedArticleIds, articlePageRows])

  const sourceColumns = useMemo(() => [
    {
      key: 'select', label: 'Selecteren', width: 70,
      renderFilter: ({ placement }) => placement === 'header' ? (
        <input type="checkbox" aria-label="Alles: zichtbare bonregels"
          checked={sourcePageRows.length > 0 && sourcePageRows.every(source => checkedSourceIds.includes(source.source_selection_key))}
          onChange={event => selectSourcePage(event.target.checked)} />
      ) : null,
      renderCell: source => (
        <input type="checkbox" aria-label={`Selecteer bonartikelnummer ${source.external_article_code || source.receipt_line_id}`}
          checked={checkedSourceIds.includes(source.source_selection_key)}
          onChange={event => toggleSource(source.source_selection_key, event.target.checked)} />
      ),
    },
    {
      key: 'article_name', label: 'Huishoudartikel', width: 210,
      sortable: true, filterable: true,
      getValue: source => source.article_name || 'Naam onbekend',
    },
    {
      key: 'retailer_code', label: 'Winkel', width: 155,
      sortable: true, filterable: true,
      getValue: source => source.retailer_code || 'Onbekend',
    },
    {
      key: 'receipt_text', label: 'Kassabonomschrijving', width: 300,
      sortable: true, filterable: true, filterPlaceholder: 'Zoek',
      getValue: source => source.receipt_text || 'Ontbreekt',
      renderCell: source => <span title={source.receipt_text || 'Ontbreekt'}>{source.receipt_text || 'Ontbreekt'}</span>,
    },
    {
      key: 'external_article_code', label: 'Bonartikelnummer', width: 190,
      sortable: true, filterable: true,
      getValue: source => source.external_article_code || 'Ontbreekt',
    },
    {
      key: 'candidate_product_id', label: 'Catalogusherkenning', width: 325,
      sortable: true, filterable: true,
      getValue: source => {
        const product = products.get(source.candidate_product_id)
        return product
          ? `${product.name || 'Catalogusproduct'} (${product.primary_gtin || 'geen barcode'})`
          : 'Nog niet eenduidig'
      },
      renderCell: source => {
        const product = products.get(source.candidate_product_id)
        const value = product
          ? `${product.name || 'Catalogusproduct'} (${product.primary_gtin || 'geen barcode'})`
          : 'Nog niet eenduidig'
        return <span title={value}>{value}</span>
      },
    },
    {
      key: 'receipt_count', label: 'Aantal bonregels', width: 150, align: 'right',
      sortable: true, filterable: true,
      getValue: source => Number(source.receipt_count || 0),
      renderCell: source => Number(source.receipt_count || 0),
    },
  ], [products, checkedSourceIds, sourcePageRows])

  async function confirmSource() {
    if (!selectedSource || saving || !targetGtin.trim()) return
    setSaving(true)
    try {
      const response = await fetchJsonWithAuth(`${REVIEW_URL}/confirm-source`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          household_article_id: selectedSource.household_article_id,
          receipt_line_id: selectedSource.receipt_line_id,
          retailer_code: selectedSource.retailer_code,
          receipt_text: selectedSource.receipt_text,
          external_article_code: selectedSource.external_article_code,
          target_gtin: targetGtin.trim(),
        }),
      })
      const result = await response.json().catch(() => ({}))
      if (!response.ok) {
        throw new Error(typeof result.detail === 'string'
          ? result.detail : 'De bonartikelcode kon niet veilig worden bevestigd.')
      }
      showFeedback({
        variant: 'success',
        message: result.changed
          ? 'De bonartikelcombinatie is centraal bevestigd. Dit lost eventuele dubbele huishoudartikelen niet op; voorraad en bestaande artikelen zijn ongewijzigd.'
          : 'De centrale boncode was al bevestigd. Het huishoudartikelconflict blijft afzonderlijk te beoordelen.',
      })
      setSelectedSource(null)
      setCheckedSourceIds([])
      setTargetGtin('')
      setRefresh(value => value + 1)
    } catch (error) {
      showFeedback({ variant: 'error', message: error?.message || 'Bevestigen is mislukt.' })
    } finally {
      setSaving(false)
    }
  }

  return (
    <section className="rz-catalog-historical-review" aria-label="Historische Catalogusconflicten beoordelen" data-testid="catalog-historical-conflicts">
      <h3>Historische Catalogusconflicten</h3>
      <p>Een conflict betekent niet automatisch dat de barcode fout is. Soms hebben twee
        huishoudartikelen dezelfde Cataloguskandidaat; die artikelen worden hier niet
        automatisch samengevoegd. Bonartikelnummer en barcode zijn verschillende gegevens.</p>
      {loading ? <p>Historische bonregels controleren…</p> : null}
      {!loading && data ? (
        <>
          <p data-testid="catalog-conflict-count">
            Te beoordelen huishoudartikelen: {data.conflict_count} · Bronregels gecontroleerd: {data.source_rows_examined}
          </p>
          {data.complete && !items.length ? (
            inSystemHousehold ? (
              <section aria-label="Beoordelen in regulier huishouden" data-testid="catalog-household-manager-guidance">
                <p>Er zijn geen historische conflicten in Systeemhuishouden. Dit zegt niets over
                  conflicten in de andere huishoudens.</p>
                <p>Wil je conflicten in een regulier huishouden beoordelen? Meld je aan met een
                  regulier account dat Beheerder is van dat huishouden en open daar
                  Catalogus → Historische conflicten beoordelen.
                  Een Frontteamrol is hiervoor niet nodig. Het Superuseraccount
                  krijgt geen toegang tot gegevens van andere huishoudens.</p>
              </section>
            ) : <p>Geen historische Catalogusconflicten aangetroffen in je actieve huishouden.</p>
          ) : null}
          {data.complete && items.length > 0 && reviewingIds.length === 0 ? (
            <>
              <p data-testid="catalog-conflicts-instruction">
                Stap 1. Vink één of meer huishoudartikelen aan. Kies daarna onder de tabel
                <strong> Bonregels beoordelen</strong>. Je kunt dan zien welke boncodes daarbij horen.
                Door alleen te bekijken verander je niets.
              </p>
              <DataTable
                columns={conflictColumns}
                data={items}
                getRowKey={item => item.household_article_id}
                onPageRowsChange={rememberArticlePageRows}
                dataTestId="catalog-conflicts-table"
                pagination
                pageSize={PAGE_SIZE}
                defaultSort={{ key: 'article_name', direction: 'asc' }}
                stickyHeader
                stickyFilters
                paginationActions={(
                  <Button type="button" disabled={!checkedArticleIds.length}
                    onClick={startSourceReview}>
                    Bonregels beoordelen ({checkedArticleIds.length})
                  </Button>
                )}
              />
            </>
          ) : null}
          {data.complete && activeArticles.length > 0 ? (
            <section aria-label="Oorspronkelijke bonregels" data-testid="catalog-conflict-sources">
              <h3>Waarom staan deze artikelen op de conflictlijst?</h3>
              {activeArticles.map(article => (
                <div key={article.household_article_id} data-testid="catalog-conflict-explanation">
                  <p><strong>{article.article_name || 'Huishoudartikel zonder naam'}</strong>:
                    {' '}{reasonLabel(article.reason)}.</p>
                  {article.related_household_articles?.length ? (
                    <p>Dezelfde Cataloguskandidaat komt ook voor bij:
                      {' '}{article.related_household_articles.map(peer =>
                        peer.article_name || 'Huishoudartikel zonder naam').join(' · ')}.
                      Dit bewijst niet dat de barcode onjuist is.</p>
                  ) : article.reason === 'catalogusproduct_al_bezet' ? (
                    <p>Dit Catalogusproduct heeft al een koppeling met een ander huishoudartikel.
                      Er is nog geen veilige keuze welk huishoudartikel moet blijven.</p>
                  ) : (
                    <p>De beschikbare bonbronnen of de bestaande Cataloguskoppeling spreken elkaar tegen.
                      Vergelijk de originele winkelgegevens voordat je een barcode kiest.</p>
                  )}
                  <p>Cataloguskandidaat:
                    {' '}{article.candidate_product_ids?.map(productName).join(' · ') || 'Nog niet eenduidig'}.
                    {' '}Huidige koppeling:
                    {' '}{article.current_product_ids?.map(productName).join(' · ') || 'Ontbreekt'}.</p>
                </div>
              ))}
              <p data-testid="catalog-source-instruction">
                Stap 2. Selecteer een bonregel. De winkel, bonomschrijving en het bonartikelnummer
                vormen samen de te beoordelen combinatie. Kies onder de tabel
                <strong> Barcode bepalen</strong> om een bewezen Catalogusbarcode te bevestigen.
                Verschillende bonartikelcombinaties beoordeel je afzonderlijk.
              </p>
              <DataTable
                key={reviewingIds.join('|')}
                columns={sourceColumns}
                data={sourceRows}
                getRowKey={source => source.source_selection_key}
                onPageRowsChange={rememberSourcePageRows}
                dataTestId="catalog-conflict-sources-table"
                pagination
                pageSize={PAGE_SIZE}
                defaultSort={{ key: 'receipt_text', direction: 'asc' }}
                stickyHeader
                stickyFilters
                paginationActions={(
                  <Button type="button" disabled={!checkedSourceIds.length}
                    onClick={startBarcodeDecision}>
                    Barcode bepalen ({checkedSourceIds.length})
                  </Button>
                )}
              />
              <p>Let op: het bevestigen van een boncode corrigeert alleen de centrale
                artikelherkenning. Dubbele huishoudartikelen blijven bestaan; hun
                geschiedenis en voorraad worden niet automatisch samengevoegd.
                Gebruik de terugknop van je browser om terug te keren naar de conflictlijst.</p>
            </section>
          ) : null}
        </>
      ) : null}
      {selectedSource && sourceArticle ? (
        <div className="rz-modal-backdrop">
          <div className="rz-modal-card" role="dialog" aria-modal="true"
            aria-label="Artikelbarcode bij bonartikel bevestigen">
            <h3>Artikel-/barcode bepalen</h3>
            <p>Winkel: {selectedSource.retailer_code}</p>
            <p>Kassabonomschrijving: {selectedSource.receipt_text}</p>
            <p>Bonartikelnummer: {selectedSource.external_article_code}</p>
            <p>Kies bewust de juiste Catalogusbarcode. Een bestaande conflicterende of verouderde koppeling wordt geweigerd.</p>
            {sourceArticle.candidate_product_ids?.length ? (
              <div aria-label="Mogelijke Catalogusproducten">
                {sourceArticle.candidate_product_ids.map(id => {
                  const product = products.get(id)
                  return product?.primary_gtin ? (
                    <Button key={id} type="button" variant="secondary"
                      onClick={() => setTargetGtin(product.primary_gtin)}>
                      {productName(id)}
                    </Button>
                  ) : null
                })}
              </div>
            ) : null}
            <label>Juiste Artikel-/barcode
              <input className="rz-input" inputMode="numeric" value={targetGtin}
                onChange={event => setTargetGtin(event.target.value)} />
            </label>
            <p>Bevestigen verandert alleen de centrale winkelcodekoppeling, niet de voorraad of bestaande huishoudartikelen.</p>
            <div className="rz-modal-actions">
              <Button type="button" variant="secondary" disabled={saving}
                onClick={() => { setSelectedSource(null); setTargetGtin('') }}>Annuleren</Button>
              <Button type="button" disabled={saving || !targetGtin.trim()} onClick={confirmSource}>
                {saving ? 'Controleren…' : 'Barcode bevestigen'}
              </Button>
            </div>
          </div>
        </div>
      ) : null}
    </section>
  )
}
