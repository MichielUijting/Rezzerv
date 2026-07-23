import { useEffect, useState } from 'react'
import { useNavigate, useParams } from 'react-router-dom'
import AppShell from '../../app/AppShell'
import ScreenCard from '../../ui/ScreenCard'
import Table from '../../ui/Table'
import Button from '../../ui/Button'
import { fetchJsonWithAuth } from '../../lib/authSession'
import './catalog.css'

function text(value, fallback = '-') {
  const normalized = String(value ?? '').trim()
  return normalized || fallback
}

export default function CatalogDetailPage() {
  const { globalProductId } = useParams()
  const navigate = useNavigate()
  const [detail, setDetail] = useState(null)
  const [isLoading, setIsLoading] = useState(true)
  const [error, setError] = useState('')

  useEffect(() => {
    let cancelled = false
    async function loadDetail() {
      setIsLoading(true)
      setError('')
      try {
        const response = await fetchJsonWithAuth(`/api/catalog/${encodeURIComponent(globalProductId)}`, { method: 'GET' })
        const data = await response.json().catch(() => ({}))
        if (!response.ok) throw new Error(data?.detail || 'Catalogusartikel kon niet worden geladen')
        if (!cancelled) setDetail(data)
      } catch (err) {
        if (!cancelled) setError(err?.message || 'Catalogusartikel kon niet worden geladen')
      } finally {
        if (!cancelled) setIsLoading(false)
      }
    }
    loadDetail()
    return () => { cancelled = true }
  }, [globalProductId])

  const product = detail?.product || {}
  const identities = Array.isArray(detail?.identities) ? detail.identities : []
  const householdArticles = Array.isArray(detail?.household_articles) ? detail.household_articles : []

  return (
    <AppShell title="Catalogusdetail" showExit={false}>
      <div className="rz-catalog-page" data-testid="catalog-detail-page">
        <ScreenCard fullWidth>
          <div className="rz-catalog-detail-actions">
            <Button type="button" variant="secondary" onClick={() => navigate('/catalogus')}>Terug naar Catalogus</Button>
          </div>

          {isLoading ? <div>Catalogusartikel laden...</div> : null}
          {error ? <div className="rz-inline-feedback rz-inline-feedback--error">{error}</div> : null}

          {!isLoading && !error ? (
            <div className="rz-catalog-detail-grid">
              <section>
                <h2>{text(product.name, 'Universeel artikel')}</h2>
                <dl className="rz-catalog-definition-list">
                  <div><dt>ID</dt><dd>{text(product.id)}</dd></div>
                  <div><dt>Merk</dt><dd>{text(product.brand)}</dd></div>
                  <div><dt>Primaire GTIN</dt><dd>{text(product.primary_gtin)}</dd></div>
                  <div><dt>Producttype</dt><dd>{text(product.product_type)}</dd></div>
                  <div><dt>Bron</dt><dd>{text(product.source)}</dd></div>
                  <div><dt>Kwaliteitsstatus</dt><dd>{text(product.quality_status)}</dd></div>
                </dl>
              </section>

              <section>
                <h3>Identiteiten</h3>
                <Table dataTestId="catalog-identities-table">
                  <thead><tr className="rz-table-header"><th>Type</th><th>Waarde</th><th>Primair</th><th>Bron</th></tr></thead>
                  <tbody>
                    {identities.length ? identities.map((identity, index) => (
                      <tr key={identity.id || `${identity.identity_type}-${identity.identity_value}-${index}`}>
                        <td>{text(identity.identity_type)}</td>
                        <td>{text(identity.identity_value)}</td>
                        <td>{identity.is_primary ? 'Ja' : 'Nee'}</td>
                        <td>{text(identity.source)}</td>
                      </tr>
                    )) : <tr><td colSpan="4">Geen aanvullende identiteiten gevonden.</td></tr>}
                  </tbody>
                </Table>
              </section>

              <section>
                <h3>Gekoppelde huishoudartikelen</h3>
                <Table dataTestId="catalog-household-articles-table">
                  <thead><tr className="rz-table-header"><th>Huishouden</th><th>Huishoudartikel</th><th>Minimum</th><th>Ideaal</th></tr></thead>
                  <tbody>
                    {householdArticles.length ? householdArticles.map((article, index) => (
                      <tr key={article.id || index}>
                        <td>{text(article.household_id)}</td>
                        <td>{text(article.name || article.article_name)}</td>
                        <td>{text(article.minimum_stock)}</td>
                        <td>{text(article.ideal_stock)}</td>
                      </tr>
                    )) : <tr><td colSpan="4">Geen gekoppelde huishoudartikelen gevonden.</td></tr>}
                  </tbody>
                </Table>
              </section>
            </div>
          ) : null}
        </ScreenCard>
      </div>
    </AppShell>
  )
}
