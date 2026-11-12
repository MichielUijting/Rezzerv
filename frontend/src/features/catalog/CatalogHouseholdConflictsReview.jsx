import { useEffect, useMemo, useState } from 'react'
import Button from '../../ui/Button'
import Table from '../../ui/Table'
import Pagination from '../../ui/Pagination.jsx'
import { useAppFeedback } from '../../ui/AppFeedbackProvider.jsx'
import { fetchJsonWithAuth } from '../../lib/authSession'

const PAGE_SIZE = 10
const REVIEW_URL = '/api/catalog/household-identity-conflicts'

function reasonLabel(reason) {
  if (reason === 'meerdere_huishoudartikelen') return 'Meerdere huishoudartikelen bij één Catalogusproduct'
  if (reason === 'catalogusproduct_al_bezet') return 'Catalogusproduct al gekoppeld aan een huishoudartikel'
  return 'Tegenstrijdige bronidentiteiten of bestaande koppeling'
}

/** The conflict list is from the current authorized household, never from a user-provided household ID. */
export default function CatalogHouseholdConflictsReview({ onClose }) {
  const { showFeedback } = useAppFeedback()
  const [data, setData] = useState(null)
  const [loading, setLoading] = useState(true)
  const [refresh, setRefresh] = useState(0)
  const [page, setPage] = useState(1)
  const [sourcePage, setSourcePage] = useState(1)
  const [selectedArticle, setSelectedArticle] = useState(null)
  const [selectedSource, setSelectedSource] = useState(null)
  const [targetGtin, setTargetGtin] = useState('')
  const [saving, setSaving] = useState(false)

  useEffect(() => {
    let alive = true
    setLoading(true)
    fetchJsonWithAuth(REVIEW_URL)
      .then(async response => {
        const payload = await response.json().catch(() => ({}))
        if (!response.ok) throw new Error(typeof payload.detail === 'string'
          ? payload.detail : 'Historische conflicten konden niet worden geladen.')
        if (alive) {
          if (!payload.complete) {
            showFeedback({
              variant: 'error',
              message: 'De historische broncontrole is onvolledig. Beoordelen is geblokkeerd totdat alle bronregels zijn gecontroleerd.',
            })
          }
          setData(payload)
          setPage(1)
          setSelectedArticle(null)
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
  const pageCount = Math.max(1, Math.ceil(items.length / PAGE_SIZE))
  const visibleItems = items.slice((page - 1) * PAGE_SIZE, page * PAGE_SIZE)

  function productName(id) {
    const product = products.get(id)
    return product ? `${product.name || 'Catalogusproduct'} (${product.primary_gtin || 'geen barcode'})` : 'Catalogusidentiteit niet beschikbaar'
  }

  async function confirmSource() {
    if (!selectedArticle || !selectedSource || saving || !targetGtin.trim()) return
    setSaving(true)
    try {
      const response = await fetchJsonWithAuth(`${REVIEW_URL}/confirm-source`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          household_article_id: selectedArticle.household_article_id,
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
          ? 'De bonartikelcombinatie is bevestigd in Catalogus. Bestaande huishoudartikelen en voorraad zijn niet gewijzigd.'
          : 'De bonartikelcombinatie was al bevestigd. Huishoudartikelen zijn niet samengevoegd.',
      })
      setSelectedSource(null)
      setSelectedArticle(null)
      setTargetGtin('')
      setRefresh(value => value + 1)
    } catch (error) {
      showFeedback({ variant: 'error', message: error?.message || 'Bevestigen is mislukt.' })
    } finally {
      setSaving(false)
    }
  }

  return (
    <section aria-label="Historische Catalogusconflicten beoordelen" data-testid="catalog-historical-conflicts">
      <div className="rz-external-databases-actions">
        <h3>Historische Catalogusconflicten</h3>
        <Button type="button" variant="secondary" onClick={onClose}>Terug naar Catalogus</Button>
      </div>
      <p>Dit overzicht gebruikt uitsluitend de oorspronkelijke bonregels van je actieve huishouden.
        Beoordeel per winkel, kassabonomschrijving en bonartikelnummer de juiste Artikel-/barcode.
        Meerdere bonartikelnummers bij dezelfde omschrijving zijn toegestaan.
        Huishoudartikelen en voorraad worden nooit automatisch samengevoegd. Een conflict kan daarom na een juiste bronbevestiging nog apart beoordeeld moeten worden.</p>
      {loading ? <p>Historische bonregels controleren…</p> : null}
      {!loading && data ? (
        <>
          <p data-testid="catalog-conflict-count">
            Te beoordelen huishoudartikelen: {data.conflict_count} · Bronregels gecontroleerd: {data.source_rows_examined}
          </p>
          {data.complete && !items.length ? <p>Geen historische Catalogusconflicten aangetroffen in dit huishouden.</p> : null}
          {data.complete && items.length ? (
            <Table dataTestId="catalog-conflicts-table" tableClassName="rz-catalog-detail-table">
              <thead><tr>
                <th>Huishoudartikel</th><th>Reden</th><th>Cataloguskandidaten</th>
                <th>Bonregels</th><th>Actie</th>
              </tr></thead>
              <tbody>{visibleItems.map(item => (
                <tr key={item.household_article_id}>
                  <td>{item.article_name || 'Huishoudartikel zonder naam'}</td>
                  <td>{reasonLabel(item.reason)}</td>
                  <td>{item.candidate_product_ids?.map(productName).join(' · ') || 'Niet eenduidig'}</td>
                  <td>{item.source_count}</td>
                  <td><Button type="button" variant="secondary"
                    onClick={() => { setSelectedArticle(item); setSourcePage(1) }}>
                    Bonregels beoordelen
                  </Button></td>
                </tr>
              ))}</tbody>
            </Table>
          ) : null}
          {items.length > PAGE_SIZE ? (
            <Pagination page={page} pageCount={pageCount} onPageChange={setPage} />
          ) : null}
          {data.complete && selectedArticle ? (
            <section aria-label="Oorspronkelijke bonregels" data-testid="catalog-conflict-sources">
              <h3>Bonregels van {selectedArticle.article_name || 'huishoudartikel'}</h3>
              <p>Huidige Cataloguskoppeling: {selectedArticle.current_product_ids?.map(productName).join(' · ') || 'Ontbreekt'}</p>
              <Table dataTestId="catalog-conflict-sources-table" tableClassName="rz-catalog-detail-table">
                <thead><tr><th>Winkel</th><th>Kassabonomschrijving</th><th>Bonartikelnummer</th>
                  <th>Catalogusherkenning</th><th>Aantal bonregels</th><th>Actie</th></tr></thead>
                <tbody>{selectedArticle.sources.slice((sourcePage - 1) * PAGE_SIZE, sourcePage * PAGE_SIZE).map(source => (
                  <tr key={`${source.retailer_code}|${source.receipt_text}|${source.external_article_code}|${source.receipt_line_id}`}>
                    <td>{source.retailer_code || 'Onbekend'}</td>
                    <td>{source.receipt_text || 'Ontbreekt'}</td>
                    <td>{source.external_article_code || 'Ontbreekt'}</td>
                    <td>{source.candidate_product_id
                      ? productName(source.candidate_product_id)
                      : 'Nog niet eenduidig'}</td>
                    <td>{source.receipt_count}</td>
                    <td>{source.retailer_code && source.receipt_text && source.external_article_code
                      ? <Button type="button" variant="secondary" onClick={() => {
                          setSelectedSource(source)
                          setTargetGtin('')
                        }}>Barcode bepalen</Button>
                      : 'Bonbron onvoldoende'}</td>
                  </tr>
                ))}</tbody>
              </Table>
              {selectedArticle.sources.length > PAGE_SIZE ? (
                <Pagination page={sourcePage} pageCount={Math.ceil(selectedArticle.sources.length / PAGE_SIZE)} onPageChange={setSourcePage} />
              ) : null}
            </section>
          ) : null}
        </>
      ) : null}
      {selectedSource && selectedArticle ? (
        <div className="rz-modal-backdrop">
          <div className="rz-modal-card" role="dialog" aria-modal="true"
            aria-label="Artikelbarcode bij bonartikel bevestigen">
            <h3>Artikel-/barcode bepalen</h3>
            <p>Winkel: {selectedSource.retailer_code}</p>
            <p>Kassabonomschrijving: {selectedSource.receipt_text}</p>
            <p>Bonartikelnummer: {selectedSource.external_article_code}</p>
            <p>Kies bewust de juiste Catalogusbarcode. Een bestaande conflicterende of verouderde koppeling wordt geweigerd.</p>
            {selectedArticle.candidate_product_ids?.length ? (
              <div aria-label="Mogelijke Catalogusproducten">
                {selectedArticle.candidate_product_ids.map(id => {
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
